# Installation

## Server

### Option 1: Docker (recommended)

```bash
git clone https://github.com/forkmark/forkmark.git
cd forkmark
python run.py
```

The launcher detects Docker and starts via `docker-compose.simple.yml`. First run builds the image (~2 minutes).

### Option 2: Python direct

If Docker is unavailable, the launcher falls back to Python direct mode:

```bash
git clone https://github.com/forkmark/forkmark.git
cd forkmark
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python run.py
```

Requirements: Python 3.9+, Node.js 18+ (for frontend build).

### Option 3: Manual

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 7700

# Frontend (separate terminal)
cd frontend
npm install && npm run dev
```

## SDK

The Python SDK is installed separately from the server:

```bash
pip install forkmark
```

### Optional extras

```bash
pip install "forkmark[openai]"      # OpenAI drop-in wrapper
pip install "forkmark[anthropic]"   # Anthropic drop-in wrapper
pip install "forkmark[langchain]"   # LangChain callback handler
pip install "forkmark[all]"         # All integrations
```

## System requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.9 | 3.11+ |
| PostgreSQL | 14 | 16 |
| Redis | 6.2 | 7+ |
| Node.js | 18 | 20+ |
| Memory | 512 MB | 2 GB |

!!! note
    PostgreSQL and Redis are only required for production multi-tenant deployments. For local development, Forkmark uses SQLite (zero configuration) and in-memory fallbacks.
