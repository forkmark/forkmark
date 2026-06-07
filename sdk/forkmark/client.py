"""Forkmark HTTP client with retry and exponential backoff."""
from __future__ import annotations
import time
from typing import Optional, List, Dict, Any
import httpx

from .workflow import WorkflowContext
from .evalrun import EvalRunContext
from .agent import AgentRunContext

# Retry policy: up to 3 total attempts on transient errors (429 / 5xx).
# Delay schedule: 0.5 s, 1 s, 2 s (2^attempt * 0.5).
_RETRY_ATTEMPTS = 3
_RETRY_BASE_S   = 0.5
_RETRY_ON       = {429, 500, 502, 503, 504}


class ForkmarkClient:
    def __init__(self, api_key: str, base_url: str = "http://127.0.0.1:7700",
                 default_workflow: str = None, timeout: float = 30.0):
        self.api_key          = api_key
        self.base_url         = base_url.rstrip("/")
        self.default_workflow = default_workflow
        self._timeout         = timeout
        # Persistent connection pool — reuses TCP connections across requests
        self._session = httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        )

    def close(self):
        """Close the underlying HTTP connection pool."""
        self._session.close()

    @property
    def _headers(self):
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    # ── HTTP helpers with retry ───────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body)

    def _get(self, path: str, params: dict = None) -> dict:
        return self._request("GET", path, params=params)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """HTTP request with exponential backoff retry on transient failures.

        Retries on: 429 Too Many Requests, 5xx Server Errors.
        Raises immediately on: 4xx Client Errors (except 429).
        """
        last_exc: Optional[Exception] = None

        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self._session.request(
                    method, path,
                    **kwargs,
                )
                if resp.status_code in _RETRY_ON and attempt < _RETRY_ATTEMPTS - 1:
                    # Transient error — back off and retry
                    delay = _RETRY_BASE_S * (2 ** attempt)
                    # Honour Retry-After header if present (rate limit)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    time.sleep(delay)
                    continue

                resp.raise_for_status()
                if resp.status_code == 204:
                    return {}
                ct = resp.headers.get("content-type", "")
                if "application/json" in ct or "ndjson" in ct:
                    return resp.json()
                return {}

            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    time.sleep(_RETRY_BASE_S * (2 ** attempt))
            except httpx.HTTPStatusError:
                raise
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    time.sleep(_RETRY_BASE_S * (2 ** attempt))

        raise RuntimeError(
            f"Forkmark request failed after {_RETRY_ATTEMPTS} attempts: {last_exc}"
        )

    # ── Single workflow run ───────────────────────────────────────────────────

    def start_run(self, workflow: str, input_data: dict = None,
                  metadata: dict = None, eval_run_id: str = None,
                  test_case_label: str = "") -> dict:
        return self._post("/api/sdk/runs", {
            "workflow_name":   workflow or self.default_workflow,
            "input_data":      input_data or {},
            "metadata":        metadata or {},
            "eval_run_id":     eval_run_id,
            "test_case_label": test_case_label,
        })

    def complete_run(self, run_id: str, status: str = "completed"):
        return self._post(f"/api/sdk/runs/{run_id}/complete", {"status": status})

    def create_branch(self, run_id: str, name: str, model_id: str,
                      temperature: float = 0.7, system_prompt: str = None,
                      extra_config: dict = None, is_baseline: bool = False) -> dict:
        return self._post("/api/sdk/branches", {
            "run_id": run_id, "name": name, "model_id": model_id,
            "temperature": temperature, "system_prompt": system_prompt,
            "extra_config": extra_config or {}, "is_baseline": is_baseline,
        })

    def log_step(self, run_id: str, branch_id: str, step_name: str,
                 step_index: int, input_messages: list, output_text: str,
                 model_id: str, temperature: float = 0.7,
                 tokens_input: int = 0, tokens_output: int = 0,
                 latency_ms: int = 0, error: str = None) -> dict:
        return self._post("/api/sdk/steps", {
            "run_id": run_id, "branch_id": branch_id,
            "step_name": step_name, "step_index": step_index,
            "input_messages": input_messages, "output_text": output_text,
            "model_id": model_id, "temperature": temperature,
            "tokens_input": tokens_input, "tokens_output": tokens_output,
            "latency_ms": latency_ms, "error": error,
        })

    def log_steps_batch(self, steps: List[Dict[str, Any]]) -> list:
        """Log multiple steps in a single API request (max 100 per batch handled automatically)."""
        if not steps:
            return []
        results = []
        for i in range(0, len(steps), 100):
            chunk = steps[i:i + 100]
            resp = self._post("/api/sdk/steps/batch", {"steps": chunk})
            if isinstance(resp, list):
                results.extend(resp)
        return results

    def create_comparison(self, run_id: str, branch_a_id: str,
                          branch_b_id: str, step_names: list = None,
                          evaluator_configs: list = None) -> dict:
        return self._post("/api/sdk/comparisons", {
            "run_id": run_id, "branch_a_id": branch_a_id,
            "branch_b_id": branch_b_id, "step_names": step_names or [],
            "evaluator_configs": evaluator_configs or [],
        })

    def poll_score_status(self, comparison_id: str) -> dict:
        """Get current scoring status of a comparison.

        Returns dict with keys: scoring_status, divergence_score,
        step_divergence_scores, eval_results.
        """
        return self._get(f"/api/comparisons/{comparison_id}/score-status")

    def wait_for_scoring(self, comparison_id: str,
                         timeout_s: float = 60.0,
                         poll_interval_s: float = 1.0) -> dict:
        """Block until scoring completes or times out.

        Args:
            comparison_id:  The comparison to wait on.
            timeout_s:      Max seconds to wait (default 60).
            poll_interval_s: Seconds between polls (default 1).

        Returns:
            The final score-status dict.

        Raises:
            TimeoutError: If scoring doesn't complete within timeout.
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = self.poll_score_status(comparison_id)
            if status.get("scoring_status") in ("completed", "failed"):
                return status
            time.sleep(poll_interval_s)
        raise TimeoutError(
            f"Scoring for comparison {comparison_id} did not complete "
            f"within {timeout_s}s"
        )

    def run(self, workflow: str = None, input_data: dict = None,
            evaluator_configs: list = None) -> WorkflowContext:
        return WorkflowContext(self, workflow=workflow or self.default_workflow,
                               input_data=input_data,
                               evaluator_configs=evaluator_configs)

    # ── Batch eval run ────────────────────────────────────────────────────────

    def create_eval_run(self, workflow_name: str, name: str,
                        branch_a_config: dict, branch_b_config: dict,
                        description: str = "", test_set_id: str = None,
                        total_cases: int = 0) -> dict:
        return self._post("/api/sdk/eval-runs", {
            "workflow_name":   workflow_name or self.default_workflow,
            "name":            name,
            "description":     description,
            "branch_a_config": branch_a_config,
            "branch_b_config": branch_b_config,
            "test_set_id":     test_set_id,
            "total_cases":     total_cases,
        })

    def complete_eval_run(self, er_id: str, status: str = "completed",
                          total_cases: int = None) -> dict:
        return self._post(f"/api/sdk/eval-runs/{er_id}/complete", {
            "status":      status,
            "total_cases": total_cases,
        })

    def eval_run(self, name: str, workflow: str = None,
                 branch_a: dict = None, branch_b: dict = None,
                 inputs: List[Dict[str, Any]] = None,
                 description: str = "") -> EvalRunContext:
        """Create and return an EvalRunContext for batch evaluation."""
        return EvalRunContext(
            client=self,
            name=name,
            workflow=workflow or self.default_workflow,
            branch_a=branch_a or {},
            branch_b=branch_b or {},
            inputs=inputs or [],
            description=description,
        )

    # ── Agent comparison run ─────────────────────────────────────────────────

    def agent_run(self, workflow: str = None,
                  input_data: dict = None,
                  metadata: dict = None) -> AgentRunContext:
        """Start an agent comparison run.

        Usage::

            with client.agent_run(workflow="my-agent",
                                   input_data={"query": "..."}) as ar:
                with ar.branch("baseline", model_id="gpt-4o") as br_a:
                    br_a.record_event("tool_call", "search", ...)
                with ar.branch("challenger", model_id="claude-3") as br_b:
                    br_b.record_event("tool_call", "search", ...)
        """
        return AgentRunContext(
            client=self,
            workflow=workflow or self.default_workflow,
            input_data=input_data,
            metadata=metadata,
        )
