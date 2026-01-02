from typing import Dict, Any, Optional
from contextlib import contextmanager
from telemetry.utils.user_context import get_user_context   # ✅ already present

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
except Exception:
    trace = None
    SpanKind = None
    Status = None
    StatusCode = None


class DummySpan:
    """A safe noop fallback span that never breaks user apps."""
    def set_attribute(self, k, v): pass
    def add_event(self, name, attributes=None): pass
    def record_exception(self, exc): pass
    def set_status(self, status): pass
    def end(self): pass


class TracesManager:
    """
    Production-ready wrapper around OpenTelemetry tracing.
    """

    def __init__(self, tracer_provider=None):
        self.tracer = None

        try:
            if trace:
                if tracer_provider is not None:
                    try:
                        current = trace.get_tracer_provider()
                        if type(current).__name__.lower().startswith("default") or \
                           type(current).__name__.lower().startswith("proxy"):
                            trace.set_tracer_provider(tracer_provider)
                    except Exception:
                        trace.set_tracer_provider(tracer_provider)

                self.tracer = trace.get_tracer(__name__)
        except Exception:
            self.tracer = None

    # ------------------------------------------------------------------
    # Internal helper: pick a safe SpanKind
    # ------------------------------------------------------------------
    def _normalize_kind(self, kind):
        if kind is not None:
            return kind
        if SpanKind is not None:
            return SpanKind.INTERNAL
        return None

    # ------------------------------------------------------------------
    # 🔥 Internal helper: inject user.id into attributes
    # ------------------------------------------------------------------
    def _inject_user(self, attributes: Dict[str, Any] | None) -> Dict[str, Any] | None:
        user_id = get_user_context()
        if not user_id:
            return attributes

        attrs = dict(attributes or {})
        attrs.setdefault("user.id", user_id)
        return attrs

    # ------------------------------------------------------------------
    # Start span (context manager)
    # ------------------------------------------------------------------
    @contextmanager
    def start_span(self, name: str, attributes: Dict[str, Any] = None, kind=None):
        kind = self._normalize_kind(kind)
        attributes = self._inject_user(attributes)   # ✅ ADD

        if self.tracer:
            try:
                with self.tracer.start_as_current_span(
                    name,
                    attributes=attributes,
                    kind=kind,
                ) as span:
                    yield span
                return
            except Exception:
                pass

        yield DummySpan()

    # ------------------------------------------------------------------
    # Start span manually as context manager
    # ------------------------------------------------------------------
    def start_span_as_current(self, name: str, attributes: Dict[str, Any] = None, kind=None):
        kind = self._normalize_kind(kind)
        attributes = self._inject_user(attributes)   # ✅ ADD

        if self.tracer:
            try:
                return self.tracer.start_as_current_span(
                    name,
                    attributes=attributes,
                    kind=kind,
                )
            except Exception:
                pass

        class DummyCM:
            def __enter__(self): return DummySpan()
            def __exit__(self, *a): return False
        return DummyCM()

    # ------------------------------------------------------------------
    # Create a span manually (not context managed)
    # ------------------------------------------------------------------
    def create_span(self, name: str, attributes: Dict[str, Any] = None, kind=None):
        kind = self._normalize_kind(kind)
        attributes = self._inject_user(attributes)   # ✅ ADD

        if self.tracer:
            try:
                return self.tracer.start_span(name, attributes=attributes, kind=kind)
            except Exception:
                return DummySpan()
        return DummySpan()

    # ------------------------------------------------------------------
    # End span safely
    # ------------------------------------------------------------------
    def end_span(self, span):
        try:
            if span and hasattr(span, "end"):
                span.end()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Add event to current span
    # ------------------------------------------------------------------
    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        span = self.get_current_span()
        try:
            if span:
                span.add_event(name, attributes or {})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Bulk attribute update
    # ------------------------------------------------------------------
    def update_attributes(self, attributes: Dict[str, Any]):
        span = self.get_current_span()
        if not span:
            return

        try:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Record exception on span
    # ------------------------------------------------------------------
    def record_exception(self, exception: Exception):
        span = self.get_current_span()
        if not span:
            return

        try:
            span.record_exception(exception)

            if Status is not None:
                span.set_status(Status(StatusCode.ERROR, str(exception)))
            else:
                span.set_status(StatusCode.ERROR)

        except Exception:
            pass

    # ------------------------------------------------------------------
    # Set status OK
    # ------------------------------------------------------------------
    def set_span_status_ok(self):
        span = self.get_current_span()
        try:
            if span and Status and StatusCode:
                span.set_status(Status(StatusCode.OK))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Set status ERROR
    # ------------------------------------------------------------------
    def set_span_status_error(self, message="error"):
        span = self.get_current_span()
        try:
            if span and Status and StatusCode:
                span.set_status(Status(StatusCode.ERROR, message))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Get active span
    # ------------------------------------------------------------------
    def get_current_span(self):
        try:
            if trace:
                return trace.get_current_span()
        except Exception:
            return DummySpan()
        return DummySpan()

    # ------------------------------------------------------------------
    # Return trace_id and span_id
    # ------------------------------------------------------------------
    def get_trace_context(self) -> Dict[str, Optional[str]]:
        try:
            span = self.get_current_span()
            ctx = span.get_span_context()

            if not ctx or ctx.trace_id == 0:
                return {}

            return {
                "trace_id": f"{ctx.trace_id:032x}",
                "span_id": f"{ctx.span_id:016x}",
            }
        except Exception:
            return {}





# | Feature                   | Description                       |
# | ------------------------- | --------------------------------- |
# | `end_span()`              | Safe manual end for spans         |
# | `set_span_status_ok()`    | Mark span status as OK            |
# | `set_span_status_error()` | Mark span status as ERROR         |
# | `record_exception()`      | Proper OTel exception recording   |
# | `add_event()`             | Add event to current span         |
# | `update_attributes()`     | Bulk attribute setter             |
# | `get_trace_context()`     | Returns trace_id/span_id properly |
# | Full fallback DummySpan   | Never breaks user app             |


"""1️⃣ Core Span Management

start_span()

start_span_as_current()

create_span()

end_span()

2️⃣ Rich Observability Helpers

add_event()

update_attributes()

record_exception()

set_span_status_ok()

set_span_status_error()

3️⃣ Safe Fallbacks

Every method works even if:

OpenTelemetry is not installed

Exporter fails

Tracer provider not configured

4️⃣ Usability Helpers

get_current_span()

get_trace_context() (trace_id + span_id)"""