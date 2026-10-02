import json
import os
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_provider_ready = False
memory_exporter = InMemorySpanExporter()


def setup_tracing() -> InMemorySpanExporter:
    """Install one tracer provider. Tests read memory_exporter."""
    global _provider_ready
    if not _provider_ready:
        provider = TracerProvider(resource=Resource.create({"service.name": "agents"}))
        provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
        trace.set_tracer_provider(provider)
        _provider_ready = True
    return memory_exporter


def record(name: str, attributes: dict) -> None:
    """Write a redacted local trace line and an in-process span.

    Attributes must already exclude prompt text, CV text, and token text.
    """
    setup_tracing()
    tracer = trace.get_tracer("agents")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    path = Path(os.environ.get("TRACE_PATH", "data/local/traces.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"name": name, "attributes": attributes}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")
