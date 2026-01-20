from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
import os


# --------------------
# ENV HELPERS
# --------------------
def env_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def env_float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


def env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


# --------------------
# CONFIG
# --------------------
@dataclass
class TelemetryConfig:
    """
    Central configuration object for the entire Observability SDK.
    Env vars override defaults automatically.
    """

    # SERVICE METADATA
    service_name: str = field(
        default_factory=lambda: env_str("OTEL_SERVICE_NAME", "sify-service")
    )

    resource_attributes: Dict[str, str] = field(default_factory=dict)

    # OTLP EXPORTER
    collector_endpoint: str = field(
        default_factory=lambda: env_str(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://otel-collector:4318"
        )
    )

    protocol: str = field(
        default_factory=lambda: env_str(
            "OTEL_EXPORTER_OTLP_PROTOCOL",
            "http/protobuf"
        )
    )

    headers: Dict[str, str] = field(default_factory=dict)

    insecure: bool = field(
        default_factory=lambda: env_bool("OTEL_EXPORTER_OTLP_INSECURE", True)
    )

    # FEATURE FLAGS
    enable_traces: bool = field(
        default_factory=lambda: env_bool("ENABLE_TRACES", True)
    )

    enable_metrics: bool = field(
        default_factory=lambda: env_bool("ENABLE_METRICS", True)
    )

    enable_logs: bool = field(
        default_factory=lambda: env_bool("ENABLE_LOGS", True)
    )

    # AUTO INSTRUMENTATION
    auto_instrument: bool = field(
        default_factory=lambda: env_bool("AUTO_INSTRUMENT", True)
    )

    instrument_frameworks: bool = field(
        default_factory=lambda: env_bool("INSTRUMENT_FRAMEWORKS", True)
    )

    framework_app: Any = None

    instrument_libraries_enabled: bool = field(
        default_factory=lambda: env_bool("INSTRUMENT_LIBRARIES", True)
    )

    instrument_libraries: List[str] = field(default_factory=list)

    instrument_databases_enabled: bool = field(
        default_factory=lambda: env_bool("INSTRUMENT_DATABASES", True)
    )

    instrument_databases: List[str] = field(default_factory=list)

    disable_framework_logs: bool = field(
        default_factory=lambda: env_bool("DISABLE_FRAMEWORK_LOGS", False)
    )

    framework_loggers_to_disable: List[str] = field(
        default_factory=lambda: ["werkzeug"]
    )

    trace_rules: Dict[str, Any] = field(default_factory=dict)

    # SAMPLING & EXPORT
    sampling_rate: float = field(
        default_factory=lambda: env_float("TRACE_SAMPLING_RATE", 1.0)
    )

    export_interval_ms: int = field(
        default_factory=lambda: env_int("EXPORT_INTERVAL_MS", 5000)
    )

    max_queue_size: int = field(
        default_factory=lambda: env_int("MAX_QUEUE_SIZE", 2048)
    )

    max_export_batch_size: int = field(
        default_factory=lambda: env_int("MAX_EXPORT_BATCH_SIZE", 512)
    )

    # HTTP CAPTURE
    capture_headers: bool = field(
        default_factory=lambda: env_bool("CAPTURE_HEADERS", False)
    )

    capture_query_params: bool = field(
        default_factory=lambda: env_bool("CAPTURE_QUERY_PARAMS", True)
    )

    capture_request_body: bool = field(
        default_factory=lambda: env_bool("CAPTURE_REQUEST_BODY", False)
    )

    capture_response_body: bool = field(
        default_factory=lambda: env_bool("CAPTURE_RESPONSE_BODY", False)
    )

    capture_sql_queries: bool = field(
        default_factory=lambda: env_bool("CAPTURE_SQL_QUERIES", True)
    )

    log_sample_rate: float = field(
        default_factory=lambda: env_float("LOG_SAMPLE_RATE", 1.0)
    )

    # SECURITY / MASKING
    mask_sensitive_data: bool = field(
        default_factory=lambda: env_bool("MASK_SENSITIVE_DATA", True)
    )

    sensitive_fields: List[str] = field(
        default_factory=lambda: ["password", "api_key", "token", "secret"]
    )

    exclude_urls: List[str] = field(
        default_factory=lambda: ["/health", "/metrics"]
    )

    max_span_attributes: int = field(
        default_factory=lambda: env_int("MAX_SPAN_ATTRIBUTES", 100)
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
