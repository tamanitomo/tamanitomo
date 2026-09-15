#!/usr/bin/env python3
"""Bounded journal reads and idempotent appends to the companion's known logs."""
from __future__ import annotations
import argparse,datetime as dt,json,pathlib,re,sys
from companion_platform import file_lock,atomic_write
import companion_config as cc

TARGETS={'daily':'Lifelog.md','weekly':'reflections/weekly.md',
         'monthly':'reflections/monthly.md','autonomy':'continuity/Autonomy.md'}

def path_for(c,target):
    if target not in TARGETS:raise ValueError('unknown journal target')
    path=(c.soul_dir/TARGETS[target]).resolve()
    if not path.is_relative_to(c.soul_dir.resolve()):raise ValueError('journal target escapes the companion soul directory')
    return path

def tail(c,target,limit=6000):
    if not 500<=limit<=16000:raise ValueError('limit must be 500–16000 characters')
    path=path_for(c,target)
    body=path.read_text(encoding='utf-8') if path.exists() else ''
    text=body[-limit:]
    return {'path':str(path),'total_chars':len(body),'omitted_chars':max(0,len(body)-len(text)),
            'text':text,'note':'Older text is retained in the file; this is only its tail.'}

def append(c,target,data):
    if not isinstance(data,dict):raise ValueError('input must be a JSON object')
    day=dt.date.fromisoformat(data.get('date','')).isoformat()
    text=data.get('text','')
    if not isinstance(text,str) or not text.strip() or len(text)>8000:raise ValueError('text must be 1–8000 characters')
    text=text.strip()
    if re.search(r'^#{1,2}\s',text,re.M):raise ValueError('provide body text only; the helper writes the date heading')
    if '<!-- companion-journal:' in text:raise ValueError('journal markers are reserved')
    ident=data.get('id') if target=='autonomy' else target+'-'+day
    if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',ident):raise ValueError('autonomy requires a unique id of 1–100 letters, digits, dots, underscores or hyphens')
    path=path_for(c,target);path.parent.mkdir(parents=True,exist_ok=True)
    marker='<!-- companion-journal:'+ident+' -->'
    end='<!-- /companion-journal:'+ident+' -->'
    entry=f'## {day}\n{marker}\n{text}\n{end}\n'
    with file_lock(path.parent/('.'+path.name+'.lock')):
        old=path.read_text(encoding='utf-8') if path.exists() else ''
        if marker in old:
            saved=old.split(marker,1)[1].split(end,1)[0].strip()
            if saved!=text:raise ValueError('entry id already exists with different text; original retained')
            return {'written':False,'id':ident,'path':str(path),'reason':'entry already recorded'}
        if target!='autonomy' and re.search(r'^## '+re.escape(day)+r'(?:\s|$)',old,re.M):
            return {'written':False,'id':ident,'path':str(path),'reason':'this date already has an entry; existing journal retained'}
        atomic_write(path,old.rstrip()+'\n\n'+entry if old.strip() else entry)
    return {'written':True,'id':ident,'path':str(path),'date':day}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',type=pathlib.Path)
    sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('tail','append'):
        q=sub.add_parser(name);q.add_argument('--target',required=True,choices=TARGETS)
        if name=='tail':q.add_argument('--limit',type=int,default=6000)
        else:q.add_argument('--file',required=True,type=pathlib.Path)
    a=p.parse_args();c=cc.load(a.home)
    out=tail(c,a.target,a.limit) if a.cmd=='tail' else append(c,a.target,json.loads(a.file.read_text(encoding='utf-8')))
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,TypeError) as exc:
        print(json.dumps({'error':str(exc)}),file=sys.stderr);sys.exit(1)
