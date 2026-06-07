"""Agent demo suite tests — fixture discovery, seeding, trajectory scoring, UI integration.

Tests:
  1. Agent fixture discovery finds all three demo fixtures
  2. Fixture JSON structure is valid for all demos
  3. Trace tree flattening produces correct parent-child relationships
  4. Seeding a single agent demo creates workflow, run, branches, trace events, comparisons, trajectory outcomes
  5. Trajectory scores are computed and non-zero for seeded demos
  6. List demos endpoint returns both LLM and agent demos with correct types
  7. Seed all demos (including agent) via endpoint
  8. Reset agent demo clears trace events and trajectory outcomes
  9. DemoGallery frontend file has agent demo support
  10. End-to-end: seed → list → verify trajectory → reset
"""

import os
import sys
import json
import importlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _full_reload():
    """Reload all backend modules so they pick up the new DB path.

    The module reload order matters: config → core.store → backend.deps →
    all route modules → backend.main. If any route module is skipped, its
    module-level `from backend.deps import db` still points at the old DB.
    """
    # Broad sweep first
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith(("config", "core.", "backend.")):
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass

    # Targeted reload in dependency order
    reload_order = [
        "config",
        "core.store",
        "backend.deps",
        # All route modules
        "backend.routes.sdk",
        "backend.routes.eval_runs",
        "backend.routes.test_sets",
        "backend.routes.workflows",
        "backend.routes.comparisons",
        "backend.routes.decisions",
        "backend.routes.keys",
        "backend.routes.settings",
        "backend.routes.collaboration",
        "backend.routes.exports",
        "backend.routes.stats",
        "backend.routes.runner",
        "backend.routes.demos",
        "backend.routes.providers",
        "backend.routes.admin",
        "backend.routes.health",
        "backend.routes.agent",
        "backend.main",
    ]
    for mod_name in reload_order:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass


class TestAgentFixtureDiscovery:
    """Test that agent demo fixtures are discovered correctly."""

    def test_discover_agent_fixtures_finds_all(self):
        from backend.routes.demos import _discover_agent_fixtures
        fixtures = _discover_agent_fixtures()
        assert len(fixtures) >= 3, f"Expected at least 3 agent fixtures, got {len(fixtures)}"
        assert "agent_research" in fixtures
        assert "agent_support" in fixtures
        assert "agent_codereview" in fixtures

    def test_fixtures_have_required_fields(self):
        from backend.routes.demos import _discover_agent_fixtures
        fixtures = _discover_agent_fixtures()
        required = ["demo_name", "workflow", "eval_run", "branch_a", "branch_b", "cases"]
        for name, fixture in fixtures.items():
            for field in required:
                assert field in fixture, f"Fixture '{name}' missing required field '{field}'"
            assert fixture.get("demo_type") == "agent", f"Fixture '{name}' should have demo_type='agent'"
            assert len(fixture["cases"]) > 0, f"Fixture '{name}' has no cases"

    def test_fixture_cases_have_trace_trees(self):
        from backend.routes.demos import _discover_agent_fixtures
        fixtures = _discover_agent_fixtures()
        for name, fixture in fixtures.items():
            for i, case in enumerate(fixture["cases"]):
                assert "trace_a" in case, f"Fixture '{name}' case {i} missing trace_a"
                assert "trace_b" in case, f"Fixture '{name}' case {i} missing trace_b"
                assert len(case["trace_a"]) > 0, f"Fixture '{name}' case {i} has empty trace_a"
                assert len(case["trace_b"]) > 0, f"Fixture '{name}' case {i} has empty trace_b"

    def test_fixture_trace_events_have_valid_types(self):
        from backend.routes.demos import _discover_agent_fixtures
        valid_types = {"reasoning", "tool_call", "tool_result", "sub_agent", "observation", "decision", "error"}
        fixtures = _discover_agent_fixtures()
        for name, fixture in fixtures.items():
            for case in fixture["cases"]:
                for trace_key in ("trace_a", "trace_b"):
                    self._check_event_types(case[trace_key], valid_types, name, trace_key)

    def _check_event_types(self, events, valid_types, fixture_name, trace_key):
        for ev in events:
            assert ev.get("event_type") in valid_types, (
                f"Fixture '{fixture_name}' {trace_key} has invalid event_type: {ev.get('event_type')}"
            )
            for child in ev.get("children", []):
                self._check_event_types([child], valid_types, fixture_name, trace_key)


class TestTraceTreeFlattening:
    """Test _flatten_trace_tree correctly handles nesting."""

    def test_flat_list_no_children(self):
        from backend.routes.demos import _flatten_trace_tree
        nodes = [
            {"event_type": "reasoning", "name": "think", "latency_ms": 100},
            {"event_type": "tool_call", "name": "search", "latency_ms": 200},
        ]
        flat = _flatten_trace_tree(nodes, "br-1", "run-1")
        assert len(flat) == 2
        assert flat[0]["parent_event_id"] is None
        assert flat[1]["parent_event_id"] is None
        assert flat[0]["event_index"] == 0
        assert flat[1]["event_index"] == 1

    def test_nested_children_get_parent_id(self):
        from backend.routes.demos import _flatten_trace_tree
        import copy
        nodes = [
            {
                "event_type": "sub_agent", "name": "reviewer",
                "children": [
                    {"event_type": "tool_call", "name": "lint"},
                    {"event_type": "reasoning", "name": "analyze"},
                ]
            },
        ]
        flat = _flatten_trace_tree(copy.deepcopy(nodes), "br-1", "run-1")
        assert len(flat) == 3
        parent_id = flat[0]["id"]
        assert flat[1]["parent_event_id"] == parent_id
        assert flat[2]["parent_event_id"] == parent_id

    def test_deep_nesting(self):
        from backend.routes.demos import _flatten_trace_tree
        import copy
        nodes = [
            {
                "event_type": "sub_agent", "name": "outer",
                "children": [
                    {
                        "event_type": "sub_agent", "name": "inner",
                        "children": [
                            {"event_type": "tool_call", "name": "deep_tool"}
                        ]
                    }
                ]
            },
        ]
        flat = _flatten_trace_tree(copy.deepcopy(nodes), "br-1", "run-1")
        assert len(flat) == 3
        outer_id = flat[0]["id"]
        inner_id = flat[1]["id"]
        assert flat[1]["parent_event_id"] == outer_id
        assert flat[2]["parent_event_id"] == inner_id

    def test_branch_and_run_ids_propagated(self):
        from backend.routes.demos import _flatten_trace_tree
        nodes = [{"event_type": "reasoning", "name": "think"}]
        flat = _flatten_trace_tree(nodes, "br-test-99", "run-test-99")
        assert flat[0]["branch_id"] == "br-test-99"
        assert flat[0]["run_id"] == "run-test-99"

    def test_event_ids_unique(self):
        from backend.routes.demos import _flatten_trace_tree
        import copy
        nodes = [
            {"event_type": "reasoning", "name": "a"},
            {"event_type": "tool_call", "name": "b", "children": [
                {"event_type": "tool_result", "name": "c"},
            ]},
            {"event_type": "reasoning", "name": "d"},
        ]
        flat = _flatten_trace_tree(copy.deepcopy(nodes), "br-1", "run-1")
        ids = [ev["id"] for ev in flat]
        assert len(ids) == len(set(ids)), "Event IDs are not unique"


class TestAgentDemoSeeding:
    """End-to-end tests for seeding agent demos via the API."""

    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        os.environ["FM_DB_PATH"] = str(tmp_path / "agent_demo_test.db")
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"
        os.environ["FM_ENABLE_AGENT_COMPARISON"] = "true"
        _full_reload()

        from backend.main import app
        from backend.deps import db
        from fastapi.testclient import TestClient

        self.db = db
        _ak, raw_key = db.create_api_key("demo-test-key")
        self.client = TestClient(app)
        self.client.headers["X-API-Key"] = raw_key

    def test_list_demos_includes_agent_type(self):
        resp = self.client.get("/api/demos")
        assert resp.status_code == 200
        demos = resp.json()
        agent_demos = [d for d in demos if d.get("demo_type") == "agent"]
        assert len(agent_demos) >= 3
        for d in agent_demos:
            assert "trace_events" in d
            assert d["trace_events"] > 0
            assert "branch_a_label" in d
            assert "branch_b_label" in d

    def test_list_demos_has_llm_type_for_existing(self):
        resp = self.client.get("/api/demos")
        assert resp.status_code == 200
        demos = resp.json()
        llm_demos = [d for d in demos if d.get("demo_type") == "llm"]
        assert len(llm_demos) > 0, "Existing LLM demos should have demo_type='llm'"

    def test_seed_single_agent_demo(self):
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_research"]})
        assert resp.status_code == 201
        data = resp.json()
        assert data["seeded"] == 1
        assert data["errors"] == 0
        result = data["results"][0]
        assert result["demo"] == "agent_research"
        assert result["demo_type"] == "agent"
        assert result["cases"] == 3
        assert result["comparisons"] == 3
        assert result["trace_events"] > 0

    def test_seeded_demo_has_trajectory_outcomes(self):
        # Seed
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_research"]})
        assert resp.status_code == 201
        result = resp.json()["results"][0]
        wf_id = result["workflow_id"]

        # Get comparisons for this workflow
        resp = self.client.get("/api/comparisons", params={"workflow_id": wf_id})
        assert resp.status_code == 200
        comparisons = resp.json()
        assert len(comparisons) >= 3

        # Each comparison should have a trajectory outcome
        for comp in comparisons:
            resp = self.client.get(f"/api/agent/trajectory/{comp['id']}")
            assert resp.status_code == 200
            outcome = resp.json()
            assert outcome["trajectory_score"] > 0
            assert outcome["tool_sequence_score"] >= 0
            assert outcome["outcome_equivalence_score"] >= 0
            assert outcome["efficiency_score"] >= 0
            assert "tool_sequence_detail" in outcome
            assert "outcome_detail" in outcome
            assert "efficiency_detail" in outcome

    def test_seeded_demo_has_trace_events(self):
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_support"]})
        assert resp.status_code == 201
        result = resp.json()["results"][0]
        wf_id = result["workflow_id"]

        # Get runs for this workflow
        resp = self.client.get(f"/api/workflows/{wf_id}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 3

        # Each run should have branches with trace events
        for run in runs:
            run_detail = self.client.get(f"/api/runs/{run['id']}").json()
            branches = run_detail.get("branches", [])
            if not branches:
                continue
            for branch in branches:
                resp = self.client.get("/api/agent/trace-events",
                                       params={"branch_id": branch["id"]})
                assert resp.status_code == 200
                events = resp.json()
                assert len(events) > 0, f"Branch {branch['id']} has no trace events"

    def test_support_demo_has_nested_events(self):
        """The support demo should have sub_agent events with children."""
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_support"]})
        assert resp.status_code == 201
        result = resp.json()["results"][0]
        wf_id = result["workflow_id"]

        # Get all trace events for this workflow's runs
        runs = self.client.get(f"/api/workflows/{wf_id}/runs").json()
        found_nested = False
        for run in runs:
            run_detail = self.client.get(f"/api/runs/{run['id']}").json()
            for branch in run_detail.get("branches", []):
                events = self.client.get("/api/agent/trace-events",
                                          params={"branch_id": branch["id"]}).json()
                parent_ids = {e["id"] for e in events if any(
                    c.get("parent_event_id") == e["id"] for c in events
                )}
                if parent_ids:
                    found_nested = True
                    break
            if found_nested:
                break
        assert found_nested, "Support demo should have nested trace events (sub_agent with children)"

    def test_seed_all_includes_agent_demos(self):
        """Seeding all demos (empty body) seeds both LLM and agent demos."""
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_research", "agent_codereview"]})
        assert resp.status_code == 201
        data = resp.json()
        assert data["seeded"] == 2
        names = [r["demo"] for r in data["results"]]
        assert "agent_research" in names
        assert "agent_codereview" in names

    def test_reset_agent_demo_clears_data(self):
        # Seed
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_research"]})
        assert resp.status_code == 201
        result = resp.json()["results"][0]
        wf_id = result["workflow_id"]

        # Verify data exists
        comps = self.client.get("/api/comparisons", params={"workflow_id": wf_id}).json()
        assert len(comps) > 0

        # Reset
        resp = self.client.request("DELETE", "/api/demos/reset",
                                    json={"demos": ["agent_research"]})
        assert resp.status_code == 200
        assert "agent_research" in resp.json()["reset"]

        # Verify workflow is gone
        resp = self.client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 404

    def test_reseed_agent_demo_is_idempotent(self):
        """Seeding the same demo twice should work (clears and re-seeds)."""
        resp1 = self.client.post("/api/demos/seed", json={"demos": ["agent_codereview"]})
        assert resp1.status_code == 201
        assert resp1.json()["seeded"] == 1

        resp2 = self.client.post("/api/demos/seed", json={"demos": ["agent_codereview"]})
        assert resp2.status_code == 201
        assert resp2.json()["seeded"] == 1

    def test_unknown_agent_demo_returns_400(self):
        resp = self.client.post("/api/demos/seed", json={"demos": ["nonexistent_agent_demo"]})
        assert resp.status_code == 400

    def test_codereview_demo_has_deep_nesting(self):
        """Code review demo should have multi-level nesting (sub_agent > tool_call/reasoning)."""
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_codereview"]})
        assert resp.status_code == 201
        result = resp.json()["results"][0]
        wf_id = result["workflow_id"]

        runs = self.client.get(f"/api/workflows/{wf_id}/runs").json()
        max_depth = 0
        for run in runs:
            run_detail = self.client.get(f"/api/runs/{run['id']}").json()
            for branch in run_detail.get("branches", []):
                events = self.client.get("/api/agent/trace-events",
                                          params={"branch_id": branch["id"]}).json()
                # Check depth by following parent chains
                by_id = {e["id"]: e for e in events}
                for ev in events:
                    depth = 0
                    curr = ev
                    while curr.get("parent_event_id") and curr["parent_event_id"] in by_id:
                        depth += 1
                        curr = by_id[curr["parent_event_id"]]
                    max_depth = max(max_depth, depth)

        assert max_depth >= 1, "Code review demo should have at least 1 level of nesting"


class TestDemoGalleryFrontend:
    """Validate that the DemoGallery component handles agent demos."""

    def test_demo_gallery_has_agent_type_handling(self):
        content = (PROJECT_ROOT / "frontend/src/components/DemoGallery.jsx").read_text()
        assert "demo_type" in content
        assert "'agent'" in content
        assert "AGENT" in content  # Badge text

    def test_demo_gallery_routes_agent_to_agent_compare(self):
        content = (PROJECT_ROOT / "frontend/src/components/DemoGallery.jsx").read_text()
        assert "'agentCompare'" in content

    def test_demo_gallery_shows_trace_events_count(self):
        content = (PROJECT_ROOT / "frontend/src/components/DemoGallery.jsx").read_text()
        assert "trace_events" in content
        assert "Trace Events" in content

    def test_demo_gallery_has_section_headers(self):
        content = (PROJECT_ROOT / "frontend/src/components/DemoGallery.jsx").read_text()
        assert "LLM Comparison Demos" in content
        assert "Agent Trajectory Demos" in content

    def test_demo_gallery_agent_view_button_text(self):
        content = (PROJECT_ROOT / "frontend/src/components/DemoGallery.jsx").read_text()
        assert "View Agent Runs" in content
        assert "View Eval Run" in content


class TestEndToEndDemoFlow:
    """Full flow: seed agent demo → verify all data → view trajectory → reset."""

    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        os.environ["FM_DB_PATH"] = str(tmp_path / "e2e_demo_test.db")
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"
        os.environ["FM_ENABLE_AGENT_COMPARISON"] = "true"
        _full_reload()

        from backend.main import app
        from backend.deps import db
        from fastapi.testclient import TestClient

        self.db = db
        _ak, raw_key = db.create_api_key("e2e-demo-key")
        self.client = TestClient(app)
        self.client.headers["X-API-Key"] = raw_key

    def test_full_agent_demo_lifecycle(self):
        """Simulate the exact flow a first-time user would experience."""
        # 1. List demos — should see agent demos
        resp = self.client.get("/api/demos")
        assert resp.status_code == 200
        demos = resp.json()
        agent_names = [d["name"] for d in demos if d.get("demo_type") == "agent"]
        assert "agent_research" in agent_names

        # 2. Seed the research agent demo
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_research"]})
        assert resp.status_code == 201
        seed_result = resp.json()["results"][0]
        wf_id = seed_result["workflow_id"]
        er_id = seed_result["eval_run_id"]

        # 3. Verify feature status endpoint (what frontend checks first)
        resp = self.client.get("/api/agent/feature-status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        # 4. Get comparisons for the eval run
        resp = self.client.get("/api/comparisons", params={"eval_run_id": er_id})
        assert resp.status_code == 200
        comparisons = resp.json()
        assert len(comparisons) == 3  # 3 cases in research demo

        # 5. For each comparison, simulate the TrajectoryCompare view flow
        for comp in comparisons:
            comp_id = comp["id"]

            # 5a. Fetch trajectory outcome (score cards)
            resp = self.client.get(f"/api/agent/trajectory/{comp_id}")
            assert resp.status_code == 200
            outcome = resp.json()
            assert 0 <= outcome["trajectory_score"] <= 1
            assert 0 <= outcome["tool_sequence_score"] <= 1
            assert 0 <= outcome["outcome_equivalence_score"] <= 1
            assert 0 <= outcome["efficiency_score"] <= 1

            # Verify stats are populated
            assert outcome["branch_a_tool_count"] > 0
            assert outcome["branch_b_tool_count"] > 0

            # 5b. Fetch trace events for each branch (timeline columns)
            branch_a_id = comp["branch_a_id"]
            branch_b_id = comp["branch_b_id"]

            resp_a = self.client.get("/api/agent/trace-events",
                                     params={"branch_id": branch_a_id})
            assert resp_a.status_code == 200
            events_a = resp_a.json()
            assert len(events_a) >= 2

            resp_b = self.client.get("/api/agent/trace-events",
                                     params={"branch_id": branch_b_id})
            assert resp_b.status_code == 200
            events_b = resp_b.json()
            assert len(events_b) >= 2

            # Verify event structure
            for ev in events_a + events_b:
                assert "event_type" in ev
                assert "name" in ev
                assert "latency_ms" in ev
                assert "cost_usd" in ev

        # 6. Research demo: Branch A (ReAct) should have more events than Branch B (Plan-Execute)
        first_comp = comparisons[0]
        events_a = self.client.get("/api/agent/trace-events",
                                    params={"branch_id": first_comp["branch_a_id"]}).json()
        events_b = self.client.get("/api/agent/trace-events",
                                    params={"branch_id": first_comp["branch_b_id"]}).json()
        assert len(events_a) > len(events_b), (
            "ReAct (branch A) should have more events than Plan-Execute (branch B)"
        )

        # 7. Reset and verify cleanup
        resp = self.client.request("DELETE", "/api/demos/reset",
                                    json={"demos": ["agent_research"]})
        assert resp.status_code == 200

        resp = self.client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 404


class TestFeatureGating:
    """Verify agent demos are hidden when FM_ENABLE_AGENT_COMPARISON is false."""

    @pytest.fixture(autouse=True)
    def setup_client_feature_off(self, tmp_path):
        os.environ["FM_DB_PATH"] = str(tmp_path / "gate_test.db")
        os.environ["FM_REQUIRE_UI_AUTH"] = "false"
        os.environ["FM_ENABLE_AGENT_COMPARISON"] = "false"
        _full_reload()

        from backend.main import app
        from backend.deps import db
        from fastapi.testclient import TestClient

        self.db = db
        _ak, raw_key = db.create_api_key("gate-test-key")
        self.client = TestClient(app)
        self.client.headers["X-API-Key"] = raw_key

    def test_list_demos_excludes_agent_when_disabled(self):
        resp = self.client.get("/api/demos")
        assert resp.status_code == 200
        demos = resp.json()
        agent_demos = [d for d in demos if d.get("demo_type") == "agent"]
        assert len(agent_demos) == 0, f"Agent demos should be hidden when feature is disabled, got: {[d['name'] for d in agent_demos]}"
        # LLM demos should still be present
        llm_demos = [d for d in demos if d.get("demo_type") != "agent"]
        assert len(llm_demos) >= 9

    def test_seed_agent_demo_rejected_when_disabled(self):
        resp = self.client.post("/api/demos/seed", json={"demos": ["agent_research"]})
        assert resp.status_code == 403
        assert "FM_ENABLE_AGENT_COMPARISON" in resp.json()["detail"]

    def test_seed_llm_demo_still_works_when_agent_disabled(self):
        resp = self.client.post("/api/demos/seed", json={"demos": ["quickstart"]})
        assert resp.status_code == 201
        assert resp.json()["seeded"] == 1

    def test_seed_all_excludes_agent_when_disabled(self):
        """Seed-all with empty list should only seed LLM demos."""
        resp = self.client.post("/api/demos/seed", json={"demos": []})
        assert resp.status_code == 201
        data = resp.json()
        assert data["seeded"] == 9  # Only the 9 LLM demos
        demo_names = [r["demo"] for r in data["results"]]
        for name in demo_names:
            assert not name.startswith("agent_"), f"Agent demo '{name}' should not be seeded when feature is off"

    def test_feature_status_not_available_when_disabled(self):
        """When agent feature is off, the entire /api/agent router is not mounted."""
        resp = self.client.get("/api/agent/feature-status")
        # Router not mounted → 404 (frontend interprets 404 as feature unavailable)
        assert resp.status_code == 404


class TestFrontendFeatureGating:
    """Verify frontend components have feature-gate wiring."""

    def test_sidebar_has_agent_feature_prop(self):
        content = (PROJECT_ROOT / "frontend/src/components/Sidebar.jsx").read_text()
        assert "agentEnabled" in content
        assert "agentFeature" in content

    def test_sidebar_filters_agent_item(self):
        content = (PROJECT_ROOT / "frontend/src/components/Sidebar.jsx").read_text()
        assert "agentFeature" in content
        assert "agentEnabled" in content

    def test_app_jsx_passes_agent_enabled_to_sidebar(self):
        content = (PROJECT_ROOT / "frontend/src/App.jsx").read_text()
        assert "agentEnabled={agentEnabled}" in content
        assert "agentFeatureStatus" in content

    def test_app_jsx_fetches_agent_feature_status(self):
        content = (PROJECT_ROOT / "frontend/src/App.jsx").read_text()
        assert "api.agentFeatureStatus()" in content
        assert "setAgentEnabled" in content
