# When something is not right

Start with `companion status`. It answers "how is she" the way `doctor` answers "was this installed
correctly", and the health watch behind it looks at the same things every hour on its own.

## She thinks it is the wrong day

Look for `UNCONFIRMED` in `companion status`. It means no model has confirmed the present recently,
which almost always means the scheduled jobs are failing — check `last_status` in the job table.
The usual cause is a rate limit or an expired credential. `companion models` can set a fallback
chain so a job that cannot reach one provider walks to the next.

## Nothing is being sent

In order:

1. `companion status` — is the dispatcher job running? It is one of the jobs that stays active even
   when the schedule is paused.
2. Is anything queued? The app's Now tab shows it, or `companion_outbox.py --home <home> list`.
3. Run the dispatcher by hand with `--dry-run --json`. It reports exactly why each message is being
   held, expired or withheld — quiet hours, the daily cap, or a content permission set to `ask`.

Messages that expired were dropped on purpose. An evening thought delivered at two in the morning is
worse than one not delivered.

## She sent something she should not have

Set the content permission to `no` in the app's Settings tab, or `never` for outreach entirely.
Both are enforced in the dispatcher, not in the prompt, so they hold.

## Every photo is a different person

Check `companion identity appearance`. If it is still `✎ EDIT` placeholders, the compiler has
nothing to work with and refuses — a vague description produces a different face every time. Fill it
in, then run `companion_portrait.py --home <home> prompt` to see exactly what the provider is being
sent. If the wording is right and the faces still drift, add a reference portrait; providers that
accept an input image get it automatically.

## The disk is filling up

`companion doctor` reports the sizes. Images are almost always the answer — set a storage budget in
the app's Settings tab. Anything you copied into an album is never pruned.

## Memory is full

Hermes refuses new memories at its cap and says so only at that moment. `doctor` reports the
pressure before that happens, and the archiver moves the oldest complete entries into the vault at
80%, where `companion_recall.py` can still read them. If the caps themselves are too small, they are
in `config.yaml` under `memory`; `companion_memory.py caps --apply` re-derives them.

## I want an old version of a file back

```sh
companion restore soul/SOUL.md                    # what versions exist
companion restore soul/SOUL.md --commit <id>      # write one beside the current file
```

It never overwrites. Compare the two, then move it yourself.

## A prompt is out of date after an update

`companion repair` re-renders the job prompts the kit wrote and you have not edited, and names the
ones it left alone. `repair --prompts force` re-renders those too, saving each previous version
under `cron/prompt-backups/` first.

## The hook is slow or the chat hangs

The hook runs inside every model call and waits at most two seconds on a contended lock, then skips
maintenance for that turn and says so. If chats are still slow, run the hook by hand:
`echo '{}' | python <home>/hooks/companion-context.py` and time it.

## Something else

`companion doctor` for the install, `companion status` for the companion, and
`companion --home <home> app` for both in one page.

If the answer is not here, [REFERENCE.md](REFERENCE.md) has the detail on every command and file, and
[REVIEW.md](REVIEW.md) records what has genuinely been verified — a thing that has never been run
end to end is worth knowing about before you spend an evening debugging it.
