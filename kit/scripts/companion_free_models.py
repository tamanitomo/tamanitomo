"""Live, tool-capable free routes. Ranking is a disclosed heuristic, not a benchmark.

A saved openrouter/free link opts into this bundle. Explicit routes outside the
bundle keep their order, including the user's final fallback.
"""

import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

PREFERRED = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "inclusionai/ling-3.0-flash-sante:free",
)


def pick(listed, preferred=PREFERRED, count=3):
    usable = []
    for row in listed:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or "")
        pricing = row.get("pricing") or {}
        try:
            free = all(float(pricing.get(k, 0)) == 0 for k in ("prompt", "completion"))
        except (ValueError, TypeError):
            free = False
        if (
            ident.endswith(":free")
            and free
            and "tools" in (row.get("supported_parameters") or [])
            and not any(
                w in ident.lower() for w in ("safety", "guard", "embed", "moderation")
            )
        ):
            usable.append(row)
    by_id = {r["id"]: r for r in usable}
    ranked = list(dict.fromkeys(m for m in preferred if m in by_id))
    # Context is only a tie-breaker for unassessed models, never called quality.
    for row in sorted(
        usable, key=lambda r: (-int(r.get("context_length") or 0), r["id"])
    ):
        if row["id"] not in ranked:
            ranked.append(row["id"])
    return ranked[:count]


def listing(home, now=None):
    now = time.time() if now is None else now
    path = Path(home) / "companion-free-models.json"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache, dict) or not isinstance(
        cache.get("checked_at", 0), (int, float)
    ):
        cache = {}
    if cache.get("data") is not None and not isinstance(cache["data"], list):
        cache = {}
    if cache and now - cache.get("checked_at", 0) < (21600 if cache.get("ok") else 300):
        return cache.get("data")
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models", headers={"User-Agent": "tamanitomo"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.load(response)["data"]
        if not isinstance(data, list):
            raise ValueError("Invalid model catalogue")
        cache = {"data": data, "ok": True, "checked_at": now}
    except (OSError, ValueError, KeyError, TypeError):
        cache.update(ok=False, checked_at=now)
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".free-models-")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cache, stream)
        os.replace(tmp, path)
    except OSError:
        pass  # A read-only cache must not block inference.
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return cache.get("data")


def expand(routes, home, max_routes=9):
    routes = [dict(r) for r in routes]
    index = next(
        (
            i
            for i, r in enumerate(routes)
            if r.get("provider") == "openrouter" and r.get("model") == "openrouter/free"
        ),
        None,
    )
    if index is None:
        return routes
    end = index + 1
    while (
        end < len(routes)
        and routes[end].get("provider") == "openrouter"
        and str(routes[end].get("model", "")).endswith(":free")
    ):
        end += 1
    listed = listing(home)
    if listed is None:
        return routes  # Last saved choices remain usable during catalogue outages.
    room = max(0, max_routes - index - len(routes[end:]) - 1)
    choices = [{**routes[index], "model": m} for m in pick(listed, count=min(3, room))]
    ordered = routes[:index] + choices + [routes[index]] + routes[end:]
    seen, unique = set(), []
    for route in ordered:
        identity = (
            route.get("provider"),
            route.get("model"),
            str(route.get("base_url") or "").rstrip("/"),
        )
        if identity not in seen:
            seen.add(identity)
            unique.append(route)
    return unique
