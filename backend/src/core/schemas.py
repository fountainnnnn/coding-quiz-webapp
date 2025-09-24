from pydantic import BaseModel
from typing import List, Union, Optional

class GenerateRequest(BaseModel):
    topic: str
    difficulty: str
    n: int

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

class AnswerRequest(BaseModel):
    session_id: str   # << added
    question_id: str
    user_answer: Union[str, List[str]]

class CheckAnswerResponse(BaseModel):
    status: str
    correct: bool
    expected: Union[str, List[str]]
    explanation: str
