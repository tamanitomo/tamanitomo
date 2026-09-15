#!/usr/bin/env python3
"""Run fixed local housekeeping before optional agent loop review."""
import argparse,datetime as dt,json,pathlib,sys
from zoneinfo import ZoneInfo
import companion_config as cc
import companion_memory as memory
import companion_rotate as rotate
import companion_prune as prune
import companion_self as slf
import companion_context as context
import companion_loops as loops

def run(c,now=None,apply=False):
    now=now or dt.datetime.now(ZoneInfo(c.timezone));reports=[]
    # Inspect every journal before making any rotation. Undated headings need a
    # human/agent repair, never an automatic move into an undated archive.
    targets=[(c.soul_dir/'continuity/Autonomy.md',7),(c.soul_dir/'Lifelog.md',180)]
    for path,days in targets:
        if not path.exists():continue
        if path.is_symlink():raise ValueError('Linked journal is not a housekeeping target')
        entries=rotate.split_entries(path.read_text(encoding='utf-8'))[1]
        if any(rotate.entry_date(e) is None for e in entries):raise ValueError('Undated journal heading: '+str(path))
        report=rotate.rotate(path,today=now.date(),keep_days=days)
        if report['entries']!=report['keep']+report['archive']:raise ValueError('Rotation count mismatch')
        reports.append((path,days,report))
    result={'mode':'apply' if apply else 'preview','rotation':[],'memory':memory.status(c),'prune':prune.prune(c,now=now),'soul':slf.soul_show(c),'open_loops':loops.loops(c,None)}
    if apply:
        result['memory_maintenance']=memory.maintain(c)
        result['rotation']=[rotate.rotate(p,today=now.date(),keep_days=d,apply=True) for p,d,_ in reports]
        result['prune']=prune.prune(c,now=now,apply=True)
        if any(r['removed'] for r in prune.prune(c,now=now)):raise ValueError('Some expired working files could not be removed')
    else:result['rotation']=[r for _,_,r in reports]
    built=context.build(c,now=now)
    if not isinstance(built,str) or not built.strip():raise ValueError('Continuity builder returned no context')
    result['continuity_check']={'status':'ok','chars':len(built)}
    # The agent sees headroom and loops; avoid returning the whole SOUL twice.
    result['soul']={k:v for k,v in result['soul'].items() if k!='self_authored'}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',type=pathlib.Path);p.add_argument('--apply',action='store_true');a=p.parse_args()
    print(json.dumps(run(cc.load(a.home),apply=a.apply),ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'status':'failed','error':str(e)}),file=sys.stderr);sys.exit(1)
