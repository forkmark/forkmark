"""Settings and system info endpoints."""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.response_models import SettingsResponse, SystemInfoResponse, OkResponse, OkRestartResponse
from backend.deps import db, ui_read_auth, ui_write_auth
from config import config

router = APIRouter(prefix="/api", tags=["settings"])


_SETTINGS_KEYS = {
    "openai_api_key", "openai_base_url", "judge_model",
    "divergence_scorer", "st_model", "embed_model",
    "theme",
    "notifications_toast", "notifications_browser", "notifications_auto_dismiss",
    "display_name", "timezone",
}
_VALID_SCORERS = {"auto", "lexical", "semantic", "openai", "llm_judge"}


class SettingsBody(BaseModel):
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    judge_model: Optional[str] = None
    divergence_scorer: Optional[str] = None
    st_model: Optional[str] = None
    embed_model: Optional[str] = None
    theme: Optional[str] = None
    notifications_toast: Optional[str] = None
    notifications_browser: Optional[str] = None
    notifications_auto_dismiss: Optional[str] = None
    display_name: Optional[str] = None
    timezone: Optional[str] = None


class SystemInfoBody(BaseModel):
    background_workers: Optional[int] = None
    require_ui_auth: Optional[str] = None


class ReviewerProfileBody(BaseModel):
    display_name: str = ""
    role: str = "reviewer"
    expertise_level: str = "intermediate"
    domain_expertise: List[str] = []


class ConsentBody(BaseModel):
    scope: str = "global"
    workflow_id: Optional[str] = None
    consent_type: str
    granted_by: str
    notes: str = ""
    expires_at: Optional[str] = None


@router.get("/settings")
def get_settings(_auth=Depends(ui_read_auth)):
    raw = db.get_all_settings()
    if "openai_api_key" in raw and raw["openai_api_key"]:
        key = raw["openai_api_key"]
        raw["openai_api_key_masked"] = key[:8] + "..." if len(key) > 8 else "***"
        raw["openai_api_key_set"] = True
        del raw["openai_api_key"]
    else:
        raw["openai_api_key_set"] = False
    raw.setdefault("divergence_scorer", config.DIVERGENCE_SCORER or "auto")
    raw.setdefault("st_model", config.ST_MODEL)
    raw.setdefault("embed_model", config.EMBED_MODEL)
    raw.setdefault("theme", "dark")
    raw.setdefault("notifications_toast", "true")
    raw.setdefault("notifications_browser", "false")
    raw.setdefault("notifications_auto_dismiss", "5")
    raw.setdefault("display_name", "")
    raw.setdefault("timezone", "")
    return raw


@router.patch("/settings")
def patch_settings(body: SettingsBody, _auth=Depends(ui_write_auth)):
    updates = body.model_dump(exclude_none=True)
    if "divergence_scorer" in updates:
        val = updates["divergence_scorer"].lower().strip()
        if val not in _VALID_SCORERS:
            raise HTTPException(400, f"Invalid divergence_scorer: {val!r}. "
                                f"Must be one of: {', '.join(sorted(_VALID_SCORERS))}")
        updates["divergence_scorer"] = val
    for key, value in updates.items():
        if key in _SETTINGS_KEYS:
            db.set_setting(key, str(value))
    return {"ok": True}


@router.get("/system-info", tags=["settings"])
def get_system_info(_auth=Depends(ui_read_auth)):
    return {
        "storage": "postgresql" if config.DATABASE_URL else "sqlite",
        "database_url_set": bool(config.DATABASE_URL),
        "version": config.VERSION,
        "background_workers": config.BACKGROUND_WORKERS,
        "require_ui_auth": config.REQUIRE_UI_AUTH,
        "multi_tenant": os.environ.get("FM_MULTI_TENANT", "").lower() in ("true", "1", "yes"),
        "scim_enabled": os.environ.get("FM_ENABLE_SCIM", "").lower() in ("true", "1", "yes"),
        "device_flow_enabled": os.environ.get("FM_ENABLE_DEVICE_FLOW", "").lower() in ("true", "1", "yes"),
        "otel_enabled": config.ENABLE_OTEL,
    }


@router.patch("/system-info", tags=["settings"])
def patch_system_info(body: SystemInfoBody, _auth=Depends(ui_write_auth)):
    from config import save_env_setting
    restart_required = False

    if body.background_workers is not None:
        workers = body.background_workers
        if not (1 <= workers <= 16):
            raise HTTPException(400, f"background_workers must be between 1 and 16")
        save_env_setting("FM_BACKGROUND_WORKERS", str(workers))
        restart_required = True

    if body.require_ui_auth is not None:
        val = body.require_ui_auth.lower().strip()
        if val not in ("true", "false"):
            raise HTTPException(400, f"require_ui_auth must be 'true' or 'false'")
        save_env_setting("FM_REQUIRE_UI_AUTH", val)
        restart_required = True

    return {"ok": True, "restart_required": restart_required}


# ── Reviewer profiles ────────────────────────────────────────────────────────

@router.get("/reviewer-profile/{reviewer_id}")
def get_reviewer_profile(reviewer_id: str, _auth=Depends(ui_read_auth)):
    p = db.get_reviewer_profile(reviewer_id)
    if not p:
        raise HTTPException(404, "Reviewer profile not found")
    return p

@router.post("/reviewer-profile/{reviewer_id}", status_code=201)
def upsert_reviewer_profile(reviewer_id: str, body: ReviewerProfileBody,
                             _auth=Depends(ui_write_auth)):
    return db.upsert_reviewer_profile(
        reviewer_id, display_name=body.display_name, role=body.role,
        expertise_level=body.expertise_level, domain_expertise=body.domain_expertise,
    )


# ── Consent management ───────────────────────────────────────────────────────

@router.get("/consent")
def list_consents(workflow_id: str = Query(None), active_only: bool = Query(True),
                  _auth=Depends(ui_read_auth)):
    return {"consents": db.list_consents(workflow_id=workflow_id, active_only=active_only)}

@router.post("/consent", status_code=201)
def grant_consent(body: ConsentBody, _auth=Depends(ui_write_auth)):
    return db.grant_consent(
        scope=body.scope, workflow_id=body.workflow_id,
        consent_type=body.consent_type, granted_by=body.granted_by,
        notes=body.notes, expires_at=body.expires_at,
    )

@router.delete("/consent/{consent_id}", status_code=204)
def revoke_consent(consent_id: str, _auth=Depends(ui_write_auth)):
    db.revoke_consent(consent_id)
