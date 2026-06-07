"""Tests for the Langfuse importer (pure pairing/parsing + dry-run CLI).

No network and no running Forkmark server are required: the data source is the
committed sample export, and pushing is exercised separately via the SDK's
already-tested logging path.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "sdk"))

from forkmark.importers import langfuse as lf   # noqa: E402
from forkmark import cli                          # noqa: E402

SAMPLE = str(REPO / "examples" / "langfuse_sample_export.json")


def test_load_from_file_data_wrapper():
    obs = lf.load_from_file(SAMPLE)
    assert isinstance(obs, list)
    assert len(obs) == 6


def test_pair_by_input_auto_detects_models():
    obs = lf.load_from_file(SAMPLE)
    pairs, model_a, model_b = lf.pair_by_input(obs)
    assert (model_a, model_b) == ("gpt-4o", "gpt-4o-mini")
    assert len(pairs) == 3
    # Branch A is the gpt-4o (more detailed) output for the first input.
    first = pairs[0]
    assert "5% late fee" in first.output_a
    assert "fee for paying late" in first.output_b
    assert first.messages[0]["role"] == "user"


def test_pair_by_input_explicit_models_swap_branches():
    obs = lf.load_from_file(SAMPLE)
    pairs, a, b = lf.pair_by_input(obs, model_a="gpt-4o-mini", model_b="gpt-4o")
    assert (a, b) == ("gpt-4o-mini", "gpt-4o")
    assert len(pairs) == 3
    # Now branch A should be the mini output.
    assert "fee for paying late" in pairs[0].output_a


def test_normalize_skips_non_generation_and_empty():
    span = {"id": "s1", "type": "SPAN", "input": "x", "output": "y"}
    no_output = {"id": "g1", "type": "GENERATION", "input": "x", "output": None}
    assert lf.normalize_observation(span) is None
    assert lf.normalize_observation(no_output) is None


def test_coercion_handles_json_string_io():
    # v2-style: input/output arrive as JSON strings + providedModelName
    obs = {
        "id": "g2", "type": "GENERATION",
        "input": '{"messages": [{"role": "user", "content": "hi"}]}',
        "output": '{"role": "assistant", "content": "hello there"}',
        "providedModelName": "gpt-4o",
    }
    g = lf.normalize_observation(obs)
    assert g is not None
    assert g.model == "gpt-4o"
    assert g.output == "hello there"
    assert g.messages[0]["content"] == "hi"


def test_pairing_requires_two_distinct_models():
    # Only one model present -> no pairs
    obs = [
        {"id": "a", "type": "GENERATION", "input": "q1", "output": "o1", "model": "m1"},
        {"id": "b", "type": "GENERATION", "input": "q2", "output": "o2", "model": "m1"},
    ]
    pairs, a, b = lf.pair_by_input(obs)
    assert pairs == []


def test_cli_dry_run(capsys):
    rc = cli.main(["import", "langfuse", "--file", SAMPLE, "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Comparisons paired: 3" in out
    assert "gpt-4o" in out
    assert "Dry run" in out


def test_cli_requires_source():
    rc = cli.main(["import", "langfuse", "--dry-run"])
    assert rc == 2


class _FakeClient:
    """Minimal stand-in for ForkmarkClient that records calls (no server)."""
    def __init__(self):
        self.calls = []
        self._n = 0

    def _id(self, prefix):
        self._n += 1
        return f"{prefix}-{self._n}"

    def create_eval_run(self, **kw):
        self.calls.append(("create_eval_run", kw))
        return {"id": "er-1"}

    def complete_eval_run(self, er_id, **kw):
        self.calls.append(("complete_eval_run", er_id, kw))
        return {}

    def start_run(self, workflow, input_data, **kw):
        self.calls.append(("start_run", workflow))
        return {"id": self._id("run")}

    def create_branch(self, **kw):
        self.calls.append(("create_branch", kw["name"], kw.get("is_baseline")))
        return {"id": self._id("branch")}

    def log_steps_batch(self, steps):
        self.calls.append(("log_steps_batch", len(steps)))
        return []

    def complete_run(self, run_id, status):
        self.calls.append(("complete_run", status))

    def create_comparison(self, **kw):
        self.calls.append(("create_comparison", kw["run_id"]))
        return {"id": self._id("cmp")}


def test_import_to_forkmark_orchestration():
    obs = lf.load_from_file(SAMPLE)
    pairs, a, b = lf.pair_by_input(obs)
    fake = _FakeClient()
    er_id, created = lf.import_to_forkmark(
        fake, pairs, workflow="wf", name="run", model_a=a, model_b=b,
    )
    assert er_id == "er-1"
    assert created == 3
    names = [c[0] for c in fake.calls]
    assert names.count("create_eval_run") == 1
    assert names.count("complete_eval_run") == 1
    assert names.count("create_comparison") == 3          # one per pair
    assert names.count("create_branch") == 6              # A and B per pair
    # each pair logged a batch of 2 steps (branch A + branch B)
    batch_sizes = [c[1] for c in fake.calls if c[0] == "log_steps_batch"]
    assert batch_sizes == [2, 2, 2]
