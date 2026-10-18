"""OpenTelemetry export: every agent step becomes a span, every run a parent span.

Off by default and harmless if the OpenTelemetry packages are missing. Turn it on with:
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006      (Arize Phoenix, Jaeger, any OTLP collector)
Then any OTel-compatible viewer shows runs as traces: one run = one trace, one step = one span.

Attributes follow plain names (agentops.*) plus the standard gen_ai.usage.* token counters.
"""
import os

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Status, StatusCode
    AVAILABLE = True
except ImportError:  # packages not installed: telemetry becomes a no-op
    AVAILABLE = False

_tracer = None
_runs = {}  # run_id -> (run span, context)


def setup(exporter=None, processor=None):
    """Start telemetry. Returns True if it is on.

    exporter / processor are for tests (an in-memory exporter). With neither given, the OTLP
    exporter is used only when OTEL_EXPORTER_OTLP_ENDPOINT is set."""
    global _tracer
    if not AVAILABLE:
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": "agentops-breaker"}))
    if processor is not None:
        provider.add_span_processor(processor)
    elif exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/")
        if not endpoint.endswith("/v1/traces"):
            endpoint += "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    else:
        return False
    _tracer = provider.get_tracer("agentops")
    return True


def enabled():
    return _tracer is not None


def run_started(run_id, agent_id, agent):
    if not enabled():
        return
    span = _tracer.start_span(f"run {agent}", attributes={
        "agentops.run_id": run_id, "agentops.agent_id": agent_id, "agentops.agent": agent})
    _runs[run_id] = (span, trace.set_span_in_context(span))


def step(run_id, step_no, tool, tokens, cost, status, trust_score=None):
    """One finished step -> one child span of the run."""
    if not enabled() or run_id not in _runs:
        return
    attrs = {"agentops.step": step_no, "agentops.tool": tool, "agentops.status": status,
             "agentops.cost_usd": float(cost), "gen_ai.usage.total_tokens": int(tokens)}
    if trust_score is not None:
        attrs["agentops.trust_score"] = int(trust_score)
    span = _tracer.start_span(f"step {step_no}: {tool}", context=_runs[run_id][1], attributes=attrs)
    if status in ("quarantined", "rejected", "error"):
        span.set_status(Status(StatusCode.ERROR, status))
    span.end()


def run_finished(run_id, status, reason=None, total_tokens=0, total_cost=0.0):
    if not enabled() or run_id not in _runs:
        return
    span, _ = _runs.pop(run_id)
    span.set_attribute("agentops.final_status", status)
    span.set_attribute("agentops.total_tokens", int(total_tokens))
    span.set_attribute("agentops.total_cost_usd", float(total_cost))
    if reason:
        span.set_attribute("agentops.stop_reason", reason)
    if status in ("tripped", "quarantined", "killed", "error"):
        span.set_status(Status(StatusCode.ERROR, reason or status))
    span.end()
