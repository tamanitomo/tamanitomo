"""Ordered inference fallbacks without implicit providers or repeated side effects.

Only configured routes participate. Temporary transport failures advance to the
next route once; invalid requests and credentials remain visible for correction.
Configured local models run last, without inventing a model or a cloud account.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from urllib.error import URLError
from urllib.parse import urlsplit

TRANSIENT_STATUSES = frozenset((429, 500, 502, 503, 504))
LOCAL_ENDPOINTS = {
    "ollama": "http://127.0.0.1:11434/v1",
    "lmstudio": "http://127.0.0.1:1234/v1",
    "lm-studio": "http://127.0.0.1:1234/v1",
    "lm_studio": "http://127.0.0.1:1234/v1",
}
PROVIDER_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "custom": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "grok": "XAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def redact(message):
    text = str(message)
    text = re.sub(r"(?i)(bearer\s+)[^\s,;\'\"]+", r"\1[redacted]", text)
    text = re.sub(
        r"(?i)((?:api[_ -]?key|token|secret|password|authorization)[\"']?\s*[=:]\s*[\"']?)[^\s,;\"'}]+",
        r"\1[redacted]",
        text,
    )
    text = re.sub(r"\b(?:sk-|sk-or-|ghp_|gho_)[A-Za-z0-9_-]{12,}", "[redacted]", text)
    return text[:1200]


class ProviderFailure(ValueError):
    """Safe error metadata that survives the isolated Hermes process boundary."""

    def __init__(self, message, status_code=None, transient=None):
        super().__init__(redact(message))
        try:
            self.status_code = int(status_code) if status_code is not None else None
        except (ValueError, TypeError):
            self.status_code = None
        self.transient = (
            self.status_code in TRANSIENT_STATUSES
            if transient is None
            else bool(transient)
        )


def status_code(error):
    value = getattr(error, "status_code", None) or getattr(error, "code", None)
    if value is None:
        value = getattr(getattr(error, "response", None), "status_code", None)
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def is_transient(error):
    if isinstance(error, ProviderFailure):
        return error.transient
    code = status_code(error)
    if code is not None:
        return code in TRANSIENT_STATUSES
    if isinstance(
        error, (TimeoutError, ConnectionError, subprocess.TimeoutExpired, URLError)
    ):
        return True
    # Hermes may use an optional provider SDK that is absent in the app's Python.
    return type(error).__name__ in (
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "ConnectTimeout",
        "ReadTimeout",
        "ConnectError",
    )


def cascade(routes, attempt, on_fallback=None):
    """Try a configured route once, advancing only after transient failure."""
    routes = list(routes)
    if not routes:
        raise ValueError("No inference route is configured")
    for index, route in enumerate(routes):
        try:
            return attempt(route)
        except Exception as exc:
            if not is_transient(exc) or index + 1 == len(routes):
                raise
            if on_fallback is not None:
                on_fallback(route, routes[index + 1], exc)


def read_config(c):
    import yaml

    path = Path(c.home) / "config.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Hermes configuration must be an object")
    return data


def normalize(route, default_provider=""):
    result = {
        key: str(route.get(key) or "").strip()
        for key in ("provider", "model", "base_url", "reasoning_effort", "api_key_env")
    }
    result["provider"] = result["provider"] or default_provider
    result["api_key_env"] = (
        result["api_key_env"] or str(route.get("key_env") or "").strip()
    )
    if not result["base_url"]:
        result["base_url"] = LOCAL_ENDPOINTS.get(result["provider"].lower(), "")
    result["direct"] = bool(result["base_url"])
    # Native Hermes configurations may own credentials or API adapters that the
    # public companion model editor does not accept. Preserve them internally.
    for field in ("api_key", "api_mode"):
        if isinstance(route.get(field), str) and route[field]:
            result[field] = route[field]
    return result


def is_local(route):
    return urlsplit(route.get("base_url") or "").hostname in (
        "127.0.0.1",
        "localhost",
        "::1",
    )


def configured_routes(c, primary=None, tier="chat"):
    """Primary, configured secondary providers, then configured local endpoints.

    Native Hermes fallbacks are authoritative when that key exists, including an
    explicitly empty chain. The companion's saved chain is used otherwise.
    """
    config = read_config(c)
    default = config.get("model") if isinstance(config.get("model"), dict) else {}
    provider = str(default.get("provider") or "")
    if primary is None:
        chosen = dict((getattr(c, "models", None) or {}).get(tier) or {})
        same_provider = not chosen.get("provider") or chosen["provider"] == provider
        same_endpoint = not chosen.get("base_url") or chosen["base_url"].rstrip(
            "/"
        ) == str(default.get("base_url") or "").rstrip("/")
        native = (
            {
                key: default[key]
                for key in ("api_key", "api_mode", "api_key_env", "key_env")
                if key in default
            }
            if same_provider and same_endpoint
            else {}
        )
        primary = {
            **native,
            **chosen,
            "provider": chosen.get("provider") or provider,
            "model": chosen.get("model")
            or default.get("default")
            or default.get("model")
            or "",
            "base_url": chosen.get("base_url")
            or (default.get("base_url") if same_provider else "")
            or "",
        }
    first = normalize(primary, provider if not primary.get("base_url") else "")
    chain = (
        config.get("fallback_providers")
        if "fallback_providers" in config
        else (getattr(c, "models", None) or {}).get("fallbacks")
    ) or []
    if not isinstance(chain, list):
        raise ValueError("Configured inference fallbacks must be a list")
    candidates = []
    for row in chain[:8]:
        if not isinstance(row, dict) or not row.get("model"):
            raise ValueError("Each fallback needs a model")
        provider = row.get("provider") or (
            "custom" if row.get("base_url") else first["provider"]
        )
        candidates.append(normalize(row, provider))
    candidates.sort(key=is_local)
    routes, seen = [], set()
    for route in [first, *candidates]:
        identity = (route["provider"], route["model"], route["base_url"].rstrip("/"))
        if identity not in seen:
            seen.add(identity)
            routes.append(route)
    return routes


def credential(c, route, primary_env="", *, primary=False):
    """Resolve only this route's credential, from this profile or its root."""
    if route.get("api_key"):
        return str(route["api_key"]).strip()
    name = route.get("api_key_env") or primary_env
    # A distinct endpoint cannot inherit the primary provider's account. Named
    # providers retain their standard credential, and the explicitly selected
    # primary route may use its own provider default.
    if not name and (primary or not route.get("base_url")):
        name = PROVIDER_KEYS.get(route.get("provider", "").lower(), "")
    if not name:
        return ""
    if os.environ.get(name):
        return os.environ[name].strip()
    from companion_gateway import _env_values

    return str(
        _env_values(c.home).get(name) or _env_values(c.hermes_root).get(name) or ""
    ).strip()
