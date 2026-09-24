"""C0 HARNESS -- run with the pinned Hermes interpreter, never imported by the app.

    <hermes python> turn_driver.py <report.json> <receipts.sqlite3> [--interrupt-after-deltas N]
                    [--recorder commit|rev2|none] -- <hermes argv...>

Runs one REAL quiet one-shot Hermes turn in this process, the way the bridge does
(kit/app/hermes_stream.py), with:
  * a sqlite3.connect tracer installed before `import cli` (O-1),
  * a source-receipt recorder installed before Hermes runs (O-2/O-4),
  * an optional watchdog that calls _thread.interrupt_main() after N stream
    deltas (O-6), standing in for the proposed ledger stop flag.
The report holds times, exit code, connects and deltas count; never message text.
"""
from __future__ import annotations

import _thread
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main(argv):
    sep = argv.index('--')
    opts, hermes_argv = argv[:sep], argv[sep + 1:]
    report_path, receipts = pathlib.Path(opts[0]), pathlib.Path(opts[1])
    interrupt_after = int(opts[opts.index('--interrupt-after-deltas') + 1]) if '--interrupt-after-deltas' in opts else None
    recorder = opts[opts.index('--recorder') + 1] if '--recorder' in opts else 'commit'
    report = {'started': time.time(), 'connects': [], 'deltas': 0, 'first_delta_at': None,
              'quiet_entered_at': None, 'interrupt_sent_at': None, 'keyboard_interrupt_seen': False,
              'exit': None, 'session_id': None, 'modules_before_quiet': None}

    real_connect = sqlite3.connect
    def traced(database, *a, **k):
        stage = ('turn' if report['quiet_entered_at'] else
                 'import' if 'imported_at' not in report else 'startup')
        report['connects'].append({'at': time.time(), 'db': pathlib.Path(str(database)).name, 'stage': stage})
        return real_connect(database, *a, **k)
    sqlite3.connect = traced

    import receipt_probe
    ledger = receipt_probe.Ledger(receipts)

    output = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(output):
        report['import_started_at'] = time.time()
        import cli
        report['imported_at'] = time.time()
        if recorder == 'commit':
            receipt_probe.install_commit(ledger)
        elif recorder == 'rev2':
            receipt_probe.install_rev2(ledger)
        configure = cli._configure_quiet_agent
        def configured(agent, *args, **kwargs):
            configure(agent, *args, **kwargs)
            def on_delta(delta):
                if not isinstance(delta, str):
                    return
                report['deltas'] += 1
                if report['first_delta_at'] is None:
                    report['first_delta_at'] = time.time()
                if interrupt_after and report['deltas'] == interrupt_after and not report['interrupt_sent_at']:
                    def fire():
                        report['interrupt_sent_at'] = time.time()
                        _thread.interrupt_main()
                    threading.Thread(target=fire, daemon=True).start()
            agent.stream_delta_callback = on_delta
        cli._configure_quiet_agent = configured
        quiet = cli._run_quiet_single_query
        def run(instance, query, *args, **kwargs):
            report['quiet_entered_at'] = time.time()
            report['state_connects_before_turn'] = [c for c in report['connects'] if c['db'] == 'state.db']
            try:
                return quiet(instance, query, *args, **kwargs)
            except KeyboardInterrupt:
                report['keyboard_interrupt_seen'] = True
                raise
            finally:
                report['session_id'] = instance.session_id
        cli._run_quiet_single_query = run
        from hermes_cli.main import main as hermes_main
        sys.argv = ['hermes', *hermes_argv]
        try:
            hermes_main()
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        except KeyboardInterrupt:
            report['keyboard_interrupt_seen'] = True
            code = 130
    report['exit'] = code
    report['finished'] = time.time()
    report['receipt_gap'] = getattr(ledger, 'receipt_gap', 0)
    report_path.write_text(json.dumps(report))
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
