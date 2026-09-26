"""The model screen: what each kind of job runs on, and what to fall back to.

Two decisions live here and nowhere else.

**Per-job tiers.** The 15- and 30-minute loops run far more often than anything
else, so they are where a model choice actually costs money or, on a local
model, time. The reflection jobs run a handful of times a week and are where
thinking is worth paying for. Hermes pins a model per job, so the kit writes the
pin; it never picks a model name, because only the person paying knows what they
have access to.

**A fallback chain.** Hermes has one natively (`fallback_providers` in
config.yaml, edited with `hermes fallback`), and its cron scheduler consults it.
The kit writes up to eight entries there from this screen. No preset is
recommended: a chain that suits one person's accounts is wrong for the next.
"""

from __future__ import annotations
import argparse
import companion_config as cc
import companion_wizard as wiz
import json
import pathlib
from .common import KIT, load_manifest, print, resolve
from .questions import ask, pick_key
from .scaffold import install_jobs, mapping

EFFORT_HELP = {
    "none": "no reasoning tokens — fastest and cheapest; right for a loop that mostly confirms a state",
    "low": "a little thinking; still cheap",
    "medium": "the usual default",
    "high": "slow and expensive; only worth it where the output lasts",
}

TIER_HELP = {
    "loops": (
        "The pulse and the autonomy loop. These run every 15 and 30 minutes, so this is the choice "
        "that decides what a companion costs to keep alive. A small, fast model is the usual answer; "
        "a local model here is what makes a cloud-free companion possible at all."
    ),
    "reflection": (
        "The daily journal and the weekly and monthly reflections. A handful of runs a week, "
        "each deciding what the companion keeps of itself. Worth your best model."
    ),
}


def current_rows(c, config):
    default = (
        (config.get("model") or {}) if isinstance(config.get("model"), dict) else {}
    )
    rows = []
    for tier in ("loops", "reflection"):
        pick = c.tier_model(tier)
        model = pick.get("model") or (default.get("default") or "the profile default")
        effort = pick.get("reasoning_effort") or "Hermes default"
        rows.append((tier, model, effort))
    return rows


def read_config(c):
    import yaml

    try:
        return (
            yaml.safe_load((c.home / "config.yaml").read_text(encoding="utf-8")) or {}
        )
    except (OSError, ValueError):
        return {}


def write_fallbacks(c, entries):
    """Write the chain into Hermes's own config key, not a kit-private copy.

    `hermes fallback` remains the native way to edit this; the kit writes the
    same key so the two never disagree.
    """
    import yaml
    from companion_platform import atomic_write

    path = c.home / "config.yaml"
    config = read_config(c)
    rows = [
        {
            k: v
            for k, v in e.items()
            if k in ("provider", "model", "base_url", "api_key_env", "key_env") and v
        }
        for e in entries
    ]
    cc.dataclasses.replace(c, models={**c.models, "fallbacks": rows})
    rows = [r for r in rows if r.get("model")]
    if rows:
        config["fallback_providers"] = rows
    else:
        config.pop("fallback_providers", None)
    atomic_write(path, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    return rows


def ask_tier(c, tier, config):
    default = (
        (config.get("model") or {}) if isinstance(config.get("model"), dict) else {}
    )
    pick = dict(c.tier_model(tier))
    print()
    print(wiz.C.dim("  " + TIER_HELP[tier]))
    print()
    model = ask(
        f"Model for {tier} (blank to follow the profile's own model, "
        f"{default.get('default') or 'unset'})",
        pick.get("model", ""),
    )
    provider = (
        ask(
            "Provider for that model (blank if Hermes already knows it)",
            pick.get("provider", ""),
        )
        if model.strip()
        else ""
    )
    effort = pick_key(
        "How much reasoning should these runs do?",
        [(k, f"{k} — {v}") for k, v in EFFORT_HELP.items()]
        + [("", "leave it to Hermes")],
        default=1,
    )
    out = {}
    if model.strip():
        out["model"] = model.strip()
    if provider.strip():
        out["provider"] = provider.strip()
    if effort:
        out["reasoning_effort"] = effort
    return out


def screen(c):
    while True:
        config = read_config(c)
        wiz.rule(f"{c.agent.upper()} — MODELS")
        print(wiz.C.dim(f"  {c.home}"))
        print()
        for tier, model, effort in current_rows(c, config):
            print(f"  {tier:<12}{model}   " + wiz.C.dim(f"reasoning: {effort}"))
        chain = config.get("fallback_providers") or []
        print(
            f"  {'fallbacks':<12}"
            + (", ".join(f"{r.get('model')}" for r in chain) if chain else "none set")
        )
        print()
        action = wiz.choose(
            "What would you like to change?",
            [
                ("The loops — pulse and autonomy, every 15 and 30 minutes", "loops"),
                ("Reflection — the daily, weekly and monthly jobs", "reflection"),
                (
                    "The fallback chain, when the first provider will not answer",
                    "fallbacks",
                ),
                ("Re-pin the installed jobs to these choices", "apply"),
                ("Back", "back"),
            ],
            allow_write=False,
            allow_skip=False,
        )
        if action == "back":
            return 0
        if action in ("loops", "reflection"):
            picked = ask_tier(c, action, config)
            models = dict(c.models)
            if picked:
                models[action] = picked
            else:
                models.pop(action, None)
            c = cc.dataclasses.replace(c, models=models)
            c.save()
            print(
                wiz.C.dim(
                    f'  saved. Run "re-pin" below to move the installed jobs onto it.'
                )
            )
        elif action == "fallbacks":
            print()
            print(
                wiz.C.dim(
                    "  Hermes tries these in order when the first provider rate-limits, overloads, refuses\n"
                    "  or cannot be reached. Up to eight. There is no recommended chain: it depends entirely\n"
                    "  on which accounts and local models you actually have."
                )
            )
            print()
            entries = []
            for i in range(1, 9):
                existing = config.get("fallback_providers") or []
                was = existing[i - 1] if len(existing) >= i else {}
                model = ask(
                    f"Fallback {i} model (blank to stop here)", was.get("model", "")
                )
                if not model.strip():
                    break
                provider = ask(f"Fallback {i} provider", was.get("provider", ""))
                endpoint = ask(
                    "Endpoint URL (blank for the provider default)",
                    was.get("base_url", ""),
                )
                entries.append(
                    {
                        "model": model.strip(),
                        "provider": provider.strip(),
                        "base_url": endpoint.strip(),
                    }
                )
            rows = write_fallbacks(c, entries)
            print(wiz.C.dim(f"  fallback_providers: {json.dumps(rows)}"))
        else:
            result = apply_job_models(c)
            print(
                wiz.C.dim(
                    f'  Updated {len(result["updated"])} jobs. Their run history is preserved.'
                )
            )
        input("\n  " + wiz.C.dim("press Enter to return"))
        wiz.clear()


def cmd_models(args):
    """Choose what each kind of scheduled job runs on, and a fallback chain."""
    c = resolve(args, require_config=True)
    if getattr(args, "apply", False):
        print(json.dumps(apply_job_models(c), indent=2))
        return 0
    if getattr(args, "show", False):
        config = read_config(c)
        print(
            json.dumps(
                {
                    "tiers": {
                        t: {"model": m, "reasoning_effort": e}
                        for t, m, e in current_rows(c, config)
                    },
                    "fallback_providers": config.get("fallback_providers") or [],
                },
                indent=2,
            )
        )
        return 0
    return screen(c)


def apply_job_models(c, run=None):
    """Re-pin existing kit jobs through Hermes without recreating their histories."""
    import os
    import subprocess
    import companion_platform as cp
    from .common import _read_jobs

    if run is None:

        def run(args):
            result = subprocess.run(
                cp.hermes_command(*args),
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "HERMES_HOME": str(c.home)},
            )
            if result.returncode:
                raise ValueError(result.stderr or "Hermes cron edit failed")
            return result

    help_text = run(["cron", "edit", "--help"]).stdout
    if not all(
        flag in help_text for flag in ("--model", "--provider", "--reasoning-effort")
    ):
        raise ValueError(
            "This Hermes does not support editing model pins; update Hermes first. No jobs were changed."
        )
    if (
        any(c.tier_model(t).get("base_url") for t in ("loops", "reflection"))
        and "--base-url" not in help_text
    ):
        raise ValueError(
            "Update Hermes to apply custom job endpoints. No jobs were changed."
        )
    specs = {
        spec["name"].replace("{{AGENT}}", c.agent): spec
        for spec in load_manifest(c)["jobs"]
    }
    updated = []
    with cp.file_lock(c.home / ".companion-jobs.lock"):
        for job in _read_jobs(c.home / "cron/jobs.json")["jobs"]:
            spec = specs.get(job.get("name"))
            if not spec or spec.get("no_agent"):
                continue
            pick = c.tier_model(spec.get("tier", "chat"))
            try:
                run(
                    [
                        "cron",
                        "edit",
                        job["id"],
                        "--model",
                        pick.get("model", ""),
                        "--provider",
                        pick.get("provider", ""),
                        "--reasoning-effort",
                        pick.get("reasoning_effort", ""),
                    ]
                    + (
                        ["--base-url", pick.get("base_url", "")]
                        if "--base-url" in help_text
                        else []
                    )
                )
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                raise ValueError(
                    f'Updated {len(updated)} jobs; stopped at {job["name"]}: {exc}. Retry Apply to finish.'
                ) from exc
            updated.append(job["name"])
    return {
        "updated": updated,
        "note": "Job IDs, run history, and enabled state are preserved.",
    }
