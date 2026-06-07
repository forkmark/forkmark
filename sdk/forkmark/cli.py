"""Forkmark command-line interface.

Usage:
    forkmark import langfuse --file export.json --model-a gpt-4o --model-b gpt-4o-mini
    forkmark import langfuse --from-api --from-time 2026-06-01T00:00:00Z
    python -m forkmark import langfuse --file export.json --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional


def _add_langfuse_parser(sub) -> None:
    p = sub.add_parser(
        "langfuse",
        help="Import logged generations from Langfuse as Forkmark A/B comparisons.",
        description="Pair Langfuse generations by identical input (model A vs model B) "
                    "and load them into Forkmark for review and DPO export.",
    )

    src = p.add_argument_group("source (choose one)")
    src.add_argument("--file", help="Path to a Langfuse export (JSON array, {'data': [...]}, or .jsonl)")
    src.add_argument("--from-api", action="store_true",
                     help="Fetch live from the Langfuse public API instead of a file")

    api = p.add_argument_group("Langfuse API (with --from-api)")
    api.add_argument("--langfuse-host", default=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                     help="Langfuse base URL (env LANGFUSE_HOST)")
    api.add_argument("--public-key", default=os.getenv("LANGFUSE_PUBLIC_KEY"),
                     help="Langfuse public key (env LANGFUSE_PUBLIC_KEY)")
    api.add_argument("--secret-key", default=os.getenv("LANGFUSE_SECRET_KEY"),
                     help="Langfuse secret key (env LANGFUSE_SECRET_KEY)")
    api.add_argument("--from-time", help="ISO8601 lower bound on observation start time")
    api.add_argument("--to-time", help="ISO8601 upper bound on observation start time")
    api.add_argument("--observation-name", dest="observation_name",
                     help="Filter by Langfuse observation name")
    api.add_argument("--limit", type=int, default=1000, help="Max observations to fetch (default 1000)")

    pair = p.add_argument_group("pairing")
    pair.add_argument("--model-a", help="Model for branch A (auto-detected if omitted)")
    pair.add_argument("--model-b", help="Model for branch B (auto-detected if omitted)")

    tgt = p.add_argument_group("Forkmark target")
    tgt.add_argument("--forkmark-url", default=os.getenv("FORKMARK_URL", "http://localhost:7700"),
                     help="Forkmark server URL (env FORKMARK_URL)")
    tgt.add_argument("--api-key", default=os.getenv("FORKMARK_API_KEY") or os.getenv("FM_API_KEY"),
                     help="Forkmark API key (env FORKMARK_API_KEY)")
    tgt.add_argument("--workflow", default="langfuse-import", help="Workflow name to file the import under")
    tgt.add_argument("--name", dest="run_name", help="Eval run name (default: 'Langfuse import: A vs B')")
    tgt.add_argument("--branch-a-label", help="Display label for branch A")
    tgt.add_argument("--branch-b-label", help="Display label for branch B")

    p.add_argument("--dry-run", action="store_true",
                   help="Parse and pair only; print a summary without pushing to Forkmark")
    p.set_defaults(func=_cmd_import_langfuse)


def _cmd_import_langfuse(args) -> int:
    from .importers import langfuse as lf

    if not args.file and not args.from_api:
        print("error: provide --file PATH or --from-api", file=sys.stderr)
        return 2

    api = None
    if args.from_api:
        if not args.public_key or not args.secret_key:
            print("error: --from-api needs --public-key and --secret-key "
                  "(or LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)", file=sys.stderr)
            return 2
        api = dict(host=args.langfuse_host, public_key=args.public_key,
                   secret_key=args.secret_key, from_time=args.from_time,
                   to_time=args.to_time, name=args.observation_name, limit=args.limit)

    if not args.dry_run and not args.api_key:
        print("error: a Forkmark API key is required to push "
              "(set --api-key or FORKMARK_API_KEY, or use --dry-run)", file=sys.stderr)
        return 2

    try:
        result = lf.run_import(
            file=args.file, api=api,
            model_a=args.model_a, model_b=args.model_b,
            forkmark_url=args.forkmark_url, api_key=args.api_key,
            workflow=args.workflow, name=args.run_name,
            branch_a_label=args.branch_a_label, branch_b_label=args.branch_b_label,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Observations read : {result.observations}")
    print(f"Models paired     : {result.model_a}  (A)  vs  {result.model_b}  (B)")
    print(f"Comparisons paired: {result.pairs}")
    if result.pairs == 0:
        print("\nNo pairs found. Check that both models ran on the same inputs, "
              "or pass --model-a/--model-b explicitly.")
        return 0
    if args.dry_run:
        print("\nDry run — nothing pushed. Re-run without --dry-run (and with an API key) to import.")
        return 0
    print(f"\nImported {result.created} comparisons into eval run {result.eval_run_id}.")
    print(f"Open {args.forkmark_url} to review and export DPO data.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forkmark", description="Forkmark command-line interface.")
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import", help="Import data from other tools into Forkmark.")
    imp_sub = imp.add_subparsers(dest="source")
    _add_langfuse_parser(imp_sub)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
