"""OpenTelemetry tracing (Keelson).

Traces are exported over OTLP/HTTP to the collector in ``OTEL_EXPORTER_OTLP_ENDPOINT``
(Jaeger, Tempo, Honeycomb, Datadog and others accept it). Without an endpoint nothing is
instrumented and there is no overhead. Projects generated with Logfire do not call this
module: Logfire configures OpenTelemetry itself.

Instrumented: incoming HTTP requests (health checks and metrics excluded), SQLAlchemy queries,
outgoing httpx calls and Redis commands. Log records carry the trace and span ids
(``app/core/logging.py``).
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.core.config import settings
from app.db.session import engine

# Comma-separated regular expressions of paths that produce no spans.
EXCLUDED_URLS = "/health,/metrics"

_provider: TracerProvider | None = None


def tracing_enabled() -> bool:
    return bool(settings.OTEL_EXPORTER_OTLP_ENDPOINT)


def build_provider(processor: SpanProcessor) -> TracerProvider:
    """A tracer provider describing this service, sampling as configured."""
    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    sampler = ParentBased(TraceIdRatioBased(settings.OTEL_TRACES_SAMPLE_RATIO))
    provider = TracerProvider(resource=resource, sampler=sampler)
    provider.add_span_processor(processor)
    return provider


def instrument_app(app: FastAPI, provider: TracerProvider) -> None:
    """Instrument the requests of ``app`` only (tests use it with an in-memory exporter)."""
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=EXCLUDED_URLS)


def setup_tracing(app: FastAPI) -> None:
    """Export traces when an OTLP endpoint is configured. Safe to call more than once."""
    global _provider
    if not tracing_enabled() or _provider is not None:
        return
    endpoint = f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip('/')}/v1/traces"
    _provider = build_provider(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(_provider)
    instrument_app(app, _provider)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=_provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=_provider)
    RedisInstrumentor().instrument(tracer_provider=_provider)


def shutdown_tracing() -> None:
    """Flush the spans still in memory (called when the application stops)."""
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None
