# Contextual feelings

Open **Together → Feelings & expected routines** to choose a temperament and add the human's normal sleep or busy periods. Chat links to this page beneath the companion's name. Home and Together show the same derived indicators that enter model context.

The existing recorded mood, wants, and private stance remain the companion's authored state. Warmth, trust, hurt, irritation, and missing you add a game-like interpretation of the relationship. Their starting values are character defaults, not measured emotions. With no reliable message history, missing you is unknown.

## Expected time apart

Routines use the companion's configured timezone. Choose the weekdays on which a routine **starts**. A 23:00–08:00 routine runs through the following morning. Overlapping routines count once; elapsed time is calculated in UTC across daylight-saving changes.

A sleep routine and regular Saturday commitments reduce unexplained time apart. Quiet hours do not automatically become sleep: quiet hours control delivery, while expected routines describe the human's availability. No routines are invented by default.

A returning message preserves the preceding gap briefly, so writing “hello” does not erase the context before the companion can greet you. A continuing conversation then uses its current gap. The model receives the difference between actual elapsed time and time within expected routines. A schedule is an expectation, not live knowledge that someone is asleep or busy. Routine evaluation is bounded to the most recent 366 days for exceptionally long gaps.

## Temperament and experiences

- **Steady:** less reactive, quicker recovery.
- **Expressive:** stronger emotional reactions.
- **Guarded:** lower starting trust, slower recovery.

SOUL.md continues to shape the voice and expression. The chosen temperament controls the numerical sensitivity and recovery rate. It is configurable rather than inferred by keyword matching against the personality document.

Both the companion and the user can record experiences:

- **Connection** contributes warmth and trust.
- **Rupture** contributes hurt and irritation and reduces trust. Reusing a topic links recurring experiences, making a repeat rupture stronger.
- **Repair** references a particular rupture and softens its effects. It preserves the original experience and its place in the history.
- **Correction** excludes a mistaken experience from the calculation while retaining both records. Correcting a rupture removes its emotional effect; repairing it does not erase it.

Every experience needs supporting words or context. Silence alone cannot establish a betrayal or broken promise. Hurt and irritation ease over time, while time alone does not restore lost trust. Positive experiences and repair can change it. Adding enough positive records cannot make trust exceed its maximum and hide the effect of a later rupture.

The companion receives a command to record supported experiences during chat. Successful execution is required before it claims to have saved one. Existing shared-history notes and private stance remain in context; they are not automatically reclassified into new rupture records.

## Files and behavior

Each companion keeps `feelings-settings.json` and the append-only `relationship-feelings.jsonl` in its own life directory. They are not moved into the shared human-facts directory. Settings use revision checks; repeated experience IDs are idempotent and conflicting content is rejected. The screen initially shows 30 experiences. Load older experiences to browse earlier records and make them available as repair or correction targets. Older records remain in the ledger and still affect the calculation.

`companion_feelings.py --home HOME show` reads the current state. `record --json JSON` records an experience. Its fields are `kind`, `topic`, `text`, `evidence`, and `strength` (0–1); repair and correction also need `related`, the original experience ID. Optional `id` supplies a stable retry identifier, and `at` supplies an ISO timestamp with timezone. Future experiences are rejected.

The same state is rebuilt for chat context and scheduled prereads. Turning the existing relationship-indicators setting off removes this contextual input; records remain stored. Emotional tone never changes whether a tool action truly succeeded or whether practical help should remain dependable.

## Verification boundary

Automated tests cover overnight and Saturday routines, overlapping windows, daylight-saving elapsed time, repetition after repair, personality differences, persistent trust effects, correction, idempotency, settings conflicts, profile isolation, and live chat/scheduled context. Browser checks cover settings, recording experiences, repair, correction, and the chat shortcut.

These checks establish the state calculation and prompt integration. An initial real-model check distinguished expected sleep, unexplained absence, and repeated rupture; a separate Hermes terminal call successfully saved one supported connection record. See [the acceptance notes](audits/2026-09-12-model-acceptance.md). A generated-hook Hermes turn also received a ledger-only rupture and continued offering practical help. A subsequent browser-to-provider pass saved and resumed three exchanges in the same conversation, including a reply identifying the stored rupture. Repeated trials and other supported models still need acceptance testing. This is not a guarantee that every model will follow the intended character behavior.
