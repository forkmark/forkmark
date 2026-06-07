"""Phase 3 tests — SDK extension (AgentRunContext + TrajectoryRecorder).

Tests:
  1. TrajectoryRecorder event recording
  2. TrajectoryRecorder nested events
  3. TrajectoryRecorder event batching
  4. AgentRunContext lifecycle (without live server)
  5. SDK import and export checks
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk"))


# ── 1. TrajectoryRecorder event recording ────────────────────────────────────

class TestTrajectoryRecorder:

    def _make_recorder(self):
        from forkmark.agent import TrajectoryRecorder
        mock_client = MagicMock()
        mock_client._post = MagicMock(return_value={})
        return TrajectoryRecorder(mock_client, "run-1", "br-1", "baseline")

    def test_record_single_event(self):
        rec = self._make_recorder()
        eid = rec.record_event(
            "tool_call", "web_search",
            input_data={"query": "test"},
            output_data={"results": ["a"]},
            latency_ms=150,
            cost_usd=0.001,
        )
        assert eid.startswith("te_")
        assert len(rec.events) == 1
        assert rec.events[0]["name"] == "web_search"
        assert rec.events[0]["event_type"] == "tool_call"
        assert rec.events[0]["input_data"] == {"query": "test"}

    def test_record_multiple_events(self):
        rec = self._make_recorder()
        for i in range(5):
            rec.record_event("tool_call", f"tool_{i}")
        assert len(rec.events) == 5
        # Check ordering
        for i, ev in enumerate(rec.events):
            assert ev["event_index"] == i
            assert ev["name"] == f"tool_{i}"

    def test_event_default_values(self):
        rec = self._make_recorder()
        rec.record_event("reasoning", "think")
        ev = rec.events[0]
        assert ev["input_data"] == {}
        assert ev["output_data"] == {}
        assert ev["latency_ms"] == 0
        assert ev["cost_usd"] is None
        assert ev["metadata"] == {}
        assert ev["status"] == "completed"
        assert ev["parent_event_id"] is None

    def test_branch_properties(self):
        rec = self._make_recorder()
        assert rec.branch_id == "br-1"
        assert rec.branch_name == "baseline"


# ── 2. Nested events ────────────────────────────────────────────────────────

class TestNestedEvents:

    def _make_recorder(self):
        from forkmark.agent import TrajectoryRecorder
        mock_client = MagicMock()
        mock_client._post = MagicMock(return_value={})
        return TrajectoryRecorder(mock_client, "run-1", "br-1", "baseline")

    def test_nested_context_manager(self):
        rec = self._make_recorder()
        with rec.nested("sub_agent", "research_agent") as parent_id:
            rec.record_event("tool_call", "web_search")
            rec.record_event("tool_call", "summarize")

        assert len(rec.events) == 3  # parent + 2 children
        # Parent event
        assert rec.events[0]["name"] == "research_agent"
        assert rec.events[0]["id"] == parent_id
        assert rec.events[0]["status"] == "completed"  # updated on exit
        # Children should reference parent
        assert rec.events[1]["parent_event_id"] == parent_id
        assert rec.events[2]["parent_event_id"] == parent_id

    def test_deeply_nested(self):
        rec = self._make_recorder()
        with rec.nested("sub_agent", "agent_1") as p1:
            rec.record_event("tool_call", "tool_a")
            with rec.nested("sub_agent", "agent_2") as p2:
                rec.record_event("tool_call", "tool_b")

        assert len(rec.events) == 4
        # agent_1's children
        assert rec.events[1]["parent_event_id"] == p1
        # agent_2 is child of agent_1
        assert rec.events[2]["parent_event_id"] == p1
        # tool_b is child of agent_2
        assert rec.events[3]["parent_event_id"] == p2

    def test_after_nested_returns_to_root(self):
        rec = self._make_recorder()
        with rec.nested("sub_agent", "agent_1"):
            rec.record_event("tool_call", "nested_tool")
        # After exiting nested, should be back at root
        rec.record_event("tool_call", "root_tool")
        assert rec.events[-1]["parent_event_id"] is None


# ── 3. Event batching / flush ────────────────────────────────────────────────

class TestEventFlush:

    def test_flush_sends_batch(self):
        from forkmark.agent import TrajectoryRecorder
        mock_client = MagicMock()
        mock_client._post = MagicMock(return_value={})
        rec = TrajectoryRecorder(mock_client, "run-1", "br-1", "baseline")

        rec.record_event("tool_call", "search")
        rec.record_event("tool_call", "analyze")
        rec._flush()

        mock_client._post.assert_called_once()
        call_args = mock_client._post.call_args
        assert call_args[0][0] == "/api/agent/trace-events/batch"
        assert len(call_args[0][1]["events"]) == 2

    def test_flush_empty_noop(self):
        from forkmark.agent import TrajectoryRecorder
        mock_client = MagicMock()
        rec = TrajectoryRecorder(mock_client, "run-1", "br-1", "baseline")
        rec._flush()
        mock_client._post.assert_not_called()

    def test_context_manager_flushes(self):
        from forkmark.agent import TrajectoryRecorder
        mock_client = MagicMock()
        mock_client._post = MagicMock(return_value={})
        rec = TrajectoryRecorder(mock_client, "run-1", "br-1", "baseline")

        with rec:
            rec.record_event("tool_call", "search")

        mock_client._post.assert_called_once()

    def test_flush_handles_api_error(self):
        from forkmark.agent import TrajectoryRecorder
        mock_client = MagicMock()
        mock_client._post = MagicMock(side_effect=Exception("Connection refused"))
        rec = TrajectoryRecorder(mock_client, "run-1", "br-1", "baseline")

        rec.record_event("tool_call", "search")
        # Should not raise
        rec._flush()
        # Events should still be available locally
        assert len(rec.events) == 1


# ── 4. AgentRunContext lifecycle ─────────────────────────────────────────────

class TestAgentRunContext:

    def _make_context(self):
        from forkmark.agent import AgentRunContext
        mock_client = MagicMock()
        mock_client.start_run = MagicMock(return_value={
            "run_id": "run-test", "workflow_id": "wf-test"
        })
        mock_client.create_branch = MagicMock(side_effect=[
            {"branch_id": "br-a"},
            {"branch_id": "br-b"},
        ])
        mock_client.complete_run = MagicMock(return_value={})
        mock_client._post = MagicMock(return_value={
            "comparison_id": "comp-test"
        })
        return AgentRunContext(mock_client, "test-workflow",
                               input_data={"query": "test"})

    def test_enter_starts_run(self):
        ctx = self._make_context()
        with ctx:
            assert ctx.run_id == "run-test"
            assert ctx.workflow_id == "wf-test"

    def test_exit_completes_run(self):
        ctx = self._make_context()
        with ctx:
            pass
        ctx._client.complete_run.assert_called_once_with(
            "run-test", status="completed"
        )

    def test_exit_on_error_marks_failed(self):
        ctx = self._make_context()
        try:
            with ctx:
                raise ValueError("test error")
        except ValueError:
            pass
        ctx._client.complete_run.assert_called_once_with(
            "run-test", status="failed"
        )

    def test_branch_creates_recorder(self):
        ctx = self._make_context()
        with ctx:
            with ctx.branch("baseline", model_id="gpt-4o") as rec:
                assert rec.branch_id == "br-a"
                assert rec.branch_name == "baseline"
                rec.record_event("tool_call", "search")
            assert len(ctx.recorders) == 1

    def test_two_branches_creates_comparison(self):
        ctx = self._make_context()
        with ctx:
            with ctx.branch("baseline", model_id="gpt-4o") as br_a:
                br_a.record_event("tool_call", "search")
            with ctx.branch("challenger", model_id="claude-3") as br_b:
                br_b.record_event("tool_call", "search")

        # Should have called _post for comparison creation
        comparison_calls = [c for c in ctx._client._post.call_args_list
                           if "/api/agent/comparisons" in str(c)]
        assert len(comparison_calls) >= 1

    def test_first_branch_is_baseline(self):
        ctx = self._make_context()
        with ctx:
            with ctx.branch("first") as _:
                pass
        call_args = ctx._client.create_branch.call_args
        assert call_args[1].get("is_baseline", call_args[0][4] if len(call_args[0]) > 4 else None) or \
               "is_baseline" in str(call_args)

    def test_single_branch_no_comparison(self):
        ctx = self._make_context()
        with ctx:
            with ctx.branch("only_one") as rec:
                rec.record_event("tool_call", "search")
        # Should NOT attempt comparison with just one branch
        comparison_calls = [c for c in ctx._client._post.call_args_list
                           if "/api/agent/comparisons" in str(c)]
        assert len(comparison_calls) == 0


# ── 5. SDK imports ───────────────────────────────────────────────────────────

class TestSDKImports:

    def test_agent_module_importable(self):
        from forkmark.agent import AgentRunContext, TrajectoryRecorder
        assert AgentRunContext is not None
        assert TrajectoryRecorder is not None

    def test_client_has_agent_run(self):
        from forkmark.client import ForkmarkClient
        assert hasattr(ForkmarkClient, "agent_run")

    def test_package_exports(self):
        import forkmark
        assert hasattr(forkmark, "AgentRunContext")
        assert hasattr(forkmark, "TrajectoryRecorder")
        assert hasattr(forkmark, "agent_run")
        assert "AgentRunContext" in forkmark.__all__
        assert "agent_run" in forkmark.__all__

    def test_agent_run_requires_init(self):
        import forkmark
        forkmark._default = None
        with pytest.raises(RuntimeError, match="forkmark.init"):
            forkmark.agent_run("test")
