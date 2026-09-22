"""A long render has to say how far along it is.

Polling ComfyUI's history says nothing at all until the picture exists, so a two
minute render reported one unchanging line -- indistinguishable from a job that
has hung, and the reason pressing Generate felt like it did nothing.
"""
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from kit.app.runtime import Operations


class OperationPercentTests(unittest.TestCase):
    """The worker reports a fraction; the indicator draws it or spins."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ops = Operations(pathlib.Path(self.tmp.name))
        # Registered after the directory, so it runs before it: the worker writes
        # the status row one last time as it finishes, and pulling the directory
        # out from under that is a flake rather than a finding.
        self.addCleanup(self.ops.pool.shutdown, wait=True)

    def settled(self, row):
        # Wait for the final write, not just the status flip: the row is saved
        # once more after it completes, and tearing the directory down between
        # the two is a flake, not a finding.
        for _ in range(2000):
            current = self.ops.rows[row['id']]
            if current['status'] != 'running' and current.get('finished_at'):return current
            time.sleep(0.01)
        self.fail('operation never finished')

    def run_reporting(self, calls):
        """Report each reading, and read back what the status row then says."""
        seen = []
        done = threading.Event()
        def work(report):
            for args in calls:
                report.percent(*args)
                seen.append(self.ops.rows[ident]['percent'])
            done.set()
            return {}
        row = self.ops.submit('scope', 'Render', work)
        ident = row['id']
        # A wait for the pool to get to it, not an assertion about speed: the
        # suite runs this alongside everything else, and a five-second budget
        # failed on a loaded machine while the code under test was fine.
        self.assertTrue(done.wait(60), 'the operation never ran')
        self.settled(row)
        return seen

    def test_a_reported_fraction_becomes_a_percentage(self):
        self.assertEqual(self.run_reporting([(5, 20), (20, 20)]), [25, 100])

    def test_an_unknown_total_stays_unknown_rather_than_becoming_zero(self):
        """None means the worker does not know, which is not the same as nothing done."""
        self.assertEqual(self.run_reporting([(3, 0), (3, None)]), [None, None])

    def test_a_nonsense_reading_is_refused_rather_than_drawn(self):
        self.assertEqual(self.run_reporting([('x', 10)]), [None])

    def test_percent_is_absent_until_something_reports_one(self):
        row = self.ops.submit('scope', 'Render', lambda report: {})
        self.assertIsNone(self.settled(row).get('percent'))


class ComfyProgressTests(unittest.TestCase):
    """The queue position, which is plain HTTP and always available.

    It answers the only question worth asking while nothing is happening yet: is
    this stuck, or is something else in front of it?
    """

    def serve(self, routes):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split('?')[0]
                body = json.dumps(routes.get(path, {})).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a):pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}'

    def test_the_websocket_listener_never_fails_the_render(self):
        """Progress is commentary. A provider that will not talk must still render."""
        import companion_media as media
        base = self.serve({})
        said = []
        result = media._comfy_progress(base, 'client', 'ident', said.append)
        if result is not None:
            result.join(timeout=5)
        # Nothing was reported and, crucially, nothing was raised.
        self.assertEqual(said, [])

    def test_a_missing_websocket_library_is_not_an_error(self):
        import companion_media as media
        real = sys.modules.get('websockets.sync.client')
        sys.modules['websockets.sync.client'] = None
        self.addCleanup(lambda: sys.modules.__setitem__('websockets.sync.client', real)
                        if real is not None else sys.modules.pop('websockets.sync.client', None))
        self.assertIsNone(media._comfy_progress('http://127.0.0.1:1', 'c', 'i', lambda m: None))


if __name__ == '__main__':
    unittest.main()
