#!/usr/bin/env python3
"""Prune the two directories that hold disposable working files.

Everything else in a companion's home is kept forever: ledgers are append-only,
logs rotate into dated archives, and images move to albums. Two places are
different, and only two:

  <data>/companion-life/.inputs/   prose the model staged for a --file flag
  <home>/cron/output/             Hermes's own capture of each job's stdout

Both are re-created on the next run and neither is memory. The directories are
resolved from the profile config, never taken from the command line, so this
tool cannot be aimed at anything that matters.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

DEFAULT_KEEP_DAYS=7

def targets(c):
    """The only prunable directories, by name, with the age each one keeps."""
    return [('staging inputs',c.life/'.inputs',DEFAULT_KEEP_DAYS),
            ('cron output',c.home/'cron/output',DEFAULT_KEEP_DAYS)]

def _entries(directory):
    try:return sorted(p for p in directory.iterdir() if p.is_file())
    except (FileNotFoundError,NotADirectoryError):return []

def survey(c):
    """Sizes for doctor, without touching anything."""
    out=[]
    for label,directory,keep in targets(c):
        files=_entries(directory)
        out.append({'label':label,'path':str(directory),'files':len(files),
                    'bytes':sum(p.stat().st_size for p in files),'keep_days':keep})
    return out

def prune(c,now=None,keep_days=None,apply=False):
    now=now or dt.datetime.now(dt.timezone.utc)
    report=[]
    for label,directory,keep in targets(c):
        keep=keep_days if keep_days is not None else keep
        cutoff=now-dt.timedelta(days=keep)
        removed,freed,kept=[],0,0
        for path in _entries(directory):
            stat=path.stat()
            if dt.datetime.fromtimestamp(stat.st_mtime,dt.timezone.utc)>=cutoff:
                kept+=1;continue
            removed.append(path.name);freed+=stat.st_size
            if apply:
                try:path.unlink()
                except OSError:pass
        report.append({'label':label,'path':str(directory),'keep_days':keep,'kept':kept,
                       'removed':len(removed),'freed_bytes':freed,'applied':bool(apply),
                       'names':removed[:20]})
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=pathlib.Path)
    p.add_argument('--keep-days',type=int,default=None,
                   help=f'override the {DEFAULT_KEEP_DAYS}-day window for both directories')
    p.add_argument('--apply',action='store_true',help='without this, only reports what would go')
    a=p.parse_args()
    print(json.dumps(prune(cc.load(a.home),keep_days=a.keep_days,apply=a.apply),indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
