from typing import List

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    activity: str = Field(..., min_length=1, description="Focus topic for the pomodoro")


class StartResponse(BaseModel):
    session_id: str


class QuizQuestion(BaseModel):
    prompt: str = Field(..., description="Quiz statement or question")
    options: List[str] = Field(
        ..., min_length=2, description="Multiple-choice options to select from"
    )
    answer_index: int = Field(
        ...,
        ge=0,
        description="Index of the correct option within the options array",
    )
    explanation: str = Field(
        ..., description="Short explanation revealing the correct answer"
    )


class QuizResponse(BaseModel):
    questions: List[QuizQuestion]
