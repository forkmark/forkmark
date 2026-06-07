"""WorkflowContext — the primary SDK interface for users."""
from __future__ import annotations
import time
from typing import TYPE_CHECKING, Optional, List, Tuple, Union

if TYPE_CHECKING:
    from .client import ForkmarkClient


class StepRunner:
    """Represents one branch's execution context within a run."""
    def __init__(self, ctx: "WorkflowContext", branch_id: str,
                 model_id: str, temperature: float, system_prompt: str = None):
        self._ctx = ctx
        self.branch_id = branch_id
        self.model_id = model_id
        self.temperature = temperature
        self.system_prompt = system_prompt
        self._step_index = 0

    def step(self, name: str, messages: List[dict],
             model_id: str = None, temperature: float = None,
             call_fn=None) -> str:
        """Execute and log one LLM step.

        Args:
            name:        Step name (e.g. "classify_intent").
            messages:    OpenAI-format message list.
            model_id:    Override branch model for this step.
            temperature: Override branch temperature.
            call_fn:     Callable invoked as call_fn(messages, model, temperature).
                         May return either:
                           - str: the output text (tokens default to 0)
                           - (str, int, int): (output, tokens_input, tokens_output)
                         If None, returns a placeholder string.
        Returns:
            The LLM output string.
        """
        model = model_id or self.model_id
        temp  = temperature if temperature is not None else self.temperature
        msgs  = messages
        if self.system_prompt and not any(m.get("role") == "system" for m in msgs):
            msgs = [{"role": "system", "content": self.system_prompt}] + msgs

        t0 = time.time()
        output, tokens_in, tokens_out, error = "", 0, 0, None
        caught_exc = None
        try:
            if call_fn:
                result = call_fn(msgs, model, temp)
                # Support both str and (str, tokens_in, tokens_out) return types
                if isinstance(result, tuple) and len(result) == 3:
                    output, tokens_in, tokens_out = result
                    output = str(output)
                    tokens_in  = int(tokens_in  or 0)
                    tokens_out = int(tokens_out or 0)
                else:
                    output = str(result) if result is not None else ""
            else:
                output = "[no call_fn provided — set output manually]"
        except Exception as e:
            error = str(e)
            caught_exc = e
        latency = int((time.time() - t0) * 1000)

        self._ctx._pending_steps.append({
            "run_id": self._ctx._run_id,
            "branch_id": self.branch_id,
            "step_name": name,
            "step_index": self._step_index,
            "input_messages": msgs,
            "output_text": output,
            "model_id": model,
            "temperature": temp,
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "latency_ms": latency,
            "error": error,
        })
        self._ctx._record_step_name(name)
        self._step_index += 1

        # Log the error to Forkmark but re-raise so callers know it failed
        if caught_exc is not None:
            raise caught_exc

        return output

    def log_output(self, name: str, messages: List[dict], output: str,
                   model_id: str = None, temperature: float = None,
                   tokens_input: int = 0, tokens_output: int = 0,
                   latency_ms: int = 0) -> str:
        """Directly log a pre-executed step without calling an LLM.

        Use this when you've already made the LLM call yourself (e.g. via
        ForkmarkOpenAI) and just want to record the output.
        """
        model = model_id or self.model_id
        temp  = temperature if temperature is not None else self.temperature
        self._ctx._pending_steps.append({
            "run_id": self._ctx._run_id,
            "branch_id": self.branch_id,
            "step_name": name,
            "step_index": self._step_index,
            "input_messages": messages,
            "output_text": output,
            "model_id": model,
            "temperature": temp,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "latency_ms": latency_ms,
            "error": None,
        })
        self._ctx._record_step_name(name)
        self._step_index += 1
        return output


class WorkflowContext:
    """Context manager for a Forkmark workflow run.

    Usage::

        with forkmark.run("my-workflow", input_data={"q": "..."}) as run:
            # Baseline branch (A) — call_fn can return str or (str, tokens_in, tokens_out)
            out_a = run.step("answer", model="gpt-4o", messages=[...],
                              call_fn=my_openai_fn)
            # Challenger branch (B)
            out_b = run.branch_step("answer", model="claude-3-5-sonnet",
                                     messages=[...], call_fn=my_anthropic_fn)
            # Comparison is auto-created when context exits
    """

    def __init__(self, client: "ForkmarkClient", workflow: str,
                 input_data: dict = None,
                 eval_run_id: str = None,
                 test_case_label: str = "",
                 evaluator_configs: list = None):
        self._client          = client
        self._workflow        = workflow
        self._input           = input_data or {}
        self._eval_run_id     = eval_run_id
        self._test_case_label = test_case_label
        self._evaluator_configs = evaluator_configs or []
        self._run_id: Optional[str] = None
        self._branches: List[StepRunner] = []
        self._baseline: Optional[StepRunner] = None
        self._challenger: Optional[StepRunner] = None
        self._step_names: List[str] = []   # ordered, deduped step names seen this run
        self._pending_steps: List[dict] = [] # steps accumulated for batch insertion
        self._comparison_id: Optional[str] = None  # set after comparison is created

    def __enter__(self) -> "WorkflowContext":
        resp = self._client.start_run(
            self._workflow, self._input,
            eval_run_id=self._eval_run_id,
            test_case_label=self._test_case_label,
        )
        self._run_id = resp["id"]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "failed" if exc_type else "completed"
        
        # Flush all accumulated steps in a single batch request
        if self._pending_steps:
            self._client.log_steps_batch(self._pending_steps)
            self._pending_steps.clear()

        self._client.complete_run(self._run_id, status)
        # Only create comparison for successful runs — a failed run may have
        # incomplete step outputs that would produce meaningless divergence scores
        # and pollute eval run stats with noise.
        if exc_type is None and self._baseline and self._challenger:
            resp = self._client.create_comparison(
                run_id=self._run_id,
                branch_a_id=self._baseline.branch_id,
                branch_b_id=self._challenger.branch_id,
                step_names=self._step_names,
                evaluator_configs=self._evaluator_configs,
            )
            self._comparison_id = resp.get("id")
        return False  # don't suppress exceptions

    @property
    def comparison_id(self) -> Optional[str]:
        """The comparison ID created when the context exited (None if not yet created)."""
        return self._comparison_id

    @property
    def run_id(self) -> str:
        return self._run_id

    def _record_step_name(self, name: str) -> None:
        """Track unique step names in call order for create_comparison."""
        if name not in self._step_names:
            self._step_names.append(name)

    def _make_branch(self, name: str, model_id: str, temperature: float = 0.7,
                     system_prompt: str = None, is_baseline: bool = False) -> StepRunner:
        resp = self._client.create_branch(
            run_id=self._run_id, name=name, model_id=model_id,
            temperature=temperature, system_prompt=system_prompt,
            is_baseline=is_baseline,
        )
        runner = StepRunner(self, resp["id"], model_id, temperature, system_prompt)
        self._branches.append(runner)
        return runner

    def _ensure_baseline(self, model: str, temperature: float,
                         system_prompt: str = None) -> StepRunner:
        if not self._baseline:
            self._baseline = self._make_branch(
                name=f"{model}@{temperature}", model_id=model,
                temperature=temperature, system_prompt=system_prompt,
                is_baseline=True,
            )
        return self._baseline

    def _ensure_challenger(self, model: str, temperature: float,
                           system_prompt: str = None) -> StepRunner:
        if not self._challenger:
            self._challenger = self._make_branch(
                name=f"{model}@{temperature}", model_id=model,
                temperature=temperature, system_prompt=system_prompt,
                is_baseline=False,
            )
        return self._challenger

    def step(self, name: str, model: str, messages: List[dict],
             temperature: float = 0.7, system_prompt: str = None,
             call_fn=None) -> str:
        """Run baseline branch step (Branch A)."""
        runner = self._ensure_baseline(model, temperature, system_prompt)
        return runner.step(name, messages, model_id=model,
                           temperature=temperature, call_fn=call_fn)

    def branch_step(self, name: str, model: str, messages: List[dict],
                    temperature: float = 0.7, system_prompt: str = None,
                    call_fn=None) -> str:
        """Run challenger branch step (Branch B)."""
        runner = self._ensure_challenger(model, temperature, system_prompt)
        return runner.step(name, messages, model_id=model,
                           temperature=temperature, call_fn=call_fn)

    def log_step_output(self, name: str, messages: List[dict], output: str,
                        model: str = None, temperature: float = 0.7,
                        tokens_input: int = 0, tokens_output: int = 0,
                        latency_ms: int = 0, branch: str = "A") -> str:
        """Directly log a pre-executed LLM output without calling anything.

        Use this with ForkmarkOpenAI or any wrapper that makes LLM calls
        independently and needs to register the output with Forkmark.

        Args:
            branch: "A" for baseline, "B" for challenger.
        """
        if branch == "A":
            runner = self._ensure_baseline(model or "unknown", temperature)
        else:
            runner = self._ensure_challenger(model or "unknown", temperature)
        return runner.log_output(
            name=name, messages=messages, output=output,
            model_id=model, temperature=temperature,
            tokens_input=tokens_input, tokens_output=tokens_output,
            latency_ms=latency_ms,
        )
