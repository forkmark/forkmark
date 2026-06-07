"""
Forkmark Demo Suite — Master Runner
=====================================

Runs all 8 demo seeders in sequence and prints a summary.

Usage:
    python run_all_demos.py                         # run all demos
    python run_all_demos.py --only retail           # run a single demo by name
    python run_all_demos.py --skip model_migration  # skip a demo by name

Available demo names:
    retail · healthcare · legal · finserv · hr · sales · engineering · model_migration · quickstart

Prerequisites:
    1. Forkmark backend running:
       cd forkmark && uvicorn backend.main:app --reload
    2. pip install requests
"""

import subprocess
import sys
import time
import os
import argparse

try:
    import httpx
except ImportError:
    print("[error] httpx is required: pip install httpx")
    sys.exit(1)

BASE_URL = os.getenv("FM_URL", "http://localhost:7700")

DEMOS = [
    {
        "name":        "retail",
        "label":       "Retail — Customer Support Triage",
        "script":      "retail_demo/seed_demo.py",
        "cases":       15,
        "steps":       4,
        "comparison":  "GPT-4o-mini vs GPT-4o",
    },
    {
        "name":        "healthcare",
        "label":       "Healthcare — Clinical Note Summarization",
        "script":      "healthcare_demo/seed_demo.py",
        "cases":       12,
        "steps":       4,
        "comparison":  "Structured SOAP Prompt v2 vs Terse Prompt v1",
    },
    {
        "name":        "legal",
        "label":       "Legal — Contract Clause Risk Review",
        "script":      "legal_demo/seed_demo.py",
        "cases":       12,
        "steps":       4,
        "comparison":  "GPT-4o Legal Context Prompt vs GPT-4o-mini Baseline",
    },
    {
        "name":        "finserv",
        "label":       "Financial Services — Fraud Alert Explanation",
        "script":      "finserv_demo/seed_demo.py",
        "cases":       10,
        "steps":       4,
        "comparison":  "Plain-Language Prompt v2 vs Technical Alert v1",
    },
    {
        "name":        "hr",
        "label":       "HR — Job Description Generator",
        "script":      "hr_demo/seed_demo.py",
        "cases":       10,
        "steps":       4,
        "comparison":  "Inclusive Role-Specific Prompt v2 vs Generic Template v1",
    },
    {
        "name":        "sales",
        "label":       "Sales — Cold Outreach Email Personalization",
        "script":      "sales_demo/seed_demo.py",
        "cases":       10,
        "steps":       4,
        "comparison":  "High-Personalization Prompt v2 vs Generic Template v1",
    },
    {
        "name":        "engineering",
        "label":       "Engineering — Bug Report Triage",
        "script":      "engineering_demo/seed_demo.py",
        "cases":       12,
        "steps":       4,
        "comparison":  "GPT-4o Engineering Context Prompt vs GPT-4o-mini Baseline",
    },
    {
        "name":        "model_migration",
        "label":       "Model Migration — gpt-3.5-turbo → gpt-4o-mini",
        "script":      "model_migration_demo/seed_demo.py",
        "cases":       10,
        "steps":       4,
        "comparison":  "gpt-4o-mini (Challenger) vs gpt-3.5-turbo (Production)",
    },
    {
        "name":        "quickstart",
        "label":       "Quick Start — Full Platform Tour",
        "script":      "seed_from_fixture.py quickstart_demo",
        "cases":       5,
        "steps":       4,
        "comparison":  "Claude 3.5 Sonnet vs GPT-4o (lifecycle demo)",
    },
]


def bootstrap_api_key() -> str:
    """Check backend health and bootstrap an API key for demo seeders.

    Returns the raw API key string, or exits on failure.
    """
    # Check if already provided via environment
    existing = os.environ.get("FORKMARK_API_KEY", "")
    if existing:
        print(f"[setup] Using existing FORKMARK_API_KEY: {existing[:12]}...")
        return existing

    # Health check
    print("[setup] Connecting to Forkmark backend...")
    try:
        r = httpx.get(BASE_URL + "/api/stats", timeout=5)
        r.raise_for_status()
        print(f"[setup] ✓ Backend reachable at {BASE_URL}")
    except Exception:
        print(f"\n[error] Cannot reach {BASE_URL}/api/stats")
        print("  Make sure the Forkmark backend is running:")
        print("  cd forkmark && uvicorn backend.main:app --reload\n")
        sys.exit(1)

    # Bootstrap API key
    print("[setup] Bootstrapping API key for demo suite...")
    try:
        kr = httpx.post(
            BASE_URL + "/api/keys",
            json={"name": "demo-suite-runner"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        kr.raise_for_status()
        raw_key = kr.json().get("raw_key", "")
        if raw_key:
            print(f"[setup] ✓ API key created: {raw_key[:12]}...\n")
            return raw_key
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Keys already exist from a previous run — need FORKMARK_API_KEY
            print("[error] API keys already exist in the database.")
            print("  Set FORKMARK_API_KEY env var to an existing key, or")
            print("  reset the database to start fresh:")
            print("    rm ~/.forkmark/forkmark.db\n")
            sys.exit(1)
        print(f"[error] Could not bootstrap API key: {e}")
    except Exception as e:
        print(f"[error] Could not bootstrap API key: {e}")

    print("[error] Failed to create API key.")
    print("  Create one manually and set FORKMARK_API_KEY env var.")
    sys.exit(1)


def run_demo(demo: dict, api_key: str) -> tuple[bool, float]:
    """Run a single demo seeder. Returns (success, elapsed_seconds)."""
    parts = demo["script"].split()
    script_path = os.path.join(os.path.dirname(__file__), parts[0])
    args = [os.path.join(os.path.dirname(__file__), a) if not a.startswith("-") else a
            for a in parts[1:]]
    env = {**os.environ, "FORKMARK_API_KEY": api_key}
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script_path] + args,
            capture_output=False,
            timeout=300,
            env=env,
        )
        elapsed = time.time() - start
        return result.returncode == 0, elapsed
    except subprocess.TimeoutExpired:
        return False, time.time() - start
    except Exception as e:
        print(f"  [error] Failed to run {demo['script']}: {e}")
        return False, time.time() - start


def print_header():
    total_cases = sum(d["cases"] for d in DEMOS)
    total_comparisons = sum(d["cases"] for d in DEMOS)
    total_steps = sum(d["cases"] * d["steps"] for d in DEMOS)

    print()
    print("╔" + "═" * 63 + "╗")
    print("║   FORKMARK DEMO SUITE — MASTER RUNNER" + " " * 24 + "║")
    # Note: total_cases and total_steps are computed dynamically from DEMOS
    print("╠" + "═" * 63 + "╣")
    ndemos = len(DEMOS)
    print(f"║   {ndemos} demos  ·  {total_cases} test cases  ·  {total_steps} total step comparisons" + " " * 9 + "║")
    print("╚" + "═" * 63 + "╝")
    print()
    print("  Demo plan:")
    for i, d in enumerate(DEMOS):
        print(f"  {i+1}. {d['label']}")
        print(f"     {d['cases']} cases × {d['steps']} steps  |  {d['comparison']}")
    print()


def print_summary(results: list):
    print()
    print("╔" + "═" * 63 + "╗")
    print("║   DEMO SUITE COMPLETE — SUMMARY" + " " * 31 + "║")
    print("╠" + "═" * 63 + "╣")

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    for demo, ok, elapsed in results:
        status = "✓" if ok else "✗"
        label  = demo["label"][:42].ljust(43)
        timing = f"{elapsed:.0f}s"
        print(f"║  {status}  {label} {timing:>5}  ║")

    print("╠" + "═" * 63 + "╣")
    total_elapsed = sum(e for _, _, e in results)
    print(f"║   {passed}/{len(results)} demos seeded successfully  ·  Total time: {total_elapsed:.0f}s" + " " * (20 - len(str(int(total_elapsed)))) + "║")
    print("╚" + "═" * 63 + "╝")
    print()

    if passed == len(results):
        print("  ✓ All demos ready. Open Forkmark:  http://localhost:5173")
        print()
        print("  What to explore:")
        print("  ┌─────────────────────────────────────────────────────────────┐")
        print("  │  Dashboard → Recent Eval Runs → pick any industry demo       │")
        print("  │  Click into an eval run → divergence histogram               │")
        print("  │  Click 'Review Next →' → highest-divergence cases first      │")
        print("  │  See Branch A vs Branch B outputs step-by-step               │")
        print("  │  Record your preference: A wins / B wins / tie / skip        │")
        print("  │  Use the 'High Δ' filter to jump to the most interesting     │")
        print("  └─────────────────────────────────────────────────────────────┘")
        print()
        print("  Highest-impact cases across all demos:")
        print("  • Legal     → data-processing-agreement     (GDPR CRITICAL)")
        print("  • FinServ   → dormant-account-activity       (ATO pattern)")
        print("  • FinServ   → pension-access-unusual         (pension liberation)")
        print("  • Retail    → allergy-safety-concern         (regulatory incident)")
        print("  • Retail    → threat-legal-action            (Score 10/10 escalation)")
        print("  • Eng       → sql-injection-search-endpoint  (P0 security)")
        print("  • Sales     → real-estate-tech-cto           (live press story hook)")
        print()
    else:
        print(f"  ⚠  {failed} demo(s) failed. Check output above for errors.")
        print("  Make sure the Forkmark backend is running:")
        print("  cd forkmark && uvicorn backend.main:app --reload")
        print()


def main():
    parser = argparse.ArgumentParser(description="Run Forkmark demo seeders.")
    parser.add_argument("--only", metavar="NAME", help="Run only this demo (e.g. --only legal)")
    parser.add_argument("--skip", metavar="NAME", help="Skip this demo (e.g. --skip retail)")
    args = parser.parse_args()

    demos_to_run = DEMOS[:]
    if args.only:
        demos_to_run = [d for d in DEMOS if d["name"] == args.only]
        if not demos_to_run:
            print(f"[error] Unknown demo name: {args.only}")
            print(f"  Available: {', '.join(d['name'] for d in DEMOS)}")
            sys.exit(1)
    if args.skip:
        demos_to_run = [d for d in demos_to_run if d["name"] != args.skip]

    api_key = bootstrap_api_key()

    print_header()

    results = []
    for i, demo in enumerate(demos_to_run):
        print(f"\n{'━' * 65}")
        print(f"  [{i+1}/{len(demos_to_run)}] {demo['label']}")
        print(f"{'━' * 65}\n")

        ok, elapsed = run_demo(demo, api_key)
        results.append((demo, ok, elapsed))

        if not ok:
            print(f"\n  [warning] {demo['name']} demo failed after {elapsed:.0f}s — continuing to next demo")

    print_summary(results)
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)


if __name__ == "__main__":
    main()
