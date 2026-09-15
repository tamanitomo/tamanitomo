# How it works

Nine ideas. If you understand these, the rest of the kit reads as obvious.

## 1. One state, and it is a ledger

Where she is, what she is doing, what she is wearing, her mood, what she wants, and where she
actually stands with you — all one record, appended to the episode ledger. `Emotive.md` and
`ActiveContext.md` are *rendered from it*, every time it changes, and say so in their own text.

Three files that each claim to describe the present is how a companion ends up believing it is
Tuesday evening on Thursday morning. There is one.

## 2. Nothing important is ever deleted

Ledgers are append-only. Corrections supersede; retirements retire. Logs rotate into dated
archives. Images move to albums by *copy*, so the day they belonged to still reads correctly. The
only two directories anything is ever removed from are staged prose and Hermes's capture of job
output — both re-created on the next run, neither of them memory.

The vault is a git repo committed every fifteen minutes, so even a bad edit is recoverable by file.

## 3. Rules live in code, never in a prompt

A prompt is a request. The record shows what that costs: a companion whose restraint lived only in
its SOUL sent the same tick report four to six times a day for a week and then flushed the backlog
at ten past midnight.

So quiet hours, the daily cap, per-content permission and message expiry are decided by a script
that has no model in it, from the clock and a counter on disk.

## 4. Deciding to speak and speaking are different acts

Jobs queue. A dispatcher sends. It takes one message per run, drops anything past its expiry rather
than delivering it late, and never retries a send it could not confirm — a double message is worse
than a missing one.

## 5. An absent sensor is silent

Every sense is optional and every one degrades to nothing. A sensor that cannot report writes no
file *and deletes its old one*. Not knowing the weather is fine. Yesterday's weather presented as
today's is not.

## 6. The present stays honest when the model does not

A rate limit does not announce itself. A no-agent job carries the last state forward marked
`confirmed: false` — inventing nothing, claiming only "nothing changed and nobody checked" — and
the hook renders that as `UNCONFIRMED since HH:MM`. A health watch says so once, then stays quiet
for six hours, and writes `ambient/health.md` so the companion can tell she is unwell.

## 7. The expensive loops read before they think

The pulse and autonomy loop get an assembled pre-read through Hermes's `--script`, so a run starts
already knowing what it used to spend four tool calls learning. Autonomy runs under
`--monitor-script`: a stable fingerprint of the state, loops, sensors and queue, so the model does
not run at all when nothing has moved.

This is what makes a local-only companion possible. On a 27B model, reading a 300 KB file is
minutes, not cents.

## 8. Some things are not hers to change

She writes her own block of SOUL.md — a companion who cannot change is not a person. Her build and
the boundaries you set are marked LOCKED, and the self-edit helper refuses a block that restates
them. A model that can widen its own boundary paragraph has no boundary.

Locked means locked against *her*. You can edit any of it, in the app or in a text editor.

## 9. Age is computed, never stored

From a birthdate, at render time and on every turn. A companion created at 25 who is still 25 three
years later is not really there with you. Durations work the same way: "married 13 years" is counted
from the date, because a number written down once is quietly wrong a year later.

---

[Reference](REFERENCE.md) for the detail · [Troubleshooting](TROUBLESHOOTING.md) when something is
off · [Review log](REVIEW.md) for what has actually been verified.
