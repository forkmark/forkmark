"""Workflow endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List

from backend.response_models import WorkflowResponse, RunDetailResponse
from backend.deps import db, ui_read_auth, ui_write_auth

router = APIRouter(prefix="/api", tags=["workflows"])


class WorkflowBody(BaseModel):
    name: str = Field(..., max_length=256)
    description: str = Field("", max_length=2000)
    tags: List[str] = Field(default=[], max_length=50)


@router.get("/workflows")
def list_workflows(_auth=Depends(ui_read_auth)):
    return [w.to_dict() for w in db.list_workflows()]

@router.get("/workflows/{wf_id}")
def get_workflow(wf_id: str, _auth=Depends(ui_read_auth)):
    wf = db.get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf.to_dict()

@router.post("/workflows", status_code=201)
def create_workflow(body: WorkflowBody, _auth=Depends(ui_write_auth)):
    wf = db.upsert_workflow(body.name, body.description, body.tags)
    return wf.to_dict()

@router.delete("/workflows/{wf_id}", status_code=204)
def delete_workflow(wf_id: str, _auth=Depends(ui_write_auth)):
    db.delete_workflow(wf_id)

@router.get("/workflows/{wf_id}/runs")
def list_runs(wf_id: str, limit: int = Query(50, le=500), cursor: str = Query(None),
              _auth=Depends(ui_read_auth)):
    return [r.to_dict() for r in db.list_runs(wf_id, limit, cursor=cursor)]

@router.get("/runs/{run_id}")
def get_run(run_id: str, _auth=Depends(ui_read_auth)):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    branches = db.list_branches(run_id)
    steps = db.get_step_outputs_for_run(run_id)
    run_comps = db.list_comparisons(run_id=run_id)
    return {
        **r.to_dict(),
        "branches":    [b.to_dict() for b in branches],
        "steps":       [s.to_dict() for s in steps],
        "comparisons": [c.to_dict() for c in run_comps],
    }

@router.get("/workflows/{wf_id}/test-case-corpus")
def export_test_case_corpus(wf_id: str, min_eval_runs: int = Query(1),
                            include_performance: bool = Query(True),
                            _auth=Depends(ui_read_auth)):
    wf = db.get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")

    def _stream():
        for line in db.export_test_case_corpus_jsonl(
            workflow_id=wf_id, min_eval_runs=min_eval_runs,
            include_performance=include_performance,
        ):
            yield line + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":
                                      f'attachment; filename="test_case_corpus_{wf_id}.jsonl"'})
