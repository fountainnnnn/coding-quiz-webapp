from pydantic import BaseModel
from typing import List, Union, Optional

# ------------------------------------------------------------
# Request models
# ------------------------------------------------------------
class GenerateRequest(BaseModel):
    language: str                  # e.g. "javascript", "python", "cpp"
    topic: str                     # e.g. "loops", "arrays", "functions"
    difficulty: str                 # "easy", "mixed", "hard"
    n: int                         # number of questions


class AnswerRequest(BaseModel):
    session_id: str                # required for backend session tracking
    question_id: str
    user_answer: Union[str, List[str]]
    language: Optional[str] = "javascript"  # default JS, can also be python/cpp


# ------------------------------------------------------------
# Question & Response models
# ------------------------------------------------------------
class SafeQuestion(BaseModel):
    question_id: str
    type: str
    question: str
    options: Optional[List[str]] = None
    code_with_blanks: Optional[str] = None


class GenerateResponse(BaseModel):
    status: str
    session_id: str
    questions: List[SafeQuestion]


class CheckAnswerResponse(BaseModel):
    status: str
    correct: bool
    expected: Union[str, List[str]]
    explanation: str
