import logging

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult, SpanExporter

from flagship_lab.fastapi_app import create_app
from flagship_lab.observability import JsonFormatter
from flagship_lab.telemetry import TelemetryConfig


class MemoryExporter(SpanExporter):
    def __init__(self): self.spans = []
    def export(self, spans): self.spans.extend(spans); return SpanExportResult.SUCCESS
    def shutdown(self): pass


def test_fastapi_and_sqlalchemy_spans_are_exported_and_health_is_excluded(tmp_path):
    exporter = MemoryExporter()
    app = create_app(str(tmp_path / "trace.db"), "telemetry-test-secret-at-least-32-characters",
                     telemetry_config=TelemetryConfig(excluded_urls="/health/live"), span_exporter=exporter)
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    app.state.tracer_provider.force_flush()
    names = [span.name for span in exporter.spans]
    assert any("health/ready" in name for name in names)
    assert not any("health/live" in name for name in names)
    assert any("SELECT" in name for name in names)


def test_json_formatter_contains_trace_correlation_inside_request_span():
    from opentelemetry.sdk.trace import TracerProvider
    provider = TracerProvider(); tracer = provider.get_tracer("test")
    formatter = JsonFormatter()
    with tracer.start_as_current_span("operation"):
        output = formatter.format(logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None))
    assert '"trace_id"' in output and '"span_id"' in output
