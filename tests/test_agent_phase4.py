"""Phase 4 tests — API endpoints (backend/routes/agent.py).

Tests:
  1. Feature status endpoint
  2. Trace event batch creation (SDK auth)
  3. Trace event listing (UI auth)
  4. Agent comparison creation with trajectory scoring
  5. Trajectory outcome retrieval
  6. Auth requirements
"""

import importlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAgentAPI:

    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        """Create a test client with a fresh isolated DB."""
        os.environ["FM_DB_PATH"] = str(tmp_path / "agent_api_test.db")
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"
        os.environ["FM_ENABLE_AGENT_COMPARISON"] = "true"

        # Force reimport to pick up new DB path
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith(("config", "core.", "backend.")):
                try:
                    importlib.reload(sys.modules[mod_name])
                except Exception:
                    pass

        # Full reload chain
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

        self.db = db
        self.app = app

        # Create API key
        _ak, raw_key = db.create_api_key("test-agent-key")
        self.raw_key = raw_key

        # Authenticated client
        self.client = TestClient(app)
        self.client.headers["X-API-Key"] = raw_key

        # Unauthenticated client
        self.no_auth_client = TestClient(app)

        # Create prerequisite data
        now = datetime.now(timezone.utc).isoformat()
        with db._conn() as c:
            c.execute(
                "INSERT INTO workflows (id, name, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("wf-test", "Agent Test", "test", now, now),
            )
            c.execute(
                "INSERT INTO workflow_runs (id, workflow_id, status, created_at, run_type) "
                "VALUES (?, ?, ?, ?, ?)",
                ("run-test", "wf-test", "completed", now, "agent"),
            )
            for bid, name, baseline in [("br-a", "baseline", 1), ("br-b", "challenger", 0)]:
                c.execute(
                    "INSERT INTO branches (id, run_id, workflow_id, name, model_id, "
                    "temperature, extra_config, created_at, is_baseline) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (bid, "run-test", "wf-test", name, "gpt-4o", 0.7, "{}", now, baseline),
                )

    # ── 1. Feature status ────────────────────────────────────────────────────

    def test_feature_status(self):
        resp = self.client.get("/api/agent/feature-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["feature"] == "agent_comparison"

    # ── 2. Trace event batch creation ────────────────────────────────────────

    def test_create_batch(self):
        events = [
            {
                "branch_id": "br-a",
                "run_id": "run-test",
                "event_type": "tool_call",
                "event_index": i,
                "name": f"tool_{i}",
                "input_data": {"arg": i},
                "output_data": {"result": f"r{i}"},
                "status": "completed",
                "latency_ms": 100 + i * 10,
                "tokens_input": 50,
                "tokens_output": 30,
                "cost_usd": 0.001,
            }
            for i in range(3)
        ]
        resp = self.client.post("/api/agent/trace-events/batch",
                                json={"events": events})
        assert resp.status_code == 200
        assert resp.json()["created"] == 3

    def test_create_empty_batch(self):
        resp = self.client.post("/api/agent/trace-events/batch",
                                json={"events": []})
        assert resp.status_code == 200
        assert resp.json()["created"] == 0

    def test_create_batch_with_nesting(self):
        root_id = f"te-root-{uuid.uuid4().hex[:6]}"
        events = [
            {
                "id": root_id,
                "branch_id": "br-b",
                "run_id": "run-test",
                "event_type": "reasoning",
                "event_index": 0,
                "name": "planning",
                "status": "completed",
            },
            {
                "branch_id": "br-b",
                "run_id": "run-test",
                "parent_event_id": root_id,
                "event_type": "tool_call",
                "event_index": 1,
                "name": "search",
                "status": "completed",
            },
        ]
        resp = self.client.post("/api/agent/trace-events/batch",
                                json={"events": events})
        assert resp.status_code == 200
        assert resp.json()["created"] == 2

    def test_batch_requires_api_key(self):
        resp = self.no_auth_client.post("/api/agent/trace-events/batch",
                                        json={"events": []})
        assert resp.status_code == 401

    # ── 3. Trace event listing ───────────────────────────────────────────────

    def test_list_by_branch(self):
        # Insert some events first
        events = [{"branch_id": "br-a", "run_id": "run-test",
                    "event_type": "tool_call", "event_index": i,
                    "name": f"list_tool_{i}", "status": "completed"}
                   for i in range(3)]
        self.client.post("/api/agent/trace-events/batch", json={"events": events})

        resp = self.client.get("/api/agent/trace-events",
                               params={"branch_id": "br-a"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_list_by_run(self):
        events = [{"branch_id": "br-a", "run_id": "run-test",
                    "event_type": "tool_call", "event_index": 0,
                    "name": "run_tool", "status": "completed"}]
        self.client.post("/api/agent/trace-events/batch", json={"events": events})

        resp = self.client.get("/api/agent/trace-events",
                               params={"run_id": "run-test"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_list_requires_filter(self):
        resp = self.client.get("/api/agent/trace-events")
        assert resp.status_code == 400

    # ── 4. Agent comparison creation ─────────────────────────────────────────

    def test_create_comparison(self):
        # Insert events for both branches
        for bid in ("br-a", "br-b"):
            events = [{"branch_id": bid, "run_id": "run-test",
                        "event_type": "tool_call", "event_index": i,
                        "name": f"tool_{i}",
                        "output_data": {"text": f"result from {bid}"},
                        "latency_ms": 100, "tokens_input": 50,
                        "tokens_output": 30, "cost_usd": 0.001,
                        "status": "completed"}
                       for i in range(2)]
            self.client.post("/api/agent/trace-events/batch", json={"events": events})

        resp = self.client.post("/api/agent/comparisons", json={
            "run_id": "run-test",
            "branch_a_id": "br-a",
            "branch_b_id": "br-b",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "comparison_id" in data
        assert "trajectory_score" in data
        for key in ("trajectory_score", "tool_sequence_score",
                    "outcome_equivalence_score", "efficiency_score"):
            assert 0.0 <= data[key] <= 1.0

    def test_comparison_requires_api_key(self):
        resp = self.no_auth_client.post("/api/agent/comparisons",
                                         json={"run_id": "run-test",
                                               "branch_a_id": "br-a",
                                               "branch_b_id": "br-b"})
        assert resp.status_code == 401

    # ── 5. Trajectory outcome retrieval ──────────────────────────────────────

    def test_get_trajectory(self):
        # Create events + comparison first
        for bid in ("br-a", "br-b"):
            events = [{"branch_id": bid, "run_id": "run-test",
                        "event_type": "tool_call", "event_index": 0,
                        "name": "tool_x",
                        "output_data": {"text": "hello"},
                        "status": "completed"}]
            self.client.post("/api/agent/trace-events/batch", json={"events": events})

        resp = self.client.post("/api/agent/comparisons", json={
            "run_id": "run-test",
            "branch_a_id": "br-a",
            "branch_b_id": "br-b",
        })
        comp_id = resp.json()["comparison_id"]

        resp = self.client.get(f"/api/agent/trajectory/{comp_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["comparison_id"] == comp_id
        assert "trajectory_score" in data
        assert "tool_sequence_detail" in data

    def test_get_nonexistent_trajectory(self):
        resp = self.client.get("/api/agent/trajectory/nonexistent-id")
        assert resp.status_code == 404
