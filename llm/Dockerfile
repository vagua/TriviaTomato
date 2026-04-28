FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1. 安裝套件
COPY requirements.txt .
# 加上 huggingface_hub 以防萬一，並安裝 auto-gptq
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir huggingface_hub && \
    pip install --no-cache-dir --extra-index-url https://huggingface.github.io/autogptq-index/whl/cu121 auto-gptq==0.7.1

# 2. 複製所有檔案 (包含你的 models 資料夾)
COPY . .

EXPOSE 9000

# ========================================================
# 關鍵修正：環境變數
# ========================================================
# 1. 強制指向容器內的路徑 (這樣程式就會讀檔，而不是下載)
ENV QWEN_MODEL_ID=/app/models/Qwen2.5-3B-Instruct-GPTQ-Int4

# 2. 強制只讀本地 (斷網也能跑)
ENV QWEN_LOCAL_ONLY=true

# 3. 修正：預設使用 cuda (既然你有 GPU 環境)
ENV QWEN_DEVICE_MAP=cuda
# ========================================================

CMD ["uvicorn", "llm_server:app", "--host", "0.0.0.0", "--port", "9000"]