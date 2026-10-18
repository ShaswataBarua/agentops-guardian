import time

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

import telemetry  # noqa: E402
from test_all import start, wait  # noqa: E402  (shared helpers; also sets up the test database)


@pytest.fixture()
def spans():
    exporter = InMemorySpanExporter()
    assert telemetry.setup(processor=SimpleSpanProcessor(exporter))
    yield exporter
    telemetry._tracer = None            # turn telemetry off again for the other tests


def attrs(span):
    return dict(span.attributes)


def test_run_becomes_one_trace_with_one_span_per_step(spans):
    rid = start("looper")               # trips at step 3 -> 2 executed steps
    wait(rid, {"tripped"})
    time.sleep(0.1)
    finished = spans.get_finished_spans()
    run_spans = [s for s in finished if s.name == "run looper"]
    step_spans = [s for s in finished if s.name.startswith("step ")]
    assert len(run_spans) == 1 and len(step_spans) == 2
    run = run_spans[0]
    assert attrs(run)["agentops.final_status"] == "tripped"
    assert attrs(run)["agentops.total_tokens"] == 4000
    assert attrs(run)["agentops.stop_reason"].startswith("loop:")
    assert not run.status.is_ok
    # every step span is a child of the run span, in the same trace
    for s in step_spans:
        assert s.parent.span_id == run.context.span_id
        assert s.context.trace_id == run.context.trace_id
    assert attrs(step_spans[0])["agentops.tool"] == "lookup_order"
    assert attrs(step_spans[0])["gen_ai.usage.total_tokens"] == 2000


def test_healthy_run_has_ok_status(spans):
    rid = start("normal")
    wait(rid, {"done"})
    time.sleep(0.1)
    run = [s for s in spans.get_finished_spans() if s.name == "run normal"][0]
    assert attrs(run)["agentops.final_status"] == "done"
    assert run.status.is_ok or run.status.status_code.name == "UNSET"


def test_telemetry_off_changes_nothing():
    assert not telemetry.enabled()
    d = wait(start("normal"), {"done"})
    assert d["run"]["status"] == "done"
