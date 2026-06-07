"""Dashboard stats and charts endpoints."""
from __future__ import annotations

import json
import time
from fastapi import APIRouter, Depends, Query

from backend.response_models import StatsResponse, ChartsResponse
from backend.deps import (
    db, redis_client, ui_read_auth,
    stats_local_cache, STATS_CACHE_TTL,
    scorer_name,
)

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def stats(_auth=Depends(ui_read_auth)):
    now = time.time()

    if redis_client:
        try:
            cached = redis_client.get("forkmark:stats_cache")
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    if stats_local_cache.get("expires_at", 0) > now:
        return stats_local_cache["data"]

    s = db.get_stats()
    s["divergence_scorer"] = scorer_name()

    if redis_client:
        try:
            redis_client.setex("forkmark:stats_cache", STATS_CACHE_TTL, json.dumps(s))
        except Exception:
            pass
    stats_local_cache["data"] = s
    stats_local_cache["expires_at"] = now + STATS_CACHE_TTL
    return s


@router.get("/stats/charts", response_model=ChartsResponse)
def stats_charts(_auth=Depends(ui_read_auth)):
    """Return divergence distribution + cost-over-time data for Dashboard charts."""
    with db._read_conn() as c:
        div_rows = c.fetchall("""
            SELECT
                CAST(CASE
                    WHEN divergence_score >= 1.0 THEN 9
                    WHEN divergence_score IS NULL THEN 0
                    ELSE CAST(divergence_score * 10 AS INTEGER)
                END AS INTEGER) AS bucket,
                COUNT(*) AS count
            FROM comparisons
            GROUP BY bucket
            ORDER BY bucket
        """)
        div_hist = []
        bucket_labels = [
            "0.0-0.1","0.1-0.2","0.2-0.3","0.3-0.4","0.4-0.5",
            "0.5-0.6","0.6-0.7","0.7-0.8","0.8-0.9","0.9-1.0",
        ]
        counts_by_bucket = {i: 0 for i in range(10)}
        for r in div_rows:
            r = dict(r) if hasattr(r, 'keys') else {"bucket": r[0], "count": r[1]}
            b = r["bucket"]
            if 0 <= b <= 9:
                counts_by_bucket[b] = r["count"]
        for i in range(10):
            div_hist.append({"range": bucket_labels[i], "count": counts_by_bucket[i]})

        cost_rows = c.fetchall("""
            SELECT
                SUBSTR(created_at, 1, 10) AS day,
                SUM(tokens_input) AS total_input,
                SUM(tokens_output) AS total_output,
                COUNT(*) AS step_count
            FROM step_outputs
            WHERE created_at IS NOT NULL
            GROUP BY day
            ORDER BY day
            LIMIT 90
        """)
        cost_series = []
        for r in cost_rows:
            r = dict(r) if hasattr(r, 'keys') else {
                "day": r[0], "total_input": r[1], "total_output": r[2], "step_count": r[3]
            }
            est_cost = (r["total_input"] or 0) * 3.0 / 1_000_000 + (r["total_output"] or 0) * 15.0 / 1_000_000
            cost_series.append({
                "date": r["day"],
                "cost": round(est_cost, 4),
                "tokens": (r["total_input"] or 0) + (r["total_output"] or 0),
                "steps": r["step_count"],
            })

    return {"divergence_histogram": div_hist, "cost_over_time": cost_series}


@router.get("/tags")
def list_tags(workflow_id: str = Query(None), _auth=Depends(ui_read_auth)):
    return {"tags": db.list_decision_tags(workflow_id)}
