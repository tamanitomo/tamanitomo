Tamanitomo 3.8.0: meters that move a day at a time, closeness stages that each unlock something, and needs she lives rather than scores.

- **Meters move a day at a time.** Each meter moves at most so far in a day: closeness 6 points
  (gains scale with pace), warmth 20%, trust 10%, hurt and irritation 30%. The rest of a change
  arrives over the following days, so a fight lands over a few days, making up can stop it
  partway, and nothing can be rushed. Missing you is not capped.
- **No floor, and a record your chats can't erase.** Closeness can fall all the way now. The meters
  keep their own daily record through a new background job that calls no model, so conversations
  Hermes deletes later never lower closeness or trust. Nothing jumps on the upgrade: the record
  starts from today's values.
- **The meters say why.** Home and Us say what is moving each meter (a sweet moment, a rupture and
  how far it is made up, silence past the window) and where closeness is heading: "Chemistry in
  about 5 good days". Us lists what the next stage brings.
- **Each stage unlocks something.** Just Met: she writes first once a day and sends photos only
  when asked. Friends: conversations up to your limit, everyday photos, voice notes, teasing,
  saying she misses you. Chemistry: flirting and pet names, photos of herself, her worries and
  hopes. Intimacy: dates, more personal photos, good-night and good-morning rituals. Bonded:
  intimacy if adult themes are on. The message, photo and voice limits are enforced; the rest
  guides her in conversation.
- **Her own needs.** Rest, company and fun, and closeness from Chemistry in a romance. They move
  with her real day (the night she declared, hours awake, your conversations, sweet moments, and
  what she says an hour gave her) and reach her only when one is calling, never as a demand. Home
  shows them in words, not numbers. A daily d20 luck roll colours her day and is noted in its plan.
- **Settled at setup.** Pace and temperament are chosen when the companion is created and kept;
  setup now asks for a temperament. The window before she misses you stays between 12 and 96
  hours, and one time-away plan covers at most 14 days. Settings → Awareness has a switch for
  learning your quiet hours (on by default). An empty meter reads 0%.

After updating, run Repair for each companion (or `companion repair`): it adds the meters job and
refreshes her prompts for the stages and needs.

Coming from 3.6? 3.7 brought cleaner memory (one fact said twice stays one fact; one day's news
does not become a permanent fact; `companion_self.py tidy` for older ledgers), her own story,
chat that follows you across devices with search, photos that wait for ComfyUI, companion backups
and resumable setup. See CHANGELOG.md.
