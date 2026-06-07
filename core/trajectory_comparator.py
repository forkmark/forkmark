"""Trajectory comparison engine for agent runs.

Provides three scoring dimensions for comparing two agent trajectories:

  1. **Tool sequence alignment** — Normalized Levenshtein distance on the
     ordered list of tool/event names.  Measures whether the agents followed
     similar decision paths regardless of the specific outputs.

  2. **Outcome equivalence** — Semantic (or lexical) similarity between the
     final outputs/observations of each trajectory.  Reuses the existing
     divergence scorer from ``core.comparator``.

  3. **Efficiency ratio** — Compares cost, latency, and token usage between
     the two trajectories.  Returns a ratio where 1.0 = identical efficiency,
     >1.0 = branch A more expensive, <1.0 = branch B more expensive.

The overall ``trajectory_score`` is a weighted mean of the three dimensions.
Default weights: sequence=0.35, outcome=0.45, efficiency=0.20.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from core.agent_models import TraceEvent, TraceEventType


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "tool_sequence": 0.35,
    "outcome_equivalence": 0.45,
    "efficiency": 0.20,
}


# ── 1. Tool Sequence Alignment ──────────────────────────────────────────────

def _levenshtein_distance(seq_a: List[str], seq_b: List[str]) -> int:
    """Classic Levenshtein distance between two sequences of strings."""
    m, n = len(seq_a), len(seq_b)
    if m == 0:
        return n
    if n == 0:
        return m
    # Use two-row optimization
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if seq_a[i - 1] == seq_b[j - 1] else 1
            curr[j] = min(
                curr[j - 1] + 1,       # insertion
                prev[j] + 1,           # deletion
                prev[j - 1] + cost,    # substitution
            )
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def _extract_tool_sequence(events: List[TraceEvent]) -> List[str]:
    """Extract ordered list of event names (flattened from tree)."""
    # Sort by event_index within each level, depth-first
    result = []
    _walk_tree(events, None, result)
    return result


def _walk_tree(events: List[TraceEvent], parent_id: Optional[str],
               result: List[str]) -> None:
    """Depth-first walk of the event tree."""
    children = sorted(
        [e for e in events if e.parent_event_id == parent_id],
        key=lambda e: e.event_index,
    )
    for child in children:
        # Include type:name for richer comparison
        result.append(f"{child.event_type.value}:{child.name}")
        _walk_tree(events, child.id, result)


def tool_sequence_score(events_a: List[TraceEvent],
                        events_b: List[TraceEvent]) -> Tuple[float, Dict[str, Any]]:
    """Score tool sequence alignment between two trajectories.

    Returns
    -------
    score : float
        0.0 = completely different sequences, 1.0 = identical.
    detail : dict
        Detailed alignment information.
    """
    seq_a = _extract_tool_sequence(events_a)
    seq_b = _extract_tool_sequence(events_b)

    if not seq_a and not seq_b:
        return 1.0, {"sequence_a": [], "sequence_b": [], "distance": 0,
                      "max_len": 0, "message": "both trajectories empty"}

    max_len = max(len(seq_a), len(seq_b))
    distance = _levenshtein_distance(seq_a, seq_b)
    score = 1.0 - (distance / max_len)

    return score, {
        "sequence_a": seq_a,
        "sequence_b": seq_b,
        "distance": distance,
        "max_len": max_len,
        "normalized_distance": distance / max_len if max_len else 0,
    }


# ── 2. Outcome Equivalence ──────────────────────────────────────────────────

def _extract_final_outputs(events: List[TraceEvent]) -> str:
    """Extract the final output text from a trajectory.

    Concatenates output_data from leaf events (those with no children)
    in order. Falls back to all event outputs if no clear leaves.
    """
    if not events:
        return ""

    event_ids = {e.id for e in events}
    parent_ids = {e.parent_event_id for e in events if e.parent_event_id}

    # Leaf events: those whose id is not a parent of any other event
    leaves = [e for e in events if e.id not in parent_ids]
    if not leaves:
        leaves = events  # fallback

    # Sort leaves by event_index
    leaves.sort(key=lambda e: e.event_index)

    parts = []
    for ev in leaves:
        out = ev.output_data
        if isinstance(out, dict):
            # Try common keys
            for key in ("text", "output", "result", "content", "response"):
                if key in out:
                    parts.append(str(out[key]))
                    break
            else:
                parts.append(json.dumps(out))
        elif isinstance(out, str):
            parts.append(out)
    return "\n".join(parts)


def outcome_equivalence_score(events_a: List[TraceEvent],
                              events_b: List[TraceEvent]) -> Tuple[float, Dict[str, Any]]:
    """Score outcome equivalence between two trajectories.

    Uses the existing divergence scorer (inverted: 0 divergence = 1.0 equivalence).

    Returns
    -------
    score : float
        0.0 = completely different outcomes, 1.0 = identical.
    detail : dict
        Comparison details.
    """
    text_a = _extract_final_outputs(events_a)
    text_b = _extract_final_outputs(events_b)

    if not text_a and not text_b:
        return 1.0, {"text_a_len": 0, "text_b_len": 0,
                      "message": "both trajectories produced no output"}

    if not text_a or not text_b:
        return 0.0, {"text_a_len": len(text_a), "text_b_len": len(text_b),
                      "message": "one trajectory produced no output"}

    # Short-circuit: identical text = perfect equivalence
    if text_a.strip() == text_b.strip():
        return 1.0, {"text_a_len": len(text_a), "text_b_len": len(text_b),
                      "divergence": 0.0, "scorer": "exact_match",
                      "text_a_preview": text_a[:200], "text_b_preview": text_b[:200]}

    try:
        from core.comparator import divergence_score as div_score, scorer_name
        divergence = div_score(text_a, text_b)
        score = 1.0 - divergence
        method = scorer_name()
    except Exception:
        # Fallback: simple ratio
        from difflib import SequenceMatcher
        score = SequenceMatcher(None, text_a, text_b).ratio()
        method = "sequence_matcher_fallback"

    return max(0.0, min(1.0, score)), {
        "text_a_preview": text_a[:200],
        "text_b_preview": text_b[:200],
        "text_a_len": len(text_a),
        "text_b_len": len(text_b),
        "divergence": 1.0 - score,
        "scorer": method,
    }


# ── 3. Efficiency Ratio ─────────────────────────────────────────────────────

@dataclass
class _TrajectoryStats:
    """Aggregated stats for one trajectory."""
    total_latency_ms: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost_usd: float = 0.0
    tool_count: int = 0
    max_depth: int = 0
    event_count: int = 0


def _compute_stats(events: List[TraceEvent]) -> _TrajectoryStats:
    """Aggregate stats across all events in a trajectory."""
    stats = _TrajectoryStats()
    stats.event_count = len(events)

    for ev in events:
        stats.total_latency_ms += ev.latency_ms
        stats.total_tokens_input += ev.tokens_input
        stats.total_tokens_output += ev.tokens_output
        stats.total_cost_usd += ev.cost_usd or 0.0
        if ev.event_type in (TraceEventType.TOOL_CALL, TraceEventType.SUB_AGENT):
            stats.tool_count += 1

    # Compute max depth
    if events:
        depth_map: Dict[Optional[str], int] = {None: 0}
        # Sort by event_index to process parents before children
        sorted_events = sorted(events, key=lambda e: e.event_index)
        for ev in sorted_events:
            parent_depth = depth_map.get(ev.parent_event_id, 0)
            depth_map[ev.id] = parent_depth + 1
        stats.max_depth = max(depth_map.values()) if depth_map else 0

    return stats


def efficiency_score(events_a: List[TraceEvent],
                     events_b: List[TraceEvent]) -> Tuple[float, Dict[str, Any]]:
    """Score relative efficiency between two trajectories.

    A score of 1.0 means identical efficiency. The score decreases as the
    efficiency gap widens.  Uses a harmonic-mean-style comparison across
    cost, latency, and token usage.

    Returns
    -------
    score : float
        0.0–1.0, where 1.0 = identical efficiency.
    detail : dict
        Per-metric breakdown.
    """
    stats_a = _compute_stats(events_a)
    stats_b = _compute_stats(events_b)

    def _ratio_score(val_a: float, val_b: float) -> float:
        """Convert two values into a 0–1 similarity score."""
        if val_a == 0 and val_b == 0:
            return 1.0
        if val_a == 0 or val_b == 0:
            return 0.0
        ratio = min(val_a, val_b) / max(val_a, val_b)
        return ratio

    latency_sim = _ratio_score(stats_a.total_latency_ms, stats_b.total_latency_ms)
    cost_sim = _ratio_score(stats_a.total_cost_usd, stats_b.total_cost_usd)
    token_sim = _ratio_score(
        stats_a.total_tokens_input + stats_a.total_tokens_output,
        stats_b.total_tokens_input + stats_b.total_tokens_output,
    )
    tool_count_sim = _ratio_score(stats_a.tool_count, stats_b.tool_count)

    # Weighted combination (cost matters most)
    weights = {"latency": 0.25, "cost": 0.35, "tokens": 0.25, "tool_count": 0.15}
    score = (
        weights["latency"] * latency_sim
        + weights["cost"] * cost_sim
        + weights["tokens"] * token_sim
        + weights["tool_count"] * tool_count_sim
    )

    return score, {
        "branch_a": {
            "total_latency_ms": stats_a.total_latency_ms,
            "total_cost_usd": stats_a.total_cost_usd,
            "total_tokens": stats_a.total_tokens_input + stats_a.total_tokens_output,
            "tool_count": stats_a.tool_count,
            "max_depth": stats_a.max_depth,
            "event_count": stats_a.event_count,
        },
        "branch_b": {
            "total_latency_ms": stats_b.total_latency_ms,
            "total_cost_usd": stats_b.total_cost_usd,
            "total_tokens": stats_b.total_tokens_input + stats_b.total_tokens_output,
            "tool_count": stats_b.tool_count,
            "max_depth": stats_b.max_depth,
            "event_count": stats_b.event_count,
        },
        "similarities": {
            "latency": latency_sim,
            "cost": cost_sim,
            "tokens": token_sim,
            "tool_count": tool_count_sim,
        },
    }


# ── Combined Trajectory Score ────────────────────────────────────────────────

def compare_trajectories(
    events_a: List[TraceEvent],
    events_b: List[TraceEvent],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Full trajectory comparison across all three dimensions.

    Parameters
    ----------
    events_a, events_b : list of TraceEvent
        The two trajectories to compare.
    weights : dict, optional
        Override default weights for {tool_sequence, outcome_equivalence, efficiency}.

    Returns
    -------
    dict
        Full comparison result with per-dimension scores and overall trajectory_score.
    """
    w = weights or DEFAULT_WEIGHTS

    seq_score, seq_detail = tool_sequence_score(events_a, events_b)
    out_score, out_detail = outcome_equivalence_score(events_a, events_b)
    eff_score, eff_detail = efficiency_score(events_a, events_b)

    # Weighted overall score
    trajectory = (
        w.get("tool_sequence", 0.35) * seq_score
        + w.get("outcome_equivalence", 0.45) * out_score
        + w.get("efficiency", 0.20) * eff_score
    )

    stats_a = _compute_stats(events_a)
    stats_b = _compute_stats(events_b)

    return {
        "trajectory_score": round(trajectory, 4),
        "tool_sequence_score": round(seq_score, 4),
        "outcome_equivalence_score": round(out_score, 4),
        "efficiency_score": round(eff_score, 4),
        "tool_sequence_detail": seq_detail,
        "outcome_detail": out_detail,
        "efficiency_detail": eff_detail,
        "branch_a_tool_count": stats_a.tool_count,
        "branch_b_tool_count": stats_b.tool_count,
        "branch_a_depth": stats_a.max_depth,
        "branch_b_depth": stats_b.max_depth,
        "branch_a_total_latency_ms": stats_a.total_latency_ms,
        "branch_b_total_latency_ms": stats_b.total_latency_ms,
        "branch_a_total_cost_usd": round(stats_a.total_cost_usd, 6),
        "branch_b_total_cost_usd": round(stats_b.total_cost_usd, 6),
        "weights": w,
    }
