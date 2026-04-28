import json
import logging
import os
import random
import re
import time
from typing import Dict, List

import torch
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI(title="LLM Gateway")
logging.basicConfig(level=logging.INFO)

# Ensure torch uses available CPU cores (container may default lower).
try:
    cpu_cores = os.cpu_count() or 1
    torch.set_num_threads(cpu_cores)
    torch.set_num_interop_threads(max(1, cpu_cores // 2))
    logging.info("Torch threads set: %s cores, interop %s", cpu_cores, max(1, cpu_cores // 2))
except Exception:
    pass

class GenerateRequest(BaseModel):
    activity: str


class QuizQuestion(BaseModel):
    prompt: str = Field(..., description="Trivia question")
    options: List[str] = Field(
        ..., min_length=2, description="Multiple-choice options"
    )
    answer_index: int = Field(..., description="Index for the correct option")
    explanation: str = Field(..., description="Reason why the answer is correct")


class GenerateResponse(BaseModel):
    questions: List[QuizQuestion]


SYSTEM_PROMPT = (
    "你是互動式冷知識題庫設計師。請根據使用者的活動主題生成 1 題，挖掘出鮮為人知、顛覆常識、或帶有歷史荒謬感深度冷知識的多選題，"
    "只輸出單一 JSON，並以 <<<JSON>>> 開頭、<<<END>>> 結尾，格式精確為："
    '<<<JSON>>>{"questions":[{"prompt":"問題","options":["選項1","選項2","選項3"],'
    '"answer_index":0,"explanation":"為何這是答案（提供帶一點趣味的理由）"}]}<<<END>>>'
    "回答須為繁體中文，不要加 A./B. 前綴，不要 Markdown 或多餘文字，內容需合理、不胡謅，避免枯燥教科書式題目。"
)

USER_PROMPT_TEMPLATE = (
    "使用者活動：{activity}\n"
    "請依此活動設計 1 題有趣冷知識多選題（繁體中文），選項 3 個，answer_index 必須介於 0~(選項數-1)，並提供簡短但有趣的解釋。"
    "務必只輸出上述 JSON，並以 <<<JSON>>> 開頭、<<<END>>> 結尾，不要其他文字或 Markdown、不要重複括號，避免枯燥或教科書式問題。"
)

JSON_BLOCK_PATTERN = re.compile(r"\{.*}", re.DOTALL)


# 這裡會讀取 Dockerfile 設定的 ENV，如果沒有設，才會用預設的 HuggingFace ID
MODEL_ID = os.getenv("QWEN_MODEL_ID", "/app/models/Qwen2.5-3B-Instruct-GPTQ-Int4")
# 確保 LOCAL_ONLY 被正確轉為布林值
LOCAL_ONLY = os.getenv("QWEN_LOCAL_ONLY", "true").lower() == "true"
DEVICE_MAP = os.getenv("QWEN_DEVICE_MAP", "cuda")
MAX_NEW_TOKENS = int(os.getenv("QWEN_MAX_TOKENS", "512"))
TEMPERATURE = float(os.getenv("QWEN_TEMPERATURE", "0.4"))

class LocalQwen:
    def __init__(self) -> None:
        print(f"🚀 Loading model from: {MODEL_ID}")
        print(f"🔧 Device: {DEVICE_MAP}, Local Only: {LOCAL_ONLY}")
        
        try:
            # 載入 Tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_ID, 
                local_files_only=LOCAL_ONLY,
                trust_remote_code=True
            )
            
            # 載入 Model
            self.model = AutoModelForCausalLM.from_pretrained(
                MODEL_ID,
                device_map=DEVICE_MAP,
                trust_remote_code=True,
                local_files_only=LOCAL_ONLY
            )
            print("✅ Model loaded successfully!")
            
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            # 印出資料夾內容幫助除錯
            if os.path.exists(MODEL_ID):
                print(f"📂 Contents of {MODEL_ID}: {os.listdir(MODEL_ID)}")
            else:
                print(f"⚠️ Path does not exist: {MODEL_ID}")
            raise e

    def _build_prompt(self, activity: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    activity=activity.strip() or "本次主題"
                ),
            },
        ]
        return self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    def _generate_text(self, activity: str) -> str:
        prompt = self._build_prompt(activity)
        inputs = self.tokenizer([prompt], return_tensors="pt").to(self.model.device)
        start = time.perf_counter()
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                temperature=TEMPERATURE,
                do_sample=True,
            )
        # Remove prompt tokens to get only generation.
        gen_ids = output_ids[0][len(inputs.input_ids[0]) :]
        generated = self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
        elapsed = time.perf_counter() - start
        logging.info("LLM raw output (%.2fs): %s", elapsed, generated[:500])
        return generated

    def _parse_questions(self, text: str) -> List[QuizQuestion]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned.split("\n", 1)[1]

        # Try multiple candidates to be resilient to trailing字元/標點
        candidates = [cleaned]

        # Extract between <<<JSON>>> and <<<END>>> if present
        if "<<<JSON>>>" in cleaned and "<<<END>>>" in cleaned:
            start = cleaned.find("<<<JSON>>>") + len("<<<JSON>>>")
            end = cleaned.find("<<<END>>>", start)
            if end != -1:
                candidates.append(cleaned[start:end].strip())

        # Extract first JSON-looking block as fallback
        match = JSON_BLOCK_PATTERN.search(cleaned)
        if match:
            candidates.append(match.group())

        # Slice between first '{' and last '}' if present
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            candidates.append(cleaned[first : last + 1])

        data = None
        for candidate in candidates:
            normalized = (
                candidate.replace("{{", "{")
                .replace("}}", "}")
                # 修復模型常見的多餘 ] 尾巴
                .replace("]]}", "]}")
            )
            try:
                data = json.loads(normalized)
                break
            except json.JSONDecodeError:
                continue

        if data is None:
            # Regex fallback parsing (tolerates malformed JSON)
            prompt_match = re.search(r'"prompt"\s*:\s*"(?P<prompt>.*?)"', cleaned)
            options_block = re.search(r'"options"\s*:\s*\[(?P<opts>.*?)\]', cleaned)
            answer_match = re.search(r'"answer_index"\s*:\s*(?P<ans>\d+)', cleaned)
            expl_match = re.search(r'"explanation"\s*:\s*"(?P<exp>.*?)"', cleaned)

            prompt_text = prompt_match.group("prompt") if prompt_match else ""
            opts: List[str] = []
            if options_block:
                raw_opts = options_block.group("opts")
                # Prefer標準引號
                opts = re.findall(r'"(.*?)"', raw_opts) or re.findall(r"'(.*?)'", raw_opts)
                if not opts:
                    cleaned_opts = raw_opts.replace('"', "").replace("'", "")
                    splitter = "，" if "，" in cleaned_opts else ","
                    opts = [o.strip() for o in cleaned_opts.split(splitter) if o.strip()]
            answer_idx = int(answer_match.group("ans")) if answer_match else 0
            explanation_text = expl_match.group("exp") if expl_match else ""

            if prompt_text and len(opts) >= 2:
                # Clamp answer index
                if not 0 <= answer_idx < len(opts):
                    answer_idx = 0
                data = {"questions": [
                    {
                        "prompt": prompt_text,
                        "options": opts,
                        "answer_index": answer_idx,
                        "explanation": explanation_text or "答案解析",
                    }
                ]}

        if data is None:
            logging.warning(
                "LLM 回傳無法解析為 JSON，將使用樣板題目。原始輸出片段：%s",
                cleaned[:500],
            )
            return []

        if isinstance(data, dict):
            raw_questions = (
                data.get("questions") or data.get("quiz") or data.get("items")
            )
            if isinstance(raw_questions, dict):
                raw_questions = [raw_questions]
        elif isinstance(data, list):
            raw_questions = data
        else:
            raw_questions = None

        quiz: List[QuizQuestion] = []
        if isinstance(raw_questions, list):
            for item in raw_questions:
                if isinstance(item, dict):
                    try:
                        options = item.get("options") or []
                        if not isinstance(options, list) or len(options) < 2:
                            continue
                        answer_index = int(item.get("answer_index", 0))
                        if not 0 <= answer_index < len(options):
                            answer_index = 0
                        normalized = {
                            "prompt": item.get("prompt") or "",
                            "options": options,
                            "answer_index": answer_index,
                            "explanation": item.get("explanation") or "",
                        }
                        quiz.append(QuizQuestion(**normalized))
                    except Exception:
                        continue
        return quiz

    def generate(self, activity: str) -> List[QuizQuestion]:
        text = self._generate_text(activity)
        return self._parse_questions(text)


local_qwen = LocalQwen()


template_last_index: Dict[str, int] = {}


def build_from_templates(
    topic: str, templates: List[dict], cache_key: str
) -> List[QuizQuestion]:
    if not templates:
        return []

    topic_key = topic.strip().lower() or "default"
    history_key = f"{cache_key}:{topic_key}"
    last_index = template_last_index.get(history_key)

    if last_index is None:
        next_index = random.randrange(len(templates))
    else:
        next_index = (last_index + 1) % len(templates)

    template_last_index[history_key] = next_index

    template = templates[next_index]
    prompt = template["prompt"].format(topic=topic)
    options = [option.format(topic=topic) for option in template["options"]]
    explanation = template["explanation"].format(topic=topic)
    answer_index = template["answer_index"]

    return [
        QuizQuestion(
            prompt=prompt,
            options=options,
            answer_index=answer_index,
            explanation=explanation,
        )
    ]


def build_default_quiz(topic: str) -> List[QuizQuestion]:
    templates = [
        {
            "prompt": "番茄原產於秘魯高地，為何早期曾被歐洲人誤以為有毒？",
            "options": [
                "因為葉片帶有強烈刺激味",
                "番茄植株會吸引蛇類",
                "它曾被當作觀賞植物，果色鮮紅被當成毒果",
            ],
            "answer_index": 2,
            "explanation": "番茄剛到歐洲時多被當作觀賞植物，鮮紅外觀讓人聯想到毒果，直到後來才普及為食材。",
        },
        {
            "prompt": "為什麼 18 世紀的義大利人會把番茄醬稱作「魔鬼醬」？",
            "options": [
                "因為需要長時間熬煮，味道濃烈",
                "它的紅色和辛香料讓人聯想到烈焰",
                "常被拿來掩蓋腐敗食材的味道",
            ],
            "answer_index": 2,
            "explanation": "早期保存技術差，番茄醬常被用來遮掩食材不新鮮的味道，因此有「魔鬼醬」的稱呼。",
        },
        {
            "prompt": "番茄曾被當成水果或蔬菜的界線爭議，最後法律怎麼定義？",
            "options": ["被界定為水果", "被界定為蔬菜", "被界定為特殊作物"],
            "answer_index": 1,
            "explanation": "1893 年美國最高法院判決番茄屬於蔬菜，理由是餐飲習慣上多作為鹹食配菜使用。",
        },
    ]
    return build_from_templates(topic, templates, "default")


def build_fallback_quiz(activity: str) -> List[QuizQuestion]:
    topic = activity.strip() or "default"
    return build_default_quiz(topic)


@app.get("/", tags=["system"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "llm"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.post("/llm/generate", response_model=GenerateResponse)
async def generate_quiz(req: GenerateRequest) -> GenerateResponse:
    try:
        llm_questions = local_qwen.generate(req.activity)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        # 若 LLM 失敗則落回樣板
        logging.exception("LLM 調用失敗")
        llm_questions = []

    questions = llm_questions or build_fallback_quiz(req.activity)
    if not questions:
        raise HTTPException(status_code=500, detail="無法產出題目")

    return GenerateResponse(questions=questions)
