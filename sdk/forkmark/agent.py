"""Agent comparison SDK — record and compare agent trajectories.

Usage::

    import forkmark

    fp = forkmark.init(api_key="fm_...", workflow="my-agent-workflow")

    with fp.agent_run(input_data={"query": "plan a trip to Tokyo"}) as ar:
        # Branch A — baseline agent
        with ar.branch("baseline", model_id="gpt-4o", temperature=0.7) as br_a:
            br_a.record_event("reasoning", "planning",
                              input_data={"prompt": "Plan a trip"},
                              output_data={"plan": "Step 1: ..."})
            br_a.record_event("tool_call", "web_search",
                              input_data={"query": "Tokyo hotels"},
                              output_data={"results": [...]},
                              latency_ms=250, cost_usd=0.002)

        # Branch B — challenger agent
        with ar.branch("challenger", model_id="claude-3-opus", temperature=0.5) as br_b:
            br_b.record_event("tool_call", "web_search",
                              input_data={"query": "Tokyo trip"},
                              output_data={"results": [...]})

    # Comparison + trajectory scoring happens automatically on exit
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import ForkmarkClient


class TrajectoryRecorder:
    """Records trace events for one branch of an agent run.

    Used as a context manager inside ``AgentRunContext.branch()``.
    Events are batched and flushed on exit for efficiency.
    """

    def __init__(self, client: "ForkmarkClient", run_id: str,
                 branch_id: str, branch_name: str):
        self._client = client
        self._run_id = run_id
        self._branch_id = branch_id
        self._branch_name = branch_name
        self._events: List[Dict[str, Any]] = []
        self._event_index = 0
        self._parent_stack: List[Optional[str]] = [None]  # stack for nesting

    @property
    def branch_id(self) -> str:
        return self._branch_id

    @property
    def branch_name(self) -> str:
        return self._branch_name

    @property
    def events(self) -> List[Dict[str, Any]]:
        """Return a copy of recorded events (for inspection/testing)."""
        return list(self._events)

    def record_event(
        self,
        event_type: str,
        name: str,
        input_data: Optional[dict] = None,
        output_data: Optional[dict] = None,
        latency_ms: int = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
        cost_usd: Optional[float] = None,
        metadata: Optional[dict] = None,
        status: str = "completed",
    ) -> str:
        """Record a single trace event.

        Parameters
        ----------
        event_type : str
            One of: reasoning, tool_call, tool_result, sub_agent,
            observation, decision, error.
        name : str
            Human-readable label (e.g. tool name).
        input_data, output_data : dict, optional
            Arbitrary payload for this event.
        latency_ms : int
            Wall-clock time in milliseconds.
        tokens_input, tokens_output : int
            Token counts if an LLM call was involved.
        cost_usd : float, optional
            Estimated cost.
        metadata : dict, optional
            Extra data (model_id, temperature, etc.).
        status : str
            Event status: pending, running, completed, failed.

        Returns
        -------
        str
            The generated event ID.
        """
        event_id = f"te_{uuid.uuid4().hex[:12]}"
        event = {
            "id": event_id,
            "branch_id": self._branch_id,
            "run_id": self._run_id,
            "parent_event_id": self._parent_stack[-1],
            "event_type": event_type,
            "event_index": self._event_index,
            "name": name,
            "input_data": input_data or {},
            "output_data": output_data or {},
            "status": status,
            "latency_ms": latency_ms,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "cost_usd": cost_usd,
            "metadata": metadata or {},
        }
        self._events.append(event)
        self._event_index += 1
        return event_id

    @contextmanager
    def nested(self, event_type: str, name: str, **kwargs):
        """Context manager for nested events (sub-agents, tool chains).

        Usage::

            with recorder.nested("sub_agent", "research_agent") as parent_id:
                recorder.record_event("tool_call", "web_search", ...)
                recorder.record_event("tool_call", "summarize", ...)
        """
        parent_id = self.record_event(event_type, name, status="running", **kwargs)
        self._parent_stack.append(parent_id)
        try:
            yield parent_id
        finally:
            self._parent_stack.pop()
            # Update the parent event status to completed
            for ev in self._events:
                if ev["id"] == parent_id:
                    ev["status"] = "completed"
                    break

    def _flush(self) -> None:
        """Send all recorded events to the server in a batch."""
        if not self._events:
            return
        try:
            self._client._post("/api/agent/trace-events/batch", {
                "events": self._events,
            })
        except Exception:
            # If API endpoint isn't available yet, silently continue
            # Events are still stored in self._events for local use
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._flush()
        return False


class AgentRunContext:
    """Context manager for an agent comparison run.

    Manages the lifecycle of a workflow run with run_type='agent',
    creates branches with TrajectoryRecorders, and auto-creates
    a comparison with trajectory scoring on exit.
    """

    def __init__(self, client: "ForkmarkClient", workflow: str,
                 input_data: Optional[dict] = None,
                 metadata: Optional[dict] = None):
        self._client = client
        self._workflow = workflow
        self._input_data = input_data or {}
        self._metadata = metadata or {}
        self._run_id: Optional[str] = None
        self._workflow_id: Optional[str] = None
        self._branches: List[Dict[str, Any]] = []
        self._recorders: List[TrajectoryRecorder] = []

    @property
    def run_id(self) -> Optional[str]:
        return self._run_id

    @property
    def workflow_id(self) -> Optional[str]:
        return self._workflow_id

    @property
    def recorders(self) -> List[TrajectoryRecorder]:
        return list(self._recorders)

    @contextmanager
    def branch(
        self,
        name: str,
        model_id: str = "",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        extra_config: Optional[dict] = None,
        is_baseline: Optional[bool] = None,
    ):
        """Create a branch and return a TrajectoryRecorder.

        The first branch is automatically marked as baseline unless
        ``is_baseline`` is explicitly set.

        Usage::

            with ar.branch("baseline", model_id="gpt-4o") as recorder:
                recorder.record_event("tool_call", "search", ...)
        """
        if is_baseline is None:
            is_baseline = len(self._branches) == 0

        try:
            resp = self._client.create_branch(
                run_id=self._run_id,
                name=name,
                model_id=model_id,
                temperature=temperature,
                system_prompt=system_prompt,
                extra_config=extra_config or {},
                is_baseline=is_baseline,
            )
            branch_id = resp.get("branch_id", resp.get("id", f"br_{uuid.uuid4().hex[:8]}"))
        except Exception:
            branch_id = f"br_{uuid.uuid4().hex[:8]}"

        branch_info = {
            "id": branch_id,
            "name": name,
            "model_id": model_id,
            "is_baseline": is_baseline,
        }
        self._branches.append(branch_info)

        recorder = TrajectoryRecorder(self._client, self._run_id, branch_id, name)
        self._recorders.append(recorder)

        with recorder:
            yield recorder

    def _create_comparison(self) -> Optional[str]:
        """Create a comparison between the first two branches."""
        if len(self._branches) < 2:
            return None
        try:
            resp = self._client._post("/api/agent/comparisons", {
                "run_id": self._run_id,
                "branch_a_id": self._branches[0]["id"],
                "branch_b_id": self._branches[1]["id"],
            })
            return resp.get("comparison_id", resp.get("id"))
        except Exception:
            return None

    def __enter__(self):
        # Start the agent run
        try:
            # Use start_run with metadata indicating agent type
            meta = {**self._metadata, "run_type": "agent"}
            resp = self._client.start_run(
                workflow=self._workflow,
                input_data=self._input_data,
                metadata=meta,
            )
            self._run_id = resp.get("run_id", resp.get("id"))
            self._workflow_id = resp.get("workflow_id")
        except Exception:
            self._run_id = f"run_{uuid.uuid4().hex[:8]}"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"

        # Create comparison if we have at least 2 branches
        comparison_id = self._create_comparison()

        # Complete the run
        try:
            self._client.complete_run(self._run_id, status=status)
        except Exception:
            pass

        return False
