Tamanitomo 2.9.0 gives a companion people to see, and tells you where her private life is being sent.

**She has friends now.** `recurring_cast` has been in the routine file since the beginning, and the guidance has always told a companion to develop recurring fictional friends gradually — but nothing ever wrote one, so every companion had an empty world. There is now a cast of eight: the oldest friend who never lets a thing drop, the neighbour you see constantly and never plan to, the friend who lives too far away and is worth the wait. Each has a rhythm, and whoever she has not seen in a while is offered alongside her evening's ideas. She can add people she meets and drop ones she does not want. None of them are real, and none stand in for anyone you know.

**Background jobs are grouped by what they actually send.** The jobs list showed a provider and a model on every job, including the seven that never contact one at all — which reads as though something is being sent when nothing is. They are now in three groups: jobs that never call a model, jobs that call one with nothing private in the prompt, and jobs that put the companion's inner life or your own words into a prompt. Each group says plainly what is at stake and what the safest choice is, and each job says what it sends. A summary at the top names how many scheduled jobs are sending private material, and where.

**Memory is no longer silently tiny.** Hermes ships a memory allowance of about eight hundred tokens, and five hundred for what it knows about you. A companion whose config did not say otherwise inherited those, which is nothing at all for somebody meant to know you next year — one profile here was running on them while another on the same machine held twenty-six times as much. A missing setting now means the full allowance rather than the smallest possible one.

Relatedly, a model reached through a signed-in provider has no endpoint address to look its context window up by, so every lookup missed and a 272,000-token model was sized as though it were 32,000 — and with it the memory allowance chosen from that window.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
