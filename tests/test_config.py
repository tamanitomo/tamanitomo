"""Profile resolution and context budgeting."""
import sys,pathlib,json,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'kit/scripts'))
import companion_config as cc

WINDOWS=[2048,4096,8192,16384,32768,65536,131072,200192,272000,900000]

class BudgetTests(unittest.TestCase):
    def test_allocation_never_exceeds_the_cap(self):
        for ctx in WINDOWS:
            b=cc.Companion(context_tokens=ctx).budgets()
            used=sum(v for k,v in b.items() if k!='total')
            self.assertLessEqual(used,b['total'],f'overspent at {ctx}')

    def test_rules_and_tail_are_always_reserved(self):
        for ctx in WINDOWS:
            b=cc.Companion(context_tokens=ctx).budgets()
            self.assertGreater(b['rules'],0);self.assertGreater(b['tail'],0)

    def test_priority_is_respected_when_sections_compete(self):
        for ctx in WINDOWS:
            b=cc.Companion(context_tokens=ctx).budgets()
            present=[k for k in cc._PRIORITY if b[k]]
            vals=[b[k] for k in present]
            self.assertEqual(vals,sorted(vals,reverse=True),f'inverted at {ctx}: {b}')

    def test_small_windows_drop_sections_rather_than_starve_them(self):
        tiny=cc.Companion(context_tokens=4096).budgets()
        kept=[k for k in cc._PRIORITY if tiny[k]]
        self.assertLess(len(kept),len(cc._PRIORITY))
        self.assertIn('loops',kept)                     # highest priority survives
        for k in kept:self.assertGreaterEqual(tiny[k],cc._MIN_USEFUL)

    def test_big_windows_keep_every_section(self):
        big=cc.Companion(context_tokens=272000).budgets()
        for k in cc._PRIORITY:self.assertGreater(big[k],0)

    def test_soul_cap_matches_the_hermes_rule_including_its_floor(self):
        self.assertEqual(cc.soul_cap(8192),20_000)          # floor
        self.assertEqual(cc.soul_cap(131072),31_457)        # measured against live Hermes
        self.assertEqual(cc.soul_cap(272000),65_280)
        self.assertEqual(cc.soul_cap(10_000_000),500_000)   # ceiling
        self.assertLess(cc.Companion(context_tokens=131072).soul_warn,cc.soul_cap(131072))

    def test_injection_is_clamped_both_ends(self):
        self.assertEqual(cc.injection_cap(1000),cc.INJECTION_MIN)
        self.assertEqual(cc.injection_cap(9_000_000),cc.INJECTION_MAX)

    def test_tiers(self):
        self.assertEqual(cc.tier(8192),'tiny');self.assertEqual(cc.tier(32768),'small')
        self.assertEqual(cc.tier(131072),'medium');self.assertEqual(cc.tier(272000),'large')
        self.assertTrue(cc.Companion(context_tokens=8192).compact)
        self.assertFalse(cc.Companion(context_tokens=272000).compact)


class ProfileTests(unittest.TestCase):
    def setUp(self):self.tmp=pathlib.Path(tempfile.mkdtemp())

    def test_root_and_profile_homes_resolve_differently(self):
        root=cc.Companion(hermes_root=self.tmp/'.hermes')
        rowan=cc.Companion(profile='rowan',hermes_root=self.tmp/'.hermes')
        self.assertTrue(root.is_root);self.assertFalse(rowan.is_root)
        self.assertEqual(root.home,self.tmp/'.hermes')
        self.assertEqual(rowan.home,self.tmp/'.hermes/profiles/rowan')

    def test_profiles_get_isolated_data_subtrees(self):
        v=self.tmp/'vault'
        root=cc.Companion(vault=v);rowan=cc.Companion(profile='rowan',vault=v)
        self.assertEqual(root.data,v)
        self.assertEqual(rowan.data,v/'agents/rowan')
        self.assertNotEqual(root.life,rowan.life)
        self.assertFalse(str(rowan.life).startswith(str(root.life)+'/'))

    def test_config_inside_a_profile_dir_pins_that_profile(self):
        home=self.tmp/'.hermes/profiles/nova'
        home.mkdir(parents=True)
        (home/cc.CONFIG_NAME).write_text(json.dumps({'agent':'Nova'}))
        c=cc.load(home)
        self.assertEqual(c.profile,'nova')
        self.assertEqual(c.home,home)

    def test_missing_config_yields_safe_defaults(self):
        c=cc.load(self.tmp/'nothing-here')
        self.assertEqual(c.context_tokens,cc.DEFAULT_CONTEXT_TOKENS)
        self.assertEqual(c.image_mode,'none')

    def test_corrupt_config_fails_instead_of_using_unrelated_defaults(self):
        home=self.tmp/'h';home.mkdir()
        (home/cc.CONFIG_NAME).write_text('{not json')
        with self.assertRaisesRegex(ValueError,'Invalid companion configuration'):cc.load(home)

    def test_save_load_roundtrip(self):
        home=self.tmp/'.hermes'
        c=cc.Companion(agent='Nova',human='Alex',context_tokens=65536,
                       hermes_root=home,vault=self.tmp/'vault',image_mode='codex')
        c.save()
        back=cc.load(home)
        self.assertEqual((back.agent,back.human,back.context_tokens,back.image_mode),
                         ('Nova','Alex',65536,'codex'))

    def test_human_dir_is_slugged_safely(self):
        for name,want in (('Alex','alex'),('Mary Jane','mary-jane'),('','human'),('../etc','etc'),('..','human'),('/','human')):
            c=cc.Companion(human=name,vault=self.tmp)
            self.assertEqual(c.human_dir.name,want)
            self.assertTrue(str(c.human_dir).startswith(str(self.tmp)))

    def test_pronouns(self):
        self.assertEqual(cc.Companion(pronoun_set='he').subj(),'he')
        self.assertEqual(cc.Companion(pronoun_set='she').poss(),'her')
        with self.assertRaisesRegex(ValueError,'Invalid pronouns'):cc.Companion(pronoun_set='nonsense')
        # Plural pronouns are not offered: the prose is written for singular verbs.
        with self.assertRaisesRegex(ValueError,'Invalid pronouns'):cc.Companion(pronoun_set='they')
        self.assertEqual(set(cc.PRONOUNS),{'he','she'})
        self.assertEqual(cc.Companion().pronoun_set,'she')

if __name__=='__main__':unittest.main()


class HomeInvariantTests(unittest.TestCase):
    """load(X).home must equal X. Violating this once wrote into a real install."""
    def test_arbitrary_home_is_never_replaced_by_a_default(self):
        for rel in ('sandbox/.hermes','a/b/c/.hermes','weird-name','.hermes'):
            tmp=pathlib.Path(tempfile.mkdtemp())/rel
            c=cc.load(tmp)
            self.assertEqual(c.home,tmp)
            self.assertEqual(c.hermes_root,tmp)
            self.assertEqual(c.profile,'')
            self.assertNotEqual(c.home,pathlib.Path.home()/'.hermes')

    def test_profile_home_round_trips(self):
        tmp=pathlib.Path(tempfile.mkdtemp())
        home=tmp/'.hermes/profiles/nova'
        c=cc.load(home)
        self.assertEqual(c.home,home);self.assertEqual(c.profile,'nova')
        self.assertEqual(c.hermes_root,tmp/'.hermes')

    def test_a_stale_stored_root_cannot_redirect_writes(self):
        tmp=pathlib.Path(tempfile.mkdtemp());home=tmp/'.hermes';home.mkdir(parents=True)
        (home/cc.CONFIG_NAME).write_text(json.dumps(
            {'agent':'Nova','hermes_root':'/somewhere/else','vault':str(tmp/'vault')}))
        c=cc.load(home)
        self.assertEqual(c.home,home)                      # path wins over stored value
        self.assertEqual(c.agent,'Nova')                   # other fields still load
        self.assertEqual(c.vault,tmp/'vault')

class DynamicContextTests(unittest.TestCase):
    def test_reload_follows_model_changes_and_fixed_mode_preserves_override(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)
            (home/'companion.json').write_text(json.dumps({'context_tokens':65536}))
            (home/'config.yaml').write_text('model:\n  default: first\n  provider: example\n  base_url: https://api.example.test/v1\n')
            (home/'models_dev_cache.json').write_text(json.dumps({'example':{'api':'https://api.example.test','models':{
                'first':{'limit':{'context':1000000}},'second':{'limit':{'context':8192}}}}}))
            self.assertEqual(cc.load(home).context_tokens,1000000)
            (home/'config.yaml').write_text('model:\n  default: second\n  provider: example\n  base_url: https://api.example.test/v1\n')
            self.assertEqual(cc.load(home).context_tokens,8192)
            (home/'companion.json').write_text(json.dumps({'context_tokens':32768,'context_mode':'fixed'}))
            self.assertEqual(cc.load(home).context_tokens,32768)

    def test_other_endpoints_do_not_inherit_native_model_capacity(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)
            (home/'config.yaml').write_text('model:\n  default: first\n  provider: example\n  base_url: https://other.example.test/v1\n')
            (home/'context_length_cache.yaml').write_text('context_lengths:\n  first@https://api.example.test/v1: 1000000\n')
            (home/'models_dev_cache.json').write_text(json.dumps({'example':{'api':'https://api.example.test','models':{'first':{'limit':{'context':1000000}}}}}))
            value,source=cc.detect_context_tokens(home)
            self.assertFalse(cc.detected_for_real(source))
            (home/'config.yaml').write_text('model:\n  context_length: 8192\n')
            self.assertEqual(cc.detect_context_tokens(home)[0],8192)


class RemotePinTests(unittest.TestCase):
    def test_valid_pins_are_accepted(self):
        c1=cc.Companion(remote_pin='1234')
        self.assertEqual(c1.remote_pin,'1234')
        c2=cc.Companion(remote_pin='0000')
        self.assertEqual(c2.remote_pin,'0000')
        c3=cc.Companion(remote_pin='')
        self.assertEqual(c3.remote_pin,'')

    def test_invalid_pins_raise_value_error(self):
        for bad in ('123','12345','abcd','12a4','','-123',' 123'):
            if bad=='':continue
            with self.assertRaises(ValueError):
                cc.Companion(remote_pin=bad)

    def test_remote_pin_serializes_and_round_trips(self):
        tmp=pathlib.Path(tempfile.mkdtemp())
        home=tmp/'.hermes'
        c=cc.Companion(hermes_root=home,remote_pin='9876')
        c.save()
        loaded=cc.load(c.home)
        self.assertEqual(loaded.remote_pin,'9876')

