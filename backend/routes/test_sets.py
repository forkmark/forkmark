"""Test set endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.deps import db, ui_read_auth, ui_write_auth

router = APIRouter(prefix="/api", tags=["test-sets"])


class TestSetCreate(BaseModel):
    name: str = Field(..., max_length=256)
    description: str = Field("", max_length=2000)
    workflow_id: Optional[str] = Field(None, max_length=64)

class TestCaseCreate(BaseModel):
    label: str = Field(..., max_length=256)
    input_data: dict = {}
    tags: List[str] = Field(default=[], max_length=50)
    expected_output: Optional[str] = Field(None, max_length=500_000)

class BulkTestCasesCreate(BaseModel):
    cases: List[dict] = Field(..., max_length=1000)

class TestCaseMetadataBody(BaseModel):
    domain: str = ""
    industry: str = ""
    use_case_type: str = ""
    failure_mode: str = ""
    test_goal: str = ""


@router.get("/test-sets")
def list_test_sets(workflow_id: str = Query(None), _auth=Depends(ui_read_auth)):
    return [ts.to_dict() for ts in db.list_test_sets(workflow_id)]

@router.post("/test-sets", status_code=201)
def create_test_set(body: TestSetCreate, _auth=Depends(ui_write_auth)):
    ts = db.create_test_set(body.name, body.description, body.workflow_id)
    return ts.to_dict()

@router.get("/test-sets/{ts_id}")
def get_test_set(ts_id: str, _auth=Depends(ui_read_auth)):
    ts = db.get_test_set(ts_id)
    if not ts:
        raise HTTPException(404, "Test set not found")
    cases = db.list_test_cases(ts_id)
    return {**ts.to_dict(), "cases": [c.to_dict() for c in cases]}

@router.delete("/test-sets/{ts_id}", status_code=204)
def delete_test_set(ts_id: str, _auth=Depends(ui_write_auth)):
    db.delete_test_set(ts_id)

@router.post("/test-sets/{ts_id}/cases", status_code=201)
def add_test_case(ts_id: str, body: TestCaseCreate, _auth=Depends(ui_write_auth)):
    try:
        tc = db.add_test_case(ts_id, body.label, body.input_data, body.tags,
                              expected_output=body.expected_output)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return tc.to_dict()

@router.post("/test-sets/{ts_id}/cases/bulk", status_code=201)
def bulk_add_test_cases(ts_id: str, body: BulkTestCasesCreate, _auth=Depends(ui_write_auth)):
    cases = db.bulk_add_test_cases(ts_id, body.cases)
    return [c.to_dict() for c in cases]

@router.delete("/test-sets/{ts_id}/cases/{tc_id}", status_code=204)
def delete_test_case(ts_id: str, tc_id: str, _auth=Depends(ui_write_auth)):
    try:
        db.delete_test_case(tc_id, test_set_id=ts_id)
    except ValueError as e:
        raise HTTPException(409, str(e))

@router.post("/test-sets/{ts_id}/version", status_code=201)
def create_test_set_version(ts_id: str, _auth=Depends(ui_write_auth)):
    try:
        new_ts = db.create_test_set_version(ts_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return new_ts.to_dict()

@router.patch("/test-sets/{ts_id}/cases/{tc_id}/metadata", status_code=200)
def patch_test_case_metadata(ts_id: str, tc_id: str, body: TestCaseMetadataBody,
                             _auth=Depends(ui_write_auth)):
    ts = db.get_test_set(ts_id)
    if not ts:
        raise HTTPException(404, "Test set not found")
    db.update_test_case_metadata(
        tc_id, domain=body.domain, industry=body.industry,
        use_case_type=body.use_case_type, failure_mode=body.failure_mode,
        test_goal=body.test_goal,
    )
    return {"ok": True}
