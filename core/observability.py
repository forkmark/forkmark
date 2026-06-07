"""Observability stack — structured logging, metrics, distributed tracing.

Three pillars:
    1. Structured logging (JSON) with correlation IDs
    2. Prometheus metrics (request latency, queue depth, error rates)
    3. OpenTelemetry tracing (request spans, DB spans, evaluator spans)

Middleware auto-attaches:
    - X-Request-ID header (generated if missing)
    - Correlation ID propagated to all downstream calls
    - Request duration histogram
    - Error counter

Usage:
    from core.observability import setup_observability, get_metrics

    # At app startup:
    setup_observability(app)

    # In endpoints:
    metrics = get_metrics()
    metrics.scoring_started.inc()

    # Structured log (correlation ID auto-attached):
    logger.info("scoring_complete", extra={"comp_id": "xxx", "duration_ms": 450})
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("forkmark")


# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter with correlation ID support."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        if hasattr(record, "workspace_id"):
            log_data["workspace_id"] = record.workspace_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id

        # Add any extra fields
        for key in ("comp_id", "duration_ms", "status_code", "method", "path",
                    "error", "event", "org_id"):
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(level: str = "INFO", json_format: bool = True):
    """Configure structured logging for the application."""
    root_logger = logging.getLogger("forkmark")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
        ))

    root_logger.handlers = [handler]
    return root_logger


# ---------------------------------------------------------------------------
# Prometheus-compatible metrics
# ---------------------------------------------------------------------------

class Metrics:
    """Application metrics exposed at /metrics endpoint.

    Uses simple counters/histograms. In production, replace with
    prometheus_client library for proper Prometheus exposition format.
    """

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, list] = {}

    def inc(self, name: str, labels: Optional[dict] = None, value: int = 1):
        """Increment a counter."""
        key = self._key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def observe(self, name: str, value: float, labels: Optional[dict] = None):
        """Record a histogram observation."""
        key = self._key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        # Keep only last 1000 observations per metric
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-500:]

    def get_counter(self, name: str, labels: Optional[dict] = None) -> int:
        return self._counters.get(self._key(name, labels), 0)

    def get_histogram_avg(self, name: str, labels: Optional[dict] = None) -> float:
        key = self._key(name, labels)
        values = self._histograms.get(key, [])
        return sum(values) / len(values) if values else 0.0

    def get_histogram_p95(self, name: str, labels: Optional[dict] = None) -> float:
        key = self._key(name, labels)
        values = sorted(self._histograms.get(key, []))
        if not values:
            return 0.0
        idx = int(len(values) * 0.95)
        return values[min(idx, len(values) - 1)]

    def snapshot(self) -> dict:
        """Return all metrics as a dict (for /metrics endpoint)."""
        result = {"counters": dict(self._counters), "histograms": {}}
        for key, values in self._histograms.items():
            if values:
                sorted_v = sorted(values)
                result["histograms"][key] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "p50": sorted_v[len(sorted_v) // 2],
                    "p95": sorted_v[int(len(sorted_v) * 0.95)],
                    "p99": sorted_v[int(len(sorted_v) * 0.99)],
                    "max": sorted_v[-1],
                }
        return result

    def _key(self, name: str, labels: Optional[dict]) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Singleton metrics instance
_metrics: Optional[Metrics] = None


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics()
    return _metrics


# ---------------------------------------------------------------------------
# Request tracing middleware
# ---------------------------------------------------------------------------

class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Adds correlation ID, request timing, and metrics to every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id

        # Start timing
        start_time = time.time()

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            metrics = get_metrics()
            metrics.inc("http_requests_total", {"status": "500", "method": request.method})
            metrics.observe("http_request_duration_ms", duration_ms, {"path": request.url.path})
            logger.error(
                "request_error",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                },
            )
            raise

        # Record metrics
        duration_ms = (time.time() - start_time) * 1000
        metrics = get_metrics()
        metrics.inc("http_requests_total", {
            "status": str(response.status_code),
            "method": request.method,
        })
        metrics.observe("http_request_duration_ms", duration_ms, {
            "path": self._normalize_path(request.url.path),
        })

        # Attach correlation ID to response
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))

        # Log request (skip health checks to reduce noise)
        if not request.url.path.startswith("/health"):
            logger.info(
                "request_complete",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

        return response

    def _normalize_path(self, path: str) -> str:
        """Normalize path for metric labels (collapse IDs to :id)."""
        parts = path.strip("/").split("/")
        normalized = []
        for part in parts:
            # Replace UUIDs and hex IDs with placeholder
            if len(part) > 20 or (len(part) > 8 and all(c in "0123456789abcdef-" for c in part)):
                normalized.append(":id")
            else:
                normalized.append(part)
        return "/" + "/".join(normalized)


# ---------------------------------------------------------------------------
# Setup function
# ---------------------------------------------------------------------------

def setup_observability(app: FastAPI):
    """Wire observability into FastAPI app.

    Call once at startup. Adds:
        - ObservabilityMiddleware (correlation ID, timing, metrics)
        - /metrics endpoint
        - Structured JSON logging
    """
    # Setup logging
    log_level = os.getenv("FM_LOG_LEVEL", "INFO")
    json_logs = os.getenv("FM_LOG_FORMAT", "json") == "json"
    setup_logging(level=log_level, json_format=json_logs)

    # Add middleware
    app.add_middleware(ObservabilityMiddleware)

    # Metrics endpoint
    @app.get("/metrics", tags=["ops"])
    async def metrics_endpoint():
        return get_metrics().snapshot()

    # Setup OpenTelemetry tracing if SDK is installed
    _setup_otel_tracing(app)

    logger.info("Observability configured: level=%s json=%s otel=%s",
                log_level, json_logs, _has_otel())


# ---------------------------------------------------------------------------
# OpenTelemetry integration
# ---------------------------------------------------------------------------

def _has_otel() -> bool:
    """Check if OpenTelemetry SDK is available."""
    try:
        from opentelemetry import trace  # noqa: F401
        return True
    except ImportError:
        return False


def _setup_otel_tracing(app: FastAPI):
    """Initialize OpenTelemetry if the SDK is installed.

    Requires:
        pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

    Env vars:
        OTEL_SERVICE_NAME:         service name (default: "forkmark")
        OTEL_EXPORTER_OTLP_ENDPOINT: collector endpoint (default: http://localhost:4317)
        FM_OTEL_ENABLED:          set to "true" to enable (default: auto-detect SDK)
    """
    if os.getenv("FM_OTEL_ENABLED", "").lower() == "false":
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.debug("OpenTelemetry SDK not installed — tracing disabled")
        return

    # Configure exporter — try OTLP gRPC, fall back to console
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter()
        logger.info("OTel: using OTLP gRPC exporter")
    except ImportError:
        try:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            exporter = ConsoleSpanExporter()
            logger.info("OTel: OTLP exporter not found, using console exporter")
        except ImportError:
            logger.warning("OTel: no exporter available — tracing disabled")
            return

    service_name = os.getenv("OTEL_SERVICE_NAME", "forkmark")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    logger.info("OTel tracing initialized: service=%s", service_name)


def get_tracer(name: str = "forkmark"):
    """Get an OTel tracer (returns a no-op tracer if OTel is not installed)."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpSpan:
    """Minimal no-op span for when OTel is not installed."""
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def record_exception(self, exc): pass
    def end(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _NoOpTracer:
    """Minimal no-op tracer for when OTel is not installed."""
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()
    def start_span(self, name, **kwargs):
        return _NoOpSpan()


def trace_llm_call(model: str, messages: list, output: str,
                   latency_ms: int = 0, tokens_in: int = 0,
                   tokens_out: int = 0, temperature: float = 0.0,
                   error: str = None):
    """Record an LLM call as an OTel span with GenAI semantic conventions.

    Uses OpenTelemetry GenAI semantic conventions (experimental):
    https://opentelemetry.io/docs/specs/semconv/gen-ai/

    This is the bridge between Forkmark's SDK integrations and OTel.
    """
    tracer = get_tracer("forkmark.genai")
    with tracer.start_as_current_span("gen_ai.chat") as span:
        # GenAI semantic conventions
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.request.temperature", temperature)
        span.set_attribute("gen_ai.response.model", model)
        span.set_attribute("gen_ai.usage.input_tokens", tokens_in)
        span.set_attribute("gen_ai.usage.output_tokens", tokens_out)

        # Forkmark-specific attributes
        span.set_attribute("forkmark.latency_ms", latency_ms)
        span.set_attribute("forkmark.message_count", len(messages) if messages else 0)

        if error:
            span.set_attribute("error", True)
            span.set_attribute("error.message", error)
            try:
                from opentelemetry.trace import StatusCode
                span.set_status(StatusCode.ERROR, error)
            except ImportError:
                pass


def trace_eval_run(eval_run_id: str, workflow_id: str, evaluator_names: list,
                   total_comparisons: int = 0, duration_ms: int = 0):
    """Record an eval run as an OTel span."""
    tracer = get_tracer("forkmark.eval")
    with tracer.start_as_current_span("forkmark.eval_run") as span:
        span.set_attribute("forkmark.eval_run.id", eval_run_id)
        span.set_attribute("forkmark.eval_run.workflow_id", workflow_id)
        span.set_attribute("forkmark.eval_run.evaluators", ",".join(evaluator_names))
        span.set_attribute("forkmark.eval_run.comparisons", total_comparisons)
        span.set_attribute("forkmark.eval_run.duration_ms", duration_ms)


def trace_scoring(comparison_id: str, scorer_name: str, score: float,
                  latency_ms: int = 0):
    """Record a divergence scoring operation as an OTel span."""
    tracer = get_tracer("forkmark.scoring")
    with tracer.start_as_current_span("forkmark.divergence_score") as span:
        span.set_attribute("forkmark.scoring.comparison_id", comparison_id)
        span.set_attribute("forkmark.scoring.scorer", scorer_name)
        span.set_attribute("forkmark.scoring.score", score)
        span.set_attribute("forkmark.scoring.latency_ms", latency_ms)
