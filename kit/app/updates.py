"""Stage a trusted release ZIP; apply it only on the next launcher start."""

import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath
from fastapi import Request, HTTPException

ROOT = Path(__file__).resolve().parents[2]
MAX_ZIP = 25 * 1024**2
import uuid

INSTANCE_ID = uuid.uuid4().hex


def stage(raw, root=ROOT):
    if len(raw) > MAX_ZIP:
        raise ValueError("Update package exceeds 25 MB")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries = z.infolist()
        names = [i.filename for i in entries]
        if len(names) != len(set(names)) or len(names) > 1000:
            raise ValueError("Invalid duplicate or oversized release")
        if sum(i.file_size for i in entries) > 80 * 1024**2:
            raise ValueError("Expanded update is too large")
        files = {}
        modes = {}
        for i in entries:
            p = PurePosixPath(i.filename)
            if (
                len(p.parts) < 2
                or p.parts[0] not in ("tamanitomo", "companion-kit")
                or ".." in p.parts
                or "\\" in i.filename
                or i.is_dir()
                or stat.S_ISLNK(i.external_attr >> 16)
            ):
                raise ValueError("Unsafe release path")
            name = "/".join(p.parts[1:])
            if (
                i.filename != p.parts[0] + "/" + name
                or ":" in name
                or any(ord(c) < 32 for c in name)
                or any(x.endswith((".", " ")) for x in p.parts)
                or name.casefold() in {n.casefold() for n in files}
            ):
                raise ValueError("Ambiguous release path")
            if name.startswith(".") and name not in (
                ".gitignore",
                ".gitattributes",
                ".github/workflows/test.yml",
            ):
                raise ValueError("Private state cannot be included in an update")
            if any(
                x in p.parts for x in (".env", ".venv", "__pycache__")
            ) or name.endswith("companion.json"):
                raise ValueError("Release contains user state")
            files[name] = z.read(i)
            modes[name] = 0o755 if (i.external_attr >> 16) & 0o111 else 0o644
        hashes = json.loads(files.pop("SHA256SUMS.json"))
        manifest = json.loads(files["release-files.json"])
        if set(manifest) != set(files) or set(hashes) != set(files):
            raise ValueError("Release manifest does not match package")
        for name, data in files.items():
            if hashes[name] != hashlib.sha256(data).hexdigest():
                raise ValueError("Update integrity check failed: " + name)
            dest = root / name
            for p in [dest, *dest.parents]:
                if p == root:
                    break
                if p.is_symlink():
                    raise ValueError("Update destination contains a link")
        version = files.get("VERSION", b"Unversioned").decode().strip()
        # Never overwrite a modified installed release. Development trees need manual updates.
        current = root / "SHA256SUMS.json"
        if not current.is_file():
            raise ValueError(
                "This is a development checkout. Install updates in an extracted release, not this working tree."
            )
        old = json.loads(current.read_text())
        if any((root / n).exists() and n not in old for n in files):
            raise ValueError(
                "Update would overwrite an unmanaged local file; move it aside first"
            )
        changed = []
        for name, digest in old.items():
            installed = root / name
            installed_digest = (
                hashlib.sha256(installed.read_bytes()).hexdigest()
                if installed.is_file()
                else None
            )
            incoming_digest = (
                hashlib.sha256(files[name]).hexdigest() if name in files else None
            )
            # A prior hot-fix that is byte-for-byte identical to this trusted
            # release is safe to adopt. Unrelated local edits remain protected.
            if installed_digest != digest and installed_digest != incoming_digest:
                changed.append(name)
        if changed:
            raise ValueError(
                "Local code changes detected; keep them and update manually: "
                + ", ".join(changed[:5])
            )
        folder = root / ".pending-update"
        if folder.exists():
            raise ValueError(
                "An update is already staged; relaunch before staging another"
            )
        folder.mkdir()
        if folder.is_symlink():
            raise ValueError("Invalid staging folder")
        for name, data in files.items():
            dest = folder / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            dest.chmod(modes[name])
        (folder / "SHA256SUMS.json").write_text(json.dumps(hashes))
        return {
            "staged": True,
            "version": version,
            "files": len(files),
            "note": "Update verified and staged. Close Tamanitomo, then launch it again to install. Your Hermes profiles and vault are untouched.",
        }


_UPDATE_CACHE = {"checked_at": 0, "data": None, "version": None}
RELEASE_API = "https://api.github.com/repos/tamanitomo/tamanitomo/releases/latest"
ASSET_NAME = "tamanitomo-release.zip"


def _version(value):
    import re

    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ValueError("Expected a stable release version, such as 2.2.2")
    return tuple(map(int, match.groups()))


def check_github_update(current_version: str, force: bool = False) -> dict:
    import time
    import urllib.request
    import urllib.error

    now = time.time()
    cached = _UPDATE_CACHE.get("data")
    if (
        not force
        and cached
        and _UPDATE_CACHE.get("version") == current_version
        and now - _UPDATE_CACHE["checked_at"] < 3600
    ):
        return cached
    result = {
        "has_update": False,
        "latest_version": None,
        "release_url": None,
        "release_notes": None,
        "download_url": None,
        "checked": False,
        "error": None,
    }
    try:
        request = urllib.request.Request(
            RELEASE_API,
            headers={
                "User-Agent": "Tamanitomo-Updater",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            release = json.loads(response.read(1024 * 1024))
        tag = release["tag_name"]
        latest = tag.removeprefix("v")
        asset = next(
            (a for a in release.get("assets", []) if a.get("name") == ASSET_NAME), None
        )
        if release.get("draft") or release.get("prerelease") or not asset:
            raise ValueError(
                "The latest release has no installable Tamanitomo ZIP yet."
            )
        url = asset.get("browser_download_url", "")
        expected = f"https://github.com/tamanitomo/tamanitomo/releases/download/{tag}/{ASSET_NAME}"
        if url != expected:
            raise ValueError("The release asset is not on the official download URL.")
        notes = (release.get("body") or "").strip()
        if len(notes) > 12000:
            notes = notes[:12000].rstrip() + "\n\n…"
        result.update(
            has_update=_version(latest) > _version(current_version),
            latest_version=latest,
            release_url=release.get("html_url"),
            release_notes=notes,
            download_url=url,
            digest=asset.get("digest"),
            tag=tag,
            checked=True,
        )
    except urllib.error.HTTPError as exc:
        result["error"] = (
            "No published release is available yet."
            if exc.code == 404
            else f"GitHub update check failed (HTTP {exc.code}). Try again later."
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["error"] = f"Could not check for updates: {exc}"
    # Failures remain retryable; do not claim that an offline host is up to date.
    if result["checked"]:
        _UPDATE_CACHE.update(checked_at=now, data=result, version=current_version)
    else:
        _UPDATE_CACHE.clear()
    return result


def _delayed_restart():
    """Restart this workspace, without restarting unrelated workspaces or Hermes."""
    import time
    import shutil
    import subprocess
    import sys

    time.sleep(2)
    if shutil.which("systemctl"):
        for unit in ("tamanitomo.service", "companion-workspace.service"):
            try:
                result = subprocess.run(
                    [
                        "systemctl",
                        "--user",
                        "show",
                        unit,
                        "--property=MainPID",
                        "--value",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip() == str(os.getpid()):
                    subprocess.run(
                        ["systemctl", "--user", "restart", "--no-block", unit],
                        check=True,
                        timeout=5,
                    )
                    return
            except (OSError, subprocess.SubprocessError):
                pass
    # Works for terminal launches and runit too; exec keeps the supervised PID.
    os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])


def _dispatch_job_ids(home):
    """This profile's outbox-dispatcher cron job id(s), identified the same way
    kit/cli/scaffold.py's own schedule refresh does: render the manifest's job names
    for this agent and match by the manifest's stable `key`, never by a guessed
    name/script-path substring (companion_dispatch.py is the module every dispatch
    job in every manifest revision has shared)."""
    from kit.cli.common import _read_jobs, load_manifest
    import companion_config as cc
    import companion_render as cr

    try:
        c = cc.load(home)
        specs = {
            cr.render(spec["name"], {"AGENT": c.agent}): spec
            for spec in load_manifest(c)["jobs"]
        }
        return [
            row["id"]
            for row in _read_jobs(home / "cron/jobs.json")["jobs"]
            if row.get("id")
            and row.get("enabled", True)
            and specs.get(row.get("name"), {}).get("key") == "dispatch"
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _all_dispatch_jobs(root):
    """(home, job_id) for every profile's dispatcher under this installation's default
    Hermes root. Does not reach a linked/secondary installation (kit/app/server.py's
    `linked-*` runtimes) -- a stated limitation, not a silent gap: those are drained
    manually today, same as before this function existed."""
    from kit.cli.roster import discover

    pairs = []
    try:
        for _name, home in discover(root):
            if home.is_symlink() or not home.is_dir():
                continue
            pairs.extend((home, job_id) for job_id in _dispatch_job_ids(home))
    except OSError:
        pass
    return pairs


def _dispatch_running():
    """Observe dispatcher processes, or return None when observation is unavailable."""
    import subprocess
    import sys

    if not sys.platform.startswith("linux"):
        command = (
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$ErrorActionPreference = 'Stop'; "
                "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID } | "
                "ForEach-Object { "
                "if ($_.CommandLine) { $_.CommandLine } "
                "elseif ($_.Name -match '^(python|pypy|hermes)') { "
                "'TAMANITOMO_UNREADABLE_PROCESS' } }",
            ]
            if os.name == "nt"
            else ["ps", "-eo", "args="]
        )
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode or "TAMANITOMO_UNREADABLE_PROCESS" in result.stdout:
                return None
            return "companion_dispatch" in result.stdout
        except (OSError, subprocess.SubprocessError):
            return None
    unreadable = False
    try:
        with os.scandir("/proc") as entries:
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                try:
                    cmdline = (Path("/proc") / entry.name / "cmdline").read_bytes()
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except OSError:
                    unreadable = True
                    continue
                if b"companion_dispatch" in cmdline:
                    return True
    except OSError:
        return None
    return None if unreadable else False


def _drain_dispatchers(root, report, runtime_cls=None, wait_seconds=60):
    """Pause enabled dispatch jobs and verify running ticks finish before updating.

    Older installed dispatchers do not share the current process lock, so observe
    their command lines as well. A failed pause, unreadable process list, or timeout
    aborts the update and restores the jobs already paused. The caller resumes the
    returned jobs after installation, including when installation itself fails.
    """
    from .runtime import Runtime
    import time

    rt = (runtime_cls or Runtime)(root)
    pairs = _all_dispatch_jobs(root)
    paused = []
    try:
        for home, job_id in pairs:
            rt.run(["cron", "pause", job_id], home=home, timeout=15)
            paused.append((home, job_id))
        if paused:
            report(
                {
                    "stage": "Pausing the outbox dispatcher and waiting for its current tick to finish...",
                    "percent": 62,
                }
            )
            deadline = time.monotonic() + wait_seconds
            while True:
                running = _dispatch_running()
                if running is None:
                    raise ValueError(
                        "Cannot verify that the outbox dispatcher has stopped. "
                        "The update was cancelled; scheduled jobs have been restored."
                    )
                if not running:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError(
                        "The outbox dispatcher is still running. "
                        "The update was cancelled; try again after its current tick finishes."
                    )
                time.sleep(min(1, remaining))
    except Exception:
        _resume_dispatchers(paused, rt)
        raise
    return paused, rt


def _resume_dispatchers(paused, rt):
    for home, job_id in paused:
        try:
            rt.run(["cron", "resume", job_id], home=home, timeout=15)
        except ValueError:
            pass


def _install_dependencies(root, requirements):
    import subprocess
    import sys

    installed = root / "requirements.txt"
    if installed.exists() and installed.read_bytes() == requirements.read_bytes():
        return
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode:
        raise ValueError(
            "Dependency installation failed; application code was not replaced. "
            + result.stderr[-1500:]
        )


def perform_in_app_update(report, root=ROOT, hermes_root=None):
    """Install the published release while preserving profile jobs and private data."""
    import subprocess
    import shutil
    import threading
    import urllib.request

    version = (root / "VERSION").read_text().strip()
    report({"stage": "Checking the official release...", "percent": 10})
    info = check_github_update(version, force=True)
    if not info.get("checked"):
        raise ValueError(info.get("error") or "Could not check the official release.")
    if not info["has_update"]:
        return {
            "success": True,
            "restarting": False,
            "version": version,
            "message": "You already have the latest stable release.",
        }
    latest = info["latest_version"]
    if hermes_root is None:
        import companion_config as cc

        hermes_root = cc.load().hermes_root
    paused, drain_rt = _drain_dispatchers(Path(hermes_root), report)
    try:
        if (root / ".git").exists() and shutil.which("git"):

            def git(*args):
                result = subprocess.run(
                    ["git", *args],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode:
                    raise ValueError(
                        "Git update failed: " + (result.stderr or result.stdout).strip()
                    )
                return result.stdout.strip()

            if git("status", "--porcelain"):
                raise ValueError(
                    "Local code changes detected. Commit or move them before updating."
                )
            report({"stage": "Fetching the published release tag...", "percent": 35})
            git(
                "fetch",
                "https://github.com/tamanitomo/tamanitomo.git",
                "tag",
                info["tag"],
            )
            if git("show", info["tag"] + ":VERSION") != latest:
                raise ValueError("Release tag and VERSION do not match.")
            # Check fast-forward feasibility before installing dependencies or changing code.
            git("merge-base", "--is-ancestor", "HEAD", info["tag"])
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                requirements = Path(tmp) / "requirements.txt"
                requirements.write_text(
                    git("show", info["tag"] + ":requirements.txt") + "\n"
                )
                _install_dependencies(root, requirements)
            git("merge", "--ff-only", info["tag"])
        elif (root / "SHA256SUMS.json").is_file():
            report({"stage": "Downloading the official release ZIP...", "percent": 35})
            request = urllib.request.Request(
                info["download_url"], headers={"User-Agent": "Tamanitomo-Updater"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(MAX_ZIP + 1)
            if len(data) > MAX_ZIP:
                raise ValueError("Update package exceeds 25 MB")
            digest = info.get("digest")
            if digest and digest != "sha256:" + hashlib.sha256(data).hexdigest():
                raise ValueError(
                    "Downloaded ZIP does not match the GitHub release digest."
                )
            report(
                {
                    "stage": "Verifying the release and preparing dependencies...",
                    "percent": 60,
                }
            )
            stage(data, root=root)
            try:
                staged = root / ".pending-update"
                if (staged / "VERSION").read_text().strip() != latest:
                    raise ValueError(
                        "Release version does not match the published tag."
                    )
                _install_dependencies(root, staged / "requirements.txt")
                report(
                    {
                        "stage": "Installing application files with rollback backup...",
                        "percent": 85,
                    }
                )
                from update_release import _apply_pending

                _apply_pending(root)
            except Exception:
                shutil.rmtree(root / ".pending-update", ignore_errors=True)
                raise
        else:
            raise ValueError(
                "This source copy is not a release installation. Extract the official release ZIP to install updates."
            )
    finally:
        _resume_dispatchers(paused, drain_rt)
    report(
        {
            "stage": f"Tamanitomo v{latest} installed. Restarting workspace...",
            "percent": 100,
        }
    )
    threading.Thread(target=_delayed_restart, daemon=True).start()
    return {
        "success": True,
        "restarting": True,
        "version": latest,
        "message": f"Tamanitomo updated to v{latest}. Workspace is restarting.",
    }


def register(app):
    @app.get("/api/updates")
    def status(force: bool = False):
        version = (
            (ROOT / "VERSION").read_text().strip()
            if (ROOT / "VERSION").exists()
            else "2.2.1"
        )
        remote = check_github_update(version, force=force)
        return {
            "version": version,
            "release_install": (ROOT / "SHA256SUMS.json").is_file(),
            "is_git": (ROOT / ".git").is_dir(),
            "pending": (ROOT / ".pending-update/SHA256SUMS.json").is_file(),
            "instance_id": INSTANCE_ID,
            **remote,
        }

    @app.post("/api/updates/check")
    def check_now():
        version = (
            (ROOT / "VERSION").read_text().strip()
            if (ROOT / "VERSION").exists()
            else "2.2.1"
        )
        return check_github_update(version, force=True)

    @app.post("/api/updates/apply")
    def apply_update_route(request: Request):
        if not hasattr(app.state, "operations"):
            raise HTTPException(500, "Operations manager not initialized")

        prof = request.query_params.get("profile") or "default"

        def run(report):
            runtime = app.state.runtimes.get("existing")
            return perform_in_app_update(
                report, root=ROOT, hermes_root=runtime.root if runtime else None
            )

        return app.state.operations.submit(
            str(ROOT), "Update Tamanitomo", run, profile=prof, kind="application"
        )

    @app.post("/api/updates/stage")
    async def upload(request: Request):
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_ZIP:
                raise HTTPException(413, "Update package exceeds 25 MB")
            chunks.append(chunk)
        try:
            return stage(b"".join(chunks))
        except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError):
            raise ValueError("Not a Tamanitomo release package")
