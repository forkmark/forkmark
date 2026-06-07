"""Preference corpus and data export endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse

from backend.deps import db, ui_read_auth

router = APIRouter(prefix="/api", tags=["exports"])


@router.get("/eval-runs/{er_id}/export/preference-corpus")
def export_preference_corpus(er_id: str,
                             anonymize: bool = Query(True),
                             require_consent: bool = Query(False),
                             _auth=Depends(ui_read_auth)):
    er = db.get_eval_run(er_id)
    if not er:
        raise HTTPException(404, "Eval run not found")

    def _stream():
        for line in db.export_preference_corpus_jsonl(
            eval_run_id=er_id, anonymize=anonymize, require_consent=require_consent,
        ):
            yield line + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson",
                             headers={"Content-Disposition":
                                      f'attachment; filename="preference_corpus_{er_id}.jsonl"'})


@router.get("/preference-corpus")
def export_global_preference_corpus(
    workflow_id: str = Query(None),
    anonymize: bool = Query(True),
    require_consent: bool = Query(False),
    _auth=Depends(ui_read_auth),
):
    def _stream():
        for line in db.export_preference_corpus_jsonl(
            workflow_id=workflow_id, anonymize=anonymize, require_consent=require_consent,
        ):
            yield line + "\n"

    fname = f"preference_corpus_{workflow_id or 'all'}.jsonl"
    return StreamingResponse(_stream(), media_type="application/x-ndjson",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
