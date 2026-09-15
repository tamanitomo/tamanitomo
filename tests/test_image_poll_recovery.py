import http.client
import io
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_media as media


class PollRecoveryTests(unittest.TestCase):
    def test_disconnected_poll_recovers_without_losing_queued_image(self):
        with patch.object(media.urllib.request,'urlopen',side_effect=[
                http.client.RemoteDisconnected(),io.BytesIO(b'{"job":{"outputs":{}}}')]) as request, \
             patch.object(media.time,'sleep'):
            result=media.request_json('http://127.0.0.1/history/job')
        self.assertIn('job',result)
        self.assertEqual(request.call_count,2)

    def test_uncertain_submission_is_never_repeated(self):
        with patch.object(media.urllib.request,'urlopen',side_effect=http.client.RemoteDisconnected()) as request:
            with self.assertRaises(http.client.RemoteDisconnected):
                media.request_json('http://127.0.0.1/prompt',{'prompt':{}})
        self.assertEqual(request.call_count,1)


if __name__=='__main__':unittest.main()
