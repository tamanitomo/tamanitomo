"""The synthetic provider behaves exactly as each scenario says.

BOUNDARY: provider transport (HTTP + SSE to 127.0.0.1). These tests prove the
fixture; they do not claim Hermes or the workspace handles these cases yet --
that is the Phase 2 integration work this fixture exists for.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mock_provider import MockProvider, PUBLIC_TEXT, consume, scenarios  # noqa: E402


class MockProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = MockProvider().__enter__();self.addCleanup(self.provider.__exit__)

    def run_scenario(self, name):
        return consume(self.provider.url, self.provider.token, name)

    def test_multiple_real_deltas_then_completion(self):
        out = self.run_scenario('deltas')
        self.assertGreater(len(out['public']), 3)
        self.assertEqual(''.join(out['public']), PUBLIC_TEXT)
        self.assertEqual((out['finish'], out['done'], out['error']), ('stop', True, None))

    def test_a_delayed_first_public_delta(self):
        out = self.run_scenario('delayed_first_delta')
        self.assertGreaterEqual(out['first_delta_after'], 0.25)
        self.assertEqual(''.join(out['public']), PUBLIC_TEXT)

    def test_non_public_fields_are_separate_from_public_text(self):
        out = self.run_scenario('mixed_fields')
        self.assertEqual(''.join(out['public']), PUBLIC_TEXT)
        self.assertNotIn('PRIVATE', ''.join(out['public']))
        self.assertEqual(set(out['hidden']), {'reasoning_content', 'reasoning', 'tool_calls'})

    def test_unicode_split_across_transport_writes(self):
        steps = scenarios()['unicode_split']
        with self.assertRaises(UnicodeDecodeError):steps[0].decode('utf-8')   # the cut really is mid-character
        out = self.run_scenario('unicode_split')
        self.assertEqual(''.join(out['public']), 'Café at night \U0001F319 — done.')
        self.assertEqual(self.run_scenario('line_split')['public'], ['byte by byte'])

    def test_truncation_and_malformed_responses_are_reported(self):
        truncated = self.run_scenario('truncated')
        self.assertEqual((truncated['finish'], ''.join(truncated['public'])), ('length', PUBLIC_TEXT[:15]))
        malformed = self.run_scenario('malformed')
        self.assertTrue(malformed['error'].startswith('malformed:'))
        self.assertEqual(''.join(malformed['public']), 'Before the bad line. ', 'what arrived before is kept')

    def test_disconnect_before_and_after_completion(self):
        before = self.run_scenario('disconnect_before_done')
        self.assertEqual((before['error'], before['done'], before['finish']), ('disconnected', False, None))
        self.assertTrue(PUBLIC_TEXT.startswith(''.join(before['public'])) and before['public'])
        after = self.run_scenario('disconnect_after_done')
        self.assertEqual((after['error'], after['done'], ''.join(after['public'])), (None, True, PUBLIC_TEXT))

    def test_connection_recovery(self):
        first, second = self.run_scenario('recover'), self.run_scenario('recover')
        self.assertEqual(first['error'], 'disconnected')
        self.assertEqual((second['error'], ''.join(second['public'])), (None, PUBLIC_TEXT))
        self.assertEqual([r for r in self.provider.requests if r[0] == 'recover'], [('recover', True, 1), ('recover', True, 2)])

    def test_deterministic_local_and_token_guarded(self):
        strip = lambda out: {k: v for k, v in out.items() if k != 'first_delta_after'}
        self.assertEqual(strip(self.run_scenario('mixed_fields')), strip(self.run_scenario('mixed_fields')))
        self.assertEqual(self.provider.server.server_address[0], '127.0.0.1')
        self.assertEqual(consume(self.provider.url, 'wrong', 'deltas')['status'], 401)
        other = MockProvider()
        self.assertNotEqual(other.token, self.provider.token, 'a new token every run')

    def test_hermes_config_disables_every_fallback(self):
        text = self.provider.hermes_config('deltas')
        self.assertIn(f'base_url: {self.provider.url}', text)
        self.assertIn('fallback_providers: []', text);self.assertIn('transport_fallback: deny', text)
        self.assertNotIn('fallback_model', text)
        self.assertNotIn(self.provider.token, text, 'the key goes in the synthetic .env, not the config')


if __name__ == '__main__':
    unittest.main()
