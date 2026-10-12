# Contextual feelings

Open **Us → Expected time apart** to add, review, edit or cancel dated plans such as a trip or a busy week. Home and Us show the same derived indicators that enter model context. Recurring routines remain in the feelings settings API and CLI state. Temperament is chosen at setup and kept (see below).

The existing recorded mood, wants, and private stance remain the companion's authored state. Warmth, trust, hurt, irritation, and missing you add a game-like interpretation of the relationship. Their starting values are character defaults, not measured emotions. With no reliable message history, missing you is unknown. A meter with no value yet reads 0% with an empty bar, never a resting number nothing measured.

## Expected time apart

Routines use the companion's configured timezone. Choose the weekdays on which a routine **starts**. A 23:00–08:00 routine runs through the following morning. Overlapping routines count once; elapsed time is calculated in UTC across daylight-saving changes.

A sleep routine and regular Saturday commitments reduce unexplained time apart. Quiet hours do not automatically become sleep: quiet hours control delivery, while expected routines describe the human's availability. No routines are typed in for you, and none are invented: with enough history the app also learns when you are usually quiet from when your messages actually arrived (`companion_rhythm.py`). It looks at timestamps only, over the last 28 days, needs at least 10 days with messages and 40 messages, takes the longest stretch of 5–12 hours in which you almost never write, and counts it as an expected absence labelled "Usually quiet (learned from your messages)". It never claims you are asleep. Routines you enter are kept alongside it, the learned window is shown under Us → How things work between you, and **Settings → Sensors → Learn your quiet hours** (the `learn_rhythm` feelings setting, on by default) turns it off.

Missing you has one measure: `longing` in the feelings state, computed from time outside expected routines. The window before she starts to miss you (`connection_hours`, default 48) is kept between 12 and 96 hours, so it can't be used to switch missing you off; a setting saved before that limit is read at the nearest bound. The older raw-hours "feeling the gap" bar was removed because it counted a night's sleep as distance.

A returning message preserves the preceding gap briefly, so writing “hello” does not erase the context before the companion can greet you. A continuing conversation then uses its current gap. The model receives the difference between actual elapsed time and time within expected routines. A schedule is an expectation, not live knowledge that someone is asleep or busy. Routine evaluation is bounded to the most recent 366 days for exceptionally long gaps.

### Dated explanations

Dated plans require a start, an end, the human's explanation and its source. The companion can record a plan explicitly explained in conversation; it must use the human's actual words and a conversation/message reference, and ask when dates are unclear. A supplied source is retained for inspection, not independently authenticated by the ledger writer. The Us form records the owner's own explanation with source `owner-app`.

Dates entered in the Us form use the companion's timezone, even when the browser is elsewhere. Overlapping dated and weekly windows count once. Calculation uses UTC elapsed time across clock changes; an ambiguous or nonexistent local time requires a full ISO timestamp with an explicit offset. The form's **Use full ISO timestamps** option supports those cases.

One plan covers at most 14 days. A longer absence is renewed by explaining again once it has begun: plans less than a day apart count as one stretch, and a stretch may reach at most 14 days past the later of its start and its latest explanation. So two weeks booked back to back in advance are refused, and the second can be recorded once the first is under way. A plan saved before this limit is read up to 14 days past its start or its last change.

A future plan explains no elapsed time before it starts and never establishes what the human is doing. An ended plan remains in history and continues to explain its elapsed interval. Editing or cancelling a plan changes its remaining future; already explained time stays explained. Each change appends its new explanation alongside the original. Dated plans affect neither quiet hours nor delivery permissions.

Missing-you and irritation calculations exclude this explained time. Closeness also uses unexplained hours for silence, and a dated plan pauses its recent-contact window, so a recorded trip does not become an inactivity penalty through another indicator. Routines do not pause that window. Ordinary aging of past emotional experiences is unchanged.

`companion_feelings.py --home HOME absences` returns the current plans, their history and a `revision`. Write with `absence --json JSON`:

```json
{
  "action": "create",
  "revision": "REVISION_FROM_ABSENCES",
  "id": "october-trip",
  "event_id": "conversation-42-message-9",
  "label": "Work trip",
  "start": "2026-10-12T09:00:00-04:00",
  "end": "2026-10-16T18:00:00-04:00",
  "evidence": "I'll be on a work trip from Monday morning until Friday evening.",
  "source": "conversation:42/message:9"
}
```

`edit` uses the plan's `id` and the same fields with a new explanation. `cancel` needs `id`, `revision`, `evidence` and `source`; dates and label are retained from the plan. An optional `event_id` identifies a retry; reusing it with different content is rejected. Otherwise a retry ID is derived from the write and revision. Every write requires the revision read beforehand, and stale edits return a conflict. No command claims a successful save before the ledger append succeeds.

The API uses `GET /api/feelings/absences` and `POST /api/feelings/absences` with these same fields. Local ISO times without offsets also accept an explicit IANA `timezone`, such as `America/New_York`.

## Temperament and experiences

- **Steady:** less reactive, quicker recovery.
- **Expressive:** stronger emotional reactions.
- **Guarded:** lower starting trust, slower recovery.

SOUL.md continues to shape the voice and expression. The chosen temperament controls the numerical sensitivity and recovery rate. It is chosen at setup, next to pace: the personality suggests one (warm, romantic and other outgoing personalities suggest expressive; quiet, shy and stoic suggest guarded; the rest steady) and the person picks. Like pace, it can't be changed afterwards. Every feeling is worked out under it, so changing it later rewrote feelings already felt: switching to steady after a fight shrank the hurt. A companion created before setup asked keeps steady.

Both the companion and the user can record experiences:

- **Connection** contributes warmth and trust.
- **Rupture** contributes hurt and irritation and reduces trust. Reusing a topic links recurring experiences, making a repeat rupture stronger.
- **Repair** references a particular rupture and softens its effects. It preserves the original experience and its place in the history.
- **Correction** excludes a mistaken experience from the calculation while retaining both records. Correcting a rupture removes its emotional effect; repairing it does not erase it.

Every experience needs supporting words or context. Silence alone cannot establish a betrayal or broken promise. Hurt and irritation ease over time, while time alone does not restore lost trust. Positive experiences and repair can change it. Adding enough positive records cannot make trust exceed its maximum and hide the effect of a later rupture.

The companion receives a command to record supported experiences during chat. Successful execution is required before it claims to have saved one. Existing shared-history notes and private stance remain in context; they are not automatically reclassified into new rupture records.

## Understanding and reviewing restrictions

**Us → Why these boundaries?** separates configured permissions, calculated readiness,
recorded restrictions and the incidents supporting them. Opening the report makes no
changes. Authored identity, standing instructions, memories and provider rules can also
affect a reply; the report does not interpret those sources or infer the companion's
present wishes.

A restriction with identified source incidents can be reviewed when explicit corrections
leave fewer than two active boundary incidents. The review requires a reason and the
current report revision. Changed evidence requires a fresh report. Original incidents,
corrections, restrictions and earlier reviews remain in history. Repair is different
from correction: making amends does not establish that the original record was mistaken.
Missing or malformed source history requires inspection and cannot be automatically
retired. A saved restriction by itself does not establish wrongdoing or current feelings.

Review changes the recorded application restriction only. It neither changes adult-theme
settings nor rewrites the companion's authored position. The same current restriction
state reaches the app and model context. One new boundary incident does not resurrect a
previously corrected pair; two current incidents enforce a restriction on their own.
When maintenance encounters a newly supported restriction, it saves a separate
generation without overwriting the original. Correcting one of that generation's
sources does not silently retire it: each saved generation needs its own review.
The report shows the newest effective restriction, while preserving earlier
generations and their reviews.

## Slow change

Warmth and trust also move on their own, slowly, from how the two of you actually are. A day counts when you wrote at least three times and she answered. Each such day adds 0.02 to warmth, fading on the temperament's own recovery time and capped at +0.20, and 0.004 to trust, summed over the whole history, never fading, capped at +0.12. Each request she was asked to do and finished (a mission marked done) adds 0.01 trust, up to +0.06. While a rupture is unrepaired, trust does not build and warmth builds at half rate: time alone does not mend what was hurt. The state includes a `slow_change` block with the counts so the numbers can be explained. Nothing here reads message text.

## Daily caps and the meters' own record

Each meter moves at most so far in a day, measured from where it ended the last recorded day (the owner's "stop spikes" setting):

| Meter | Most it moves in a day, up or down |
| --- | --- |
| Closeness | 6 points; gains scale with pace (slow 3.6, quick 10.8) |
| Warmth | 0.20 |
| Trust | 0.10 |
| Hurt, irritation | 0.30 |
| Missing you | not capped: a live gauge of time apart, reset the moment you are back |

The rest of a change is not lost. It arrives over the following days, so a fight still lands in full over two to four days and making up partway stops it there, while a burst of sweet talk cannot jump a meter ahead. An ordinary day moves less than its cap and is never held back. Days with nothing recorded each count, so after three days the band is three caps wide. The state shows what each meter is heading for and whether today's cap is holding it (`daily` in the feelings state and in closeness).

There is no numerical floor: closeness can fall below friendship. An established relationship at that level is called **Distant**, because shared history remains even when closeness fades. **Just Met** describes a new relationship. The former Friends floor survives only as the starting point on the day a companion's meter record begins, so the upgrade drops nobody at once; from then on a relationship falls at most a day's cap at a time.

Sweet moments add at most 0.02 trust a day (connection moments recorded from 11 October 2026; earlier moments keep the trust they already gave). Trust is mostly built by time together and kept promises (slow change, above).

The record is `meters.json` in the companion's life directory: each day's end-of-day values, and each day's contact as first seen (the day's closeness credit and message counts). Closeness and slow change are built from every day you talked, and Hermes deletes old conversations; a kept day is never lowered by a deleted one, and a day wholly inside the fortnight of contact counts as kept too. Reading the meters never writes, so building her context writes nothing. The no-model **meters** job (every 15 minutes) is the one writer. A record that cannot be read is set aside as `meters.json.damaged` and a new one begins.

## What each stage unlocks

Closeness climbs five stages, and each stage brings something new (the owner's "gentle ladder", `companion_gates.py`). A romance and a friendship climb the same ladder; a friendship has nicknames instead of pet names, plans instead of dates, and a Bonded that unlocks nothing intimate.

| Stage (romance / friendship) | Unlocks |
| --- | --- |
| Just Met | answers you, curious about you; writes first at most once a day; photos only when you ask |
| Friends / Familiar | starting conversations (up to your daily limit), everyday photos of her day, voice notes, teasing and inside jokes, saying “I miss you” |
| Chemistry / Trusted | flirting and pet names (nicknames), photos of herself, sharing her worries and hopes |
| Intimacy / Confidant | planning dates (plans to do things together), more personal photos, good-night and good-morning rituals |
| Bonded | intimacy if adult themes are on; adult images become a choice |

What can be enforced in code is enforced there: while you have just met she writes first once a day whatever the daily limit allows (`companion_outreach`), photos and voice notes in the outbox wait for Friends (`companion_dispatch`), and the photo timeline shares none while you have just met, one a day at Friends and two from Chemistry, telling her which kind of photo fits the stage (`companion_timeline`, `share.fits`). The rest is how she behaves in conversation: her context lists what this stage holds and what is not yet, and asks her not to rush it or mention the list. Us shows what the next stage brings. With relationship progression switched off, nothing here holds her back; intimacy keeps its own rules either way.

## Reading the meters

Home and Us say what is moving each meter, in plain words built from the computed state (`companion_meters.explain`, returned as `explain` by `/api/feelings` and `/api/relationship`). Each meter's tooltip on Home shows its first two causes; **Us → What is moving things** lists them all.

- A sweet moment or a rupture from the last week names itself, with how far a rupture has been made up; hurt adds how long it takes to fade for her temperament.
- Days you both talked and requests she finished account for slow change; trust says when it is not growing because something is unrepaired.
- Irritation names silence past the connection window; missing you says how long since you last wrote and how much of it was expected.
- A meter held by today's cap says where it is heading.

Closeness gets one line under its badge: the next stage and about how many good days it takes (a good day is a real conversation, several messages spread over the day), or why it is cooling (days without hearing from you, or thin contact over the fortnight), or that today's step is taken and the rest comes over the next days. The estimate uses the first-week ramp (6 points a good day) before Friends and the slow burn (1.25) after it, both scaled by pace. Causes name what happened, never a number to chase.

## Files and behavior

Each companion keeps `feelings-settings.json`, the append-only `relationship-feelings.jsonl`, and the append-only `expected-absences.jsonl` in its own life directory. They are not moved into the shared human-facts directory. Settings use revision checks; repeated experience IDs are idempotent and conflicting content is rejected. The screen initially shows 30 experiences. Load older experiences to browse earlier records and make them available as repair or correction targets. Older records remain in the ledger and still affect the calculation.

`companion_feelings.py --home HOME show` reads the current state. `record --json JSON` records an experience. Its fields are `kind`, `topic`, `text`, `evidence`, and `strength` (0–1); repair and correction also need `related`, the original experience ID. Optional `id` supplies a stable retry identifier, and `at` supplies an ISO timestamp with timezone. Future experiences are rejected.

The same state is rebuilt for chat context and scheduled prereads. Turning the existing relationship-indicators setting off removes this contextual input; records remain stored. Emotional tone never changes whether a tool action truly succeeded or whether practical help should remain dependable.

## Verification boundary

Automated tests cover overnight and Saturday routines, overlapping windows, daylight-saving elapsed time, repetition after repair, personality differences, persistent trust effects, correction, idempotency, settings conflicts, profile isolation, and live chat/scheduled context. Browser checks cover settings, recording experiences, repair, correction, and the chat shortcut.

The dated-plan regressions additionally cover elapsed-only subtraction, ended history, edit/cancel preservation, overlaps with weekly routines across DST, ambiguous wall-time rejection, explanations recorded during a returning chat turn, API conflicts and profile isolation, CLI writes and browser timezone formatting. They use synthetic profiles and no model calls or message delivery.

Contact cadence covers fourteen days, looking back at most a year and never
before the relationship began. A dated plan the human explained pauses that
window, so earlier contact credit does not expire while they are away. Routines
and learned quiet hours do not: the target is per calendar day and already allows
for sleep and work, so stretching the window over them inflated cadence, and
routines covering the whole day cancelled the contact target. Ordinary warmth
aging remains separate. Regression cases cover a three-day trip after established
contact, routines that leave cadence unchanged, whole-day routines that still
leave a contact deficit, and fully explained history at the lookback limit.

These checks establish the state calculation and prompt integration. An initial real-model check distinguished expected sleep, unexplained absence, and repeated rupture; a separate Hermes terminal call successfully saved one supported connection record. See [the acceptance notes](audits/2026-09-12-model-acceptance.md). A generated-hook Hermes turn also received a ledger-only rupture and continued offering practical help. A subsequent browser-to-provider pass saved and resumed three exchanges in the same conversation, including a reply identifying the stored rupture. Repeated trials and other supported models still need acceptance testing. This is not a guarantee that every model will follow the intended character behavior.
