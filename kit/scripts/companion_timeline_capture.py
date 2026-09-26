#!/usr/bin/env python3
"""Capture a recorded timeline scene without spending conversation-model turns.

Uses the saved Image Studio preset and its normal review policy. Never sends
messages, invents a scene, or falls back to an unconfigured image provider.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import companion_config as cc
import companion_media as media
import companion_portrait as portrait
import companion_timeline as timeline


def capture(c, now=None):
    claimed = timeline.prepare(c, now)
    if not claimed["ready"]:
        return {"status": "skipped", "reason": claimed["reason"]}
    ident = claimed["capture_id"]
    try:
        recipe = media.effective(c)
        preset = recipe.get("routes", {}).get("portrait") or recipe.get(
            "default_preset"
        )
        if not preset:
            raise ValueError(
                "Choose a saved Image Studio portrait preset before automatic capture"
            )
        # Freeze the claimed scene even if a concurrent pulse advances presence.
        overrides = portrait.recorded_overrides(c, record=claimed["scene"])
        # `prepare` has already refused this moment unless it may be rendered as what
        # it is, so reaching here with an undressed scene means the permissions hold.
        # Saying so lifts the modesty negatives; leaving them on is what put clothes
        # back into the shower.
        intimate = timeline.private_reason(c, claimed["scene"]["state"]) == "undressed"
        # A capture is a look at what she is doing, not something she made, so it
        # is rendered out of sight and the timeline becomes its only home. It used
        # to land in Creations as well, which filed every automatic moment as her
        # work and left two identical files behind for the library to reconcile.
        generated = media.generate(
            c, preset, "portrait", overrides, intimate=intimate, purpose="capture"
        )
        try:
            saved = timeline.save(
                c,
                ident,
                generated["path"],
                generated["provider"],
                now,
                prompts=generated.get("prompts"),
            )
        finally:
            media.discard_scratch(generated["path"])
        return {
            "status": saved["status"],
            "capture_id": ident,
            "path": str(timeline.root(c) / "images" / saved["filename"]),
            "provider": saved["provider"],
            "sha256": saved["sha256"],
        }
    except Exception as exc:
        timeline.fail(c, ident, str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(capture(cc.load(args.home)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
