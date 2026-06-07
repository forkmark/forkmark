"""No-code workflow runner and prompt playground endpoints."""
from __future__ import annotations

import os
import time
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.response_models import RunnerResponse, PlaygroundResponse
from backend.deps import (
    db, ui_write_auth, redis_client,
    divergence_score, summarize_divergence, async_enqueue_scoring,
)
from core.models import RunStatus, EvalRunStatus

router = APIRouter(prefix="/api", tags=["runner"])


# ── Runner schemas ───────────────────────────────────────────────────────────

class RunnerStepConfig(BaseModel):
    name: str
    system_prompt: str
    user_prompt_template: str

class RunnerBranchConfig(BaseModel):
    name: str
    model_id: str
    temperature: float = 0.7
    steps: List[RunnerStepConfig]
    provider_id: Optional[str] = None

class RunnerTestCase(BaseModel):
    label: str
    input: str

class RunnerBody(BaseModel):
    workflow_name: str
    eval_run_name: str
    branch_a: RunnerBranchConfig
    branch_b: RunnerBranchConfig
    test_cases: List[RunnerTestCase]


# ── Playground schemas ───────────────────────────────────────────────────────

class PlaygroundRequest(BaseModel):
    prompt: str
    model_a: str = "gpt-4o-mini"
    model_b: str = "gpt-4o"
    system_prompt: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=16384)
    workflow_id: Optional[str] = None
    provider_id_a: Optional[str] = None
    provider_id_b: Optional[str] = None


# ── Provider credential resolution ──────────────────────────────────────────

def _resolve_credentials(provider_id: Optional[str] = None) -> tuple:
    """Resolve LLM credentials from provider_id, default provider, or legacy settings.

    Returns (api_key, base_url). Raises HTTPException if no credentials found.
    """
    if provider_id:
        creds = db.get_provider_credentials(provider_id)
        if creds is None:
            raise HTTPException(400, f"Provider '{provider_id}' not found")
        if not creds["api_key"]:
            raise HTTPException(400, f"Provider '{provider_id}' has no API key configured")
        return creds["api_key"], creds["base_url"]

    # Try default provider
    default = db.get_default_provider_credentials()
    if default and default.get("api_key"):
        return default["api_key"], default.get("base_url", "")

    # Fall back to legacy settings
    api_key = (db.get_setting("openai_api_key")
               or os.getenv("OPENAI_API_KEY")
               or os.getenv("FM_OPENAI_API_KEY"))
    base_url = db.get_setting("openai_base_url") or ""
    if not api_key:
        raise HTTPException(400, "No LLM provider configured. Add one in Settings → Providers.")
    return api_key, base_url


# ── LLM call helper ─────────────────────────────────────────────────────────

def _call_llm(api_key: str, base_url: str, model_id: str,
              temperature: float, messages: list) -> dict:
    import httpx
    url = (base_url.rstrip("/") if base_url else "https://api.openai.com") + "/v1/chat/completions"
    t0 = time.time()
    resp = httpx.post(
        url,
        json={"model": model_id, "messages": messages, "temperature": temperature},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60,
    )
    latency_ms = int((time.time() - t0) * 1000)
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "text": choice,
        "tokens_input": usage.get("prompt_tokens", 0),
        "tokens_output": usage.get("completion_tokens", 0),
        "latency_ms": latency_ms,
    }


# ── Runner endpoint ──────────────────────────────────────────────────────────

@router.post("/runner", status_code=201, response_model=RunnerResponse)
def run_workflow_nocode(body: RunnerBody, _auth=Depends(ui_write_auth)):
    import concurrent.futures as _cf

    # Resolve credentials per branch (or shared fallback)
    key_a, url_a = _resolve_credentials(body.branch_a.provider_id)
    key_b, url_b = _resolve_credentials(body.branch_b.provider_id)

    if not body.test_cases:
        raise HTTPException(400, "test_cases must not be empty")

    wf = db.upsert_workflow(body.workflow_name)
    er = db.create_eval_run(
        workflow_id=wf.id, name=body.eval_run_name,
        description=f"No-code runner: {body.branch_a.model_id} vs {body.branch_b.model_id}",
        branch_a_config={"name": body.branch_a.name, "model_id": body.branch_a.model_id,
                         **({"provider_id": body.branch_a.provider_id} if body.branch_a.provider_id else {})},
        branch_b_config={"name": body.branch_b.name, "model_id": body.branch_b.model_id,
                         **({"provider_id": body.branch_b.provider_id} if body.branch_b.provider_id else {})},
    )

    errors: list[str] = []

    for tc in body.test_cases:
        run = db.create_run(
            workflow_id=wf.id,
            input_data={"input": tc.input, "label": tc.label},
            eval_run_id=er.id, test_case_label=tc.label,
        )
        branch_a_obj = db.create_branch(run.id, wf.id, body.branch_a.name, body.branch_a.model_id)
        branch_b_obj = db.create_branch(run.id, wf.id, body.branch_b.name, body.branch_b.model_id)

        def _run_branch(branch_cfg, branch_obj, b_key, b_url):
            context_messages: list[dict] = []
            for idx, step in enumerate(branch_cfg.steps):
                user_content = step.user_prompt_template.replace("{{input}}", tc.input)
                messages = (
                    [{"role": "system", "content": step.system_prompt}] if step.system_prompt else []
                ) + context_messages + [{"role": "user", "content": user_content}]
                try:
                    result = _call_llm(b_key, b_url, branch_cfg.model_id, branch_cfg.temperature, messages)
                    db.save_step_output(
                        run_id=run.id, branch_id=branch_obj.id,
                        step_name=step.name, step_index=idx,
                        input_messages=messages, output_text=result["text"],
                        model_id=branch_cfg.model_id, temperature=branch_cfg.temperature,
                        tokens_input=result["tokens_input"], tokens_output=result["tokens_output"],
                        latency_ms=result["latency_ms"],
                    )
                    context_messages.append({"role": "assistant", "content": result["text"]})
                except Exception as exc:
                    errors.append(f"[{tc.label}/{branch_cfg.name}/{step.name}] {exc}")

        with _cf.ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(_run_branch, body.branch_a, branch_a_obj, key_a, url_a)
            fb = pool.submit(_run_branch, body.branch_b, branch_b_obj, key_b, url_b)
            fa.result()
            fb.result()

        step_names = [s.name for s in body.branch_a.steps]
        comp = db.create_comparison(
            run_id=run.id, workflow_id=wf.id,
            branch_a_id=branch_a_obj.id, branch_b_id=branch_b_obj.id,
            step_names=step_names, eval_run_id=er.id,
            test_case_label=tc.label, scoring_status="pending",
        )
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(async_enqueue_scoring(db, comp.id, branch_a_obj.id, branch_b_obj.id, []))
        except RuntimeError:
            from core.comparator import divergence_score as _div_score
            steps_a = db.get_step_outputs_for_branch(branch_a_obj.id)
            steps_b = db.get_step_outputs_for_branch(branch_b_obj.id)
            text_a = " ".join(s.output_text for s in steps_a)
            text_b = " ".join(s.output_text for s in steps_b)
            div = _div_score(text_a, text_b) if (text_a or text_b) else None
            db.update_comparison_scoring(comp.id, divergence_score=div, scoring_status="completed")
        db.complete_run(run.id)

    db.update_eval_run_status(er.id, EvalRunStatus.COMPLETED, total_cases=len(body.test_cases))
    return {"eval_run_id": er.id, "errors": errors}


# ── Playground endpoint ──────────────────────────────────────────────────────

@router.post("/playground")
async def playground_run(body: PlaygroundRequest, background: BackgroundTasks,
                         _auth=Depends(ui_write_auth)):
    import httpx

    # Resolve credentials per model
    key_a, url_a = _resolve_credentials(body.provider_id_a)
    key_b, url_b = _resolve_credentials(body.provider_id_b)

    messages = []
    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})
    messages.append({"role": "user", "content": body.prompt})

    wf = db.upsert_workflow("Playground", description="Interactive prompt playground")

    async def _call_model(model: str, m_key: str, m_url: str):
        t0 = time.time()
        url = (m_url.rstrip("/") if m_url else "https://api.openai.com/v1") + "/chat/completions"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {m_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages,
                      "temperature": body.temperature, "max_tokens": body.max_tokens},
            )
            resp.raise_for_status()
            data = resp.json()
        latency_ms = int((time.time() - t0) * 1000)
        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})
        return {
            "output_text": choice.get("message", {}).get("content", ""),
            "model_id": model,
            "latency_ms": latency_ms,
            "tokens_input": usage.get("prompt_tokens", 0),
            "tokens_output": usage.get("completion_tokens", 0),
            "finish_reason": choice.get("finish_reason", ""),
        }

    try:
        import asyncio
        result_a, result_b = await asyncio.gather(
            _call_model(body.model_a, key_a, url_a),
            _call_model(body.model_b, key_b, url_b),
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Model API error: {e.response.status_code} — {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {str(e)[:200]}")

    run = db.create_run(
        workflow_id=wf.id,
        input_data={"prompt": body.prompt, "system_prompt": body.system_prompt},
        metadata={"source": "playground"},
    )
    branch_a = db.create_branch(run_id=run.id, workflow_id=wf.id, name="Branch A", model_id=body.model_a, temperature=body.temperature)
    branch_b = db.create_branch(run_id=run.id, workflow_id=wf.id, name="Branch B", model_id=body.model_b, temperature=body.temperature)

    db.save_step_output(run_id=run.id, branch_id=branch_a.id, step_name="answer", step_index=0,
                        input_messages=messages, output_text=result_a["output_text"],
                        model_id=body.model_a, temperature=body.temperature,
                        tokens_input=result_a["tokens_input"], tokens_output=result_a["tokens_output"],
                        latency_ms=result_a["latency_ms"])
    db.save_step_output(run_id=run.id, branch_id=branch_b.id, step_name="answer", step_index=0,
                        input_messages=messages, output_text=result_b["output_text"],
                        model_id=body.model_b, temperature=body.temperature,
                        tokens_input=result_b["tokens_input"], tokens_output=result_b["tokens_output"],
                        latency_ms=result_b["latency_ms"])

    db.complete_run(run.id)
    div_score = divergence_score(result_a["output_text"], result_b["output_text"])
    summary = summarize_divergence(result_a["output_text"], result_b["output_text"], div_score)

    comp = db.create_comparison(run_id=run.id, workflow_id=wf.id,
                                branch_a_id=branch_a.id, branch_b_id=branch_b.id,
                                step_names=["answer"], scoring_status="completed")
    db.update_comparison_scoring(comp.id, divergence_score=div_score, scoring_status="completed")

    return {
        "comparison_id": comp.id, "run_id": run.id,
        "model_a": result_a, "model_b": result_b,
        "divergence_score": div_score, "divergence_summary": summary,
    }
