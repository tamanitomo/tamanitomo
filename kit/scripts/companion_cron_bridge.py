"""Per-job toolsets, set inside Hermes. Plumbing between the kit and Hermes.

Each kit job names the tools its work needs (cron/manifest.json). Hermes's cron
command line offers no flag for that, so every job ran with every tool its
platform allows: a day pulse could browse, load skills, delegate and inspect
images, and a model inclined to explore did, at several million tokens a run.
Hermes keeps `enabled_toolsets` on the job record itself; this sets it through
Hermes's own `update_job`, under Hermes's own lock.

Reads {"jobs": [{"id": ..., "toolsets": [...]}]} on stdin and prints one line,
COMPANION_CRON=<json list of results>. A toolset this Hermes does not know is
left out and reported rather than passed on.
"""

import json
import os
import sys


def main():
    payload = json.load(sys.stdin)
    from cron.jobs import update_job

    try:
        from toolsets import TOOLSETS

        known = set(TOOLSETS)
    except Exception:
        known = None
    results = []
    for item in payload.get("jobs", []):
        wanted = [str(t) for t in item.get("toolsets") or []]
        names = [t for t in wanted if known is None or t in known]
        unknown = sorted(set(wanted) - set(names))
        try:
            update_job(item["id"], {"enabled_toolsets": names or None})
            results.append(
                {"id": item["id"], "ok": True, "toolsets": names, "unknown": unknown}
            )
        except Exception as exc:  # reported per job; the others still apply
            results.append({"id": item["id"], "ok": False, "error": str(exc)[:200]})
    print("COMPANION_CRON=" + json.dumps(results))


if __name__ == "__main__":
    # Importing Hermes can re-run this script under Hermes's own Python (execv, in
    # isolated mode). Let that happen before stdin is read, as the other bridges do.
    try:
        import hermes_bootstrap  # noqa: F401
    except ImportError:
        pass
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
