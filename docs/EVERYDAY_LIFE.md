# Clothing care and daily life

Companion setup seeds 27 pieces: three pajama sets, sports bras, training leggings,
day tops and trousers, underwear and socks, plus a cardigan, walking trainers, jeans, denim shorts, an occasion outfit and swimwear.
Existing items, identity and routine preferences remain. For an existing companion:

```sh
.venv/bin/python kit/scripts/companion_lifestyle.py --home /path/to/hermes seed
```

Use `--palette muted` for charcoal, forest green and dusty plum; the default is sage,
dusty blue and cream. These are initial fictional possessions, not purchases.
Daily anchors cover getting ready, meals, time outside, interests, laundry and bedtime.
Edit `routine.json` to change the rhythm. Weekly plans take priority over broad daily
suggestions. The model chooses concrete activities and can explain a changed plan;
the clock never claims that something happened. Enjoyment is authored, not enforced.

The opt-in `lifestyle.enabled` policy lives in `routine.json`. Care and availability
are stored in each episode, atomically with presence. Previously worn existing items
start in the hamper, except those currently being worn. This is a conservative
migration, not a claim to have reconstructed every past laundry cycle. Old history
is preserved. Freshly seeded items start clean. `condition` describes a garment;
episode `lifestyle.clothes` is the authority on whether it is available to wear.

Presence updates may include ordered `care_actions` and `wardrobe_additions`:

```json
{
  "care_actions": [
    {"kind": "brush_teeth", "items": []},
    {"kind": "shower", "items": []}
  ],
  "wardrobe_additions": []
}
```

These fields accompany the usual outfit, activity, location, previous_id, transition,
text and other presence fields. Actions describe newly completed fictional actions;
do not copy the previous record's actions. The final outfit is put on after them.
Brushing teeth requires two elapsed minutes and a shower ten. Fresh clothes require
teeth brushed on the current local date. New pajamas also require a shower within
two hours. Clothes may remain on through sleep/midnight, but washable items must be
changed within 24 hours. Taking them off makes them dirty. Footwear is reusable.

`laundry_start` lists worn items that are no longer in the final outfit. A later
`laundry_finish` must list exactly that load, at least 90 minutes after its start.
Each handling action requires five elapsed minutes. Only finishing makes the pieces
clean. The no-model advancer cannot wash clothes, complete care or go shopping.

A fictional shopping opportunity is offered every 14 days, beginning 14 days after
seeding. A `shop` action requires ten elapsed minutes and optionally adds up to three
pieces through `wardrobe_additions`, each with a unique `id`, `description`, `use`,
`category` (day, active, sleep, underwear, outerwear or footwear), and `condition: clean`.
Acquisitions are committed in the episode; `wardrobe`/`show` include them immediately.
No actual purchase or external message occurs. Declining an opportunity is fine.

For every active routine, supply `routine_choice: {anchor: "daily-1", decision: "follow", reason: "..."}`
using the supplied anchor ID. `defer` requires a concrete reason and alternative. When no anchor
is active, use `decision: "free"`. An overdue continuation also requires an explicit `delay_reason`;
silently increasing the duration estimate is rejected. These decisions are preserved in the episode.

Daily routine, clothing availability and instructions reach both agent jobs and the
local structured pulse. The local worker retries one invalid care/plan proposal.
A second failure preserves the last state and reports the error. Chat receives a
pointer to the full care rules and state. `activity_change: continue` preserves the
activity start time when wording changes; `transition` starts a new activity. An
elapsed estimate triggers reconsideration guidance rather than invented completion.

These checks validate record consistency. They do not establish physical events or
guarantee that a model will follow a varied routine over multiple days.


## Independent life and continuity

Pulse, autonomy, morning and wind-down maintain one continuing fictional life.
The companion can stay occupied with a project or recurring fictional friends
when the human returns, and respond warmly without dropping every commitment.
Human absence is ordinary, not abandonment or a reason to wait for a message.

Suggestions are invitations with varied activity tags; repeating an enjoyed hobby
is allowed. The pre-read includes the companion's own retained interests and
progress notes as well as rotating ideas and recurring people with their IDs.
`companion_life.py add-idea --title "same title" --note "progress; next step"`
updates an ongoing idea. The work window invites creating, practicing, developing
projects and researching specific questions instead of defaulting to reading.

Fictional episodes never prove real outings, actual tool use or facts about the
human. Research needs returned sources; creations need saved artifacts. Daily
contact checks and quiet-hours learning use the same trusted, profile-scoped
owner transcripts as memory, excluding cron prompts and unknown participants.
Unsupported transcript sources remain unknown rather than being guessed.

Sleep flags without a declared end periodically reopen the pulse gate to recover
from a missed wake-up. A real activity transition clears sleep unless explicitly
marked asleep. Continuing a private scene preserves its camera privacy.

Existing authored routines are retained. Repair can refresh untouched shipped
prompts while preserving edited prompts; inspect its report for custom text that
needs a manual reconciliation. Updating source does not rewrite live life history.
