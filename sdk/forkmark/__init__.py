"""Forkmark SDK — instrument your AI workflows in 3 lines."""
__version__ = "0.1.2"

from .client import ForkmarkClient
from .workflow import WorkflowContext
from .evalrun import EvalRunContext, EvalCase
from .agent import AgentRunContext, TrajectoryRecorder

# Optional integrations — imported lazily so missing optional deps don't break import
try:
    from .integrations.openai_wrapper import ForkmarkOpenAI
except ImportError:
    ForkmarkOpenAI = None  # type: ignore

try:
    from .integrations.langchain_callback import ForkmarkCallbackHandler
except ImportError:
    ForkmarkCallbackHandler = None  # type: ignore

try:
    from .integrations.anthropic_wrapper import ForkmarkAnthropic
except ImportError:
    ForkmarkAnthropic = None  # type: ignore

_default: ForkmarkClient | None = None


def init(api_key: str, base_url: str = "http://127.0.0.1:7700",
         workflow: str = None) -> ForkmarkClient:
    """Initialise the global Forkmark client.

    Args:
        api_key:  Your Forkmark API key (fm_...).
        base_url: Forkmark server URL (default: local).
        workflow: Default workflow name for all subsequent calls.
    """
    global _default
    _default = ForkmarkClient(api_key=api_key, base_url=base_url,
                                default_workflow=workflow)
    return _default


def run(workflow: str = None, input_data: dict = None,
        evaluator_configs: list = None) -> WorkflowContext:
    """Start a single workflow run context manager.

    Usage::

        with forkmark.run("support-triage", input_data={"ticket": text},
                           evaluator_configs=[{"name": "json_schema"}]) as wf:
            out_a = wf.step("classify", model="gpt-4o-mini", messages=[...], call_fn=fn)
            out_b = wf.branch_step("classify", model="gpt-4o", messages=[...], call_fn=fn)
    """
    if _default is None:
        raise RuntimeError("Call forkmark.init() first.")
    return _default.run(workflow=workflow, input_data=input_data,
                        evaluator_configs=evaluator_configs)


def eval_run(name: str, workflow: str = None,
             branch_a: dict = None, branch_b: dict = None,
             inputs: list = None, description: str = "") -> EvalRunContext:
    """Run a batch evaluation over a list of test inputs.

    Usage::

        with forkmark.eval_run(
            name="GPT-4o-mini vs GPT-4o — Q3 support tickets",
            workflow="support-triage",
            branch_a={"label": "GPT-4o-mini", "model_id": "gpt-4o-mini", "temperature": 0.3},
            branch_b={"label": "GPT-4o",      "model_id": "gpt-4o",      "temperature": 0.3},
            inputs=my_test_cases,   # list of dicts, add "label" key to name each case
        ) as er:
            for case in er:
                out_a = case.step(
                    "classify",
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": case.input["ticket"]}],
                    call_fn=openai_fn,
                )
                out_b = case.branch_step(
                    "classify",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": case.input["ticket"]}],
                    call_fn=openai_fn,
                )

        print(f"Done — {er.stats['completed']} cases. Open Forkmark UI to review.")
    """
    if _default is None:
        raise RuntimeError("Call forkmark.init() first.")
    return _default.eval_run(
        name=name, workflow=workflow, branch_a=branch_a,
        branch_b=branch_b, inputs=inputs, description=description,
    )


def agent_run(workflow: str = None, input_data: dict = None,
              metadata: dict = None) -> AgentRunContext:
    """Start an agent comparison run.

    Usage::

        with forkmark.agent_run("my-agent", input_data={"query": "..."}) as ar:
            with ar.branch("baseline", model_id="gpt-4o") as br_a:
                br_a.record_event("tool_call", "search", ...)
            with ar.branch("challenger", model_id="claude-3") as br_b:
                br_b.record_event("tool_call", "search", ...)
    """
    if _default is None:
        raise RuntimeError("Call forkmark.init() first.")
    return _default.agent_run(workflow=workflow, input_data=input_data,
                               metadata=metadata)


__all__ = [
    "__version__",
    "init", "run", "eval_run", "agent_run",
    "ForkmarkClient", "WorkflowContext", "EvalRunContext", "EvalCase",
    "AgentRunContext", "TrajectoryRecorder",
    "ForkmarkOpenAI", "ForkmarkCallbackHandler", "ForkmarkAnthropic",
]
