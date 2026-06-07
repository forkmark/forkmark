"""LLM provider management endpoints."""
from __future__ import annotations

import os
import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.deps import db, ui_read_auth, ui_write_auth

router = APIRouter(prefix="/api", tags=["providers"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(default="openai")
    base_url: str = ""
    api_key: str = ""
    is_default: bool = False

class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None      # empty string = keep existing key
    is_default: Optional[bool] = None

class ProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str = "openai"
    base_url: str = ""
    api_key_set: bool = False
    api_key_masked: str = ""
    is_default: bool = False
    created_at: str
    updated_at: str

class ProviderTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int = 0


# ── Valid provider types ────────────────────────────────────────────────────

_VALID_TYPES = {"openai", "anthropic", "openrouter", "ollama", "custom"}


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/providers", response_model=List[ProviderResponse])
def list_providers(_auth=Depends(ui_read_auth)):
    # Auto-migrate legacy key on first access
    db.migrate_legacy_provider()
    return db.list_providers()


@router.post("/providers", status_code=201, response_model=ProviderResponse)
def create_provider(body: ProviderCreate, _auth=Depends(ui_write_auth)):
    ptype = body.provider_type.lower().strip()
    if ptype not in _VALID_TYPES:
        raise HTTPException(400,
            f"Invalid provider_type: {ptype!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_TYPES))}")
    result = db.create_provider(
        name=body.name, provider_type=ptype,
        base_url=body.base_url.strip(), api_key=body.api_key,
        is_default=body.is_default,
    )
    # Re-fetch to get masked key fields
    return db.get_provider(result["id"]) or result


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
def update_provider(provider_id: str, body: ProviderUpdate,
                    _auth=Depends(ui_write_auth)):
    kwargs = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.provider_type is not None:
        ptype = body.provider_type.lower().strip()
        if ptype not in _VALID_TYPES:
            raise HTTPException(400, f"Invalid provider_type: {ptype!r}")
        kwargs["provider_type"] = ptype
    if body.base_url is not None:
        kwargs["base_url"] = body.base_url.strip()
    if body.api_key is not None:
        kwargs["api_key"] = body.api_key
    if body.is_default is not None:
        kwargs["is_default"] = body.is_default

    result = db.update_provider(provider_id, **kwargs)
    if result is None:
        raise HTTPException(404, "Provider not found")
    return result


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: str, _auth=Depends(ui_write_auth)):
    ok = db.delete_provider(provider_id)
    if not ok:
        raise HTTPException(404, "Provider not found")


@router.post("/providers/{provider_id}/test", response_model=ProviderTestResult)
def test_provider(provider_id: str, _auth=Depends(ui_write_auth)):
    """Test a provider's connection by making a lightweight API call."""
    creds = db.get_provider_credentials(provider_id)
    if creds is None:
        raise HTTPException(404, "Provider not found")
    if not creds["api_key"]:
        return {"ok": False, "message": "No API key configured for this provider",
                "latency_ms": 0}

    import httpx
    ptype = creds.get("provider_type", "openai")
    base = creds["base_url"].rstrip("/") if creds["base_url"] else ""

    try:
        t0 = time.time()

        if ptype == "anthropic":
            # Anthropic uses a different API format
            url = (base or "https://api.anthropic.com") + "/v1/messages"
            resp = httpx.post(url, json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }, headers={
                "x-api-key": creds["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }, timeout=15)
        else:
            # OpenAI-compatible (openai, openrouter, ollama, custom)
            url = (base or "https://api.openai.com/v1") + "/models"
            resp = httpx.get(url, headers={
                "Authorization": f"Bearer {creds['api_key']}",
            }, timeout=15)

        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code < 400:
            return {"ok": True,
                    "message": f"Connection successful ({latency_ms}ms)",
                    "latency_ms": latency_ms}
        else:
            detail = resp.text[:200]
            return {"ok": False,
                    "message": f"API returned {resp.status_code}: {detail}",
                    "latency_ms": latency_ms}

    except httpx.ConnectError:
        return {"ok": False,
                "message": f"Could not connect to {base or 'API endpoint'}",
                "latency_ms": 0}
    except httpx.TimeoutException:
        return {"ok": False, "message": "Connection timed out (15s)",
                "latency_ms": 15000}
    except Exception as e:
        return {"ok": False, "message": f"Connection failed: {str(e)[:200]}",
                "latency_ms": 0}
