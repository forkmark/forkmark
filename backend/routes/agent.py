"""Agent comparison API endpoints.

All endpoints are gated behind the agent_comparison feature flag.
SDK endpoints require API key; UI endpoints use conditional auth.

Endpoints:
  POST /api/agent/trace-events/batch  — Bulk-create trace events (SDK)
  GET  /api/agent/trace-events        — List trace events for a branch/run (UI)
  POST /api/agent/comparisons         — Create agent comparison with trajectory scoring
  GET  /api/agent/trajectory/{comparison_id} — Get trajectory outcome for a comparison
  GET  /api/agent/feature-status      — Check if agent comparison is enabled
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from backend.deps import db, require_key, ui_read_auth, ui_write_auth
from config import config
from core.feature_flags import agent_comparison_enabled


router = APIRouter(prefix="/api/agent", tags=["agent"])


# ── Feature gate dependency ──────────────────────────────────────────────────

def _require_agent_feature():
    """Dependency that checks agent comparison is enabled."""
    if not config.ENABLE_AGENT_COMPARISON:
        raise HTTPException(
            status_code=403,
            detail="Agent comparison feature is disabled. "
                   "Set FM_ENABLE_AGENT_COMPARISON=true to enable.",
        )
    return True


# ── Request/Response schemas ─────────────────────────────────────────────────

class TraceEventCreate(BaseModel):
    id: Optional[str] = None
    branch_id: str = Field(..., max_length=64)
    run_id: str = Field(..., max_length=64)
    parent_event_id: Optional[str] = Field(None, max_length=64)
    event_type: str = Field("tool_call", max_length=32)
    event_index: int = 0
    name: str = Field("", max_length=256)
    input_data: dict = {}
    output_data: dict = {}
    status: str = Field("completed", max_length=32)
    latency_ms: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: Optional[float] = None
    metadata: dict = {}


class TraceEventBatchCreate(BaseModel):
    events: List[TraceEventCreate] = Field(..., max_length=500)


class AgentComparisonCreate(BaseModel):
    run_id: str = Field(..., max_length=64)
    branch_a_id: str = Field(..., max_length=64)
    branch_b_id: str = Field(..., max_length=64)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/feature-status")
def get_feature_status():
    """Check if agent comparison feature is enabled."""
    return {
        "enabled": config.ENABLE_AGENT_COMPARISON,
        "feature": "agent_comparison",
    }


@router.post("/trace-events/batch",
             dependencies=[Depends(_require_agent_feature)])
def create_trace_events_batch(
    body: TraceEventBatchCreate,
    api_key: str = Depends(require_key),
):
    """Bulk-create trace events (SDK endpoint, requires API key)."""
    if not body.events:
        return {"created": 0}

    events_to_insert = []
    for ev in body.events:
        event_dict = ev.model_dump() if hasattr(ev, 'model_dump') else ev.dict()
        if not event_dict.get("id"):
            event_dict["id"] = f"te_{uuid.uuid4().hex[:12]}"
        events_to_insert.append(event_dict)

    try:
        db.create_trace_events_batch(events_to_insert)
    except Exception as e:
        raise HTTPException(500, f"Failed to create trace events: {e}")

    return {"created": len(events_to_insert)}


@router.get("/trace-events",
            dependencies=[Depends(_require_agent_feature)])
def list_trace_events(
    branch_id: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
    parent_event_id: Optional[str] = Query("__UNSET__"),
    _auth: Optional[str] = Depends(ui_read_auth),
):
    """List trace events for a branch or run (UI endpoint)."""
    if not branch_id and not run_id:
        raise HTTPException(400, "Provide branch_id or run_id")

    events = db.get_trace_events(
        branch_id=branch_id,
        run_id=run_id,
        parent_event_id=parent_event_id if parent_event_id != "__UNSET__" else "__UNSET__",
    )
    return [e.to_dict() for e in events]


@router.post("/comparisons",
             dependencies=[Depends(_require_agent_feature)])
def create_agent_comparison(
    body: AgentComparisonCreate,
    api_key: str = Depends(require_key),
):
    """Create a comparison between two agent branches with trajectory scoring.

    This endpoint:
    1. Retrieves trace events for both branches
    2. Runs the trajectory comparator (sequence alignment + outcome + efficiency)
    3. Stores the trajectory outcome
    4. Creates the standard comparison record
    """
    from core.trajectory_comparator import compare_trajectories

    # Fetch trace events for both branches
    events_a = db.get_trace_events(branch_id=body.branch_a_id)
    events_b = db.get_trace_events(branch_id=body.branch_b_id)

    # Run trajectory comparison
    traj_result = compare_trajectories(events_a, events_b)

    # Get workflow_id from the run
    try:
        with db._read_conn() as c:
            row = c.fetchone(
                "SELECT workflow_id FROM workflow_runs WHERE id = ?",
                (body.run_id,),
            )
        workflow_id = dict(row)["workflow_id"] if row else ""
    except Exception:
        workflow_id = ""

    # Create comparison record (standard)
    comp_id = f"comp_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    # Collect step names from trace events
    step_names = list({e.name for e in events_a} | {e.name for e in events_b})

    try:
        with db._conn() as c:
            c.execute(
                "INSERT INTO comparisons (id, run_id, workflow_id, branch_a_id, "
                "branch_b_id, created_at, step_names, divergence_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (comp_id, body.run_id, workflow_id, body.branch_a_id,
                 body.branch_b_id, now, json.dumps(step_names),
                 1.0 - traj_result["trajectory_score"]),
            )
    except Exception as e:
        raise HTTPException(500, f"Failed to create comparison: {e}")

    # Store trajectory outcome
    outcome_id = f"to_{uuid.uuid4().hex[:12]}"
    try:
        db.create_trajectory_outcome(
            id=outcome_id,
            comparison_id=comp_id,
            run_id=body.run_id,
            workflow_id=workflow_id,
            tool_sequence_score=traj_result["tool_sequence_score"],
            outcome_equivalence_score=traj_result["outcome_equivalence_score"],
            efficiency_score=traj_result["efficiency_score"],
            trajectory_score=traj_result["trajectory_score"],
            tool_sequence_detail=traj_result["tool_sequence_detail"],
            outcome_detail=traj_result["outcome_detail"],
            efficiency_detail=traj_result["efficiency_detail"],
            branch_a_tool_count=traj_result["branch_a_tool_count"],
            branch_b_tool_count=traj_result["branch_b_tool_count"],
            branch_a_depth=traj_result["branch_a_depth"],
            branch_b_depth=traj_result["branch_b_depth"],
            branch_a_total_latency_ms=traj_result["branch_a_total_latency_ms"],
            branch_b_total_latency_ms=traj_result["branch_b_total_latency_ms"],
            branch_a_total_cost_usd=traj_result["branch_a_total_cost_usd"],
            branch_b_total_cost_usd=traj_result["branch_b_total_cost_usd"],
        )
    except Exception as e:
        # Non-fatal: comparison was created, trajectory scoring failed
        import logging
        logging.getLogger("forkmark.agent").warning(
            f"Trajectory outcome creation failed: {e}"
        )

    return {
        "comparison_id": comp_id,
        "trajectory_outcome_id": outcome_id,
        "trajectory_score": traj_result["trajectory_score"],
        "tool_sequence_score": traj_result["tool_sequence_score"],
        "outcome_equivalence_score": traj_result["outcome_equivalence_score"],
        "efficiency_score": traj_result["efficiency_score"],
    }


@router.get("/trajectory/{comparison_id}",
            dependencies=[Depends(_require_agent_feature)])
def get_trajectory_outcome(
    comparison_id: str,
    _auth: Optional[str] = Depends(ui_read_auth),
):
    """Get trajectory comparison outcome for a specific comparison."""
    outcomes = db.get_trajectory_outcomes(comparison_id=comparison_id)
    if not outcomes:
        raise HTTPException(404, "No trajectory outcome found for this comparison")
    return outcomes[0].to_dict()
