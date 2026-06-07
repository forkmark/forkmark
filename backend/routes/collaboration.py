"""Collaboration endpoints: comments, review assignments, review queue."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional

from backend.deps import db, ui_read_auth, ui_write_auth

router = APIRouter(prefix="/api", tags=["collaboration"])


class CommentCreate(BaseModel):
    author_id: str
    author_name: str = ""
    body: str
    parent_id: Optional[str] = None

class CommentUpdate(BaseModel):
    body: Optional[str] = None
    is_resolved: Optional[bool] = None

class ReviewAssignBody(BaseModel):
    reviewer_id: str
    assigned_by: str = ""
    notes: str = ""

class BulkAssignBody(BaseModel):
    reviewer_ids: list
    assigned_by: str = ""

class AssignmentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


# ── Comments ─────────────────────────────────────────────────────────────────

@router.get("/comparisons/{comp_id}/comments")
def list_comments(comp_id: str, _auth=Depends(ui_read_auth)):
    return db.list_comments(comp_id)

@router.post("/comparisons/{comp_id}/comments", status_code=201)
def add_comment(comp_id: str, body: CommentCreate, _auth=Depends(ui_write_auth)):
    comp = db.get_comparison(comp_id)
    if not comp:
        raise HTTPException(404, "Comparison not found")
    return db.add_comment(comp_id, body.author_id, body.body,
                          author_name=body.author_name, parent_id=body.parent_id)

@router.patch("/comments/{comment_id}")
def update_comment(comment_id: str, body: CommentUpdate, _auth=Depends(ui_write_auth)):
    c = db.get_comment(comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    return db.update_comment(comment_id, body=body.body, is_resolved=body.is_resolved)

@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: str, _auth=Depends(ui_write_auth)):
    db.delete_comment(comment_id)


# ── Review assignments ───────────────────────────────────────────────────────

@router.post("/comparisons/{comp_id}/assign", status_code=201)
def assign_review(comp_id: str, body: ReviewAssignBody, _auth=Depends(ui_write_auth)):
    comp = db.get_comparison(comp_id)
    if not comp:
        raise HTTPException(404, "Comparison not found")
    return db.assign_review(
        eval_run_id=comp.get("eval_run_id", "") if isinstance(comp, dict) else getattr(comp, "eval_run_id", ""),
        comparison_id=comp_id, reviewer_id=body.reviewer_id,
        assigned_by=body.assigned_by, notes=body.notes,
    )

@router.post("/eval-runs/{er_id}/assign", status_code=201)
def bulk_assign_reviews(er_id: str, body: BulkAssignBody, _auth=Depends(ui_write_auth)):
    er = db.get_eval_run(er_id)
    if not er:
        raise HTTPException(404, "Eval run not found")
    assignments = db.bulk_assign_reviews(er_id, body.reviewer_ids, body.assigned_by)
    return {"assigned": len(assignments), "assignments": assignments}

@router.patch("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, body: AssignmentStatusUpdate,
                      _auth=Depends(ui_write_auth)):
    a = db.get_assignment(assignment_id)
    if not a:
        raise HTTPException(404, "Assignment not found")
    valid = ("pending", "in_review", "completed", "skipped")
    if body.status not in valid:
        raise HTTPException(400, f"status must be one of: {', '.join(valid)}")
    return db.update_assignment_status(assignment_id, body.status, body.notes)

@router.get("/assignments")
def list_assignments(eval_run_id: str = Query(None),
                     reviewer_id: str = Query(None),
                     status: str = Query(None),
                     _auth=Depends(ui_read_auth)):
    return db.list_assignments(eval_run_id=eval_run_id, reviewer_id=reviewer_id, status=status)

@router.get("/review-queue/{reviewer_id}")
def get_review_queue(reviewer_id: str, _auth=Depends(ui_read_auth)):
    return db.get_review_queue(reviewer_id)
