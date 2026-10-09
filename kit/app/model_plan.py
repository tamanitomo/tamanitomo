"""One plan for the models a companion runs on, applied to every companion at once.

A model choice used to live in five places, each with a screen of its own: Hermes's
primary and fallbacks, the companion's tiers, the pin on every scheduled job, Hermes's
helper tasks (vision, compression, titles) and the cron default. Changing one left the
rest behind. A local server was switched off and one companion's vision and cron
default still pointed at it; jobs pinned to an account that had run out of credit kept
failing after the move to another one. Each companion was also changed on its own, so
"use this everywhere" meant doing it twice and hoping both came out the same.

A plan is the whole answer: who answers a conversation, what the everyday routines
and the reflections run on, and what to fall back to. Applying it rewrites the places
the kit owns, and moves anything else that still points at an account the plan no
longer uses. A deliberate choice on an account the plan does use is left alone.
"""

from __future__ import annotations

from . import model_chain as mc

TIERS = ("chat", "loops", "reflection")
EFFORTS = ("", "none", "minimal", "low", "medium", "high", "xhigh")
# Hermes's helper tasks. "auto" (or nothing) follows the main model.
FOLLOW = ("", "auto", "main")
# Keys that belong to one endpoint and must not outlive a move away from it.
ENDPOINT_KEYS = ("base_url", "api_key", "key_env", "api_key_env", "api_mode")
# llama.cpp request extras a local helper carried; another provider would reject them.
LOCAL_EXTRAS = ("id_slot", "cache_prompt")


def clean_tier(row, name):
    """A tier choice from the page: None (follow the conversation model) or a route."""
    if row in (None, {}, ""):
        return None
    route = mc.clean_route(row)
    effort = str(row.get("reasoning_effort") or "").strip().lower()
    if effort not in EFFORTS:
        raise ValueError(
            f"Reasoning for {name} must be one of: {', '.join(EFFORTS[1:])}"
        )
    return {**route, **({"reasoning_effort": effort} if effort else {})}


def tier_view(c, tier):
    """The saved tier, or None when it follows the conversation model."""
    row = (c.models or {}).get(tier)
    if not isinstance(row, dict) or not row.get("model"):
        return None
    return {
        k: row[k]
        for k in ("provider", "model", "base_url", "reasoning_effort")
        if row.get(k)
    }


def plan_of(c, cfg, bundles):
    """What this companion runs on now, in the page's terms."""
    routes = mc.current_routes(cfg)
    chat = {k: v for k, v in (routes[0] if routes else {}).items() if v}
    effort = ((c.models or {}).get("chat") or {}).get("reasoning_effort") or (
        (cfg.get("agent") or {}).get("reasoning_effort") or ""
    )
    if effort:
        chat["reasoning_effort"] = str(effort)
    return {
        "chat": chat,
        "loops": tier_view(c, "loops"),
        "reflection": tier_view(c, "reflection"),
        "links": mc.collapse(routes[1:], bundles) if len(routes) > 1 else [],
    }


def accounts(routes):
    """Where a plan goes: one (provider, endpoint) per distinct account."""
    return {(mc.identity(r)[0], mc.identity(r)[2]) for r in routes if r.get("provider")}


def stranded(row, where):
    """True when `row` points at an account the plan does not use.

    An endpoint left empty means that provider's own, so it matches the provider
    however the plan spells the endpoint, and the other way round."""
    provider, _, url = mc.identity(row)
    if not provider or provider in FOLLOW:
        return False
    return not any(provider == p and (not url or not u or url == u) for p, u in where)


def helpers(cfg):
    """Hermes's own model settings outside the chain: helper tasks, delegation, cron."""
    rows = []
    aux = cfg.get("auxiliary") if isinstance(cfg.get("auxiliary"), dict) else {}
    for task, value in aux.items():
        if not isinstance(value, dict):
            continue
        provider = str(value.get("provider") or "").strip().lower()
        if provider in FOLLOW:
            continue
        rows.append(
            {
                "key": "auxiliary." + task,
                "label": task.replace("_", " ") + " helper",
                "provider": provider,
                "model": str(value.get("model") or ""),
                "base_url": str(value.get("base_url") or ""),
            }
        )
    delegation = (
        cfg.get("delegation") if isinstance(cfg.get("delegation"), dict) else {}
    )
    if delegation.get("provider"):
        rows.append(
            {
                "key": "delegation",
                "label": "delegated tasks",
                "provider": str(delegation["provider"]),
                "model": str(delegation.get("model") or ""),
                "base_url": str(delegation.get("base_url") or ""),
            }
        )
    cron = cfg.get("cron") if isinstance(cfg.get("cron"), dict) else {}
    if cron.get("model_provider") or cron.get("provider"):
        rows.append(
            {
                "key": "cron",
                "label": "default for scheduled jobs",
                "provider": str(cron.get("model_provider") or cron.get("provider")),
                "model": str(cron.get("model") or ""),
                "base_url": str(cron.get("base_url") or ""),
            }
        )
    return rows


def background(plan):
    """The route background work falls to: the routines tier, else the conversation."""
    row = plan.get("loops") or plan["chat"]
    return {k: row[k] for k in ("provider", "model", "base_url") if row.get(k)}


def repoint(cfg, plan, where):
    """Move every helper that points outside the plan; return what moved.

    Helper tasks go back to following the main model. Delegated tasks and the cron
    default take the background route, since that is what they are."""
    moved = []
    aux = cfg.get("auxiliary") if isinstance(cfg.get("auxiliary"), dict) else {}
    for task, value in aux.items():
        if not isinstance(value, dict):
            continue
        if str(value.get("provider") or "").strip().lower() in FOLLOW:
            continue
        if not stranded(value, where):
            continue
        value["provider"] = "auto"
        value["model"] = ""
        for key in ENDPOINT_KEYS:
            value.pop(key, None)
        extra = value.get("extra_body")
        if isinstance(extra, dict):
            for key in LOCAL_EXTRAS:
                extra.pop(key, None)
        moved.append(task.replace("_", " ") + " helper")
    target = background(plan)
    delegation = cfg.get("delegation")
    if isinstance(delegation, dict) and delegation.get("provider"):
        if stranded(delegation, where):
            for key in ENDPOINT_KEYS:
                delegation.pop(key, None)
            delegation.update(provider=target["provider"], model=target["model"])
            if target.get("base_url"):
                delegation["base_url"] = target["base_url"]
            moved.append("delegated tasks")
    cron = cfg.get("cron")
    if isinstance(cron, dict) and (cron.get("model_provider") or cron.get("model")):
        wanted = (target["provider"], target["model"])
        if (cron.get("model_provider"), cron.get("model")) != wanted:
            cron["model_provider"], cron["model"] = wanted
            cron.pop("provider", None)
            if target.get("base_url"):
                cron["base_url"] = target["base_url"]
            else:
                cron.pop("base_url", None)
            moved.append("default for scheduled jobs")
    return moved


def write(cfg, plan, routes):
    """Point one Hermes config at the plan: primary, fallbacks, reasoning, helpers."""
    mc.write_chain(cfg, routes)
    effort = plan["chat"].get("reasoning_effort")
    if effort:
        agent = cfg.setdefault("agent", {})
        agent["reasoning_effort"] = effort
        # A per-model override would otherwise outrank the choice just made.
        overrides = agent.get("reasoning_overrides")
        if isinstance(overrides, dict) and plan["chat"]["model"] in overrides:
            overrides[plan["chat"]["model"]] = effort
    return repoint(cfg, plan, accounts(routes + plan_routes(plan)))


def plan_routes(plan):
    return [
        {k: row[k] for k in ("provider", "model", "base_url") if row.get(k)}
        for row in (plan["chat"], plan.get("loops"), plan.get("reflection"))
        if row
    ]


def tiers(plan, routes):
    """The companion's saved tiers for this plan; an absent tier follows the chat model."""
    out = {"chat": dict(plan["chat"])}
    for tier in ("loops", "reflection"):
        if plan.get(tier):
            out[tier] = dict(plan[tier])
    if routes[1:]:
        out["fallbacks"] = [dict(r) for r in routes[1:]]
    return out


def survey_jobs(jobs, kit_names, expected, where):
    """Kit routines against the plan, and your own jobs that point outside it."""
    routines = {"total": 0, "on_plan": 0, "off": []}
    own = []
    for job in jobs:
        if job.get("no_agent"):
            continue
        name = job.get("name") or job.get("id")
        row = {
            "id": job.get("id"),
            "name": name,
            "provider": job.get("provider") or "",
            "model": job.get("model") or "",
            "enabled": bool(job.get("enabled", True)),
        }
        if name in kit_names:
            routines["total"] += 1
            want = expected.get(name)
            if want and mc.same_route(job, want):
                routines["on_plan"] += 1
            else:
                routines["off"].append(
                    {
                        **row,
                        "expected_provider": (want or {}).get("provider", ""),
                        "expected_model": (want or {}).get("model", ""),
                    }
                )
        else:
            own.append(
                {
                    **row,
                    "stranded": bool(row["provider"]) and stranded(job, where),
                    "unpinned": not row["provider"] and not row["model"],
                }
            )
    return routines, own
