# TriviaTomato — AI 冷知識番茄鐘

一款結合**番茄鐘工作法**與**AI 即時出題**的雲端應用程式。使用者輸入專注主題並啟動番茄鐘，倒數結束後系統會透過本地部署的大型語言模型（Qwen 2.5-3B）自動生成與該主題相關的趣味冷知識問答，讓休息時間也能學到新東西。

專案同時展示了在 Kubernetes 上實作 **GPU Time-Slicing**、**HPA 自動水平擴展**與**高可用性（HA）故障轉移**的雲端部署實務。

## 系統架構

```
使用者 (瀏覽器)
    │
    ▼
┌──────────────────┐
│   Frontend       │  React + Vite + TypeScript
│   (Port 80)      │  番茄鐘 UI / 問答互動介面
└────────┬─────────┘
         │ REST API
         ▼
┌──────────────────┐
│   Backend        │  Python FastAPI
│   (Port 8000)    │  Session 管理 / 非同步出題 / Retry + Fallback
└────────┬─────────┘
         │ HTTP (ClusterIP 內網)
         ▼
┌──────────────────┐
│   LLM Service    │  Python FastAPI + Transformers
│   (Port 9000)    │  Qwen 2.5-3B-Instruct (GPTQ-Int4, GPU 推論)
└──────────────────┘
```

## 核心功能

- **番茄鐘計時**：使用者自訂專注主題與時間，倒數計時完成後觸發 AI 出題
- **AI 冷知識問答**：LLM 根據使用者的專注主題即時生成繁體中文多選題，附帶趣味解說
- **容錯機制**：後端具備非同步重試邏輯（最多 3 次），LLM 無法回應時自動切換為內建題庫

## 雲端部署特色

| 技術 | 說明 |
|------|------|
| **GPU Time-Slicing** | 透過 NVIDIA Device Plugin 將單張 GPU 虛擬化為 4 份，讓多個 LLM Pod 共享 GPU 資源 |
| **高可用性 (HA)** | LLM 採雙副本部署，模型預載於映像檔（Baked-in Model）實現秒級重啟（RTO < 2s） |
| **HPA 自動擴展** | Backend 依據 CPU 使用率自動擴展（1 → 5 副本），流量降低後自動縮減 |
| **服務發現** | 後端透過 Kubernetes DNS 呼叫 `llm-gateway:9000`，完全解耦、無需寫死 IP |
| **故障轉移** | 手動刪除 LLM Pod 時，K8s 自動重啟 + 後端 Retry 機制確保使用者無感 |

## 技術棧

- **Frontend**：React 18 + TypeScript + Vite
- **Backend**：Python FastAPI + httpx（非同步 HTTP）+ Pydantic
- **LLM Service**：Hugging Face Transformers + Qwen 2.5-3B-Instruct-GPTQ-Int4 + PyTorch (CUDA)
- **容器化**：Docker + Docker Compose（GPU 支援）
- **編排部署**：Kubernetes (Minikube) + NVIDIA Device Plugin + HPA

## 專案結構

```
├── frontend/               # React 前端
│   ├── src/
│   │   ├── pages/          # TimerPage — 番茄鐘主頁面
│   │   ├── components/     # Countdown（倒數計時）、QuizModal（問答彈窗）
│   │   └── api/            # API client（與後端通訊）
│   └── Dockerfile
├── backend/                # FastAPI 後端
│   ├── main.py             # API 路由（/api/start, /api/quiz, /api/stress）
│   ├── llm_client.py       # LLM 呼叫代理（含重試邏輯）
│   ├── models.py           # Pydantic 資料模型
│   └── Dockerfile
├── llm/                    # LLM 推論服務
│   ├── llm_server.py       # 模型載入、Prompt 建構、JSON 解析、Fallback 題庫
│   ├── models/             # 本地模型權重存放處
│   └── Dockerfile
├── k8s/                    # Kubernetes 部署設定
│   ├── frontend-deployment.yaml
│   ├── backend-deployment.yaml
│   ├── llm-deployment.yaml
│   ├── hpa.yaml            # Backend HPA 設定（CPU > 10% 觸發擴展）
│   └── time-slicing-config.yaml  # GPU 虛擬化為 4 份
└── docker-compose.yml      # 本地開發用 Compose 設定
```

## 快速啟動

### Docker Compose（需要 NVIDIA GPU）

```bash
# 確保已安裝 NVIDIA 驅動與 nvidia-container-toolkit
# 將 Qwen 模型權重放入 llm/models/Qwen2.5-3B-Instruct-GPTQ-Int4/

docker compose up --build
```

啟動後：
- 前端：http://localhost:8080
- 後端：http://localhost:8000
- LLM：http://localhost:9000

### Kubernetes (Minikube + GPU)

```bash
# 1. 啟動 GPU 叢集
minikube start --driver=docker --gpus=all

# 2. 安裝 NVIDIA Device Plugin 並啟用 Time-Slicing
helm install nvdp nvdp/nvidia-device-plugin \
  --namespace kube-system \
  --set config.name=time-slicing-config \
  --set config.default=time-slicing-config.yaml

# 3. 建置映像並載入 Minikube
docker build -t myfrontend:v1 frontend/
docker build -t mybackend:v1 backend/
docker build -t myllm:v1 llm/
minikube image load myfrontend:v1 mybackend:v1 myllm:v1

# 4. 部署至叢集
kubectl apply -f k8s/

# 5. 開啟 Tunnel 存取服務
minikube tunnel
```

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `QWEN_MODEL_ID` | `/models/Qwen2.5-3B-Instruct-GPTQ-Int4` | 模型路徑 |
| `QWEN_LOCAL_ONLY` | `true` | 僅讀取本地模型，不從 HuggingFace 下載 |
| `QWEN_DEVICE_MAP` | `cuda` | 推論裝置（`cuda` 或 `cpu`） |
| `QWEN_MAX_TOKENS` | `512` | 最大生成 token 數 |
| `QWEN_TEMPERATURE` | `0.4` | 生成溫度 |
| `LLM_URL` | `http://llm:9000` | Backend 連線 LLM 的位址 |

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/api/start` | 建立 Session，背景非同步呼叫 LLM 生成題目 |
| `GET` | `/api/quiz/{session_id}` | 取得該 Session 的冷知識問答題 |
| `GET` | `/api/stress` | CPU 壓力測試端點（用於驗證 HPA 擴展） |
| `POST` | `/llm/generate` | LLM 服務：根據活動主題生成問答題（內部呼叫） |
