"""Synthetic real-HTTP + actual client-script cache tests. Never point at a live home.

Usage: TMPDIR=<supported fixture filesystem> python run_cache_witness.py <repo> --out <evidence-dir>
The repository's existing Server fixture creates/disposes every home. No owner profile is an input.
Node executes the unmodified store/controller/renderer item code; this is NOT a browser test.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,subprocess,sys

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo',type=pathlib.Path)
    parser.add_argument('--out',required=True,type=pathlib.Path)
    args=parser.parse_args();repo=args.repo.resolve();args.out.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(repo),str(repo/'kit/scripts'),str(repo/'tests')]
    from tests.phase1b_c3.fixture import Server
    from tests.test_chat_trusted_integration import seed_mixed,T
    from kit.app import chat_sources
    script=pathlib.Path(__file__).with_name('cache_witness.cjs')
    results=[]
    expected={'revocation_success':False,'outage_only':True,'invalidated_outage':False,'revocation_outage':False}
    for mode,want_marker in expected.items():
        server=Server()
        try:
            db=seed_mixed(server.companions['nova'])
            for i in range(70):
                db.say('term','user',f'Old synthetic line {i}',T-100000+i*60)
            source=server.home()/'state.db';before=hashlib.sha256(source.read_bytes()).hexdigest()
            env=os.environ.copy();env['WITNESS_BINDING_PATH']=str(server.home()/chat_sources.BINDING_FILE)
            done=subprocess.run(['node',str(script),str(repo),server.base,str(server.home()),mode],
                                env=env,text=True,capture_output=True,timeout=30)
            if done.returncode:raise RuntimeError(f'{mode}: Node failed\n{done.stderr}')
            result=json.loads(done.stdout)
            result['source_bytes_preserved']=hashlib.sha256(source.read_bytes()).hexdigest()==before
            result['durable_sends']=len(server.sends())
            result['expected_marker_retained']=want_marker
            result['passed']=(result['markerStillInRendererItems']==want_marker and
                result['markerRetainedInStore']==want_marker and result['pendingPreserved'] and
                result['draftPreserved'] and result['source_bytes_preserved'] and result['durable_sends']==0)
            results.append(result)
        finally:server.close()
    report={'boundary':'Actual uvicorn/HTTP/projection + Node executing actual store/controller/renderer item code; no browser or live Hermes',
            'cases':results,'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results)}
    (args.out/'cache_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failed':report['failed']}))
    return 0 if report['failed']==0 else 1
if __name__=='__main__':raise SystemExit(main())
