# backend/src/core/openai_qg.py

import os, json, uuid, logging, re
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
    answer: Any
    explanation: str


class QuestionResult(TypedDict):
    safe: List[SafeQuestion]
    secret: List[SecretRecord]


# ------------------------------------------------------------
# OpenAI client
# ------------------------------------------------------------
def configure_openai(api_key: str | None = None) -> OpenAI:
    """
    Create an OpenAI client with the given API key or environment variable.
    """
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing. Provide via env or param.")
    logger.info("OpenAI client configured (key present).")
    return OpenAI(api_key=key)


# ------------------------------------------------------------
# Prompt template
# ------------------------------------------------------------
QG_SYSTEM = (
    "You are a strict JavaScript quiz generator. "
    "Allowed topics: for/while loops, arrays, functions. "
    "Allowed types: mcq, fill_code, drag_drop.\n\n"
    "Rules:\n"
    "- Output ONLY JSON (no markdown, no explanations outside JSON).\n"
    "- Return a JSON list with exactly N objects (N is provided in the user prompt).\n"
    "- The list MUST include a mix of question types (at least 1 mcq, 1 fill_code, and 1 drag_drop if N >= 3).\n"
    "- Keys: ['type','question','options','code_with_blanks','answer','explanation'].\n"
    "- For 'mcq': include exactly 4 plausible options, one correct.\n"
    "- For 'fill_code': return code_with_blanks with proper indentation and ___ placeholders for blanks.\n"
    "- For 'drag_drop': 'options' must be a list of items to arrange; 'answer' must be the correct ordered list.\n"
    "- Always include an 'answer' and an 'explanation'.\n"
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _parse_json_response(text: str) -> List[Dict[str, Any]]:
    """
    Parse raw model output into a valid JSON list of questions.
    Tries to be tolerant of extra formatting.
    """
    if not text:
        raise HTTPException(status_code=500, detail="Empty response from model")

    logger.warning(f"Raw model output:\n{text}\n")

    # Direct attempt
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except Exception:
        pass

    # Extract JSON array
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        snippet = text[start:end+1]
        try:
            return json.loads(snippet)
        except Exception as e:
            logger.error(f"Failed to parse extracted snippet: {e}")

    # Clean common issues (e.g., trailing commas)
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
    except Exception as e:
        logger.error(f"Failed after cleaning JSON: {e}")

    raise HTTPException(
        status_code=500,
        detail=f"Invalid JSON from model. Raw output (truncated): {text[:500]}..."
    )


# ------------------------------------------------------------
# Main generator
# ------------------------------------------------------------
def generate_questions(
    topic: str = "loops",
    difficulty: str = "mixed",
    n: int = 10,
    model_name: str = "gpt-4o-mini",
    api_key: str | None = None,
) -> QuestionResult:
    """
    Generate N JavaScript quiz questions using OpenAI.
    """
    client = configure_openai(api_key)

    user_prompt = (
        f"Generate {n} {difficulty} JavaScript quiz questions about {topic}. "
        f"The set MUST include a balanced mix of mcq, fill_code, and drag_drop question types "
        f"(at least 1 of each if N >= 3). "
        f"Return a JSON list with exactly {n} objects."
    )

    logger.info(f"Requesting {n} questions on {topic} ({difficulty}) from {model_name}")

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": QG_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw = resp.choices[0].message.content or ""
    items = _parse_json_response(raw)

    safe_list: List[SafeQuestion] = []
    secret_list: List[SecretRecord] = []

    for q in items:
        qid = str(uuid.uuid4())
        safe_list.append(
            {
                "question_id": qid,
                "type": q.get("type"),
                "question": q.get("question"),
                "options": q.get("options"),
                "code_with_blanks": q.get("code_with_blanks"),
            }
        )
        secret_list.append(
            {
                "question_id": qid,
                "answer": q.get("answer"),
                "explanation": q.get("explanation"),
            }
        )

    logger.info(f"Generated {len(safe_list)} questions successfully.")
    return {"safe": safe_list, "secret": secret_list}
