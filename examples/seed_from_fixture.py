"""
Forkmark Demo Seeder — Fixture-Based
======================================

Seeds any demo by loading its fixtures.json file and calling the
Forkmark REST API to create workflows, eval runs, branches, steps,
and comparisons.

Usage:
    python seed_from_fixture.py <fixtures_dir_or_json_path>

    # Examples:
    python seed_from_fixture.py retail_demo
    python seed_from_fixture.py retail_demo/fixtures.json
    python seed_from_fixture.py .   (seeds from ./fixtures.json)

Environment:
    FORKMARK_API_KEY   – API key for auth (auto-bootstraps if empty)
    FM_URL              – Backend URL (default: http://localhost:7700)

Requirements:   pip install httpx
"""

import httpx
import json
import re
import time
import sys
import os
from pathlib import Path
from difflib import SequenceMatcher

BASE_URL = os.environ.get("FM_URL", "http://localhost:7700")
_api_key = os.environ.get("FORKMARK_API_KEY", "")
HEADERS = {"Content-Type": "application/json"}
if _api_key:
    HEADERS["X-API-Key"] = _api_key


def api(method, path, data=None, _retries=4, _backoff=1.0):
    url = BASE_URL + path
    for attempt in range(_retries):
        try:
            r = getattr(httpx, method)(url, json=data, headers=HEADERS, timeout=10)
            if r.status_code == 429:
                wait = _backoff * (2 ** attempt)
                print(f"  [rate-limit] backing off {wait:.1f}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            print(f"\n[error] Cannot connect to {BASE_URL}")
            print("  Make sure the Forkmark backend is running:")
            print("  cd forkmark && uvicorn backend.main:app --reload\n")
            sys.exit(1)
        except Exception as e:
            print(f"[error] {method.upper()} {path}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  Response: {e.response.text[:200]}")
            return None
    print(f"[error] {method.upper()} {path}: rate limit retries exhausted")
    return None


def check_backend():
    """Verify backend is reachable and bootstrap API key if needed."""
    global _api_key
    try:
        r = httpx.get(BASE_URL + "/api/stats", timeout=5)
        r.raise_for_status()
    except Exception:
        print(f"[error] Cannot reach {BASE_URL}/api/stats")
        sys.exit(1)
    if not _api_key:
        try:
            kr = httpx.post(
                BASE_URL + "/api/keys",
                json={"name": "demo-seeder"},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            kr.raise_for_status()
            _api_key = kr.json().get("raw_key", "")
            if _api_key:
                HEADERS["X-API-Key"] = _api_key
                print(f"  [auth] Bootstrapped API key: {_api_key[:12]}...")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("[error] API keys exist. Set FORKMARK_API_KEY env var.")
                sys.exit(1)


def divergence(a: str, b: str) -> float:
    """Fast lexical divergence score between two texts."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    j = 1 - len(wa & wb) / (len(wa | wb) or 1)
    s = 1 - SequenceMatcher(None, a, b).ratio()
    return round(j * 0.6 + s * 0.4, 4)


def seed_fixture(fixture_path: str):
    """Seed a single demo from its fixture file."""
    with open(fixture_path) as f:
        fixture = json.load(f)

    demo_name = fixture["demo_name"]
    wf_cfg = fixture["workflow"]
    er_cfg = fixture["eval_run"]
    ba_cfg = fixture["branch_a"]
    bb_cfg = fixture["branch_b"]
    steps = fixture["steps"]
    sfm = fixture["step_field_map"]
    inp_field = fixture["input_field"]
    cases = fixture["cases"]

    print(f"\n{'━' * 60}")
    print(f"  {fixture.get('display_name', demo_name)}")
    print(f"  {len(cases)} cases × {len(steps)} steps")
    print(f"  {ba_cfg.get('label', ba_cfg['name'])} vs {bb_cfg.get('label', bb_cfg['name'])}")
    print(f"{'━' * 60}\n")

    # 1. Create workflow
    print("  [1/4] Creating workflow...")
    wf = api("post", "/api/sdk/workflows", {
        "name": wf_cfg["name"],
        "description": wf_cfg.get("description", ""),
    })
    if not wf:
        print("[error] Failed to create workflow")
        return False
    wf_id = wf["id"]
    print(f"    → {wf_cfg['name']} ({wf_id[:8]})")

    # 2. Create eval run
    print("  [2/4] Creating eval run...")
    er = api("post", "/api/sdk/eval-runs", {
        "workflow_id": wf_id,
        "name": er_cfg["name"],
        "description": er_cfg.get("description", ""),
        "branch_a_config": {k: v for k, v in ba_cfg.items() if k != "is_baseline"},
        "branch_b_config": {k: v for k, v in bb_cfg.items() if k != "is_baseline"},
        "total_cases": len(cases),
    })
    if not er:
        print("[error] Failed to create eval run")
        return False
    er_id = er["id"]
    print(f"    → {er_cfg['name'][:50]} ({er_id[:8]})")

    # 3. Seed cases
    print(f"  [3/4] Seeding {len(cases)} cases...")
    comparisons = 0
    for ci, case in enumerate(cases):
        input_data = case.get(inp_field, "")
        if isinstance(input_data, dict):
            input_text = str(input_data)
        else:
            input_text = str(input_data)

        # Build input data (all fields except step outputs and label)
        step_fields = set()
        for fa, fb in sfm.values():
            step_fields.add(fa)
            step_fields.add(fb)
        run_input = {k: v for k, v in case.items() if k not in step_fields and k != "label"}

        # Create run
        run = api("post", "/api/sdk/runs", {
            "workflow_id": wf_id,
            "input_data": run_input,
            "metadata": {"source": "demo", "demo_name": demo_name},
            "eval_run_id": er_id,
            "test_case_label": case["label"],
        })
        if not run:
            continue
        run_id = run["id"]

        # Create branches
        ba = api("post", "/api/sdk/branches", {
            "run_id": run_id,
            "workflow_id": wf_id,
            "name": ba_cfg["name"],
            "model_id": ba_cfg["model_id"],
            "temperature": ba_cfg.get("temperature", 0.7),
            "is_baseline": ba_cfg.get("is_baseline", True),
        })
        bb = api("post", "/api/sdk/branches", {
            "run_id": run_id,
            "workflow_id": wf_id,
            "name": bb_cfg["name"],
            "model_id": bb_cfg["model_id"],
            "temperature": bb_cfg.get("temperature", 0.7),
            "is_baseline": bb_cfg.get("is_baseline", False),
        })
        if not ba or not bb:
            continue

        # Log steps
        user_msg = [{"role": "user", "content": input_text}]
        for idx, step_name in enumerate(steps):
            field_a, field_b = sfm[step_name]
            out_a = case.get(field_a, "")
            out_b = case.get(field_b, "")

            api("post", "/api/sdk/steps", {
                "run_id": run_id,
                "branch_id": ba["id"],
                "step_name": step_name,
                "step_index": idx,
                "input_messages": user_msg,
                "output_text": out_a,
                "model_id": ba_cfg["model_id"],
                "temperature": ba_cfg.get("temperature", 0.7),
                "tokens_input": 120 + len(input_text) // 4,
                "tokens_output": len(out_a.split()),
                "latency_ms": 180 + idx * 40,
            })
            api("post", "/api/sdk/steps", {
                "run_id": run_id,
                "branch_id": bb["id"],
                "step_name": step_name,
                "step_index": idx,
                "input_messages": user_msg,
                "output_text": out_b,
                "model_id": bb_cfg["model_id"],
                "temperature": bb_cfg.get("temperature", 0.7),
                "tokens_input": 120 + len(input_text) // 4,
                "tokens_output": len(out_b.split()),
                "latency_ms": 340 + idx * 60,
            })

        # Complete run
        api("post", f"/api/sdk/runs/{run_id}/complete", {"status": "completed"})

        # Create comparison
        all_a = " ".join(case.get(sfm[s][0], "") for s in steps)
        all_b = " ".join(case.get(sfm[s][1], "") for s in steps)
        div = divergence(all_a, all_b)

        api("post", "/api/sdk/comparisons", {
            "run_id": run_id,
            "branch_a_id": ba["id"],
            "branch_b_id": bb["id"],
            "eval_run_id": er_id,
            "test_case_label": case["label"],
        })
        comparisons += 1

        # Progress
        bar = "█" * ((ci + 1) * 30 // len(cases)) + "░" * (30 - (ci + 1) * 30 // len(cases))
        print(f"\r    [{bar}] {ci+1}/{len(cases)}  {case['label'][:30]:<30}", end="", flush=True)

    print()

    # 4. Complete eval run
    print("  [4/4] Completing eval run...")
    api("post", f"/api/sdk/eval-runs/{er_id}/complete", {"total_cases": len(cases)})

    print(f"\n  ✓ Done: {comparisons} comparisons created")
    print(f"    Workflow:  {wf_id}")
    print(f"    Eval Run:  {er_id}")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path_arg = sys.argv[1]
    fixture_path = Path(path_arg)

    # Resolve fixture path
    if fixture_path.is_dir():
        fixture_path = fixture_path / "fixtures.json"
    elif not fixture_path.exists():
        # Try relative to examples/
        examples_dir = Path(__file__).parent
        fixture_path = examples_dir / path_arg / "fixtures.json"

    if not fixture_path.exists():
        print(f"[error] Fixture not found: {fixture_path}")
        sys.exit(1)

    print(f"[setup] Loading fixture: {fixture_path}")
    check_backend()
    ok = seed_fixture(str(fixture_path))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
