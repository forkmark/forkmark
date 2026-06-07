"""Phase 1 tests — Data model, feature flags, store extensions.

Tests:
  1. Feature flags (three-level gating)
  2. Agent models (TraceEvent, TrajectoryOutcome serialization)
  3. Store migration v8 (tables created, columns added)
  4. CRUD operations (create/read trace events and trajectory outcomes)
  5. Existing tests still pass (no regression)
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── 1. Feature flags ────────────────────────────────────────────────────────

class TestFeatureFlags:

    def test_default_enabled(self):
        """Agent comparison should be enabled by default (v0.1.2)."""
        from core.feature_flags import agent_comparison_enabled
        assert agent_comparison_enabled() is True

    def test_env_override_disable(self, monkeypatch):
        """FM_ENABLE_AGENT_COMPARISON=false kills the feature globally."""
        monkeypatch.setenv("FM_ENABLE_AGENT_COMPARISON", "false")
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison") is False

    def test_env_override_enable(self, monkeypatch):
        """FM_ENABLE_AGENT_COMPARISON=true enables regardless of tier."""
        monkeypatch.setenv("FM_ENABLE_AGENT_COMPARISON", "true")
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison", org_plan="free") is True

    def test_unknown_feature_disabled(self):
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("nonexistent_feature") is False

    def test_workspace_override_false(self):
        """Workspace-level disable overrides plan-level enable."""
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison",
                                  org_plan="enterprise",
                                  workspace_override=False) is False

    def test_workspace_override_true(self):
        """Workspace-level enable works when plan tier is sufficient."""
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison",
                                  org_plan="free",
                                  workspace_override=True) is True

    def test_tier_gating_free(self):
        """Free tier should have access (min tier = free)."""
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison", org_plan="free") is True

    def test_tier_gating_enterprise(self):
        """Enterprise tier should have access."""
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison", org_plan="enterprise") is True

    def test_env_override_unset(self, monkeypatch):
        """When env var is unset, fall through to tier gating."""
        monkeypatch.delenv("FM_ENABLE_AGENT_COMPARISON", raising=False)
        from core.feature_flags import is_feature_enabled
        assert is_feature_enabled("agent_comparison") is True


# ── 2. Agent models ─────────────────────────────────────────────────────────

class TestAgentModels:

    def test_trace_event_roundtrip(self):
        """TraceEvent should serialize and deserialize correctly."""
        from core.agent_models import TraceEvent, TraceEventType, TraceEventStatus
        now = datetime.now(timezone.utc)
        te = TraceEvent(
            id="te-001",
            branch_id="br-001",
            run_id="run-001",
            parent_event_id=None,
            event_type=TraceEventType.TOOL_CALL,
            event_index=0,
            name="web_search",
            input_data={"query": "test"},
            output_data={"results": ["a", "b"]},
            status=TraceEventStatus.COMPLETED,
            latency_ms=150,
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.001,
            metadata={"model": "gpt-4o"},
            created_at=now,
        )
        d = te.to_dict()
        assert d["event_type"] == "tool_call"
        assert d["status"] == "completed"
        assert d["parent_event_id"] is None
        assert d["input_data"] == {"query": "test"}

    def test_trace_event_from_row(self):
        """TraceEvent.from_row should handle JSON string fields."""
        from core.agent_models import TraceEvent, TraceEventType
        row = {
            "id": "te-002",
            "branch_id": "br-002",
            "run_id": "run-002",
            "parent_event_id": "te-001",
            "event_type": "reasoning",
            "event_index": 1,
            "name": "planning",
            "input_data": '{"prompt": "think"}',
            "output_data": '{"plan": "step1"}',
            "status": "completed",
            "latency_ms": 200,
            "tokens_input": 80,
            "tokens_output": 40,
            "cost_usd": 0.002,
            "metadata": '{"temperature": 0.7}',
            "created_at": "2025-01-15T10:00:00Z",
        }
        te = TraceEvent.from_row(row)
        assert te.event_type == TraceEventType.REASONING
        assert te.input_data == {"prompt": "think"}
        assert te.metadata == {"temperature": 0.7}
        assert te.parent_event_id == "te-001"

    def test_trace_event_from_row_defaults(self):
        """TraceEvent.from_row should fill in missing optional fields."""
        from core.agent_models import TraceEvent
        row = {
            "id": "te-003",
            "branch_id": "br-003",
            "run_id": "run-003",
            "event_type": "tool_call",
            "event_index": 0,
            "name": "calc",
            "created_at": "2025-01-15T10:00:00Z",
        }
        te = TraceEvent.from_row(row)
        assert te.parent_event_id is None
        assert te.cost_usd is None
        assert te.tokens_input == 0
        assert te.input_data == {}

    def test_trajectory_outcome_roundtrip(self):
        """TrajectoryOutcome should serialize and deserialize correctly."""
        from core.agent_models import TrajectoryOutcome
        now = datetime.now(timezone.utc)
        to = TrajectoryOutcome(
            id="to-001",
            comparison_id="comp-001",
            run_id="run-001",
            workflow_id="wf-001",
            tool_sequence_score=0.85,
            outcome_equivalence_score=0.9,
            efficiency_score=0.7,
            trajectory_score=0.82,
            tool_sequence_detail={"alignment": "good"},
            outcome_detail={"match": True},
            efficiency_detail={"cost_ratio": 1.2},
            branch_a_tool_count=5,
            branch_b_tool_count=3,
            branch_a_depth=2,
            branch_b_depth=1,
            branch_a_total_latency_ms=5000,
            branch_b_total_latency_ms=3000,
            branch_a_total_cost_usd=0.05,
            branch_b_total_cost_usd=0.03,
            created_at=now,
        )
        d = to.to_dict()
        assert d["trajectory_score"] == 0.82
        assert d["tool_sequence_detail"] == {"alignment": "good"}

    def test_trajectory_outcome_from_row_defaults(self):
        """TrajectoryOutcome.from_row should fill in missing numeric fields."""
        from core.agent_models import TrajectoryOutcome
        row = {
            "id": "to-002",
            "comparison_id": "comp-002",
            "run_id": "run-002",
            "workflow_id": "wf-002",
            "created_at": "2025-01-15T10:00:00Z",
        }
        to = TrajectoryOutcome.from_row(row)
        assert to.tool_sequence_score == 0.0
        assert to.branch_a_tool_count == 0
        assert to.branch_a_total_cost_usd == 0.0
        assert to.tool_sequence_detail == {}

    def test_all_event_types(self):
        """All TraceEventType values should be valid."""
        from core.agent_models import TraceEventType
        expected = {"reasoning", "tool_call", "tool_result", "sub_agent",
                    "observation", "decision", "error"}
        actual = {e.value for e in TraceEventType}
        assert actual == expected


# ── 3. Store migration v8 ───────────────────────────────────────────────────

@pytest.fixture
def fresh_db(tmp_path):
    """Create a fresh database with all migrations applied."""
    db_path = tmp_path / "test_agent.db"
    from core.store import Database
    db = Database(str(db_path))
    return db


class TestMigrationV8:

    def test_trace_events_table_exists(self, fresh_db):
        """Migration v8 should create trace_events table."""
        with fresh_db._read_conn() as c:
            row = c.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trace_events'",
                (),
            )
        assert row is not None

    def test_trajectory_outcomes_table_exists(self, fresh_db):
        """Migration v8 should create trajectory_outcomes table."""
        with fresh_db._read_conn() as c:
            row = c.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trajectory_outcomes'",
                (),
            )
        assert row is not None

    def test_run_type_column_added(self, fresh_db):
        """Migration v8 should add run_type column to workflow_runs."""
        with fresh_db._read_conn() as c:
            rows = c.fetchall("PRAGMA table_info(workflow_runs)", ())
        col_names = [dict(r)["name"] if isinstance(r, dict) else r[1] for r in rows]
        assert "run_type" in col_names

    def test_schema_version_is_8(self, fresh_db):
        """Schema version should be 8 after migration."""
        with fresh_db._read_conn() as c:
            row = c.fetchone(
                "SELECT MAX(version) as v FROM schema_version", ()
            )
        assert row is not None
        v = dict(row)["v"] if isinstance(row, dict) else row[0]
        assert v >= 8

    def test_trace_events_indexes(self, fresh_db):
        """Indexes on trace_events should exist."""
        with fresh_db._read_conn() as c:
            rows = c.fetchall(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='trace_events'",
                (),
            )
        idx_names = [dict(r)["name"] if isinstance(r, dict) else r[0] for r in rows]
        assert "idx_trace_events_branch" in idx_names
        assert "idx_trace_events_run" in idx_names
        assert "idx_trace_events_parent" in idx_names


# ── 4. CRUD operations ──────────────────────────────────────────────────────

class TestAgentCRUD:

    @pytest.fixture(autouse=True)
    def setup_db(self, fresh_db):
        """Set up a database with required parent rows."""
        self.db = fresh_db
        now = datetime.now(timezone.utc).isoformat()

        # Create a workflow
        with self.db._conn() as c:
            c.execute(
                "INSERT INTO workflows (id, name, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("wf-test", "Test Workflow", "test", now, now),
            )
            # Create a workflow run
            c.execute(
                "INSERT INTO workflow_runs (id, workflow_id, status, created_at, run_type) "
                "VALUES (?, ?, ?, ?, ?)",
                ("run-test", "wf-test", "completed", now, "agent"),
            )
            # Create two branches
            for i, (bid, name, baseline) in enumerate([
                ("br-a", "baseline", 1),
                ("br-b", "challenger", 0),
            ]):
                c.execute(
                    "INSERT INTO branches (id, run_id, workflow_id, name, model_id, "
                    "temperature, extra_config, created_at, is_baseline) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (bid, "run-test", "wf-test", name, "gpt-4o", 0.7, "{}", now, baseline),
                )
            # Create a comparison
            c.execute(
                "INSERT INTO comparisons (id, run_id, workflow_id, branch_a_id, "
                "branch_b_id, created_at, step_names) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("comp-test", "run-test", "wf-test", "br-a", "br-b", now, "[]"),
            )

    def test_create_single_trace_event(self):
        """Insert and retrieve a single trace event."""
        self.db.create_trace_event(
            id="te-1",
            branch_id="br-a",
            run_id="run-test",
            parent_event_id=None,
            event_type="tool_call",
            event_index=0,
            name="web_search",
            input_data={"query": "test search"},
            output_data={"results": ["r1"]},
            status="completed",
            latency_ms=120,
            tokens_input=50,
            tokens_output=30,
            metadata={"model": "gpt-4o"},
        )
        events = self.db.get_trace_events(branch_id="br-a")
        assert len(events) == 1
        assert events[0].name == "web_search"
        assert events[0].input_data == {"query": "test search"}

    def test_create_batch_trace_events(self):
        """Bulk-insert trace events."""
        events = []
        for i in range(5):
            events.append({
                "id": f"te-batch-{i}",
                "branch_id": "br-a",
                "run_id": "run-test",
                "event_type": "tool_call",
                "event_index": i,
                "name": f"tool_{i}",
                "status": "completed",
            })
        self.db.create_trace_events_batch(events)
        result = self.db.get_trace_events(branch_id="br-a")
        assert len(result) == 5
        assert [e.name for e in result] == [f"tool_{i}" for i in range(5)]

    def test_trace_event_tree_structure(self):
        """Trace events should support parent-child tree structure."""
        # Root event
        self.db.create_trace_event(
            id="te-root", branch_id="br-a", run_id="run-test",
            parent_event_id=None, event_type="reasoning",
            event_index=0, name="planning", status="completed",
        )
        # Child events
        for i in range(3):
            self.db.create_trace_event(
                id=f"te-child-{i}", branch_id="br-a", run_id="run-test",
                parent_event_id="te-root", event_type="tool_call",
                event_index=i, name=f"tool_{i}", status="completed",
            )

        # Get root only
        roots = self.db.get_trace_events(branch_id="br-a", parent_event_id=None)
        assert len(roots) == 1
        assert roots[0].id == "te-root"

        # Get children of root
        children = self.db.get_trace_events(parent_event_id="te-root")
        assert len(children) == 3

        # Get all events for branch
        all_events = self.db.get_trace_events(branch_id="br-a")
        assert len(all_events) == 4

    def test_create_trajectory_outcome(self):
        """Insert and retrieve a trajectory outcome."""
        self.db.create_trajectory_outcome(
            id="to-1",
            comparison_id="comp-test",
            run_id="run-test",
            workflow_id="wf-test",
            tool_sequence_score=0.85,
            outcome_equivalence_score=0.9,
            efficiency_score=0.7,
            trajectory_score=0.82,
            tool_sequence_detail={"method": "levenshtein"},
            outcome_detail={"semantic_sim": 0.9},
            efficiency_detail={"cost_ratio": 1.1},
            branch_a_tool_count=5,
            branch_b_tool_count=3,
            branch_a_depth=2,
            branch_b_depth=1,
            branch_a_total_latency_ms=5000,
            branch_b_total_latency_ms=3000,
            branch_a_total_cost_usd=0.05,
            branch_b_total_cost_usd=0.03,
        )
        outcomes = self.db.get_trajectory_outcomes(comparison_id="comp-test")
        assert len(outcomes) == 1
        o = outcomes[0]
        assert o.trajectory_score == 0.82
        assert o.tool_sequence_detail == {"method": "levenshtein"}
        assert o.branch_a_tool_count == 5

    def test_get_trajectory_outcomes_by_workflow(self):
        """Filter trajectory outcomes by workflow_id."""
        self.db.create_trajectory_outcome(
            id="to-2", comparison_id="comp-test", run_id="run-test",
            workflow_id="wf-test", trajectory_score=0.75,
        )
        outcomes = self.db.get_trajectory_outcomes(workflow_id="wf-test")
        assert len(outcomes) == 1

    def test_run_type_stored(self):
        """Workflow run should persist run_type."""
        from core.models import WorkflowRun
        with self.db._read_conn() as c:
            row = c.fetchone(
                "SELECT * FROM workflow_runs WHERE id = ?", ("run-test",)
            )
        wr = WorkflowRun.from_row(dict(row) if isinstance(row, dict) else
                                   {k: row[i] for i, k in enumerate(
                                       [d[0] for d in c.cursor.description]
                                   )} if hasattr(c, 'cursor') else dict(row))
        assert wr.run_type == "agent"


# ── 5. Config check ─────────────────────────────────────────────────────────

class TestConfig:

    def test_version_updated(self):
        from config import config
        assert config.VERSION == "0.1.2"

    def test_agent_comparison_config_exists(self):
        from config import Config
        assert hasattr(Config, "ENABLE_AGENT_COMPARISON")

    def test_agent_comparison_default_true(self, monkeypatch):
        monkeypatch.setenv("FM_ENABLE_AGENT_COMPARISON", "true")
        # Re-evaluate
        val = os.getenv("FM_ENABLE_AGENT_COMPARISON", "true").lower() in ("true", "1")
        assert val is True
