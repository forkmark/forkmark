"""OpenAI client wrapper — auto-logs all completions to Forkmark.

Two usage patterns:

1. Standalone (requires .attach() after run starts)::

    from forkmark.integrations.openai_wrapper import ForkmarkOpenAI
    import forkmark

    forkmark.init(api_key="fm_...", workflow="my-workflow")
    client_a = ForkmarkOpenAI(openai_api_key="sk-...", fm_client=forkmark._default,
                                branch_type="A", step_name="answer")
    client_b = ForkmarkOpenAI(openai_api_key="sk-...", fm_client=forkmark._default,
                                branch_type="B", step_name="answer")

    with forkmark.run("my-workflow") as run:
        client_a.attach(run)
        client_b.attach(run)

        resp_a = client_a.chat.completions.create(model="gpt-4o-mini", messages=[...])
        resp_b = client_b.chat.completions.create(model="gpt-4o",      messages=[...])
    # Comparison auto-created when context exits.

2. Context-bound at construction (simplest)::

    with forkmark.run("my-workflow") as run:
        client_a = ForkmarkOpenAI(openai_api_key="sk-...", fm_client=forkmark._default,
                                    workflow_ctx=run, branch_type="A", step_name="answer")
        client_b = ForkmarkOpenAI(openai_api_key="sk-...", fm_client=forkmark._default,
                                    workflow_ctx=run, branch_type="B", step_name="answer")

        resp_a = client_a.chat.completions.create(model="gpt-4o-mini", messages=[...])
        resp_b = client_b.chat.completions.create(model="gpt-4o",      messages=[...])
"""

from __future__ import annotations
import time
import warnings
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from forkmark.client import ForkmarkClient
    from forkmark.workflow import WorkflowContext


class ForkmarkOpenAI:
    """Drop-in replacement for openai.OpenAI that auto-logs to Forkmark.

    Args:
        openai_api_key:  Your OpenAI API key.
        fm_client:       A ForkmarkClient instance (or forkmark._default after init).
        branch_type:     "A" for baseline branch, "B" for challenger branch.
        step_name:       Name logged for each completion step (default "completion").
        workflow_ctx:    Optional WorkflowContext — bind at construction rather than
                         calling .attach() later.
    """

    def __init__(self, openai_api_key: str, fm_client: "ForkmarkClient",
                 branch_type: str = "A",
                 step_name: str = "completion",
                 workflow_ctx: Optional["WorkflowContext"] = None):
        try:
            from openai import OpenAI
            self._oa = OpenAI(api_key=openai_api_key)
        except ImportError:
            raise ImportError("pip install openai")

        self._fp          = fm_client
        self._branch_type = branch_type.upper()  # "A" or "B"
        self._step_name   = step_name
        self._ctx: Optional["WorkflowContext"] = workflow_ctx
        self.chat = _ChatCompletions(self)

    def _get_async_client(self):
        """Lazily create an AsyncOpenAI client sharing the same API key."""
        if not hasattr(self, "_oa_async") or self._oa_async is None:
            from openai import AsyncOpenAI
            self._oa_async = AsyncOpenAI(api_key=self._oa.api_key)
        return self._oa_async

    def attach(self, workflow_ctx: "WorkflowContext") -> "ForkmarkOpenAI":
        """Bind to a WorkflowContext after the run has started.

        Call this inside the `with forkmark.run(...) as run:` block before
        making any completions.

        Returns self for chaining.
        """
        self._ctx = workflow_ctx
        return self

    def _log(self, messages: list, model: str, temperature: float,
             output: str, tokens_in: int, tokens_out: int, latency_ms: int):
        """Log a completed LLM call to Forkmark via WorkflowContext."""
        if self._ctx is None:
            warnings.warn(
                "ForkmarkOpenAI has no WorkflowContext — LLM call was not logged to Forkmark. "
                "Call .attach(run) inside your 'with forkmark.run(...) as run:' block, "
                "or pass workflow_ctx=run at construction time.",
                stacklevel=3,
            )
            return
        self._ctx.log_step_output(
            name=self._step_name,
            messages=messages,
            output=output,
            model=model,
            temperature=temperature,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            latency_ms=latency_ms,
            branch=self._branch_type,
        )


class _ChatCompletions:
    def __init__(self, parent: ForkmarkOpenAI):
        self._p = parent
        self.completions = self

    def create(self, model: str, messages: list, temperature: float = 0.7, **kwargs):
        """Synchronous chat completion with auto-logging.

        If stream=True is passed, returns a wrapper that accumulates chunks
        and logs the full call on completion.
        """
        stream = kwargs.get("stream", False)

        if stream:
            return self._create_stream(model, messages, temperature, **kwargs)

        t0 = time.time()
        resp = self._p._oa.chat.completions.create(
            model=model, messages=messages, temperature=temperature, **kwargs
        )
        latency = int((time.time() - t0) * 1000)
        output     = resp.choices[0].message.content or ""
        tokens_in  = getattr(resp.usage, "prompt_tokens",     0) if resp.usage else 0
        tokens_out = getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0
        self._p._log(messages, model, temperature, output, tokens_in, tokens_out, latency)
        return resp

    def _create_stream(self, model: str, messages: list, temperature: float, **kwargs):
        """Streaming wrapper: yields chunks, logs the full result on completion."""
        t0 = time.time()
        stream = self._p._oa.chat.completions.create(
            model=model, messages=messages, temperature=temperature, **kwargs
        )
        return _StreamWrapper(stream, self._p, messages, model, temperature, t0)

    async def acreate(self, model: str, messages: list, temperature: float = 0.7, **kwargs):
        """Async chat completion with auto-logging.

        Requires the openai.AsyncOpenAI client — initializes one lazily.
        If stream=True is passed, returns an async wrapper that accumulates
        chunks and logs on completion.
        """
        import asyncio

        stream = kwargs.get("stream", False)
        async_client = self._p._get_async_client()

        if stream:
            return self._acreate_stream(async_client, model, messages, temperature, **kwargs)

        t0 = time.time()
        resp = await async_client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, **kwargs
        )
        latency = int((time.time() - t0) * 1000)
        output     = resp.choices[0].message.content or ""
        tokens_in  = getattr(resp.usage, "prompt_tokens",     0) if resp.usage else 0
        tokens_out = getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0
        self._p._log(messages, model, temperature, output, tokens_in, tokens_out, latency)
        return resp

    def _acreate_stream(self, async_client, model, messages, temperature, **kwargs):
        """Async streaming wrapper."""
        t0 = time.time()
        # Return a coroutine that sets up the stream
        return _AsyncStreamWrapper(async_client, self._p, messages, model, temperature, t0, **kwargs)


class _StreamWrapper:
    """Wraps an OpenAI sync stream to accumulate output and log on completion."""

    def __init__(self, stream, parent: ForkmarkOpenAI, messages: list,
                 model: str, temperature: float, t0: float):
        self._stream = stream
        self._parent = parent
        self._messages = messages
        self._model = model
        self._temperature = temperature
        self._t0 = t0
        self._chunks: list = []

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._stream)
            self._chunks.append(chunk)
            return chunk
        except StopIteration:
            self._finalize()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._finalize()

    def _finalize(self):
        if not self._chunks:
            return
        latency = int((time.time() - self._t0) * 1000)
        output = "".join(
            c.choices[0].delta.content or ""
            for c in self._chunks
            if c.choices and c.choices[0].delta
        )
        # Usage info is typically in the final chunk (with stream_options)
        tokens_in = tokens_out = 0
        for c in reversed(self._chunks):
            if hasattr(c, "usage") and c.usage:
                tokens_in = getattr(c.usage, "prompt_tokens", 0)
                tokens_out = getattr(c.usage, "completion_tokens", 0)
                break
        self._parent._log(self._messages, self._model, self._temperature,
                          output, tokens_in, tokens_out, latency)
        self._chunks = []  # prevent double logging


class _AsyncStreamWrapper:
    """Wraps an OpenAI async stream to accumulate output and log on completion."""

    def __init__(self, async_client, parent: ForkmarkOpenAI, messages: list,
                 model: str, temperature: float, t0: float, **kwargs):
        self._async_client = async_client
        self._parent = parent
        self._messages = messages
        self._model = model
        self._temperature = temperature
        self._t0 = t0
        self._kwargs = kwargs
        self._chunks: list = []
        self._stream = None

    async def __aenter__(self):
        self._stream = await self._async_client.chat.completions.create(
            model=self._model, messages=self._messages,
            temperature=self._temperature, **self._kwargs
        )
        return self

    async def __aexit__(self, *args):
        self._finalize()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._stream is None:
            raise RuntimeError("Use 'async with' to initialize the stream")
        try:
            chunk = await self._stream.__anext__()
            self._chunks.append(chunk)
            return chunk
        except StopAsyncIteration:
            self._finalize()
            raise

    def _finalize(self):
        if not self._chunks:
            return
        latency = int((time.time() - self._t0) * 1000)
        output = "".join(
            c.choices[0].delta.content or ""
            for c in self._chunks
            if c.choices and c.choices[0].delta
        )
        tokens_in = tokens_out = 0
        for c in reversed(self._chunks):
            if hasattr(c, "usage") and c.usage:
                tokens_in = getattr(c.usage, "prompt_tokens", 0)
                tokens_out = getattr(c.usage, "completion_tokens", 0)
                break
        self._parent._log(self._messages, self._model, self._temperature,
                          output, tokens_in, tokens_out, latency)
        self._chunks = []
