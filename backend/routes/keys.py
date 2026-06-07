"""API key management endpoints."""
from __future__ import annotations

import hmac
import os
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field

from backend.deps import db, ui_write_auth

router = APIRouter(prefix="/api", tags=["keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=256)


@router.get("/keys")
def list_keys(_auth=Depends(ui_write_auth)):
    return [k.to_dict() for k in db.list_api_keys()]


@router.post("/keys", status_code=201)
def create_key(body: ApiKeyCreate, request: Request,
               x_api_key: str = Header(None, alias="X-API-Key")):
    existing = db.list_api_keys(active_only=True)
    if existing:
        if not x_api_key:
            raise HTTPException(401, "X-API-Key required to create additional keys")
        if not db.verify_api_key(x_api_key):
            raise HTTPException(401, "Invalid or revoked API key")
    else:
        bootstrap_token = os.getenv("FM_BOOTSTRAP_TOKEN")
        client_host = request.client.host if request.client else ""
        if client_host != "127.0.0.1" and client_host != "::1":
            if not bootstrap_token or not hmac.compare_digest(
                    str(x_api_key or ""), str(bootstrap_token)):
                raise HTTPException(401, "Must be on localhost or provide FM_BOOTSTRAP_TOKEN")
    ak, raw = db.create_api_key(body.name)
    return {**ak.to_dict(), "raw_key": raw}


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, _auth=Depends(ui_write_auth)):
    db.revoke_api_key(key_id)
