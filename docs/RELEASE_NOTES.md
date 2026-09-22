Tamanitomo 3.0.3 is about a companion not inventing the person it is talking to.

A journal entry described a morning greeting that never happened — a pet name, a question about how she was, none of it said by anyone. The instruction not to invent his words was already in the prompt, written out in prose, and prose is what the model is made of. Asking it to remember whether someone spoke to it is asking the wrong question: it will fill the silence, because filling silences is the thing it does.

The session record already knows the answer. `companion_life.py contact --day` reports what it says — how many of a day's sessions came from a person rather than a scheduled job, at what times, under what titles — and the daily journal now runs it before writing a word about the human. No sessions from a person means it may not put words, wants or feelings in their mouth, and should say the day held no exchange, plainly. Where sessions exist they are the only exchanges there were, and their titles are summaries written afterwards rather than anything anyone said. A session record that cannot be read reports unknown, never "nobody was there" — those are different facts and only one of them is safe to write from. Two companions talking to each other is counted as what it is rather than as company.

This matters more than a wrong detail. Affection nobody gave is the easiest thing in the world to write and the worst thing to read back, because it describes someone its person is not. An empty day is allowed to be empty.

Separately, a validation bug with the same shape underneath it: before writing a presence record, the pulse asks whether the record would be accepted, and that question was being answered against the wall clock rather than the moment the record describes. Which routine anchor is active is a fact about a moment. So the same pulse was accepted before nine in the morning and refused at ten, and a job catching up after a gap was judged against a day it was not writing about.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
