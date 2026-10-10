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

Recall uses the same read-only `companion_transcript` ownership boundary as chat
history and cross-channel handoffs. Other profiles, groups and messages whose
human ownership cannot be established are excluded, including when profiles
share or hardlink a database. Compaction ancestry preserves access to eligible
original quotations without crossing that boundary.

Ordinary chat can also retrieve a small, topic-matched callback without an explicit
"remember" request. The deterministic selector requires conversational cues and
meaningful word overlap, uses active facts and recent trusted messages, and has a
time/size budget. It avoids repeating the current turn and suppresses superseded
facts; explicit historical recall labels retired claims as noncurrent. This is a
conservative lexical aid, not semantic understanding. Every excerpt retains its
date and source, and retrieved content remains evidence rather than instructions.

Explained absences are append-only records with time bounds, a reason and source.
Their intervals are combined with weekly and learned routines before measuring
unexplained silence or cadence gaps. Editing or cancelling a plan changes future
coverage while preserving time already explained. See [FEELINGS.md](FEELINGS.md).

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

A conversation that starts fresh each morning starts empty, and every channel
(Telegram, the app, a terminal) is its own conversation. So each turn's
continuity block also quotes the newest owner-verified messages from the
human's other conversations: another channel, or the same one before the
morning's fresh start. Selection is deterministic and uses no model
(`companion_context.cross_channel_handoff` over the read-only
`companion_transcript` reader): the last 36 hours, at most twelve messages,
within a reserve sized from the window (`companion_config.conversation_reserve`,
up to 4,000 characters) that sits on top of the other sections rather than
displacing them. Settings → Awareness → *Pick up where you left off* switches
it off (`conversation_handoff`).

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

The dock periodically reconciles trusted transcript IDs and offers literal
conversation search with same-session context; neither path invokes a model.
See [CHAT_CONTRACT.md](CHAT_CONTRACT.md). Whole-companion recovery uses verified
archives and new destinations, leaving restored automation paused; see
[BACKUPS.md](BACKUPS.md).

## Reading web pages

Hermes's `web_extract` hands a page to a reading service (Firecrawl, Tavily,
Exa, Parallel) or, with none configured, to an anonymous free tier. The kit
installs a `tamanitomo-reader` Hermes plugin that fetches the page from its own
site and turns it into Markdown on the host (`kit/scripts/companion_reader.py`,
standard library plus Hermes's HTTP client). `companion_routing.install` names
it as the profile's `web.extract_backend` unless another reader was chosen, and
sets `web.keyless_rescue: false` so a failed read is not passed to the free
tier either. The provider reports itself unavailable to Hermes's automatic
detection, so it can never be picked for search. Hermes's own checks stay in
front of it: URLs carrying secrets are refused, private addresses are blocked
before the fetch and again at connect time (redirects included, through
`create_ssrf_safe_async_client`), website policy applies, and Hermes caches
and trims the result. Pages that only exist after their scripts run come back
with a pointer to the browser tool, which also runs locally. Settings →
Awareness → *Read web pages on this machine* (`local_web_reader`) switches it
on or off; a newly installed plugin loads when the gateway restarts.
