"""Shared routing policy for job installation, UI presets and background workers."""

import json
from pathlib import Path

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


def _sync(files, dest):
    """Copy {name: source} into `dest`; True when anything there changed.

    A running gateway keeps the plugin code it loaded, so a change means a restart."""
    dest.mkdir(parents=True, exist_ok=True)
    changed = False
    for name, source in files.items():
        target = dest / name
        data = source if isinstance(source, bytes) else Path(source).read_bytes()
        if not target.is_file() or target.read_bytes() != data:
            cp.atomic_write(target, data.decode("utf-8"))
            changed = True
    return changed


def install_context_plugin(c):
    """Copy the context engine into this profile, named for this companion."""
    kit = Path(__file__).resolve().parent.parent
    src = kit / "plugins" / CONTEXT_ENGINE
    return _sync(
        {
            "__init__.py": src / "__init__.py",
            "plugin.yaml": src / "plugin.yaml",
            "snapshot.py": Path(__file__).with_name("companion_local_context.py"),
            "companion.json": json.dumps({"agent": c.agent}).encode(),
        },
        c.home / "plugins" / CONTEXT_ENGINE,
    )


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


# Pages a companion reads are fetched and read on this machine unless another
# reader was chosen. A search-only backend in the extract seat is not a choice: it
# cannot read pages, and every web_extract under it failed.
READER = "tamanitomo-reader"
SEARCH_ONLY = ("searxng", "brave-free", "ddgs", "perplexity", "xai")
# Credentials that make Hermes pick a reading service when nothing is named.
READER_KEYS = {
    "FIRECRAWL_API_KEY": "firecrawl",
    "FIRECRAWL_API_URL": "firecrawl",
    "TAVILY_API_KEY": "tavily",
    "EXA_API_KEY": "exa",
    "PARALLEL_API_KEY": "parallel",
    "KEENABLE_API_KEY": "keenable",
}


def install_reader_plugin(c):
    kit = Path(__file__).resolve().parent.parent
    src = kit / "plugins" / READER
    return _sync(
        {
            "__init__.py": src / "__init__.py",
            "plugin.yaml": src / "plugin.yaml",
            "reader.py": Path(__file__).with_name("companion_reader.py"),
        },
        c.home / "plugins" / READER,
    )


def _web(cfg):
    return cfg.get("web") if isinstance(cfg.get("web"), dict) else {}


def chosen_reader(cfg, env):
    """The reading service someone set up for this profile, or "" for none."""
    web = _web(cfg)
    named = str(web.get("extract_backend") or "").strip().lower()
    if named:
        return "" if named in (READER, *SEARCH_ONLY) else named
    shared = str(web.get("backend") or "").strip().lower()
    if shared:
        return "" if shared in SEARCH_ONLY else shared
    if web.get("use_gateway"):
        return "firecrawl"
    for key, vendor in READER_KEYS.items():
        if str(env.get(key) or "").strip():
            return vendor
    return ""


def reads_locally(cfg):
    return str(_web(cfg).get("extract_backend") or "").strip().lower() == READER


def enroll_reader(cfg, env, force=False):
    """Read pages on this machine, and never hand a failed read to a free online
    service: Hermes "rescues" a failed read through Exa or Parallel unless told not
    to. Left alone when another reader was chosen, unless `force` (the person asked
    for this in the app)."""
    if not force and chosen_reader(cfg, env):
        return False
    web = _web(cfg)
    web["extract_backend"] = READER
    web["keyless_rescue"] = False
    cfg["web"] = web
    _enable(cfg, READER)
    return True


def retire_reader(cfg):
    """Hand reading back to Hermes's own choice."""
    web = _web(cfg)
    if reads_locally(cfg):
        web["extract_backend"] = ""
        if web.get("keyless_rescue") is False:
            web.pop("keyless_rescue")
        cfg["web"] = web


def reader_status(c):
    """Whether this profile reads pages here, and which other reader it uses if not."""
    from companion_gateway import _env_values

    try:
        cfg = inference.read_config(c)
    except Exception:  # noqa: BLE001 -- an unreadable config must not break Settings
        return {"local": False, "other": ""}
    if reads_locally(cfg):
        return {"local": True, "other": ""}
    return {"local": False, "other": chosen_reader(cfg, _env_values(c.home))}


def set_reader(c, on):
    """The app's switch. On reads pages here even over a reader chosen in Hermes,
    because the person asked for exactly that; off hands reading back to Hermes.
    True when the plugin had to be installed or updated, which a running gateway
    only loads on restart."""
    import yaml

    from companion_gateway import _env_values

    fresh = install_reader_plugin(c) if on else False
    with cp.file_lock(c.home / ".companion-config.lock"):
        cfg = inference.read_config(c)
        if on:
            enroll_reader(cfg, _env_values(c.home), force=True)
        else:
            retire_reader(cfg)
        cp.atomic_write(c.home / "config.yaml", yaml.safe_dump(cfg, sort_keys=False))
    return fresh


def _enable(cfg, name):
    plugins = cfg.setdefault("plugins", {})
    disabled = plugins.get("disabled", []) or []
    if name in disabled:
        plugins["disabled"] = [n for n in disabled if n != name]
    enabled = plugins.setdefault("enabled", []) or []
    if name not in enabled:
        enabled.append(name)
    plugins["enabled"] = enabled


def install(c):
    """Install the profile-scoped Hermes adapters and explicitly enroll kit jobs.

    True when a plugin was added or changed, which a running gateway only picks up
    after a restart."""
    import yaml

    from companion_gateway import _env_values

    kit = Path(__file__).resolve().parent.parent
    src = kit / "plugins/tamanitomo-routing"
    changed = _sync(
        {
            "__init__.py": src / "__init__.py",
            "plugin.yaml": src / "plugin.yaml",
            "free_models.py": Path(__file__).with_name("companion_free_models.py"),
        },
        c.home / "plugins/tamanitomo-routing",
    )
    changed = install_context_plugin(c) or changed
    changed = install_reader_plugin(c) or changed
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
        _enable(cfg, "tamanitomo-routing")
        enroll_context(cfg)
        if c.local_web_reader:
            enroll_reader(cfg, _env_values(c.home))
        cp.atomic_write(c.home / "config.yaml", yaml.safe_dump(cfg, sort_keys=False))
    return changed


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
