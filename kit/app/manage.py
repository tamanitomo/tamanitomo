"""Application management routes. Every mutation has an explicit installation/profile."""

from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import yaml
import itertools
from fastapi import HTTPException, Request
from . import runtime as hr
import companion_config as cc
import companion_platform as cp

_ONBOARDING_OAUTH_SESSIONS = {}
_ONBOARDING_OAUTH_LOCK = threading.Lock()

# Workspace appearance. Themes are defined in static/product.css; this list is the
# validation allowlist, and the two groups decide what "match system" switches between.
DARK_THEMES = [
    "midnight",
    "nord",
    "ocean",
    "emerald",
    "amethyst",
    "synthwave",
    "ember",
    "sakura",
    "carbon",
]
LIGHT_THEMES = ["daylight", "parchment", "mist"]
THEMES = DARK_THEMES + LIGHT_THEMES
# Destinations a person may pin to the mobile bar. "more" is fixed and never pinned.
PINNABLE = [
    "now",
    "chat",
    "timeline",
    "photos",
    "journals",
    "creations",
    "relationship",
    "loops",
    "knows",
    "vault",
    "identity",
    "settings",
    "environment",
    "health",
    "roster",
    "image-studio",
    "voice",
    "local-models",
]
APPEARANCE_DEFAULT = {
    "theme": "midnight",
    "accent": "",
    "follow_system": False,
    "dark_theme": "midnight",
    "light_theme": "daylight",
    "nav_pins": ["chat", "now", "photos", "journals"],
}

FALLBACK_CATALOG = [
    {
        "slug": "openrouter",
        "label": "OpenRouter",
        "api_key_env_vars": ["OPENROUTER_API_KEY"],
        "auth_type": "api_key",
    },
    {
        "slug": "mistral",
        "label": "Mistral AI",
        "api_key_env_vars": ["MISTRAL_API_KEY"],
        "auth_type": "api_key",
    },
    {
        "slug": "deepseek",
        "label": "DeepSeek",
        "api_key_env_vars": ["DEEPSEEK_API_KEY"],
        "auth_type": "api_key",
    },
    {
        "slug": "openai",
        "label": "OpenAI",
        "api_key_env_vars": ["OPENAI_API_KEY"],
        "auth_type": "api_key",
    },
    {
        "slug": "anthropic",
        "label": "Anthropic",
        "api_key_env_vars": ["ANTHROPIC_API_KEY"],
        "auth_type": "api_key",
    },
    {
        "slug": "ollama",
        "label": "Ollama (local)",
        "api_key_env_vars": [],
        "auth_type": "none",
    },
    {
        "slug": "custom",
        "label": "OpenAI-compatible endpoint",
        "api_key_env_vars": ["OPENAI_API_KEY"],
        "auth_type": "api_key",
    },
]

INFERENCE_PRESETS = [
    {
        "id": "openrouter_free",
        "name": "OpenRouter Free Tier Cascade",
        "badge": "Free Cloud",
        "description": "Zero-cost inference via OpenRouter smart router with graceful failover across active free models (open-weights models).",
        "primary": {"provider": "openrouter", "model": "openrouter/free"},
        "fallbacks": [
            {"provider": "openrouter", "model": "google/gemma-4-26b-a4b-it:free"},
            {
                "provider": "openrouter",
                "model": "nvidia/nemotron-3-super-120b-a12b:free",
            },
            {
                "provider": "openrouter",
                "model": "inclusionai/ling-3.0-flash-sante:free",
            },
        ],
        "requires_env": ["OPENROUTER_API_KEY"],
    },
    {
        "id": "deepseek_free_cascade",
        "name": "DeepSeek Fast + OpenRouter Free Fallbacks",
        "badge": "High Performance",
        "description": "DeepSeek Flash primary for high responsiveness, backed by OpenRouter free cascade on rate-limits.",
        "primary": {"provider": "deepseek", "model": "deepseek-flash"},
        "fallbacks": [
            {"provider": "openrouter", "model": "openrouter/free"},
            {"provider": "openrouter", "model": "google/gemma-4-26b-a4b-it:free"},
        ],
        "requires_env": ["DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"],
    },
    {
        "id": "local_hardware_cloud_fallback",
        "name": "Local Hardware (Vulkan/Ollama) + Cloud Fallback",
        "badge": "Private Local",
        "description": "Runs locally on hardware with automatic failover to DeepSeek / OpenRouter if busy or unavailable.",
        "primary": {
            "provider": "custom",
            "model": "local-model",
            "base_url": "http://127.0.0.1:11434/v1",
        },
        "fallbacks": [
            {"provider": "deepseek", "model": "deepseek-flash"},
            {"provider": "openrouter", "model": "openrouter/free"},
        ],
        "requires_env": [],
    },
]

# Recommendations describe the work, not a vendor SKU. Provider catalogues
# change and account access differs; the UI pairs this advice with the live
# model dropdown so a person can choose something they actually have.
# Three questions a person should be able to answer about a background job:
# does it call a model at all, what does it put in the prompt, and where does
# that prompt go. The jobs list answered none of them -- every job showed a
# provider, including the seven that never contact one, which reads as though
# something is being sent when nothing is.
SENSITIVITY = {
    "none": {
        "label": "No model, ever",
        "blurb": "These never contact a provider. They move files, send messages that were "
        "already written, and keep the ledgers tidy. Nothing they touch leaves the machine.",
        "advice": "Nothing to decide here. A provider setting on one of these is cosmetic.",
        "order": 0,
    },
    "routine": {
        "label": "Uses a model, nothing private",
        "blurb": "These call a model, but what they send is mechanical or outward-facing "
        "rather than the companion's inner life.",
        "advice": "A hosted model is a reasonable choice. Use a local one if you would rather "
        "nothing at all left the machine.",
        "order": 1,
    },
    "sensitive": {
        "label": "Uses a model, sends private material",
        "blurb": "These put the companion's inner life -- her SOUL file, her recorded mood "
        "and private stance, her appearance -- or your own words into a prompt. "
        "Whatever answers them reads that.",
        "advice": "A local model on this machine is the safest option, because nothing "
        "leaves it. A hosted provider is a real choice with real convenience; "
        "make it deliberately, and prefer one whose terms you have actually read.",
        "order": 2,
    },
}

# Whether a provider tells you how much thinking it did. Asking for reasoning
# and being told nothing back is not the same as being told it did none, and
# only one of those is worth a warning. Measured by asking, not assumed.
REASONING_REPORTED = {"openai-codex": False}

CONTINUITY_RECOMMENDATIONS = {
    "pulse": (
        "Fast, reliable tool-use model",
        "low",
        "Preserve the present without overthinking every 15-minute tick.",
    ),
    "autonomy": (
        "Strong general model with tool use",
        "medium",
        "Planning and follow-through benefit from some reasoning.",
    ),
    "daily": (
        "Strong reasoning model",
        "medium",
        "Daily memory should be careful without becoming an essay.",
    ),
    "weekly": (
        "Best reasoning model available",
        "high",
        "This run decides which patterns and memories last.",
    ),
    "monthly": (
        "Best reasoning model available",
        "high",
        "Long-horizon reflection is rare and worth the strongest model.",
    ),
    "hygiene": (
        "Fast, reliable tool-use model",
        "low",
        "Mostly bounded cleanup and integrity checks.",
    ),
    "timeline": (
        "Fast multimodal/tool-use model",
        "low",
        "Chooses a moment and hands a structured brief to the image provider.",
    ),
    "wake": (
        "Fast, warm conversational model",
        "low",
        "A short grounded start to the day.",
    ),
    "winddown": (
        "Fast, warm conversational model",
        "low",
        "A short continuity update, not deep analysis.",
    ),
    "window": (
        "Strong general model with web/tool use",
        "medium",
        "Independent work needs judgment and reliable tools.",
    ),
    "checkin": (
        "Fast, reliable extraction model",
        "low",
        "Turns recent conversation into verified continuity records.",
    ),
}


def _live_models(home, base_url, model_cfg):
    """Ask an OpenAI-shaped endpoint what it serves, using the profile's credential.

    The key is stored as a ${VAR} reference, so it is expanded from the same
    .env Hermes reads rather than being held anywhere else.
    """
    import urllib.request
    from companion_gateway import _env_values

    raw = str(model_cfg.get("api_key") or "")
    key = ""
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", raw.strip())
    if match:
        values = _env_values(home)
        key = str(values.get(match.group(1)) or os.environ.get(match.group(1)) or "")
    elif raw and not raw.startswith("$"):
        key = raw
    if not key:
        values = _env_values(home)
        if "mistral" in base_url.lower():
            key = str(
                values.get("MISTRAL_API_KEY") or os.environ.get("MISTRAL_API_KEY") or ""
            )
        elif "openai" in base_url.lower():
            key = str(
                values.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
            )
    request = urllib.request.Request(base_url.rstrip("/") + "/models")
    if key:
        request.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    rows = payload.get("data") if isinstance(payload, dict) else payload
    return sorted(
        str(r.get("id")) for r in (rows or []) if isinstance(r, dict) and r.get("id")
    )


def text(value, name, maxlen=300, empty=False):
    if (
        not isinstance(value, str)
        or len(value) > maxlen
        or any(ord(c) < 32 for c in value)
        or (not empty and not value.strip())
    ):
        raise ValueError(f"{name} must be plain text (maximum {maxlen} characters)")
    return value.strip()


def config(home):
    path = home / "config.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("Hermes config.yaml must be a mapping")
    return value


def sensitive_key(key):
    # Token counts are model settings, whereas singular tokens are credentials.
    key = re.sub(
        r"(?i)\b(?:max_|input_|output_|context_|total_|budget_)?tokens\b", "", str(key)
    )
    return bool(
        re.search(
            r"(?i)(secret|password|token|api.?key|auth|credential|cookie|bearer)", key
        )
    )


def public_config(value):
    if isinstance(value, dict):
        return {
            k: ("[configured]" if sensitive_key(k) and v else public_config(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [public_config(v) for v in value]
    if isinstance(value, str):
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

        if value.startswith(("http://", "https://")):
            try:
                url = urlsplit(value)
                host = url.netloc.rsplit("@", 1)[-1]
                query = urlencode(
                    [
                        (
                            k,
                            (
                                "[configured]"
                                if re.search(r"(?i)(key|token|secret|auth|password)", k)
                                else v
                            ),
                        )
                        for k, v in parse_qsl(url.query)
                    ]
                )
                return urlunsplit((url.scheme, host, url.path, query, ""))
            except ValueError:
                return "[invalid URL]"
        return hr.redact(value)
    return value


def save_config(home, mutate):
    with cp.file_lock(home / ".companion-config.lock"):
        value = config(home)
        mutate(value)
        path = home / "config.yaml"
        if path.exists():
            backup = (
                home
                / "companion-config-backups"
                / f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}-{uuid.uuid4().hex[:8]}.yaml'
            )
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        cp.atomic_write(
            path, yaml.safe_dump(value, sort_keys=False, allow_unicode=True)
        )


def inherit_api_credentials(source_home: Path, target_home: Path):
    """Copy onboarding API credentials into a newly created Hermes profile."""
    source = source_home / ".env"
    target = target_home / ".env"
    if not source.exists() or source.resolve() == target.resolve():
        return
    pattern = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*_API_KEY)\s*=")
    inherited = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            inherited[match.group(1)] = line
    if not inherited:
        return
    with cp.file_lock(target_home / ".companion-env.lock"):
        lines = (
            target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        )
        lines = [
            line
            for line in lines
            if not (pattern.match(line) and pattern.match(line).group(1) in inherited)
        ]
        lines.extend(inherited.values())
        cp.atomic_write(target, "\n".join(lines) + "\n")
        if os.name != "nt":
            target.chmod(0o600)


def register(app, select, load, operations):
    from .terminal import Consoles

    consoles = Consoles()
    app.state.consoles = consoles
    app.state.operations = operations

    def context():
        rt, profile = select()
        return rt, profile, rt.home(profile)

    def op(label, action):
        rt, profile, home = context()
        if any(
            c.scope[0] == str(rt.root) and not c.finished
            for c in consoles.rows.values()
        ):
            raise ValueError(
                "Close the native Hermes setup console before starting another action."
            )
        return operations.submit(
            str(rt.root),
            label,
            lambda report: action(rt, profile, home, report),
            profile=profile,
        )

    @app.post("/api/terminal")
    def open_terminal(payload: dict):
        rt, p, h = context()
        if str(rt.root) in operations.busy:
            raise ValueError("Wait for the running action to finish first")
        return consoles.open(rt, h, payload.get("action")).read()

    @app.get("/api/terminal/{ident}")
    def read_terminal(ident: str):
        rt, p, h = context()
        return consoles.get(ident, rt, h).read()

    @app.post("/api/terminal/{ident}/input")
    def write_terminal(ident: str, payload: dict):
        rt, p, h = context()
        consoles.get(ident, rt, h).write(payload.get("data"))
        return {"sent": True}

    @app.post("/api/terminal/{ident}/close")
    def close_terminal(ident: str):
        rt, p, h = context()
        consoles.get(ident, rt, h).close()
        return {"closed": True}

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/installations")
    def installations():
        return {
            "installations": [
                dict(id=k, **v.info()) for k, v in app.state.runtimes.items()
            ]
        }

    @app.post("/api/installations/link")
    def link_installation(payload: dict):
        root = (
            Path(text(payload.get("path"), "Hermes location", 4096))
            .expanduser()
            .resolve()
        )
        if root.is_file() and root.name in ("config.yaml", "companion.json"):
            root = root.parent
        if not root.is_dir() or not any(
            (root / name).exists()
            for name in ("config.yaml", "profiles", "hermes-agent")
        ):
            raise ValueError("Choose an existing Hermes home, or its config.yaml file.")
        for ident, runtime in app.state.runtimes.items():
            if runtime.root.resolve() == root:
                return {"installation": ident}
        ident = "linked-" + hashlib.sha256(str(root).encode()).hexdigest()[:12]
        path = app.state.linked_installations_file
        with cp.file_lock(path.with_suffix(".lock")):
            saved = hr.read_json(path, {})
            saved[ident] = str(root)
            cp.atomic_write(path, json.dumps(saved, indent=2) + "\n")
            import threading

            app.state.write_locks[ident] = threading.Lock()
            app.state.runtimes[ident] = hr.Runtime(root)
        return {"installation": ident}

    @app.post("/api/install")
    def install():
        return op("Install Hermes", lambda rt, p, h, report: rt.install(report))

    @app.get("/api/operations/{ident}")
    def operation(ident: str):
        row = operations.get(ident)
        rt, profile = select()
        application_root = str(Path(__file__).resolve().parents[2])
        visible_scope = row["scope"] == str(rt.root) or (
            row.get("kind") == "application" and row["scope"] == application_root
        )
        if not visible_scope or row.get("profile") != (profile or "default"):
            raise HTTPException(404, "Unknown operation")
        return row

    @app.get("/api/profiles")
    def profiles():
        from kit.cli.roster import discover

        rt, selected_profile = select()
        rows = []
        for name, home in discover(rt.root):
            if home.is_symlink():
                continue
            try:
                c = cc.load(home)
                label_path = home / "companion-display-name.json"
                label = (
                    json.loads(label_path.read_text()).get("name")
                    if label_path.is_file() and not label_path.is_symlink()
                    else None
                )
                rows.append(
                    {
                        "id": name or "default",
                        "name": label
                        or (
                            c.agent
                            if (home / cc.CONFIG_NAME).exists()
                            else (name or "Default Hermes")
                        ),
                        "installed": (home / cc.CONFIG_NAME).exists(),
                        "type": c.agent_type,
                        "home": str(home),
                        "vault": str(c.vault),
                    }
                )
            except (ValueError, OSError) as exc:
                rows.append(
                    {
                        "id": name or "default",
                        "name": name or "Default Hermes",
                        "installed": False,
                        "error": str(exc),
                    }
                )
        archives = []
        archive_root = rt.root / "profiles-removed"
        if archive_root.is_dir():
            for p in sorted(archive_root.iterdir(), reverse=True):
                if p.is_dir() and not p.is_symlink():
                    archives.append({"id": p.name})
        return {
            "profiles": rows,
            "archives": archives,
            "runtime": rt.info(),
            "selected_profile": selected_profile,
        }

    @app.post("/api/profile/display-name")
    def display_name(payload: dict):
        name = payload.get("name")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 100
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError("Choose a display name of 1–100 characters")

        def run(rt, p, h, report):
            target = h / "companion-display-name.json"
            if target.is_symlink():
                raise ValueError("Display-name file must not be a symlink")
            cp.atomic_write(
                target, json.dumps({"name": name.strip()}, ensure_ascii=False) + "\n"
            )
            return {
                "name": name.strip(),
                "note": "Workspace name saved. Hermes identity, profile paths, and jobs are unchanged.",
            }

        return op("Rename workspace profile", run)

    def appearance_file(home):
        target = home / "companion-appearance.json"
        if target.is_symlink():
            raise ValueError("Appearance file must not be a symlink")
        return target

    @app.get("/api/appearance")
    def appearance():
        rt, p, h = context()
        stored = hr.read_json(appearance_file(h), {})
        out = dict(APPEARANCE_DEFAULT)
        if isinstance(stored, dict):
            for k, v in stored.items():
                if k in out:
                    out[k] = v
        return {
            "appearance": out,
            "themes": {"dark": DARK_THEMES, "light": LIGHT_THEMES},
            "pinnable": PINNABLE,
        }

    @app.post("/api/appearance")
    def appearance_save(payload: dict):
        rt, p, h = context()
        if not isinstance(payload, dict):
            raise ValueError("Invalid appearance payload")
        current = hr.read_json(appearance_file(h), {})
        out = dict(APPEARANCE_DEFAULT)
        if isinstance(current, dict):
            for k, v in current.items():
                if k in out:
                    out[k] = v
        for key in ("theme", "dark_theme", "light_theme"):
            if key in payload:
                value = payload[key]
                if value not in THEMES:
                    raise ValueError(f"Unknown theme for {key}")
                if key == "dark_theme" and value not in DARK_THEMES:
                    raise ValueError("Choose a dark theme")
                if key == "light_theme" and value not in LIGHT_THEMES:
                    raise ValueError("Choose a light theme")
                out[key] = value
        if "accent" in payload:
            accent = payload["accent"] or ""
            if accent and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(accent)):
                raise ValueError(
                    "Accent must be a #rrggbb colour, or empty for the theme default"
                )
            out["accent"] = str(accent).lower()
        if "follow_system" in payload:
            out["follow_system"] = bool(payload["follow_system"])
        if "nav_pins" in payload:
            pins = payload["nav_pins"]
            if not isinstance(pins, list):
                raise ValueError("nav_pins must be a list")
            clean = []
            for item in pins:
                if item not in PINNABLE:
                    raise ValueError(f"Cannot pin unknown destination: {item}")
                if item not in clean:
                    clean.append(item)
            if not 1 <= len(clean) <= 4:
                raise ValueError("Pin between 1 and 4 destinations")
            out["nav_pins"] = clean
        cp.atomic_write(
            appearance_file(h), json.dumps(out, ensure_ascii=False, indent=2) + "\n"
        )
        return {"appearance": out, "saved": True}

    @app.get("/api/catalog")
    def catalog():
        import companion_render as render
        import companion_wizard as wizard
        import companion_catalog as catalog
        from zoneinfo import available_timezones

        return {
            "timezones": sorted(available_timezones()),
            "personas": render.load_personas(),
            "image_styles": render.load_styles(),
            "boundaries": {
                k: {
                    "label": v["label"],
                    "description": v["oneline"]
                    .replace("{H}’s", "your")
                    .replace("{H}", "you")
                    .replace("{A}", "they")
                    .replace("{AS_LOWER}", "they"),
                }
                for k, v in wizard.BOUNDARY_BANK.items()
            },
            "catalog": catalog.load(),
            "answer_keys": sorted(
                __import__(
                    "kit.cli.questions", fromlist=["known_answer_keys"]
                ).known_answer_keys()
            ),
        }

    @app.post("/api/onboarding/schedule")
    def onboarding_schedule(payload: dict):
        from kit.cli.common import load_manifest, mapping, next_schedule_offset
        import companion_render as render

        rt, _ = select()
        c = cc.Companion(
            profile=cp.profile_name(payload.get("profile") or "companion"),
            hermes_root=rt.root,
            agent_type=payload.get("agent_type", "companion"),
            quiet_start=payload.get("quiet_start", "23:00"),
            quiet_end=payload.get("quiet_end", "08:00"),
            timezone=payload.get("timezone", "UTC"),
        )
        if payload.get("adopt") is True:
            original = cc.load(rt.home(payload.get("profile") or "default"))
            c = cc.dataclasses.replace(
                original,
                quiet_start=c.quiet_start,
                quiet_end=c.quiet_end,
                timezone=c.timezone,
                agent_type=c.agent_type,
            )
        c.schedule_offset_minutes = next_schedule_offset(c)
        m = mapping(c, {})
        return {
            "timezone": c.timezone,
            "offset_minutes": c.schedule_offset_minutes,
            "jobs": [
                {
                    "name": spec["key"].replace("_", " "),
                    "schedule": render.render(spec["expr"], m),
                    "uses_model": not spec.get("no_agent", False),
                }
                for spec in load_manifest(c)["jobs"]
            ],
        }

    def approve_schedule(rt, home, report, result, approved):
        if approved:
            try:
                report(
                    "Testing the new companion’s model before enabling its approved schedule"
                )
                response = rt.run(
                    [
                        "chat",
                        "--quiet",
                        "--oneshot",
                        "--ignore-rules",
                        "--max-turns",
                        "1",
                        "-q",
                        "Reply with exactly: CONNECTION_OK. Do not use any tools.",
                    ],
                    home=home,
                    timeout=180,
                )
                if "CONNECTION_OK" not in response.stdout:
                    raise ValueError("The model did not return the connection check.")
                rt.run(
                    ["--home", str(home), "schedule", "active"],
                    home=home,
                    kit=True,
                    timeout=600,
                )
                result.update(
                    schedule_active=True,
                    schedule_note="Schedule approved and enabled. The owning Hermes gateway must be running; review its status in Settings.",
                )
            except Exception as exc:
                result["schedule_note"] = (
                    "Companion saved; schedule activation needs attention. "
                    + hr.redact(str(exc))[:400]
                )
        return result

    @app.post("/api/profiles")
    def create(payload: dict):
        name = cp.profile_name(payload.get("profile", ""))
        answers = payload.get("answers")
        if not isinstance(answers, dict) or not answers.get("boundary"):
            raise ValueError("Choose a relationship frame")
        from kit.cli.questions import known_answer_keys

        if set(answers) - known_answer_keys():
            raise ValueError("Unknown setup answers")
        rt, _ = select()
        if cp.profile_path(rt.root, name).exists():
            raise ValueError("Profile already exists. Choose Adopt or Repair.")
        answers = {
            **answers,
            "gateway_mode": "later",
            "gateway_action": "status",
            "cron_active": False,
        }
        if not answers.get("vault"):
            from kit.cli.roster import existing_vault

            answers["vault"] = str(
                existing_vault(rt.root)
                or (
                    rt.root.parent / "companion-vault"
                    if rt.managed
                    else Path.home() / "vault"
                )
            )
        approved = payload.get("schedule_approved") is True

        def create_profile(rt, p, h, report):
            output = hr.redact(
                rt.run(
                    [
                        "--home",
                        str(rt.root),
                        "add",
                        name,
                        "--answers",
                        json.dumps(answers),
                    ],
                    home=rt.root,
                    kit=True,
                    timeout=600,
                ).stdout
            )
            profile_home = cp.profile_path(rt.root, name)
            inherit_api_credentials(rt.root, profile_home)
            result = {
                "output": output,
                "profile": name,
                "schedule_active": False,
                "schedule_note": "Background model jobs are paused. Enable them in Schedule & usage.",
            }
            approve_schedule(rt, profile_home, report, result, approved)
            return result

        return op("Create " + name, create_profile)

    @app.post("/api/adopt")
    def adopt(payload: dict):
        answers = payload.get("answers", {})
        if not isinstance(answers, dict) or not answers.get("boundary"):
            raise ValueError("Choose a relationship frame")

        def adopt_profile(rt, p, h, report):
            output = hr.redact(
                rt.run(
                    [
                        "--home",
                        str(h),
                        "upgrade",
                        "--soul",
                        "keep",
                        "--answers",
                        json.dumps(
                            {
                                **answers,
                                "cron_active": False,
                                "gateway_mode": "later",
                                "gateway_action": "status",
                            }
                        ),
                    ],
                    home=h,
                    kit=True,
                    timeout=600,
                ).stdout
            )
            result = {
                "output": output,
                "profile": p,
                "schedule_active": False,
                "schedule_note": "Background model jobs are paused. Enable them in Schedule & usage.",
            }
            return approve_schedule(
                rt, h, report, result, payload.get("schedule_approved") is True
            )

        return op("Adopt existing Hermes companion", adopt_profile)

    @app.post("/api/profile/archive")
    def archive(payload: dict):
        rt, profile, home = context()
        if profile in ("", "default"):
            raise ValueError("The root installation cannot be archived as a profile")
        if payload.get("confirm") != profile:
            raise ValueError("Type the profile name to confirm archiving")

        def action(rt, p, h, report):
            import companion_gateway as gateway

            state = gateway.status(cc.load(h))
            if state["pid_records"]:
                raise ValueError(
                    "Stop the owning gateway before archiving this profile, then retry."
                )
            if gateway.service_units(h):
                raise ValueError(
                    "Uninstall this profile’s dedicated gateway service before archiving, then retry. Its vault will be preserved."
                )
            return {
                "output": hr.redact(
                    rt.run(
                        ["--home", str(rt.root), "remove", p, "--force"],
                        home=rt.root,
                        kit=True,
                    ).stdout
                )
            }

        return op("Archive " + profile, action)

    @app.post("/api/profile/restore")
    def restore(payload: dict):
        ident = text(payload.get("archive"), "archive", 120)
        name = cp.profile_name(payload.get("profile", ""))
        if "/" in ident or "\\" in ident or ident.startswith("."):
            raise ValueError("Invalid archive")

        def action(rt, p, h, report):
            source = rt.root / "profiles-removed" / ident
            if not source.is_dir() or source.is_symlink():
                raise ValueError("Archive not found")
            stored = hr.read_json(source / "companion.json", {})
            if stored.get("profile") != name:
                raise ValueError(
                    "Restore using the original profile name to preserve vault paths"
                )
            dest = cp.profile_path(rt.root, name)
            if dest.exists():
                raise ValueError("Profile name is already in use")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))
            return {
                "restored": name,
                "note": "Profile restored with its original paths. Inspect Health before starting its gateway.",
            }

        return op("Restore " + name, action)

    @app.post("/api/profile/purge")
    def purge(payload: dict):
        # Permanent deletion is intentionally limited to already archived homes.
        ident = text(payload.get("archive"), "archive", 120)
        if (
            payload.get("confirm") != ident
            or "/" in ident
            or "\\" in ident
            or ident.startswith(".")
        ):
            raise ValueError("Type the complete archive name to permanently delete it")

        def action(rt, p, h, report):
            source = rt.root / "profiles-removed" / ident
            if not source.is_dir() or source.is_symlink():
                raise ValueError("Archive not found")
            shutil.rmtree(source)
            return {"deleted": ident, "vault_preserved": True}

    @app.get("/api/onboarding/environment")
    def onboarding_environment():
        rt, p, h = context()
        c = load()
        from kit.cli.roster import discover

        installed = []
        for name, home in discover(rt.root):
            if not home.is_symlink() and (home / cc.CONFIG_NAME).exists():
                installed.append(name or "default")

        from companion_gateway import _env_values, preflight, status

        env = _env_values(c.home)
        root_env = _env_values(c.hermes_root)
        token = (
            env.get("TELEGRAM_BOT_TOKEN")
            or root_env.get("TELEGRAM_BOT_TOKEN")
            or os.environ.get("TELEGRAM_BOT_TOKEN")
            or ""
        )
        users = (
            env.get("TELEGRAM_ALLOWED_USERS")
            or root_env.get("TELEGRAM_ALLOWED_USERS")
            or os.environ.get("TELEGRAM_ALLOWED_USERS")
            or ""
        )

        gw_pre = preflight(c)
        is_connected = bool(gw_pre.get("connected")) or (
            bool(token) and bool(gw_pre.get("alive"))
        )

        cfg = config(h)
        root_cfg = config(c.hermes_root)
        model_cfg = cfg.get("model") or root_cfg.get("model") or {}
        if isinstance(model_cfg, str):
            model_name = model_cfg
            provider_name = ""
        else:
            model_name = model_cfg.get("default") or model_cfg.get("model") or ""
            provider_name = model_cfg.get("provider") or ""

        catalog_rows = rt.catalog() if rt.info()["available"] else []
        has_cred = False
        for row in catalog_rows or FALLBACK_CATALOG:
            if any(
                bool(env.get(k) or root_env.get(k) or os.environ.get(k))
                for k in row.get("api_key_env_vars", [])
            ):
                has_cred = True
                break
        auth_file = c.hermes_root / "auth.json"
        if auth_file.exists():
            try:
                auth_data = json.loads(auth_file.read_text(encoding="utf-8"))
                if auth_data.get("active_provider") or auth_data.get("credential_pool"):
                    has_cred = True
            except Exception:
                pass

        loc = {}
        try:
            from kit.app import local_models as lm

            mem = lm.get_host_memory()
            lm_stat = lm.status(rt)
            loc = {
                "is_mobile": mem["is_mobile"],
                "host_memory": mem,
                "safety_limit_gb": lm.MOBILE_MAX_MODEL_GB if mem["is_mobile"] else None,
                "online": lm_stat.get("online", False),
                "engine": lm_stat.get("engine", "None"),
                "installed": lm_stat.get("installed", False),
                "loaded_model": lm_stat.get("loaded_model"),
                "recommendations": lm_stat.get("recommendations", []),
                "recommended_gguf": lm_stat.get(
                    "recommended_gguf", getattr(lm, "RECOMMENDED_GGUF_MODELS", [])
                ),
                "available_models": lm_stat.get("available_models", []),
            }
        except Exception:
            pass

        return {
            "profiles_count": len(installed),
            "has_installed_profiles": len(installed) > 0,
            "telegram": {
                "configured": bool(token),
                "has_token": bool(token),
                "token_preview": (
                    (token[:6] + "..." + token[-4:])
                    if token and len(token) > 10
                    else ""
                ),
                "has_user_id": bool(users),
                "user_id": users,
                "is_connected": is_connected,
            },
            "inference": {
                "configured": bool(model_name and has_cred),
                "model": model_name,
                "provider": provider_name,
                "has_credential": has_cred,
            },
            "local_models": loc,
        }

    @app.post("/api/onboarding/local-setup")
    def onboarding_local_setup(payload: dict):
        rt, p, h = context()
        c = load()
        from kit.app import local_models as lm

        model_id = text(payload.get("model_id", ""), "Model ID", 200, empty=True)
        setup_type = payload.get("type", "gguf")
        model_path = payload.get("path", "")

        def perform_setup(report):
            mem = lm.get_host_memory()
            target_alias = model_id
            target_path = model_path

            if setup_type == "gguf":
                res = lm.download_gguf(rt, model_id, report)
                target_path = res.get("path", "")
                target_alias = model_id.replace("-instruct-q4_k_m", "").replace(
                    "-q4_k_m", ""
                )[:24]
            elif setup_type == "ollama":
                lm.pull(rt, model_id, report)
                target_alias = model_id
            elif setup_type == "disk":
                p_file = Path(target_path)
                if not target_path or not p_file.is_file():
                    raise ValueError(f"Model file not found at {target_path}")
                size_gb = round(p_file.stat().st_size / (1024**3), 2)
                safe, msg = lm.validate_model_safety(size_gb, mem)
                if not safe:
                    raise ValueError(msg)
                target_alias = (
                    p_file.stem.lower()
                    .replace("-it", "")
                    .replace("-abliterated", "")[:24]
                )

            if not lm.status(rt)["online"]:
                try:
                    lm.start(rt, report)
                except Exception:
                    pass

            ctx_len = 4096 if mem["is_mobile"] else 8192
            provider_type = "ollama" if setup_type == "ollama" else "custom:local_llama"

            for target_home in dict.fromkeys([c.home, c.hermes_root]):

                def mutate(cfg):
                    cfg.setdefault("model", {})
                    if isinstance(cfg["model"], str):
                        cfg["model"] = {"default": cfg["model"]}
                    cfg["model"]["default"] = target_alias
                    cfg["model"]["provider"] = provider_type
                    cfg["model"]["base_url"] = "http://127.0.0.1:11434/v1"
                    cfg["model"]["context_length"] = ctx_len
                    cfg["fallback_providers"] = []

                save_config(target_home, mutate)

            with cp.file_lock(h / ".companion-profile-editor.lock"):
                companion_path = h / cc.CONFIG_NAME
                if companion_path.exists():
                    cfg = json.loads(companion_path.read_text(encoding="utf-8"))
                    cfg.setdefault("models", {})
                    cfg["models"]["chat"] = {
                        "provider": provider_type,
                        "model": target_alias,
                        "reasoning_effort": "none",
                    }
                    cfg["models"]["loops"] = {
                        "provider": provider_type,
                        "model": target_alias,
                        "reasoning_effort": "none",
                    }
                    cfg["models"]["reflection"] = {
                        "provider": provider_type,
                        "model": target_alias,
                        "reasoning_effort": "none",
                    }
                    cp.atomic_write(
                        companion_path,
                        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                    )

            report(f"Configured {target_alias} as local brain for your companion.")
            return {
                "ok": True,
                "configured": True,
                "model": target_alias,
                "path": target_path,
                "provider": provider_type,
                "note": f"Local model {target_alias} is active and ready.",
            }

        return app.state.operations.submit(
            str(rt.root), "Set up local companion model", perform_setup, profile=p
        )

    @app.post("/api/onboarding/telegram")
    def onboarding_telegram(payload: dict):
        rt, p, h = context()
        c = load()
        token = text(payload.get("token", ""), "Telegram Bot Token", 200, empty=True)
        user_id = text(payload.get("user_id", ""), "Telegram User ID", 200, empty=True)
        if token and not re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", token):
            raise ValueError(
                "Invalid Telegram Bot Token format. Tokens look like: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
            )
        if user_id and not re.match(r"^[\d,\s-]+$", user_id):
            raise ValueError(
                "Telegram User ID must be numeric (e.g. from @userinfobot)"
            )

        for target_home in dict.fromkeys([c.home, c.hermes_root]):
            env_path = target_home / ".env"
            with cp.file_lock(target_home / ".companion-env.lock"):
                lines = (
                    env_path.read_text(encoding="utf-8").splitlines()
                    if env_path.exists()
                    else []
                )
                lines = [
                    l
                    for l in lines
                    if not re.match(
                        r"^\s*(?:export\s+)?TELEGRAM_(?:BOT_TOKEN|ALLOWED_USERS)\s*=", l
                    )
                ]
                if token:
                    lines.append(f"TELEGRAM_BOT_TOKEN={json.dumps(token)}")
                if user_id:
                    clean_users = ",".join(re.findall(r"\d+", user_id))
                    lines.append(f"TELEGRAM_ALLOWED_USERS={json.dumps(clean_users)}")
                cp.atomic_write(env_path, "\n".join(lines) + "\n")
                if os.name != "nt":
                    env_path.chmod(0o600)
        return {"saved": True, "configured": bool(token)}

    @app.post("/api/onboarding/inference")
    def onboarding_inference(payload: dict):
        rt, p, h = context()
        c = load()
        provider = text(
            payload.get("provider", ""), "Provider", 100, empty=True
        ).lower()
        model = text(payload.get("model", ""), "Model", 300, empty=True)
        api_key = text(payload.get("api_key", ""), "API Key", 1000, empty=True)

        if api_key and provider:
            rows = rt.catalog() if rt.info()["available"] else []
            p_row = next(
                (
                    r
                    for r in (rows or FALLBACK_CATALOG)
                    if r.get("id") == provider or r.get("slug") == provider
                ),
                None,
            )
            env_var = p_row.get("api_key_env_vars", [None])[0] if p_row else None
            if not env_var:
                env_var = {
                    "mistral": "MISTRAL_API_KEY",
                    "openrouter": "OPENROUTER_API_KEY",
                    "openai": "OPENAI_API_KEY",
                    "xai": "XAI_API_KEY",
                    "deepseek": "DEEPSEEK_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY",
                    "groq": "GROQ_API_KEY",
                }.get(provider, f"{provider.upper()}_API_KEY")

            for target_home in dict.fromkeys([c.home, c.hermes_root]):
                env_path = target_home / ".env"
                with cp.file_lock(target_home / ".companion-env.lock"):
                    lines = (
                        env_path.read_text(encoding="utf-8").splitlines()
                        if env_path.exists()
                        else []
                    )
                    lines = [
                        l
                        for l in lines
                        if not re.match(
                            r"^\s*(?:export\s+)?" + re.escape(env_var) + r"\s*=", l
                        )
                    ]
                    lines.append(f"{env_var}={json.dumps(api_key)}")
                    cp.atomic_write(env_path, "\n".join(lines) + "\n")
                    if os.name != "nt":
                        env_path.chmod(0o600)

        if model:

            def mutate(cfg):
                cfg.setdefault("model", {})
                if isinstance(cfg["model"], str):
                    cfg["model"] = {"default": cfg["model"]}
                cfg["model"]["default"] = model
                if provider:
                    cfg["model"]["provider"] = provider

            save_config(c.hermes_root, mutate)
            save_config(h, mutate)

        return {"saved": True, "model": model, "provider": provider}

    @app.post("/api/onboarding/oauth/start")
    def onboarding_oauth_start(payload: dict):
        rt, p, h = context()
        provider = text(payload.get("provider", "xai-oauth"), "Provider", 50).lower()
        if provider not in ("xai-oauth", "openai-codex", "qwen-oauth", "minimax-oauth"):
            raise ValueError("Unsupported OAuth provider")

        sid = secrets.token_hex(8)
        sess = {
            "session_id": sid,
            "provider": provider,
            "status": "pending",
            "url": "",
            "code": "",
            "created_at": time.time(),
        }
        cmd = rt.command() + [
            "auth",
            "add",
            provider,
            "--type",
            "oauth",
            "--no-browser",
            "--timeout",
            "300",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                env=rt.env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            raise ValueError(f"Failed to start OAuth flow: {exc}")

        sess["proc"] = proc
        with _ONBOARDING_OAUTH_LOCK:
            _ONBOARDING_OAUTH_SESSIONS[sid] = sess

        def _worker():
            out_lines = []
            err_lines = []

            def _read_out():
                for line in iter(proc.stdout.readline, ""):
                    out_lines.append(line)
                    m_url = re.search(r"https?://[^\s)]+", line)
                    if m_url and not sess.get("url"):
                        sess["url"] = m_url.group(0)
                    m_code = re.search(
                        r"(?:user_code=([A-Za-z0-9_-]+)|code:\s*([A-Za-z0-9_-]+))",
                        line,
                        re.IGNORECASE,
                    )
                    if m_code and not sess.get("code"):
                        sess["code"] = m_code.group(1) or m_code.group(2)
                proc.stdout.close()

            def _read_err():
                for line in iter(proc.stderr.readline, ""):
                    err_lines.append(line)
                proc.stderr.close()

            t_out = threading.Thread(target=_read_out, daemon=True)
            t_err = threading.Thread(target=_read_err, daemon=True)
            t_out.start()
            t_err.start()
            ret = proc.wait()
            t_out.join(timeout=2)
            t_err.join(timeout=2)

            with _ONBOARDING_OAUTH_LOCK:
                if sess.get("cancelled"):
                    sess["status"] = "cancelled"
                elif ret == 0:
                    sess["status"] = "approved"
                else:
                    sess["status"] = "error"
                    sess["error"] = hr.redact("".join(err_lines) or "".join(out_lines))[
                        -1000:
                    ]

        threading.Thread(target=_worker, daemon=True).start()

        deadline = time.time() + 3.5
        while time.time() < deadline:
            if sess.get("url") or sess.get("status") in ("approved", "error"):
                break
            time.sleep(0.15)

        return {
            "session_id": sid,
            "provider": provider,
            "verification_url": sess.get("url", ""),
            "user_code": sess.get("code", ""),
            "status": sess.get("status", "pending"),
            "error": sess.get("error"),
        }

    @app.get("/api/onboarding/oauth/poll/{ident}")
    def onboarding_oauth_poll(ident: str):
        with _ONBOARDING_OAUTH_LOCK:
            sess = _ONBOARDING_OAUTH_SESSIONS.get(ident)
        if not sess:
            raise HTTPException(status_code=404, detail="OAuth session not found")
        return {
            "session_id": ident,
            "provider": sess.get("provider"),
            "status": sess.get("status", "pending"),
            "verification_url": sess.get("url", ""),
            "user_code": sess.get("code", ""),
            "error": sess.get("error"),
        }

    @app.post("/api/onboarding/oauth/cancel/{ident}")
    def onboarding_oauth_cancel(ident: str):
        with _ONBOARDING_OAUTH_LOCK:
            sess = _ONBOARDING_OAUTH_SESSIONS.get(ident)
        if sess and sess.get("proc"):
            sess["cancelled"] = True
            try:
                sess["proc"].terminate()
            except Exception:
                pass
            sess["status"] = "cancelled"
        return {"cancelled": True}

    @app.get("/api/environment")
    def environment():
        rt, p, h = context()
        cfg = config(h)
        model = cfg.get("model") or {}
        if isinstance(model, str):
            model = {"default": model}
        # Explicit allowlist: config can contain inline credentials anywhere else.
        public = {k: model.get(k, "") for k in ("default", "provider", "base_url")}
        chain = [
            {k: r.get(k, "") for k in ("model", "provider", "base_url")}
            for r in (cfg.get("fallback_providers") or [])
            if isinstance(r, dict)
        ]
        c = cc.load(h)
        return {
            "runtime": rt.info(),
            "model": public_config(public),
            "fallbacks": public_config(chain),
            "tiers": public_config(c.models),
            "timezone": cfg.get("timezone", c.timezone),
            "restart_note": "New sessions and job runs use updated settings; restart the gateway to reload persistent workers.",
        }

    @app.get("/api/voice")
    def voice_settings():
        from . import speech

        rt, p, h = context()
        return {
            "tts": public_config(config(h).get("tts") or {}),
            "fields": speech.FIELDS,
            "labels": speech.LABELS,
            "local": list(speech.LOCAL),
            "reference": sorted(speech.REFERENCE),
            "installed": {
                name: speech.engine_python(rt.root, name).is_file()
                for name in speech.LOCAL
            },
        }

    @app.post("/api/voice")
    def voice_save(payload: dict):
        from . import speech

        provider = payload.get("provider")
        controls = payload.get("controls", {})
        # Preserve the original workspace API for existing clients.
        if "controls" not in payload:
            controls = {
                k: payload[k]
                for k in ("speed", "pitch")
                if k in payload and k in speech.FIELDS.get(provider, {})
            }
        controls = speech.validate(provider, controls)
        voice = text(payload.get("voice", ""), "voice", 200, empty=True)
        transcript = payload.get("transcript", "")
        if not isinstance(transcript, str) or len(transcript) > 10000:
            raise ValueError("Transcript is too long")

        def run(rt, p, h, report):
            if provider in speech.LOCAL:
                source = rt.root / "hermes-agent" / "tools" / "tts_command_provider.py"
                if not source.is_file():
                    raise ValueError(
                        "Update Hermes to a version supporting tts.providers command adapters before selecting this engine."
                    )
            save_config(
                h,
                lambda cfg: speech.configure(
                    cfg, rt.root, h, provider, voice, controls, transcript
                ),
            )
            return {
                "note": "Voice saved in this companion’s Hermes config. New speech requests use these settings."
            }

        return op("Save voice", run)

    @app.post("/api/voice/inherit")
    def voice_inherit():
        import shlex

        def run(rt, p, h, report):
            if h == rt.root:
                raise ValueError("The default profile cannot inherit from itself")
            root_tts = config(rt.root).get("tts") or {}
            if (
                not root_tts.get("provider")
                or root_tts.get("provider") == "companion-default"
            ):
                raise ValueError(
                    "Configure a voice on the installation’s default profile first"
                )
            python = cp.venv_executable(rt.root / "hermes-agent")
            script = hr.KIT / "kit/scripts/companion_tts_inherit.py"
            if (
                not python.is_file()
                or not (
                    rt.root / "hermes-agent/tools/tts_command_provider.py"
                ).is_file()
            ):
                raise ValueError("Update Hermes for command-provider support first")
            args = [
                str(python),
                str(script),
                "--root",
                str(rt.root),
                "--input",
                "{input_path}",
                "--output",
                "{output_path}",
            ]
            command = (
                __import__("subprocess").list2cmdline(args)
                if os.name == "nt"
                else shlex.join(args)
            )

            def change(cfg):
                tts = cfg.setdefault("tts", {})
                tts["provider"] = "companion-default"
                tts.setdefault("providers", {})["companion-default"] = {
                    "type": "command",
                    "command": command,
                    "output_format": "wav",
                    "timeout": 660,
                }

            save_config(h, change)
            return {
                "note": "This companion now uses the installation’s current voice settings for every speech request."
            }

        return op("Use installation voice", run)

    @app.post("/api/voice/install")
    def install_voice(payload: dict):
        provider = payload.get("provider")
        from . import speech

        if provider in speech.LOCAL:
            return op(
                "Install " + provider,
                lambda rt, p, h, report: speech.install(rt, provider, report),
            )
        if provider not in ("piper", "kittentts", "neutts"):
            raise ValueError("Choose a local engine to install")

        def run(rt, p, h, report):
            import subprocess

            python = cp.venv_executable(rt.root / "hermes-agent")
            if not python.is_file():
                raise ValueError("Use Full Hermes setup for this installation")
            script = "import sys, shutil, importlib; from hermes_cli import setup; from hermes_cli.tools_config import _pip_install; provider=sys.argv[1]; "
            script += "assert provider!='neutts' or shutil.which('espeak-ng') or shutil.which('espeak'), 'Install espeak-ng through Full Hermes setup first'; "
            script += "ok=(getattr(setup, '_install_kittentts_deps', None) or importlib.import_module('hermes_cli.setup_tts')._install_kittentts_deps)() if provider=='kittentts' else _pip_install(['piper-tts' if provider=='piper' else 'neutts[all]'], timeout=600).returncode==0; sys.exit(0 if ok else 1)"
            report(
                "Installing "
                + provider
                + " into the Hermes environment. Models download on first use."
            )
            result = subprocess.run(
                [str(python), "-c", script, provider],
                env=rt.env(h),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=660,
            )
            if result.returncode:
                raise ValueError(hr.redact(result.stderr or result.stdout)[-4000:])
            return {
                "note": "Engine installed. Save your voice and generate a preview to download its model and try it."
            }

        return op("Install local speech engine", run)

    @app.post("/api/voice/reference")
    async def voice_reference(request: Request, provider: str = "neutts"):
        from .speech import REFERENCE

        if provider not in REFERENCE:
            raise ValueError("This provider does not use reference clips")
        import io
        import wave

        data = await request.body()
        if len(data) > 20_000_000:
            raise ValueError("Reference clip exceeds 20 MB")
        try:
            with wave.open(io.BytesIO(data)) as clip:
                duration = clip.getnframes() / clip.getframerate()
                if not 1 <= duration <= 30:
                    raise ValueError("Choose a WAV clip between 1 and 30 seconds")
        except (wave.Error, EOFError):
            raise ValueError("Choose an uncompressed WAV audio clip")
        rt, p, h = context()
        c = cc.load(h)
        dest = (
            (c.data / "voice" / "reference.wav")
            if provider == "neutts"
            else (c.data / "voice" / provider / "reference.wav")
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as handle:
            handle.write(data)
            temporary = handle.name
        os.replace(temporary, dest)
        save_config(
            h,
            lambda cfg: cfg.setdefault("tts", {})
            .setdefault(provider, {})
            .update(ref_audio=str(dest)),
        )
        return {"saved": True}

    FORBIDDEN_VOICE_TERMS = {
        "sex",
        "orgasm",
        "moan",
        "erotic",
        "nsfw",
        "pussy",
        "penis",
        "breasts",
        "boobs",
        "fuck",
        "cum",
        "whore",
        "slut",
    }

    @app.post("/api/voice/preview")
    def voice_preview(payload: dict):
        sample = text(payload.get("text"), "preview text", 1000)
        if any(term in sample.lower() for term in FORBIDDEN_VOICE_TERMS):
            raise HTTPException(
                400,
                "Audio synthesis of sexual or intimate phrases without companion agency is strictly disallowed.",
            )

        def run(rt, p, h, report):
            import subprocess

            command = Path(rt.command()[0]).resolve()
            python = cp.venv_executable(rt.root / "hermes-agent")
            if not python.is_file():
                python = command.parent / (
                    "python.exe" if os.name == "nt" else "python"
                )
            if not python.is_file():
                raise ValueError(
                    "Cannot locate Hermes Python. Use Full Hermes setup to check this installation."
                )
            c = cc.load(h)
            dest = c.data / "voice" / "preview.mp3"
            dest.parent.mkdir(parents=True, exist_ok=True)
            script = 'from tools.tts_tool import text_to_speech_tool; import sys,json; print("COMPANION_VOICE_RESULT="+json.dumps(json.loads(text_to_speech_tool(sys.argv[1],sys.argv[2]))))'
            result = subprocess.run(
                [str(python), "-c", script, sample, str(dest)],
                env=rt.env(h),
                capture_output=True,
                text=True,
                timeout=660,
            )
            if result.returncode:
                raise ValueError(hr.redact(result.stderr)[-3000:])
            try:
                response = json.loads(
                    next(
                        line.split("=", 1)[1]
                        for line in result.stdout.splitlines()
                        if line.startswith("COMPANION_VOICE_RESULT=")
                    )
                )
            except (ValueError, IndexError, StopIteration):
                raise ValueError("Speech engine returned an unreadable response")
            if not response.get("success"):
                raise ValueError(hr.redact(str(response.get("error") or response)))
            actual = Path(response.get("file_path", str(dest))).resolve()
            if (
                actual.parent != dest.parent.resolve()
                or not actual.is_file()
                or actual.suffix not in (".wav", ".mp3", ".ogg")
            ):
                raise ValueError("Speech engine did not save a playable preview")
            cp.atomic_write(
                dest.parent / "preview-result.json", json.dumps({"file": actual.name})
            )
            return {"note": "Preview ready", "audio": "/api/voice/preview-audio"}

        return op("Preview voice", run)

    @app.get("/api/voice/preview-audio")
    def voice_preview_audio():
        from fastapi.responses import FileResponse

        c = load()
        folder = (c.data / "voice").resolve()
        metadata = hr.read_json(folder / "preview-result.json", {})
        path = (folder / metadata.get("file", "missing")).resolve()
        if (
            path.parent != folder
            or path.suffix not in (".mp3", ".wav", ".ogg")
            or not path.is_file()
        ):
            raise HTTPException(404, "No preview yet")
        return FileResponse(path)

    @app.get("/api/config")
    def full_config():
        rt, p, h = context()
        return {"config": public_config(config(h))}

    @app.post("/api/config")
    def config_value(payload: dict):
        key = text(payload.get("key"), "configuration key", 150)
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)*", key):
            raise ValueError("Use a dotted Hermes config key such as terminal.backend")
        if sensitive_key(key):
            raise ValueError(
                "Use the credential form or native provider setup for secrets"
            )
        value = payload.get("value")
        encoded = value if isinstance(value, str) else json.dumps(value)
        if len(encoded) > 20000:
            raise ValueError("Configuration value is too large")

        def run(rt, p, h, report):
            rt.run(["config", "set", key, encoded, "--force"], home=h)
            return {
                "saved": key,
                "note": "Hermes saved the setting. Restart persistent workers when needed.",
            }

        return op("Save Hermes setting", run)

    @app.get("/api/inference/presets")
    def inference_presets():
        rt, _, h = context()
        from companion_gateway import _env_values

        values = _env_values(h)
        out = []
        for p in INFERENCE_PRESETS:
            ready = all(
                bool(values.get(k) or os.environ.get(k)) for k in p["requires_env"]
            )
            out.append({**p, "ready": ready})
        return {"presets": out}

    @app.post("/api/inference/apply-preset")
    def apply_inference_preset(payload: dict):
        preset_id = text(payload.get("id", ""), "preset id", 100)
        preset = next((p for p in INFERENCE_PRESETS if p["id"] == preset_id), None)
        if not preset:
            raise ValueError("Unknown inference preset")
        rt, p, h = context()
        c = cc.load(h)
        primary = dict(preset["primary"])
        fallbacks = [dict(f) for f in preset["fallbacks"]]

        def mutate(cfg):
            old = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
            cfg["model"] = {
                "default": primary["model"],
                "provider": primary["provider"],
            }
            if "base_url" in primary:
                cfg["model"]["base_url"] = primary["base_url"]
            else:
                cfg["model"].pop("base_url", None)
            cfg["fallback_providers"] = fallbacks

        save_config(h, mutate)
        for tier in ("chat", "loops", "reflection"):
            c.models[tier] = {
                "provider": primary["provider"],
                "model": primary["model"],
                "reasoning_effort": "none",
            }
        c.models["fallbacks"] = fallbacks
        c.save()
        return {
            "applied": True,
            "preset": preset["name"],
            "primary": primary,
            "fallbacks": fallbacks,
            "note": f"Applied {preset['name']}. Primary and fallback cascade saved to config.",
        }

    @app.get("/api/providers")
    def providers():
        rt, _, h = context()
        rows = rt.catalog() if rt.info()["available"] else []
        from companion_gateway import _env_values

        values = _env_values(h)
        return {
            "providers": [
                {
                    **row,
                    "credential_configured": any(
                        bool(values.get(k) or os.environ.get(k))
                        for k in row.get("api_key_env_vars", [])
                    ),
                }
                for row in (rows or FALLBACK_CATALOG)
            ],
            "source": (
                "installed Hermes catalog" if rows else "basic compatibility catalog"
            ),
        }

    @app.get("/api/models/catalog")
    def models_catalog(provider: str = "", base_url: str = "", refresh: int = 0):
        """The models a provider actually offers, so picking one is a choice from a list.

        Hermes writes a per-provider cache of live /v1/models results whenever
        its own picker runs, and that file is the fast path here — reading it
        beats importing hermes_cli, which lives in a different virtualenv.
        Named providers are keyed by name; a `custom` provider is keyed by its
        address, because "custom" alone says nothing about what is served
        there. An address also means we can go and ask, which is what Refresh
        does."""
        rt, _, h = context()
        provider = (provider or "").strip().lower()
        base_url = (base_url or "").strip()
        cfg = config(h).get("model") or {}
        if not provider:
            provider = str(cfg.get("provider") or "").strip().lower()
        # An empty endpoint on a custom provider means "whatever the profile uses".
        if not base_url and provider in ("", "custom"):
            base_url = str(cfg.get("base_url") or "").strip()

        key = f'custom:{base_url.rstrip("/")}' if base_url else provider
        models, source, note = [], "none", ""
        if not refresh or not base_url:
            try:
                cache = json.loads(
                    (h / "provider_models_cache.json").read_text(encoding="utf-8")
                )
                models = [str(m) for m in ((cache.get(key) or {}).get("models") or [])]
                if models:
                    source = "cache"
            except Exception:
                pass
        target_url = base_url or (
            "https://api.mistral.ai/v1" if provider == "mistral" else ""
        )
        if not models and target_url:
            try:
                models = _live_models(h, target_url, cfg)
                source = "live"
            except Exception as exc:
                if provider == "mistral":
                    models = [
                        "mistral-large-latest",
                        "mistral-medium-latest",
                        "mistral-small-latest",
                        "ministral-14b-latest",
                        "ministral-8b-latest",
                        "codestral-latest",
                    ]
                    source = "static"
                else:
                    note = f"Could not reach {target_url}: " + hr.redact(str(exc))[:160]
        elif not models and provider == "mistral":
            models = [
                "mistral-large-latest",
                "mistral-medium-latest",
                "mistral-small-latest",
                "ministral-14b-latest",
                "ministral-8b-latest",
                "codestral-latest",
            ]
            source = "static"
        if not models and not note:
            note = "Hermes has no model list yet. Connect this provider in Hermes, or enter a model name."
        return {
            "models": models,
            "provider": provider,
            "base_url": base_url,
            "source": source,
            "cache_key": key,
            "note": note,
        }

    @app.get("/api/models/providers")
    def models_providers():
        """The providers this profile can actually reach, discovered rather than assumed.

        Three signals, because no one of them is complete. `credential_configured`
        only notices a provider's own API-key variable, so it misses a Mistral
        wired up as `custom` and an OpenAI signed in through OAuth. A non-empty
        model cache is the strongest evidence there is — Hermes only caches a
        live /v1/models result that came back populated, which means the
        credential worked. And the profile's own default belongs in the list
        whether or not anything else has noticed it."""
        rt, _, h = context()
        cfg = config(h).get("model") or {}
        cache = {}
        try:
            cache = json.loads(
                (h / "provider_models_cache.json").read_text(encoding="utf-8")
            )
        except Exception:
            pass
        labels = {"mistral": "Mistral AI"}
        try:
            catalog_rows = (
                rt.catalog() if rt.info()["available"] else []
            ) or FALLBACK_CATALOG
            for row in catalog_rows:
                labels[str(row.get("slug") or "").lower()] = row.get(
                    "label"
                ) or row.get("slug")
        except Exception:
            pass

        rows, seen = {}, set()

        def add(provider, base_url, ready, why):
            key = f'custom:{base_url.rstrip("/")}' if base_url else provider
            if not key or key in seen:
                return
            seen.add(key)
            models = len((cache.get(key) or {}).get("models") or [])
            label = labels.get(provider) or provider or "Custom endpoint"
            if base_url:
                host = base_url.split("//")[-1].split("/")[0]
                label = (
                    f"{label} · {host}" if provider and provider != "custom" else host
                )
            rows[key] = {
                "key": key,
                "provider": provider,
                "base_url": base_url,
                "label": label,
                "models": models,
                "ready": bool(ready or models),
                "why": why,
            }

        # 1. whatever this profile is set to use right now
        add(
            str(cfg.get("provider") or "").lower(),
            str(cfg.get("base_url") or ""),
            True,
            "this profile",
        )
        # 2. anything with a populated cache — proof a credential worked
        for key, entry in cache.items():
            if not (entry or {}).get("models"):
                continue
            if key.startswith("custom:"):
                add("custom", key[len("custom:") :], True, "reachable")
            else:
                add(key.lower(), "", True, "reachable")
        # 3. anything holding an API key, even if never listed
        try:
            from companion_gateway import _env_values

            values = _env_values(h)
            check_rows = (
                rt.catalog() if rt.info()["available"] else []
            ) or FALLBACK_CATALOG
            for row in check_rows:
                if any(
                    bool(values.get(k) or os.environ.get(k))
                    for k in row.get("api_key_env_vars", [])
                ):
                    add(str(row.get("slug") or "").lower(), "", True, "key configured")
        except Exception:
            pass

        order = sorted(
            rows.values(),
            key=lambda r: (
                r["why"] != "this profile",
                -r["models"],
                r["label"].lower(),
            ),
        )
        return {
            "providers": order,
            "profile": {
                "provider": str(cfg.get("provider") or ""),
                "base_url": str(cfg.get("base_url") or ""),
                "model": str(cfg.get("default") or ""),
            },
        }

    @app.post("/api/environment")
    def save_environment(payload: dict):
        rt, p, h = context()
        allowed = {"model", "fallbacks", "tiers", "timezone"}
        if set(payload) - allowed:
            raise ValueError("Unknown environment setting")

        def entry(row, primary=False):
            if not isinstance(row, dict) or set(row) - {
                "model",
                "provider",
                "base_url",
            }:
                raise ValueError("Invalid model entry")
            out = {k: text(v, k, 500, empty=True) for k, v in row.items()}
            if out.get("base_url"):
                from urllib.parse import urlsplit

                url = urlsplit(out["base_url"])
                if (
                    url.scheme not in ("http", "https")
                    or not url.hostname
                    or url.username
                    or url.password
                ):
                    raise ValueError(
                        "Use an HTTP(S) provider URL without embedded credentials"
                    )
            if not out.get("model"):
                raise ValueError("Model name is required")
            if primary:
                out["default"] = out.pop("model")
            return out

        model = entry(payload["model"], True) if "model" in payload else None
        chain = payload.get("fallbacks")
        if chain is not None:
            if not isinstance(chain, list) or len(chain) > 8:
                raise ValueError("Choose up to eight ordered fallbacks")
            chain = [entry(row) for row in chain]
        c = cc.load(h)
        if "tiers" in payload:
            c.models = payload["tiers"]
            c.__post_init__()
        timezone = payload.get("timezone")
        if timezone is not None:
            from zoneinfo import ZoneInfo

            ZoneInfo(text(timezone, "timezone", 100))

        def mutate(cfg):
            if model is not None:
                old = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
                cfg["model"] = {**old, **model}
                if "base_url" not in model:
                    cfg["model"].pop("base_url", None)
            if chain is not None:
                cfg["fallback_providers"] = chain
            if timezone is not None:
                cfg["timezone"] = timezone

        save_config(h, mutate)
        if "tiers" in payload:
            c.save()
        return {
            "saved": True,
            "note": "Use Apply job models to update existing job pins; restart the gateway to reload persistent workers.",
        }

    @app.post("/api/credentials")
    def credential(payload: dict):
        rt, p, h = context()
        key = text(payload.get("name"), "credential name", 100)
        value = text(payload.get("value"), "credential value", 10000, empty=True)
        rows = rt.catalog() or FALLBACK_CATALOG
        allowed = {v for row in rows for v in row.get("api_key_env_vars", [])} | {
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_ALLOWED_USERS",
            "DISCORD_BOT_TOKEN",
            "DISCORD_ALLOWED_USERS",
        }
        if key not in allowed:
            raise ValueError(
                "Choose a credential from the provider or messaging catalog"
            )
        path = h / ".env"
        with cp.file_lock(h / ".companion-env.lock"):
            lines = (
                path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            )
            lines = [
                line
                for line in lines
                if not re.match(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=", line)
            ]
            if value:
                lines.append(key + "=" + json.dumps(value))
            cp.atomic_write(path, "\n".join(lines) + "\n")
            if os.name != "nt":
                path.chmod(0o600)
        return {"saved": key, "configured": bool(value)}

    @app.post("/api/models/probe")
    def probe(payload: dict):
        """Probe exactly one selected route without tools, history, or failover."""
        if set(payload) - {"model", "provider", "base_url"}:
            raise ValueError("Unknown model probe setting")
        rt, profile, home = context()
        saved = config(home).get("model") or {}
        if not isinstance(saved, dict):
            saved = {"default": saved}
        model = text(payload.get("model") or saved.get("default") or "", "model", 300)
        provider = text(
            payload.get("provider") or saved.get("provider") or "",
            "provider",
            100,
            empty=True,
        )
        saved_url = (
            saved.get("base_url", "") if provider == saved.get("provider", "") else ""
        )
        base_url = text(payload.get("base_url", saved_url), "base_url", 500, empty=True)
        if base_url:
            from urllib.parse import urlsplit

            url = urlsplit(base_url)
            if (
                url.scheme not in ("http", "https")
                or not url.hostname
                or url.username
                or url.password
            ):
                raise ValueError(
                    "Use an HTTP(S) provider URL without embedded credentials"
                )
        if not provider and not base_url:
            raise ValueError("Choose a provider or an explicit model endpoint to test")
        route = {
            "model": model,
            "provider": provider,
            "base_url": base_url,
            "reasoning_effort": "",
            "direct": bool(base_url),
        }
        if provider == saved.get("provider", "") and base_url.rstrip("/") == str(
            saved.get("base_url") or ""
        ).rstrip("/"):
            for key in ("api_key", "api_key_env", "key_env", "api_mode"):
                if saved.get(key):
                    route[key] = saved[key]

        def action(rt, p, h, report):
            from companion_worker_model import complete

            report(
                "Making one small request to the selected model; fallback is disabled"
            )
            reply = complete(
                cc.load(h),
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with exactly: CONNECTION_OK.",
                        }
                    ],
                    "max_tokens": 64,
                    "temperature": 0,
                },
                route,
                allow_remote=True,
                timeout=60,
                what="Model probe",
                allow_fallback=False,
                require_thinking=False,
            )
            return {
                "response": hr.redact(reply.get("content", ""))[-2000:],
                "tested_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "model_requested": model,
                "provider_requested": provider,
                "base_url": base_url,
                "note": "Only the selected model was tested. No fallback or companion context was used.",
            }

        return op("Test model response", action)

    @app.post("/api/jobs/apply-models")
    def apply_models():
        def action(rt, p, h, report):
            from kit.cli.models import apply_job_models

            c = cc.load(h)
            return apply_job_models(c, run=lambda args: rt.run(args, home=h))

        return op("Apply job models", action)

    @app.get("/api/jobs")
    def jobs():
        from kit.cli.common import _read_jobs
        from kit.cli.common import load_manifest
        import companion_render as cr

        rt, p, h = context()
        # The settings page edits these jobs in place, so it needs the whole
        # picture per job: which model answers it, how hard it is told to think,
        # and what went wrong the last time it ran.
        fields = (
            "id",
            "name",
            "schedule",
            "enabled",
            "no_agent",
            "model",
            "provider",
            "base_url",
            "reasoning_effort",
            "last_status",
            "last_error",
            "last_run_at",
            "next_run_at",
            "script",
            "deliver",
            "skills",
        )
        companion = cc.load(h)
        specs = {
            cr.render(spec["name"], {"AGENT": companion.agent}): spec
            for spec in load_manifest(companion)["jobs"]
        }
        rows = []
        for row in _read_jobs(h / "cron/jobs.json")["jobs"]:
            out = {k: row.get(k) for k in fields}
            spec = specs.get(row.get("name"))
            if spec:
                key = spec.get("key", "")
                advice = CONTINUITY_RECOMMENDATIONS.get(key)
                out.update(
                    companion_job=True,
                    job_key=key,
                    tier=spec.get("tier"),
                    expected_no_agent=bool(spec.get("no_agent")),
                    sensitivity=spec.get("sensitivity", "routine"),
                    sends=spec.get("sends", ""),
                )
                if advice:
                    out["recommendation"] = {
                        "model_role": advice[0],
                        "reasoning_effort": advice[1],
                        "why": advice[2],
                    }
                script_name = str(row.get("script") or "")
                out["legacy_worker"] = bool(
                    row.get("no_agent")
                    and not spec.get("no_agent")
                    and script_name.startswith("companion-local-")
                )
            # Two spellings of the same field exist in the wild.
            out["provider"] = row.get("provider") or row.get("model_provider")
            out["model_provider"] = out["provider"]
            prompt = row.get("prompt") or ""
            out["prompt"] = prompt
            # There is no per-job token budget in Hermes. Prompt size is the
            # honest stand-in: it is what this job actually sends every run.
            out["prompt_chars"] = len(prompt)
            out["last_error"] = (
                hr.redact(str(row.get("last_error") or ""))[:600] or None
            )
            rows.append(out)
        # A pre-read script runs before the agent turn and calls a model of its
        # own, resolved from the companion's model tiers rather than from the
        # job row. So one job makes two model calls with two different settings,
        # and this page only ever showed one of them -- changing a job's model
        # here left the call that actually writes her presence untouched.
        preread = None
        try:
            import companion_worker_model as worker

            preread = worker.resolve(companion, "loops")
        except Exception:
            preread = None
        # Which of the three a job belongs to, so the list can say plainly what
        # ships with Tamanitomo, what this person added, and what is not
        # companion work at all. A port scanner running under her name is not
        # hidden by calling it a job like any other.
        for row in rows:
            if row.get("companion_job"):
                row["origin"] = "shipped"
            elif str(row.get("name") or "").startswith(companion.agent + " "):
                row["origin"] = "yours"
            else:
                row["origin"] = "other"
        for row in rows:
            # A job the manifest does not know is still a job that runs. Say what
            # can be said -- whether it calls a model -- rather than asserting
            # that nothing private is in a prompt nobody here has read.
            if "sensitivity" not in row:
                row["sensitivity"] = "none" if row.get("no_agent") else "routine"
                row["sends"] = (
                    ""
                    if row.get("no_agent")
                    else "Not one of the companion\u2019s own jobs. What it sends depends on "
                    "the prompt it was given; read it below."
                )
            row.setdefault("sends", "")
            script = str(row.get("script") or "")
            if (
                preread
                and script.startswith("companion-local-")
                and not row.get("no_agent")
            ):
                row["second_call"] = {
                    "why": "Its pre-read writes her presence before the agent turn.",
                    "reasoning_reported": REASONING_REPORTED.get(
                        preread["provider"], None
                    ),
                    "setting": "models.loops",
                    "provider": preread["provider"],
                    "model": preread["model"],
                    "reasoning_effort": preread["reasoning_effort"],
                }
            # A provider on a job that never calls one is noise that reads as data leaving.
            row["provider_matters"] = row["sensitivity"] != "none"
        groups = [
            {
                "key": k,
                **v,
                "jobs": [r["id"] for r in rows if r.get("sensitivity") == k],
            }
            for k, v in sorted(SENSITIVITY.items(), key=lambda kv: kv[1]["order"])
        ]
        origins = [
            {
                "key": "shipped",
                "label": "Ships with Tamanitomo",
                "blurb": "The companion\u2019s own machinery. Every install has these.",
            },
            {
                "key": "yours",
                "label": "Yours",
                "blurb": "Jobs you added for this companion. Tamanitomo does not ship or update them.",
            },
            {
                "key": "other",
                "label": "Not companion work",
                "blurb": "Jobs that run in this profile but have nothing to do with her. "
                "They use her identity and her tools, and count against her usage.",
            },
        ]
        for group in origins:
            group["jobs"] = [r["id"] for r in rows if r.get("origin") == group["key"]]
        return {
            "timezone": companion.timezone,
            "jobs": rows,
            "usage": hr.job_usage(companion, rows),
            "sensitivity": groups,
            "origins": origins,
            "local_endpoint": bool(
                (companion.models or {}).get("loops", {}).get("base_url")
            ),
        }

    # `hermes cron edit` can set a job's model, provider and reasoning effort, but
    # it has no flag for base_url — and scheduler.py passes a stored base_url as
    # explicit_base_url, overriding everything else. A job pinned to a dead local
    # server therefore cannot be rescued from the CLI at all. This writes that one
    # field, so the workspace can move a job between providers in one action.
    def _write_job_base_url(home, ident, value):
        import tempfile

        path = home / "cron/jobs.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        found = False
        for row in data.get("jobs", []):
            if row.get("id") == ident:
                row["base_url"] = value or None
                found = True
        if not found:
            raise ValueError("Job not found in this profile")
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".jobs-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def _job_routing_args(payload):
        """The model/provider/reasoning arguments shared by one edit and a bulk move."""
        args = []
        if payload.get("model") is not None:
            args += ["--model", text(payload.get("model"), "model", 200, empty=True)]
        if payload.get("provider") is not None:
            args += [
                "--provider",
                text(payload.get("provider"), "provider", 120, empty=True),
            ]
        effort = payload.get("reasoning_effort")
        if effort is not None:
            if effort not in (
                "",
                "none",
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
                "ultra",
            ):
                raise ValueError("Unknown reasoning effort")
            args += ["--reasoning-effort", effort]
        return args

    @app.post("/api/jobs/{ident}/{action}")
    def job_action(ident: str, action: str, payload: dict):
        if action not in ("pause", "resume", "run", "edit"):
            raise ValueError("Unknown job action")
        from kit.cli.common import _read_jobs

        rt, p, h = context()
        row = next(
            (
                j
                for j in _read_jobs(h / "cron/jobs.json")["jobs"]
                if j.get("id") == ident
            ),
            None,
        )
        if not row:
            raise ValueError("Job not found in this profile")
        if row.get("no_agent") and action == "pause":
            raise ValueError(
                "Model-free continuity and maintenance jobs remain active. Pause the model-backed routine instead."
            )
        args = ["cron", action, ident]
        if action == "edit":
            # Every field is optional; only what the page actually changed is
            # passed through, so an edit to one never blanks the others.
            if payload.get("schedule") is not None:
                args += ["--schedule", text(payload.get("schedule"), "schedule", 120)]
            if payload.get("name") is not None:
                args += ["--name", text(payload.get("name"), "name", 200)]
            if payload.get("prompt") is not None:
                # A job prompt is a paragraph, so newlines are allowed here
                # where text() would reject them as control characters.
                prompt = payload.get("prompt")
                if (
                    not isinstance(prompt, str)
                    or len(prompt) > 20000
                    or not prompt.strip()
                ):
                    raise ValueError("prompt must be text of at most 20000 characters")
                args += ["--prompt", prompt.strip()]
            args += _job_routing_args(payload)
            # base_url has no CLI flag, so it is written straight to the store.
            if payload.get("base_url") is not None:
                url = text(payload.get("base_url"), "base_url", 500, empty=True)
                if url and not url.startswith(("http://", "https://")):
                    raise ValueError("base_url must start with http:// or https://")
                _write_job_base_url(h, ident, url)
                if len(args) == 3:
                    return op(
                        "Job edit", lambda rt, p, h, report: {"note": "Endpoint saved."}
                    )
            if len(args) == 3:
                raise ValueError("Nothing to change on this job")
        return op(
            "Job " + action,
            lambda rt, p, h, report: {
                "output": hr.redact(rt.run(args, home=h).stdout),
                "note": (
                    "Run now queues a job for the next scheduler tick; the owning gateway must be running."
                    if action == "run"
                    else "Saved by Hermes."
                ),
            },
        )

    @app.post("/api/jobs/routing")
    def job_routing(payload: dict):
        """Move every model-backed job in this profile onto one provider.

        Swapping providers used to mean editing each job by hand and then
        discovering that base_url had stayed behind, still pointing at whatever
        served the last model. One action sets all three axes together."""
        from kit.cli.common import _read_jobs

        rt, p, h = context()
        url = payload.get("base_url")
        if url is not None:
            url = text(url, "base_url", 500, empty=True)
            if url and not url.startswith(("http://", "https://")):
                raise ValueError("base_url must start with http:// or https://")
        args = _job_routing_args(payload)
        only = payload.get("jobs")
        if only is not None and not isinstance(only, list):
            raise ValueError("jobs must be a list of job ids")
        rows = [
            j
            for j in _read_jobs(h / "cron/jobs.json")["jobs"]
            if not j.get("no_agent") and (only is None or j.get("id") in only)
        ]
        if not rows:
            raise ValueError("No model-backed jobs to move in this profile")
        if not args and url is None:
            raise ValueError("Nothing to change")

        def action(rt, p, h, report):
            moved, failed = [], []
            for row in rows:
                ident = row.get("id")
                try:
                    if url is not None:
                        _write_job_base_url(h, ident, url)
                    if args:
                        result = rt.run(
                            ["cron", "edit", ident, *args], home=h, check=False
                        )
                        if result.returncode:
                            failed.append(
                                f"{row.get('name') or ident}: "
                                f"{hr.redact(result.stderr or result.stdout)[-200:]}"
                            )
                            continue
                    moved.append(row.get("name") or ident)
                except Exception as exc:
                    failed.append(f"{row.get('name') or ident}: {exc}")
            note = f"{len(moved)} job(s) moved."
            if failed:
                note += f" {len(failed)} could not be changed."
            return {"moved": moved, "failed": failed, "note": note}

        return op("Move jobs to a provider", action)

    @app.post("/api/jobs/history")
    def job_history():
        return op(
            "Recent scheduled runs",
            lambda rt, p, h, report: {
                "output": hr.redact(rt.run(["cron", "runs"], home=h).stdout)
            },
        )

    @app.post("/api/maintenance/{action}")
    def maintenance(action: str):
        if action not in ("doctor", "repair", "activate", "pause", "update", "version"):
            raise ValueError("Unknown maintenance action")

        def run(rt, p, h, report):
            if action in ("update", "version"):
                args = ["--version"] if action == "version" else ["update", "--yes"]
                result = rt.run(args, home=rt.root, timeout=1800, check=False)
            else:
                args = {
                    "doctor": ["doctor"],
                    "repair": ["repair"],
                    "activate": ["schedule", "active"],
                    "pause": ["schedule", "paused"],
                }[action]
                result = rt.run(
                    ["--home", str(h), *args],
                    home=h,
                    kit=True,
                    timeout=600,
                    check=False,
                )
            if result.returncode:
                raise ValueError(hr.redact(result.stderr or result.stdout)[-12000:])
            return {"output": hr.redact(result.stdout)[-20000:]}

        return op(action.title(), run)

    @app.get("/api/gateway")
    def gateway_status():
        import companion_gateway as gateway

        c = load()
        return {**gateway.status(c), "preflight": gateway.preflight(c)}

    @app.post("/api/gateway/{action}")
    def gateway_action(action: str, payload: dict):
        if action not in (
            "status",
            "install",
            "uninstall",
            "start",
            "stop",
            "restart",
            "shared",
            "dedicated",
            "restart-root",
        ):
            raise ValueError("Unknown gateway action")

        def run(rt, p, h, report):
            import companion_gateway as gateway

            c = cc.load(h)
            if action in ("shared", "dedicated"):
                return gateway.configure(c, action)
            state = gateway.status(c)
            owner = Path(state["owner_home"])
            if action == "uninstall":
                if state["mode"] == "shared":
                    raise ValueError(
                        "Select the root profile to uninstall its shared service."
                    )
                return {
                    "output": hr.redact(rt.run(["gateway", "uninstall"], home=h).stdout)
                }
            if action == "restart-root":
                if not payload.get("affects_all_profiles"):
                    raise ValueError(
                        "Confirm the root restart, which affects every shared profile."
                    )
                args = ["gateway", "restart"]
                if any(u["scope"] == "system" for u in gateway.service_units(rt.root)):
                    args += ["--system"]
                result = rt.run(args, home=rt.root, timeout=180)
                plan = gateway.saved(c)
                if plan:
                    plan["restart_required"] = False
                    cp.atomic_write(h / gateway.PLAN, json.dumps(plan, indent=2) + "\n")
                return {"output": hr.redact(result.stdout)}
            if action == "stop":
                if state["mode"] == "shared" and not payload.get(
                    "affects_all_profiles"
                ):
                    raise ValueError(
                        "Stopping the shared gateway affects all its profiles. Confirm this in the app."
                    )
                return {
                    "output": hr.redact(rt.run(["gateway", "stop"], home=owner).stdout)
                }
            args = ["--home", str(h), "gateway", "--action", action]
            if payload.get("root_restarted"):
                args += ["--root-restarted"]
            return {
                "output": hr.redact(rt.run(args, home=h, kit=True, timeout=180).stdout)
            }

        return op("Gateway " + action, run)

    @app.get("/api/sessions")
    def session_list(before: str | None = None, limit: int = 100):
        return hr.sessions_page(load(), limit, before)

    def _attach_media(c, rows):
        """Resolve the pictures, audio and video a message refers to."""
        from .content import catalog

        references = []
        for row in rows:
            content = row.get("content") or ""
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            row["content"] = content
            matches = re.findall(r"!\[[^\]]*\]\(([^)]+)\)|MEDIA:\s*([^\s]+)", content)
            references.append(
                {value.strip("\"'") for pair in matches for value in pair if value}
            )
        paths = set().union(*references) if references else set()
        media = catalog(c, reference_paths=paths)["items"] if paths else []
        for row, paths in zip(rows, references):
            row["attachments"] = []
            for item in media:
                if item["kind"] not in ("image", "audio", "video"):
                    continue
                copy = next(
                    (
                        copy
                        for copy in item.get("copies", [item])
                        if copy["path"] in paths or str(c.data / copy["path"]) in paths
                    ),
                    None,
                )
                if copy:
                    row["attachments"].append({**item, **copy})
                if len(row["attachments"]) == 12:
                    break
        return rows

    app.state.attach_media = _attach_media

    @app.get("/api/sessions/{ident}")
    def session_messages(ident: str, before: str | None = None, limit: int = 200):
        c = load()
        page = hr.messages_page(c, ident, limit, before)
        return {
            **page,
            "messages": _attach_media(c, page["messages"]),
            "session": ident,
        }

    @app.get("/api/feed")
    def conversation_feed(before: str | None = None, limit: int = 60):
        """One conversation, across every channel it happened on."""
        c = load()
        page = hr.feed_page(c, limit, before)
        return {
            **page,
            "messages": _attach_media(c, page["messages"]),
            "session": hr.latest_session(c),
            "agent": c.agent,
        }

    @app.get("/api/activity")
    def activity():
        from kit.cli.common import _read_jobs
        from .content import catalog

        c = load()
        rows = []
        for job in _read_jobs(c.home / "cron/jobs.json")["jobs"]:
            rows.append(
                {
                    "kind": "job",
                    "title": job.get("name", "Scheduled job"),
                    "status": job.get("last_status") or "Not run yet",
                    "at": job.get("last_run_at"),
                    "detail": hr.redact(str(job.get("last_error") or ""))[:1200],
                    "next": job.get("next_run_at"),
                    "enabled": bool(job.get("enabled")),
                    "id": job.get("id"),
                }
            )
        for item in catalog(c)["items"][:60]:
            rows.append(
                {
                    "kind": "content",
                    "title": item["title"],
                    "status": "Saved",
                    "at": item["at"],
                    "media": item,
                }
            )

        def event_time(row):
            try:
                return dt.datetime.fromisoformat(
                    str(row.get("at")).replace("Z", "+00:00")
                ).timestamp()
            except (ValueError, TypeError):
                return 0

        return {"events": sorted(rows, key=event_time, reverse=True)[:100]}

    @app.post("/api/chat")
    def chat(payload: dict, request: Request):
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 30000:
            raise ValueError("Write a message (up to 30,000 characters)")
        session = payload.get("session")
        c = load()
        if session:
            hr.resumable_session(c, text(session, "session", 200))

        def run(rt, p, h, report):
            report("Waiting for " + c.agent)
            args = ["chat", "--quiet", "--oneshot", "-q", message]
            if session:
                args += ["--resume", session]
            # No auto-approval of arbitrary existing hooks. Setup has its own
            # explicit, reviewable hook approval action.
            before = {r["id"] for r in hr.sessions(c)}
            r = rt.chat(args, home=h, report=report)
            after = hr.sessions(c)
            new = getattr(r, "session", None) or next(
                (
                    row["id"]
                    for row in after
                    if row["id"] not in before
                    and row.get("source") in ("cli", "desktop", "tui")
                ),
                session,
            )
            # Hermes files this as a cli session; the feed should still be able
            # to say it happened here rather than at a terminal.
            hr.note_workspace_session(c, new)
            return {
                "response": ANSI_TEXT(r.stdout),
                "session": new,
                "messages": hr.messages(c, new) if new else [],
                "note": "Hermes owns this conversation. All channels share this profile’s identity, memory, and lived state.",
            }

        operation = op("Chat with " + c.agent, run)
        if "text/event-stream" not in request.headers.get("accept", ""):
            return operation

        from fastapi.responses import StreamingResponse

        async def events():
            import asyncio

            def event(kind, payload):
                return f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            # The operation survives a disconnected browser. Reconnection reads history
            # or operation status; it must never silently submit the user's turn twice.
            yield event("operation", {"id": operation["id"]})
            offset = 0
            while True:
                row = operations.get(operation["id"])
                streamed = row.get("stream_text", "")
                if len(streamed) > offset:
                    yield event("delta", {"text": streamed[offset:]})
                    offset = len(streamed)
                if row["status"] == "complete":
                    result = row.get("result", {})
                    if result.get("session"):
                        yield event("session", {"id": result["session"]})
                    yield event("final", result)
                    return
                if row["status"] != "running":
                    yield event(
                        "error", {"error": row.get("error", "Chat could not complete.")}
                    )
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.05)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/hooks")
    def hooks():
        rt, p, h = context()
        # Present exactly what will be approved, including existing user hooks.
        hooks = config(h).get("hooks", {})
        return {
            "hooks": hooks,
            "digest": hashlib.sha256(
                json.dumps(hooks, sort_keys=True).encode()
            ).hexdigest(),
            "note": "Approval executes configured shell hooks on subsequent Hermes turns.",
        }

    @app.post("/api/hooks/approve")
    def approve(payload: dict):
        rt, p, h = context()
        existing = config(h).get("hooks", {})
        digest = hashlib.sha256(
            json.dumps(existing, sort_keys=True).encode()
        ).hexdigest()
        if payload.get("digest") != digest:
            raise ValueError("Reload and review the current hooks before approving")
        # Hermes's native hook verifier writes approval state during chat. The
        # supplied message makes that first conversation an explicit user action.
        message = text(payload.get("message", "Hello."), "first message", 1000)
        return op(
            "Approve hooks and say hello",
            lambda rt, p, h, report: {
                "response": ANSI_TEXT(
                    rt.run(
                        [
                            "chat",
                            "--quiet",
                            "--oneshot",
                            "--accept-hooks",
                            "-q",
                            message,
                        ],
                        home=h,
                        timeout=600,
                    ).stdout
                )
            },
        )

    @app.get("/api/vault")
    def vault_list(path: str = ""):
        from . import vault

        return vault.listing(load(), path)

    @app.get("/api/vault/file")
    def vault_read(path: str):
        from . import vault

        return vault.read(load(), path)

    @app.get("/api/vault/search")
    def vault_search(q: str):
        from . import vault

        return vault.search(load(), q)

    @app.post("/api/vault/trash")
    def vault_trash(payload: dict):
        from . import vault

        try:
            return vault.trash(load(), payload.get("path"), payload.get("revision"))
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/vault/trash")
    def vault_trash_list():
        from . import vault

        return vault.trash_list(load())

    @app.post("/api/vault/restore")
    def vault_restore(payload: dict):
        from . import vault

        try:
            return vault.restore(load(), payload.get("id"))
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/vault/download")
    def vault_download(path: str):
        from . import vault
        from fastapi.responses import FileResponse

        target = vault.resolve(load(), path)
        if not target.is_file():
            raise ValueError("File not found")
        return FileResponse(
            target, filename=target.name, media_type="application/octet-stream"
        )

    @app.get("/api/vault/export")
    def vault_export():
        from . import vault
        from fastapi.responses import FileResponse
        from starlette.background import BackgroundTask
        import zipfile

        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        target = Path(handle.name)
        handle.close()
        try:
            total = 0
            with zipfile.ZipFile(
                target, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for path, relative in vault.files(load()):
                    total += path.stat().st_size
                    if total > 2_000_000_000:
                        raise ValueError(
                            "Use the vault folder directly for exports larger than 2 GB"
                        )
                    archive.write(path, relative)
            return FileResponse(
                target,
                filename="companion-vault.zip",
                media_type="application/zip",
                background=BackgroundTask(target.unlink),
            )
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.put("/api/vault/file")
    def vault_write(payload: dict):
        from . import vault

        try:
            return vault.write(
                load(),
                payload.get("path"),
                payload.get("text"),
                payload.get("revision"),
            )
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/feelings")
    def feelings_read():
        import companion_feelings as feelings
        import companion_integrity
        import companion_intimacy

        c = load()
        integrity = companion_integrity.verify_integrity(c)
        intimacy = companion_intimacy.compute(c)
        return {
            **feelings.settings(c),
            "state": feelings.compute(c),
            "integrity_lockout": False,
            "integrity_warning": None,
            "intimacy": intimacy,
        }

    @app.put("/api/feelings/settings")
    def feelings_settings(payload: dict):
        import companion_feelings as feelings

        try:
            return feelings.save_settings(
                load(), payload.get("settings"), payload.get("revision")
            )
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/feelings/experiences")
    def feelings_history(limit: int = 30, before: str | None = None):
        import companion_feelings as feelings
        from .runtime import _page_cursor, _encode_cursor

        if not 1 <= limit <= 100:
            raise ValueError("Experience page size must be 1–100")
        cursor = _page_cursor(before)
        if cursor and not isinstance(cursor[1], str):
            raise ValueError("Invalid experience cursor")
        now = dt.datetime.now(dt.timezone.utc)
        rows = [
            r for r in feelings.experiences(load()) if feelings._stamp(r["at"]) <= now
        ]
        key = lambda row: (feelings._stamp(row["at"]).timestamp(), row["id"])
        rows.sort(key=key, reverse=True)
        total = len(rows)
        if cursor:
            rows = [r for r in rows if key(r) < tuple(cursor)]
        more = len(rows) > limit
        rows = rows[:limit]
        return {
            "experiences": rows,
            "total": total,
            "next_cursor": _encode_cursor(*key(rows[-1])) if more else None,
        }

    @app.post("/api/feelings/experiences")
    def feelings_record(payload: dict):
        import companion_feelings as feelings

        try:
            return feelings.record(load(), payload)
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/relationship")
    def relationship():
        import companion_notes as notes
        import companion_integrity
        import companion_intimacy

        c = load()
        rows = notes.moments(c, None)
        active = [r for r in rows if r.get("status") == "active"]
        kinds = {r["moment"] for r in active}
        integrity = companion_integrity.verify_integrity(c)
        intimacy = companion_intimacy.compute(c)
        return {
            "bars": (__import__("companion_bars").compute(c) if c.bars else None),
            "moments": rows,
            "kinds": notes.LABELS,
            "boundary": c.boundary,
            "settings": {
                k: getattr(c, k)
                for k in (
                    "relationship_progression",
                    "relationship_pace",
                    "peer_interaction",
                    "bars",
                    "explicit",
                )
            },
            "milestones": [
                {"label": label, "earned": kind in kinds}
                for kind, label in [
                    ("first", "A first to remember"),
                    ("joke", "An inside joke"),
                    ("ritual", "A shared ritual"),
                    ("nickname", "A name between you"),
                    ("milestone", "A meaningful milestone"),
                ]
            ],
            "intimacy": intimacy,
            "pronoun_set": c.pronoun_set,
            "integrity_lockout": False,
            "integrity_warning": None,
            "note": "Milestones reflect saved shared history. Time away never removes progress.",
        }

    @app.post("/api/relationship")
    def relationship_add(payload: dict):
        import companion_notes as notes

        return notes.add_moment(load(), payload, dt.datetime.now(dt.timezone.utc))

    @app.post("/api/relationship/{ident}/retire")
    def relationship_retire(ident: str):
        import companion_notes as notes

        return notes.retire_moment(
            load(),
            ident,
            "Retired by the user in the app",
            dt.datetime.now(dt.timezone.utc),
        )


def ANSI_TEXT(value):
    return hr.ANSI.sub("", value).strip()
