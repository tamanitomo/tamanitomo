"""What a background job sends, and whether it contacts a model at all.

The jobs list showed a provider and a model on every job, including the seven
that never contact one, which reads as though something is being sent when
nothing is. Three questions should be answerable per job: does it call a model,
what goes into the prompt, and where does that prompt go.
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'kit/scripts')]

from kit.app.manage import SENSITIVITY

MANIFEST = json.loads((ROOT / 'kit/templates/cron/manifest.json').read_text(encoding='utf-8'))


class ManifestSensitivityTests(unittest.TestCase):
    def test_every_job_declares_what_it_sends(self):
        for job in MANIFEST['jobs']:
            with self.subTest(job=job.get('key')):
                self.assertIn(job.get('sensitivity'), SENSITIVITY, job.get('name'))
                self.assertTrue(job.get('sends'), 'a job that says nothing about what it sends')

    def test_a_job_that_never_calls_a_model_is_the_only_kind_marked_none(self):
        """The one claim a person must be able to trust without reading code."""
        for job in MANIFEST['jobs']:
            with self.subTest(job=job.get('key')):
                self.assertEqual(job['sensitivity'] == 'none', bool(job.get('no_agent')),
                                 'sensitivity and no_agent disagree about whether a model is called')

    def test_the_jobs_carrying_her_inner_life_are_marked_sensitive(self):
        by_key = {j['key']: j for j in MANIFEST['jobs'] if j.get('key')}
        for key in ('pulse', 'winddown', 'wake', 'daily', 'weekly', 'monthly', 'checkin', 'timeline'):
            with self.subTest(key=key):
                self.assertEqual(by_key[key]['sensitivity'], 'sensitive')

    def test_each_group_says_what_the_safest_choice_is(self):
        for key, group in SENSITIVITY.items():
            with self.subTest(group=key):
                for field in ('label', 'blurb', 'advice'):
                    self.assertTrue(group.get(field))
        self.assertIn('local', SENSITIVITY['sensitive']['advice'],
                      'the sensitive group must say that local is the safest option')
        self.assertIn('Nothing', SENSITIVITY['none']['blurb'])


class MemoryDefaultTests(unittest.TestCase):
    """A missing setting must not quietly mean the smallest possible memory.

    Hermes ships 2,200 and 1,375 characters. Inheriting those silently was how
    one companion ended up able to hold about five hundred tokens about the
    person she speaks to daily, while another profile on the same machine held
    twenty-six times that.
    """

    def test_the_kit_does_not_inherit_the_smallest_possible_memory(self):
        import companion_memory as memory
        self.assertGreaterEqual(memory.DEFAULT_CAPS['MEMORY.md'], 50_000)
        self.assertGreaterEqual(memory.DEFAULT_CAPS['USER.md'], 36_000)
        self.assertEqual(memory.HERMES_CAPS, {'USER.md': 1375, 'MEMORY.md': 2200},
                         'kept so an audit can say what was avoided')

    def test_the_default_matches_the_largest_tier(self):
        import companion_memory as memory
        self.assertEqual(memory.DEFAULT_CAPS['MEMORY.md'], memory.TIER_CAPS['large']['MEMORY.md'])
        self.assertEqual(memory.DEFAULT_CAPS['USER.md'], memory.TIER_CAPS['large']['USER.md'])


class ContextWindowTests(unittest.TestCase):
    """A provider Hermes holds the session for has no base_url to key a lookup on."""

    def test_a_model_with_no_endpoint_still_finds_its_window(self):
        import tempfile
        import companion_config as cc
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / 'config.yaml').write_text(
                'model:\n  default: big-model\n  provider: some-oauth\n', encoding='utf-8')
            (home / 'context_length_cache.yaml').write_text(
                'context_lengths:\n  big-model@https://example.invalid/api: 272000\n', encoding='utf-8')
            tokens, source = cc.detect_context_tokens(home, home)
            self.assertEqual(tokens, 272000)
            self.assertIn('model name', source)

    def window(self, cache, config='model:\n  default: big-model\n  provider: some-oauth\n'):
        import tempfile
        import companion_config as cc
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / 'config.yaml').write_text(config, encoding='utf-8')
            (home / 'context_length_cache.yaml').write_text(
                'context_lengths:\n' + ''.join(f'  {k}: {v}\n' for k, v in cache.items()),
                encoding='utf-8')
            return cc.detect_context_tokens(home, home)

    def test_the_window_is_as_large_as_the_model_allows(self):
        """Nothing should cap this but the person running it."""
        tokens, _ = self.window({'big-model@https://a.invalid': 272000,
                                 'big-model@https://b.invalid': 131072})
        self.assertEqual(tokens, 272000)

    def test_a_server_on_this_network_does_not_set_the_window_for_a_hosted_model(self):
        """A local server is always configured with an address, and a same-named
        model behind one may be an entirely different size."""
        tokens, _ = self.window({'big-model@http://192.168.1.50:11434/v1': 8192,
                                 'big-model@https://a.invalid': 272000})
        self.assertEqual(tokens, 272000)
        for private in ('http://127.0.0.1:11434/v1', 'http://10.0.0.4:11434/v1',
                        'http://172.16.3.9:11434/v1', 'http://localhost:11434/v1'):
            with self.subTest(endpoint=private):
                tokens, source = self.window({f'big-model@{private}': 8192})
                self.assertNotEqual(tokens, 8192, 'a LAN server sized a hosted model')

    def test_an_explicit_setting_is_the_only_thing_that_caps_it(self):
        tokens, source = self.window(
            {'big-model@https://a.invalid': 272000},
            config='model:\n  default: big-model\n  provider: some-oauth\n  context_length: 65536\n')
        self.assertEqual(tokens, 65536)
        self.assertIn('config.yaml', source)


if __name__ == '__main__':
    unittest.main()
