import logging
import sys
from typing import Any

from opentelemetry import trace
from opentelemetry.context import attach
from opentelemetry.trace import INVALID_SPAN

from telemetry.utils.trace_decision import should_trace

logger = logging.getLogger(__name__)


class FrameworkInstrumentor:
    """
    Framework-specific instrumentation:
    - Flask
    - FastAPI / Starlette (ASGI)
    - Django (global instrumentation)

    Supports:
    - Auto-instrumentation
    - Route-based configuration-driven tracing
    """

    def __init__(self, telemetry):
        self.telemetry = telemetry
        self._instrumented_apps = {}  # app id -> framework name

    # ---------------------------------------------------------------------
    def instrument_app(self, app: Any, framework: str = None) -> bool:
        try:

            # ============================================================
            # 1) AUTO-DETECTION
            # ============================================================
            if framework is None:
                if hasattr(app, "wsgi_app") and hasattr(app, "route"):
                    framework = "flask"
                elif hasattr(app, "router") and hasattr(app, "add_event_handler"):
                    framework = "fastapi" if "fastapi" in sys.modules else "starlette"
                else:
                    try:
                        import django  # noqa
                        framework = "django"
                    except ImportError:
                        logger.debug("Could not auto-detect framework.")
                        return False

            framework = framework.lower()

            # ============================================================
            # 2) FLASK
            # ============================================================
            if framework == "flask":
                from opentelemetry.instrumentation.flask import FlaskInstrumentor

                FlaskInstrumentor().instrument_app(app)

                # ---- Route-based tracing hook ----
                @app.before_request
                def _otel_route_trace_guard():
                    try:
                        from flask import request

                        ctx = {
                            "layer": "http",
                            "route": request.path,
                            "method": request.method,
                        }

                        if not should_trace(self.telemetry, ctx):
                            # Disable tracing for this request
                            attach(trace.set_span_in_context(INVALID_SPAN))

                    except Exception:
                        logger.debug("Route trace guard failed", exc_info=True)

                self._instrumented_apps[id(app)] = "flask"
                logger.info("Instrumented Flask application with route-based tracing.")
                return True

            # ============================================================
            # 3) FASTAPI / STARLETTE
            # ============================================================
            if framework in ("fastapi", "starlette"):
                from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
                from starlette.middleware.base import BaseHTTPMiddleware

                class RouteTraceMiddleware(BaseHTTPMiddleware):
                    async def dispatch(self, request, call_next):
                        ctx = {
                            "layer": "http",
                            "route": request.url.path,
                            "method": request.method,
                        }

                        if not should_trace(self.telemetry, ctx):
                            attach(trace.set_span_in_context(INVALID_SPAN))

                        return await call_next(request)

                # Avoid double middleware
                existing = [
                    (m.cls.__name__ if hasattr(m, "cls") else m.__class__.__name__)
                    for m in getattr(app, "user_middleware", [])
                ]

                if "OpenTelemetryMiddleware" not in existing:
                    app.add_middleware(OpenTelemetryMiddleware)

                app.add_middleware(RouteTraceMiddleware)

                self._instrumented_apps[id(app)] = framework
                logger.info(f"Instrumented {framework} app with route-based tracing.")
                return True

            # ============================================================
            # 4) DJANGO
            # ============================================================
            if framework == "django":
                from opentelemetry.instrumentation.django import DjangoInstrumentor

                DjangoInstrumentor().instrument()
                self._instrumented_apps[id(app)] = "django"
                logger.info("Instrumented Django globally.")
                return True

            logger.debug("Framework '%s' not supported.", framework)
            return False

        except Exception as e:
            logger.debug("instrument_app error: %s", e, exc_info=True)
            return False

    # ---------------------------------------------------------------------
    def uninstrument_app(self, app: Any) -> bool:
        try:
            fid = id(app)
            framework = self._instrumented_apps.get(fid)

            if not framework:
                return False

            if framework == "flask":
                from opentelemetry.instrumentation.flask import FlaskInstrumentor
                FlaskInstrumentor().uninstrument_app(app)
                self._instrumented_apps.pop(fid, None)
                logger.info("Uninstrumented Flask app.")
                return True

            if framework in ("fastapi", "starlette"):
                logger.debug("FastAPI/Starlette runtime uninstrumentation not supported.")
                return False

            if framework == "django":
                logger.debug("Django cannot be uninstrumented at runtime.")
                return False

            return False

        except Exception as e:
            logger.debug("uninstrument_app error: %s", e, exc_info=True)
            return False



""" Usage scenarios:

# If auto_instrumentation = True - sinstrumentation happens automatically as :

# The user just passes their app instance (like Flask(app) or FastAPI()) into our SDK through config.framework_app.

# The SDK automatically detects the framework by checking the app’s attributes (Flask → wsgi_app, FastAPI → router, Django → WSGI/ASGI handlers).

# Based on the detected framework, the SDK applies the correct OpenTelemetry instrumentor (FlaskInstrumentor, ASGI middleware, DjangoInstrumentor).

# The user doesn’t need to configure anything manually 

# If auto_instrumentation = False, then the behavior is:

# The SDK will NOT auto-detect any framework (Flask/Django/FastAPI).

# No automatic tracing, metrics, or middleware will be added to the app.

# The user must explicitly call: tele.instrument_app(app, framework="flask")

# Only then does the SDK apply the correct instrumentor—otherwise, the framework is completely untouched."""