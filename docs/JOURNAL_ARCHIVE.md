# Journal archive: Day | Reflection

The first Journal consolidation slice. Journal is an archive of dates with two
views of the selected date. It reads existing records only; it does not write,
schedule, or call a model. Timeline remains as it was.

## What it reads

| Section | Source | Read by |
|---|---|---|
| Scenes | `companion-life/episodes/<date>.jsonl`, `imagined_episode` rows (presence snapshots and other recorded episodes) | `companion_life.read_events` |
| Photos | `image-timeline/captures/<id>.json` (saved captures) → catalog rows for their image files | `companion_timeline.records`, `content.catalog(reference_paths=…)` |
| Plan | `companion-life/plans/<date>.json` | `companion_plan.read_for` |
| Reflection | Nightly `Lifelog.md` entries and `continuity/archive/Lifelog-*.md` | `content.journals` (the existing reader) |
| You two | `companion-life/relationship.jsonl` moments | `companion_notes.moments` |

Routes (`kit/app/journal_archive.py`, request-scoped to the selected profile like every other `/api` route, token-checked by the existing middleware):

- `GET /api/journal/archive` lists the dates that have scenes and/or a reflection. The calendar uses it for markers.
- `GET /api/journal/archive/<YYYY-MM-DD>` returns that day's scenes, attached photos, unplaced photos, plan, reflection entries and shared moments, and a state for each source.

The Reflection view uses the existing `/api/journals` and `/api/journals/<id>` routes and draws the entry with the reader markup and `richText` renderer it used before.

## Dates

- The date is taken from the profile's configured timezone (`companion.json` `timezone`). A scene belongs to the date of its `recorded_at` instant in that timezone, not to the name of the file it sits in. The files for the dates either side are also read, so a row written just before midnight, or written while the profile had a different timezone, is placed by its instant.
- Across daylight-saving changes, instants are converted with `zoneinfo`: the missing spring hour and the repeated autumn hour both stay on their correct date. Scenes are ordered by their UTC instant, not by local wall time, so 01:10-05:00 after the fall-back follows 01:50-04:00 (J1).
- Date-only values stay dates. A journal heading (`## 2026-09-20`) and a moment's `happened_on` are compared as dates. A `recorded_at` value that is only a date, is naive, or does not parse gets no time: the row is kept only from the file named for that date and is shown as "Time not recorded", never given midnight or a guessed zone.
- Client-side date stepping uses calendar arithmetic in UTC (`journalAddDays`), so it cannot skip or repeat a day around a DST change. Invalid dates such as `2026-02-30` are refused by the route (400) and ignored in the address.

## Source association

- A photo reaches a scene only through the scene id its capture recorded when it was taken (`capture.scene.id`). The photo does not attach just because it shares the date or is close in time. Creations, album copies and other same-day images are not attached to scenes.
- A capture that says it was taken on this date, but whose scene id is not in the day's record, is listed separately as "Photos whose scene is no longer on record". It shows the capture's own recorded activity and is not moved onto a neighbouring scene.
- A capture whose image file is gone is counted as "no longer in the library". If the catalog hit its file-scan limit, photos are reported as `partial` and nothing is called missing.
- Adjacent snapshots with identical state (all fields except `transition`) and status collapse into one scene for display. The scene lists every id it covers, so a photo taken during any of them finds it. Stored history is not changed.
- Scene status keeps the source's meaning: `planned` and `skipped` episodes are labelled as such, a snapshot with `confirmed: false` is "Carried forward · unconfirmed", and everything else is "recorded". The plan file is shown under "Planned for this day" with the note that a plan is not a record of what happened.
- Scenes are shown with the episode's own provenance: they are the companion's account of its day, not a record of the owner. Nothing in a scene, including text such as "coffee with Alex", produces a shared moment.
- The "You two" section appears only when a relationship moment has `happened_on` equal to the selected date. A moment's recording date is not treated as its event date, and free-text dates ("last spring") are not interpreted. Otherwise the section is left out.
- The reflection excerpt on the Day view is the existing entry's own excerpt. No summary is generated.

## Empty and unavailable states

Each source reports `available`, `none` (nothing on record), `empty` (the day's file exists but holds no scenes), `unavailable` (present but could not be read: an unreadable or linked episode file, a corrupt capture record, a linked plan or relationship file) or, for photos, `partial`. The page shows the matching sentence:

- "No scenes were recorded on this day." or "Nothing on record for this day" when there is truly nothing. A future date says it has not happened yet.
- "This day's scene record could not be read. It has not been changed; refresh to try again…" for an unreadable source.
- Reflection: "No reflection saved for this day" (with the nearest older/newer reflection and a link to the Day view) is kept apart from "The reflection could not be read" (a journal file failed to read, so an entry may exist). A new profile gets the existing "No journal entries yet" state.

## Navigation and compatibility

- Address: `#journals/<date>/<day|reflection>`. It can be shared and survives a refresh. Bare `#journals` still opens where it did before, on the latest reflection or, with no reflections, today's Day view. It also remembers the last date/view chosen in this page session.
- Choosing a date or view pushes a history entry and `popstate` replays it, so back/forward move between chosen dates. Tab switches still replace the address, as they always have. `showTab` keeps a page's own sub-route when that page is the one shown, and the boot code reads the tab from the first path segment.
- Home ("Read … journal") and Timeline ("Read her diary for this day") still set `selectedJournal`. Journal treats that as a one-time request and opens that entry's date in Reflection.
- Controls: a Day/Reflection tab pair (`role=tablist`, arrow keys switch), Older/Newer buttons that step to the nearest date on record (in Reflection, the nearest reflection), and the existing date panel. The panel now has a date input, Today, Latest reflection, reflection search, and a calendar where every date can be chosen and dates with reflections or scenes are marked.
- Stale answers: each request carries a token, and results are drawn only if the same date, view, installation and profile are still selected. The opening route is read after Journal's initial list and index arrive, so a date chosen while they were pending stands (J2).
- Timeline's handler, `#timeline` route, navigation entries and saved `nav_pins` are unchanged. No preference or data migration.

## What remains in Timeline (not yet in Journal)

Before Timeline can be retired, a later decision needs:

1. A multi-day stream. Timeline scrolls 12 days per page with "Show earlier days". Journal shows one date at a time.
2. Scene/place search and the "only days with photos" filter. Journal's search covers reflections only.
3. Photos not tied to a capture. Timeline places every gallery image, including creations and album copies, into the scene before it by time. Journal deliberately does not, so those images are reachable only through Photos and the Reflection view's existing "pictures from this day" strip.
4. The live "Now" marker and open-ended duration on today's current scene.
5. Different collapse rules. Timeline merges by activity and place. Journal merges by the full state, so a mood change starts a new scene.
6. A Timeline→Journal alias (`TAB_ALIASES`) and a `nav_pins` migration, plus navigation copy changes.

## Not in this slice

No events, unread state, notifications, vault editing, reflection scheduling, model calls, new editor, UI framework, or Timeline retirement. Keyed activation and the Phase 1C continuity options stay OFF. N1/N2 (Phase 1C) are unchanged.
