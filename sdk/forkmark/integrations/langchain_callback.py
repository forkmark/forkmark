"""LangChain callback handler — auto-logs LLM calls to Forkmark.

Fixes vs. original:
  - Captures the actual prompt from on_llm_start (was always logging []).
  - Reads temperature from the serialized LLM config (was hardcoded 0.7).
  - Cleans up _t0 / _prompts dicts on both success and error paths.
"""
from __future__ import annotations
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from forkmark.client import ForkmarkClient


class ForkmarkCallbackHandler:
    """LangChain callback that ships LLM calls to Forkmark.

    Usage::

        from forkmark.integrations.langchain_callback import ForkmarkCallbackHandler
        import forkmark

        fp = forkmark.init(api_key="fm_...", workflow="my-chain")
        handler = ForkmarkCallbackHandler(fm_client=fp,
                                            run_id="...", branch_id="...")

        llm = ChatOpenAI(callbacks=[handler])
        chain = prompt | llm
    """

    def __init__(self, fm_client: "ForkmarkClient",
                 run_id: str, branch_id: str, step_name: str = "llm_call"):
        self._fp          = fm_client
        self._run_id      = run_id
        self._branch_id   = branch_id
        self._step_name   = step_name
        self._step_index  = 0
        # Per LangChain run_id: start timestamps and captured prompts
        self._t0:      Dict[str, float]      = {}
        self._prompts: Dict[str, List[dict]] = {}

    def on_llm_start(self, serialized: Dict, prompts: List[str], **kwargs):
        """Capture start time and prompts keyed by LangChain's internal run_id."""
        run_id_str = str(kwargs.get("run_id", uuid.uuid4()))
        self._t0[run_id_str] = time.time()

        # Convert bare prompt strings to OpenAI-format message dicts so they
        # render correctly in Forkmark's CompareView.
        self._prompts[run_id_str] = [
            {"role": "user", "content": p} for p in (prompts or [])
        ]

    def on_llm_end(self, response, **kwargs):
        run_id_str = str(kwargs.get("run_id", ""))
        latency    = int((time.time() - self._t0.pop(run_id_str, time.time())) * 1000)
        messages   = self._prompts.pop(run_id_str, [])

        # Pull actual temperature from the LLM output metadata when available
        temperature = 0.7
        llm_output  = getattr(response, "llm_output", {}) or {}
        if "temperature" in llm_output:
            try:
                temperature = float(llm_output["temperature"])
            except (TypeError, ValueError):
                pass

        for gen_list in response.generations:
            for gen in gen_list:
                output = gen.text if hasattr(gen, "text") else str(gen)
                model  = llm_output.get("model_name", "unknown")
                self._fp.log_step(
                    run_id=self._run_id,
                    branch_id=self._branch_id,
                    step_name=self._step_name,
                    step_index=self._step_index,
                    input_messages=messages,
                    output_text=output,
                    model_id=model,
                    temperature=temperature,
                    latency_ms=latency,
                )
                self._step_index += 1

    def on_llm_error(self, error: Exception, **kwargs):
        run_id_str = str(kwargs.get("run_id", ""))
        messages   = self._prompts.pop(run_id_str, [])
        self._t0.pop(run_id_str, None)

        self._fp.log_step(
            run_id=self._run_id,
            branch_id=self._branch_id,
            step_name=self._step_name,
            step_index=self._step_index,
            input_messages=messages,
            output_text="",
            model_id="unknown",
            error=str(error),
        )
        self._step_index += 1
