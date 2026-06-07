"""Guards the README quickstart against SDK drift.

The README's "SDK Integration" snippet must always match the real SDK surface.
This test exists because the snippet previously showed `run.compare(...)` (a
method that never existed) and the wrong `ForkmarkClient(...)` argument order —
i.e. the headline example did not run. If you change the README SDK example or
the SDK signatures, update both together so they stay in sync.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "sdk"))

import forkmark                                  # noqa: E402
from forkmark import ForkmarkClient             # noqa: E402
from forkmark.workflow import WorkflowContext    # noqa: E402

README = (REPO / "README.md").read_text(encoding="utf-8")


def test_readme_entrypoints_exist():
    """The module-level calls the README uses must exist and be callable."""
    assert callable(forkmark.init)
    assert callable(forkmark.run)
    assert callable(forkmark.eval_run)


def test_forkmark_client_api_key_is_first_param():
    """README/SDK contract: api_key is the first argument, not base_url."""
    params = list(inspect.signature(ForkmarkClient.__init__).parameters)
    assert params[1] == "api_key", params


def test_init_and_run_signatures():
    init_params = set(inspect.signature(forkmark.init).parameters)
    assert {"api_key", "base_url"} <= init_params, init_params
    run_params = set(inspect.signature(forkmark.run).parameters)
    assert {"workflow", "input_data"} <= run_params, run_params


def test_log_step_output_accepts_readme_kwargs():
    sig = inspect.signature(WorkflowContext.log_step_output)
    for kw in ("name", "messages", "output", "model", "branch"):
        assert kw in sig.parameters, kw


def test_eval_run_signature():
    p = set(inspect.signature(forkmark.eval_run).parameters)
    for kw in ("name", "workflow", "branch_a", "branch_b", "inputs"):
        assert kw in p, kw


def test_readme_snippet_uses_supported_api_only():
    """Lock the README text to the supported calls; ban the regressed ones."""
    assert "forkmark.init(" in README
    assert "forkmark.run(" in README
    assert "log_step_output(" in README
    # Calls that previously broke the quickstart must never reappear:
    assert "run.compare(" not in README
    assert 'ForkmarkClient("http' not in README
