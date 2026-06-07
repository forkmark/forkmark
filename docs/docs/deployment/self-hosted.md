# Self-Hosted Deployment

Forkmark is designed for self-hosting. This guide covers production deployment with PostgreSQL, Redis, and optional Celery workers.

## Architecture

```
                    ┌─────────────┐
                    │   Clients   │
                    │  (SDK/UI)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Forkmark │
                    │   (FastAPI) │
                    └──┬────┬──┬──┘
                       │    │  │
              ┌────────┘    │  └────────┐
              ▼             ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │PostgreSQL│ │  Redis   │ │  Celery   │
        │          │ │          │ │ Workers   │
        └──────────┘ └──────────┘ └──────────┘
```

## Docker Compose (recommended)

```yaml
# docker-compose.yml
version: '3.8'
services:
  forkmark:
    build: .
    ports:
      - "7700:7700"
    environment:
      - FM_DATABASE_URL=postgresql://fp:fp@postgres:5432/forkmark
      - FM_REDIS_URL=redis://redis:6379/0
      - FM_SECRET_KEY=${FM_SECRET_KEY}
      - JWT_SIGNING_KEY=${JWT_SIGNING_KEY}
      - FM_REQUIRE_UI_AUTH=true
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: forkmark
      POSTGRES_USER: fp
      POSTGRES_PASSWORD: fp
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data

  worker:
    build: .
    command: celery -A core.celery_app worker -l info --max-tasks-per-child=200
    environment:
      - FM_DATABASE_URL=postgresql://fp:fp@postgres:5432/forkmark
      - FM_REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

volumes:
  pgdata:
  redisdata:
```

## Environment setup

Generate secrets before first deploy:

```bash
# Generate Fernet key for settings encryption
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate JWT signing key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Create a `.env` file:

```bash
FM_DATABASE_URL=postgresql://fp:fp@localhost:5432/forkmark
FM_REDIS_URL=redis://localhost:6379/0
FM_SECRET_KEY=your-fernet-key-here
JWT_SIGNING_KEY=your-jwt-key-here
FM_REQUIRE_UI_AUTH=true
FM_LOG_LEVEL=INFO
FM_LOG_FORMAT=json
```

## Database setup

Forkmark auto-creates tables on first startup. For PostgreSQL:

```bash
createdb forkmark
```

Migrations run automatically via the inline migration system in `store.py`. For multi-tenant deployments, Alembic manages control plane tables (organizations, workspaces, users):

```bash
cd forkmark
alembic upgrade head
```

## Bootstrapping the first admin API key

On a networked deployment, Forkmark requires an API key for its UI endpoints by
default (see the security note in the README). Because a fresh database has no
keys yet, set a one-time `FM_BOOTSTRAP_TOKEN` in your environment and use it to
mint your first permanent key:

```bash
# In your .env (and restart):  FM_BOOTSTRAP_TOKEN=choose-a-strong-secret

curl -X POST https://forkmark.yourcompany.com/api/keys \
  -H "X-API-Key: choose-a-strong-secret" \
  -H "Content-Type: application/json" \
  -d '{"name": "Admin Key"}'
```

The response contains `raw_key` (e.g. `fm_…`). **Save it immediately** — it is
hashed with argon2id at rest and shown only once. Remove `FM_BOOTSTRAP_TOKEN`
from the environment once you have your first key.

## Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Basic liveness check |
| `GET /healthz` | Kubernetes liveness probe |
| `GET /readyz` | Kubernetes readiness probe (checks DB + Redis) |

## Reverse proxy

Behind nginx:

```nginx
server {
    listen 443 ssl;
    server_name forkmark.yourcompany.com;

    location / {
        proxy_pass http://127.0.0.1:7700;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Scaling

- **Horizontal API scaling**: Run multiple Forkmark instances behind a load balancer. State is in PostgreSQL and Redis, not in-process.
- **Worker scaling**: Add Celery worker replicas for background scoring throughput.
- **Database scaling**: Use PgBouncer for connection pooling at scale. See [Production checklist](production-checklist.md).
