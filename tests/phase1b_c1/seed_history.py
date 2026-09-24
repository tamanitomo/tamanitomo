"""Seed a synthetic Hermes session through the PINNED SessionDB (tests only; never shipped).

    <hermes python> seed_history.py <state.db> <session_id> <pairs> <chars>

Writes <pairs> synthetic user/assistant exchanges of about <chars> characters each into a new
`cli` session, so that a resumed turn exceeds the compression threshold and the real CLI
compression path runs. Prints one JSON line: the row ids written.
"""
import json
import pathlib
import sys


def main(db_path, session, pairs, chars):
    from hermes_state import SessionDB
    db = SessionDB(db_path=pathlib.Path(db_path))
    db.create_session(session, 'cli')
    ids = []
    filler = 'synthetic history line for compression evidence. '
    for i in range(int(pairs)):
        body = (f'Synthetic earlier message {i}. ' + filler * (int(chars) // len(filler)))[:int(chars)]
        ids.append(db.append_message(session, 'user', body))
        ids.append(db.append_message(session, 'assistant', 'Synthetic earlier reply ' + str(i) + '. ' + body,
                                     finish_reason='stop'))
    print(json.dumps({'rows': ids}))


if __name__ == '__main__':
    main(*sys.argv[1:5])
