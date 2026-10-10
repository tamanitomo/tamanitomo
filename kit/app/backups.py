"""Authenticated export, inspection and isolated restore of companion bundles."""

import datetime as dt
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import time

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

import companion_backup as backup
from companion_platform import atomic_write, file_lock


def register(app, select, load):
    uploads = app.state.operations.directory.parent / "recovery-uploads"

    def scope():
        runtime, profile = select()
        return str(runtime.root), profile

    def upload_files(ident):
        if (
            not isinstance(ident, str)
            or len(ident) != 32
            or any(c not in "0123456789abcdef" for c in ident)
        ):
            raise ValueError("Unknown recovery upload")
        archive, metadata = uploads / (ident + ".zip"), uploads / (ident + ".json")
        if not metadata.is_file() or not archive.is_file():
            raise ValueError("Recovery preview expired. Choose the backup again.")
        saved = json.loads(metadata.read_text(encoding="utf-8"))
        if saved["scope"] != list(scope()):
            raise HTTPException(404, "Recovery upload not found")
        return archive, metadata

    @app.get("/api/backup/status")
    def backup_status():
        path = load().home / ".tamanitomo-backup.json"
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {"verified_at": None}
        )

    @app.post("/api/backup/export")
    def export(payload: dict):
        c = load()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as stream:
            path = Path(stream.name)
        path.unlink()
        try:
            result = backup.export(
                c, path, include_credentials=payload.get("include_credentials") is True
            )
            atomic_write(
                c.home / ".tamanitomo-backup.json",
                json.dumps(
                    {
                        "verified_at": result["finished_at"],
                        "files": len(result["files"]),
                        "bytes": result["bytes"],
                        "credentials_included": result["credentials_included"],
                    }
                ),
            )
            filename = (
                (c.profile or "companion")
                + "-recovery-"
                + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                + ".zip"
            )
            return FileResponse(
                path,
                filename=filename,
                media_type="application/zip",
                background=BackgroundTask(path.unlink),
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/backup/preview")
    async def preview(request: Request):
        owner_scope = list(scope())
        uploads.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Uploaded backups contain private history; discard abandoned previews.
        for path in uploads.glob("*.*"):
            if path.is_file() and time.time() - path.stat().st_mtime > 86400:
                path.unlink(missing_ok=True)
        ident = secrets.token_hex(16)
        path = uploads / (ident + ".zip")
        metadata = uploads / (ident + ".json")
        try:
            size = 0
            with path.open("xb") as stream:
                path.chmod(0o600)
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > backup.MAX_BYTES + 40_000_000:
                        raise ValueError("Recovery upload exceeds 2 GB")
                    stream.write(chunk)
            manifest = await run_in_threadpool(backup.inspect, path)
            atomic_write(metadata, json.dumps({"scope": owner_scope}))
            return {
                "id": ident,
                "agent": manifest["agent"],
                "profile": manifest["profile"] or "default",
                "created_at": manifest["created_at"],
                "files": len(manifest["files"]),
                "bytes": manifest["bytes"],
                "credentials_included": manifest["credentials_included"],
                "excluded": manifest["excluded"],
                "note": manifest["note"],
            }
        except Exception:
            path.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            raise

    @app.post("/api/backup/restore")
    def restore(payload: dict):
        from .runtime import Runtime, read_json

        path, metadata = upload_files(payload.get("id"))
        if not all(
            isinstance(payload.get(key), str) and payload[key].strip()
            for key in ("root", "vault")
        ):
            raise ValueError("Choose new Hermes and vault folders on this host")
        result = backup.restore(path, payload["root"], payload["vault"])
        ident = "linked-" + hashlib.sha256(result["root"].encode()).hexdigest()[:12]
        import threading

        response = {**result, "installation": None, "linked": False}
        try:
            restored_runtime = Runtime(result["root"])
            registry = app.state.linked_installations_file
            # Match /api/installations/link: writes from different installations
            # have different request locks but share this one durable registry.
            with file_lock(registry.with_suffix(".lock")):
                saved = read_json(registry, {})
                if not isinstance(saved, dict):
                    raise ValueError("The saved installation list is not an object")
                saved[ident] = result["root"]
                atomic_write(registry, json.dumps(saved, indent=2) + "\n")
                app.state.write_locks[ident] = threading.Lock()
                app.state.runtimes[ident] = restored_runtime
            response.update(installation=ident, linked=True)
        except Exception as exc:
            # The new directories already contain a verified, paused restore.
            # Registration is a separate convenience, never a reason to repeat it.
            response["registration_error"] = type(exc).__name__ + ": " + str(exc)[:300]
            response["note"] += (
                " Your companion was restored successfully, but this app could not "
                "add its installation. Link the restored Hermes folder under "
                "Settings → Installation & gateway to open it here. The restored "
                "files are intact; do not restore the backup again."
            )
        for upload in (path, metadata):
            try:
                upload.unlink(missing_ok=True)
            except OSError:
                response["cleanup_warning"] = (
                    "A temporary uploaded copy could not be removed; the restored "
                    "companion is unaffected."
                )
        return response
