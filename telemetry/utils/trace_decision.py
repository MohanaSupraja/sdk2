import fnmatch


def should_trace(telemetry, ctx):
    """
    NOTE:
    - HTTP route filtering is handled at framework instrumentation level
      (e.g., FlaskInstrumentor excluded_urls)
    - This function applies only to business-layer spans
    """
    if not getattr(telemetry, "enable_traces", False):
        return False

    trace_rules = getattr(telemetry, "trace_rules", None)
    if not trace_rules:
        return True

    layer = ctx.get("layer")

    layer_rules = trace_rules.get(layer)
    if not layer_rules:
        return True
    if layer == "business":
        method = ctx.get("method", "")

        include_methods = layer_rules.get("include_methods")
        if include_methods:
            if not any(fnmatch.fnmatch(method, p) for p in include_methods):
                return False

        exclude_methods = layer_rules.get("exclude_methods", [])
        if any(fnmatch.fnmatch(method, p) for p in exclude_methods):
            return False

        return True
    return True

