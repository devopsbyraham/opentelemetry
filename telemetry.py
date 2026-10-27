"""
telemetry.py - the ONE place where OpenTelemetry is configured.

Every service calls setup_telemetry(...) once at startup. After that:
  * incoming HTTP requests automatically create spans        (FlaskInstrumentor)
  * outgoing HTTP calls automatically create spans AND
    inject the trace context into HTTP headers               (RequestsInstrumentor)
  * every log line gets trace_id / span_id attached          (LoggingInstrumentor)

Set OTEL_EXPORTER=console to print telemetry to the terminal (no backend needed).
Default is OTLP -> OpenTelemetry Collector.
"""
import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_telemetry(service_name: str, app):
    # 1) RESOURCE = "who is sending this data?"  Attached to every span/metric.
    resource = Resource.create(
        {
            "service.name": service_name,          # the most important attribute
            "service.version": "1.0.0",
            "deployment.environment": os.getenv("ENV", "dev"),
        }
    )

    use_console = os.getenv("OTEL_EXPORTER", "otlp") == "console"

    # 2) EXPORTERS = "where does the data go?"
    if use_console:
        span_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()
    else:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        # Endpoint comes from env var OTEL_EXPORTER_OTLP_ENDPOINT
        # (set in docker-compose.yml -> http://otel-collector:4317)
        span_exporter = OTLPSpanExporter()
        metric_exporter = OTLPMetricExporter()

    # 3) TRACING pipeline: Tracer -> SpanProcessor (batches) -> Exporter
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # 4) METRICS pipeline: Meter -> MetricReader (every 5s) -> Exporter
    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    # 5) LOG CORRELATION: adds otelTraceID / otelSpanID to every log record
    LoggingInstrumentor().instrument(set_logging_format=True)
    logging.getLogger().setLevel(logging.INFO)

    # 6) AUTO-INSTRUMENTATION: no manual code needed for HTTP in/out
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

    return trace.get_tracer(service_name), metrics.get_meter(service_name)
