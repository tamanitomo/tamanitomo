"""One ordered model chain for everything a companion runs.

The chain is a list of links. A link is one route (provider, model, optional
base_url) or a named bundle of routes, such as the OpenRouter free cascade.
Hermes holds the result in its own config: the first route is `model`, and the
rest, in order, are `fallback_providers`. Chat, the gateway and every scheduled
job read that fallback list, so it is the one place that has to be right.

Jobs follow the chain by being pinned to its first route. An unpinned job
cannot follow it: Hermes's drift guard skips an unpinned run once the default
has moved away from the job's creation snapshot. A pinned job never counts as
drift, and still gets the fallback list when its model fails.
"""

from __future__ import annotations

# Hermes and the workers read at most eight fallbacks after the primary.
MAX_ROUTES = 9
ROUTE_KEYS = ("provider", "model", "base_url")
# Keys in Hermes's `model` block that belong to one provider's endpoint and
# must not survive a change of provider.
PROVIDER_BOUND_KEYS = ("base_url", "api_key", "api_mode", "api_key_env", "key_env")


def _norm_url(value) -> str:
    return str(value or "").strip().rstrip("/")


def identity(route: dict) -> tuple:
    return (
        str(route.get("provider") or "").strip().lower(),
        str(route.get("model") or "").strip().lower(),
        _norm_url(route.get("base_url")).lower(),
    )


def clean_route(row) -> dict:
    if not isinstance(row, dict):
        raise ValueError("Each step needs a provider and a model")
    provider = str(row.get("provider") or "").strip()
    model = str(row.get("model") or "").strip()
    if not provider or not model:
        raise ValueError("Each step needs a provider and a model")
    if len(provider) > 120 or len(model) > 300:
        raise ValueError("Provider or model name is too long")
    out = {"provider": provider, "model": model}
    url = _norm_url(row.get("base_url"))
    if url:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            raise ValueError("Use an HTTP(S) endpoint without embedded credentials")
        out["base_url"] = url
    return out


def flatten(links, bundles: dict) -> list:
    """The ordered, de-duplicated routes a list of links stands for."""
    if not isinstance(links, list) or not links:
        raise ValueError("Choose at least one model")
    routes, seen = [], set()
    for link in links:
        if isinstance(link, dict) and link.get("bundle"):
            bundle = bundles.get(link["bundle"])
            if not bundle:
                raise ValueError("Unknown model bundle")
            members = bundle["routes"]
        else:
            members = [link]
        for row in members:
            route = clean_route(row)
            if identity(route) not in seen:
                seen.add(identity(route))
                routes.append(route)
    if len(routes) > MAX_ROUTES:
        raise ValueError(
            f"That chain has {len(routes)} models; Hermes uses at most {MAX_ROUTES}."
        )
    return routes


def collapse(routes: list, bundles: dict) -> list:
    """Links for display: a run of routes that is exactly a bundle shows as it."""
    links, i = [], 0
    while i < len(routes):
        for key, bundle in bundles.items():
            members = [identity(r) for r in bundle["routes"]]
            window = [identity(r) for r in routes[i : i + len(members)]]
            if window == members:
                links.append({"bundle": key, "name": bundle["name"]})
                i += len(members)
                break
        else:
            links.append({k: routes[i][k] for k in ROUTE_KEYS if routes[i].get(k)})
            i += 1
    return links


def current_routes(cfg: dict) -> list:
    """The chain Hermes will actually use, read from its config."""
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    primary = {
        "provider": model.get("provider") or "",
        "model": model.get("default") or model.get("model") or "",
        "base_url": model.get("base_url") or "",
    }
    routes = [primary] if primary["provider"] and primary["model"] else []
    for row in cfg.get("fallback_providers") or []:
        if isinstance(row, dict) and row.get("provider") and row.get("model"):
            routes.append({k: row.get(k) or "" for k in ROUTE_KEYS})
    return routes


def write_chain(cfg: dict, routes: list) -> None:
    """Point Hermes's primary and fallbacks at the chain, in place."""
    primary, rest = routes[0], routes[1:]
    old = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    same_provider = str(old.get("provider") or "").lower() == primary[
        "provider"
    ].lower() and _norm_url(old.get("base_url")) == _norm_url(primary.get("base_url"))
    # Keep settings that describe the model (context_length and the like);
    # drop what belonged to the previous provider's endpoint.
    model = {
        k: v
        for k, v in old.items()
        if k not in ("provider", "default", "model")
        and (same_provider or k not in PROVIDER_BOUND_KEYS)
    }
    model.update(provider=primary["provider"], default=primary["model"])
    if primary.get("base_url"):
        model["base_url"] = primary["base_url"]
    else:
        model.pop("base_url", None)
    cfg["model"] = model
    cfg["fallback_providers"] = [dict(r) for r in rest]


def job_state(job: dict, primary: dict) -> str:
    """'follows' when pinned to the chain's first model, else 'pinned' or 'unpinned'."""
    if not job.get("provider") and not job.get("model"):
        return "unpinned"
    return "follows" if same_route(job, primary) else "pinned"


def same_route(a: dict, b: dict) -> bool:
    """Same provider and model; an endpoint left empty means that provider's own."""
    ours, theirs = identity(a), identity(b)
    return ours[:2] == theirs[:2] and (not ours[2] or not theirs[2] or ours[2] == theirs[2])
