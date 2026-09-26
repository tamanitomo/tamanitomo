#!/usr/bin/env python3
"""The stable description of a companion, in the words an image model reads.

The appearance section of a SOUL is prose, written for a person: full
sentences, motivation, the reason a feature matters. An image model reads a
prompt as a bag of weighted phrases, so that same prose arrives as a thousand
characters of connective tissue — "she gives the impression of someone" carries
no pixels — and the traits that actually fix a likeness get diluted among them.

So this keeps a second description beside the first: the same person, reduced
to the fixed traits, comma separated, in a stable order. It is derived from the
appearance section once, by a model, and then it stays put. That is the whole
point. A likeness is consistent across generations because the same words are
sent every time, not because the same paragraph is re-summarised every time.

Three rules, the same ones `companion_vision` works by.

**It never writes on its own.** `propose()` returns text. Saving is a separate
call a person makes after reading it.

**It knows when it is out of date, and says so rather than acting.** The
appearance it was derived from is fingerprinted. When the SOUL changes, the
block is marked stale and the person is asked; nothing is rewritten because a
file changed.

**It is not the source of truth.** The SOUL is. This is a rendering of it, and
a person may edit that rendering freely — an edit is not stale, it is theirs.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_portrait as portrait
from companion_platform import hermes_command

TIMEOUT = 120
MAX_CHARS = 600

PROMPT = """Below is a written description of a person's appearance.

Rewrite it as a prompt fragment for an image generation model.

Rules:
- Comma-separated phrases only. No sentences, no verbs like "is" or "has", no
  pronouns, no narration.
- Keep ONLY fixed physical traits: apparent age, build, skin, freckles or other
  markings, eye colour, hair colour and length and usual styling, and whether
  they wear makeup.
- Drop anything that changes day to day: clothing, mood, activity, location,
  posture, and any sentence about the impression they give.
- Drop anything that is not visible in a photograph.
- Keep the person's own distinguishing details exactly as specified. If the
  description calls the freckles heavy and abundant, say heavy freckles; do not
  soften it to "some freckles".
- Aim for 12 to 25 phrases. Never exceed {limit} characters.

Return JSON and nothing else: {{"identity": "phrase, phrase, phrase"}}

The description:
---
{appearance}
---"""


def appearance_text(c):
    """The prose this block is derived from, or '' when there is none."""
    return portrait.identity_block(c, use_override=False)


def fingerprint(text):
    """A stable marker for the source, so a changed SOUL can be noticed."""
    return hashlib.sha256(
        " ".join(str(text or "").split()).encode("utf-8")
    ).hexdigest()[:16]


def state(c):
    """What is stored, what it came from, and whether the two still agree."""
    import companion_media as media

    data = media.effective(c)
    stored = data.get("identity_override")
    source = appearance_text(c)
    return {
        "text": stored if isinstance(stored, str) else "",
        "saved": isinstance(stored, str) and bool(stored.strip()),
        "appearance": source,
        "has_appearance": bool(source.strip()),
        # Stale only once something was saved: with nothing saved there is
        # nothing to be out of date, only something not written yet.
        "stale": bool(
            isinstance(stored, str)
            and stored.strip()
            and data.get("identity_source") != fingerprint(source)
        ),
        "source_fingerprint": fingerprint(source),
        "saved_fingerprint": data.get("identity_source") or "",
    }


def _extract(text):
    """The first balanced JSON object in the reply."""
    start = text.find("{")
    while start != -1:
        depth = 0
        quoted = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\" and quoted:
                escaped = True
                continue
            if ch == '"':
                quoted = not quoted
                continue
            if quoted:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("the model did not return JSON; nothing was written")


def tidy(text):
    """One line of comma-separated phrases, deduplicated, within the limit."""
    import companion_media as media

    seen = []
    known = set()
    for term in media.split_terms(" ".join(str(text or "").split())):
        key = term.lower()
        if key and key not in known:
            known.add(key)
            seen.append(term)
    out = ", ".join(seen)
    if len(out) > MAX_CHARS:
        kept = []
        for term in seen:
            if len(", ".join(kept + [term])) > MAX_CHARS:
                break
            kept.append(term)
        out = ", ".join(kept)
    return out


def propose(c, model="", provider="", timeout=TIMEOUT):
    """Ask a model to render the appearance section as prompt phrases.

    Runs with `--ignore-rules`, so the companion's own SOUL and memory are not
    injected: this asks a model to rewrite a paragraph, not to be the person the
    paragraph is about.
    """
    appearance = appearance_text(c)
    if not appearance.strip():
        raise ValueError("There is no appearance section to derive this from yet")
    argv = list(
        hermes_command("chat", "--oneshot", "-Q", "--ignore-rules", "--max-turns", "1")
    )
    if model:
        argv += ["--model", model]
    if provider:
        argv += ["--provider", provider]
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".txt", encoding="utf-8", delete=False
    )
    try:
        handle.write(PROMPT.format(appearance=appearance, limit=MAX_CHARS))
        handle.close()
        argv += ["--query-file", handle.name]
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                env={
                    **os.environ,
                    "HERMES_HOME": str(c.home),
                    "HERMES_TIMEZONE": c.timezone,
                },
            )
        except FileNotFoundError:
            raise ValueError(
                "Hermes is not on PATH, so no model can be reached from here"
            )
        except subprocess.TimeoutExpired:
            raise ValueError(
                f"the model did not answer within {timeout}s; nothing was written"
            )
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    if result.returncode:
        lines = [
            l.strip()
            for l in (result.stderr or result.stdout or "").splitlines()
            if l.strip()
        ]
        raise ValueError(
            "Hermes refused the call: "
            + (" ".join(lines[-3:])[:300] if lines else "no output")
        )
    proposed = tidy(_extract(result.stdout).get("identity", ""))
    if not proposed:
        raise ValueError("the model returned nothing usable; nothing was written")
    return {
        "identity": proposed,
        "appearance": appearance,
        "source_fingerprint": fingerprint(appearance),
        "written": False,
        "note": "Read it before you keep it. Nothing is saved until you accept it.",
    }


def save(c, text, source=None):
    """Keep this block, and remember which appearance it belongs to.

    `source` defaults to the appearance as it stands now, which is what a person
    editing the text by hand means: this is the block for the SOUL I can see.
    """
    import companion_media as media

    text = tidy(text)
    if not text:
        raise ValueError(
            "An empty block would send nothing; clear it with `follow` instead"
        )
    data = media.load(c)
    data["identity_override"] = text
    data["identity_source"] = fingerprint(
        appearance_text(c) if source is None else source
    )
    media.save(c, data, media.revision(c))
    return state(c)


def follow(c):
    """Go back to sending the SOUL prose directly, keeping nothing."""
    import companion_media as media

    data = media.load(c)
    data["identity_override"] = None
    data.pop("identity_source", None)
    media.save(c, data, media.revision(c))
    return state(c)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("show", help="the stored block and whether it is out of date")
    d = s.add_parser(
        "propose", help="ask a model to derive it from the appearance section"
    )
    d.add_argument("--model", default="")
    d.add_argument("--provider", default="")
    d.add_argument(
        "--apply", action="store_true", help="keep it without reading it first"
    )
    w = s.add_parser("set", help="store a block written by hand")
    w.add_argument("text")
    s.add_parser("follow", help="forget it and send the SOUL prose instead")
    a = p.parse_args()
    c = cc.load(a.home)
    if a.cmd == "show":
        out = state(c)
    elif a.cmd == "set":
        out = save(c, a.text)
    elif a.cmd == "follow":
        out = follow(c)
    else:
        out = propose(c, model=a.model, provider=a.provider)
        if a.apply:
            out = {**out, **save(c, out["identity"]), "written": True}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
