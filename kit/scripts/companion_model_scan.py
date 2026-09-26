"""Read what a safetensors file says about itself, without moving the file.

A safetensors file begins with an 8-byte little-endian length followed by that
many bytes of JSON. Training tools record the base model in that header under
`ss_base_model_version` or `ss_sd_model_name`, so a few kilobytes per file is
enough to tell an Illustrious LoRA from an SD 1.5 one.

It runs where the models are: locally, or piped to `python3 -c` over SSH, which
is how the weight downloader already reaches a remote Comfy host. It reads
headers only and writes nothing.
"""

import hashlib
import json
import os
import struct
import sys

MAX_HEADER = 8 * 1024 * 1024
FAMILY_HINTS = [
    ("illustrious", "Illustrious"),
    ("noob", "NoobAI"),
    ("pony", "Pony"),
    ("animagine", "Animagine"),
    ("flux", "Flux"),
    ("sdxl", "SDXL"),
    ("xl_base", "SDXL"),
    ("stable-diffusion-xl", "SDXL"),
    ("sd_xl", "SDXL"),
    ("v1-5", "SD 1.5"),
    ("sd15", "SD 1.5"),
    ("stable-diffusion-v1", "SD 1.5"),
]


def family_from(text):
    lowered = str(text or "").lower()
    for token, label in FAMILY_HINTS:
        if token in lowered:
            return label
    return ""


def read_header(path):
    """The file's own metadata, or None when it does not have any."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(8)
            if len(raw) < 8:
                return None
            length = struct.unpack("<Q", raw)[0]
            if not 0 < length <= MAX_HEADER:
                return None
            header = json.loads(handle.read(length).decode("utf-8", "replace"))
    except (OSError, ValueError, struct.error):
        return None
    return header.get("__metadata__") if isinstance(header, dict) else None


def describe(path):
    meta = read_header(path) or {}
    # The explicit field first; the trained-on model name is the fallback.
    for key in (
        "ss_base_model_version",
        "modelspec.architecture",
        "ss_sd_model_name",
        "ss_base_model",
        "ss_pretrained_model_name_or_path",
    ):
        family = family_from(meta.get(key))
        if family:
            return {"family": family, "source": key}
    if meta:
        return {"family": "", "source": "header had no base model"}
    return {"family": "", "source": "no header"}


def sha256(path):
    """The whole-file digest Civitai indexes its weights under.

    Reading several gigabytes per file is the reason this is opt-in, and the
    reason it is only ever asked for on files the header could not identify.
    """
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return ""
    return digest.hexdigest()


def scan(folders, hash_unknown=False, known=None):
    known = known or {}
    out = {}
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in sorted(dirs) if not d.startswith(".")]
            for entry in sorted(files):
                if not entry.endswith(".safetensors"):
                    continue
                full = os.path.join(root, entry)
                if not os.path.isfile(full):
                    continue
                key = os.path.relpath(full, folder).replace(os.sep, "/")
                if key in out:
                    continue
                record = describe(full)
                # Only files the header could not place are worth hashing, and
                # only once: a digest already on file is reused as it stands.
                if hash_unknown and not record["family"]:
                    record["sha256"] = known.get(key) or sha256(full)
                out[key] = record
    return out


def main():
    request = json.loads(sys.stdin.read() or "{}")
    folders = [f for f in (request.get("folders") or []) if isinstance(f, str)]
    known = request.get("known") if isinstance(request.get("known"), dict) else {}
    try:
        models = scan(folders, bool(request.get("hash_unknown")), known)
        print("RESULT=" + json.dumps({"models": models}))
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        print("ERROR=" + str(exc)[:300])


if __name__ == "__main__":
    main()
