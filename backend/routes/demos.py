"""Demo seeding endpoints."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.deps import db, ui_read_auth, ui_write_auth, stats_local_cache
from config import config
from core.models import RunStatus, DecisionChoice, ConfidenceLevel, EvalRunStatus
from core.comparator import divergence_score as _div_score, summarize_divergence


def _agent_feature_enabled() -> bool:
    """Check if agent comparison feature is enabled."""
    return getattr(config, "ENABLE_AGENT_COMPARISON", False)

router = APIRouter(prefix="/api", tags=["demos"])


class DemoSeedBody(BaseModel):
    demos: List[str] = Field(default=[], description="Demo names to seed (empty = all)")

class DemoResetBody(BaseModel):
    demos: List[str] = Field(default=[], description="Demo names to reset (empty = all)")


def _discover_demo_fixtures() -> Dict[str, dict]:
    import glob as _glob
    fixtures = {}
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    for fpath in sorted(_glob.glob(str(examples_dir / "*/fixtures.json"))):
        try:
            with open(fpath) as f:
                fixture = json.load(f)
            name = fixture.get("demo_name", Path(fpath).parent.name.replace("_demo", ""))
            fixture["_fixture_path"] = fpath
            fixtures[name] = fixture
        except Exception:
            continue
    return fixtures


def _discover_agent_fixtures() -> Dict[str, dict]:
    """Discover agent demo fixtures from examples/*/agent_fixtures.json."""
    import glob as _glob
    fixtures = {}
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    for fpath in sorted(_glob.glob(str(examples_dir / "*/agent_fixtures.json"))):
        try:
            with open(fpath) as f:
                fixture = json.load(f)
            name = fixture.get("demo_name", Path(fpath).parent.name.replace("_demo", ""))
            fixture["_fixture_path"] = fpath
            fixture["demo_type"] = "agent"
            fixtures[name] = fixture
        except Exception:
            continue
    return fixtures


def _flatten_trace_tree(
    nodes: list,
    branch_id: str,
    run_id: str,
    parent_event_id: str = None,
    base_index: int = 0,
) -> List[dict]:
    """Recursively flatten a trace event tree (with 'children' arrays) into flat records.

    Each node in *nodes* may have a 'children' key containing nested events.
    Returns a flat list of dicts ready for db.create_trace_events_batch().
    """
    flat: List[dict] = []
    idx = base_index
    for node in nodes:
        event_id = f"te_{uuid.uuid4().hex[:12]}"
        children = node.pop("children", [])
        ev = {
            "id": event_id,
            "branch_id": branch_id,
            "run_id": run_id,
            "parent_event_id": parent_event_id,
            "event_type": node.get("event_type", "tool_call"),
            "event_index": idx,
            "name": node.get("name", ""),
            "input_data": node.get("input_data", {}),
            "output_data": node.get("output_data", {}),
            "status": node.get("status", "completed"),
            "latency_ms": node.get("latency_ms", 0),
            "tokens_input": node.get("tokens_input", 0),
            "tokens_output": node.get("tokens_output", 0),
            "cost_usd": node.get("cost_usd", 0.0),
            "metadata": node.get("metadata", {}),
        }
        flat.append(ev)
        idx += 1
        if children:
            child_flat = _flatten_trace_tree(children, branch_id, run_id, event_id, idx)
            flat.extend(child_flat)
            idx += len(child_flat)
    return flat


def _seed_one_agent_demo(fixture: dict, api_key: str) -> dict:
    """Seed one agent comparison demo — creates workflow, runs, branches,
    trace events, comparisons, and trajectory outcomes."""
    from core.trajectory_comparator import compare_trajectories
    from core.agent_models import TraceEvent

    demo_name = fixture["demo_name"]
    cases = fixture["cases"]

    wf = db.upsert_workflow(
        fixture["workflow"]["name"],
        fixture["workflow"].get("description", ""),
    )
    er = db.create_eval_run(
        workflow_id=wf.id,
        name=fixture["eval_run"]["name"],
        description=fixture["eval_run"].get("description", ""),
        branch_a_config={k: v for k, v in fixture["branch_a"].items() if k != "is_baseline"},
        branch_b_config={k: v for k, v in fixture["branch_b"].items() if k != "is_baseline"},
        total_cases=len(cases),
    )
    db.update_eval_run_status(er.id, EvalRunStatus.RUNNING)

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12] if api_key else "demo"
    comparisons_created = 0
    trace_events_created = 0

    for case in cases:
        input_text = case.get("input", "")
        run_input = {"input": input_text}
        if "label" in case:
            run_input["label"] = case["label"]

        # Create run with run_type "agent"
        run = db.create_run(
            workflow_id=wf.id, input_data=run_input,
            metadata={"source": "demo", "demo_name": demo_name, "run_type": "agent"},
            sdk_key_prefix=key_hash, eval_run_id=er.id,
            test_case_label=case.get("label", ""),
        )
        # Mark run_type on the runs table
        try:
            with db._conn() as c:
                c.execute("UPDATE workflow_runs SET run_type = 'agent' WHERE id = ?", (run.id,))
        except Exception:
            pass

        ba_cfg = fixture["branch_a"]
        bb_cfg = fixture["branch_b"]
        ba = db.create_branch(
            run_id=run.id, workflow_id=wf.id,
            name=ba_cfg["name"], model_id=ba_cfg["model_id"],
            temperature=ba_cfg.get("temperature", 0.7),
            is_baseline=ba_cfg.get("is_baseline", True),
        )
        bb = db.create_branch(
            run_id=run.id, workflow_id=wf.id,
            name=bb_cfg["name"], model_id=bb_cfg["model_id"],
            temperature=bb_cfg.get("temperature", 0.7),
            is_baseline=bb_cfg.get("is_baseline", False),
        )

        # Deep-copy trace trees so pop("children") doesn't mutate fixture in memory
        import copy
        trace_a_tree = copy.deepcopy(case.get("trace_a", []))
        trace_b_tree = copy.deepcopy(case.get("trace_b", []))

        # Flatten and insert trace events
        flat_a = _flatten_trace_tree(trace_a_tree, ba.id, run.id)
        flat_b = _flatten_trace_tree(trace_b_tree, bb.id, run.id)

        if flat_a:
            db.create_trace_events_batch(flat_a)
            trace_events_created += len(flat_a)
        if flat_b:
            db.create_trace_events_batch(flat_b)
            trace_events_created += len(flat_b)

        db.complete_run(run.id, RunStatus.COMPLETED)

        # Run trajectory comparison
        events_a = db.get_trace_events(branch_id=ba.id)
        events_b = db.get_trace_events(branch_id=bb.id)
        traj_result = compare_trajectories(events_a, events_b)

        # Create comparison record
        step_names = list({e.name for e in events_a} | {e.name for e in events_b})
        comp = db.create_comparison(
            run_id=run.id, workflow_id=wf.id,
            branch_a_id=ba.id, branch_b_id=bb.id,
            step_names=step_names,
            eval_run_id=er.id, test_case_label=case.get("label", ""),
            divergence_score=1.0 - traj_result["trajectory_score"],
            scoring_status="completed",
        )

        # Store trajectory outcome
        outcome_id = f"to_{uuid.uuid4().hex[:12]}"
        db.create_trajectory_outcome(
            id=outcome_id,
            comparison_id=comp.id,
            run_id=run.id,
            workflow_id=wf.id,
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
        comparisons_created += 1

    db.update_eval_run_status(er.id, EvalRunStatus.COMPLETED, total_cases=len(cases))

    return {
        "demo": demo_name, "demo_type": "agent",
        "workflow_id": wf.id, "eval_run_id": er.id,
        "cases": len(cases), "comparisons": comparisons_created,
        "trace_events": trace_events_created,
    }


def _seed_one_demo(fixture: dict, api_key: str) -> dict:
    wf_name = fixture["workflow"]["name"]
    demo_name = fixture["demo_name"]
    sfm = fixture["step_field_map"]
    inp_field = fixture["input_field"]
    steps = fixture["steps"]
    cases = fixture["cases"]

    wf = db.upsert_workflow(wf_name, fixture["workflow"].get("description", ""))
    er = db.create_eval_run(
        workflow_id=wf.id, name=fixture["eval_run"]["name"],
        description=fixture["eval_run"].get("description", ""),
        branch_a_config={k: v for k, v in fixture["branch_a"].items() if k != "is_baseline"},
        branch_b_config={k: v for k, v in fixture["branch_b"].items() if k != "is_baseline"},
        total_cases=len(cases),
    )
    db.update_eval_run_status(er.id, EvalRunStatus.RUNNING)

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12] if api_key else "demo"
    comparisons_created = 0

    for case in cases:
        input_data = case.get(inp_field, "")
        input_text = str(input_data)

        step_fields = set()
        for fa, fb in sfm.values():
            step_fields.add(fa)
            step_fields.add(fb)
        run_input = {k: v for k, v in case.items() if k not in step_fields and k != "label"}

        run = db.create_run(
            workflow_id=wf.id, input_data=run_input,
            metadata={"source": "demo", "demo_name": demo_name},
            sdk_key_prefix=key_hash, eval_run_id=er.id,
            test_case_label=case["label"],
        )

        ba_cfg = fixture["branch_a"]
        bb_cfg = fixture["branch_b"]
        ba = db.create_branch(run_id=run.id, workflow_id=wf.id,
                              name=ba_cfg["name"], model_id=ba_cfg["model_id"],
                              temperature=ba_cfg.get("temperature", 0.7),
                              is_baseline=ba_cfg.get("is_baseline", True))
        bb = db.create_branch(run_id=run.id, workflow_id=wf.id,
                              name=bb_cfg["name"], model_id=bb_cfg["model_id"],
                              temperature=bb_cfg.get("temperature", 0.7),
                              is_baseline=bb_cfg.get("is_baseline", False))

        user_msg = [{"role": "user", "content": input_text}]
        for idx, step_name in enumerate(steps):
            field_a, field_b = sfm[step_name]
            out_a = case.get(field_a, "")
            out_b = case.get(field_b, "")
            db.save_step_output(run_id=run.id, branch_id=ba.id, step_name=step_name, step_index=idx,
                                input_messages=user_msg, output_text=out_a, model_id=ba_cfg["model_id"],
                                temperature=ba_cfg.get("temperature", 0.7),
                                tokens_input=120 + len(input_text) // 4, tokens_output=len(out_a.split()),
                                latency_ms=180 + idx * 40)
            db.save_step_output(run_id=run.id, branch_id=bb.id, step_name=step_name, step_index=idx,
                                input_messages=user_msg, output_text=out_b, model_id=bb_cfg["model_id"],
                                temperature=bb_cfg.get("temperature", 0.7),
                                tokens_input=120 + len(input_text) // 4, tokens_output=len(out_b.split()),
                                latency_ms=340 + idx * 60)

        db.complete_run(run.id, RunStatus.COMPLETED)
        comp = db.create_comparison(run_id=run.id, workflow_id=wf.id,
                                    branch_a_id=ba.id, branch_b_id=bb.id,
                                    eval_run_id=er.id, test_case_label=case["label"],
                                    scoring_status="completed")

        steps_a = db.get_step_outputs_for_branch(ba.id)
        steps_b = db.get_step_outputs_for_branch(bb.id)
        text_a = " ".join(s.output_text for s in steps_a)
        text_b = " ".join(s.output_text for s in steps_b)
        div = _div_score(text_a, text_b)
        db.update_comparison_scoring(comp.id, divergence_score=div, scoring_status="completed")
        comparisons_created += 1

    db.update_eval_run_status(er.id, EvalRunStatus.COMPLETED, total_cases=len(cases))

    # Lifecycle features
    decisions_created = 0
    comments_created = 0
    reviewers_created = 0
    test_set_id = None
    assignments_created = 0

    if fixture.get("lifecycle_demo"):
        all_comps = db.list_comparisons(eval_run_id=er.id, limit=1000)
        comp_by_label = {c.test_case_label: c for c in all_comps}
        comp_by_index = [comp_by_label.get(case["label"]) for case in cases]

        for rev in fixture.get("reviewers", []):
            db.upsert_reviewer_profile(rev["id"], display_name=rev.get("display_name", ""),
                                       role=rev.get("role", "reviewer"),
                                       expertise_level=rev.get("expertise_level", "intermediate"),
                                       domain_expertise=rev.get("domain_expertise", []))
            reviewers_created += 1

        ts_cfg = fixture.get("test_set")
        if ts_cfg:
            ts = db.create_test_set(name=ts_cfg["name"], description=ts_cfg.get("description", ""), workflow_id=wf.id)
            test_set_id = ts.id
            for case in cases:
                inp = case.get(fixture["input_field"], "")
                db.add_test_case(test_set_id=ts.id, label=case["label"],
                                 input_data={fixture["input_field"]: inp,
                                             "category": case.get("category", ""),
                                             "priority": case.get("priority", "")},
                                 tags=[case.get("category", ""), case.get("priority", "")])

        for dec in fixture.get("decisions", []):
            idx = dec["case_index"]
            comp = comp_by_index[idx] if idx < len(comp_by_index) else None
            if not comp:
                continue
            try:
                choice = DecisionChoice(dec["choice"])
                conf = ConfidenceLevel(dec["confidence"])
            except ValueError:
                continue
            div = comp.divergence_score or 0.0
            div_sum = summarize_divergence("", "", div)
            winner_id = comp.branch_a_id if choice == DecisionChoice.BRANCH_A else (
                        comp.branch_b_id if choice == DecisionChoice.BRANCH_B else None)
            loser_id = comp.branch_b_id if choice == DecisionChoice.BRANCH_A else (
                       comp.branch_a_id if choice == DecisionChoice.BRANCH_B else None)
            db.create_decision(
                comparison_id=comp.id, run_id=comp.run_id, workflow_id=wf.id,
                reviewer_id=dec["reviewer_id"], choice=choice, confidence=conf,
                rationale_for_choice=dec["rationale_for_choice"],
                rationale_for_rejection=dec.get("rationale_for_rejection", ""),
                tags=dec.get("tags", []), branch_winner_id=winner_id, branch_loser_id=loser_id,
                divergence_score=div, divergence_summary=div_sum, eval_run_id=er.id)
            decisions_created += 1

        comment_ids_by_case = {}
        for ci, cmt in enumerate(fixture.get("comments", [])):
            idx = cmt["case_index"]
            comp = comp_by_index[idx] if idx < len(comp_by_index) else None
            if not comp:
                continue
            parent_id = comment_ids_by_case.get((idx, cmt["parent_index"])) if "parent_index" in cmt else None
            result = db.add_comment(comparison_id=comp.id, author_id=cmt["author_id"], body=cmt["body"],
                                    author_name=cmt.get("author_name", ""), parent_id=parent_id)
            if result:
                comment_ids_by_case[(idx, ci)] = result["id"]
                comments_created += 1

        reviewer_ids = [r["id"] for r in fixture.get("reviewers", [])]
        if reviewer_ids:
            undecided = [c for c in all_comps if not c.decided]
            for i, comp in enumerate(undecided):
                rid = reviewer_ids[i % len(reviewer_ids)]
                try:
                    db.assign_review(eval_run_id=er.id, comparison_id=comp.id,
                                     reviewer_id=rid, assigned_by="demo-seeder")
                    assignments_created += 1
                except Exception:
                    pass

    return {
        "demo": demo_name, "workflow_id": wf.id, "eval_run_id": er.id,
        "cases": len(cases), "comparisons": comparisons_created,
        "decisions": decisions_created, "comments": comments_created,
        "reviewers": reviewers_created, "test_set_id": test_set_id,
        "assignments": assignments_created,
    }


def _clear_demo_data(demo_name: str):
    workflows = db.list_workflows()
    fixtures = _discover_demo_fixtures()
    if demo_name not in fixtures:
        return
    wf_name = fixtures[demo_name]["workflow"]["name"]
    for wf in workflows:
        if wf.name == wf_name:
            ers = db.list_eval_runs(wf.id)
            for er in ers:
                try:
                    db.delete_eval_run(er.id)
                except Exception:
                    pass
            try:
                db.delete_workflow(wf.id)
            except Exception:
                pass


def _clear_agent_demo_data(demo_name: str):
    """Clear agent demo data — deletes workflow, runs, trace events, trajectory outcomes."""
    workflows = db.list_workflows()
    fixtures = _discover_agent_fixtures()
    if demo_name not in fixtures:
        return
    wf_name = fixtures[demo_name]["workflow"]["name"]
    for wf in workflows:
        if wf.name == wf_name:
            # Delete trace events and trajectory outcomes for all runs in this workflow
            try:
                with db._conn() as c:
                    c.execute("""DELETE FROM trace_events WHERE run_id IN
                                 (SELECT id FROM workflow_runs WHERE workflow_id = ?)""", (wf.id,))
                    c.execute("""DELETE FROM trajectory_outcomes WHERE workflow_id = ?""", (wf.id,))
            except Exception:
                pass
            ers = db.list_eval_runs(wf.id)
            for er in ers:
                try:
                    db.delete_eval_run(er.id)
                except Exception:
                    pass
            try:
                db.delete_workflow(wf.id)
            except Exception:
                pass


@router.get("/demos")
def list_demos(_auth=Depends(ui_read_auth)):
    fixtures = _discover_demo_fixtures()
    result = [
        {"name": name, "display_name": f.get("display_name", name),
         "demo_type": "llm",
         "workflow_name": f["workflow"]["name"], "eval_run_name": f["eval_run"]["name"],
         "description": f["eval_run"].get("description", ""),
         "cases": len(f["cases"]), "steps": len(f["steps"]),
         "step_names": f["steps"],
         "branch_a_label": f["branch_a"].get("label", ""),
         "branch_b_label": f["branch_b"].get("label", "")}
        for name, f in fixtures.items()
    ]

    # Agent demos — only included when the feature is enabled
    if not _agent_feature_enabled():
        return result
    agent_fixtures = _discover_agent_fixtures()
    for name, f in agent_fixtures.items():
        # Count total trace events across all cases
        total_events = 0
        for case in f.get("cases", []):
            def _count_nodes(nodes):
                n = 0
                for node in nodes:
                    n += 1
                    n += _count_nodes(node.get("children", []))
                return n
            total_events += _count_nodes(case.get("trace_a", []))
            total_events += _count_nodes(case.get("trace_b", []))
        result.append({
            "name": name,
            "display_name": f.get("display_name", name),
            "demo_type": "agent",
            "workflow_name": f["workflow"]["name"],
            "eval_run_name": f["eval_run"]["name"],
            "description": f["eval_run"].get("description", ""),
            "cases": len(f.get("cases", [])),
            "trace_events": total_events,
            "branch_a_label": f["branch_a"].get("label", ""),
            "branch_b_label": f["branch_b"].get("label", ""),
        })
    return result


@router.post("/demos/seed", status_code=201)
def seed_demos(body: DemoSeedBody, _auth=Depends(ui_write_auth)):
    fixtures = _discover_demo_fixtures()
    agent_enabled = _agent_feature_enabled()
    agent_fixtures = _discover_agent_fixtures() if agent_enabled else {}
    all_fixtures = {**fixtures, **agent_fixtures}
    available = list(all_fixtures.keys())

    if body.demos:
        # Check if any requested demos are agent demos that require the feature flag
        if not agent_enabled:
            all_agent = _discover_agent_fixtures()
            blocked = [d for d in body.demos if d in all_agent]
            if blocked:
                raise HTTPException(
                    403,
                    f"Agent demos {blocked} require FM_ENABLE_AGENT_COMPARISON=true. "
                    f"Available demos: {list(fixtures.keys())}",
                )
        unknown = [d for d in body.demos if d not in all_fixtures]
        if unknown:
            raise HTTPException(400, f"Unknown demos: {unknown}. Available: {available}")
        to_seed = {k: all_fixtures[k] for k in body.demos}
    else:
        to_seed = all_fixtures

    for name, fix in to_seed.items():
        if fix.get("demo_type") == "agent":
            _clear_agent_demo_data(name)
        else:
            _clear_demo_data(name)

    keys = db.list_api_keys(active_only=True)
    api_key = keys[0].key_hash if keys else "demo-seeder"

    results = []
    for name, fixture in to_seed.items():
        try:
            if fixture.get("demo_type") == "agent":
                result = _seed_one_agent_demo(fixture, api_key)
            else:
                result = _seed_one_demo(fixture, api_key)
            results.append(result)
        except Exception as e:
            results.append({"demo": name, "error": str(e)})

    stats_local_cache.clear()
    return {"seeded": len([r for r in results if "error" not in r]),
            "errors": len([r for r in results if "error" in r]), "results": results}


@router.delete("/demos/reset", status_code=200)
def reset_demos(body: DemoResetBody = DemoResetBody(), _auth=Depends(ui_write_auth)):
    fixtures = _discover_demo_fixtures()
    agent_enabled = _agent_feature_enabled()
    agent_fixtures = _discover_agent_fixtures() if agent_enabled else {}
    all_fixtures = {**fixtures, **agent_fixtures}

    if body.demos:
        unknown = [d for d in body.demos if d not in all_fixtures]
        if unknown:
            raise HTTPException(400, f"Unknown demos: {unknown}. Available: {list(all_fixtures.keys())}")
        to_reset = body.demos
    else:
        to_reset = list(all_fixtures.keys())

    cleared = []
    for name in to_reset:
        try:
            if name in agent_fixtures:
                _clear_agent_demo_data(name)
            else:
                _clear_demo_data(name)
            cleared.append(name)
        except Exception as e:
            cleared.append(f"{name} (error: {e})")

    stats_local_cache.clear()
    return {"reset": cleared}
