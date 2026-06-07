"""
run_live_comparison.py — Live Model Migration Comparison
=========================================================

Runs the StyleForge product content pipeline against BOTH models in real-time
and streams every result into Forkmark for human review.

Requires:
    OPENAI_API_KEY    — your OpenAI key (charged at normal rates)
    FORKMARK_API_KEY — your Forkmark API key (bootstrap one first)
    pip install httpx tenacity

What this script does:
    1. Verifies both environment variables are set
    2. Confirms the Forkmark backend is reachable
    3. Creates a Forkmark eval run for this migration study
    4. Processes every product through BOTH models simultaneously
    5. Logs all four pipeline steps per model to Forkmark
    6. Prints a live result table
    7. Prints the Forkmark URL where you can review results

Usage:
    export OPENAI_API_KEY=sk-...
    export FORKMARK_API_KEY=fm_...

    # Run all 10 products (default: gpt-3.5-turbo vs gpt-4o-mini)
    python run_live_comparison.py

    # Try a single SKU first to verify setup
    python run_live_comparison.py --sku SUP-0042

    # Evaluate a different model pair
    python run_live_comparison.py --baseline gpt-4o-mini --challenger gpt-4o

    # Point at a non-default Forkmark backend
    python run_live_comparison.py --forkmark-url http://localhost:7700
"""

from __future__ import annotations

import os
import sys
import time
import argparse
import textwrap

# ── Resolve paths ──────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_EXAMPLES = os.path.dirname(_HERE)
_SDK = os.path.join(os.path.dirname(_EXAMPLES), "sdk")
sys.path.insert(0, _HERE)      # allows: from workflow_with_forkmark import ...
sys.path.insert(0, _SDK)       # allows: from forkmark.client import ...


# ── Pre-flight checks ──────────────────────────────────────────────────────────

def check_env(baseline: str, challenger: str, forkmark_url: str) -> bool:
    ok = True

    openai_key    = os.environ.get("OPENAI_API_KEY", "")
    forkmark_key = os.environ.get("FORKMARK_API_KEY", "")

    print()
    print("  Pre-flight checks")
    print("  " + "─" * 60)

    # OpenAI key
    if openai_key:
        masked = openai_key[:8] + "..." + openai_key[-4:]
        print(f"  ✓  OPENAI_API_KEY      {masked}")
    else:
        print("  ✗  OPENAI_API_KEY      NOT SET")
        print("        export OPENAI_API_KEY=sk-...")
        ok = False

    # Forkmark key
    if forkmark_key:
        masked = forkmark_key[:6] + "..."
        print(f"  ✓  FORKMARK_API_KEY   {masked}")
    else:
        print("  ✗  FORKMARK_API_KEY   NOT SET")
        print("        Bootstrap one:")
        print(f"        curl -s -X POST {forkmark_url}/api/keys \\")
        print("             -H 'Content-Type: application/json' \\")
        print("             -H 'X-API-Key: <FM_BOOTSTRAP_TOKEN>' \\")
        print("             -d '{\"name\": \"live-comparison\"}'")
        ok = False

    # Forkmark reachability
    try:
        import httpx as _httpx_check
        r = _httpx_check.get(f"{forkmark_url}/api/health", timeout=3)
        if r.status_code == 200:
            print(f"  ✓  Forkmark backend   {forkmark_url}  (reachable)")
        else:
            print(f"  ⚠  Forkmark backend   {forkmark_url}  HTTP {r.status_code}")
    except Exception as e:
        print(f"  ✗  Forkmark backend   {forkmark_url}  NOT REACHABLE")
        print(f"        Start it with:  cd forkmark && uvicorn backend.main:app --reload --port 7700")
        ok = False

    # httpx / tenacity
    try:
        import httpx, tenacity  # noqa: F401
        print(f"  ✓  httpx + tenacity    installed")
    except ImportError as e:
        print(f"  ✗  Missing package:    {e}")
        print(f"        pip install httpx tenacity")
        ok = False

    # Model note
    print(f"  ─  Baseline model:     {baseline}  (production)")
    print(f"  ─  Challenger model:   {challenger}  (candidate)")
    print("  " + "─" * 60)

    return ok


# ── Cost estimate ──────────────────────────────────────────────────────────────

COST_PER_1K_INPUT = {
    "gpt-3.5-turbo": 0.0005,
    "gpt-4o-mini":   0.00015,
    "gpt-4o":        0.005,
}
COST_PER_1K_OUTPUT = {
    "gpt-3.5-turbo": 0.0015,
    "gpt-4o-mini":   0.0006,
    "gpt-4o":        0.015,
}

def estimate_cost(baseline: str, challenger: str, n_products: int) -> str:
    """Rough cost estimate: ~400 tokens in + ~300 tokens out per step × 4 steps × n_products × 2 models."""
    total = 0.0
    for model in (baseline, challenger):
        in_rate  = COST_PER_1K_INPUT.get(model, 0.005)
        out_rate = COST_PER_1K_OUTPUT.get(model, 0.015)
        tok_in   = n_products * 4 * 400 / 1000
        tok_out  = n_products * 4 * 300 / 1000
        total   += tok_in * in_rate + tok_out * out_rate
    return f"~${total:.3f}"


# ── Result printer ─────────────────────────────────────────────────────────────

def print_result_row(i: int, total: int, sku: str, title: str, comparison_id: str | None,
                     latency_ms: int, ok: bool, error: str | None):
    check  = "✓" if ok else "✗"
    short  = textwrap.shorten(title or error or "—", width=42)
    fm_ref = f"  cmp:{comparison_id[:8]}" if comparison_id else ""
    elapsed = f"{latency_ms/1000:.1f}s"
    print(f"  {check}  [{i:02d}/{total:02d}]  {sku:<14}  {short:<44}  {elapsed:>5}{fm_ref}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Live model migration comparison via Forkmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--sku",           help="Process only this SKU (useful for quick smoke test)")
    parser.add_argument("--baseline",      default="gpt-3.5-turbo", help="Baseline (production) model")
    parser.add_argument("--challenger",    default="gpt-4o-mini",   help="Challenger model")
    parser.add_argument("--forkmark-url", default="http://127.0.0.1:7700", dest="forkmark_url")
    parser.add_argument("--skip-preflight", action="store_true",    help="Skip environment checks")
    args = parser.parse_args()

    # ── Banner ─────────────────────────────────────────────────────────────────
    print()
    print("╔" + "═" * 63 + "╗")
    print("║   STYLEFORGE COMMERCE — LIVE MODEL MIGRATION COMPARISON" + " " * 7 + "║")
    print("╠" + "═" * 63 + "╣")
    print(f"║   Baseline:   {args.baseline:<48}║")
    print(f"║   Challenger: {args.challenger:<48}║")
    print(f"║   Forkmark:  {args.forkmark_url:<48}║")
    print("╚" + "═" * 63 + "╝")

    # ── Pre-flight ─────────────────────────────────────────────────────────────
    if not args.skip_preflight:
        if not check_env(args.baseline, args.challenger, args.forkmark_url):
            print()
            print("  ✗  Pre-flight failed. Fix the issues above and re-run.")
            print()
            sys.exit(1)
        print("  ✓  All checks passed")
        print()

    # ── Import pipeline (after path setup) ───────────────────────────────────
    try:
        from workflow_with_forkmark import (
            ProductContentPipelineWithForkmark,
            PipelineConfig,
            SAMPLE_PRODUCTS,
        )
    except ImportError as e:
        print(f"\n  ✗  Could not import workflow_with_forkmark: {e}")
        print("     Make sure you're running this from the model_migration_demo directory,")
        print("     or that forkmark/sdk is on your PYTHONPATH.")
        sys.exit(1)

    # ── Filter products ───────────────────────────────────────────────────────
    products = SAMPLE_PRODUCTS
    if args.sku:
        products = [p for p in products if p.sku == args.sku]
        if not products:
            available = ", ".join(p.sku for p in SAMPLE_PRODUCTS)
            print(f"  ✗  SKU not found: {args.sku}")
            print(f"     Available SKUs: {available}")
            sys.exit(1)

    n = len(products)
    est = estimate_cost(args.baseline, args.challenger, n)
    print(f"  Processing {n} product(s)  ·  Estimated API cost: {est}")
    print(f"  Each product: {args.baseline} + {args.challenger} × 4 pipeline steps")
    print()

    # ── Confirm if running all products ───────────────────────────────────────
    if n >= 5 and not args.sku:
        try:
            answer = input(f"  Proceed with all {n} products? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("y", "yes"):
            print("  Aborted.")
            sys.exit(0)
        print()

    # ── Run pipeline ──────────────────────────────────────────────────────────
    config = PipelineConfig(
        baseline_model   = args.baseline,
        challenger_model = args.challenger,
        forkmark_url    = args.forkmark_url,
        eval_run_name    = f"{args.baseline} vs {args.challenger} — Product Content",
    )
    config.validate()

    print(f"  {'SKU':<14}  {'Title / Error':<44}  {'Time':>5}  Comparison")
    print("  " + "─" * 80)

    passed   = 0
    t_suite  = time.perf_counter()
    eval_url = ""

    with ProductContentPipelineWithForkmark(config) as pipeline:
        for i, product in enumerate(products, 1):
            result = pipeline.process_with_comparison(product)
            ok     = result.success
            if ok:
                passed += 1

            print_result_row(
                i            = i,
                total        = n,
                sku          = product.sku,
                title        = result.title.title if result.title else None,
                comparison_id= result.comparison_id,
                latency_ms   = result.total_latency_ms,
                ok           = ok,
                error        = result.error,
            )

        pipeline.finish_eval_run(total_cases=passed)
        eval_url = f"{args.forkmark_url.replace('7700','5173')}"

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed_total = time.perf_counter() - t_suite
    print()
    print("  " + "─" * 80)
    print(f"  {passed}/{n} products compared  ·  Total time: {elapsed_total:.0f}s")
    print()

    if passed > 0:
        print("  Results are live in Forkmark:")
        print(f"  {eval_url}")
        print()
        print("  What to do next:")
        print("  ┌─────────────────────────────────────────────────────────────────┐")
        print("  │  1. Open the Forkmark dashboard (link above)                    │")
        print(f"  │  2. Find eval run: '{config.eval_run_name}'  │")
        print("  │  3. Check the divergence histogram — which steps changed most?  │")
        print("  │  4. Click 'Review Next →' to review highest-divergence cases    │")
        print("  │  5. Record your preference per product: A / B / tie             │")
        print("  │  6. Once you've reviewed >60% of cases, check the win rate      │")
        print("  │                                                                   │")
        print(f"  │  If {args.challenger} wins on >60%:                                  │")
        print(f"  │    → In workflow_original.py, change:                           │")
        print(f"  │      model = \"{args.baseline}\"                                    │")
        print(f"  │    to:                                                            │")
        print(f"  │      model = \"{args.challenger}\"                                    │")
        print(f"  │    That's the only line you need to change.                      │")
        print("  └─────────────────────────────────────────────────────────────────┘")
        print()
    else:
        print("  ✗  No products succeeded. Check errors above.")
        print("     Run with --sku <SKU> to debug a single product.")
        print()


if __name__ == "__main__":
    main()
