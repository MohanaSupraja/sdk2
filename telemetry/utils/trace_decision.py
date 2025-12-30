import fnmatch

def should_trace(telemetry, ctx):
    if not telemetry.enable_traces:
        return False

    rules = telemetry.trace_rules
    if not rules:
        return True 

    if rules.get("layer") and ctx.get("layer") != rules["layer"]:
        return False

    method = ctx.get("method")

    includes = rules.get("include_methods")
    if includes:
        if not any(fnmatch.fnmatch(method, p) for p in includes):
            return False

    # Exclude rules
    excludes = rules.get("exclude_methods", [])
    if any(fnmatch.fnmatch(method, p) for p in excludes):
        return False

    return True
