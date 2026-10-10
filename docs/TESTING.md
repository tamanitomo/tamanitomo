# Tests

Install the application dependencies, then run the complete domain suite:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
```

The collected suites cover presence/settings/platform behavior, evidence
memory, outbox limits, vault files, journals/photos, floating chat, model
routing/probes, and the signals that must never invent anything (music, seasons,
missing-you, learned quiet hours, unknown meters). Fixtures use temporary homes and vaults; tests never operate on a
live companion. `tests/support.py` contains fixture helpers, not additional tests.
No legacy suites are hidden behind collection exclusions.

Run the source formatting checks with the development dependencies:

```sh
python -m pip install -r requirements-dev.txt
python -m black --check kit/scripts kit/cli kit/app launch.py update_release.py
python -m ruff check kit/scripts kit/cli kit/app
```

CI runs the full pytest suite on Linux, Windows and macOS. The Linux job also
checks installer syntax. Node is required for browser-script contract tests.

For a manual browser preview, use the synthetic fixture:

```sh
python tools/preview_fixture.py --port 38500
```

The command prints its local URL and temporary token. Its generated profiles,
notes and conversations contain invented data. They are removed when the preview
stops. Check at 390px and 1440px: all five destinations, auxiliary links, vault
editing, dock open/minimize/close, chat streaming, navigation during a reply,
reconnection and profile isolation. A real browser check is separate from pytest;
no browser download or live provider is needed for the fast suite.

## Multi-day continuity acceptance

Run the combined six-day synthetic scenario into a new evidence directory:

```sh
.venv/bin/python tools/check_continuity.py --output /tmp/tamanitomo-continuity-check
```

It advances a disposable companion through an evidence-backed shared project,
a promised calculation completed by an actual local Python process, a supported
rupture and repair, dated explained absence, independent fictional interests,
simulated provider outage and restart, and an owner-verified return on another
channel. Ten combined checks verify saved records, one-time completion, file
hashes, explanation retention, source separation and stranger exclusion. The
report includes five context snapshots and local operation receipts. This mode
makes no model calls and sends no messages. `tests/test_continuity_scenarios.py`
also exercises mocked transport failures, credential isolation and bounded runs.

For a bounded frontier dialogue review, supply the runtime and credentials
explicitly. This makes provider requests and normal usage applies:

```sh
.venv/bin/python tools/check_continuity.py \
  --output /tmp/tamanitomo-continuity-frontier \
  --frontier --runtime-python /path/to/hermes/python \
  --runtime-source /path/to/hermes-agent \
  --provider openai-codex --model YOUR_AVAILABLE_FRONTIER_MODEL \
  --auth-file /path/to/hermes/auth.json --max-turns 5
```

Only the supplied auth file is copied into a temporary private home. Existing
profiles, conversations, memories, plugins and provider `.env` files are not
loaded. The temporary auth copy is removed on exit. An audit guard rejects writes
outside the temporary home and child-process launches before Hermes imports.
The harness bypasses dependency installation, recovery and re-execution during
bootstrap because the interpreter is explicitly selected and already installed.
Each fresh Hermes turn has
no tools, at most 500 output tokens, one model iteration, low reasoning and a
120-second process limit. An unavailable provider stops the run; no unrelated
provider is tried. Recorded input/output usage stays unknown if Hermes does not
provide an authoritative usage anchor.

Review each reply against the rubric in `report.json`. A successful provider
response is not a quality verdict. These probes receive production continuity
context plus explicit local state/tool readouts from the scenario; they do not
certify autonomous tool selection, overnight scheduling, or external delivery.
Deterministic state checks and frontier availability are reported separately.

## Hermes compatibility

Run the integration seam checks against the selected installed Hermes source
and its interpreter:

```sh
.venv/bin/python tools/check_hermes_compatibility.py \
  --hermes-root /path/to/hermes-agent --python /path/to/hermes/python \
  --report /tmp/tamanitomo-hermes-compatibility.json
```

The check uses isolated synthetic profiles and makes no model calls or message
deliveries. The runner records the reviewed Hermes revision. The dedicated
`.github/workflows/hermes-compatibility.yml` workflow checks the pinned revision;
changing that revision requires another compatibility review. A locally passing
run does not establish that the newly authored workflow has run on GitHub.
