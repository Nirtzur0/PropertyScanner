"""
OpenTelemetry instrumentation — thin wrapper for tracing service boundaries.

Usage::

    from src.platform.observability import trace_span

    with trace_span("valuation.evaluate_deal", listing_id=listing.id):
        result = service.evaluate_deal(listing)

When OpenTelemetry is not installed or not configured, the wrapper is a no-op
(zero overhead). This keeps instrumentation code in the codebase without
forcing the dependency in dev environments.
"""

from __future__ import annotations

import contextlib
from typing import Any, Generator

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("property_scanner")
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False
    _tracer = None


@contextlib.contextmanager
def trace_span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Context manager that creates an OpenTelemetry span (no-op if OTEL absent)."""
    if _HAS_OTEL and _tracer is not None:
        with _tracer.start_as_current_span(name, attributes=attributes) as span:
            yield span
    else:
        yield None


def record_exception(exc: BaseException) -> None:
    """Record an exception on the current span, if any."""
    if not _HAS_OTEL:
        return
    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exc)
        span.set_status(trace.StatusCode.ERROR, str(exc))
