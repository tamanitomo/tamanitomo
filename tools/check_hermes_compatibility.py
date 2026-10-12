#!/usr/bin/env python3
"""Exercise the installed Hermes loader, routing and hooks in a disposable home.

No provider is called, no gateway is started and no message is delivered. The
probe uses real Hermes modules, synthetic credentials and generated kit hooks.
Run with --hermes-root CHECKOUT --python CHECKOUT/.venv/bin/python. A revision
mismatch fails until explicitly reviewed with --expected-revision NEW_COMMIT.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_REVISION = "bddd22be7c2e5f7630c3d90507e6e7280ff092e3"

# Also inherited by the genuine shell-hook subprocesses. Synthetic homes are the
# only writable location. Environment credentials are not inherited by the probe.
# The folder around the checkout is treated as real profile data (an install keeps
# hermes-agent inside ~/.hermes), except for the kit itself: CI checks Hermes out
# inside this repository, and without the exception the probe could not open its
# own script, so the workflow failed with exit 2 on every run. The runtime is the
# interpreter's own prefix: its parent was "/" for a system Python in /usr, which
# let every read through.
GUARD = r"""
import os, pathlib, sys
scratch = pathlib.Path(os.environ["TAMANITOMO_COMPAT_SCRATCH"]).resolve()
checkout = pathlib.Path(os.environ["TAMANITOMO_COMPAT_CHECKOUT"]).resolve()
kit = pathlib.Path(os.environ["TAMANITOMO_COMPAT_KIT"]).resolve()
runtime_roots = (pathlib.Path(sys.prefix).resolve(), pathlib.Path(sys.base_prefix).resolve())
def inside(path, root):
    try: return pathlib.Path(path).resolve().is_relative_to(root)
    except (TypeError, ValueError, OSError): return False
def guard(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"):
        with open(scratch / "network-attempted", "a") as stream: stream.write(event + "\n")
        raise PermissionError("Compatibility probe forbids network access")
    if event == "open" and not isinstance(args[0], int):
        path, mode, flags = args
        write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if write and not inside(path, scratch) and str(path) != os.devnull:
            raise PermissionError("Compatibility probe writes only to its disposable directory")
        resolved = pathlib.Path(path).resolve()
        if not inside(resolved, scratch):
            if inside(resolved, checkout.parent) and not any(inside(resolved, root) for root in (checkout, kit, *runtime_roots)):
                raise PermissionError("Real Hermes profile data is outside this probe")
            if resolved.name in (".env", "auth.json", "companion.json", ".netrc"):
                raise PermissionError("Real credentials are outside this probe")
    if event in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime") and not inside(args[0], scratch):
        raise PermissionError("Compatibility probe cannot modify external paths")
    if event in ("os.rename", "os.link") and not (inside(args[0], scratch) and inside(args[1], scratch)):
        raise PermissionError("Compatibility probe cannot modify external paths")
    if event == "os.symlink" and not inside(args[1], scratch):
        raise PermissionError("Compatibility probe cannot modify external paths")
sys.addaudithook(guard)
"""


def isolated_environment(scratch, checkout):
    """Keep runtime necessities, never the caller's account credentials/config."""
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "COMSPEC")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    home = scratch / "hermes" / "profiles" / "compatibility"
    env.update(
        HERMES_HOME=str(home),
        HERMES_CONFIG=str(home / "config.yaml"),
        HERMES_ENV=str(home / ".env"),
        HERMES_BUNDLED_PLUGINS=str(scratch / "empty-bundled-plugins"),
        HERMES_TIMEZONE="UTC",
        TAMANITOMO_COMPAT_SCRATCH=str(scratch),
        TAMANITOMO_COMPAT_CHECKOUT=str(checkout),
        TAMANITOMO_COMPAT_KIT=str(ROOT),
        PYTHONPATH=os.pathsep.join(
            (
                str(scratch / "guard"),
                str(checkout),
                str(ROOT),
                str(ROOT / "kit/scripts"),
            )
        ),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        XDG_CACHE_HOME=str(scratch / "cache"),
        XDG_CONFIG_HOME=str(scratch / "config"),
        TMPDIR=str(scratch),
        TEMP=str(scratch),
        TMP=str(scratch),
        COMPANION_MEMORY_READ_ONLY="1",
        COMPAT_BACKUP_KEY="synthetic-second-endpoint-key",
    )
    return env


def revision(checkout):
    return subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def require(condition, description):
    if not condition:
        raise RuntimeError(description)


def probe(scratch, checkout):
    import copy
    import yaml

    import companion_config as cc
    import companion_render as render
    import companion_routing as routing
    from kit.cli.scaffold import install_hook

    c = cc.Companion(
        agent="CompatibilityFixture",
        human="SyntheticOwner",
        profile="compatibility",
        hermes_root=scratch / "hermes",
        vault=scratch / "vault",
        timezone="UTC",
        context_mode="fixed",
        soul_in_vault=False,
    )
    require(
        c.home.resolve() == Path(os.environ["HERMES_HOME"]).resolve(),
        "Profile is not isolated",
    )
    c.home.mkdir(parents=True, exist_ok=True)
    c.vault.mkdir(parents=True)
    c.life.mkdir(parents=True, exist_ok=True)
    c.save()
    routes = [
        {
            "provider": "custom",
            "model": "backup",
            "base_url": "https://first.invalid/v1",
            "api_key": "synthetic-first-key",
        },
        {
            "provider": "custom",
            "model": "backup",
            "base_url": "https://second.invalid/v1",
            "api_key_env": "COMPAT_BACKUP_KEY",
        },
        {
            "provider": "ollama",
            "model": "final-local",
            "base_url": "http://127.0.0.1:19999/v1",
            "api_key": "synthetic-local-key",
        },
    ]
    cfg = {
        "model": {
            "provider": "custom",
            "default": "synthetic-primary",
            "base_url": "https://primary.invalid/v1",
            "api_key": "synthetic-primary-key",
            "context_length": 32768,
        },
        "fallback_providers": routes,
        "plugins": {"enabled": []},
        "compression": {"enabled": False},
    }
    (c.home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    routing.install(c)
    mapping = render.mapping_for(c, "warm", "none")
    c.soul.write_text(render.render_template("SOUL.md.tmpl", mapping), encoding="utf-8")
    install_hook(c, mapping, [])

    from hermes_constants import get_hermes_home
    from hermes_cli import plugins
    from hermes_cli.config import load_config
    from cron import scheduler
    from gateway import run_config_loaders

    require(
        get_hermes_home().resolve() == c.home.resolve(),
        "Hermes resolved a different home",
    )
    require(
        Path(scheduler.__file__).resolve().is_relative_to(checkout),
        "Imported a different Hermes checkout",
    )
    native_job_chain = scheduler._job_fallback_chain
    native_gateway_chain = run_config_loaders.get_fallback_chain
    plugins.discover_plugins()
    manager = plugins.get_plugin_manager()
    discovered = {p["name"]: p for p in manager.list_plugins()}
    expected_plugins = ("tamanitomo-routing", "tamanitomo-context", "tamanitomo-reader")
    for name in expected_plugins:
        row = discovered.get(name) or {}
        require(
            row.get("enabled") and not row.get("error"),
            f"Real Hermes loader did not load {name}: {row.get('error')}",
        )
    require(
        scheduler._job_fallback_chain is not native_job_chain,
        "Cron adapter was not installed",
    )
    require(
        run_config_loaders.get_fallback_chain is not native_gateway_chain,
        "Gateway adapter was not installed",
    )
    require(
        manager._context_engine.name == "tamanitomo-context",
        "Companion context engine not registered",
    )
    checks = ["real_plugin_discovery", "context_engine_registration"]
    cfg = load_config()
    enrolled = cfg["tamanitomo_routing"]["jobs"]
    pinned = {
        "name": enrolled[0],
        "provider": "custom",
        "model": "workload-model",
        "base_url": "https://workload.invalid/v1",
        "reasoning_effort": "high",
    }
    before = copy.deepcopy(pinned)
    require(
        scheduler._job_fallback_chain(pinned, cfg) == routes,
        "Pinned companion job changed the fallback order or endpoint credentials",
    )
    require(
        pinned == before,
        "Cron routing mutated a job's explicit model/reasoning override",
    )
    require(
        run_config_loaders.get_fallback_chain(cfg) == routes,
        "Gateway chain differs from the configured chain",
    )
    from hermes_cli.fallback_config import resolve_entry_api_key

    require(
        resolve_entry_api_key(routes[0]) == "synthetic-first-key",
        "Inline endpoint credential lost",
    )
    require(
        resolve_entry_api_key(routes[1]) == "synthetic-second-endpoint-key",
        "Endpoint-specific environment credential lost",
    )
    own_chain = [routes[-1], routes[0]]
    require(
        scheduler._job_fallback_chain({**pinned, "fallback_providers": own_chain}, cfg)
        == own_chain,
        "Per-job chain override lost",
    )
    require(
        scheduler._job_fallback_chain({**pinned, "fallback_providers": []}, cfg)
        is None,
        "Explicit empty chain did not disable fallback",
    )
    unrelated = {**pinned, "name": "An unrelated job"}
    require(
        scheduler._job_fallback_chain(unrelated, cfg)
        == native_job_chain(unrelated, cfg),
        "Adapter changed unrelated pinned jobs",
    )
    disabled = {**cfg, "plugins": {"disabled": ["tamanitomo-routing"]}}
    require(
        scheduler._job_fallback_chain(pinned, disabled)
        == native_job_chain(pinned, disabled),
        "Disabled adapter still routes jobs",
    )
    checks += [
        "ordered_cron_and_gateway_fallbacks",
        "endpoint_credentials",
        "individual_overrides",
        "unrelated_job_policy",
    ]

    specs = json.loads((ROOT / "kit/templates/cron/manifest.json").read_text())["jobs"]
    maintenance = [s for s in specs if s.get("no_agent")]
    require(
        all(
            s["name"].replace("{{AGENT}}", c.agent) not in enrolled for s in maintenance
        ),
        "Maintenance jobs were enrolled for model routing",
    )
    scripts = c.home / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    script = scripts / "compatibility-maintenance.py"
    script.write_text("print('MAINTENANCE_WITHOUT_MODEL')\n", encoding="utf-8")
    result, prompt = scheduler._prepare_job_prompt(
        {
            "id": "compat-maintenance",
            "name": "Compatibility maintenance",
            "no_agent": True,
            "script": str(script),
            "workdir": str(scratch),
        },
        "compat-maintenance",
        "Compatibility maintenance",
        None,
        None,
    )
    require(
        result
        and result[0]
        and prompt is None
        and "MAINTENANCE_WITHOUT_MODEL" in str(result),
        f"Native no-agent cron did not complete before creating an agent: {result}",
    )
    checks.append("native_no_agent_maintenance")

    # The gateway uses the same real shell-hook registry as chat and cron.
    from agent import shell_hooks
    from companion_local_context import BEGIN, END
    import companion_checkin as checkin

    wired = shell_hooks.register_from_config(cfg, accept_hooks=True)
    require(
        {s.event for s in wired} >= {"pre_llm_call", "on_session_end"},
        "Generated hooks did not register in Hermes",
    )
    result = manager.invoke_hook(
        "pre_llm_call",
        session_id="synthetic-gateway-session",
        platform="telegram",
        user_message="Hello from the compatibility fixture",
    )
    context = "\n".join(r.get("context", "") for r in result if isinstance(r, dict))
    require(
        BEGIN in context and END in context and c.agent in context,
        "Actual Hermes hook invocation lost companion continuity",
    )
    manager.invoke_hook(
        "on_session_end", session_id="synthetic-gateway-session", platform="telegram"
    )
    require(
        checkin.read(c)["pending"] == 1,
        "Gateway session end did not flag the owner conversation",
    )
    manager.invoke_hook(
        "on_session_end", session_id="synthetic-cron-session", platform="cron"
    )
    require(
        checkin.read(c)["pending"] == 1,
        "Cron end incorrectly rearmed the owner check-in",
    )
    checks += [
        "generated_gateway_continuity_hook",
        "owner_session_end_hook",
        "internal_session_does_not_rearm",
    ]
    require(
        not (scratch / "network-attempted").exists(),
        "A compatibility check attempted network access",
    )
    return {
        "status": "passed",
        "checks": checks,
        "plugins": list(expected_plugins),
        "maintenance_jobs": len(maintenance),
        "model_calls": 0,
        "messages_sent": 0,
        "python_version": ".".join(str(n) for n in sys.version_info[:3]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument(
        "--python", type=Path, help="Interpreter with Hermes dependencies installed"
    )
    parser.add_argument("--expected-revision", default=SUPPORTED_REVISION)
    parser.add_argument(
        "--report", type=Path, help="Write the non-secret JSON result here"
    )
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scratch", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    checkout = args.hermes_root.resolve()
    if args.probe:
        require(
            args.scratch
            and os.environ.get("TAMANITOMO_COMPAT_SCRATCH") == str(args.scratch),
            "Probe requires its isolated launcher",
        )
        report = probe(args.scratch, checkout)
        print("TAMANITOMO_COMPAT_RESULT=" + json.dumps(report, sort_keys=True))
        return 0
    actual = revision(checkout)
    require(
        actual == args.expected_revision,
        f"Hermes revision {actual} is not the reviewed revision {args.expected_revision}; inspect compatibility before updating the pin",
    )
    interpreter = args.python
    if interpreter is None:
        interpreter = next(
            (
                p
                for p in (
                    checkout / ".venv/bin/python",
                    checkout / ".hermes/bin/python",
                    checkout / ".venv/Scripts/python.exe",
                )
                if p.is_file()
            ),
            None,
        )
    require(
        interpreter and interpreter.is_file(),
        "Pass --python with the installed Hermes interpreter",
    )
    with tempfile.TemporaryDirectory(prefix="tamanitomo-hermes-compat-") as directory:
        scratch = Path(directory).resolve()
        (scratch / "guard").mkdir()
        (scratch / "guard/sitecustomize.py").write_text(GUARD, encoding="utf-8")
        (scratch / "empty-bundled-plugins").mkdir()
        result = subprocess.run(
            [
                str(interpreter.absolute()),
                str(Path(__file__).resolve()),
                "--probe",
                "--scratch",
                str(scratch),
                "--hermes-root",
                str(checkout),
            ],
            cwd=scratch,
            env=isolated_environment(scratch, checkout),
            text=True,
            capture_output=True,
            timeout=90,
        )
        if result.returncode:
            print(result.stdout, file=sys.stderr, end="")
            print(result.stderr, file=sys.stderr, end="")
            return result.returncode
        lines = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("TAMANITOMO_COMPAT_RESULT=")
        ]
        require(len(lines) == 1, "Hermes probe did not return a verification result")
        report = json.loads(lines[0].split("=", 1)[1])
        report["hermes_revision"] = actual
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
