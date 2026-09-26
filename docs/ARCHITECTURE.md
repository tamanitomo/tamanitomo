# Architectural boundaries

Tamanitomo is a single-user companion workspace. Hermes owns conversations;
the profile and vault keep ordinary files that remain usable outside the app.
Code enforces limits and storage rules; language models propose content within
those rules.

## Deterministic boundaries

Quiet hours and daily outreach slots are enforced by `companion_outreach.py`
and `companion_dispatch.py`. Delivery checks the configured clock and policy,
then reserves a slot under a file lock before sending. High-priority messages
or recent recorded human activity can permit delivery during quiet hours, but
cannot raise the configured daily cap. A cap of zero explicitly means unlimited.
Failed or uncertain sends keep their slot and are not automatically repeated.
These guarantees cover the supported delivery helpers, not arbitrary tools a
separate agent may invoke.

`companion_presence.py` validates wardrobe IDs, explicit virtual tokens such as
`bathing` or `towel`, outfit size, coverage and public/private declarations.
It checks the previous episode ID under a lock before recording a transition.
A fluent sentence cannot override an invalid state or a stale update. This is
why these rules live in Python rather than only in SOUL instructions: model
changes, inference fallback and concurrent jobs must preserve the same limits.

## Evidence-backed memory

`companion_self.py` stores human claims in `facts.jsonl`, with evidence and
source kept alongside the statement. The companion's own preferences and
questions use separate ledgers. Corrections append records; they do not erase
the original claim or its provenance.

Structured reflection in `companion_local_reflection.py` selects trusted human
transcript quotes by ID. Code writes the verbatim quotation and source citation,
while the model's readable statement is stored separately as a paraphrase.
Obvious mismatches are held for review. The screen is not proof that every
accepted paraphrase is correct. Direct fact-writing callers must provide
substantive evidence, but the low-level ledger writer cannot authenticate an
arbitrary supplied quotation.

Retrieval may locate a useful candidate; it does not establish truth. Keeping
the original quotation makes a memory inspectable and correctable instead of
allowing an embedding match or an invented recollection to become authority.
Memory maintenance archives complete entries without model calls and preserves
originals during interrupted writes.

## Zero-LLM maintenance

`kit/templates/cron/manifest.json` marks these six maintenance routines
`no_agent`; `kit/cli/scaffold.py` installs Python wrappers using
`--script --no-agent`:

| Job key | Helper | Work |
| --- | --- | --- |
| `timeline_cleanup` | `companion_timeline prune` | Prune old timeline images to the configured budget |
| `watch` | `companion_watch` | Check job health and issue bounded operational alerts |
| `dispatch` | `companion_dispatch` | Deliver an already-written, eligible outbox message |
| `sensors` | `companion_sensors` | Read configured sensors into local context files |
| `quiet` | `companion_quiet --apply` | Apply opted-in, evidence-based quiet-hour adjustments |
| `vault` | `companion_vault commit` | Commit changes to the vault's local Git repository |

The manifest also contains `rollover`, a seventh no-agent job for session
lifecycle. It preserves transcripts and flags reflection work; the later
reflection is a separate inference job. Profile type and optional settings
control which jobs are installed.

These jobs need no language-model completion. They can maintain records and
enforce policy during provider outages without paying for an agent turn that
only checks a clock or moves a file. They still depend on the files, devices,
transport or network services their individual tasks require.

## Interactive chat

The floating dock is the only chat surface. `POST /api/chat` streams the
`runtime.py` / `hermes_stream.py` bridge over server-sent events. Hermes keeps
the transcript; the browser keeps a draft, a session reference and the current
operation ID for reconnecting. Checking an interrupted operation does not
resubmit the message. Profile scope is captured for each request so a late
response cannot write into another companion's view or draft.
