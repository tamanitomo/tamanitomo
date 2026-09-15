"""Cross-agent access: allowed on request, contained by construction."""
import sys,json,pathlib,tempfile,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kit/scripts'))
import companion_config as cc, companion_peer as peer

def build(tmp):
    root=cc.Companion(agent='Nova',hermes_root=tmp/'.hermes',vault=tmp/'vault')
    kit=cc.Companion(agent='Kit',profile='kit',hermes_root=tmp/'.hermes',vault=tmp/'vault')
    for c in (root,kit):
        c.home.mkdir(parents=True,exist_ok=True);c.data.mkdir(parents=True,exist_ok=True)
        (c.home/'SOUL.md').write_text(f'# {c.agent}\n');c.save()
        (c.home/'skills').mkdir(exist_ok=True)
    (kit.home/'skills/tidy').mkdir(parents=True,exist_ok=True)
    (kit.home/'skills/tidy/SKILL.md').write_text('# Tidy\nA reusable procedure.\n')
    (kit.data/'notes.md').write_text('Kit note.\n')
    (kit.data/'.env').write_text('SECRET=1\n')
    return root,kit

class Args:
    def __init__(self,**kw):self.__dict__.update(kw)

class PeerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp());self.root,self.kit=build(self.tmp)

    def test_list_sees_the_other_agent_only(self):
        names=[p['name'] for p in peer.cmd_list(self.root,None)['peers']]
        self.assertEqual(names,['kit'])
        self.assertNotIn('root',[p['name'] for p in peer.cmd_list(self.root,None)['peers']])

    def test_ls_and_read_reach_skills_and_vault(self):
        out=peer.cmd_ls(self.root,Args(agent='kit',path='skills'))
        self.assertIn('tidy/',[e['name'] for e in out['entries']])
        got=peer.cmd_read(self.root,Args(agent='kit',path='vault/notes.md'))
        self.assertIn('Kit note.',got['content'])
        self.assertIn('not your memory',got['note'].lower().replace("do not adopt it as your own memory","not your memory"))

    def test_copy_lands_in_the_callers_own_tree(self):
        out=peer.cmd_copy(self.root,Args(agent='kit',path='skills/tidy/SKILL.md',
                                         dest='skills/tidy/SKILL.md',overwrite=False))
        dest=pathlib.Path(out['to'])
        self.assertTrue(dest.exists())
        self.assertTrue(str(dest).startswith(str(self.root.home/'skills')))
        self.assertIn('Borrowed from Kit',out['note'])

    def test_secrets_are_refused(self):
        for p in ('vault/.env','skills/../.env'):
            with self.assertRaises(ValueError):
                peer.cmd_read(self.root,Args(agent='kit',path=p))

    def test_traversal_is_refused(self):
        for p in ('../../../etc/passwd','vault/../../../etc/passwd','/etc/passwd'):
            with self.assertRaises(ValueError):
                peer.cmd_read(self.root,Args(agent='kit',path=p))

    def test_copy_cannot_escape_the_callers_tree(self):
        for dest in ('/etc/evil','../../../etc/evil','nowhere/x'):
            with self.assertRaises(ValueError):
                peer.cmd_copy(self.root,Args(agent='kit',path='skills/tidy/SKILL.md',
                                             dest=dest,overwrite=True))

    def test_copy_will_not_silently_overwrite(self):
        a=Args(agent='kit',path='skills/tidy/SKILL.md',dest='skills/tidy/SKILL.md',overwrite=False)
        peer.cmd_copy(self.root,a)
        with self.assertRaises(ValueError):peer.cmd_copy(self.root,a)

    def test_unknown_peer_is_a_clear_error(self):
        with self.assertRaises(ValueError):peer.cmd_ls(self.root,Args(agent='nobody',path='skills'))

    def test_every_access_is_logged(self):
        peer.cmd_ls(self.root,Args(agent='kit',path='skills'))
        peer.cmd_copy(self.root,Args(agent='kit',path='skills/tidy/SKILL.md',
                                     dest='skills/t.md',overwrite=True))
        lines=[json.loads(l) for l in (self.root.home/'peer-access.log').read_text().splitlines()]
        self.assertEqual([l['action'] for l in lines],['ls','copy'])

    def test_the_peer_tree_is_never_written_to(self):
        import hashlib
        snap=lambda: {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in self.kit.home.rglob('*') if p.is_file()}
        before=snap()
        peer.cmd_ls(self.root,Args(agent='kit',path='skills'))
        peer.cmd_copy(self.root,Args(agent='kit',path='skills/tidy/SKILL.md',
                                     dest='skills/x.md',overwrite=True))
        self.assertEqual(before,snap())


class DetectionTests(unittest.TestCase):
    def setUp(self):self.tmp=pathlib.Path(tempfile.mkdtemp())

    def write(self,home,cfg):
        home.mkdir(parents=True,exist_ok=True);(home/'config.yaml').write_text(cfg);return home

    def test_explicit_context_length_wins(self):
        h=self.write(self.tmp/'a','model:\n  default: x\n  provider: deepseek\n  context_length: 65536\n')
        self.assertEqual(cc.detect_context_tokens(h)[0],65536)

    def test_hermes_cache_is_used(self):
        h=self.write(self.tmp/'b','model:\n  default: mymodel\n  base_url: http://x/v1\n')
        (h/'context_length_cache.yaml').write_text('context_lengths:\n  mymodel@http://x/v1: 131072\n')
        tokens,how=cc.detect_context_tokens(h)
        self.assertEqual(tokens,131072);self.assertIn('cache',how)

    def test_unknown_model_uses_conservative_default(self):
        h=self.write(self.tmp/'c','model:\n  provider: anthropic\n')
        self.assertEqual(cc.detect_context_tokens(h)[0],cc.DEFAULT_CONTEXT_TOKENS)

    def test_fallback_is_safe(self):
        tokens,how=cc.detect_context_tokens(self.tmp/'missing')
        self.assertEqual(tokens,cc.DEFAULT_CONTEXT_TOKENS);self.assertIn('fallback',how)

    def test_detected_window_drives_the_budget(self):
        small=cc.Companion(context_tokens=cc.detect_context_tokens(
            self.write(self.tmp/'d','model:\n  context_length: 8192\n'))[0])
        self.assertEqual(small.tier,'tiny')


class QuietHoursTests(unittest.TestCase):
    def test_quiet_hours_reach_the_prompts(self):
        import companion_render as cr
        c=cc.Companion(agent='Nova',human='Alex',quiet_start='23:30',quiet_end='07:00')
        m=cr.mapping_for(c,'warm','none')
        for name in ('autonomy.md.tmpl','pulse.md.tmpl'):
            out=cr.render((ROOT/'kit/templates/cron'/name).read_text(),m)
            self.assertIn('23:30',out);self.assertIn('07:00',out)
            self.assertEqual(cr.unresolved(out),[])

if __name__=='__main__':unittest.main()
