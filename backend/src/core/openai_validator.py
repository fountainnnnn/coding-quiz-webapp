import os, json, re
from typing import Dict, Any
from fastapi import HTTPException
from openai import OpenAI

def configure_openai(api_key: str | None = None) -> OpenAI:
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing. Provide via env or param.")
    return OpenAI(api_key=key)

VALIDATOR_SYSTEM = (
    "You are a strict JavaScript quiz validator.\n"
    "Rules:\n"
    "- For 'mcq': match ignoring case/spacing.\n"
    "- For 'fill_code' and 'fill_blank': accept equivalent code/terms if logically correct.\n"
    "- For 'drag_drop': require same order, allow case-insensitive matches.\n"
    "Output STRICT JSON only:\n"
    "{ \"correct\": true/false, \"feedback\": \"short explanation\" }"
)

def _safe_json(text: str) -> dict:
    """Try to extract/clean JSON from model output."""
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip fences
    cleaned = re.sub(r"^```json|```$", "", text.strip(), flags=re.M)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    raise ValueError(f"Invalid JSON: {text[:200]}")

def validate_with_llm(
    question: Dict[str, Any],
    expected_answer: Any,
    user_answer: Any,
    api_key: str | None = None,
) -> Dict[str, Any]:
    client = configure_openai(api_key)

    payload = {
        "type": question.get("type"),
        "question": question.get("question"),
        "code_with_blanks": question.get("code_with_blanks"),
        "options": question.get("options"),
        "expected_answer": expected_answer,
        "user_answer": user_answer,
    }

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",  # ⚡ more reliable than nano
        messages=[
            {"role": "system", "content": VALIDATOR_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )

    raw = resp.choices[0].message.content or "{}"
    try:
        data = _safe_json(raw)
        return {
            "correct": bool(data.get("correct", False)),
            "feedback": str(data.get("feedback", "No feedback provided")),
        }
    except Exception:
        return {
            "correct": False,
            "feedback": "Validator error, please try again.",
        }
