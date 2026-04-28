import asyncio  # <--- 新增這行 (為了 sleep)
import logging  # <--- 新增這行 (為了印出重試訊息)
from typing import List

import httpx
from pydantic import ValidationError

from models import QuizQuestion

# 設定 log 格式，方便觀察重試過程
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMClient:
    """Simple async client that proxies quiz generation to the LLM layer."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        # 放寬 timeout 避免過早失敗
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60)

    async def generate_quiz(self, activity: str) -> List[QuizQuestion]:
        max_retries = 3  # 設定最大重試次數
        
        for attempt in range(max_retries):
            try:
                # 嘗試呼叫 LLM
                response = await self._client.post(
                    "/llm/generate",
                    json={"activity": activity},
                )
                response.raise_for_status() # 檢查是否有 500 錯誤
                
                # 若成功，開始解析資料
                data = response.json()
                raw_questions = data.get("questions", [])
                quiz: List[QuizQuestion] = []
                for raw in raw_questions:
                    try:
                        quiz.append(QuizQuestion(**raw))
                    except (TypeError, ValidationError) as exc:
                        logger.warning(f"Invalid quiz payload skipped: {exc}")
                
                # 解析成功，直接回傳 (跳出迴圈)
                return quiz

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                # 這是最關鍵的地方：捕捉連線錯誤或伺服器錯誤
                logger.warning(f"⚠️ 第 {attempt + 1} 次呼叫 LLM 失敗: {exc}")
                
                # 如果是最後一次嘗試也失敗，就真的拋出錯誤，讓外層去處理 (Fallback)
                if attempt == max_retries - 1:
                    logger.error("❌ 已達最大重試次數，宣告失敗。")
                    raise exc
                
                # 等待 1 秒，讓 Kubernetes 有時間切換流量到健康的 Pod
                logger.info("⏳ 正在重試... K8s 應該會把我導向另一個活著的 Pod")
                await asyncio.sleep(1)

        return []

    async def close(self) -> None:
        await self._client.aclose()