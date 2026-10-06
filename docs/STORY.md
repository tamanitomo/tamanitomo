# Her story, and what she can notice

Everything here is computed or recorded by code. No model is called to produce it, and nothing is claimed that the history does not support. Each piece degrades to silence.

## Dates she keeps (`together` sense)

On by switch in Settings → Sensors ("Your story together"). The relationship starts at the first message in the session history, or at a date entered with `companion_together.py set --since YYYY-MM-DD` (which wins). From it she knows how long you have known each other, every monthly anniversary, 50/100/150/200/250/300/400/500… days, and each yearly anniversary (a year is an anniversary, not twelve months). A week ahead she is told what is coming.

Your birthday is stored once you have told her: `companion_together.py set --human-birthday MM-DD --evidence "your words"`. The evidence is required so it can be checked. A ritual recorded with `--recurs yearly|monthly|weekly` and `--first-on DATE` is counted ("the 3rd time") and shown two weeks before it comes round (yearly and monthly).

`dates.md` and `care.md` still work for anything else.

## Holidays (`holidays` sense)

Public holidays a week ahead, in the country of her timezone (read from the IANA `zone.tab`, so there is no country question at setup). It asks Nager.Date for the country and year, once, and keeps the answer in `state/`; nothing about you leaves the machine. Regional holidays are skipped. Offline with no kept copy, or a timezone with no country, it says nothing. It is off until you switch it on.

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

## Moments

The relationship ledger (`companion_notes.py moment ...`) records jokes, nicknames, rituals, firsts and milestones with the words or occasion they came from (`--evidence`). Rituals can recur, as above.

## Warmth and trust move on their own

See [FEELINGS.md](FEELINGS.md). Days of real two-way conversation nudge them; they do not replace recorded experiences.

## Small context windows

On a window too small to carry them, the places and canon are left out with a disclosure in the "Omitted this turn" notice, and the paragraph that teaches her the recording commands is skipped (it is only included for windows large enough to afford it).
