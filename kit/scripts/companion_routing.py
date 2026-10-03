"""Shared routing policy for job installation, UI presets and background workers."""

import json
from pathlib import Path
import shutil

import companion_inference as inference
import companion_platform as cp


def job_route(c, spec):
    tier = spec.get("tier", "chat")
    route = inference.configured_routes(c, tier=tier, refresh_free=False)[0]
    # The workload preset is recognizable by its saved tiers. A subsequent tier
    # edit takes precedence, as do per-job edits after Apply.
    if c.models.get(tier) == codex_tiers().get(tier):
        key = spec.get("key")
        if key in ("autonomy", "winddown"):
            route.update(model="gpt-5.6-sol", reasoning_effort="low")
        elif key in ("weekly", "monthly"):
            route.update(reasoning_effort="high")
        elif key == "hygiene":
            route.update(model="gpt-5.6-luna", reasoning_effort="none")
    return route


def install(c):
    """Install the profile-scoped Hermes adapter and explicitly enroll kit jobs."""
    import yaml

    kit = Path(__file__).resolve().parent.parent
    dest = c.home / "plugins/tamanitomo-routing"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(kit / "plugins/tamanitomo-routing" / name, dest / name)
    shutil.copy2(
        Path(__file__).with_name("companion_free_models.py"), dest / "free_models.py"
    )
    specs = json.loads((kit / "templates/cron/manifest.json").read_text())["jobs"]
    with cp.file_lock(c.home / ".companion-config.lock"):
        cfg = inference.read_config(c)
        cfg["tamanitomo_routing"] = {
            "jobs": [
                s["name"].replace("{{AGENT}}", c.agent)
                for s in specs
                if not s.get("no_agent")
            ]
        }
        plugins = cfg.setdefault("plugins", {})
        disabled = plugins.get("disabled", [])
        if "tamanitomo-routing" in disabled:
            plugins["disabled"] = [n for n in disabled if n != "tamanitomo-routing"]
        enabled = plugins.setdefault("enabled", [])
        if "tamanitomo-routing" not in enabled:
            enabled.append("tamanitomo-routing")
        cp.atomic_write(c.home / "config.yaml", yaml.safe_dump(cfg, sort_keys=False))


def codex_tiers():
    """Explicit product defaults; users can subsequently override individual jobs."""
    return {
        "chat": {
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "none",
        },
        "loops": {
            "provider": "openai-codex",
            "model": "gpt-5.6-luna",
            "reasoning_effort": "none",
        },
        "reflection": {
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
        },
    }
