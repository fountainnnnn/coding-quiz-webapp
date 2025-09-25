# backend/src/core/openai_qg.py

import os, json, uuid, logging, re, asyncio
from typing import Dict, Any, List, TypedDict
from openai import AsyncOpenAI
from fastapi import HTTPException
from dotenv import load_dotenv

# ------------------------------------------------------------
# Ensure environment is loaded early
# ------------------------------------------------------------
load_dotenv()
logger = logging.getLogger("quiz.qg")

# ------------------------------------------------------------
# Types for clarity
# ------------------------------------------------------------
class SafeQuestion(TypedDict):
    question_id: str
    type: str
    question: str
    options: List[str] | None
    code_with_blanks: str | None

class SecretRecord(TypedDict):
    question_id: str
    answer: List[str]
    explanation: str

class QuestionResult(TypedDict):
    safe: List[SafeQuestion]
    secret: List[SecretRecord]

# ------------------------------------------------------------
# Global OpenAI client (async)
# ------------------------------------------------------------
_client: AsyncOpenAI | None = None

def configure_openai(api_key: str | None = None) -> AsyncOpenAI:
    """Create or reuse an AsyncOpenAI client."""
    global _client
    if _client is None:
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY missing. Provide via env or param.")
        _client = AsyncOpenAI(api_key=key)
        logger.info("OpenAI async client configured (global instance).")
    return _client

# ------------------------------------------------------------
# Prompt template
# ------------------------------------------------------------
QG_SYSTEM_TEMPLATE = (
    "You are a strict {language} quiz generator.\n"
    "Allowed topics: loops, arrays/lists, functions, conditionals, classes/objects, "
    "and other core {language} constructs.\n"
    "Allowed types: mcq, fill_code, drag_drop.\n\n"
    "Output rules:\n"
    "- Output ONLY JSON (no markdown, no commentary outside JSON).\n"
    "- You MUST return EXACTLY N questions.\n"
    "- If N >= 3, include at least 1 'mcq', 1 'fill_code', and 1 'drag_drop'.\n"
    "- Each item MUST have keys: ['type','question','options','code_with_blanks','answer','explanation'].\n"
    "- The 'question' text MUST NOT contain code — only describe the task.\n"
    "- All code must appear only in 'code_with_blanks'.\n"
    "- Never duplicate code in both 'question' and 'code_with_blanks'.\n\n"
    "Quality & Variety rules:\n"
    "- Ensure variety: conceptual, debugging, edge cases, off-by-one, nested loops, logic errors.\n"
    "- Vary difficulty within the batch.\n"
    "- Avoid trivial repetition across questions.\n"
    "- Explanations must be clear and correct.\n"
    "- Code must follow correct {language} syntax.\n"
    "- Always include a non-empty 'answer' and 'explanation'.\n"
)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _parse_json_response(text: str) -> List[Dict[str, Any]]:
    if not text:
        raise HTTPException(status_code=500, detail="Empty response from model")

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "questions" in data and isinstance(data["questions"], list):
            return data["questions"]
    except Exception:
        pass

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        snippet = text[start:end+1]
        try:
            return json.loads(snippet)
        except Exception:
            pass

    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "questions" in data:
            return data["questions"]
    except Exception as e:
        logger.error(f"Failed after cleaning JSON: {e}")

    raise HTTPException(status_code=500, detail=f"Invalid JSON from model. Raw output: {text[:500]}...")

def _normalize_answer(qtype: str, ans: Any) -> List[str]:
    """Normalize answers into comparable lists of strings."""
    if isinstance(ans, list):
        return [str(x).strip(" '\"\n") for x in ans]

    if isinstance(ans, str):
        s = ans.strip()
        # Handle JSON-like arrays: "[2, 4, 6]"
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s.replace("'", '"'))
                if isinstance(arr, list):
                    return [str(x).strip(" '\"\n") for x in arr]
            except Exception:
                # fallback: split manually
                return [x.strip(" '\"\n") for x in re.split(r"[,\n]", s[1:-1]) if x.strip()]
        # Handle CSV or newline separated
        if "," in s or "\n" in s:
            return [x.strip(" '\"\n") for x in re.split(r"[,\n]", s) if x.strip()]
        return [s.strip(" '\"\n")]

    return [str(ans).strip(" '\"\n")]

def _normalize_blanks(qtype: str, code: str | None, ans: List[str]) -> str | None:
    if qtype != "fill_code" or not code:
        return code
    if "___" not in code and ans:
        for a in ans:
            code = code.replace(a, "___", 1)
    return code

def _normalize_options(opts: Any) -> List[str] | None:
    if opts is None:
        return None
    if isinstance(opts, list):
        normed = []
        for o in opts:
            if isinstance(o, str):
                normed.append(o.strip())
            elif isinstance(o, dict):
                if "content" in o:
                    normed.append(str(o["content"]))
                elif "loop" in o and "output" in o:
                    normed.append(f"{o['loop']} -> {o['output']}")
                else:
                    normed.append(json.dumps(o, ensure_ascii=False))
            else:
                normed.append(str(o))
        return normed
    return [str(opts)]

def _deduplicate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique_items = []
    for q in items:
        sig = (q.get("question", ""), q.get("code_with_blanks", ""))
        if sig not in seen:
            seen.add(sig)
            unique_items.append(q)
    return unique_items

# ------------------------------------------------------------
# Main generator (async with parallel batching)
# ------------------------------------------------------------
async def generate_questions(
    language: str = "JavaScript",
    topic: str = "loops",
    difficulty: str = "mixed",
    n: int = 10,
    model_name: str = "gpt-4o-mini",
    api_key: str | None = None,
    batch_size: int = 1,  # set 1 for max parallelism, >1 for fewer calls
) -> QuestionResult:
    client = configure_openai(api_key)
    system_prompt = QG_SYSTEM_TEMPLATE.format(language=language)

    async def request_batch(batch_n: int) -> List[Dict[str, Any]]:
        if topic.lower() == "mixed":
            topic_instruction = f"across a variety of {language} topics (loops, arrays/lists, functions, conditionals, classes/objects)"
        else:
            topic_instruction = f"about {topic}"

        user_prompt = (
            f"Generate {batch_n} {difficulty} {language} quiz questions {topic_instruction}. "
            f"The set MUST include a balanced mix of mcq, fill_code, and drag_drop types if N >= 3. "
            f"Return a JSON list with exactly {batch_n} objects."
        )

        resp = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = resp.choices[0].message.content or ""
        return _parse_json_response(raw)

    # ---- Split into batches
    tasks = []
    full_batches, remainder = divmod(n, batch_size)
    for _ in range(full_batches):
        tasks.append(request_batch(batch_size))
    if remainder:
        tasks.append(request_batch(remainder))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    items: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Batch failed: {r}")
            continue
        items.extend(r)

    # Deduplicate
    items = _deduplicate(items)

    # Ensure we hit exact n
    while len(items) < n:
        missing = n - len(items)
        logger.warning(f"Missing {missing}, requesting extras...")
        extras = await asyncio.gather(*[request_batch(1) for _ in range(missing)])
        for e in extras:
            if not isinstance(e, Exception):
                items.extend(e)
        items = _deduplicate(items)

    if len(items) > n:
        items = items[:n]

    # ---- Build safe & secret
    safe_list: List[SafeQuestion] = []
    secret_list: List[SecretRecord] = []

    for q in items:
        qid = str(uuid.uuid4())
        ans_list = _normalize_answer(q.get("type"), q.get("answer"))
        code_with_blanks = _normalize_blanks(q.get("type"), q.get("code_with_blanks"), ans_list)

        safe_list.append(
            {
                "question_id": qid,
                "type": q.get("type"),
                "question": q.get("question"),
                "options": _normalize_options(q.get("options")),
                "code_with_blanks": code_with_blanks,
            }
        )
        secret_list.append(
            {
                "question_id": qid,
                "answer": ans_list,
                "explanation": q.get("explanation"),
            }
        )

    logger.info(f"Generated {len(safe_list)} unique questions successfully in parallel batches.")
    return {"safe": safe_list, "secret": secret_list}
