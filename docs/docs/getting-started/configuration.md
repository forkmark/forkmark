# Configuration

All settings are controlled via environment variables. Forkmark works out of the box with zero configuration for local development.

## Core settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_HOST` | `127.0.0.1` | Server bind address |
| `FM_PORT` | `7700` | Server port |
| `FM_DB_PATH` | `~/.forkmark/forkmark.db` | SQLite database path (dev only) |
| `FM_DATABASE_URL` | _(unset)_ | PostgreSQL connection string for production |
| `FM_REDIS_URL` | _(unset)_ | Redis URL for caching, rate limiting, and message bus |
| `FM_REQUIRE_UI_AUTH` | `false` | Require API key for UI write endpoints |

## Divergence scoring

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_DIVERGENCE_SCORER` | `auto` | Scoring method: `auto`, `lexical`, `semantic`, `openai`, `llm_judge` |
| `FM_ST_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model (for `semantic` scorer) |
| `FM_EMBED_MODEL` | `text-embedding-3-small` | OpenAI embedding model (for `openai` scorer) |
| `FM_JUDGE_MODEL` | `gpt-4o-mini` | LLM judge model (for `llm_judge` scorer) |
| `FM_JUDGE_BASE_URL` | `https://api.openai.com/v1` | Judge endpoint (supports Ollama, vLLM, etc.) |
| `FM_OPENAI_API_KEY` | _(unset)_ | API key for OpenAI-based scoring |

### Scorer comparison

| Scorer | Latency | Cost | Dependencies |
|--------|---------|------|-------------|
| `lexical` | ~1 ms | Free | None |
| `semantic` | ~50 ms | Free | `sentence-transformers` (80 MB model) |
| `openai` | ~200 ms | ~$0.0001/pair | `FM_OPENAI_API_KEY` |
| `llm_judge` | 2-5 s | ~$0.001/pair | `FM_OPENAI_API_KEY` |

The `auto` mode tries `semantic` first and falls back to `lexical` if sentence-transformers is not installed.

## Authentication and security

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_SECRET_KEY` | _(unset)_ | Fernet encryption key for sensitive settings at rest |
| `JWT_SIGNING_KEY` | _(unset)_ | HS256 signing key for device flow JWT tokens |
| `FORKMARK_CI_TOKEN` | _(unset)_ | HMAC token for CI/CD authentication |
| `FM_BOOTSTRAP_TOKEN` | _(unset)_ | Token for creating the first API key remotely |

## Multi-tenancy

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_MULTI_TENANT` | `false` | Enable PostgreSQL schema-level workspace isolation |
| `FM_PG_POOL_MIN` | `1` | Minimum connections in PostgreSQL pool |
| `FM_PG_POOL_MAX` | `10` | Maximum connections in PostgreSQL pool |

## Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `FM_LOG_FORMAT` | `json` | Log format: `json` for structured, anything else for plain |
| `FM_OTEL_ENABLED` | _(auto)_ | Enable OpenTelemetry tracing (`true`/`false`) |
| `OTEL_SERVICE_NAME` | `forkmark` | OTel service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTel collector endpoint |

## Background processing

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_BACKGROUND_WORKERS` | `4` | Number of background worker threads |
| `FM_CELERY_BROKER_URL` | _(unset)_ | Celery broker URL (uses Redis URL if unset) |

## CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_CORS_ORIGINS` | _(unset)_ | Comma-separated additional CORS origins |

Default CORS origins include `localhost:5173` (Vite dev server) and `localhost:7700` (Forkmark server).

## Data residency

| Variable | Default | Description |
|----------|---------|-------------|
| `FM_REGION` | `us-east-1` | Active region for this deployment |
| `FM_DB_URL_US` | _(unset)_ | PostgreSQL URL for US region |
| `FM_DB_URL_EU` | _(unset)_ | PostgreSQL URL for EU region |
| `FM_DB_URL_APAC` | _(unset)_ | PostgreSQL URL for APAC region |
| `FM_REDIS_URL_US` | _(unset)_ | Redis URL for US region |
| `FM_REDIS_URL_EU` | _(unset)_ | Redis URL for EU region |
| `FM_REDIS_URL_APAC` | _(unset)_ | Redis URL for APAC region |
