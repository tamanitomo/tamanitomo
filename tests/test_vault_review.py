"""Finite V1/V2/V3 regressions against the actual editor/controller and CM bundle.

Keep observe_vault_review.js beside this file. These are Node module-state tests,
not browser journeys or full HTTP tests. The observer exports existing functions
through one test seam; it does not replace their logic or the CodeMirror classes.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import pytest

ROOT = Path(os.environ.get('TAMANITOMO_REVIEW_ROOT', Path(__file__).resolve().parents[1]))

@pytest.fixture(scope='module')
def outcomes():
    node=shutil.which('node')
    if not node:
        pytest.fail('Node is required for the supplied Vault reviewer regressions')
    result=subprocess.run([node,str(Path(__file__).with_name('observe_vault_review.js')),str(ROOT)],
                          cwd=ROOT, capture_output=True,text=True,timeout=20)
    assert result.returncode==0, result.stdout+'\n'+result.stderr
    return json.loads(result.stdout)

def test_v1_offline_recovered_edits_remain_dirty_and_kept(outcomes):
    r=outcomes['offline_edit']
    assert r['dirty'] and r['kept'] and r['kept']['text']==r['buffer'], r

def test_v1_external_revalidation_preserves_recovered_text_as_conflict(outcomes):
    r=outcomes['offline_external_read']
    assert r['buffer']=='recovered owner draft' and r['status']=='conflict', r
    assert r['conflict']['text']=='external editor text', r

def test_v2_copy_receipt_does_not_clear_later_edits(outcomes):
    r=outcomes['delayed_copy']
    expected='copy request text PLUS NEWER TYPING'
    assert r['buffer']==expected and r['kept'] and r['kept']['text']==expected, r
    assert r['status']=='conflict' and r['savedCopy']=='copy request text', r
    assert r['active']=='notes/a.md', r

def test_v2_copy_receipt_does_not_navigate_away_from_newer_note(outcomes):
    r=outcomes['delayed_copy_navigation']
    assert r['active']==r['expected'],r

def test_v3_closed_offline_note_has_no_unsent_retry(outcomes):
    r=outcomes['closed_offline_retry']
    assert r['writes']==[] and r['kept'] is None,r

def test_v3_closed_note_failed_request_does_not_restart_saves(outcomes):
    r=outcomes['closed_inflight_failure']
    assert r['writes']==[] and r['kept'] is None and r['known'] is None,r

def test_control_serial_save_keeps_newer_buffer_and_revisions(outcomes):
    r=outcomes['normal_serial_save']
    assert r['afterAck']==r['buffer']=='newer queued edit',r
    assert r['status']=='saved' and r['bodies']==['first submitted','newer queued edit'],r
    assert r['bases']==['rev0','rev1'],r

def test_control_unchanged_copy_retains_expected_behavior(outcomes):
    r=outcomes['normal_copy']
    assert r['original']=='external disk' and r['status']=='saved',r
    assert r['savedCopy']=='saved copy text' and r['activeIsCopy'] and r['kept'] is None,r
