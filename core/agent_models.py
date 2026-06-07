"""Agent comparison data models.

Hierarchy addition for agent/agentic workflow comparison:

  WorkflowRun (existing)
    Branch (existing)
      TraceEvent         -- one node in the agent's decision graph
        TraceEvent       -- nested sub-events (self-referencing tree)
    TrajectoryOutcome    -- per-comparison trajectory-level scoring

TraceEvent forms a tree via parent_event_id, enabling nested tool calls
and sub-agent traces.  The tree is rooted at events with parent_event_id=NULL
(top-level reasoning / tool calls from the main agent).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import json


def _parse_dt(s: str) -> datetime:
    """Parse ISO-8601 datetime, handling 'Z' suffix on Python < 3.11."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


# ── Enums ────────────────────────────────────────────────────────────────────

class TraceEventType(str, Enum):
    """Categorizes what happened at this point in the agent trajectory."""
    REASONING    = "reasoning"      # chain-of-thought / planning step
    TOOL_CALL    = "tool_call"      # tool invocation
    TOOL_RESULT  = "tool_result"    # tool response/observation
    SUB_AGENT    = "sub_agent"      # delegated to a sub-agent
    OBSERVATION  = "observation"    # environment observation (non-tool)
    DECISION     = "decision"       # branching/routing decision
    ERROR        = "error"          # error / exception in trajectory


class TraceEventStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


# ── TraceEvent ───────────────────────────────────────────────────────────────

@dataclass
class TraceEvent:
    """One node in the agent's decision/execution graph.

    Forms a tree via parent_event_id.  Root events have parent_event_id=None.
    Events within a branch are ordered by event_index.

    Attributes
    ----------
    id : str
        UUID primary key.
    branch_id : str
        FK to branches.id — which branch this event belongs to.
    run_id : str
        FK to workflow_runs.id — denormalized for efficient queries.
    parent_event_id : str | None
        FK to trace_events.id — None for root events.
    event_type : TraceEventType
        What kind of event this is.
    event_index : int
        Ordering within this level (siblings share parent_event_id).
    name : str
        Human-readable label (e.g. tool name, "planning", sub-agent name).
    input_data : dict
        Input to this event (tool args, reasoning prompt, etc.).
    output_data : dict
        Output from this event (tool response, reasoning result, etc.).
    status : TraceEventStatus
        Execution status.
    latency_ms : int
        Wall-clock time for this event.
    tokens_input : int
        Token count for input (if LLM call involved).
    tokens_output : int
        Token count for output (if LLM call involved).
    cost_usd : float | None
        Estimated cost in USD.
    metadata : dict
        Arbitrary extra data (model_id, temperature, etc.).
    created_at : datetime
        When this event was recorded.
    """
    id: str
    branch_id: str
    run_id: str
    parent_event_id: Optional[str]
    event_type: TraceEventType
    event_index: int
    name: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    status: TraceEventStatus
    latency_ms: int
    tokens_input: int
    tokens_output: int
    cost_usd: Optional[float]
    metadata: Dict[str, Any]
    created_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "TraceEvent":
        r = dict(r)
        r["event_type"] = TraceEventType(r["event_type"])
        r["status"] = TraceEventStatus(r.get("status", "completed"))
        r["created_at"] = _parse_dt(r["created_at"])
        r["input_data"] = json.loads(r.get("input_data") or "{}")
        r["output_data"] = json.loads(r.get("output_data") or "{}")
        r["metadata"] = json.loads(r.get("metadata") or "{}")
        r.setdefault("parent_event_id", None)
        r.setdefault("cost_usd", None)
        r.setdefault("tokens_input", 0)
        r.setdefault("tokens_output", 0)
        r.setdefault("latency_ms", 0)
        return cls(**r)


# ── TrajectoryOutcome ────────────────────────────────────────────────────────

@dataclass
class TrajectoryOutcome:
    """Trajectory-level scoring for an agent comparison.

    Linked to a comparison, stores the three scoring dimensions:
      - tool_sequence_score: Levenshtein-based alignment of tool call sequences
      - outcome_equivalence_score: semantic similarity of final outcomes
      - efficiency_score: ratio of cost/latency/token usage

    Overall trajectory_score is a weighted mean of the three dimensions.
    """
    id: str
    comparison_id: str
    run_id: str
    workflow_id: str

    # Scoring dimensions (each 0.0 - 1.0)
    tool_sequence_score: float
    outcome_equivalence_score: float
    efficiency_score: float
    trajectory_score: float           # weighted overall score

    # Detailed breakdown
    tool_sequence_detail: Dict[str, Any]    # alignment visualization data
    outcome_detail: Dict[str, Any]          # what differed in outcomes
    efficiency_detail: Dict[str, Any]       # cost/latency/token breakdowns

    # Trajectory metadata
    branch_a_tool_count: int
    branch_b_tool_count: int
    branch_a_depth: int                     # max tree depth
    branch_b_depth: int
    branch_a_total_latency_ms: int
    branch_b_total_latency_ms: int
    branch_a_total_cost_usd: float
    branch_b_total_cost_usd: float

    created_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "TrajectoryOutcome":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["tool_sequence_detail"] = json.loads(r.get("tool_sequence_detail") or "{}")
        r["outcome_detail"] = json.loads(r.get("outcome_detail") or "{}")
        r["efficiency_detail"] = json.loads(r.get("efficiency_detail") or "{}")
        # numeric defaults
        for f in ("tool_sequence_score", "outcome_equivalence_score",
                  "efficiency_score", "trajectory_score"):
            r.setdefault(f, 0.0)
        for f in ("branch_a_tool_count", "branch_b_tool_count",
                  "branch_a_depth", "branch_b_depth"):
            r.setdefault(f, 0)
        for f in ("branch_a_total_latency_ms", "branch_b_total_latency_ms"):
            r.setdefault(f, 0)
        for f in ("branch_a_total_cost_usd", "branch_b_total_cost_usd"):
            r.setdefault(f, 0.0)
        return cls(**r)
