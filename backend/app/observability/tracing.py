"""Per-call LLM tracing, exported to Langfuse over OTLP.

Every model call in this app goes through pydantic-ai, which emits
OpenTelemetry spans natively when instrumented. Langfuse accepts OTLP. So
tracing is a wiring job, not an instrumentation job: turn on pydantic-ai's
instrumentation, point an OTLP exporter at Langfuse, and every agent run,
tool call, grounding judge call and rerank appears
with its prompt, its completion and its token counts.

Instrumenting pydantic-ai once covers every agent, including ones added
later, so there are no spans to remember to place by hand.

Silent no-op when the keys are unset, like every other optional integration
(AGENTS.md), so nothing here is required to run locally.
"""

import base64

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)

_started = False


def configure_tracing() -> bool:
    """Wire pydantic-ai's spans to Langfuse. Returns whether it did.

    Safe to call more than once; only the first call does anything.
    """
    global _started
    if _started:
        return True
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from pydantic_ai import Agent
    except ImportError:
        log.warning("tracing.unavailable", reason="opentelemetry or pydantic-ai missing")
        return False

    auth = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "deployment.environment": settings.environment,
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{settings.langfuse_host.rstrip('/')}/api/public/otel/v1/traces",
                headers={"Authorization": f"Basic {auth}"},
            )
        )
    )
    trace.set_tracer_provider(provider)

    # One call covers every agent in the app, including ones added later.
    # Per-agent instrumentation would need remembering at each new call site.
    Agent.instrument_all()

    _started = True
    log.info("tracing.enabled", exporter="langfuse", host=settings.langfuse_host)
    return True


def flush_tracing() -> None:
    """Force pending spans out. For scripts, which exit before the batch
    processor's timer fires and would otherwise lose the whole run."""
    if not _started:
        return
    try:
        from opentelemetry import trace

        force_flush = getattr(trace.get_tracer_provider(), "force_flush", None)
        if callable(force_flush):
            force_flush()
    except Exception:  # noqa: BLE001 -- flushing traces must not fail an exit
        log.exception("tracing.flush_failed")
