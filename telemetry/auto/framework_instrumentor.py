import logging
import sys
from typing import Any

from telemetry.utils.user_context import get_user_context

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Span Processor to inject user.id into ALL framework spans
# ------------------------------------------------------------
class UserContextSpanProcessor:
    def on_start(self, span, parent_context=None):
        try:
            user_id = get_user_context()
            if user_id and span is not None:
                span.set_attribute("user.id", user_id)
        except Exception:
            pass

    def on_end(self, span):
        pass


class FrameworkInstrumentor:
    def __init__(self, telemetry):
        self.telemetry = telemetry
        self._instrumented_apps = {}  # app id -> framework name

        # ----------------------------------------------------
        #  Register span processor ONCE
        # ----------------------------------------------------
        try:
            tracer_provider = getattr(self.telemetry.traces, "tracer_provider", None)
            if tracer_provider:
                tracer_provider.add_span_processor(UserContextSpanProcessor())
        except Exception:
            logger.debug("Failed to register UserContextSpanProcessor", exc_info=True)

    def instrument_app(self, app: Any, framework: str = None) -> bool:
        try:
            # ---------------- AUTO DETECTION ----------------
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
                        return False

            framework = framework.lower()

            # ---------------- FLASK ----------------
            if framework == "flask":
                from opentelemetry.instrumentation.flask import FlaskInstrumentor

                excluded = ""
                try:
                    http_rules = self.telemetry.trace_rules.get("http", {})
                    excluded_routes = http_rules.get("exclude_routes", [])
                    excluded = "|".join(excluded_routes)
                except Exception:
                    pass

                FlaskInstrumentor().instrument_app(
                    app,
                    excluded_urls=excluded or None
                )

                self._instrumented_apps[id(app)] = "flask"
                logger.info("Instrumented Flask application (route-aware).")
                return True

            # ---------------- FASTAPI / STARLETTE ----------------
            if framework in ("fastapi", "starlette"):
                from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
                app.add_middleware(OpenTelemetryMiddleware)
                self._instrumented_apps[id(app)] = framework
                return True

            # ---------------- DJANGO ----------------
            if framework == "django":
                from opentelemetry.instrumentation.django import DjangoInstrumentor
                DjangoInstrumentor().instrument()
                self._instrumented_apps[id(app)] = "django"
                return True

            return False

        except Exception:
            logger.exception("Framework instrumentation failed")
            return False

    # ---------------------------------------------------------------------
    # UN-INSTRUMENTATION (best-effort)
    # ---------------------------------------------------------------------
    def uninstrument_app(self, app: Any) -> bool:
        try:
            fid = id(app)
            framework = self._instrumented_apps.get(fid)

            if not framework:
                return False

            if framework == "flask":
                try:
                    from opentelemetry.instrumentation.flask import FlaskInstrumentor
                    FlaskInstrumentor().uninstrument_app(app)
                    self._instrumented_apps.pop(fid, None)
                    logger.info("Uninstrumented Flask app.")
                    return True
                except Exception:
                    logger.debug("Flask uninstrumentation failed.", exc_info=True)
                    return False

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
