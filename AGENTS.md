# Tamanitomo development

Use three long-lived branches only:

- `beta`: all software edits, reviews and integration. Work directly here; do not
  create feature, agent, checkpoint or review branches unless the owner explicitly
  requests one. Do not create extra worktrees by default.
- `main`: the tested, tagged GitHub release. Promote reviewed beta changes here
  when a stable release is authorized, update VERSION and release notes, run the
  release checks, then tag. Never develop directly on main.
- `gh-pages`: the website at tamanitomo.com. Keep its independent history and CNAME.

Before consolidation or deleting branches, create and verify a Git bundle of
all refs and preserve worktree changes, untracked files and relevant ignored
files. Never merge stale experiments merely to mark a branch merged. Record
which newer implementation supersedes them. Android wheels are retained by the
immutable `wheelhouse-aarch64` tag, not a development branch.

Develop and validate companion behavior with frontier providers. Local models
remain supported, but do not add model-specific tool-call workarounds merely to
compensate for their limitations.

Provider selection must reach chat, workers and shipped model-backed cron jobs.
Respect workload reasoning and individual overrides; preserve the explicitly
ordered fallback chain and endpoint-specific credentials. Maintenance scripts
must not acquire model calls. Do not replay a tool-executing turn to fail over.

Companion life continues without the human. Preserve fictional-life provenance,
real tool evidence, persistent interests and commitments, and the app's outreach
and quiet-hours settings. Do not turn human absence into guilt or waiting.
Record input/output usage when available; unknown usage is not zero.

Validation: run `.venv/bin/python -m pytest -q`, Black and Ruff as configured in
CI, installer shell syntax checks, and `python tools/build_release.py` for
packaging changes. Verify Hermes routing compatibility in an isolated profile;
do not exercise real user memories or send messages as part of tests.
