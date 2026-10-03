"""Compatibility adapter for Hermes's pinned-cron fallback policy.

Only explicitly enrolled companion jobs inherit the configured chain. Other
profiles and jobs retain Hermes's own policy. No agent turn or tool is replayed.
"""

from functools import wraps


def enrolled(cfg):
    return bool((cfg or {}).get("tamanitomo_routing")) and "tamanitomo-routing" not in (
        (cfg or {}).get("plugins") or {}
    ).get("disabled", [])


def effective(routes, primary, home, expand):
    # When the bundle is itself primary, the saved fallback tail has no marker.
    # Include the marker while refreshing, then remove the already-tried primary.
    if not routes:
        return None
    router = (
        primary.get("provider") == "openrouter"
        and primary.get("model") == "openrouter/free"
    )
    rows = expand(
        ([primary] if router else []) + list(routes),
        home,
        max_routes=9 if router else 8,
    )
    identity = lambda r: (
        r.get("provider"),
        r.get("model"),
        str(r.get("base_url") or "").rstrip("/"),
    )
    return [r for r in rows if identity(r) != identity(primary)] or None


def install_gateway(loader, home_resolver, expand):
    original = loader.get_fallback_chain
    if getattr(original, "_tamanitomo", False):
        return

    @wraps(original)
    def chain(cfg):
        routes = original(cfg)
        if not enrolled(cfg):
            return routes
        model = cfg.get("model") or {}
        primary = (
            {**model, "model": model.get("default") or model.get("model")}
            if isinstance(model, dict)
            else {}
        )
        return effective(routes or [], primary, home_resolver(), expand)

    chain._tamanitomo = True
    loader.get_fallback_chain = chain


def install(scheduler, home_resolver, expand):
    original = getattr(scheduler, "_job_fallback_chain", None)
    if not callable(original):
        raise RuntimeError("Update Hermes: companion routing needs _job_fallback_chain")
    if getattr(original, "_tamanitomo", False):
        return

    @wraps(original)
    def chain(job, cfg):
        policy = (cfg or {}).get("tamanitomo_routing") or {}
        if (
            not enrolled(cfg)
            or job.get("name") not in policy.get("jobs", [])
            or job.get("no_agent")
        ):
            return original(job, cfg)
        # An explicit job-specific chain, including [], wins if Hermes gains one.
        routes = job.get(
            "fallback_providers", (cfg or {}).get("fallback_providers", [])
        )
        if job.get("fallback_providers") == []:
            return None
        return effective(routes or [], job, home_resolver(), expand)

    chain._tamanitomo = True
    scheduler._job_fallback_chain = chain


def register(ctx):
    from cron import scheduler
    from hermes_constants import get_hermes_home
    from .free_models import expand

    install(scheduler, get_hermes_home, expand)
    from gateway import run_config_loaders

    install_gateway(run_config_loaders, get_hermes_home, expand)
