"""
Forkmark — Customer Support AI Pipeline Simulation
=====================================================

Runs a live A/B model comparison:
  Branch A (Production) : openai/gpt-3.5-turbo
  Branch B (Challenger)  : openai/gpt-4o-mini
  Divergence scorer      : LLM-as-judge via openai/gpt-4o

Prerequisites
-------------
1. Forkmark running:
       Run     : python run.py
       Mac/Lin : docker compose -f docker-compose.simple.yml up --build -d

2. An OpenRouter API key (https://openrouter.ai):
       export OPENROUTER_API_KEY=sk-or-v1-...

3. Python deps:
       pip install httpx

Usage
-----
    python run_simulation.py

    # Run only specific cases:
    python run_simulation.py --only allergy billing

    # Point at a remote Forkmark instance:
    FM_URL=http://my-server:7700 python run_simulation.py
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────

FM_URL      = os.getenv("FM_URL", "http://localhost:7700/api")
OR_KEY      = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
OR_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

BRANCH_A_MODEL = "openai/gpt-3.5-turbo"   # production
BRANCH_B_MODEL = "openai/gpt-4o-mini"     # challenger
JUDGE_MODEL    = "openai/gpt-4o"           # LLM-as-judge

WORKFLOW_NAME = "Customer Support AI Pipeline"
EVAL_RUN_NAME = "GPT-3.5-turbo (Production) vs GPT-4o-mini (Challenger)"

SYSTEM_PROMPT = (
    "You are a senior customer support agent for ShopEase, a leading e-commerce platform. "
    "Write a professional, empathetic, actionable response to the customer. "
    "Be concise (3-5 sentences). "
    "Never promise timelines you cannot guarantee. "
    "Sign off as 'ShopEase Support Team'."
)

TEST_CASES = [
    {
        "label": "allergy-safety-concern",
        "input": (
            "After using your face cream yesterday I had a severe allergic reaction — "
            "my face swelled up and I had to go to urgent care. "
            "I need the full ingredient list and a refund immediately."
        ),
    },
    {
        "label": "billing-double-charge",
        "input": (
            "I was charged twice for order #ORD-88234. "
            "Two identical charges of $147.99 appear on the same day. "
            "Reverse one immediately or I'll dispute both with my bank."
        ),
    },
    {
        "label": "vip-threatening-churn",
        "input": (
            "I'm a 7-year customer who spends $3,000/year with you. "
            "My last three orders had issues — wrong items, delays, or damage. "
            "If this isn't resolved I'm moving to a competitor and leaving reviews everywhere."
        ),
    },
    {
        "label": "legal-threat-child-injury",
        "input": (
            "My child was injured by a toy I purchased from you last week. "
            "There was a loose metal piece inside with no product warning. "
            "We have $1,200 in medical bills. My attorney says to contact you before filing with the CPSC."
        ),
    },
    {
        "label": "shipping-delay-birthday-gift",
        "input": (
            "I ordered a birthday gift for my daughter arriving today but it's been stuck "
            "in Memphis for 5 days. Her birthday is tomorrow. "
            "Please expedite or send a replacement — Order #ORD-77102."
        ),
    },
]


# ── Forkmark API helper ───────────────────────────────────────────────────────

def fp(method: str, path: str, data: dict = None, fm_key: str = "") -> dict:
    """Call the Forkmark API. Requires an API key for write operations."""
    headers = {"Content-Type": "application/json"}
    if fm_key:
        headers["X-API-Key"] = fm_key
    r = getattr(httpx, method)(
        FM_URL + path, json=data, headers=headers, timeout=60
    )
    if r.status_code >= 400:
        print(f"  [forkmark error] {method.upper()} {path}: {r.status_code} {r.text[:200]}")
        r.raise_for_status()
    return r.json() if r.status_code != 204 else {}


# ── LLM caller (OpenRouter) ───────────────────────────────────────────────────

def call_model(model_id: str, messages: list, temperature: float = 0.7) -> dict:
    """Call an OpenAI-compatible endpoint. Returns text + token counts + latency."""
    t0 = time.time()
    resp = httpx.post(
        OR_BASE_URL.rstrip("/") + "/chat/completions",
        json={
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 400,
        },
        headers={
            "Authorization": f"Bearer {OR_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://forkmark.io",
            "X-Title": "Forkmark Simulation",
        },
        timeout=45,
    )
    resp.raise_for_status()
    data    = resp.json()
    text    = data["choices"][0]["message"]["content"].strip()
    usage   = data.get("usage", {})
    return {
        "text":          text,
        "tokens_input":  usage.get("prompt_tokens", 0),
        "tokens_output": usage.get("completion_tokens", 0),
        "latency_ms":    int((time.time() - t0) * 1000),
    }


# ── Divergence scorer (LLM-as-judge) ─────────────────────────────────────────

JUDGE_PROMPT = """You are evaluating two AI-generated customer support responses.

Response A:
{output_a}

Response B:
{output_b}

Score how DIFFERENT these responses are on a scale from 0.0 to 1.0:
  0.0 = Identical or nearly identical
  0.25 = Minor wording differences, same substance
  0.50 = Moderate divergence — different emphasis or structure
  0.75 = Significant divergence — different approaches
  1.0 = Completely different content

Reply with ONLY a single decimal number (e.g. 0.5). No explanation."""


def judge_divergence(text_a: str, text_b: str) -> float:
    """Score divergence between two outputs using LLM-as-judge."""
    try:
        resp = httpx.post(
            OR_BASE_URL.rstrip("/") + "/chat/completions",
            json={
                "model": JUDGE_MODEL,
                "messages": [{"role": "user", "content": JUDGE_PROMPT.format(
                    output_a=text_a[:2000], output_b=text_b[:2000]
                )}],
                "temperature": 0.0,
                "max_tokens": 10,
            },
            headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return max(0.0, min(1.0, float(raw.split()[0].rstrip(".,;"))))
    except Exception as e:
        print(f"  [judge warning] {e} — falling back to 0.5")
        return 0.5


# ── Core runner ───────────────────────────────────────────────────────────────

def run_branch(tc: dict, model_id: str) -> dict:
    """Call the model for one branch of one test case. Returns outputs + metadata."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Customer message:\n{tc['input']}"},
    ]
    result = call_model(model_id, messages)
    return {"tc": tc, "model_id": model_id, "messages": messages, "result": result}


def main():
    parser = argparse.ArgumentParser(description="Run Forkmark customer support simulation")
    parser.add_argument("--only", nargs="+", metavar="LABEL",
                        help="Run only test cases whose label contains one of these strings")
    args = parser.parse_args()

    # ── Validate setup ─────────────────────────────────────────────────────
    if not OR_KEY:
        print("ERROR: Set OPENROUTER_API_KEY (or OPENAI_API_KEY) before running.")
        print("  export OPENROUTER_API_KEY=sk-or-v1-...")
        sys.exit(1)

    try:
        health = httpx.get(FM_URL.replace("/api", "") + "/api/health", timeout=5).json()
        print(f"  Forkmark: {health.get('status')} (v{health.get('version')})")
    except Exception:
        print("ERROR: Cannot reach Forkmark at", FM_URL)
        print("  Make sure the platform is running (python run.py or docker compose up)")
        sys.exit(1)

    # ── API key (create one automatically for this run) ────────────────────
    try:
        key_resp = httpx.post(
            FM_URL + "/keys",
            json={"name": "simulation-runner"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        ).json()
        fm_key = key_resp.get("raw_key", "")
        if not fm_key:
            print("  WARNING: Could not auto-create API key.")
            print("  Create one manually in the UI (API Keys → Create Key)")
            print("  Then set: export FM_KEY=fm_...")
            fm_key = os.getenv("FM_KEY", "")
        else:
            print(f"  API key created: {fm_key[:12]}...")
    except Exception as e:
        print(f"  WARNING: Could not create API key ({e})")
        fm_key = os.getenv("FM_KEY", "")

    # ── Filter test cases ──────────────────────────────────────────────────
    cases = TEST_CASES
    if args.only:
        cases = [tc for tc in TEST_CASES
                 if any(f in tc["label"] for f in args.only)]
        if not cases:
            print(f"ERROR: No test cases matched {args.only}")
            sys.exit(1)

    print(f"\n  Workflow : {WORKFLOW_NAME}")
    print(f"  Branch A : {BRANCH_A_MODEL} (Production)")
    print(f"  Branch B : {BRANCH_B_MODEL} (Challenger)")
    print(f"  Judge    : {JUDGE_MODEL}")
    print(f"  Cases    : {len(cases)}\n")

    # ── Create workflow + eval run ─────────────────────────────────────────
    wf = fp("post", "/workflows", {"name": WORKFLOW_NAME,
             "description": "Two-branch customer support response pipeline."})
    er = fp("post", "/eval-runs", {
        "workflow_name": WORKFLOW_NAME,
        "name":          EVAL_RUN_NAME,
        "description":   f"LLM judge: {JUDGE_MODEL} via OpenRouter",
        "branch_a_config": {"name": "Production", "model_id": BRANCH_A_MODEL},
        "branch_b_config": {"name": "Challenger",  "model_id": BRANCH_B_MODEL},
    })
    print(f"  Workflow ID : {wf['id']}")
    print(f"  Eval run ID : {er['id']}\n")

    # ── Phase 1: LLM calls (all cases, both branches, concurrent) ─────────
    print("Phase 1 — LLM calls...")
    futures = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for tc in cases:
            fa = pool.submit(run_branch, tc, BRANCH_A_MODEL)
            fb = pool.submit(run_branch, tc, BRANCH_B_MODEL)
            futures[tc["label"]] = (fa, fb)

    branch_results = {}
    for label, (fa, fb) in futures.items():
        ra = fa.result()
        rb = fb.result()
        branch_results[label] = (ra, rb)
        print(f"  ✓ {label:<38}  A={ra['result']['latency_ms']}ms  B={rb['result']['latency_ms']}ms")

    # ── Phase 2: Divergence scoring (concurrent) ──────────────────────────
    print("\nPhase 2 — LLM-as-judge scoring...")
    score_futures = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for label, (ra, rb) in branch_results.items():
            score_futures[label] = pool.submit(
                judge_divergence, ra["result"]["text"], rb["result"]["text"]
            )

    scores = {}
    for label, fut in score_futures.items():
        scores[label] = fut.result()
        print(f"  ✓ {label:<38}  div={scores[label]:.3f}")

    # ── Phase 3: Persist to Forkmark ─────────────────────────────────────
    print("\nPhase 3 — Persisting to Forkmark...")
    for tc in cases:
        ra, rb = branch_results[tc["label"]]

        run = fp("post", "/sdk/runs", {
            "workflow_id":     wf["id"],
            "eval_run_id":     er["id"],
            "test_case_label": tc["label"],
            "input_data":      {"input": tc["input"], "label": tc["label"]},
        }, fm_key=fm_key)

        branch_ids = []
        for r, bname in [(ra, "Production"), (rb, "Challenger")]:
            branch = fp("post", "/sdk/branches", {
                "run_id":      run["id"],
                "workflow_id": wf["id"],
                "name":        bname,
                "model_id":    r["model_id"],
                "temperature": 0.7,
            }, fm_key=fm_key)
            fp("post", "/sdk/steps", {
                "run_id":         run["id"],
                "branch_id":      branch["id"],
                "step_name":      "respond",
                "step_index":     0,
                "input_messages": r["messages"],
                "output_text":    r["result"]["text"],
                "model_id":       r["model_id"],
                "temperature":    0.7,
                "tokens_input":   r["result"]["tokens_input"],
                "tokens_output":  r["result"]["tokens_output"],
                "latency_ms":     r["result"]["latency_ms"],
            }, fm_key=fm_key)
            branch_ids.append(branch["id"])

        fp("post", "/sdk/comparisons", {
            "run_id":          run["id"],
            "workflow_id":     wf["id"],
            "branch_a_id":     branch_ids[0],
            "branch_b_id":     branch_ids[1],
            "step_names":      ["respond"],
            "eval_run_id":     er["id"],
            "test_case_label": tc["label"],
            "divergence_score": scores[tc["label"]],
            "scoring_status":  "completed",
        }, fm_key=fm_key)

        fp("patch", f"/sdk/runs/{run['id']}/complete", {"status": "completed"}, fm_key=fm_key)
        print(f"  ✓ {tc['label']}")

    fp("patch", f"/sdk/eval-runs/{er['id']}/complete",
       {"status": "completed", "total_cases": len(cases)}, fm_key=fm_key)

    # ── Results summary ────────────────────────────────────────────────────
    divs   = list(scores.values())
    avg    = sum(divs) / len(divs) if divs else 0
    ranked = sorted(scores.items(), key=lambda x: -x[1])

    print()
    print("╔" + "═" * 62 + "╗")
    print("║  SIMULATION COMPLETE" + " " * 41 + "║")
    print("╠" + "═" * 62 + "╣")
    print(f"║  Cases : {len(cases)}   |   Avg divergence : {avg:.3f}" + " " * 29 + "║")
    print("╠" + "═" * 62 + "╣")
    for label, div in ranked:
        bar = "▓" * int(div * 25)
        print(f"║  {label:<36}  {div:.3f}  {bar:<18}  ║")
    print("╚" + "═" * 62 + "╝")
    print()
    print(f"  Open Forkmark:  http://localhost:7700")
    print(f"  Eval run:        http://localhost:7700/#evalRunDetail?evalRunId={er['id']}")
    print()


if __name__ == "__main__":
    main()
