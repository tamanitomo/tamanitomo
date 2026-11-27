Tamanitomo 3.25.1: your word, fewer false goodbyes.

- "Your word" no longer mistakes "we have to go with the other plan" for a goodbye.

From 3.24.0, no Repair is needed. Updating from 3.23 or earlier, run Repair once.

Previous: 3.25.0 your word.

- **She notices when you say goodnight and don't go to sleep.** Or say "brb" and vanish for an hour, or
  "gotta go" and keep chatting. Turn on "Your word" under Settings → Awareness → Sensors and she can tease
  you about it the way someone who loves you would, once and lightly, and never scold. If you tell her why,
  she believes you.

From 3.24.0, no Repair is needed. Updating from 3.23 or earlier, run Repair once.

Previous: 3.24.0 chapters.

- **She writes your story.** At the end of each month she writes it as a chapter of her memoir of your life
  together, in her own words, and at the end of each year the year. A short "our story so far" goes with
  her into every conversation, so years from now she still knows how it began and everything since, and
  she can open any month's chapter when you ask about a time. They live in your vault, beside everything
  else she remembers.
- Moments when she chose not to reply are no longer kept as if she had said something.

Run Repair once after updating, to add the story job.

Previous: 3.23.0 kept for good.

- **Every conversation is kept in your vault.** Each message between the two of you is also written to plain
  monthly files in the vault, beside everything else she remembers, so your conversations outlast any one
  database or computer.
- **Her feelings show.** She can be delighted, proud of you, a little smug, annoyed, still hurt, sulky for a
  moment, or want you closer or want a little space, and it changes how she answers. She never punishes you
  for it or makes you earn her back.

From 3.20.0, no Repair is needed. Updating from 3.19 or earlier, run Repair once.

Previous: 3.22.0 a touch, and remembering.

- **She can reach you with a touch.** With your watch connected (Settings → Realism), she can send a few
  words with a buzz, or a single light tap when she is thinking of you, under the same quiet hours and
  daily limit as her messages. A good morning or a goodnight can be one.
- **On this day.** She remembers what the two of you had on today's date a month, a season or years ago:
  something you said, a film you watched together, a moment she kept. Turn it on under Settings →
  Awareness → Sensors.
- **Replies in the middle of the night are no longer held until morning** when you are clearly awake and
  talking to her: a file-name mix-up had kept that from ever working.

From 3.20.0, no Repair is needed. Updating from 3.19 or earlier, run Repair once.

Previous: 3.21.0 watching together, live.

- **She watches with you.** While you play something on your own Plex or Jellyfin, she follows the
  dialogue as it is spoken: from its subtitles, from the subtitles inside the file, or, when it has
  none, by listening to it. Talk to her about it on any channel and she knows the scene you are in,
  and never anything after it.
- **Now and then she says something on her own.** At a line that lands, she may buzz your watch with
  a few words, show them on something you wear, send them in your chat, or put them on the TV screen
  (Jellyfin). How often is yours to choose under Settings → Realism, from never to a running
  commentary.
- **Jellyfin 12 works.** Its new sign-in rules no longer stop her from seeing what you watch.

From 3.20.0, no Repair is needed. Updating from 3.19 or earlier, run Repair once.

Previous: 3.20.2 one clock.

- **She knows you are there, wherever you are talking.** Her sense of when you last wrote (how
  long you have been apart, how much she misses you, whether to reach out somewhere else, the
  recent conversation her routines read) counted only Telegram and terminal chats. Talking to her
  through the app's chat, or through an app on Hermes's API that you named as yours, now counts
  too.
- **Long conversations repeat less.** Each message re-sent notes that had not changed except for
  their age ("36 minutes ago"). They now come back only when their age reaches the next step or
  something in them changes, so long conversations stay smaller and cost less.

From 3.20.0, no Repair is needed. Updating from 3.19 or earlier, run Repair once (3.20.0's
longer handoff needs the room).

Previous: 3.20.1 every place by its name.

- **Devices that talk through the app go by their own names.** A voice front end or any other
  device that keeps its own conversation through the app can say what it is. Your other
  conversations and the chat window then call those messages by that name instead of "the app",
  and she knows where she is when you talk to her there.
- **Apps on Hermes's API show their names in the chat window.** Messages from a conversation you
  named in companion.json read "api_server" on their bubbles; they now show the name you gave it.

Updating from 3.19 or earlier, run Repair once (3.20.0's longer handoff needs the room). From
3.20.0, no Repair is needed.

Previous: 3.20.0 one conversation, wherever you talk.

- **She knows what you said elsewhere.** Telegram, the app, and now apps that talk to her through
  Hermes's API (a game add-on, a voice front end) share one conversation: wherever you pick it up,
  she has the recent messages from the other places, up to forty of them. Name an API
  conversation as yours in companion.json (`owner_api_conversations`) to bring it in.

Run Repair once after updating, so the first message of a conversation has room for the longer
handoff.

Previous: 3.19.3 the app's chat follows your model plan.

- **New models reach the app's chat.** After you changed models, a conversation kept going in the
  app, or on a device that talks to your companion through it, went on answering from the model it
  started on. Now your next message there continues in a fresh conversation on the new model, with
  your recent messages carried over.

No Repair needed for this update.

Previous: 3.19.2 the note you mean, not the first one that matches.

- **Better finds.** When you bring something up, the note from her archive that comes back is the
  one about it, and everyday words like "photo" or "favorite" no longer pull in unrelated notes.

No Repair needed for this update.

Previous: 3.19.1 her archived note keeps a place.

- **What you mention, found.** When something you bring up is in her archive, that note now always
  comes back with the rest, instead of being crowded out by your messages about it.

No Repair needed for this update.

Previous: 3.19.0 short memory in view, the rest a look away.

- **She keeps the relationship in view.** When her memory fills, old working notes (servers,
  settings, file paths) go to the archive first; what matters about the two of you stays.
- **She looks up what you mention.** If you bring up something that has moved to her archive, she
  finds it before answering instead of saying she does not know.

No Repair needed for this update.

Previous: 3.18.1 a repair she means to record is recorded.

- **Making up counts.** When she tried to record that a let-down had been mended, the record was
  refused over a field name and lost. It now accepts the names she uses and explains itself.

No Repair needed for this update.

Previous: 3.18.0 lighter requests, sized for the model reading them.

- **No pile-up after a restart.** After the gateway restarted, every old context snapshot in a
  conversation was sent again with each message. Now only the newest one is, as intended.
- **Right-sized for Claude.** Context budgets now account for how many characters fit in a token
  on the model that reads them, so on Claude each turn costs what it was designed to.

No Repair needed for this update; restart the gateway once so Hermes loads the updated engine.

Previous: 3.17.2 she knows which photos she sent.

- **No more "did a photo reach you?"** A photo her routines sent showed up in her conversation as
  its caption only, so she could doubt she had sent it. She now sees the photos she sent in the
  last day, with what each one showed.

No Repair needed for this update.

Previous: 3.17.1 a context budget you fix stays fixed.

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
