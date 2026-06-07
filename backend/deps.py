"""Shared dependencies for route modules.

All route modules import from here to access db, config, auth functions,
and common utilities. This avoids circular imports and keeps routes clean.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections import deque
from typing import Dict, Optional

from fastapi import Header, HTTPException, Request, Depends, Query

from config import config
from core.store import Database
from core.models import RunStatus, DecisionChoice, ConfidenceLevel, EvalRunStatus
from core.comparator import divergence_score, inline_diff, summarize_divergence, scorer_name
from core.background import async_enqueue_scoring


# ── Database ─────────────────────────────────────────────────────────────────

db = Database(str(config.DB_PATH), database_url=config.DATABASE_URL, trace_backend=config.TRACE_BACKEND)

# ── Redis (optional) ─────────────────────────────────────────────────────────

import redis
redis_client = redis.from_url(config.REDIS_URL) if hasattr(config, 'REDIS_URL') and config.REDIS_URL else None


# ── Inline diff LRU cache ────────────────────────────────────────────────────

_inline_diff_cache: Dict[str, tuple] = {}
_INLINE_DIFF_MAX = 512


def cached_inline_diff(comp_id: str, text_a: str, text_b: str) -> tuple:
    """Cached wrapper — uses Redis if available, else local in-memory LRU cache."""
    cache_key = None
    if redis_client:
        try:
            cache_key = f"diff:{comp_id}:{hashlib.md5((text_a+text_b).encode()).hexdigest()[:8]}"
            cached = redis_client.get(cache_key)
            if cached:
                return tuple(json.loads(cached))
        except Exception:
            pass

    if comp_id in _inline_diff_cache:
        return _inline_diff_cache[comp_id]

    result = tuple(inline_diff(text_a, text_b))

    if redis_client and cache_key:
        try:
            redis_client.setex(cache_key, 86400, json.dumps(result))
        except Exception:
            pass

    if len(_inline_diff_cache) >= _INLINE_DIFF_MAX:
        _inline_diff_cache.pop(next(iter(_inline_diff_cache)))
    _inline_diff_cache[comp_id] = result
    return result


# ── Rate limiting ────────────────────────────────────────────────────────────

_RATE_WINDOW = 60.0
_RATE_LIMIT = int(os.getenv("FM_RATE_LIMIT", "1000"))
_MAX_RATE_KEYS = 4096


class _RateBucket:
    __slots__ = ('lock', 'timestamps')
    def __init__(self):
        self.lock = threading.Lock()
        self.timestamps: deque = deque()


_rate_buckets: dict = {}
_rate_meta_lock = threading.Lock()


def _check_rate(key_id: str) -> bool:
    """Return True if request is allowed; False if rate limit exceeded."""
    if redis_client:
        try:
            now = time.time()
            cutoff = now - _RATE_WINDOW
            redis_key = f"rate:{key_id}"
            member = str(uuid.uuid4())

            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zadd(redis_key, {member: now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, int(_RATE_WINDOW + 5))
            results = pipe.execute()

            count = results[2]
            return count <= _RATE_LIMIT
        except Exception:
            pass

    bucket = _rate_buckets.get(key_id)
    if bucket is None:
        with _rate_meta_lock:
            bucket = _rate_buckets.get(key_id)
            if bucket is None:
                if len(_rate_buckets) >= _MAX_RATE_KEYS:
                    now_t = time.time()
                    cutoff_t = now_t - _RATE_WINDOW
                    for k, b in list(_rate_buckets.items()):
                        with b.lock:
                            while b.timestamps and b.timestamps[0] < cutoff_t:
                                b.timestamps.popleft()
                            if not b.timestamps:
                                _rate_buckets.pop(k, None)
                    if len(_rate_buckets) >= _MAX_RATE_KEYS:
                        to_remove = list(_rate_buckets.keys())[:_MAX_RATE_KEYS // 10]
                        for k in to_remove:
                            _rate_buckets.pop(k, None)
                bucket = _RateBucket()
                _rate_buckets[key_id] = bucket

    now = time.time()
    cutoff = now - _RATE_WINDOW
    with bucket.lock:
        q = bucket.timestamps
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= _RATE_LIMIT:
            return False
        q.append(now)
        return True


# ── Auth dependencies ────────────────────────────────────────────────────────

def require_key(x_api_key: str = Header(None, alias="X-API-Key")) -> str:
    """Hard auth — always required. Used on all SDK endpoints."""
    if not x_api_key:
        raise HTTPException(401, "X-API-Key header required")
    ak = db.verify_api_key(x_api_key)
    if not ak:
        raise HTTPException(401, "Invalid or revoked API key")
    if not _check_rate(ak.id):
        raise HTTPException(429, "Rate limit exceeded — max 1000 requests/minute per key")
    return x_api_key


def ui_write_auth(request: Request,
                  x_api_key: str = Header(None, alias="X-API-Key")) -> Optional[str]:
    """Conditional auth for UI write endpoints."""
    rate_id = x_api_key or (request.client.host if request.client else "unknown")
    if not _check_rate(f"ui:{rate_id}"):
        raise HTTPException(429, "Rate limit exceeded")
    if x_api_key:
        ak = db.verify_api_key(x_api_key)
        if not ak:
            raise HTTPException(401, "Invalid or revoked API key")
        return x_api_key
    if config.REQUIRE_UI_AUTH:
        raise HTTPException(401, "X-API-Key required (FM_REQUIRE_UI_AUTH is enabled)")
    return None


def ui_read_auth(request: Request,
                 x_api_key: str = Header(None, alias="X-API-Key")) -> Optional[str]:
    """Conditional auth for UI read endpoints."""
    rate_id = x_api_key or (request.client.host if request.client else "unknown")
    if not _check_rate(f"ui:{rate_id}"):
        raise HTTPException(429, "Rate limit exceeded")
    if x_api_key:
        ak = db.verify_api_key(x_api_key)
        if not ak:
            raise HTTPException(401, "Invalid or revoked API key")
        return x_api_key
    if config.REQUIRE_UI_AUTH:
        raise HTTPException(401, "X-API-Key required (FM_REQUIRE_UI_AUTH is enabled)")
    return None


# ── Stats cache ──────────────────────────────────────────────────────────────

STATS_CACHE_TTL = 15
stats_local_cache: dict = {}
