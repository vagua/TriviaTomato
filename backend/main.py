import asyncio
import os
import uuid
from typing import Dict, List

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from llm_client import LLMClient
from models import QuizQuestion, QuizResponse, StartRequest, StartResponse

app = FastAPI(title="靈感番茄 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LLM_URL = os.getenv("LLM_URL", "http://llm:9000")
llm_client = LLMClient(base_url=LLM_URL)
quiz_store: Dict[str, List[QuizQuestion]] = {}
store_lock = asyncio.Lock()


@app.get("/", tags=["system"])
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await llm_client.close()


FALLBACK_QUIZ = [
    QuizQuestion(
        prompt="番茄為什麼常被說越來越沒有味道？",
        options=["農夫疏於照顧", "運輸時間過長", "為求外觀選擇耐儲運的品種"],
        answer_index=2,
        explanation="為了在長途運輸後仍然美觀，商用番茄多選擇果皮厚、耐碰撞的品種，"
        "但也犧牲了原本濃郁的香氣與甜味。",
    ),
]


async def cache_quiz(session_id: str, activity: str) -> None:
    try:
        questions = await llm_client.generate_quiz(activity)
    except Exception as exc:  # pragma: no cover - log for observability
        print(f"LLM generation failed: {exc}")
        questions = FALLBACK_QUIZ

    if not questions:
        questions = FALLBACK_QUIZ

    async with store_lock:
        quiz_store[session_id] = [question.model_copy() for question in questions]


@app.post("/api/start", response_model=StartResponse)
async def start_session(
    req: StartRequest, background: BackgroundTasks
) -> StartResponse:
    session_id = str(uuid.uuid4())
    background.add_task(cache_quiz, session_id, req.activity)
    return StartResponse(session_id=session_id)


@app.get("/api/quiz/{session_id}", response_model=QuizResponse)
async def get_quiz(session_id: str) -> QuizResponse:
    async with store_lock:
        questions = quiz_store.get(session_id)

    if not questions:
        raise HTTPException(status_code=404, detail="Quiz not ready")

    return QuizResponse(questions=questions)

import math
@app.get("/api/stress")
def stress_test():
    """這是一個專門用來消耗 CPU 的測試 API"""
    x = 0.0001
    # 跑一個超大的迴圈做浮點數運算，保證燒 CPU
    for i in range(1000000): 
        x += math.sqrt(i)
    return {"message": "CPU burned!", "result": x}