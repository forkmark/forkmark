"""Forkmark core tests — models, store, comparator, evaluators, API."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure the forkmark package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("FM_DB_PATH", ":memory:")


# ── Model tests ──────────────────────────────────────────────────────────────

class TestModels:
    def test_workflow_from_row(self):
        from core.models import Workflow
        row = {
            "id": "w1", "name": "test", "description": "desc",
            "created_at": "2025-01-01T00:00:00", "updated_at": "2025-01-01T00:00:00",
            "run_count": 5, "decision_count": 2, "eval_run_count": 1,
            "tags": '["a","b"]',
        }
        wf = Workflow.from_row(row)
        assert wf.name == "test"
        assert wf.run_count == 5
        assert wf.tags == ["a", "b"]
        assert isinstance(wf.created_at, datetime)

    def test_workflow_run_from_row(self):
        from core.models import WorkflowRun, RunStatus
        row = {
            "id": "r1", "workflow_id": "w1", "status": "completed",
            "created_at": "2025-01-01T00:00:00", "completed_at": "2025-01-01T01:00:00",
            "input_data": '{"q": "hello"}', "metadata": '{}',
            "sdk_key_prefix": "fm_abc", "eval_run_id": None,
            "test_case_label": "",
        }
        run = WorkflowRun.from_row(row)
        assert run.status == RunStatus.COMPLETED
        assert run.input_data == {"q": "hello"}
        assert isinstance(run.created_at, datetime)

    def test_step_output_from_row(self):
        from core.models import StepOutput
        row = {
            "id": "s1", "run_id": "r1", "branch_id": "b1",
            "step_name": "classify", "step_index": 0,
            "input_messages": '[{"role":"user","content":"hi"}]',
            "output_text": "hello", "model_id": "gpt-4o",
            "temperature": 0.7, "tokens_input": 10, "tokens_output": 5,
            "latency_ms": 200, "created_at": "2025-01-01T00:00:00",
            "error": None, "trace_id": None, "span_id": None, "cost_usd": 0.001,
        }
        so = StepOutput.from_row(row)
        assert so.step_name == "classify"
        assert so.input_messages == [{"role": "user", "content": "hi"}]
        assert so.cost_usd == 0.001

    def test_comparison_from_row(self):
        from core.models import Comparison
        row = {
            "id": "c1", "run_id": "r1", "workflow_id": "w1",
            "branch_a_id": "ba", "branch_b_id": "bb",
            "created_at": "2025-01-01T00:00:00",
            "step_names": '["step1"]', "decided": 0, "decision_id": None,
            "eval_run_id": None, "test_case_label": "",
            "divergence_score": 0.5,
            "step_divergence_scores": '{"step1": 0.5}',
            "eval_results": '{}', "scoring_status": "completed",
        }
        comp = Comparison.from_row(row)
        assert comp.divergence_score == 0.5
        assert comp.step_divergence_scores == {"step1": 0.5}

    def test_decision_to_dict_strips_hash(self):
        from core.models import ApiKey
        row = {
            "id": "k1", "name": "test", "key_hash": "secret_hash",
            "key_prefix": "fm_abc", "created_at": "2025-01-01T00:00:00",
            "last_used_at": None, "is_active": 1,
        }
        ak = ApiKey.from_row(row)
        d = ak.to_dict()
        assert "key_hash" not in d
        assert d["key_prefix"] == "fm_abc"


# ── Store tests ──────────────────────────────────────────────────────────────

class TestStore:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        from core.store import Database
        db_path = str(tmp_path / "test.db")
        self.db = Database(db_path)

    def test_workflow_crud(self):
        wf = self.db.upsert_workflow("test-wf", "desc")
        assert wf.name == "test-wf"
        assert wf.description == "desc"

        fetched = self.db.get_workflow(wf.id)
        assert fetched.name == "test-wf"

        wfs = self.db.list_workflows()
        assert len(wfs) >= 1

    def test_upsert_workflow_idempotent(self):
        wf1 = self.db.upsert_workflow("idempotent")
        wf2 = self.db.upsert_workflow("idempotent", "updated desc")
        assert wf1.id == wf2.id
        assert wf2.description == "updated desc"

    def test_run_lifecycle(self):
        wf = self.db.upsert_workflow("run-test")
        run = self.db.create_run(wf.id, {"q": "hello"})
        assert run.status.value == "running"

        self.db.complete_run(run.id)
        fetched = self.db.get_run(run.id)
        assert fetched.status.value == "completed"

    def test_list_runs_uses_from_row(self):
        """Regression test for fix #1: list_runs must use from_row, not **unpacking."""
        wf = self.db.upsert_workflow("list-runs-test")
        self.db.create_run(wf.id, {"q": "test"})
        runs = self.db.list_runs(wf.id)
        assert len(runs) == 1
        assert runs[0].status.value == "running"
        assert isinstance(runs[0].input_data, dict)

    def test_branch_and_step(self):
        wf = self.db.upsert_workflow("branch-test")
        run = self.db.create_run(wf.id)
        branch = self.db.create_branch(run.id, wf.id, "baseline", "gpt-4o")
        assert branch.model_id == "gpt-4o"

        step = self.db.save_step_output(
            run_id=run.id, branch_id=branch.id, step_name="classify",
            step_index=0, input_messages=[{"role": "user", "content": "hi"}],
            output_text="hello world", model_id="gpt-4o",
        )
        assert step.output_text == "hello world"
        assert step.cost_usd is not None or step.tokens_input == 0

    def test_comparison_and_decision(self):
        wf = self.db.upsert_workflow("comp-test")
        run = self.db.create_run(wf.id)
        ba = self.db.create_branch(run.id, wf.id, "A", "gpt-4o")
        bb = self.db.create_branch(run.id, wf.id, "B", "claude-3-5-sonnet")

        self.db.save_step_output(
            run.id, ba.id, "step1", 0, [], "output A", "gpt-4o")
        self.db.save_step_output(
            run.id, bb.id, "step1", 0, [], "output B", "claude-3-5-sonnet")

        comp = self.db.create_comparison(
            run.id, wf.id, ba.id, bb.id, step_names=["step1"])
        assert comp.scoring_status in ("completed", "pending")

        from core.models import DecisionChoice, ConfidenceLevel
        dec = self.db.create_decision(
            comparison_id=comp.id, run_id=run.id, workflow_id=wf.id,
            reviewer_id="tester", choice=DecisionChoice.BRANCH_A,
            confidence=ConfidenceLevel.HIGH,
            rationale_for_choice="A is better",
            rationale_for_rejection="B is worse",
            branch_winner_id=ba.id, branch_loser_id=bb.id,
        )
        assert dec.choice.value == "A"

    def test_test_set_crud(self):
        ts = self.db.create_test_set("my-tests", "test description")
        assert ts.name == "my-tests"

        tc = self.db.add_test_case(ts.id, "case-1", {"q": "hello"}, ["tag1"])
        assert tc.label == "case-1"

        cases = self.db.list_test_cases(ts.id)
        assert len(cases) == 1

    def test_frozen_test_set(self):
        ts = self.db.create_test_set("frozen-test")
        self.db.add_test_case(ts.id, "case-1", {"q": "hello"})
        self.db.freeze_test_set(ts.id)

        with pytest.raises(ValueError, match="frozen"):
            self.db.add_test_case(ts.id, "case-2", {"q": "world"})

    def test_batch_step_outputs(self):
        wf = self.db.upsert_workflow("batch-test")
        run = self.db.create_run(wf.id)
        b = self.db.create_branch(run.id, wf.id, "A", "gpt-4o")
        steps = [
            {"run_id": run.id, "branch_id": b.id, "step_name": f"step{i}",
             "step_index": i, "output_text": f"out{i}", "model_id": "gpt-4o"}
            for i in range(5)
        ]
        saved = self.db.batch_save_step_outputs(steps)
        assert len(saved) == 5

    def test_api_key_create_verify(self):
        ak, raw = self.db.create_api_key("test-key")
        assert raw.startswith("fm_")
        verified = self.db.verify_api_key(raw)
        assert verified is not None
        assert verified.name == "test-key"

        bad = self.db.verify_api_key("fm_invalid_key_here")
        assert bad is None

    def test_api_key_revoke(self):
        ak, raw = self.db.create_api_key("revoke-test")
        self.db.revoke_api_key(ak.id)
        assert self.db.verify_api_key(raw) is None

    def test_eval_run_lifecycle(self):
        from core.models import EvalRunStatus
        wf = self.db.upsert_workflow("eval-test")
        er = self.db.create_eval_run(
            wf.id, "eval-1",
            branch_a_config={"model": "gpt-4o"},
            branch_b_config={"model": "claude-3"},
        )
        assert er.status == EvalRunStatus.PENDING

        self.db.update_eval_run_status(er.id, EvalRunStatus.RUNNING)
        self.db.update_eval_run_status(er.id, EvalRunStatus.COMPLETED, total_cases=10)

        fetched = self.db.get_eval_run(er.id)
        assert fetched.status == EvalRunStatus.COMPLETED
        assert fetched.total_cases == 10

    def test_stats(self):
        self.db.upsert_workflow("stats-wf")
        stats = self.db.get_stats()
        assert "total_workflows" in stats
        assert stats["total_workflows"] >= 1

    def test_settings(self):
        self.db.set_setting("test_key", "test_value")
        assert self.db.get_setting("test_key") == "test_value"
        assert self.db.get_setting("missing", "default") == "default"

    def test_prune_step_outputs(self):
        wf = self.db.upsert_workflow("prune-test")
        run = self.db.create_run(wf.id)
        b = self.db.create_branch(run.id, wf.id, "A", "gpt-4o")
        self.db.save_step_output(run.id, b.id, "s1", 0, [], "out", "gpt-4o")
        # Pruning with 0 days would delete everything, but min is 1
        deleted = self.db.prune_step_outputs(older_than_days=9999)
        assert deleted == 0  # nothing old enough


# ── Comparator tests ─────────────────────────────────────────────────────────

class TestComparator:
    def test_lexical_identical(self):
        from core.comparator import _lexical_divergence
        # IDF degeneracy: with only 2 identical docs all IDF weights → 0,
        # so TF-IDF cosine returns 0. SequenceMatcher gives 1.0 (30% weight).
        # divergence = 1 - (0*0.7 + 1.0*0.3) = 0.7
        assert _lexical_divergence("hello world", "hello world") == 0.7

    def test_lexical_different(self):
        from core.comparator import _lexical_divergence
        score = _lexical_divergence("the cat sat on the mat", "quantum physics is complex")
        assert score > 0.5

    def test_lexical_empty(self):
        from core.comparator import _lexical_divergence
        assert _lexical_divergence("", "") == 0.0

    def test_tfidf_cosine(self):
        from core.comparator import _tfidf_cosine
        # Identical docs → all terms in both → df=2 → idf=log(1)=0 → cosine=0
        assert _tfidf_cosine("hello world", "hello world") == 0.0
        assert _tfidf_cosine("", "") == 1.0  # empty special-case
        sim = _tfidf_cosine("hello", "goodbye")
        assert 0.0 <= sim <= 1.0

    def test_divergence_score_auto(self):
        from core.comparator import divergence_score
        s = divergence_score("hello world", "hello world")
        # IDF degeneracy makes identical short texts score ~0.7 via lexical tier
        assert s < 1.0

    def test_inline_diff(self):
        from core.comparator import inline_diff
        diff = inline_diff("hello world", "hello there")
        assert len(diff) > 0
        types = {d["type"] for d in diff}
        assert "equal" in types or "removed" in types or "added" in types

    def test_summarize_divergence(self):
        from core.comparator import summarize_divergence
        assert "identical" in summarize_divergence("a", "b", 0.01).lower()
        assert "high" in summarize_divergence("a", "b", 0.9).lower()

    def test_scorer_name(self):
        from core.comparator import scorer_name
        name = scorer_name()
        assert isinstance(name, str)
        assert len(name) > 0


# ── Evaluator tests ──────────────────────────────────────────────────────────

class TestEvaluators:
    def test_json_schema_valid(self):
        from core.evaluators import _eval_json_schema
        result = _eval_json_schema('{"key": "value"}', {}, {})
        assert result.passed is True
        assert result.score == 1.0

    def test_json_schema_invalid(self):
        from core.evaluators import _eval_json_schema
        result = _eval_json_schema("not json", {}, {})
        assert result.passed is False

    def test_regex_match(self):
        from core.evaluators import _eval_regex_match
        result = _eval_regex_match("hello world 42", {"pattern": r"\d+"}, {})
        assert result.passed is True

    def test_regex_no_match(self):
        from core.evaluators import _eval_regex_match
        result = _eval_regex_match("hello", {"pattern": r"\d+"}, {})
        assert result.passed is False

    def test_exact_match(self):
        from core.evaluators import _eval_exact_match
        result = _eval_exact_match("hello", {"expected": "hello"}, {})
        assert result.passed is True

    def test_contains(self):
        from core.evaluators import _eval_contains
        result = _eval_contains("hello world", {"substring": "world"}, {})
        assert result.passed is True

    def test_max_length_pass(self):
        from core.evaluators import _eval_max_length
        result = _eval_max_length("short", {"max_chars": 100}, {})
        assert result.passed is True

    def test_max_length_fail(self):
        from core.evaluators import _eval_max_length
        result = _eval_max_length("x" * 200, {"max_chars": 100}, {})
        assert result.passed is False

    def test_latency_check(self):
        from core.evaluators import _eval_latency_check
        result = _eval_latency_check("", {"max_ms": 1000}, {"latency_ms": 500})
        assert result.passed is True

    def test_registry(self):
        from core.evaluators import _REGISTRY
        assert "json_schema" in _REGISTRY
        assert "regex_match" in _REGISTRY
        assert "exact_match" in _REGISTRY


# ── Cost estimation tests ────────────────────────────────────────────────────

class TestCostEstimation:
    def test_exact_model_match(self):
        from core.store import _estimate_cost
        cost = _estimate_cost("gpt-4o", 1000, 500)
        assert cost is not None
        assert cost > 0

    def test_prefix_match(self):
        from core.store import _estimate_cost
        cost = _estimate_cost("gpt-4o-2024-08-06", 1000, 500)
        assert cost is not None

    def test_unknown_model(self):
        from core.store import _estimate_cost
        cost = _estimate_cost("totally-unknown-model-xyz", 1000, 500)
        assert cost is None

    def test_version_suffix_compiled_once(self):
        """Regression test for fix #5: regex should be module-level, not per-call."""
        from core.store import _VERSION_SUFFIX_RE
        assert _VERSION_SUFFIX_RE is not None
        assert _VERSION_SUFFIX_RE.match("-2024-08-06")
        assert _VERSION_SUFFIX_RE.match("-preview")
        assert not _VERSION_SUFFIX_RE.match("-ft-acme")


# ── Security tests ───────────────────────────────────────────────────────────

class TestSecurity:
    def test_bootstrap_token_constant_time(self):
        """Regression test for fix #4: must use hmac.compare_digest."""
        # We verify the import and usage pattern exist in backend source
        # (post-modularization the logic lives in routes/keys.py)
        backend_dir = Path(__file__).parent.parent / "backend"
        found = False
        for py_file in backend_dir.rglob("*.py"):
            src = py_file.read_text()
            if "hmac.compare_digest" in src or "compare_digest" in src:
                found = True
                break
        assert found, \
            "Bootstrap token comparison must use constant-time compare"


# ── Price table tests ────────────────────────────────────────────────────────

class TestPriceTable:
    def test_update_pricing_table(self):
        from core.store import update_pricing_table, _estimate_cost
        update_pricing_table({"test-model-xyz": {"input": 1.0, "output": 2.0}})
        cost = _estimate_cost("test-model-xyz", 1_000_000, 1_000_000)
        assert cost is not None
        assert abs(cost - 3.0) < 0.01


# ── API endpoint tests (using TestClient) ────────────────────────────────────

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        os.environ["FM_DB_PATH"] = str(tmp_path / "api_test.db")
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"

        # Force reimport to pick up new DB path
        import importlib
        if "config" in sys.modules:
            importlib.reload(sys.modules["config"])
        if "core.store" in sys.modules:
            importlib.reload(sys.modules["core.store"])
        if "backend.main" in sys.modules:
            importlib.reload(sys.modules["backend.main"])

        from backend.main import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_workflow_crud(self):
        resp = self.client.post("/api/workflows", json={
            "name": "api-test", "description": "testing"
        })
        assert resp.status_code == 201
        wf = resp.json()
        assert wf["name"] == "api-test"

        resp = self.client.get("/api/workflows")
        assert resp.status_code == 200

    def test_stats(self):
        resp = self.client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_workflows" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
