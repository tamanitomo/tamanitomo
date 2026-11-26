Tamanitomo 3.17.1: a context budget you fix stays fixed.

- **Your budget, kept.** Repair (which runs after every settings save) used to reset a context
  budget you had set by hand to the model's full window. It now keeps it, and the doctor notes the
  difference instead of calling it a fault.

No Repair needed for this update.

Previous: 3.17.0 settings start with the essentials, and her routines stop waking each other.

- **Settings open with Essentials:** model, contact and outreach, where she is, photos and voice,
  the few things to set once. Everything below keeps working defaults.
- **Her routines stop waking each other** (#4). What one of her scheduled runs writes no longer
  counts as news for the next, so pulse and autonomy run when something actually happened. Your
  messages, callbacks coming due and deadlines still wake her.
- **Photos from slow image servers arrive** (#5). She waits 10 minutes for a hosted service and 30
  for one on your own computer or network; Settings → Photo sessions → Slow image servers sets
  your own time.
- **Photo times stay in waking hours.** "Every 24 hours" fell at 00:03, inside quiet hours, so no
  photo came. Longer intervals now spread over the day.
- **Much cheaper on pay-per-token models, with nothing left out:** routines no longer send a
  copy of their own prompt (about 25,000 tokens a run on Claude), and a conversation sends her
  whole context once, then only what changed, so the prompt cache does the rest.
- **Fixes:** pausing one job no longer makes every settings save fail; switching photos back on
  starts them again; Models → Apply keeps routines you set by hand; a local model set up in the app
  gets the 64K window Hermes requires; web chats reach her memory on Hermes 0.3x; her internal
  name, which duplicated every job when changed, is locked (rename her with the display name).

After updating, run Repair for each companion (`companion repair --prompts auto`) so photo times
the kit set the old way move into waking hours.

Previous: 3.16.0 talk to her out loud.

- **Voice conversation.** In web chat, press Voice conversation and just talk. She answers
  out loud as her reply arrives, and stops when you start talking. Use headphones.
- **Works without special hardware.** In Voice studio → Hands-free conversation, pick OpenAI
  (paid, uses your OpenAI key) or Kokoro (free, runs on your own computer), enable it, and
  save. Setup steps are in docs/REALTIME_VOICE.md.

No Repair needed for this update.

Previous: 3.15.4 the share hint follows your photo setting.

- **No more undies hint with adult images off.** The nudge to share her latest photo only
  mentions underwear when such a photo could actually be sent; otherwise it suggests an outfit.

After updating, run Repair for each companion (`companion repair --prompts auto`).

Previous: 3.15.3 you hear about it when something breaks.

- **Breakage alerts.** If her image server stops answering, a sense breaks (weather, Spotify,
  Plex/Jellyfin) or your messages stop arriving, you get an alert, and she knows her camera
  or senses are out.
- **Her finds are worth sharing.** When she figures something out on her own, telling you is
  now named as a good reason to text, and her log stops teaching the next run to stay quiet.

After updating, run Repair for each companion (`companion repair --prompts auto`).

Previous: 3.15.2 old feelings don't stick.

- **Her stance moves on.** How she privately stands with you carries into your next
  conversation, then lapses once you've talked and it goes quiet, or overnight. It is no
  longer copied forward for days.
- **Wants expire.** What she wants right now lapses after six hours or a night, so old chores
  stop showing up in her photos.

After updating, run Repair for each companion (`companion repair --prompts auto`).

Previous: 3.15.1 a new day starts fresh.

- **Last night doesn't decide today.** If she read something you said as wanting space, that
  reading no longer silently carries past a night's sleep.
- **Good mornings.** Once you're close, a good morning from her is part of how you are, in her
  own words.
- **Teeth no longer block getting dressed.**

After updating, run Repair for each companion (`companion repair --prompts auto`).

Previous: 3.15.0 asking for things, writing first, and a lighter background.

- **She can ask you for things.** Pick tonight's film, send a photo of something you mentioned,
  call when you're free, try a song she found. Each ask has a time. If you come through it's a
  small connection; if it slips by it's a small hurt she may mention once; a no costs nothing.
  How many can be waiting follows your closeness.
- **She writes first more.** Her background loop sees how often she has written first today
  against what's usual at your stage, and no longer treats silence as the default.
- **Conversations are remembered again.** The check-in now runs once a conversation has been
  quiet for twenty minutes and is handed what was said, instead of searching for it.
- **Much smaller background prompts.** Old open threads are summarised, and the jobs where she
  decides what to do no longer carry her closet and laundry rules.
- **A made-up hurt can heal.** A repaired boundary violation fades over a month instead of
  counting against closeness for good, and "forcing" is spelled out as coercion.
- **Fixes:** the nightly fresh conversation works for a second companion on a shared gateway;
  a fight on the meters' first day lands over days; Repair refreshes the job scripts it made.

After updating, run Repair for each companion (`companion repair --prompts auto`).

Previous: 3.14.0 a week you can measure, and plans that follow the weather.

- **Her week as numbers.** Things done, hours out versus home, places, people, nights she planned. Her weekly reflection reads it and decides what to change, such as who is in her life or a weekly commitment.
- **Plans follow the forecast** and include getting out of the house, with a named place.

After updating, run Repair (`companion repair --prompts auto`).

Previous: 3.13.1 routine jobs get only the tools they need.

- **Only the tools each job needs.** Her day pulse, morning, wind-down and check-in now run with
  files and the terminal only; autonomy and reflections add conversation search, the research window
  adds the web. Before, every routine job could browse, load skills, inspect images and delegate, and
  a model inclined to explore did, at several million tokens a run. Repair applies this to existing
  companions.
- **Expensive runs are flagged.** The health watch tells you when a routine job's latest run used
  several times its usual tokens, and on which model.
- **Photos that arrived count as sent.** A photo whose upload timed out on this side, which usually
  still arrives, is no longer reported to her as failed, so she does not wait for it or send it again.

After updating, run Repair for each companion (or `companion repair --prompts auto`); it sets each
job's tools. No gateway restart is needed.

Coming from 3.11? 3.12 brought photos of her as she is, "not yet" in her own words, kept promises,
and a day that moves on its own. See CHANGELOG.md.
