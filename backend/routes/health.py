"""Health, readiness, and ops endpoints."""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Depends

from backend.response_models import HealthResponse, ReadinessResponse
from backend.deps import db, redis_client, ui_read_auth
from config import config

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
def health_check():
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
def readiness_check():
    checks = {"database": "unknown", "redis": "unknown", "pgbouncer": "unknown"}
    db_url = os.getenv("FM_DATABASE_URL", "")
    is_pgbouncer = "pgbouncer" in db_url.lower() or ":6432" in db_url
    try:
        with db.adapter.connect() as conn:
            conn.execute("SELECT 1")
        checks["database"] = "connected"
        checks["pgbouncer"] = "connected (transaction mode)" if is_pgbouncer else "direct connection (no pooler)"
    except Exception as e:
        raise HTTPException(503, detail={"status": "not_ready", "checks": checks, "error": str(e)})

    if redis_client:
        try:
            redis_client.ping()
            checks["redis"] = "connected"
        except Exception:
            checks["redis"] = "disconnected (degraded mode)"
    else:
        checks["redis"] = "not configured"

    return {"status": "ready", "checks": checks}


@router.get("/health", include_in_schema=False)
@router.get("/api/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "version": config.VERSION}


@router.get("/api/pool-stats", tags=["ops"])
def pool_stats(_auth=Depends(ui_read_auth)):
    pool_info = {
        "database_url_masked": "***pgbouncer***" if "pgbouncer" in os.getenv("FM_DATABASE_URL", "").lower()
                               else "***direct***",
        "pool_min": int(os.getenv("DB_POOL_MIN", "2")),
        "pool_max": int(os.getenv("DB_POOL_MAX", "10")),
    }
    try:
        adapter = db.adapter
        if hasattr(adapter, 'pool') and adapter.pool:
            pool = adapter.pool
            pool_info["pool_size"] = getattr(pool, 'size', None)
            pool_info["pool_checkedin"] = getattr(pool, 'checkedin', lambda: None)()
            pool_info["pool_checkedout"] = getattr(pool, 'checkedout', lambda: None)()
            pool_info["pool_overflow"] = getattr(pool, 'overflow', lambda: None)()
    except Exception:
        pass
    return pool_info
