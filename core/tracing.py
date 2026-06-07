"""Forkmark OpenTelemetry tracing — optional integration.

When opentelemetry is installed and FM_ENABLE_OTEL=true, Forkmark creates
spans for each LLM step with standard GenAI semantic conventions:
    gen_ai.system, gen_ai.request.model, gen_ai.usage.input_tokens, etc.

This allows Forkmark steps to appear in your existing application traces
(e.g. from LangChain, LlamaIndex, or custom OTel instrumentation).

If opentelemetry is not installed, all functions are no-ops.

Usage:
    tracer = ForkmarkTracer()

    with tracer.step_span("classify", model_id="gpt-4o", temperature=0.7) as span:
        # ... make LLM call ...
        tracer.record_step_result(span, tokens_in=100, tokens_out=50, latency_ms=200)

    trace_id, span_id = tracer.get_ids(span)
"""
from __future__ import annotations

import os
from typing import Optional, Any

_OTEL_ENABLED = os.getenv("FM_ENABLE_OTEL", "false").lower() == "true"

# Try to import OpenTelemetry — graceful no-op if not installed
_tracer = None
_trace_api = None
_has_otel = False

if _OTEL_ENABLED:
    try:
        from opentelemetry import trace as _trace_api_mod
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        _trace_api = _trace_api_mod

        # Only set up provider if none exists yet (don't conflict with app-level setup)
        if not isinstance(_trace_api.get_tracer_provider(), TracerProvider):
            resource = Resource.create({"service.name": "forkmark"})
            provider = TracerProvider(resource=resource)
            _trace_api.set_tracer_provider(provider)

        _tracer = _trace_api.get_tracer("forkmark", "0.1.0")
        _has_otel = True
    except ImportError:
        pass


class _NoOpSpan:
    """No-op span for when OTel is not available."""
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass


class ForkmarkTracer:
    """Lightweight wrapper around OpenTelemetry for LLM step tracing.

    All methods are safe to call regardless of whether OTel is installed.
    """

    @property
    def enabled(self) -> bool:
        return _has_otel

    def step_span(
        self,
        step_name: str,
        model_id: str = "",
        temperature: float = 0.0,
        branch_name: str = "",
        run_id: str = "",
    ):
        """Create a span for an LLM step.

        Returns a context manager (real OTel span or no-op).
        """
        if not _has_otel or _tracer is None:
            return _NoOpSpan()

        span = _tracer.start_span(
            name=f"forkmark.step.{step_name}",
            attributes={
                "gen_ai.system": "forkmark",
                "gen_ai.request.model": model_id,
                "gen_ai.request.temperature": temperature,
                "forkmark.step_name": step_name,
                "forkmark.branch": branch_name,
                "forkmark.run_id": run_id,
            },
        )
        return _trace_api.use_span(span, end_on_exit=True)

    def record_step_result(
        self,
        span: Any,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Record LLM call results on an active span."""
        if not _has_otel:
            return

        real_span = getattr(span, '_span', span)
        if hasattr(real_span, 'set_attribute'):
            real_span.set_attribute("gen_ai.usage.input_tokens", tokens_in)
            real_span.set_attribute("gen_ai.usage.output_tokens", tokens_out)
            real_span.set_attribute("forkmark.latency_ms", latency_ms)
            if error:
                real_span.set_attribute("error", True)
                real_span.set_attribute("error.message", error)

    def get_ids(self, span: Any) -> tuple:
        """Extract trace_id and span_id from a span.

        Returns:
            (trace_id, span_id) as hex strings, or (None, None) if unavailable.
        """
        if not _has_otel:
            return (None, None)

        real_span = getattr(span, '_span', span)
        ctx = getattr(real_span, 'get_span_context', lambda: None)()
        if ctx is None:
            return (None, None)

        trace_id = format(ctx.trace_id, '032x') if ctx.trace_id else None
        span_id = format(ctx.span_id, '016x') if ctx.span_id else None
        return (trace_id, span_id)

    def inject_context(self, trace_id: Optional[str] = None,
                       span_id: Optional[str] = None):
        """Create a span context from external trace/span IDs.

        Allows linking Forkmark operations to an existing distributed trace
        from LangChain, LlamaIndex, or any OTel-instrumented application.
        """
        if not _has_otel or not trace_id or not span_id:
            return _NoOpSpan()

        try:
            from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
            ctx = SpanContext(
                trace_id=int(trace_id, 16),
                span_id=int(span_id, 16),
                is_remote=True,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
            parent = NonRecordingSpan(ctx)
            from opentelemetry.context import attach
            from opentelemetry.trace import set_span_in_context
            token = attach(set_span_in_context(parent))
            return token
        except Exception:
            return _NoOpSpan()


# Module-level singleton
tracer = ForkmarkTracer()
