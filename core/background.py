"""Forkmark background task queue — async divergence scoring & evaluation.

Decouples slow scoring (semantic embeddings, OpenAI API calls, LLM-as-judge)
from the SDK ingestion hot path. Comparisons are inserted with
scoring_status='pending' and scored asynchronously by the FastAPI event loop.

Architecture:
    - FastAPI BackgroundTasks runs tasks concurrently.
    - An asyncio.Semaphore limits concurrency (FM_BACKGROUND_WORKERS).
    - Failed tasks set scoring_status='failed' so the UI can flag them.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Any

if TYPE_CHECKING:
    from .store import Database

from config import config as _cfg
from .comparator import divergence_score
from .evaluators import run_evaluators, run_pairwise_evaluators

logger = logging.getLogger("forkmark.background")

_MAX_WORKERS = _cfg.BACKGROUND_WORKERS
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-init the global semaphore inside the active event loop."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_WORKERS)
    return _semaphore


async def async_enqueue_scoring(
    db: "Database",
    comp_id: str,
    branch_a_id: str,
    branch_b_id: str,
    evaluator_configs: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Async wrapper to limit concurrency using a semaphore."""
    sem = _get_semaphore()
    async with sem:
        await _score_comparison_async(db, comp_id, branch_a_id, branch_b_id, evaluator_configs or [])


async def _score_comparison_async(
    db: "Database",
    comp_id: str,
    branch_a_id: str,
    branch_b_id: str,
    evaluator_configs: List[Dict[str, Any]],
) -> None:
    """Worker function — runs in the FastAPI async event loop."""
    try:
        # Mark as running
        await asyncio.to_thread(db.update_comparison_scoring, comp_id, scoring_status="running")

        # Fetch step outputs
        all_steps = await asyncio.to_thread(db.get_step_outputs_for_branches, branch_a_id, branch_b_id)
        steps_a = [s for s in all_steps if s.branch_id == branch_a_id]
        steps_b = [s for s in all_steps if s.branch_id == branch_b_id]

        # Per-step divergence
        steps_a_map = {s.step_name: s for s in steps_a}
        steps_b_map = {s.step_name: s for s in steps_b}
        shared_steps = set(steps_a_map.keys()) & set(steps_b_map.keys())

        step_divs: Dict[str, float] = {}
        # Parallelize per-step divergence scoring
        async def _score_step(sname: str):
            sa = steps_a_map[sname]
            sb = steps_b_map[sname]
            if sa.output_text or sb.output_text:
                return sname, await asyncio.to_thread(divergence_score, sa.output_text, sb.output_text)
            return sname, None

        div_results = await asyncio.gather(*[_score_step(n) for n in shared_steps])
        for sname, div in div_results:
            if div is not None:
                step_divs[sname] = div

        # Overall divergence
        if step_divs:
            overall_div = round(sum(step_divs.values()) / len(step_divs), 4)
        elif steps_a or steps_b:
            text_a = " ".join(s.output_text for s in steps_a)
            text_b = " ".join(s.output_text for s in steps_b)
            overall_div = await asyncio.to_thread(divergence_score, text_a, text_b) if (text_a or text_b) else None
        else:
            overall_div = None

        # Run standard + pairwise evaluators in parallel
        eval_results: Dict[str, List[Dict]] = {}
        if evaluator_configs:
            # Standard evaluators — one task per step output
            async def _run_std(step):
                context = {
                    "input_messages": step.input_messages,
                    "model_id":       step.model_id,
                    "latency_ms":     step.latency_ms,
                    "branch_id":      step.branch_id,
                    "step_index":     step.step_index,
                }
                results = await run_evaluators(step.output_text, evaluator_configs, context)
                return f"{step.branch_id}:{step.step_name}", [r.to_dict() for r in results]

            # Pairwise evaluators — one task per shared step
            async def _run_pw(sname):
                sa = steps_a_map[sname]
                sb = steps_b_map[sname]
                pairwise_context = {
                    "input_messages": sa.input_messages,
                    "model_id_a":     sa.model_id,
                    "model_id_b":     sb.model_id,
                    "step_name":      sname,
                }
                pw_results = await run_pairwise_evaluators(
                    sa.output_text, sb.output_text, evaluator_configs, pairwise_context,
                )
                if pw_results:
                    return f"pairwise:{sname}", [r.to_dict() for r in pw_results]
                return None, None

            all_tasks = [_run_std(s) for s in steps_a + steps_b] + \
                        [_run_pw(n) for n in shared_steps]
            all_results = await asyncio.gather(*all_tasks)
            for key, val in all_results:
                if key is not None and val is not None:
                    eval_results[key] = val

        # Update the comparison row
        await asyncio.to_thread(
            db.update_comparison_scoring,
            comp_id,
            divergence_score=overall_div,
            step_divergence_scores=step_divs,
            eval_results=eval_results,
            scoring_status="completed",
        )
        logger.debug(f"Scored comparison {comp_id}: divergence={overall_div}")

    except Exception as e:
        logger.error(f"Background scoring failed for {comp_id}: {e}")
        try:
            await asyncio.to_thread(db.update_comparison_scoring, comp_id, scoring_status="failed")
        except Exception:
            pass  # best-effort status update

