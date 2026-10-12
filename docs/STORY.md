# Her story, and what she can notice

Everything here is computed or recorded by code. No model is called to produce it, and nothing is claimed that the history does not support. Each piece degrades to silence.

## Dates she keeps (`together` sense)

On by switch in Settings → Sensors ("Your story together"). The relationship starts at the first message in the session history, or at a date entered with `companion_together.py set --since YYYY-MM-DD` (which wins). From it she knows how long you have known each other, every monthly anniversary, 50/100/150/200/250/300/400/500… days, and each yearly anniversary (a year is an anniversary, not twelve months). A week ahead she is told what is coming.

Your birthday is stored once you have told her: `companion_together.py set --human-birthday MM-DD --evidence "your words"`. The evidence is required so it can be checked. A ritual recorded with `--recurs yearly|monthly|weekly` and `--first-on DATE` is counted ("the 3rd time") and shown two weeks before it comes round (yearly and monthly).

`dates.md` and `care.md` still work for anything else.

## Holidays (`holidays` sense)

Public holidays a week ahead, in the country of her timezone (read from the IANA `zone.tab`, so there is no country question at setup). It asks Nager.Date for the country and year, once, and keeps the answer in `state/`; nothing about you leaves the machine. Regional holidays are skipped. Offline with no kept copy, or a timezone with no country, it says nothing. It is off until you switch it on.

## What you watch (`viewing` sense)

From your own Plex or Jellyfin server, set in Settings → Awareness → Your media server (address, which server, your account, and a token; Save and check shows what it can read). Switched on as "What you watch". Only your server is contacted. The titles reach her model provider like everything else she knows, which is why it is off until you switch it on.

- **What is on.** "At 20:51 Robin was watching Severance S2E3 on Plex, 24 of 51 minutes in." Music is left to the music sense.
- **Lately.** The latest of each series or film you finished in the last ten days: "Severance up to S2E2, last night; Paddington 2 (2017), on Saturday". A viewing day runs to 4 am, so a film finished at 1 am was last night.
- **Kept.** Every episode or film the server reports finished goes into `viewing.jsonl` once, so the memory outlasts the server's own history.
- **Watching together.** When you agree to watch something, she records it: `companion_viewing.py together --title "Severance"` (three hours unless `--hours` says otherwise, `stop` to end it). While it holds and that title is on, she is told what the episode is about, and the chat checks what is on at most once a minute instead of every fifteen. Episodes finished in that time are kept as watched together.

Only your own account is read: the server's owner on Plex unless you name another, the administrator on Jellyfin unless you name another. The token sits in `secrets/` in the profile, which backups leave out, and is never shown again; removing the server address forgets it. A server that cannot be read says nothing rather than half a picture.

## Things she could notice

Added to chat context while relationship indicators are on, from timestamps and message lengths counted in the database (no message text is read for this):

- **Late nights:** you wrote during your usual quiet hours (learned, else 00:00–05:00) on three or more of the last seven nights, with the usual weekly count for comparison.
- **Writing style:** today's median message length is at most half, or at least double, your usual.
- **A hanging question:** her last message ended on a question and you did not write back, or your next message arrived 20 or more minutes later. Whether it answers the question is stated as not known.

They are worded as observations. She is told she may remark on one the way someone who had noticed would, and told not to say why it is happening or claim a mood from it. Detecting a question means "her message ends with a question mark", which is a shallow test, so it is only ever stated, never acted on.

## What she has told about her past (`companion_canon.py`)

Her history is hers to invent and then it is fixed. Each statement has a topic. A new statement on a topic she has already covered is refused until she says whether it revises the old one (`--supersedes ID`, which keeps the old text in the history) or adds to it (`--also`). It is stored in `companion-life/canon.jsonl`, apart from facts about you, and never becomes a claim about you.

## Her places (`companion_places.py`)

Her home has a floor plan: a description and rooms (`set-home --room "Kitchen=yellow tile"`). Until she has recorded it she is told so, and told not to describe the inside of her home in detail. Any other place (the gym, the corner bookstore) is recorded the first time she describes it in detail, and later visits add details instead of rewriting it. `companion-life/places.md` is a readable copy rendered from `places.jsonl`; editing it changes nothing. Scheduled runs that choose where she is see the same places.

Where she is is a field on every presence record, set by her, never read out of the location's wording: `place` is `home` (with `room`), the id of a place she has been, or `out` when she is out and about with nowhere in particular to be. The first time she goes somewhere she describes it with `new_place` in the same record, and her home is described once with `home` (a description and its rooms). Staying put carries the place forward. Until her home is on record, every scheduled run asks her to describe it; once it is, a record that moves somewhere without saying which place is refused with her rooms and places listed, so one kitchen stops being written eight ways. A room not yet on the floor plan is added when she names it. Pictures of a place carry how she described it, so the shop she goes back to looks like the same shop.

## Storylines (`companion_arcs.py`)

The parts of her life that take weeks: learning something, a project, a problem to sort out,
something at work or with someone she knows. She starts one (`start --title --premise --kind
--weeks`), records a step when it moves (`beat`, at most one a day) and ends it, resolved or
dropped (`end`). At most two run at once. Her runs and her chats carry the running ones with how
far along they are and their last step; one that has not moved for four days is mentioned as still,
and one past the weeks she gave it is asked to come to an end. With none running she is invited to
start one, and the weekly reflection looks at the week ahead: storylines, people, and somewhere to
be.

## The people in her life (`companion_life.py`)

Her people are the ones setup wrote into her routine and the ones she adds (`add-person`). The
shared seed list is offered a few at a time, a different few per companion, only while she has
fewer than three people of her own, and she is asked to let someone in until she has. A presence
record says who is with her (`with`), which records the meeting and counts as company, and `news`
keeps what is going on in someone's own life so it comes back the next time they are due.

## Moments

The relationship ledger (`companion_notes.py moment ...`) records jokes, nicknames, rituals, firsts and milestones with the words or occasion they came from (`--evidence`). Rituals can recur, as above.

## Warmth and trust move on their own

See [FEELINGS.md](FEELINGS.md). Days of real two-way conversation nudge them; they do not replace recorded experiences.

## Small context windows

On a window too small to carry them, the places and canon are left out with a disclosure in the "Omitted this turn" notice, and the paragraph that teaches her the recording commands is skipped (it is only included for windows large enough to afford it).
