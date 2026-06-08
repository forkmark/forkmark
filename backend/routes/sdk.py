"""SDK endpoints — always require API key authentication."""
from __future__ import annotations

import hashlib
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.deps import db, require_key, async_enqueue_scoring
from core.models import RunStatus, EvalRunStatus


router = APIRouter(prefix="/api/sdk", tags=["sdk"])


# ── Request schemas ──────────────────────────────────────────────────────────

class EvalRunCreate(BaseModel):
    workflow_name: str = Field(..., max_length=256)
    name: str = Field(..., max_length=256)
    description: str = Field("", max_length=2000)
    branch_a_config: dict = {}
    branch_b_config: dict = {}
    test_set_id: Optional[str] = Field(None, max_length=64)
    total_cases: int = 0

class EvalRunComplete(BaseModel):
    status: str = "completed"
    total_cases: Optional[int] = None

class RunCreate(BaseModel):
    workflow_name: str = Field(..., max_length=256)
    input_data: dict = {}
    metadata: dict = {}
    eval_run_id: Optional[str] = Field(None, max_length=64)
    test_case_label: str = Field("", max_length=256)

class RunComplete(BaseModel):
    status: str = "completed"

class BranchCreate(BaseModel):
    run_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=256)
    model_id: str = Field(..., max_length=256)
    temperature: float = 0.7
    system_prompt: Optional[str] = Field(None, max_length=100_000)
    extra_config: dict = {}
    is_baseline: bool = False

class StepCreate(BaseModel):
    run_id: str = Field(..., max_length=64)
    branch_id: str = Field(..., max_length=64)
    step_name: str = Field(..., max_length=256)
    step_index: int
    input_messages: list = []
    output_text: str = Field(..., max_length=500_000)
    model_id: str = Field(..., max_length=256)
    temperature: float = 0.7
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    error: Optional[str] = Field(None, max_length=10_000)
    trace_id: Optional[str] = Field(None, max_length=128)
    span_id: Optional[str] = Field(None, max_length=128)

class StepBatchCreate(BaseModel):
    steps: List[StepCreate]

class ComparisonCreate(BaseModel):
    run_id: str = Field(..., max_length=64)
    branch_a_id: str = Field(..., max_length=64)
    branch_b_id: str = Field(..., max_length=64)
    step_names: List[str] = Field(default=[], max_length=100)
    evaluator_configs: List[dict] = Field(default=[], max_length=50)


# ── Response schemas ─────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = True


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/eval-runs", status_code=201)
def sdk_create_eval_run(body: EvalRunCreate, key: str = Depends(require_key)):
    wf = db.upsert_workflow(body.workflow_name)
    er = db.create_eval_run(
        workflow_id=wf.id, name=body.name, description=body.description,
        branch_a_config=body.branch_a_config, branch_b_config=body.branch_b_config,
        test_set_id=body.test_set_id, total_cases=body.total_cases,
    )
    db.update_eval_run_status(er.id, EvalRunStatus.RUNNING)
    return er.to_dict()


@router.post("/eval-runs/{er_id}/complete")
def sdk_complete_eval_run(er_id: str, body: EvalRunComplete, key: str = Depends(require_key)):
    er = db.get_eval_run(er_id)
    if not er:
        raise HTTPException(404, "Eval run not found")
    try:
        status = EvalRunStatus(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}")
    db.update_eval_run_status(er_id, status, total_cases=body.total_cases)
    return OkResponse()


@router.post("/runs", status_code=201)
def sdk_create_run(body: RunCreate, key: str = Depends(require_key)):
    wf = db.upsert_workflow(body.workflow_name)
    run = db.create_run(
        wf.id, body.input_data, body.metadata,
        sdk_key_prefix=hashlib.sha256(key.encode()).hexdigest()[:12],
        eval_run_id=body.eval_run_id,
        test_case_label=body.test_case_label,
    )
    return run.to_dict()


@router.post("/runs/{run_id}/complete")
def sdk_complete_run(run_id: str, body: RunComplete, key: str = Depends(require_key)):
    try:
        status = RunStatus(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}")
    db.complete_run(run_id, status)
    return OkResponse()


@router.post("/branches", status_code=201)
def sdk_create_branch(body: BranchCreate, key: str = Depends(require_key)):
    run = db.get_run(body.run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    b = db.create_branch(
        run_id=body.run_id, workflow_id=run.workflow_id,
        name=body.name, model_id=body.model_id, temperature=body.temperature,
        system_prompt=body.system_prompt, extra_config=body.extra_config,
        is_baseline=body.is_baseline,
    )
    return b.to_dict()


@router.post("/steps", status_code=201)
def sdk_log_step(body: StepCreate, key: str = Depends(require_key)):
    so = db.save_step_output(
        run_id=body.run_id, branch_id=body.branch_id,
        step_name=body.step_name, step_index=body.step_index,
        input_messages=body.input_messages, output_text=body.output_text,
        model_id=body.model_id, temperature=body.temperature,
        tokens_input=body.tokens_input, tokens_output=body.tokens_output,
        latency_ms=body.latency_ms, error=body.error,
        trace_id=body.trace_id, span_id=body.span_id,
    )
    return so.to_dict()


@router.post("/steps/batch", status_code=201)
def sdk_log_steps_batch(body: StepBatchCreate, key: str = Depends(require_key)):
    """Insert up to 100 steps in a single request."""
    if len(body.steps) > 100:
        raise HTTPException(400, "Maximum 100 steps per batch")
    rows = [s.model_dump() for s in body.steps]
    saved = db.batch_save_step_outputs(rows)
    return [s.to_dict() for s in saved]


@router.post("/comparisons", status_code=201)
def sdk_create_comparison(body: ComparisonCreate, background_tasks: BackgroundTasks,
                          key: str = Depends(require_key)):
    """Create comparison and enqueue background divergence scoring."""
    run = db.get_run(body.run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    comp = db.create_comparison(
        run_id=body.run_id, workflow_id=run.workflow_id,
        branch_a_id=body.branch_a_id, branch_b_id=body.branch_b_id,
        step_names=body.step_names,
        eval_run_id=run.eval_run_id,
        test_case_label=run.test_case_label,
        scoring_status="pending",
    )
    background_tasks.add_task(async_enqueue_scoring, db, comp.id,
                              body.branch_a_id, body.branch_b_id, body.evaluator_configs)
    return comp.to_dict()
