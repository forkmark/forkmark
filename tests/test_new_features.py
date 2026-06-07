"""Tests for all new features: collaboration (comments, assignments, review queue),
prompt playground, observability dashboard, PgBouncer health checks, DPO export
enhancements, SDK versioning, and Anthropic wrapper.

These tests run alongside the existing test_core.py suite and validate
integration of all features added during the review-driven improvements.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("FM_DB_PATH", ":memory:")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fresh_db():
    """Create a fresh in-memory Database instance."""
    from core.store import Database
    return Database(":memory:")


def _db_with_comparison(db=None):
    """Create a DB with a workflow, run, branches, steps, and comparison.
    Returns (db, wf, run, ba, bb, comp)."""
    if db is None:
        db = _fresh_db()
    wf = db.upsert_workflow("test-wf")
    run = db.create_run(wf.id)
    ba = db.create_branch(run.id, wf.id, "A", "gpt-4o-mini")
    bb = db.create_branch(run.id, wf.id, "B", "gpt-4o")
    db.save_step_output(run.id, ba.id, "answer", 0, [], "Output A text", "gpt-4o-mini",
                        tokens_input=10, tokens_output=20, latency_ms=200)
    db.save_step_output(run.id, bb.id, "answer", 0, [], "Output B text", "gpt-4o",
                        tokens_input=10, tokens_output=25, latency_ms=350)
    comp = db.create_comparison(run.id, wf.id, ba.id, bb.id, step_names=["answer"])
    return db, wf, run, ba, bb, comp


# ── Collaboration: Comments ──────────────────────────────────────────────────

class TestComments:
    def setup_method(self):
        self.db, self.wf, self.run, self.ba, self.bb, self.comp = _db_with_comparison()

    def test_add_comment(self):
        c = self.db.add_comment(self.comp.id, "reviewer1", "Great output on branch A",
                                author_name="Alice")
        assert c["id"]
        assert c["body"] == "Great output on branch A"
        assert c["author_id"] == "reviewer1"
        assert c["author_name"] == "Alice"
        assert c["comparison_id"] == self.comp.id
        assert not c["is_resolved"]  # SQLite stores as 0/1
        assert c["parent_id"] is None

    def test_list_comments(self):
        self.db.add_comment(self.comp.id, "r1", "Comment 1")
        self.db.add_comment(self.comp.id, "r2", "Comment 2")
        comments = self.db.list_comments(self.comp.id)
        assert len(comments) == 2

    def test_threaded_reply(self):
        parent = self.db.add_comment(self.comp.id, "r1", "Top-level comment")
        reply = self.db.add_comment(self.comp.id, "r2", "I agree!",
                                     parent_id=parent["id"])
        assert reply["parent_id"] == parent["id"]
        comments = self.db.list_comments(self.comp.id)
        assert len(comments) == 2
        replies = [c for c in comments if c["parent_id"] is not None]
        assert len(replies) == 1

    def test_resolve_comment(self):
        c = self.db.add_comment(self.comp.id, "r1", "Needs work")
        updated = self.db.update_comment(c["id"], is_resolved=True)
        assert updated["is_resolved"]  # SQLite stores as 0/1

    def test_update_comment_body(self):
        c = self.db.add_comment(self.comp.id, "r1", "Original text")
        updated = self.db.update_comment(c["id"], body="Edited text")
        assert updated["body"] == "Edited text"

    def test_delete_comment(self):
        c = self.db.add_comment(self.comp.id, "r1", "To be deleted")
        self.db.delete_comment(c["id"])
        comments = self.db.list_comments(self.comp.id)
        assert len(comments) == 0

    def test_get_comment(self):
        c = self.db.add_comment(self.comp.id, "r1", "Fetch me")
        fetched = self.db.get_comment(c["id"])
        assert fetched is not None
        assert fetched["body"] == "Fetch me"

    def test_get_nonexistent_comment(self):
        result = self.db.get_comment("nonexistent-id")
        assert result is None


# ── Collaboration: Review Assignments ────────────────────────────────────────

class TestReviewAssignments:
    def setup_method(self):
        self.db, self.wf, self.run, self.ba, self.bb, self.comp = _db_with_comparison()
        self.er = self.db.create_eval_run(
            self.wf.id, "test-eval",
            branch_a_config={"model": "gpt-4o-mini"},
            branch_b_config={"model": "gpt-4o"},
        )

    def test_assign_review(self):
        a = self.db.assign_review(self.er.id, self.comp.id, "reviewer-1",
                                   assigned_by="admin", notes="Priority review")
        assert a["id"]
        assert a["reviewer_id"] == "reviewer-1"
        assert a["comparison_id"] == self.comp.id
        assert a["status"] == "pending"
        assert a["notes"] == "Priority review"

    def test_update_assignment_status(self):
        a = self.db.assign_review(self.er.id, self.comp.id, "reviewer-1")
        updated = self.db.update_assignment_status(a["id"], "in_progress")
        assert updated["status"] == "in_progress"

        completed = self.db.update_assignment_status(a["id"], "completed", notes="Done")
        assert completed["status"] == "completed"
        assert completed["notes"] == "Done"

    def test_list_assignments_by_reviewer(self):
        self.db.assign_review(self.er.id, self.comp.id, "reviewer-1")
        assignments = self.db.list_assignments(reviewer_id="reviewer-1")
        assert len(assignments) >= 1
        assert any(a["reviewer_id"] == "reviewer-1" for a in assignments)

    def test_list_assignments_by_status(self):
        self.db.assign_review(self.er.id, self.comp.id, "reviewer-1")
        pending = self.db.list_assignments(status="pending")
        assert len(pending) >= 1

    def test_bulk_assign_reviews(self):
        results = self.db.bulk_assign_reviews(self.er.id, ["rev-1", "rev-2"],
                                               assigned_by="admin")
        # At least returns a list (may be empty if no unassigned comparisons in eval run)
        assert isinstance(results, list)

    def test_get_review_queue(self):
        self.db.assign_review(self.er.id, self.comp.id, "queue-reviewer")
        queue = self.db.get_review_queue("queue-reviewer")
        assert isinstance(queue, list)

    def test_review_stats(self):
        self.db.assign_review(self.er.id, self.comp.id, "reviewer-stats")
        stats = self.db.get_review_stats(self.er.id)
        assert isinstance(stats, dict)

    def test_get_assignment(self):
        a = self.db.assign_review(self.er.id, self.comp.id, "reviewer-get")
        fetched = self.db.get_assignment(a["id"])
        assert fetched is not None
        assert fetched["reviewer_id"] == "reviewer-get"


# ── DPO Export Enhancements ──────────────────────────────────────────────────

class TestDPOExport:
    def setup_method(self):
        self.db, self.wf, self.run, self.ba, self.bb, self.comp = _db_with_comparison()

    def test_export_dpo_jsonl_basic(self):
        from core.models import DecisionChoice, ConfidenceLevel
        self.db.create_decision(
            comparison_id=self.comp.id, run_id=self.run.id, workflow_id=self.wf.id,
            reviewer_id="test-reviewer", choice=DecisionChoice.BRANCH_A,
            confidence=ConfidenceLevel.HIGH,
            rationale_for_choice="A is better",
            rationale_for_rejection="B is worse",
            branch_winner_id=self.ba.id, branch_loser_id=self.bb.id,
        )
        result = self.db.export_dpo_jsonl(self.wf.id)
        assert result is not None

    def test_export_dpo_with_filters(self):
        from core.models import DecisionChoice, ConfidenceLevel
        self.db.create_decision(
            comparison_id=self.comp.id, run_id=self.run.id, workflow_id=self.wf.id,
            reviewer_id="test-reviewer", choice=DecisionChoice.BRANCH_A,
            confidence=ConfidenceLevel.HIGH,
            rationale_for_choice="A is better",
            rationale_for_rejection="B is worse",
            branch_winner_id=self.ba.id, branch_loser_id=self.bb.id,
        )
        result = self.db.export_dpo_jsonl(self.wf.id, min_confidence="high")
        assert result is not None


# ── Observability Module ─────────────────────────────────────────────────────

class TestObservability:
    def test_metrics_singleton(self):
        from core.observability import get_metrics
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_counter_increment(self):
        from core.observability import get_metrics
        m = get_metrics()
        initial = m.get_counter("test_counter_incr_nf")
        m.inc("test_counter_incr_nf")
        m.inc("test_counter_incr_nf")
        assert m.get_counter("test_counter_incr_nf") == initial + 2

    def test_counter_with_labels(self):
        from core.observability import get_metrics
        m = get_metrics()
        m.inc("labeled_counter_nf", {"method": "GET", "status": "200"})
        m.inc("labeled_counter_nf", {"method": "POST", "status": "201"})
        assert m.get_counter("labeled_counter_nf", {"method": "GET", "status": "200"}) >= 1

    def test_histogram_observe(self):
        from core.observability import get_metrics
        m = get_metrics()
        for v in [100, 200, 300, 400, 500]:
            m.observe("test_histogram_obs_nf", v)
        avg = m.get_histogram_avg("test_histogram_obs_nf")
        assert 200 <= avg <= 400
        p95 = m.get_histogram_p95("test_histogram_obs_nf")
        assert p95 >= 400

    def test_snapshot(self):
        from core.observability import get_metrics
        m = get_metrics()
        m.inc("snapshot_test_counter_nf")
        m.observe("snapshot_test_hist_nf", 42.0)
        snap = m.snapshot()
        assert "counters" in snap
        assert "histograms" in snap

    def test_noop_tracer(self):
        from core.observability import _NoOpTracer, _NoOpSpan
        tracer = _NoOpTracer()
        span = tracer.start_as_current_span("test")
        assert isinstance(span, _NoOpSpan)
        span.set_attribute("key", "value")
        span.end()

    def test_noop_span_context_manager(self):
        from core.observability import _NoOpSpan
        span = _NoOpSpan()
        with span as s:
            s.set_attribute("foo", "bar")
            s.record_exception(Exception("test"))

    def test_get_tracer_without_otel(self):
        from core.observability import get_tracer
        tracer = get_tracer("test")
        span = tracer.start_as_current_span("test-span")
        span.set_attribute("k", "v")

    def test_trace_llm_call(self):
        from core.observability import trace_llm_call
        trace_llm_call(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            output="hello",
            latency_ms=100, tokens_in=5, tokens_out=3,
        )

    def test_trace_eval_run(self):
        from core.observability import trace_eval_run
        trace_eval_run(
            eval_run_id="er-1", workflow_id="wf-1",
            evaluator_names=["pairwise_preference"],
            total_comparisons=10, duration_ms=5000,
        )

    def test_trace_scoring(self):
        from core.observability import trace_scoring
        trace_scoring(
            comparison_id="c-1", scorer_name="lexical",
            score=0.45, latency_ms=50,
        )


# ── SDK Versioning ───────────────────────────────────────────────────────────

class TestSDKVersioning:
    def test_version_defined(self):
        from sdk.forkmark import __version__
        assert __version__
        assert isinstance(__version__, str)
        parts = __version__.split(".")
        assert len(parts) >= 2

    def test_setup_py_version_sourced(self):
        setup_path = Path(__file__).parent.parent / "sdk" / "setup.py"
        if setup_path.exists():
            content = setup_path.read_text()
            assert "version" in content


# ── Anthropic Wrapper ────────────────────────────────────────────────────────

class TestAnthropicWrapper:
    def test_import(self):
        from sdk.forkmark import ForkmarkAnthropic
        assert ForkmarkAnthropic is not None

    def test_to_fm_messages_string_content(self):
        from sdk.forkmark.integrations.anthropic_wrapper import _to_fm_messages
        msgs = _to_fm_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ])
        assert len(msgs) == 2
        assert msgs[0]["content"] == "Hello"
        assert msgs[1]["content"] == "Hi there"

    def test_to_fm_messages_block_content(self):
        from sdk.forkmark.integrations.anthropic_wrapper import _to_fm_messages
        msgs = _to_fm_messages([
            {"role": "assistant", "content": [{"type": "text", "text": "Block text"}]},
        ])
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Block text"

    def test_to_fm_messages_with_system(self):
        from sdk.forkmark.integrations.anthropic_wrapper import _to_fm_messages
        msgs = _to_fm_messages(
            [{"role": "user", "content": "Hello"}],
            system="You are helpful"
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are helpful"


# ── OpenAI Wrapper Enhancements ──────────────────────────────────────────────

class TestOpenAIWrapperEnhancements:
    def test_import_wrapper(self):
        from sdk.forkmark.integrations.openai_wrapper import ForkmarkOpenAI
        assert ForkmarkOpenAI is not None

    def test_stream_wrapper_exists(self):
        from sdk.forkmark.integrations.openai_wrapper import _StreamWrapper
        assert _StreamWrapper is not None

    def test_async_stream_wrapper_exists(self):
        from sdk.forkmark.integrations.openai_wrapper import _AsyncStreamWrapper
        assert _AsyncStreamWrapper is not None


# ── API Endpoint Tests ───────────────────────────────────────────────────────

class TestAPIEndpoints:
    """Test endpoints via FastAPI TestClient."""

    def setup_method(self):
        os.environ["FM_DB_PATH"] = ":memory:"
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"
        # Reload modules to get fresh DB
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith(("core.store", "backend.main", "config")):
                importlib.reload(sys.modules[mod_name])

        from backend.main import app
        from fastapi.testclient import TestClient
        self.client = TestClient(app)

    def test_healthz(self):
        resp = self.client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.skipif(
        os.environ.get("FM_ENTERPRISE_MODE", "").lower() not in ("true", "1", "yes"),
        reason="/metrics is enterprise-only (requires FM_ENTERPRISE_MODE=true)"
    )
    def test_metrics_endpoint(self):
        resp = self.client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "counters" in data
        assert "histograms" in data

    def test_workflow_crud(self):
        resp = self.client.post("/api/workflows", json={"name": "test-wf"})
        assert resp.status_code == 201
        wf = resp.json()
        assert wf["name"] == "test-wf"

        resp = self.client.get("/api/workflows")
        assert resp.status_code == 200


# ── Migration v6 Tests ───────────────────────────────────────────────────────

class TestMigrationV6:
    """Verify that migration v6 creates the collaboration tables."""

    def setup_method(self):
        self.db = _fresh_db()

    def test_comments_table_exists(self):
        with self.db._conn() as c:
            result = c.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='comments'"
            )
            assert result is not None, "comments table should exist after migration"

    def test_review_assignments_table_exists(self):
        with self.db._conn() as c:
            result = c.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='review_assignments'"
            )
            assert result is not None, "review_assignments table should exist after migration"

    def test_comparison_has_review_status_column(self):
        with self.db._conn() as c:
            rows = c.fetchall("PRAGMA table_info(comparisons)")
            columns = [row[1] if isinstance(row, (list, tuple)) else row["name"] for row in rows]
            assert "review_status" in columns

    def test_comparison_has_assigned_to_column(self):
        with self.db._conn() as c:
            rows = c.fetchall("PRAGMA table_info(comparisons)")
            columns = [row[1] if isinstance(row, (list, tuple)) else row["name"] for row in rows]
            assert "assigned_to" in columns


# ── Evaluator Registry ───────────────────────────────────────────────────────

class TestEvaluators:
    def test_builtin_evaluators_registered(self):
        """All documented built-in evaluators should be in the registry."""
        from core.evaluators import _REGISTRY
        builtins = ["json_schema", "regex_match", "exact_match", "contains",
                     "max_length", "latency_check", "faithfulness", "relevance", "toxicity"]
        for name in builtins:
            assert name in _REGISTRY, f"Built-in evaluator '{name}' should be registered"

    def test_custom_evaluator_registration(self):
        from core.evaluators import register_evaluator, _REGISTRY

        def my_eval(output, config, context=None):
            return {"pass": True, "score": 1.0}

        register_evaluator("test_custom_eval_nf", my_eval)
        assert "test_custom_eval_nf" in _REGISTRY

    def test_run_evaluators(self):
        """run_evaluators should execute and return results."""
        import asyncio
        from core.evaluators import run_evaluators
        # Evaluators receive the full config dict — params are top-level keys
        results = asyncio.get_event_loop().run_until_complete(
            run_evaluators("the answer is positive", [
                {"name": "exact_match", "expected": "the answer is positive"},
                {"name": "contains", "substring": "positive"},
            ])
        )
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
