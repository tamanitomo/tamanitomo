"""TEST DOUBLE of agent/session_persistence.py `_db_flush_write(agent, batch_rows, batch_msgs)`:
commits each row through the SessionDB commit point and copies the committed id back as
`_row_id` (the pinned contract the executor's seam relies on). Protocol double only.

`pause_file` on the agent: after the commit, wait for that file to exist before returning, so
a test can read the conversation after the row is committed and before its provenance fact
is written (the executor writes it when this returns)."""
import os
import time


def _db_flush_write(agent, batch_rows, batch_msgs, *args, **kwargs):
    for row in batch_rows:
        row['_row_id'] = agent.db.append_message(agent.session_id, row['role'], row['content'])
    pause = getattr(agent, 'pause_file', None)
    if pause:
        open(pause + '.reached', 'w').close()     # tells the test the note is committed
        end = time.monotonic() + 60
        while not os.path.exists(pause) and time.monotonic() < end:
            time.sleep(0.02)
    return len(batch_rows)
