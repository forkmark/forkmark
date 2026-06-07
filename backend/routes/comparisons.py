"""Comparison and decision endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional

from backend.deps import (
    db, ui_read_auth, ui_write_auth, cached_inline_diff,
    divergence_score, summarize_divergence,
)
from core.models import DecisionChoice, ConfidenceLevel

router = APIRouter(prefix="/api", tags=["comparisons"])


class DecisionCreate(BaseModel):
    reviewer_id: str = Field("default", max_length=256)
    choice: str = Field(..., max_length=20)
    confidence: str = Field("medium", max_length=20)
    rationale_for_choice: str = Field(..., max_length=10_000)
    rationale_for_rejection: str = Field("", max_length=10_000)
    tags: List[str] = Field(default=[], max_length=50)


@router.get("/comparisons/{comp_id}/score-status")
def get_score_status(comp_id: str, _auth=Depends(ui_read_auth)):
    comp = db.get_comparison(comp_id)
    if not comp:
        raise HTTPException(404, "Comparison not found")
    return {
        "id": comp.id,
        "scoring_status": comp.scoring_status,
        "divergence_score": comp.divergence_score,
        "step_divergence_scores": comp.step_divergence_scores,
        "eval_results": comp.eval_results,
    }


@router.get("/comparisons")
def list_comparisons(workflow_id: str = Query(None),
                     undecided_only: bool = Query(False),
                     eval_run_id: str = Query(None),
                     run_id: str = Query(None),
                     limit: int = Query(200, le=1000),
                     offset: int = Query(0, ge=0),
                     cursor: str = Query(None),
                     _auth=Depends(ui_read_auth)):
    comps = db.list_comparisons(workflow_id, undecided_only, eval_run_id,
                                run_id=run_id, limit=limit, offset=offset, cursor=cursor)
    return [c.to_dict() for c in comps]


@router.get("/comparisons/{comp_id}")
def get_comparison(comp_id: str, _auth=Depends(ui_read_auth)):
    full = db.get_comparison_full(comp_id)
    if not full:
        raise HTTPException(404, "Comparison not found")

    comp = full["comp"]
    branch_a = full["branch_a"]
    branch_b = full["branch_b"]
    steps_a = full["steps_a"]
    steps_b = full["steps_b"]

    steps_b_map = {s.step_name: s for s in steps_b}
    step_diffs = []
    for sa in steps_a:
        sb = steps_b_map.get(sa.step_name)
        if sb:
            score = comp.step_divergence_scores.get(sa.step_name) or \
                    divergence_score(sa.output_text, sb.output_text)
            diff_key = f"{comp_id}:{sa.step_name}"
            diff = list(cached_inline_diff(diff_key, sa.output_text or "", sb.output_text or ""))
            summary = summarize_divergence(sa.output_text, sb.output_text, score)
            step_diffs.append({
                "step_name": sa.step_name,
                "step_index": sa.step_index,
                "branch_a": {**sa.to_dict(), "model_id": sa.model_id},
                "branch_b": {**sb.to_dict(), "model_id": sb.model_id},
                "divergence_score": score,
                "divergence_summary": summary,
                "inline_diff": diff,
            })

    decision = full["decision"].to_dict() if full["decision"] else None

    return {
        **comp.to_dict(),
        "branch_a": branch_a.to_dict() if branch_a else None,
        "branch_b": branch_b.to_dict() if branch_b else None,
        "steps": step_diffs,
        "decision": decision,
        "eval_run": full["eval_run_info"],
        "run_input": full["run_input"],
    }


@router.get("/costs")
def get_costs(run_id: str = Query(None),
              comparison_id: str = Query(None),
              eval_run_id: str = Query(None),
              _auth=Depends(ui_read_auth)):
    if not any([run_id, comparison_id, eval_run_id]):
        raise HTTPException(400, "Provide run_id, comparison_id, or eval_run_id")
    return db.get_cost_breakdown(
        run_id=run_id, comparison_id=comparison_id, eval_run_id=eval_run_id,
    )


@router.post("/comparisons/{comp_id}/decide", status_code=201)
def record_decision(comp_id: str, body: DecisionCreate, _auth=Depends(ui_write_auth)):
    comp = db.get_comparison(comp_id)
    if not comp:
        raise HTTPException(404, "Comparison not found")
    if comp.decided:
        raise HTTPException(409, "Already decided — use PATCH to update")
    try:
        choice = DecisionChoice(body.choice)
        conf = ConfidenceLevel(body.confidence)
    except ValueError as e:
        raise HTTPException(400, str(e))

    div = comp.divergence_score
    if div is None:
        steps_a = db.get_step_outputs_for_branch(comp.branch_a_id)
        steps_b = db.get_step_outputs_for_branch(comp.branch_b_id)
        text_a = " ".join(s.output_text for s in steps_a)
        text_b = " ".join(s.output_text for s in steps_b)
        div = divergence_score(text_a, text_b)

    div_sum = summarize_divergence("", "", div)
    winner_id = comp.branch_a_id if choice == DecisionChoice.BRANCH_A else (
                comp.branch_b_id if choice == DecisionChoice.BRANCH_B else None)
    loser_id = comp.branch_b_id if choice == DecisionChoice.BRANCH_A else (
               comp.branch_a_id if choice == DecisionChoice.BRANCH_B else None)

    run = db.get_run(comp.run_id)
    d = db.create_decision(
        comparison_id=comp_id, run_id=comp.run_id,
        workflow_id=run.workflow_id if run else comp.workflow_id,
        reviewer_id=body.reviewer_id, choice=choice, confidence=conf,
        rationale_for_choice=body.rationale_for_choice,
        rationale_for_rejection=body.rationale_for_rejection,
        tags=body.tags, branch_winner_id=winner_id, branch_loser_id=loser_id,
        divergence_score=div, divergence_summary=div_sum,
        eval_run_id=comp.eval_run_id,
    )
    return d.to_dict()


@router.patch("/comparisons/{comp_id}/decide")
def update_decision(comp_id: str, body: DecisionCreate, _auth=Depends(ui_write_auth)):
    comp = db.get_comparison(comp_id)
    if not comp:
        raise HTTPException(404, "Comparison not found")
    if not comp.decided:
        raise HTTPException(400, "No decision to update — use POST first")
    if not comp.decision_id:
        raise HTTPException(400, "No decision_id found on comparison")
    try:
        choice = DecisionChoice(body.choice)
        conf = ConfidenceLevel(body.confidence)
    except ValueError as e:
        raise HTTPException(400, str(e))

    winner_id = comp.branch_a_id if choice == DecisionChoice.BRANCH_A else (
                comp.branch_b_id if choice == DecisionChoice.BRANCH_B else None)
    loser_id = comp.branch_b_id if choice == DecisionChoice.BRANCH_A else (
               comp.branch_a_id if choice == DecisionChoice.BRANCH_B else None)

    d = db.update_decision(
        decision_id=comp.decision_id, choice=choice, confidence=conf,
        rationale_for_choice=body.rationale_for_choice,
        rationale_for_rejection=body.rationale_for_rejection,
        tags=body.tags,
        reviewer_id=body.reviewer_id if body.reviewer_id != "default" else None,
        branch_winner_id=winner_id, branch_loser_id=loser_id,
    )
    if not d:
        raise HTTPException(404, "Decision not found")
    return d.to_dict()
