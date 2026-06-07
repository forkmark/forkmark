"""EvalRunContext — batch evaluation over a list of test inputs.

Usage (sequential)::

    import forkmark

    forkmark.init(api_key="fm_...")

    test_inputs = [
        {"label": "formal-email",  "text": "Dear Sir/Madam..."},
        {"label": "casual-slack",  "text": "hey quick q..."},
    ]

    with forkmark.eval_run(
        name="GPT-4o-mini vs GPT-4o — summarisation",
        workflow="email-summariser",
        branch_a={"label": "GPT-4o-mini", "model_id": "gpt-4o-mini", "temperature": 0.3},
        branch_b={"label": "GPT-4o",      "model_id": "gpt-4o",      "temperature": 0.3},
        inputs=test_inputs,
    ) as er:
        for case in er:
            summary_a = case.step(
                "summarise",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": case.input["text"]}],
                call_fn=my_openai_fn,
            )
            summary_b = case.branch_step(
                "summarise",
                model="gpt-4o",
                messages=[{"role": "user", "content": case.input["text"]}],
                call_fn=my_openai_fn,
            )

Usage (parallel — 4x–10x faster for large batches)::

    with forkmark.eval_run(..., inputs=test_inputs) as er:
        def run_case(case):
            case.step("summarise", model="gpt-4o-mini", messages=[...], call_fn=fn)
            case.branch_step("summarise", model="gpt-4o", messages=[...], call_fn=fn)

        er.run(run_case, max_workers=8)

    print(er.stats)
"""

from __future__ import annotations
import sys
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Iterator, Callable
from .workflow import WorkflowContext

if TYPE_CHECKING:
    from .client import ForkmarkClient


class EvalCase:
    """A single test case within a batch eval run.

    Wraps a WorkflowContext and passes through .step() / .branch_step() calls.
    Also exposes the raw input data as .input.
    """

    def __init__(self, ctx: WorkflowContext, input_data: dict, label: str, index: int):
        self._ctx   = ctx
        self.input  = input_data
        self.label  = label
        self.index  = index

    def step(self, name: str, model: str, messages: List[dict],
             temperature: float = 0.7, system_prompt: str = None,
             call_fn=None) -> str:
        """Run baseline branch step (Branch A) for this test case."""
        return self._ctx.step(name, model, messages,
                              temperature=temperature,
                              system_prompt=system_prompt,
                              call_fn=call_fn)

    def branch_step(self, name: str, model: str, messages: List[dict],
                    temperature: float = 0.7, system_prompt: str = None,
                    call_fn=None) -> str:
        """Run challenger branch step (Branch B) for this test case."""
        return self._ctx.branch_step(name, model, messages,
                                     temperature=temperature,
                                     system_prompt=system_prompt,
                                     call_fn=call_fn)

    @property
    def run_id(self) -> str:
        return self._ctx.run_id


class EvalRunContext:
    """Context manager for a batch evaluation run.

    Creates one WorkflowContext (and therefore one comparison) per input.
    Handles error isolation — a failure on one case doesn't abort the batch.

    Two execution modes:
      - Sequential iterator:  for case in er: ...
      - Parallel:             er.run(fn, max_workers=N)
    """

    def __init__(self, client: "ForkmarkClient", name: str, workflow: str,
                 branch_a: dict, branch_b: dict,
                 inputs: List[Dict[str, Any]],
                 description: str = ""):
        self._client      = client
        self._name        = name
        self._workflow    = workflow
        self._branch_a    = branch_a
        self._branch_b    = branch_b
        self._inputs      = inputs
        self._description = description
        self.eval_run_id: Optional[str] = None
        self._completed   = 0
        self._failed      = 0

    def __enter__(self) -> "EvalRunContext":
        resp = self._client.create_eval_run(
            workflow_name=self._workflow,
            name=self._name,
            description=self._description,
            branch_a_config=self._branch_a,
            branch_b_config=self._branch_b,
            total_cases=len(self._inputs),
        )
        self.eval_run_id = resp["id"]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"
        self._client.complete_eval_run(
            self.eval_run_id,
            status=status,
            total_cases=self._completed + self._failed,
        )
        return False  # don't suppress exceptions

    def __iter__(self) -> Iterator[EvalCase]:
        """Sequential iterator — yields one EvalCase at a time.

        Each iteration:
          1. Starts a workflow run linked to this eval run
          2. Yields EvalCase (caller runs their workflow steps)
          3. Completes the run and auto-creates the comparison on exit

        Errors on individual cases are caught, logged to stderr, and skipped
        so a single bad input doesn't abort the whole batch.
        """
        for i, input_data in enumerate(self._inputs):
            label = input_data.get("label", f"case-{i+1}")
            wf_ctx = WorkflowContext(
                self._client,
                workflow=self._workflow,
                input_data=input_data,
                eval_run_id=self.eval_run_id,
                test_case_label=label,
            )
            try:
                with wf_ctx:
                    yield EvalCase(wf_ctx, input_data, label, i)
                self._completed += 1
            except Exception as e:
                self._failed += 1
                print(f"[forkmark] case {i+1}/{len(self._inputs)} ({label}) failed: {e}",
                      file=sys.stderr)

    def run(self, fn: Callable[["EvalCase"], None], max_workers: int = 4) -> "EvalRunContext":
        """Parallel execution — runs all cases concurrently via ThreadPoolExecutor.

        Args:
            fn:          Callable that receives an EvalCase and runs the eval steps.
                         It should call case.step() / case.branch_step() inside.
            max_workers: Number of concurrent workers. Each worker runs one case at
                         a time. Recommended: 4–8 for API-bound workloads.

        Returns:
            self — so you can inspect er.stats after completion.

        Example::

            with forkmark.eval_run(..., inputs=cases) as er:
                def process(case):
                    case.step("classify", model="gpt-4o-mini", messages=[...], call_fn=fn)
                    case.branch_step("classify", model="gpt-4o", messages=[...], call_fn=fn)

                er.run(process, max_workers=8)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_one(input_data: dict, i: int) -> bool:
            label = input_data.get("label", f"case-{i+1}")
            wf_ctx = WorkflowContext(
                self._client,
                workflow=self._workflow,
                input_data=input_data,
                eval_run_id=self.eval_run_id,
                test_case_label=label,
            )
            try:
                with wf_ctx:
                    fn(EvalCase(wf_ctx, input_data, label, i))
                return True
            except Exception as e:
                print(
                    f"[forkmark] case {i+1}/{len(self._inputs)} ({label}) failed: {e}",
                    file=sys.stderr,
                )
                return False

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_run_one, inp, i): i
                for i, inp in enumerate(self._inputs)
            }
            for future in as_completed(futures):
                if future.result():
                    self._completed += 1
                else:
                    self._failed += 1

        return self

    @property
    def stats(self) -> dict:
        return {
            "eval_run_id": self.eval_run_id,
            "total":       len(self._inputs),
            "completed":   self._completed,
            "failed":      self._failed,
        }
