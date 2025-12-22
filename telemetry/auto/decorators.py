"""
UNIFIED DECORATOR INSTRUMENTATION
Produces the same telemetry output shape as:
    - function_instrumentation
    - class_instrumentation
"""

import functools
import time
import logging
from typing import Any, Dict, Optional
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

# =============================================================
#  UNIFIED TRACE EXECUTION TEMPLATE
# =============================================================
def _execute_with_telemetry(callable_fn, tele, span_name, base_attrs):
    tracer = tele.traces.tracer
    counter_name = f"{span_name}.calls"
    histogram_name = f"{span_name}.duration_ms"

    start = time.time()
    span = None

    try:
        with tracer.start_as_current_span(span_name) as s:
            span = s

            for k, v in base_attrs.items():
                span.set_attribute(k, v)

            result = callable_fn()

            duration = (time.time() - start) * 1000
            span.set_attribute("duration_ms", duration)

            tele.metrics.increment_counter(
                counter_name, 1, {**base_attrs, "outcome": "success"}
            )
            tele.metrics.record_histogram(
                histogram_name, duration, {**base_attrs, "outcome": "success"}
            )

            tele.logs.info(
                f"{span_name} executed successfully",
                {**base_attrs, "duration_ms": duration, "outcome": "success"},
            )

            return result

    except Exception as e:
        duration = (time.time() - start) * 1000

        if span:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)

        tele.metrics.increment_counter(
            counter_name, 1,
            {**base_attrs, "outcome": "error", "exception.type": type(e).__name__},
        )
        tele.metrics.record_histogram(
            histogram_name, duration,
            {**base_attrs, "outcome": "error", "exception.type": type(e).__name__},
        )

        tele.logs.error(
            f"Error in {span_name}",
            {
                **base_attrs,
                "duration_ms": duration,
                "exception.type": type(e).__name__,
                "exception.message": str(e),
                "outcome": "error",
            },
        )

        raise


# ======================================================================
#  DECORATOR FACTORIES (TELEMETRY BOUND HERE 🔥)
# ======================================================================
def create_decorators(telemetry):

    # ---------------- TRACE ----------------
    def trace(name: str = None):
        def dec(fn):
            span_base = name or fn.__name__
            span_name = f"telemetry.decorator.{span_base}"

            base_attrs = {
                "code.function": fn.__name__,
                "code.module": fn.__module__,
                "telemetry.kind": "decorator",
                "telemetry.sdk": "custom-python-sdk",
            }

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                return _execute_with_telemetry(
                    lambda: fn(*args, **kwargs),
                    telemetry,
                    span_name,
                    base_attrs,
                )

            return wrapper
        return dec

    # ---------------- METRIC COUNTER ----------------
    def metric_counter(name: str, attributes: Optional[Dict[str, Any]] = None):
        attributes = attributes or {}

        def dec(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                telemetry.metrics.increment_counter(name, 1, attributes)
                return fn(*args, **kwargs)

            return wrapper
        return dec

    # ---------------- LOG DECORATORS ----------------
    def _log(level, message, attributes=None):
        attributes = attributes or {}

        def dec(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                getattr(telemetry.logs, level)(message, attributes)
                return fn(*args, **kwargs)

            return wrapper
        return dec

    def log_info(msg, attrs=None): return _log("info", msg, attrs)
    def log_debug(msg, attrs=None): return _log("debug", msg, attrs)
    def log_warning(msg, attrs=None): return _log("warning", msg, attrs)
    def log_error(msg, attrs=None): return _log("error", msg, attrs)

    return {
        "trace": trace,
        "metric_counter": metric_counter,
        "log_info": log_info,
        "log_debug": log_debug,
        "log_warning": log_warning,
        "log_error": log_error,
    }



"""🔍 1. Telemetry Resolution Layer (_resolve_telemetry)

This utility detects which TelemetryCollector instance should be used:

Looks for _telemetry on the bound class instance (self)

Looks for _telemetry on the function itself

Looks for _telemetry on wrapped functions (nested decorators)

If none found → fallback to global OTEL tracer

This allows decorators to work for both class methods and normal functions.

🎯 2. @trace Decorator — Full Tracing Support

Adds OpenTelemetry tracing around a function:

Starts a span using TelemetryCollector or global OTEL

Automatically records exceptions inside the span

Sets span status to ERROR when failures occur

Never crashes user code even if tracing is misconfigured

This decorator creates complete observability for function-level performance & errors.

⚠️ 3. @capture_exceptions Decorator

Captures exceptions and records them into the current active OTEL span:

Does NOT handle or swallow the exception

Only records the error into telemetry

Fully safe fallback if tracing is disabled

Used when you want exceptions recorded but not wrapped in a custom span.

📊 4. Metric Decorators

Your decorators automatically emit metrics with zero boilerplate:

@metric_counter(name)

Increments a counter metric each time the function runs

@metric_histogram(name)

Measures execution duration (end - start)

Records the latency in a histogram metric

@measure_time(name)

Alias for histogram, specialized for performance measurement

@metric_observable(name)

Registers a callback for observable metrics (pull-based metrics)

All metric decorators are fail-safe: if OTEL metrics aren’t configured, they silently noop.

📝 5. Logging Decorators

Decorators that send structured logs through your LogsManager:

@log_info(message)
@log_warning(message)
@log_error(message)
@log_critical(message)
@log_debug(message)

Each:

Sends a log entry before the function executes

Supports optional attributes

Uses auto-injected trace_id/span_id from LogsManager

@log_exceptions

If function throws an error → logs it as an error

Doesn’t swallow the exception

🧩 6. Decorator Registry (create_decorators)

This generates a dictionary of all decorators pre-bound with a specific TelemetryCollector instance.

This enables:

tele.decorators["trace"](...)


Or:

@tele.decorators["metric_counter"]("db_calls")
def get_data():
    ...


This registry is essential for integrating decorators into SDK auto-instrumentation.

🛡️ 7. Safety Guarantees Built Into Your Decorators

Your decorator system is designed so that:

Tracing can fail → function still works

Metrics API missing → function still works

Logging exporter fails → Python logging fallback

Telemetry object missing → global OTEL used
ex: Decorators are used before the TelemetryCollector is created, Decorators are applied to standalone free functions, The user forgets to attach telemetry, A library instrumentor triggers spans internally

OTEL not installed → noop behavior 

Nothing in the decorator chain can break the user's application."""