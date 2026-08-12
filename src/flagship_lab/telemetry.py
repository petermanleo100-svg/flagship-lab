from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter


@dataclass(frozen=True)
class TelemetryConfig:
    service_name: str = "flagship-lab"
    service_version: str = "0.5.0"
    otlp_endpoint: str | None = None
    excluded_urls: str = "/health/live,/health/ready,/metrics"


def configure_telemetry(app, engine, config: TelemetryConfig | None = None,
                        span_exporter: SpanExporter | None = None) -> TracerProvider:
    config = config or TelemetryConfig(otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"))
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: config.service_name,
                                                         SERVICE_VERSION: config.service_version}))
    exporter = span_exporter
    if exporter is None and config.otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint, timeout=5)
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=200))
    # App-local provider avoids replacing a provider already installed by an
    # OpenTelemetry Operator or zero-code launcher.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=config.excluded_urls)
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
    app.state.tracer_provider = provider
    return provider


def trace_context() -> tuple[str | None, str | None]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None, None
    return f"{context.trace_id:032x}", f"{context.span_id:016x}"
