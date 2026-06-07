"""Admin endpoints (pruning, maintenance)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.deps import db, ui_write_auth

router = APIRouter(prefix="/api", tags=["admin"])


class PruneBody(BaseModel):
    older_than_days: int = 30


@router.delete("/admin/prune", status_code=200)
def admin_prune(body: PruneBody, _auth=Depends(ui_write_auth)):
    if body.older_than_days < 1:
        raise HTTPException(400, "older_than_days must be >= 1")
    deleted = db.prune_step_outputs(body.older_than_days)
    return {"deleted_rows": deleted, "older_than_days": body.older_than_days}
