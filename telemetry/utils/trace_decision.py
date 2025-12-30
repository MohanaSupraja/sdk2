import fnmatch


def should_trace(telemetry, ctx):
    """
    Decide whether tracing should occur for the current operation.

    ctx examples:
    -------------
    HTTP:
        {
            "layer": "http",
            "route": "/api/deployments",
            "method": "GET"
        }

    Business:
        {
            "layer": "business",
            "class": "DeploymentManager",
            "method": "get_all_for_user",
            "qualified_name": "DeploymentManager.get_all_for_user",
        }
    """

    # ------------------------------------------------------------
    # 1. Global master switch
    # ------------------------------------------------------------
    if not getattr(telemetry, "enable_traces", False):
        return False

    trace_rules = getattr(telemetry, "trace_rules", None)
    if not trace_rules:
        # No rules configured → trace everything
        return True

    layer = ctx.get("layer")

    # ------------------------------------------------------------
    # 2. No rules for this layer → allow by default
    # ------------------------------------------------------------
    layer_rules = trace_rules.get(layer)
    if not layer_rules:
        return True

    # ------------------------------------------------------------
    # 3. HTTP / Route-based tracing
    # ------------------------------------------------------------
    if layer == "http":
        route = ctx.get("route", "")

        include_routes = layer_rules.get("include_routes")
        if include_routes:
            if not any(fnmatch.fnmatch(route, p) for p in include_routes):
                return False

        exclude_routes = layer_rules.get("exclude_routes", [])
        if any(fnmatch.fnmatch(route, p) for p in exclude_routes):
            return False

        return True

    # ------------------------------------------------------------
    # 4. Business / Method-based tracing
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # 5. Unknown layer → allow by default
    # ------------------------------------------------------------
    return True
