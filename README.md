# Balu LLM API

Production-grade LLM API built with **FastAPI** and **LangChain**, deployable to **Azure Container Apps**.

Supports **Ollama** (local, free) and **Azure OpenAI** as interchangeable backends.

---

## Features

- `POST /v1/chat` — chat completions with streaming (SSE) support
- `GET /health` — LLM backend health check
- **X-API-Key** authentication
- Structured JSON logging (Azure Monitor / Datadog ready)
- CORS middleware
- Pydantic v2 request/response validation
- 32 unit tests (no live LLM required)
- Multi-stage Docker build
- Azure Container Apps Bicep deployment template

---

## Quick Start (Local with Ollama)

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) running locally with a model pulled:
  ```bash
  ollama pull orca-mini
  ```

### Run

```bash
git clone https://github.com/balakrishnav171/balu-llm-api
cd balu-llm-api

pip install -r requirements.txt

cp .env.example .env
# Edit .env — set API_KEY to a strong secret

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API is live at `http://localhost:8000`
Docs at `http://localhost:8000/docs`

---

## API Usage

### Health Check
```bash
curl http://localhost:8000/health
```
```json
{
  "status": "ok",
  "model": "orca-mini",
  "backend": "ollama",
  "version": "1.0.0",
  "llm_reachable": true
}
```

### Chat (non-streaming)
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "message": {"role": "assistant", "content": "Hello! How can I help you?"},
  "model": "orca-mini",
  "usage": {}
}
```

### Chat (streaming)
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `ollama` | `ollama` or `azure_openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `orca-mini` | Model name |
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_KEY` | — | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | Deployment name |
| `API_KEY` | — | Secret key for `X-API-Key` auth |
| `MAX_TOKENS` | `1024` | Max tokens per response |
| `TEMPERATURE` | `0.7` | LLM temperature |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins |

---

## Docker

### Local (with Ollama bundled)
```bash
docker compose up --build
docker compose exec ollama ollama pull orca-mini
```

API: `http://localhost:8000`

### Build only
```bash
docker build -t balu-llm-api .
docker run -p 8000:8000 --env-file .env balu-llm-api
```

---

## Tests

```bash
pip install pytest httpx
API_KEY=test-key pytest tests/ -v
```

32 tests covering auth, chat, streaming, validation, error handling — no live LLM needed (mocked).

---

## Azure Deployment

### Prerequisites
- Azure CLI (`az login`)
- Docker
- Azure Container Registry

### Deploy
```bash
cd azure
chmod +x deploy.sh
./deploy.sh
```

This will:
1. Create a resource group and Container Registry
2. Build and push the Docker image to ACR
3. Deploy via Bicep to Azure Container Apps
4. Print the public URL

### Infrastructure (Bicep)
- **Azure Container Apps** — serverless, scales 0→5 instances
- **Log Analytics Workspace** — structured logs
- HTTP liveness/readiness probes at `/health`
- Secrets for API key and Azure OpenAI key

---

## Project Structure

```
llm-api/
├── app/
│   ├── main.py              # FastAPI app factory, lifespan, middleware
│   ├── core/
│   │   ├── config.py        # Pydantic settings (reads .env)
│   │   ├── auth.py          # X-API-Key dependency → 401 if wrong
│   │   └── logging.py       # Structured JSON logging
│   ├── schemas/
│   │   └── chat.py          # Pydantic v2 request/response models
│   ├── services/
│   │   └── llm_service.py   # LangChain LLM wrapper (Ollama / Azure OpenAI)
│   └── routers/
│       ├── chat.py          # POST /v1/chat
│       └── health.py        # GET /health
├── tests/                   # 32 unit tests
├── azure/
│   ├── container-app.bicep  # Azure Container Apps infrastructure
│   └── deploy.sh            # End-to-end deploy script
├── Dockerfile               # Multi-stage, non-root user
├── docker-compose.yml       # API + Ollama services
├── requirements.txt
└── .env.example
```

---

## CI/CD

GitHub Actions runs on every push to `main`:

| Job | What it does |
|---|---|
| **Lint & Test** | Installs deps, runs 32 pytest tests (mocked LLM) |
| **Docker Build Check** | Builds the Docker image to catch Dockerfile errors |
