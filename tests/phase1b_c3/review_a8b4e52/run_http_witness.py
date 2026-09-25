"""Actual app HTTP/ledger witness with the submitted client executed in Node, not a browser.

python run_http_witness.py /path/to/repo --out /safe/review-output \
    --tmpdir /supported/fixture/filesystem [--candidate /path/to/candidate-copy]

Only synthetic Server fixtures are used. No live Hermes/model/platform request.
A fixture ledger is moved after a settled receipt and idle worker, never while executing.
The original repository files are not changed. A candidate path is used only for its JS;
the server always uses the specified repository's actual backend.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('repository', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--candidate', type=Path)
    ap.add_argument('--tmpdir', type=Path)
    args = ap.parse_args()
    src = args.repository.resolve()
    if not (src / 'tests/phase1b_c3/fixture.py').is_file():
        ap.error('repository must contain the C3 fixture')
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(src), str(src / 'kit/scripts')]
    if args.tmpdir:
        args.tmpdir.mkdir(parents=True, exist_ok=True)
        os.environ['TMPDIR'] = str(args.tmpdir.resolve())
    from tests.phase1b_c3.fixture import Server
    from kit.app import send_protocol as sp
    args.out.mkdir(parents=True, exist_ok=True)
    variants = {'source': src}
    if args.candidate:
        variants['candidate'] = args.candidate.resolve()
    failed = False
    for variant, client_root in variants.items():
        for mode in ('lost', 'known'):
            s = Server()
            s.scenario(reply='A synthetic completed reply.')

            @s.app.get('/api/review-idle')
            def review_idle():
                with s.app.state.operations.lock:
                    return {'idle': not s.app.state.operations.busy}
            try:
                ledger = sp.ledger_dir(s.home()) / sp.LEDGER_FILE
                command = ['node', str(Path(__file__).with_name('c3_real_http_witness.cjs')),
                           str(client_root), s.base, str(ledger), mode]
                result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                if not result.stdout.strip():
                    raise RuntimeError(result.stderr)
                data = json.loads(result.stdout)
                data.update(exit_code=result.returncode,
                            client_sha256=hashlib.sha256((client_root / 'kit/app/static/chat-sends.js').read_bytes()).hexdigest())
                kept = Path(str(ledger) + '.review-kept')
                con = sqlite3.connect(kept.resolve().as_uri() + '?mode=ro', uri=True)
                try:
                    data['durable_send_count'] = con.execute('SELECT count(*) FROM sends').fetchone()[0]
                    data['durable_launch_count'] = con.execute(
                        "SELECT count(*) FROM send_facts WHERE kind='executor_started'").fetchone()[0]
                finally:
                    con.close()
                data['hermes_owner_rows'] = s.owner_rows()
                data['fixture_stderr'] = result.stderr
                (args.out / f'http_witness_{variant}_{mode}.json').write_text(json.dumps(data, indent=2))
                failed |= result.returncode != 0
                print(variant, mode, 'exit', result.returncode, 'pending', data['pending_preserved'],
                      'status', data['status'], 'launches', data['durable_launch_count'], flush=True)
            finally:
                s.close()
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
