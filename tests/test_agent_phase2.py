"""Phase 2 tests — Trajectory scoring engine.

Tests:
  1. Levenshtein distance correctness
  2. Tool sequence extraction (tree flattening)
  3. Tool sequence scoring (identical, different, partial overlap)
  4. Outcome equivalence scoring
  5. Efficiency scoring
  6. Combined trajectory comparison
  7. Edge cases (empty trajectories, single events)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent_models import TraceEvent, TraceEventType, TraceEventStatus
from core.trajectory_comparator import (
    _levenshtein_distance,
    _extract_tool_sequence,
    tool_sequence_score,
    outcome_equivalence_score,
    efficiency_score,
    compare_trajectories,
    _compute_stats,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_event(
    id: str,
    branch_id: str = "br-a",
    run_id: str = "run-1",
    parent_event_id: Optional[str] = None,
    event_type: str = "tool_call",
    event_index: int = 0,
    name: str = "tool",
    input_data: dict = None,
    output_data: dict = None,
    latency_ms: int = 100,
    tokens_input: int = 50,
    tokens_output: int = 30,
    cost_usd: float = 0.001,
) -> TraceEvent:
    return TraceEvent(
        id=id,
        branch_id=branch_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        event_type=TraceEventType(event_type),
        event_index=event_index,
        name=name,
        input_data=input_data or {},
        output_data=output_data or {},
        status=TraceEventStatus.COMPLETED,
        latency_ms=latency_ms,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


# ── 1. Levenshtein distance ─────────────────────────────────────────────────

class TestLevenshtein:

    def test_identical_sequences(self):
        assert _levenshtein_distance(["a", "b", "c"], ["a", "b", "c"]) == 0

    def test_completely_different(self):
        assert _levenshtein_distance(["a", "b", "c"], ["x", "y", "z"]) == 3

    def test_empty_sequences(self):
        assert _levenshtein_distance([], []) == 0

    def test_one_empty(self):
        assert _levenshtein_distance(["a", "b"], []) == 2
        assert _levenshtein_distance([], ["a", "b"]) == 2

    def test_single_insertion(self):
        assert _levenshtein_distance(["a", "b"], ["a", "x", "b"]) == 1

    def test_single_deletion(self):
        assert _levenshtein_distance(["a", "b", "c"], ["a", "c"]) == 1

    def test_single_substitution(self):
        assert _levenshtein_distance(["a", "b", "c"], ["a", "x", "c"]) == 1


# ── 2. Tool sequence extraction ─────────────────────────────────────────────

class TestToolSequenceExtraction:

    def test_flat_sequence(self):
        events = [
            _make_event("e1", event_index=0, name="search"),
            _make_event("e2", event_index=1, name="analyze"),
            _make_event("e3", event_index=2, name="summarize"),
        ]
        seq = _extract_tool_sequence(events)
        assert seq == ["tool_call:search", "tool_call:analyze", "tool_call:summarize"]

    def test_nested_tree(self):
        """Tree: root -> [child1, child2 -> [grandchild]]"""
        events = [
            _make_event("root", event_index=0, name="plan",
                        event_type="reasoning"),
            _make_event("c1", parent_event_id="root", event_index=0,
                        name="search"),
            _make_event("c2", parent_event_id="root", event_index=1,
                        name="analyze"),
            _make_event("gc1", parent_event_id="c2", event_index=0,
                        name="detail_check"),
        ]
        seq = _extract_tool_sequence(events)
        assert seq == [
            "reasoning:plan",
            "tool_call:search",
            "tool_call:analyze",
            "tool_call:detail_check",
        ]

    def test_empty_events(self):
        assert _extract_tool_sequence([]) == []


# ── 3. Tool sequence scoring ────────────────────────────────────────────────

class TestToolSequenceScore:

    def test_identical_trajectories(self):
        events = [
            _make_event("e1", event_index=0, name="search"),
            _make_event("e2", event_index=1, name="analyze"),
        ]
        score, detail = tool_sequence_score(events, events)
        assert score == 1.0
        assert detail["distance"] == 0

    def test_completely_different(self):
        events_a = [_make_event("e1", event_index=0, name="search")]
        events_b = [_make_event("e2", event_index=0, name="calculate")]
        score, detail = tool_sequence_score(events_a, events_b)
        assert score == 0.0  # 1 substitution out of max_len=1

    def test_partial_overlap(self):
        events_a = [
            _make_event("e1", event_index=0, name="search"),
            _make_event("e2", event_index=1, name="analyze"),
            _make_event("e3", event_index=2, name="summarize"),
        ]
        events_b = [
            _make_event("e4", event_index=0, name="search"),
            _make_event("e5", event_index=1, name="calculate"),
            _make_event("e6", event_index=2, name="summarize"),
        ]
        score, detail = tool_sequence_score(events_a, events_b)
        # 1 substitution out of 3
        assert abs(score - (1.0 - 1/3)) < 0.01

    def test_both_empty(self):
        score, detail = tool_sequence_score([], [])
        assert score == 1.0


# ── 4. Outcome equivalence ──────────────────────────────────────────────────

class TestOutcomeEquivalence:

    def test_identical_outputs(self):
        events_a = [_make_event("e1", output_data={"text": "Hello world"})]
        events_b = [_make_event("e2", output_data={"text": "Hello world"})]
        score, detail = outcome_equivalence_score(events_a, events_b)
        # Should be very high (close to 1.0)
        assert score > 0.9

    def test_empty_outputs(self):
        score, detail = outcome_equivalence_score([], [])
        assert score == 1.0

    def test_one_empty(self):
        events_a = [_make_event("e1", output_data={"text": "data"})]
        score, detail = outcome_equivalence_score(events_a, [])
        assert score == 0.0

    def test_different_outputs(self):
        events_a = [_make_event("e1", output_data={"text": "The weather is sunny today"})]
        events_b = [_make_event("e2", output_data={"text": "Python programming language tutorial"})]
        score, detail = outcome_equivalence_score(events_a, events_b)
        assert score < 0.8  # substantially different


# ── 5. Efficiency scoring ───────────────────────────────────────────────────

class TestEfficiencyScore:

    def test_identical_efficiency(self):
        events_a = [_make_event("e1", latency_ms=100, cost_usd=0.01,
                                 tokens_input=50, tokens_output=30)]
        events_b = [_make_event("e2", latency_ms=100, cost_usd=0.01,
                                 tokens_input=50, tokens_output=30)]
        score, detail = efficiency_score(events_a, events_b)
        assert score == 1.0

    def test_very_different_efficiency(self):
        events_a = [_make_event("e1", latency_ms=100, cost_usd=0.001,
                                 tokens_input=50, tokens_output=30)]
        events_b = [
            _make_event(f"e{i}", latency_ms=1000, cost_usd=0.1,
                        tokens_input=500, tokens_output=300)
            for i in range(5)
        ]
        score, detail = efficiency_score(events_a, events_b)
        assert score < 0.3  # very different

    def test_empty_trajectories(self):
        score, detail = efficiency_score([], [])
        assert score == 1.0  # both zero = identical

    def test_compute_stats(self):
        events = [
            _make_event("e1", latency_ms=100, cost_usd=0.01,
                        tokens_input=50, tokens_output=30),
            _make_event("e2", parent_event_id="e1", event_index=1,
                        latency_ms=200, cost_usd=0.02,
                        tokens_input=80, tokens_output=40),
        ]
        stats = _compute_stats(events)
        assert stats.total_latency_ms == 300
        assert stats.total_cost_usd == pytest.approx(0.03)
        assert stats.total_tokens_input == 130
        assert stats.tool_count == 2
        assert stats.event_count == 2


# ── 6. Combined comparison ──────────────────────────────────────────────────

class TestCompareTrajectories:

    def test_identical_trajectories(self):
        events = [
            _make_event("e1", event_index=0, name="search",
                        output_data={"text": "result"},
                        latency_ms=100, cost_usd=0.01),
            _make_event("e2", event_index=1, name="analyze",
                        output_data={"text": "analysis"},
                        latency_ms=150, cost_usd=0.015),
        ]
        result = compare_trajectories(events, events)
        assert result["trajectory_score"] > 0.95
        assert result["tool_sequence_score"] == 1.0
        assert result["efficiency_score"] == 1.0
        assert "weights" in result

    def test_structure_of_result(self):
        events_a = [_make_event("e1", name="search")]
        events_b = [_make_event("e2", name="search")]
        result = compare_trajectories(events_a, events_b)

        required_keys = {
            "trajectory_score", "tool_sequence_score",
            "outcome_equivalence_score", "efficiency_score",
            "tool_sequence_detail", "outcome_detail", "efficiency_detail",
            "branch_a_tool_count", "branch_b_tool_count",
            "branch_a_depth", "branch_b_depth",
            "branch_a_total_latency_ms", "branch_b_total_latency_ms",
            "branch_a_total_cost_usd", "branch_b_total_cost_usd",
            "weights",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_custom_weights(self):
        events_a = [_make_event("e1", name="search")]
        events_b = [_make_event("e2", name="calculate")]
        # Weight tool_sequence at 100%
        result = compare_trajectories(
            events_a, events_b,
            weights={"tool_sequence": 1.0, "outcome_equivalence": 0.0, "efficiency": 0.0},
        )
        assert result["trajectory_score"] == result["tool_sequence_score"]

    def test_empty_trajectories(self):
        result = compare_trajectories([], [])
        assert result["trajectory_score"] == 1.0

    def test_scores_in_valid_range(self):
        """All scores should be between 0 and 1."""
        events_a = [
            _make_event("e1", event_index=0, name="search",
                        output_data={"text": "hello"}),
            _make_event("e2", event_index=1, name="analyze",
                        output_data={"text": "world"}),
        ]
        events_b = [
            _make_event("e3", event_index=0, name="calculate",
                        output_data={"text": "different"}),
        ]
        result = compare_trajectories(events_a, events_b)
        for key in ("trajectory_score", "tool_sequence_score",
                    "outcome_equivalence_score", "efficiency_score"):
            assert 0.0 <= result[key] <= 1.0, f"{key} = {result[key]} out of range"


# ── 7. Edge cases ────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_single_event_vs_many(self):
        """One event vs multiple should still produce valid scores."""
        events_a = [_make_event("e1", name="search")]
        events_b = [
            _make_event("e2", event_index=0, name="plan",
                        event_type="reasoning"),
            _make_event("e3", event_index=1, name="search"),
            _make_event("e4", event_index=2, name="analyze"),
            _make_event("e5", event_index=3, name="summarize"),
        ]
        result = compare_trajectories(events_a, events_b)
        assert 0.0 <= result["trajectory_score"] <= 1.0
        assert result["branch_a_tool_count"] == 1
        assert result["branch_b_tool_count"] >= 1

    def test_deep_nesting(self):
        """Deeply nested tree should still produce valid results."""
        events = []
        parent = None
        for i in range(10):
            eid = f"e{i}"
            events.append(_make_event(
                eid, parent_event_id=parent, event_index=0,
                name=f"step_{i}",
            ))
            parent = eid
        result = compare_trajectories(events, events)
        assert result["trajectory_score"] == 1.0
        assert result["branch_a_depth"] > 0

    def test_zero_cost_events(self):
        """Events with zero cost should not cause division errors."""
        events_a = [_make_event("e1", cost_usd=0.0, latency_ms=0,
                                 tokens_input=0, tokens_output=0)]
        events_b = [_make_event("e2", cost_usd=0.0, latency_ms=0,
                                 tokens_input=0, tokens_output=0)]
        score, detail = efficiency_score(events_a, events_b)
        assert score == 1.0  # both zero = identical
