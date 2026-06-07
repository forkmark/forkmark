"""Forkmark core data models.

Hierarchy:
  TestSet            — a named, reusable collection of test inputs
    TestCase         — one input in a test set
  EvalRun            — a batch evaluation: run N test cases through two branch configs
    WorkflowRun      — one execution per test case (linked via eval_run_id)
      Branch         — baseline (A) or challenger (B) config variant
        StepOutput   — one LLM call result per branch per step
      Comparison     — side-by-side of A vs B for this run (with divergence_score)
        Decision     — human verdict recorded in the review UI
  Workflow           — named workflow grouping all eval runs and ad-hoc runs
  ApiKey             — SDK authentication
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


# ── Enums ─────────────────────────────────────────────────────────────────────

class RunStatus(str, Enum):
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class DecisionChoice(str, Enum):
    BRANCH_A  = "A"
    BRANCH_B  = "B"
    NEITHER   = "neither"
    BOTH      = "both"


class ConfidenceLevel(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class EvalRunStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class ScoringStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


# ── EvalResult ────────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    """Result of a single auto-evaluator run on a step output."""
    name: str          # evaluator name, e.g. 'json_schema', 'regex_match'
    passed: bool       # did the output pass the evaluation?
    score: float       # numeric score ∈ [0, 1], 1.0 = perfect
    detail: str = ""   # human-readable explanation

    def to_dict(self) -> dict:
        return asdict(self)


# ── TestSet ───────────────────────────────────────────────────────────────────

@dataclass
class TestSet:
    """A named, reusable collection of test inputs.

    version:   Auto-incremented when a new version is created from a frozen set.
    is_frozen: Set to True when an EvalRun references this set — prevents
               mutations so past evaluation results remain reproducible.
    """
    id: str
    name: str
    description: str
    workflow_id: Optional[str]
    created_at: datetime
    case_count: int = 0
    version: int = 1
    is_frozen: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "TestSet":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r.setdefault("workflow_id", None)
        r.setdefault("case_count", 0)
        r.setdefault("version", 1)
        r["is_frozen"] = bool(r.get("is_frozen", 0))
        return cls(**r)


# ── TestCase ──────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    """A single named input belonging to a test set."""
    id: str
    test_set_id: str
    label: str                  # human-readable name for this input
    input_data: Dict[str, Any]  # arbitrary payload passed to the workflow
    tags: List[str]
    created_at: datetime
    expected_output: Optional[str] = None  # ground-truth for evaluators
    # flywheel-1 metadata (migration v4)
    domain: str = ""
    industry: str = ""
    use_case_type: str = ""
    failure_mode: str = ""
    test_goal: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "TestCase":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["input_data"] = json.loads(r.get("input_data") or "{}")
        r["tags"] = json.loads(r.get("tags") or "[]")
        r.setdefault("expected_output", None)
        # flywheel-1 metadata defaults
        for f in ("domain", "industry", "use_case_type", "failure_mode", "test_goal"):
            r.setdefault(f, "")
        return cls(**r)


# ── EvalRun ───────────────────────────────────────────────────────────────────

@dataclass
class EvalRun:
    """A batch evaluation grouping N workflow runs under two branch configs.

    branch_a_config and branch_b_config are descriptive labels set at creation
    time by the SDK or UI — Forkmark doesn't execute LLM calls itself.
    """
    id: str
    workflow_id: str
    name: str
    description: str
    test_set_id: Optional[str]       # if created from a saved test set
    branch_a_config: Dict[str, Any]  # {label, model_id, temperature, system_prompt}
    branch_b_config: Dict[str, Any]
    status: EvalRunStatus
    total_cases: int                 # how many inputs were submitted
    created_at: datetime
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        d["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return d

    @classmethod
    def from_row(cls, r: dict) -> "EvalRun":
        r = dict(r)
        r["status"] = EvalRunStatus(r["status"])
        r["created_at"] = _parse_dt(r["created_at"])
        r["completed_at"] = _parse_dt(r["completed_at"]) if r.get("completed_at") else None
        r["branch_a_config"] = json.loads(r.get("branch_a_config") or "{}")
        r["branch_b_config"] = json.loads(r.get("branch_b_config") or "{}")
        r.setdefault("test_set_id", None)
        r.setdefault("total_cases", 0)
        return cls(**r)


# ── Workflow ──────────────────────────────────────────────────────────────────

@dataclass
class Workflow:
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    run_count: int = 0
    decision_count: int = 0
    eval_run_count: int = 0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "Workflow":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["updated_at"] = _parse_dt(r["updated_at"])
        r["tags"] = json.loads(r.get("tags") or "[]")
        r.setdefault("run_count", 0)
        r.setdefault("decision_count", 0)
        r.setdefault("eval_run_count", 0)
        return cls(**r)


# ── WorkflowRun ───────────────────────────────────────────────────────────────

@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    status: RunStatus
    created_at: datetime
    completed_at: Optional[datetime]
    input_data: Dict[str, Any]
    metadata: Dict[str, Any]
    sdk_key_prefix: str = ""
    eval_run_id: Optional[str] = None    # set when part of a batch eval
    test_case_label: str = ""            # denormalized label for display
    run_type: str = "standard"           # "standard" or "agent" (v0.1.2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        d["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return d

    @classmethod
    def from_row(cls, r: dict) -> "WorkflowRun":
        r = dict(r)
        r["status"] = RunStatus(r["status"])
        r["created_at"] = _parse_dt(r["created_at"])
        r["completed_at"] = _parse_dt(r["completed_at"]) if r.get("completed_at") else None
        r["input_data"] = json.loads(r.get("input_data") or "{}")
        r["metadata"] = json.loads(r.get("metadata") or "{}")
        r.setdefault("sdk_key_prefix", "")
        r.setdefault("eval_run_id", None)
        r.setdefault("test_case_label", "")
        r.setdefault("run_type", "standard")
        return cls(**r)


# ── Branch ────────────────────────────────────────────────────────────────────

@dataclass
class Branch:
    id: str
    run_id: str
    workflow_id: str
    name: str
    model_id: str
    temperature: float
    system_prompt: Optional[str]
    extra_config: Dict[str, Any]
    created_at: datetime
    is_baseline: bool = False
    provider_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "Branch":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["extra_config"] = json.loads(r.get("extra_config") or "{}")
        r["is_baseline"] = bool(r.get("is_baseline", 0))
        return cls(**r)


# ── StepOutput ────────────────────────────────────────────────────────────────

@dataclass
class StepOutput:
    id: str
    run_id: str
    branch_id: str
    step_name: str
    step_index: int
    input_messages: List[Dict]
    output_text: str
    model_id: str
    temperature: float
    tokens_input: int
    tokens_output: int
    latency_ms: int
    created_at: datetime
    error: Optional[str] = None
    trace_id: Optional[str] = None   # OpenTelemetry trace ID
    span_id: Optional[str] = None    # OpenTelemetry span ID
    cost_usd: Optional[float] = None # estimated cost in USD

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_row(cls, r: dict) -> "StepOutput":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["input_messages"] = json.loads(r.get("input_messages") or "[]")
        r.setdefault("error", None)
        r.setdefault("trace_id", None)
        r.setdefault("span_id", None)
        r.setdefault("cost_usd", None)
        return cls(**r)


# ── Comparison ────────────────────────────────────────────────────────────────

@dataclass
class Comparison:
    """A side-by-side of two branches for one run.

    divergence_score is pre-computed and stored at creation time by the SDK
    endpoint — this enables efficient aggregate stats for eval runs without
    loading step outputs.

    step_divergence_scores maps step_name → divergence for per-step breakdown.
    Overall divergence_score is the mean of per-step scores (not a concatenated
    blob), which gives a more accurate picture of where the runs diverged.
    """
    id: str
    run_id: str
    workflow_id: str
    branch_a_id: str
    branch_b_id: str
    created_at: datetime
    step_names: List[str]
    decided: bool = False
    decision_id: Optional[str] = None
    eval_run_id: Optional[str] = None        # set when part of a batch eval
    test_case_label: str = ""                # label of the test input
    divergence_score: Optional[float] = None # pre-computed mean of step scores
    step_divergence_scores: Dict[str, float] = field(default_factory=dict)  # per-step breakdown
    eval_results: Dict[str, List[Dict]] = field(default_factory=dict)  # step_name → [EvalResult dicts]
    scoring_status: ScoringStatus = ScoringStatus.COMPLETED
    review_status: str = "pending"      # pending/assigned/reviewed/skipped
    assigned_to: str = ""               # reviewer ID for queue management

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["scoring_status"] = self.scoring_status.value
        return d

    @classmethod
    def from_row(cls, r: dict) -> "Comparison":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["step_names"] = json.loads(r.get("step_names") or "[]")
        r["decided"] = bool(r.get("decided", 0))
        r.setdefault("decision_id", None)
        r.setdefault("eval_run_id", None)
        r.setdefault("test_case_label", "")
        r.setdefault("divergence_score", None)
        r["step_divergence_scores"] = json.loads(r.get("step_divergence_scores") or "{}")
        r["eval_results"] = json.loads(r.get("eval_results") or "{}")
        r["scoring_status"] = ScoringStatus(r.get("scoring_status", "completed"))
        r.setdefault("review_status", "pending")
        r.setdefault("assigned_to", "")
        return cls(**r)


# ── Decision ──────────────────────────────────────────────────────────────────

@dataclass
class Decision:
    """Human verdict on a comparison — the primary data asset."""
    id: str
    comparison_id: str
    run_id: str
    workflow_id: str
    reviewer_id: str
    choice: DecisionChoice
    confidence: ConfidenceLevel
    rationale_for_choice: str
    rationale_for_rejection: str
    tags: List[str]
    created_at: datetime
    updated_at: Optional[datetime] = None   # set on edit — enables audit trail
    branch_winner_id: Optional[str] = None
    branch_loser_id: Optional[str] = None
    divergence_score: float = 0.0
    divergence_summary: Optional[str] = None
    eval_run_id: Optional[str] = None  # denormalized for efficient eval stats
    provenance_hash: str = ""         # SHA-256(workflow_id:label:input_snippet)
    data_category: str = ""           # auto-classified category tag

    def to_dict(self) -> dict:
        d = asdict(self)
        d["choice"] = self.choice.value
        d["confidence"] = self.confidence.value
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return d

    @classmethod
    def from_row(cls, r: dict) -> "Decision":
        r = dict(r)
        r["choice"] = DecisionChoice(r["choice"])
        r["confidence"] = ConfidenceLevel(r["confidence"])
        r["created_at"] = _parse_dt(r["created_at"])
        r["updated_at"] = _parse_dt(r["updated_at"]) if r.get("updated_at") else None
        r["tags"] = json.loads(r.get("tags") or "[]")
        r.setdefault("branch_winner_id", None)
        r.setdefault("branch_loser_id", None)
        r.setdefault("divergence_score", 0.0)
        r.setdefault("divergence_summary", None)
        r.setdefault("eval_run_id", None)
        r.setdefault("provenance_hash", "")
        r.setdefault("data_category", "")
        return cls(**r)


# ── API Key ───────────────────────────────────────────────────────────────────

@dataclass
class ApiKey:
    id: str
    name: str
    key_hash: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    is_active: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("key_hash")
        d["created_at"] = self.created_at.isoformat()
        d["last_used_at"] = self.last_used_at.isoformat() if self.last_used_at else None
        return d

    @classmethod
    def from_row(cls, r: dict) -> "ApiKey":
        r = dict(r)
        r["created_at"] = _parse_dt(r["created_at"])
        r["last_used_at"] = (_parse_dt(r["last_used_at"])
                             if r.get("last_used_at") else None)
        r["is_active"] = bool(r.get("is_active", 1))
        return cls(**r)
