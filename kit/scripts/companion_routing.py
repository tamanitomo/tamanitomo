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


# Context engines a person might have chosen on purpose are left alone; these are the
# ones that mean "nobody chose": Hermes's default, and the name of the hand-made
# copy this plugin replaces.
CONTEXT_ENGINE = "tamanitomo-context"
REPLACEABLE_ENGINES = ("", "compressor", "companion-local")
LEGACY_CONTEXT_PLUGIN = "companion-local-context"


def install_context_plugin(c):
    """Copy the context engine into this profile, named for this companion."""
    kit = Path(__file__).resolve().parent.parent
    dest = c.home / "plugins" / CONTEXT_ENGINE
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(kit / "plugins" / CONTEXT_ENGINE / name, dest / name)
    shutil.copy2(
        Path(__file__).with_name("companion_local_context.py"), dest / "snapshot.py"
    )
    cp.atomic_write(dest / "companion.json", json.dumps({"agent": c.agent}))


def enroll_context(cfg):
    """Select the companion context engine unless another one was chosen."""
    context = cfg.get("context") if isinstance(cfg.get("context"), dict) else {}
    if str(context.get("engine") or "") not in REPLACEABLE_ENGINES:
        return
    cfg["context"] = {**context, "engine": CONTEXT_ENGINE}
    plugins = cfg.setdefault("plugins", {})
    enabled = [
        n for n in plugins.get("enabled", []) or [] if n != LEGACY_CONTEXT_PLUGIN
    ]
    if CONTEXT_ENGINE not in enabled:
        enabled.append(CONTEXT_ENGINE)
    plugins["enabled"] = enabled
    disabled = plugins.get("disabled", []) or []
    if CONTEXT_ENGINE in disabled:
        plugins["disabled"] = [n for n in disabled if n != CONTEXT_ENGINE]


def install(c):
    """Install the profile-scoped Hermes adapters and explicitly enroll kit jobs."""
    import yaml

    kit = Path(__file__).resolve().parent.parent
    dest = c.home / "plugins/tamanitomo-routing"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(kit / "plugins/tamanitomo-routing" / name, dest / name)
    shutil.copy2(
        Path(__file__).with_name("companion_free_models.py"), dest / "free_models.py"
    )
    install_context_plugin(c)
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
        enroll_context(cfg)
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
