"""Forkmark FastAPI backend — modular router architecture.

This file is the application entry point. All route logic lives in
backend/routes/ modules. Shared dependencies (db, auth, caching) are
in backend/deps.py.

v0.1.1 refactor: split from monolithic 2200-line main.py into:
  - deps.py          — db, redis, auth, rate limiting, caching
  - routes/sdk.py    — SDK endpoints (always require API key)
  - routes/eval_runs.py  — eval run CRUD + stats
  - routes/test_sets.py  — test set management
  - routes/workflows.py  — workflow CRUD + runs
  - routes/comparisons.py — comparisons, decisions, costs
  - routes/decisions.py  — decision listing + DPO/CSV/JSONL exports
  - routes/keys.py       — API key management
  - routes/settings.py   — settings, system info, reviewer profiles, consent
  - routes/collaboration.py — comments + review assignments
  - routes/exports.py   — preference corpus export
  - routes/stats.py     — dashboard stats + charts
  - routes/runner.py    — no-code runner + playground
  - routes/demos.py     — demo seeding
  - routes/admin.py     — pruning + maintenance
  - routes/health.py    — liveness/readiness probes
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import config
from backend.deps import db


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: sync LLM pricing table from LiteLLM upstream."""
    import httpx
    try:
        url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

            new_prices = {}
            for model, info in data.items():
                if isinstance(info, dict) and "input_cost_per_token" in info and "output_cost_per_token" in info:
                    try:
                        new_prices[model] = {
                            "input": float(info["input_cost_per_token"]) * 1_000_000,
                            "output": float(info["output_cost_per_token"]) * 1_000_000,
                        }
                    except (ValueError, TypeError):
                        pass
            from core.store import update_pricing_table
            update_pricing_table(new_prices)
    except Exception as e:
        print(f"Warning: Failed to sync LLM pricing table: {e}")
    yield


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Forkmark",
    version=config.VERSION,
    description="Self-hosted A/B prompt comparison platform with human review and DPO export.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# ── Enterprise stack (conditional) ───────────────────────────────────────────

def _init_enterprise_stack():
    """Initialize enterprise modules.

    DISABLED for the open-source launch (v0.1.2). The enterprise modules
    (multi-tenancy, SCIM, device-flow, data-residency) are not shipped in this
    OSS build, so this block is intentionally a no-op. Re-enable once the `ee/`
    modules are present and license-gated — see the launch runbook, Phase 2.3.
    """
    print("[forkmark] OSS edition — enterprise stack not loaded.")
    return

    # ---------------------------------------------------------------------------
    # Enterprise init (kept for reference; re-enable when ee/ modules exist).
    # ---------------------------------------------------------------------------
    # enterprise_mode = os.environ.get("FM_ENTERPRISE_MODE", "").lower() in ("true", "1", "yes")
    # if not enterprise_mode:
    #     return
    # from core.observability import setup_observability
    # setup_observability(app)
    # from core.workspace_router import get_workspace_router
    # multi_tenant = os.environ.get("FM_MULTI_TENANT", "").lower() in ("true", "1", "yes")
    # database_url = getattr(config, "DATABASE_URL", None)
    # db_path = str(getattr(config, "DB_PATH", ""))
    # router = get_workspace_router(database_url, db_path, multi_tenant)
    # app.state.workspace_router = router
    # app.state.db = db
    # from core.message_bus import get_message_bus
    # redis_url = getattr(config, "REDIS_URL", None)
    # app.state.message_bus = get_message_bus(redis_url)
    # from core.audit import AuditLogger
    # app.state.audit_logger = AuditLogger(router)
    # from core.data_residency import get_residency_manager
    # residency = get_residency_manager(default_database_url=database_url or "",
    #                                   default_redis_url=redis_url or "")
    # residency.set_router(router)
    # app.state.residency_manager = residency
    # webhook_secret = os.environ.get("WORKOS_WEBHOOK_SECRET", "")
    # if multi_tenant:
    #     from core.multitenancy import WorkspaceProvisioner
    #     from core.scim_handler import SCIMProvisioner, scim_router
    #     provisioner = WorkspaceProvisioner(database_url or "")
    #     app.state.scim_provisioner = SCIMProvisioner(provisioner, webhook_secret)
    #     app.include_router(scim_router, prefix="/api/webhooks")
    # from backend.deps import redis_client
    # if redis_client:
    #     from core.device_flow import DeviceCodeStore, device_flow_router
    #     app.state.device_code_store = DeviceCodeStore(redis_client)
    #     app.include_router(device_flow_router, prefix="/api/auth")

_init_enterprise_stack()


# ── Register route modules ───────────────────────────────────────────────────

from backend.routes.sdk import router as sdk_router
from backend.routes.eval_runs import router as eval_runs_router
from backend.routes.test_sets import router as test_sets_router
from backend.routes.workflows import router as workflows_router
from backend.routes.comparisons import router as comparisons_router
from backend.routes.decisions import router as decisions_router
from backend.routes.keys import router as keys_router
from backend.routes.settings import router as settings_router
from backend.routes.collaboration import router as collaboration_router
from backend.routes.exports import router as exports_router
from backend.routes.stats import router as stats_router
from backend.routes.runner import router as runner_router
from backend.routes.demos import router as demos_router
from backend.routes.providers import router as providers_router
from backend.routes.admin import router as admin_router
from backend.routes.health import router as health_router

# Agent comparison router (feature-gated)
if config.ENABLE_AGENT_COMPARISON:
    from backend.routes.agent import router as agent_router

app.include_router(sdk_router)
app.include_router(eval_runs_router)
app.include_router(test_sets_router)
app.include_router(workflows_router)
app.include_router(comparisons_router)
app.include_router(decisions_router)
app.include_router(keys_router)
app.include_router(settings_router)
app.include_router(collaboration_router)
app.include_router(exports_router)
app.include_router(stats_router)
app.include_router(runner_router)
app.include_router(providers_router)
app.include_router(demos_router)
app.include_router(admin_router)
app.include_router(health_router)
if config.ENABLE_AGENT_COMPARISON:
    app.include_router(agent_router)


# ── API v1 prefix alias ─────────────────────────────────────────────────────

class _V1RewriteMiddleware(BaseHTTPMiddleware):
    """Transparently strip /api/v1 → /api so both prefixes work."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/v1/"):
            scope = request.scope
            scope["path"] = "/api/" + request.url.path[len("/api/v1/"):]
            scope["raw_path"] = scope["path"].encode("ascii")
        return await call_next(request)

app.add_middleware(_V1RewriteMiddleware)


# ── Serve React SPA ──────────────────────────────────────────────────────────

_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, f"API route not found: /{full_path}")
        return FileResponse(str(_DIST / "index.html"))
