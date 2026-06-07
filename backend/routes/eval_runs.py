"""Eval run UI endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.deps import db, ui_read_auth, ui_write_auth
from backend.response_models import EvalRunResponse, OkResponse
from core.models import EvalRunStatus

router = APIRouter(prefix="/api", tags=["eval-runs"])


class EvalRunCreateBody(BaseModel):
    workflow_name: str = Field(..., max_length=256)
    name: str = Field(..., max_length=256)
    description: str = Field("", max_length=2000)
    branch_a_config: dict = {}
    branch_b_config: dict = {}
    test_set_id: Optional[str] = Field(None, max_length=64)
    total_cases: int = 0

class EvalRunCompleteBody(BaseModel):
    status: str = "completed"
    total_cases: Optional[int] = None


@router.get("/eval-runs", response_model=List[EvalRunResponse])
def list_eval_runs(workflow_id: str = Query(None), limit: int = Query(50, le=200),
                   _auth=Depends(ui_read_auth)):
    ers = db.list_eval_runs(workflow_id, limit)
    if not ers:
        return []
    batch_stats = db.batch_eval_run_stats([er.id for er in ers])
    return [{**er.to_dict(), "stats": batch_stats[er.id]} for er in ers]


@router.post("/eval-runs", status_code=201)
def create_eval_run(body: EvalRunCreateBody, _auth=Depends(ui_write_auth)):
    wf = db.upsert_workflow(body.workflow_name)
    er = db.create_eval_run(
        workflow_id=wf.id, name=body.name, description=body.description,
        branch_a_config=body.branch_a_config, branch_b_config=body.branch_b_config,
        test_set_id=body.test_set_id, total_cases=body.total_cases,
    )
    return er.to_dict()


@router.get("/eval-runs/{er_id}")
def get_eval_run(er_id: str, _auth=Depends(ui_read_auth)):
    er = db.get_eval_run(er_id)
    if not er:
        raise HTTPException(404, "Eval run not found")
    stats = db.get_eval_run_stats(er_id)
    return {**er.to_dict(), "stats": stats}


@router.delete("/eval-runs/{er_id}", status_code=204)
def delete_eval_run(er_id: str, _auth=Depends(ui_write_auth)):
    db.delete_eval_run(er_id)


@router.patch("/eval-runs/{er_id}/complete")
def complete_eval_run(er_id: str, body: EvalRunCompleteBody, _auth=Depends(ui_write_auth)):
    er = db.get_eval_run(er_id)
    if not er:
        raise HTTPException(404, "Eval run not found")
    try:
        status = EvalRunStatus(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}")
    db.update_eval_run_status(er_id, status, total_cases=body.total_cases)
    return {"ok": True}


@router.get("/eval-runs/{er_id}/export")
def export_eval_run_decisions(er_id: str, _auth=Depends(ui_read_auth)):
    generator = db.export_decisions_jsonl(eval_run_id=er_id)
    return StreamingResponse(
        generator, media_type="application/x-ndjson",
        headers={"Content-Disposition": f"attachment; filename=eval_{er_id[:8]}_decisions.jsonl"},
    )


@router.get("/eval-runs/{er_id}/review-stats")
def get_review_stats(er_id: str, _auth=Depends(ui_read_auth)):
    return db.get_review_stats(er_id)
