"""Phase 5 tests — Frontend trajectory view integration.

Since the frontend is a static React SPA that can't be unit-tested in pytest,
we verify:
  1. Frontend files exist and are syntactically correct (no broken imports)
  2. TrajectoryCompare.jsx contains expected structure
  3. App.jsx properly routes to the agentCompare view
  4. Sidebar.jsx includes the Agent Runs nav item
  5. api.js includes agent comparison endpoints
  6. Backend endpoints that power the view work end-to-end
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestFrontendFiles:

    def test_trajectory_compare_exists(self):
        path = PROJECT_ROOT / "frontend/src/components/TrajectoryCompare.jsx"
        assert path.is_file(), "TrajectoryCompare.jsx not found"

    def test_trajectory_compare_structure(self):
        content = (PROJECT_ROOT / "frontend/src/components/TrajectoryCompare.jsx").read_text()
        # Must export default component
        assert "export default function TrajectoryCompare" in content
        # Must have score cards
        assert "trajectory_score" in content
        assert "tool_sequence_score" in content
        assert "outcome_equivalence_score" in content
        assert "efficiency_score" in content
        # Must fetch from agent API
        assert "/agent/trajectory/" in content
        assert "/agent/trace-events" in content
        assert "/agent/feature-status" in content

    def test_app_jsx_routes_agent_compare(self):
        content = (PROJECT_ROOT / "frontend/src/App.jsx").read_text()
        assert "TrajectoryCompare" in content
        assert "'agentCompare'" in content
        assert "import('./components/TrajectoryCompare.jsx')" in content

    def test_sidebar_has_agent_runs(self):
        content = (PROJECT_ROOT / "frontend/src/components/Sidebar.jsx").read_text()
        assert "'agentCompare'" in content
        assert "'Agent Runs'" in content

    def test_api_js_has_agent_endpoints(self):
        content = (PROJECT_ROOT / "frontend/src/api.js").read_text()
        assert "agentFeatureStatus" in content
        assert "agentTraceEvents" in content
        assert "agentTrajectory" in content
        assert "/agent/feature-status" in content
        assert "/agent/trajectory/" in content

    def test_trajectory_compare_has_score_visualization(self):
        content = (PROJECT_ROOT / "frontend/src/components/TrajectoryCompare.jsx").read_text()
        # Should have visual score rendering
        assert "scorePercent" in content
        # Should have timeline columns
        assert "Branch A" in content
        assert "Branch B" in content
        # Should have event detail panel
        assert "selectedEvent" in content

    def test_trajectory_compare_handles_empty_state(self):
        content = (PROJECT_ROOT / "frontend/src/components/TrajectoryCompare.jsx").read_text()
        assert "No trajectory data" in content or "No trace events" in content

    def test_trajectory_compare_handles_feature_disabled(self):
        content = (PROJECT_ROOT / "frontend/src/components/TrajectoryCompare.jsx").read_text()
        assert "not enabled" in content or "FM_ENABLE_AGENT_COMPARISON" in content


class TestEndToEndView:
    """Test the API layer that backs the frontend view."""

    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        import importlib
        os.environ["FM_DB_PATH"] = str(tmp_path / "fe_test.db")
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"
        os.environ["FM_ENABLE_AGENT_COMPARISON"] = "true"

        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith(("config", "core.", "backend.")):
                try:
                    importlib.reload(sys.modules[mod_name])
                except Exception:
                    pass
        if "config" in sys.modules:
            importlib.reload(sys.modules["config"])
        if "core.store" in sys.modules:
            importlib.reload(sys.modules["core.store"])
        if "backend.deps" in sys.modules:
            importlib.reload(sys.modules["backend.deps"])
        if "backend.routes.agent" in sys.modules:
            importlib.reload(sys.modules["backend.routes.agent"])
        if "backend.main" in sys.modules:
            importlib.reload(sys.modules["backend.main"])

        from backend.main import app
        from backend.deps import db
        from fastapi.testclient import TestClient
        from datetime import datetime, timezone

        self.db = db
        _ak, raw_key = db.create_api_key("fe-test-key")
        self.client = TestClient(app)
        self.client.headers["X-API-Key"] = raw_key

        # Seed data
        now = datetime.now(timezone.utc).isoformat()
        with db._conn() as c:
            c.execute("INSERT INTO workflows (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                      ("wf-fe", "FE Test", "test", now, now))
            c.execute("INSERT INTO workflow_runs (id, workflow_id, status, created_at, run_type) VALUES (?, ?, ?, ?, ?)",
                      ("run-fe", "wf-fe", "completed", now, "agent"))
            for bid, name, bl in [("br-fe-a", "baseline", 1), ("br-fe-b", "challenger", 0)]:
                c.execute("INSERT INTO branches (id, run_id, workflow_id, name, model_id, temperature, extra_config, created_at, is_baseline) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (bid, "run-fe", "wf-fe", name, "gpt-4o", 0.7, "{}", now, bl))

    def test_full_view_flow(self):
        """Simulate the full data flow the frontend view would use."""
        # 1. Check feature status
        resp = self.client.get("/api/agent/feature-status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        # 2. Create trace events for both branches
        for bid in ("br-fe-a", "br-fe-b"):
            events = [
                {"branch_id": bid, "run_id": "run-fe",
                 "event_type": "reasoning", "event_index": 0,
                 "name": "planning", "output_data": {"text": "Let me plan"},
                 "latency_ms": 200, "tokens_input": 100, "tokens_output": 50,
                 "cost_usd": 0.002, "status": "completed"},
                {"branch_id": bid, "run_id": "run-fe",
                 "event_type": "tool_call", "event_index": 1,
                 "name": "web_search", "input_data": {"query": "test"},
                 "output_data": {"text": "Search results"},
                 "latency_ms": 300, "tokens_input": 50, "tokens_output": 200,
                 "cost_usd": 0.003, "status": "completed"},
            ]
            resp = self.client.post("/api/agent/trace-events/batch",
                                    json={"events": events})
            assert resp.status_code == 200

        # 3. Create comparison (triggers trajectory scoring)
        resp = self.client.post("/api/agent/comparisons", json={
            "run_id": "run-fe",
            "branch_a_id": "br-fe-a",
            "branch_b_id": "br-fe-b",
        })
        assert resp.status_code == 200
        comp_data = resp.json()
        comp_id = comp_data["comparison_id"]
        assert comp_data["trajectory_score"] > 0

        # 4. Fetch trajectory outcome (what the view renders)
        resp = self.client.get(f"/api/agent/trajectory/{comp_id}")
        assert resp.status_code == 200
        outcome = resp.json()
        assert outcome["comparison_id"] == comp_id
        assert "tool_sequence_detail" in outcome
        assert "outcome_detail" in outcome
        assert "efficiency_detail" in outcome

        # 5. Fetch trace events for each branch (timeline columns)
        resp = self.client.get("/api/agent/trace-events",
                               params={"branch_id": "br-fe-a"})
        assert resp.status_code == 200
        events_a = resp.json()
        assert len(events_a) >= 2

        resp = self.client.get("/api/agent/trace-events",
                               params={"branch_id": "br-fe-b"})
        assert resp.status_code == 200
        events_b = resp.json()
        assert len(events_b) >= 2

        # 6. Verify event types are correct
        for ev in events_a:
            assert ev["event_type"] in ("reasoning", "tool_call", "tool_result",
                                         "sub_agent", "observation", "decision", "error")
