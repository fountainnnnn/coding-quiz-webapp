# backend/src/core/__init__.py
"""
Core package for the JavaScript Quiz WebApp.
Only exposes schemas for request/response models.
"""

from .schemas import (
    GenerateRequest,
    AnswerRequest,
    GenerateResponse,
    CheckAnswerResponse,
)

__all__ = [
    "GenerateRequest",
    "AnswerRequest",
    "GenerateResponse",
    "CheckAnswerResponse",
]
