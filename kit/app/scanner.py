"""Optional, host-local NudeNet installation shared by companion profiles."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from companion_platform import file_lock
import companion_media_review as review

PACKAGES = ["nudenet==3.4.2", "onnxruntime==1.30.0", "pillow>=10,<13", "numpy>=1.26,<3"]
CHECK = "import importlib.metadata,json,pathlib,nudenet,onnxruntime; p=pathlib.Path(nudenet.__file__).parent/'320n.onnx'; assert p.is_file(); print(json.dumps({'version':importlib.metadata.version('nudenet'),'model_bytes':p.stat().st_size}))"


def directory(c):
    return c.hermes_root / "companion-engines" / "nsfw"


def python_path(c):
    return (
        directory(c)
        / "venv"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )


def status(c):
    python = python_path(c)
    installed = False
    details = {}
    if python.is_file():
        try:
            r = subprocess.run(
                [str(python), "-c", CHECK], capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                details = json.loads(r.stdout)
                installed = details["version"] == "3.4.2"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return {
        "installed": installed,
        "selected": review.preferences(c)["review_provider"] == "local-nsfw",
        "name": "NudeNet · local nudity scanner",
        "model": "320n",
        "model_mb": 12,
        "memory_mb": 150,
        "directory": str(directory(c)),
        **details,
    }


def install(c, report):
    root = directory(c)
    if root.is_symlink() or (root / "venv").is_symlink():
        raise ValueError("Scanner directory must not be a symbolic link")
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / ".scan.lock"):
        if status(c)["installed"]:
            return {
                "note": "The local scanner is already installed. Select Use for this companion to enable it."
            }
        if shutil.disk_usage(root).free < 600 * 1024 * 1024:
            raise ValueError("Free at least 600 MB to install the scanner runtime")

        def run(args):
            result = subprocess.run(args, capture_output=True, text=True, timeout=600)
            if result.returncode:
                raise ValueError(
                    "Scanner installation failed: "
                    + (result.stderr or result.stdout)[-1500:]
                )

        python = python_path(c)
        uv = shutil.which("uv")
        report("Preparing an isolated CPU scanner runtime on this host")
        if not python.is_file():
            if uv:
                run([uv, "venv", "--python", "3.12", str(root / "venv")])
            else:
                run([sys.executable, "-m", "venv", str(root / "venv")])
        report(
            "Downloading NudeNet and its CPU runtime; no companion images are uploaded"
        )
        if uv:
            run([uv, "pip", "install", "--python", str(python), *PACKAGES])
        else:
            run([str(python), "-m", "pip", "install", "--only-binary=:all:", *PACKAGES])
        report("Testing the installed model locally")
        # Run real inference on a synthetic image, with no user's media involved.
        code = "import sys,tempfile; from pathlib import Path; from PIL import Image; sys.path.insert(0,sys.argv[1]); from companion_nsfw import classify; t=tempfile.TemporaryDirectory(); p=Path(t.name)/'test.png'; Image.new('RGB',(64,64),'blue').save(p); assert classify(p)['rating'] in ('safe','nsfw','unknown')"
        run(
            [
                str(python),
                "-c",
                code,
                str(Path(__file__).resolve().parents[1] / "scripts"),
            ]
        )
        if not status(c)["installed"]:
            raise ValueError("Scanner runtime verification failed")
    return {
        "note": "Local scanner installed and tested. Use for this companion enables private scanning."
    }


def register(app, load):
    @app.get("/api/media/scanner")
    def scanner_status():
        return status(load())

    @app.post("/api/media/scanner/install")
    def scanner_install():
        c = load()
        return app.state.operations.submit(
            str(c.hermes_root),
            "Install local image scanner",
            lambda report: install(c, report),
            profile=c.profile or "default",
        )

    @app.post("/api/media/scanner/use")
    def scanner_use():
        c = load()
        if not status(c)["installed"]:
            raise ValueError("Install the local scanner first")
        result = review.save_preferences(
            c,
            {
                "review_provider": "local-nsfw",
                "review_model": "",
                "review_before_delivery": True,
                "blur_unknown_initially": True,
                "blur_nsfw_initially": True,
            },
        )
        if (c.data / "image-timeline").is_dir():
            import companion_timeline

            companion_timeline.render_gallery(c)
        return result
