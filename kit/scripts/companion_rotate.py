#!/usr/bin/env python3
"""Rotate a long append-style continuity log into dated archives. Nothing is ever deleted.

Entries are split on '## ' headings, kept if recent, otherwise appended to
soul/continuity/archive/<name>-<YYYY-MM>.md. The entry count in must equal the entry
count out or the rotation aborts and the live file is left untouched.
"""
from __future__ import annotations
import argparse, datetime as dt, os, pathlib, re, sys
from zoneinfo import ZoneInfo
from companion_platform import file_lock, atomic_write

TZ=dt.timezone.utc
DATE=re.compile(r'(20\d\d)-(\d\d)-(\d\d)')

def split_entries(text):
    """Preamble plus one string per '## ' entry, content preserved verbatim."""
    parts=re.split(r'(?m)^(?=## )',text)
    if not parts:return '',[]
    if parts[0].startswith('## '):return '',parts
    return parts[0],parts[1:]

def entry_date(entry):
    m=DATE.search(entry)
    if not m:return None
    try:return dt.date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
    except ValueError:return None

def plan(text,today,keep_days=14,keep_head=50):
    pre,entries=split_entries(text)
    cutoff=today-dt.timedelta(days=keep_days)
    keep,move=[],[]
    for i,e in enumerate(entries):
        d=entry_date(e)
        if (d is None and i<keep_head) or (d is not None and d>=cutoff):keep.append(e)
        else:move.append((d,e))
    return pre,entries,keep,move

def rotate(path,today=None,keep_days=14,keep_head=50,apply=False):
    path=pathlib.Path(path).resolve()
    today=today or dt.datetime.now(TZ).date()
    with file_lock(path.parent/('.'+path.name+'.lock')):
        text=path.read_text(encoding='utf-8')
        pre,entries,keep,move=plan(text,today,keep_days,keep_head)
        buckets={}
        for d,e in move:buckets.setdefault(d.strftime('%Y-%m') if d else 'undated',[]).append(e)
        report={'file':str(path),'entries':len(entries),'keep':len(keep),'archive':len(move),
                'buckets':{k:len(v) for k,v in sorted(buckets.items())},
                'before_chars':len(text),'after_chars':len(pre)+sum(map(len,keep)),'applied':False}
        if not apply or not move:return report
        archive=path.parent/'archive';archive.mkdir(parents=True,exist_ok=True)
        from collections import Counter
        for month,items in buckets.items():
            dest=archive/f'{path.stem}-{month}.md'
            previous=dest.read_text(encoding='utf-8') if dest.exists() else f'# {path.stem} — archive ({month})\n\n'
            # Count duplicates rather than dropping repeated but legitimate entries.
            existing=Counter(e.rstrip('\r\n') for e in split_entries(previous)[1]);needed=Counter()
            additions=[]
            for item in items:
                key=item.rstrip('\r\n');needed[key]+=1
                if needed[key]>existing[key]:additions.append(item)
            atomic_write(dest,previous+''.join(additions))
            saved=Counter(e.rstrip('\r\n') for e in split_entries(dest.read_text(encoding='utf-8'))[1])
            if any(saved[item]<count for item,count in needed.items()):raise ValueError('Archive verification failed; source retained')
        out=pre+''.join(keep)
        if len(split_entries(out)[1])!=len(keep):raise ValueError('Kept-entry mismatch; source retained')
        if path.read_text(encoding='utf-8')!=text:raise ValueError('Source changed during rotation; source retained, retry safely')
        atomic_write(path,out)
        report['applied']=True;report['after_chars']=len(out)
        return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('paths',nargs='+',type=pathlib.Path)
    p.add_argument('--keep-days',type=int,default=14);p.add_argument('--keep-head',type=int,default=50)
    p.add_argument('--apply',action='store_true',help='without this, only reports what would move')
    a=p.parse_args()
    import json
    print(json.dumps([rotate(x,keep_days=a.keep_days,keep_head=a.keep_head,apply=a.apply) for x in a.paths],indent=2))

if __name__=='__main__':main()
