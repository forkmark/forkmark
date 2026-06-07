"""Anthropic client wrapper — auto-logs all completions to Forkmark.

Usage::

    from forkmark.integrations.anthropic_wrapper import ForkmarkAnthropic
    import forkmark

    forkmark.init(api_key="fm_...", workflow="my-workflow")
    client_a = ForkmarkAnthropic(anthropic_api_key="sk-ant-...",
                                   fm_client=forkmark._default,
                                   branch_type="A", step_name="answer")
    client_b = ForkmarkAnthropic(anthropic_api_key="sk-ant-...",
                                   fm_client=forkmark._default,
                                   branch_type="B", step_name="answer")

    with forkmark.run("my-workflow") as run:
        client_a.attach(run)
        client_b.attach(run)

        resp_a = client_a.messages.create(model="claude-sonnet-4-20250514", ...)
        resp_b = client_b.messages.create(model="claude-opus-4-20250514", ...)
"""

from __future__ import annotations
import time
import warnings
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from forkmark.client import ForkmarkClient
    from forkmark.workflow import WorkflowContext


class ForkmarkAnthropic:
    """Drop-in replacement for anthropic.Anthropic that auto-logs to Forkmark.

    Args:
        anthropic_api_key: Your Anthropic API key.
        fm_client:         A ForkmarkClient instance.
        branch_type:       "A" for baseline, "B" for challenger.
        step_name:         Name logged for each step (default "completion").
        workflow_ctx:      Optional WorkflowContext — bind at construction.
    """

    def __init__(self, anthropic_api_key: str, fm_client: "ForkmarkClient",
                 branch_type: str = "A",
                 step_name: str = "completion",
                 workflow_ctx: Optional["WorkflowContext"] = None):
        try:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=anthropic_api_key)
        except ImportError:
            raise ImportError("pip install anthropic")

        self._fp = fm_client
        self._branch_type = branch_type.upper()
        self._step_name = step_name
        self._ctx: Optional["WorkflowContext"] = workflow_ctx
        self._api_key = anthropic_api_key
        self.messages = _Messages(self)

    def _get_async_client(self):
        """Lazily create an AsyncAnthropic client."""
        if not hasattr(self, "_async_client") or self._async_client is None:
            from anthropic import AsyncAnthropic
            self._async_client = AsyncAnthropic(api_key=self._api_key)
        return self._async_client

    def attach(self, workflow_ctx: "WorkflowContext") -> "ForkmarkAnthropic":
        """Bind to a WorkflowContext after the run has started."""
        self._ctx = workflow_ctx
        return self

    def _log(self, messages: list, model: str, temperature: float,
             output: str, tokens_in: int, tokens_out: int, latency_ms: int):
        """Log a completed LLM call to Forkmark."""
        if self._ctx is None:
            warnings.warn(
                "ForkmarkAnthropic has no WorkflowContext — call was not logged. "
                "Call .attach(run) inside your 'with forkmark.run(...)' block.",
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


class _Messages:
    """Wraps the Anthropic messages API with Forkmark auto-logging."""

    def __init__(self, parent: ForkmarkAnthropic):
        self._p = parent

    def create(self, model: str, messages: list, max_tokens: int = 1024,
               temperature: float = 0.7, system: str = None, **kwargs):
        """Synchronous message creation with auto-logging.

        If stream=True, returns a streaming wrapper that logs on completion.
        """
        stream = kwargs.pop("stream", False)

        if stream:
            return self._create_stream(model, messages, max_tokens, temperature,
                                       system=system, **kwargs)

        t0 = time.time()
        api_kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                          temperature=temperature, **kwargs)
        if system:
            api_kwargs["system"] = system

        resp = self._p._client.messages.create(**api_kwargs)
        latency = int((time.time() - t0) * 1000)

        output = _extract_text(resp)
        tokens_in = getattr(resp.usage, "input_tokens", 0)
        tokens_out = getattr(resp.usage, "output_tokens", 0)

        # Build OpenAI-format messages for Forkmark's CompareView
        fm_messages = _to_fm_messages(messages, system)
        self._p._log(fm_messages, model, temperature, output, tokens_in, tokens_out, latency)
        return resp

    def _create_stream(self, model, messages, max_tokens, temperature,
                       system=None, **kwargs):
        """Sync streaming wrapper."""
        t0 = time.time()
        api_kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                          temperature=temperature, stream=True, **kwargs)
        if system:
            api_kwargs["system"] = system

        stream = self._p._client.messages.create(**api_kwargs)
        fm_messages = _to_fm_messages(messages, system)
        return _StreamWrapper(stream, self._p, fm_messages, model, temperature, t0)

    async def acreate(self, model: str, messages: list, max_tokens: int = 1024,
                      temperature: float = 0.7, system: str = None, **kwargs):
        """Async message creation with auto-logging.

        If stream=True, returns an async streaming wrapper.
        """
        stream = kwargs.pop("stream", False)
        async_client = self._p._get_async_client()

        if stream:
            return _AsyncStreamWrapper(
                async_client, self._p,
                _to_fm_messages(messages, system),
                model, messages, max_tokens, temperature,
                system=system, **kwargs
            )

        t0 = time.time()
        api_kwargs = dict(model=model, messages=messages, max_tokens=max_tokens,
                          temperature=temperature, **kwargs)
        if system:
            api_kwargs["system"] = system

        resp = await async_client.messages.create(**api_kwargs)
        latency = int((time.time() - t0) * 1000)

        output = _extract_text(resp)
        tokens_in = getattr(resp.usage, "input_tokens", 0)
        tokens_out = getattr(resp.usage, "output_tokens", 0)

        fm_messages = _to_fm_messages(messages, system)
        self._p._log(fm_messages, model, temperature, output, tokens_in, tokens_out, latency)
        return resp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(resp) -> str:
    """Extract text content from an Anthropic Message response."""
    parts = []
    for block in getattr(resp, "content", []):
        if hasattr(block, "text"):
            parts.append(block.text)
    return " ".join(parts)


def _to_fm_messages(messages: list, system: str = None) -> list:
    """Convert Anthropic messages format to OpenAI-style for Forkmark's CompareView."""
    fm_messages = []
    if system:
        fm_messages.append({"role": "system", "content": system})
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Anthropic multi-part content — extract text blocks
            text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
            content = " ".join(text_parts)
        fm_messages.append({"role": role, "content": content})
    return fm_messages


class _StreamWrapper:
    """Wraps an Anthropic sync stream to accumulate output and log on completion."""

    def __init__(self, stream, parent: ForkmarkAnthropic, fm_messages: list,
                 model: str, temperature: float, t0: float):
        self._stream = stream
        self._parent = parent
        self._fm_messages = fm_messages
        self._model = model
        self._temperature = temperature
        self._t0 = t0
        self._text_parts: list = []
        self._tokens_in = 0
        self._tokens_out = 0
        self._finalized = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self._stream)
            self._accumulate(event)
            return event
        except StopIteration:
            self._finalize()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._finalize()

    def _accumulate(self, event):
        """Accumulate text deltas and usage from stream events."""
        event_type = getattr(event, "type", "")
        if event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta and hasattr(delta, "text"):
                self._text_parts.append(delta.text)
        elif event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg and hasattr(msg, "usage"):
                self._tokens_in = getattr(msg.usage, "input_tokens", 0)
        elif event_type == "message_delta":
            usage = getattr(event, "usage", None)
            if usage:
                self._tokens_out = getattr(usage, "output_tokens", 0)

    def _finalize(self):
        if self._finalized:
            return
        self._finalized = True
        latency = int((time.time() - self._t0) * 1000)
        output = "".join(self._text_parts)
        self._parent._log(self._fm_messages, self._model, self._temperature,
                          output, self._tokens_in, self._tokens_out, latency)


class _AsyncStreamWrapper:
    """Wraps an Anthropic async stream to accumulate output and log on completion."""

    def __init__(self, async_client, parent: ForkmarkAnthropic, fm_messages: list,
                 model: str, messages: list, max_tokens: int, temperature: float,
                 system: str = None, **kwargs):
        self._async_client = async_client
        self._parent = parent
        self._fm_messages = fm_messages
        self._model = model
        self._messages = messages
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._system = system
        self._kwargs = kwargs
        self._text_parts: list = []
        self._tokens_in = 0
        self._tokens_out = 0
        self._t0 = time.time()
        self._stream = None
        self._finalized = False

    async def __aenter__(self):
        api_kwargs = dict(model=self._model, messages=self._messages,
                          max_tokens=self._max_tokens, temperature=self._temperature,
                          stream=True, **self._kwargs)
        if self._system:
            api_kwargs["system"] = self._system
        self._stream = await self._async_client.messages.create(**api_kwargs)
        return self

    async def __aexit__(self, *args):
        self._finalize()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._stream is None:
            raise RuntimeError("Use 'async with' to initialize the stream")
        try:
            event = await self._stream.__anext__()
            self._accumulate(event)
            return event
        except StopAsyncIteration:
            self._finalize()
            raise

    def _accumulate(self, event):
        event_type = getattr(event, "type", "")
        if event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta and hasattr(delta, "text"):
                self._text_parts.append(delta.text)
        elif event_type == "message_start":
            msg = getattr(event, "message", None)
            if msg and hasattr(msg, "usage"):
                self._tokens_in = getattr(msg.usage, "input_tokens", 0)
        elif event_type == "message_delta":
            usage = getattr(event, "usage", None)
            if usage:
                self._tokens_out = getattr(usage, "output_tokens", 0)

    def _finalize(self):
        if self._finalized:
            return
        self._finalized = True
        latency = int((time.time() - self._t0) * 1000)
        output = "".join(self._text_parts)
        self._parent._log(self._fm_messages, self._model, self._temperature,
                          output, self._tokens_in, self._tokens_out, latency)
