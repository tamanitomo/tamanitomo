"""Browser regressions supplied with review 5027108.

NOT RUN by the reviewer: Chromium is not installed in the review environment.
Copy to tests/ and use the existing synthetic Chromium fixture; no live profiles.
"""
import json
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'kit/scripts'),str(ROOT/'tests')]
from tests.test_chat_trusted_browser import Trusted
from tests.test_phase1b_c3_browser import until
from kit.app import chat_sources

class CacheAuthority(Trusted):
    def _outage(self, *, revoke, older):
        self.seed(older=70)
        self.open()
        marker='Morning! On the train again.'
        self.assertIn(marker,self.log())
        self.page.fill('#chat-message','Preserve my newer draft')
        database=self.s.home()/'state.db'
        backup=self.s.home()/'state.db.review-backup'
        if revoke:
            (self.s.home()/chat_sources.BINDING_FILE).write_text(json.dumps({'telegram':[]}))
        database.rename(backup)
        try:
            action='loadOlder' if older else 'loadNewest'
            self.page.evaluate(f'PersistentChat.{action}(ChatStore.now())')
            until(lambda:'unavailable' in self.log().lower(),what='source outage disclosed')
            if revoke:self.assertNotIn(marker,self.log(),'revoked cached history must not remain drawn')
            else:self.assertIn(marker,self.log(),'unchanged-generation outage keeps earlier history')
            self.assertEqual(self.page.input_value('#chat-message'),'Preserve my newer draft')
            self.assertEqual(self.s.sends(),[],'read recovery never sends')
        finally:backup.rename(database)

    def test_revoked_history_removed_when_resync_snapshot_is_unavailable(self):
        self._outage(revoke=True,older=True)

    def test_revoked_history_removed_on_direct_unavailable_snapshot(self):
        self._outage(revoke=True,older=False)

    def test_ordinary_same_generation_outage_keeps_earlier_rows(self):
        self._outage(revoke=False,older=False)

if __name__=='__main__':unittest.main()
