# backend/src/app.py

import os, uuid, logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from src.core.schemas import (
    GenerateRequest,
    AnswerRequest,
    GenerateResponse,
    CheckAnswerResponse,
)
from src.core.openai_qg import generate_questions

# ------------------------------------------------------------
# Setup
# ------------------------------------------------------------
load_dotenv()
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("quiz")

app = FastAPI(title="JavaScript Quiz API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to log requests
class LogRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            body = await request.body()
            logger.info(f"Incoming {request.method} {request.url.path} body={body.decode('utf-8')}")
        except Exception:
            logger.warning("Could not read request body")
        return await call_next(request)

app.add_middleware(LogRequestMiddleware)

# In-memory store for answers: { session_id: { qid: {answer, explanation} } }
SESSION_STORE: dict[str, dict[str, dict]] = {}

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def normalize(s: str) -> str:
    """Lowercase and collapse whitespace for fair comparison."""
    return " ".join(str(s).strip().lower().split())

# ------------------------------------------------------------
# Exception handlers
# ------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()} body={exc.body}")
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "detail": exc.errors(),
            "body": exc.body,
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)},
    )

# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@app.post("/generate_questions", response_model=GenerateResponse)
def generate_questions_route(req: GenerateRequest):
    try:
        result = generate_questions(req.topic, req.difficulty, req.n)
    except RuntimeError as e:
        logger.error(f"RuntimeError: {e}")
        return JSONResponse(
            {"status": "error", "message": "OpenAI API key is missing."},
            status_code=500,
        )
    except Exception as e:
        logger.error("Exception during generate_questions", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    # New session
    session_id = str(uuid.uuid4())
    SESSION_STORE[session_id] = {}

    for item in result["secret"]:
        SESSION_STORE[session_id][item["question_id"]] = {
            "answer": item["answer"],
            "explanation": item["explanation"],
        }
        logger.debug(f"Stored qid={item['question_id']} for session={session_id}")

    logger.debug(f"Session {session_id} has {len(SESSION_STORE[session_id])} questions stored")

    return {"status": "ok", "session_id": session_id, "questions": result["safe"]}

@app.post("/check_answer", response_model=CheckAnswerResponse)
def check_answer(req: AnswerRequest):
    session_id = req.session_id
    record = SESSION_STORE.get(session_id, {}).get(req.question_id)

    if not record:
        logger.warning(f"Question not found for session={session_id}, qid={req.question_id}")
        raise HTTPException(status_code=404, detail="Question not found or expired")

    expected = record["answer"]
    user_ans = req.user_answer
    logger.debug(
        f"Checking answer for session={session_id}, qid={req.question_id}, "
        f"expected={expected}, user={user_ans}"
    )

    correct = False
    if isinstance(expected, list):
        if isinstance(user_ans, list):
            correct = [normalize(x) for x in user_ans] == [normalize(x) for x in expected]
        else:
            correct = normalize(user_ans) in [normalize(x) for x in expected]
    else:
        correct = normalize(user_ans) == normalize(expected)

    return {
        "status": "ok",
        "correct": correct,
        "expected": expected,
        "explanation": record["explanation"] or "",
    }

@app.post("/end_quiz")
def end_quiz(session_id: str):
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
        logger.info(f"Cleared session={session_id}")
    return {"status": "ok", "message": f"Quiz session {session_id} ended."}

@app.get("/healthz")
def healthz():
    return {"ok": True}
