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

## Self-development acceptance

Run the focused five-day scenario into a new disposable evidence directory:

```sh
.venv/bin/python tools/check_self_development.py \
  --output /tmp/tamanitomo-self-development
```

It creates only a synthetic profile below that new directory, keeps outreach off,
and makes no model or network calls. The saved report, literal encounter input,
reflection input, append-only ledgers and created fictional artifact demonstrate:
stable source lineage and structural deduplication; an encounter becoming an
interpretation and provisional view; relevant chat/planning selection after
unrelated growth and restart; consideration of an opposite human preference without
automatic adoption; a linked making investigation and project result; later nuance
informed by the real saved artifact; an outage retained as an obstacle; complete
revision history; and read-only inspection. The deterministic adapter authors the
project action, so this is a plumbing guarantee rather than behavioral acceptance.

The automated cases additionally cover stale and concurrent revisions, conflicting
operation IDs, cross-profile targets, malformed ledgers, legacy preference/question/
arc loading, corrected/unavailable support, fiction and metadata boundaries,
artifact traversal/symlink escape and later disappearance, compact selection,
reflection-plan replay, autonomy due edges, API current/history separation and stored
prose escaping.

For bounded frontier dialogue, explicitly select the already installed runtime,
provider, model and an authentication file:

```sh
.venv/bin/python tools/check_self_development.py \
  --output /tmp/tamanitomo-self-development-frontier \
  --frontier --runtime-python /path/to/hermes/python \
  --runtime-source /path/to/hermes-agent \
  --provider openai-codex --model YOUR_AVAILABLE_FRONTIER_MODEL \
  --auth-file /path/to/hermes/auth.json
```

The authentication file is copied into a private synthetic home and the copy is
removed afterward. Existing profiles, memories and `.env` files are not loaded;
tools and fallback providers are disabled. The four fresh-turn rubrics assess
coherent reasons, uncertainty, continuity after restart, independence, response to
an opposite preference, and natural reconsideration after a creative result. A
transport success is not a behavioral pass: review every reply. The choice turn can
show natural selection among constrained options but, with tools disabled, does not
certify autonomous tool execution. If provider resolution or authentication fails,
report frontier acceptance as blocked with input/output usage unknown rather than
substituting deterministic checks.

The October 12 self-development acceptance run used the configured frontier route
`xai-oauth/grok-4.20-0309-non-reasoning`. Its final four-turn evidence run completed
with 14,188 input and 285 output tokens. Qualitative review found that the companion
retained a provisional view after restart, considered an opposite preference without
adopting it, chose the connected bounded writing step without claiming it was already
done, and later used the saved fictional result while leaving its pending reread
pending. The human-facing replies stayed natural. The private action-selection reply
still used the internal word “arc”; that is a presentation limitation in this
tool-free planning probe, not deterministic proof of autonomous execution.

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

## Relationship restriction review validation

The synthetic suite covers corrected source records, stale and cross-profile
review revisions, malformed history, read-only inspection, and later restriction
generations. A later saved restriction requires its own explicit review after a
source correction; the original record and earlier reviews remain intact. Tests
also verify that a saved restriction does not invent wrongdoing, current feelings
or consent, and that invitations do not become agreements without acceptance.

The complete local run passed **1,036 tests and 50 subtests**. Its one optional
real-Hermes integration check passed separately using the explicitly selected
runtime and disposable synthetic profile. CI Black/Ruff checks and installer
shell syntax checks passed. Synthetic browser inspection of the review flow and
the self-development current/history, empty-profile and mobile surfaces passed.
Profile switching kept those views isolated and preserved an unsent draft;
opening a report did not change records.

The bounded `openai-codex` behavior check stopped during provider resolution:
the privately copied authentication token could not be refreshed because it had
already been consumed by another client. No model request started, no fallback or
retry was attempted, and the remaining case was not run. Input/output usage is
unknown, not zero. The temporary profile and authentication copy were removed.
This is a provider-availability limitation, not a behavioral acceptance pass.
