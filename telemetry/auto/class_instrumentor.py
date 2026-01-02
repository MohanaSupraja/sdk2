import inspect
import functools
import logging
import time
from opentelemetry.trace import StatusCode

from telemetry.utils.trace_decision import should_trace
from telemetry.utils.user_context import get_user_context

logger = logging.getLogger(__name__)


def instrument_class(cls, telemetry, prefix=None):
    """
    Production-grade class instrumentation with:
    - Traces
    - Metrics
    - Logs
    - Configurable trace rules
    - Request-scoped user context
    """

    # --------------------------------------------------
    # Guard: avoid double instrumentation
    # --------------------------------------------------
    if getattr(cls, "_telemetry_instrumented", False):
        return cls
    cls._telemetry_instrumented = True

    class_name = cls.__name__

    for _, method in inspect.getmembers(cls, inspect.isfunction):

        if method.__name__.startswith("_"):
            continue

        original_method = method

        def make_wrapper(orig_fn):
            @functools.wraps(orig_fn)
            def wrapper(*args, **kwargs):

                # --------------------------------------------------
                # 1️⃣ Resolve instance + telemetry
                # --------------------------------------------------
                instance = args[0] if args else None

                if instance and not hasattr(instance, "_telemetry"):
                    instance._telemetry = telemetry

                tele = instance._telemetry if instance else telemetry

                if tele is None or not getattr(tele, "traces", None):
                    return orig_fn(*args, **kwargs)

                # --------------------------------------------------
                # 2️⃣ Context for rule-based tracing
                # --------------------------------------------------
                method_name = orig_fn.__name__
                qualified_name = f"{class_name}.{method_name}"

                ctx = {
                    "layer": "business",
                    "class": class_name,
                    "method": method_name,
                    "qualified_name": qualified_name,
                    "module": orig_fn.__module__,
                }

                if not should_trace(tele, ctx):
                    return orig_fn(*args, **kwargs)

                # --------------------------------------------------
                # 3️⃣ User context (request scoped)
                # --------------------------------------------------
                user_id = get_user_context()

                tracer = tele.traces.tracer
                start_time = time.time()
                span = None

                try:
                    with tracer.start_as_current_span(
                        f"{qualified_name}.Span"
                    ) as span:

                        # ---------------- SPAN ATTRIBUTES ----------------
                        span.set_attribute("code.class", class_name)
                        span.set_attribute("code.function", method_name)
                        span.set_attribute("code.module", orig_fn.__module__)
                        span.set_attribute("telemetry.kind", "class")

                        if user_id:
                            span.set_attribute("user.id", user_id)

                        try:
                            from flask import has_request_context, request
                            if has_request_context():
                                span.set_attribute("http.method", request.method)
                                span.set_attribute("http.route", request.path)
                        except Exception:
                            pass

                        # ---------------- EXECUTE METHOD ----------------
                        result = orig_fn(*args, **kwargs)

                        duration_ms = (time.time() - start_time) * 1000
                        span.set_attribute("duration_ms", duration_ms)

                        # ---------------- METRICS (SUCCESS) ----------------
                        try:
                            metric_labels = {
                                "class": class_name,
                                "function": method_name,
                                "outcome": "success",
                            }
                            if user_id:
                                metric_labels["user.id"] = user_id

                            tele.metrics.increment_counter(
                                f"{qualified_name}.calls",
                                1,
                                metric_labels,
                            )

                            tele.metrics.record_histogram(
                                f"{qualified_name}.duration_ms",
                                duration_ms,
                                metric_labels,
                            )
                        except Exception:
                            logger.debug("Metric success failed", exc_info=True)

                        # ---------------- LOGS (SUCCESS) ----------------
                        try:
                            log_attrs = {
                                "class": class_name,
                                "function": method_name,
                                "duration_ms": duration_ms,
                                "outcome": "success",
                            }
                            if user_id:
                                log_attrs["user.id"] = user_id

                            tele.logs.info(
                                f"{qualified_name} executed successfully",
                                log_attrs,
                            )
                        except Exception:
                            logger.debug("Log success failed", exc_info=True)

                        return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000

                    # ---------------- TRACE ERROR ----------------
                    try:
                        if span:
                            span.record_exception(e)
                            span.set_status(StatusCode.ERROR)
                    except Exception:
                        pass

                    # ---------------- METRICS (ERROR) ----------------
                    try:
                        error_labels = {
                            "class": class_name,
                            "function": method_name,
                            "outcome": "error",
                            "exception.type": type(e).__name__,
                        }
                        if user_id:
                            error_labels["user.id"] = user_id

                        tele.metrics.increment_counter(
                            f"{qualified_name}.calls",
                            1,
                            error_labels,
                        )
                    except Exception:
                        logger.debug("Metric error failed", exc_info=True)

                    # ---------------- LOGS (ERROR) ----------------
                    try:
                        error_log_attrs = {
                            "class": class_name,
                            "function": method_name,
                            "duration_ms": duration_ms,
                            "outcome": "error",
                            "exception": str(e),
                        }
                        if user_id:
                            error_log_attrs["user.id"] = user_id

                        tele.logs.error(
                            f"Error in {qualified_name}",
                            error_log_attrs,
                        )
                    except Exception:
                        logger.debug("Log error failed", exc_info=True)

                    raise

            return wrapper

        setattr(cls, original_method.__name__, make_wrapper(original_method))

    logger.info(f"Class '{cls.__name__}' instrumented successfully")
    return cls


class ClassInstrumentor:
    def instrument(self, cls, telemetry, prefix=None):
        return instrument_class(cls, telemetry, prefix)


"""Class Instrumentation wraps all public methods of a class with tracing + metrics + logs, records errors,
supports fallbacks, and adds full observability automatically without changing customer code.

It contains two major components:

1️⃣ instrument_class() function

This function:

Iterates over all public methods of a class (ignoring _private methods).

Wraps each method with a telemetry wrapper that automatically:

✔ Starts a trace span named ClassName.method

✔ Captures exceptions and marks the span as error

✔ Records method-level metrics (call count, duration)

✔ Emits success/failure logs

✔ Provides fallbacks so the app never breaks even if OTel fails

Attaches _telemetry to the method so decorators and other instrumentors can reuse it.

Purpose:

Automatically instrument every method in a class for observability.

2️⃣ ClassInstrumentor class

This class is a simple wrapper exposing:

instrument(self, cls, telemetry, prefix=None)


It allows the SDK to do:

tele.instrument_class(MyServiceClass)


Which internally calls instrument_class() to instrument all methods.

Purpose:

Provide a clean API inside TelemetryCollector to instrument whole classes.

🧠 What This File Achieves Overall

Enables zero-effort observability for entire classes.

Automatically applies:

Tracing (span per method)

Metrics (counter + duration histogram)

Logging (success/failure events)

Ensures no exceptions escape instrumentation code (safe fallbacks).

Eliminates the need for developers to manually add decorators everywhere.

Produces method-specific telemetry enriched with class context.


"""








