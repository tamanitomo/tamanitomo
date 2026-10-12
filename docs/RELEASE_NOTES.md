Tamanitomo 3.13.1: routine jobs get only the tools they need.

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
