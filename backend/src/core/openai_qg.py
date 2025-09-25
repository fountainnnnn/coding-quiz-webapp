import os, json, uuid, logging, re, time
from typing import Dict, Any, List, TypedDict
from openai import OpenAI
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
# OpenAI client
# ------------------------------------------------------------
def configure_openai(api_key: str | None = None) -> OpenAI:
    """Create an OpenAI client with the given API key or environment variable."""
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing. Provide via env or param.")
    logger.info("OpenAI client configured (key present).")
    return OpenAI(api_key=key)


# ------------------------------------------------------------
# Prompt template
# ------------------------------------------------------------
QG_SYSTEM_TEMPLATE = (
    "You are a strict {language} quiz generator.\n"
    "Allowed topics: loops (for/while), arrays/lists, functions, conditionals, classes/objects, "
    "and other common {language} constructs.\n"
    "Allowed types: mcq, fill_code, drag_drop.\n\n"
    "Output rules:\n"
    "- Output ONLY JSON (no markdown, no commentary outside JSON).\n"
    "- You MUST return EXACTLY N questions, no fewer and no more. "
    "N is provided in the user prompt.\n"
    "- If N >= 3, the list MUST include at least 1 'mcq', 1 'fill_code', and 1 'drag_drop'.\n"
    "- Each item MUST have keys: ['type','question','options','code_with_blanks','answer','explanation'].\n\n"
    "Formatting rules:\n"
    "- 'question': concise natural-language instruction ONLY (do not embed code here).\n"
    "- 'code_with_blanks': include properly indented code with ___ placeholders for blanks (ONLY for fill_code).\n"
    "- 'mcq': provide exactly 4 plausible options, one correct.\n"
    "- 'drag_drop': 'options' must be a list of items to arrange; 'answer' must be the correct ordered list.\n\n"
    "Quality rules:\n"
    "- Avoid trivial or repetitive questions; vary between syntax, logic, debugging, and small problem-solving tasks.\n"
    "- Mix simple and slightly tricky cases (e.g., off-by-one loops, nested loops, array indexing edge cases, function returns).\n"
    "- Explanations must be clear, technically correct, and show reasoning (why the answer works, why distractors fail).\n"
    "- Ensure code snippets follow correct {language} syntax.\n"
    "- Do not repeat code inside 'question'.\n"
    "- Always include a non-empty 'answer' and 'explanation'.\n"
    "- If you fail to generate exactly N, your output is invalid.\n"
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _parse_json_response(text: str) -> List[Dict[str, Any]]:
    """Parse raw model output into a valid JSON list of questions."""
    if not text:
        raise HTTPException(status_code=500, detail="Empty response from model")

    logger.warning(f"Raw model output:\n{text}\n")

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "questions" in data and isinstance(data["questions"], list):
                return data["questions"]
            raise ValueError("Root object is dict without 'questions' key")
    except Exception:
        pass

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        snippet = text[start:end+1]
        try:
            return json.loads(snippet)
        except Exception as e:
            logger.error(f"Failed to parse extracted snippet: {e}")

    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "questions" in data and isinstance(data["questions"], list):
            return data["questions"]
    except Exception as e:
        logger.error(f"Failed after cleaning JSON: {e}")

    raise HTTPException(
        status_code=500,
        detail=f"Invalid JSON from model. Raw output (truncated): {text[:500]}..."
    )


def _normalize_answer(qtype: str, ans: Any) -> List[str]:
    """Normalize answer field into a list of strings with robust handling."""
    if isinstance(ans, list):
        return [str(x).strip(" '\"") for x in ans]

    if isinstance(ans, str):
        s = ans.strip()

        # Case: "[1, 3, 5]"
        if s.startswith("[") and s.endswith("]"):
            cleaned = s[1:-1]
            return [x.strip(" '\"") for x in cleaned.split(",") if x.strip()]

        # Case: "'1', '3', '5'"
        if "," in s:
            return [x.strip(" '\"") for x in s.split(",") if x.strip()]

        # Case: single value
        return [s.strip(" '\"")]

    return [str(ans).strip(" '\"")]


def _normalize_blanks(qtype: str, code: str | None, ans: List[str]) -> str | None:
    """Ensure code_with_blanks always has ___ placeholders for fill_code questions."""
    if qtype != "fill_code" or not code:
        return code

    if "___" not in code and ans:
        for a in ans:
            code = code.replace(a, "___", 1)
    return code


# ------------------------------------------------------------
# Main generator
# ------------------------------------------------------------
def generate_questions(
    language: str = "JavaScript",
    topic: str = "loops",
    difficulty: str = "mixed",
    n: int = 10,
    model_name: str = "gpt-4o-mini",
    api_key: str | None = None,
    max_retries: int = 3,
) -> QuestionResult:
    client = configure_openai(api_key)
    system_prompt = QG_SYSTEM_TEMPLATE.format(language=language)

    attempt = 0
    items: List[Dict[str, Any]] = []

    while attempt < max_retries:
        attempt += 1
        user_prompt = (
            f"Generate {n} {difficulty} {language} quiz questions about {topic}. "
            f"The set MUST include a balanced mix of mcq, fill_code, and drag_drop question types "
            f"(at least 1 of each if N >= 3). "
            f"Return a JSON list with exactly {n} objects. "
            f"If you return fewer or more, the output is invalid."
        )

        logger.info(
            f"Attempt {attempt}/{max_retries}: requesting {n} questions "
            f"on {topic} ({difficulty}) in {language} using {model_name}"
        )

        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw = resp.choices[0].message.content or ""
        items = _parse_json_response(raw)

        if len(items) == n:
            logger.info(f"Model returned correct count ({n}) on attempt {attempt}")
            break
        else:
            logger.warning(f"Model returned {len(items)} questions (expected {n}). Retrying...")
            time.sleep(1.0)
            items = []

    if not items or len(items) != n:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate exactly {n} questions after {max_retries} attempts."
        )

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
                "options": q.get("options"),
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

    logger.info(f"Generated {len(safe_list)} questions successfully.")
    return {"safe": safe_list, "secret": secret_list}
