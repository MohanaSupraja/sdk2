import logging
from typing import Dict, List, Any, Optional

from telemetry.utils.user_context import get_user_context

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# 🔥 SpanProcessor to inject user.id into DB spans
# ------------------------------------------------------------
class UserContextDBSpanProcessor:
    def on_start(self, span, parent_context=None):
        try:
            user_id = get_user_context()
            if user_id and span is not None:
                span.set_attribute("user.id", user_id)
        except Exception:
            pass

    def on_end(self, span):
        pass


class DatabaseInstrumentor:
    """
    Production-grade instrumentor for database libraries.
    """

    _INSTRUMENTOR_MAP: Dict[str, tuple] = {
        "sqlalchemy": (
            "opentelemetry.instrumentation.sqlalchemy",
            "SQLAlchemyInstrumentor",
        ),
        "psycopg2": (
            "opentelemetry.instrumentation.psycopg2",
            "Psycopg2Instrumentor",
        ),
        "redis": (
            "opentelemetry.instrumentation.redis",
            "RedisInstrumentor",
        ),
        "pymongo": (
            "opentelemetry.instrumentation.pymongo",
            "PymongoInstrumentor",
        ),
    }

    def __init__(self):
        self._status: Dict[str, str] = {}

        # ----------------------------------------------------
        # 🔥 Register span processor ONCE (global)
        # ----------------------------------------------------
        try:
            from opentelemetry import trace
            provider = trace.get_tracer_provider()
            if provider:
                provider.add_span_processor(UserContextDBSpanProcessor())
        except Exception:
            logger.debug("Failed to register DB user context span processor", exc_info=True)

    # ----------------------------------------------------------------------
    def instrument(
        self,
        libraries: List[str],
        sqlalchemy_engine: Optional[Any] = None
    ) -> Dict[str, bool]:

        results = {}

        for lib in libraries:
            lib = lib.lower()

            if self._status.get(lib) == "instrumented":
                results[lib] = True
                continue

            if lib not in self._INSTRUMENTOR_MAP:
                results[lib] = False
                continue

            module_path, class_name = self._INSTRUMENTOR_MAP[lib]

            try:
                mod = __import__(module_path, fromlist=[class_name])
                InstrumentorClass = getattr(mod, class_name)
            except Exception as e:
                logger.warning(
                    f"[DB-INSTRUMENTOR] Failed to import {class_name} for {lib}: {e}",
                    exc_info=True
                )
                results[lib] = False
                continue

            inst = InstrumentorClass()

            try:
                if lib == "sqlalchemy" and sqlalchemy_engine is not None:
                    inst.instrument(engine=sqlalchemy_engine)
                else:
                    inst.instrument()

                self._status[lib] = "instrumented"
                logger.info(f"Instrumented database: {lib}")
                results[lib] = True

            except Exception as e:
                logger.error(
                    f"[DB-INSTRUMENTOR] Instrumentation FAILED for {lib}: {e}",
                    exc_info=True
                )
                results[lib] = False

        return results

    # ----------------------------------------------------------------------
    def uninstrument(self, lib: str) -> bool:
        lib = lib.lower()

        if lib not in self._INSTRUMENTOR_MAP:
            return False

        module_path, class_name = self._INSTRUMENTOR_MAP[lib]

        try:
            mod = __import__(module_path, fromlist=[class_name])
            InstrumentorClass = getattr(mod, class_name)
            inst = InstrumentorClass()
        except Exception:
            return False

        try:
            if hasattr(inst, "uninstrument"):
                inst.uninstrument()

            self._status[lib] = "uninstrumented"
            logger.info(f"[DB-INSTRUMENTOR] Uninstrumented {lib}")
            return True

        except Exception:
            logger.debug(
                f"[DB-INSTRUMENTOR] Uninstrumentation failed for {lib}",
                exc_info=True
            )
            return False

    # ----------------------------------------------------------------------
    def status(self) -> Dict[str, str]:
        return dict(self._status)
