"""`tamanitomo restore` — the way back from a bad edit.

Everything a companion is made of is plain text in one folder, and a job commits
that folder every fifteen minutes. This is the front door to that history: list
what a file used to be, and put an old version back beside the current one so a
person can compare them before deciding.
"""
from __future__ import annotations
import argparse
import companion_wizard as wiz
import json
import pathlib
from .common import print, resolve

def cmd_restore(args):
    """List or recover earlier versions of a file in the vault."""
    import companion_vault as vault
    c=resolve(args,require_config=True)
    root=pathlib.Path(c.vault)
    target=pathlib.Path(args.path)
    if target.is_absolute():
        try:relative=str(target.resolve().relative_to(root.resolve()))
        except ValueError:
            raise ValueError(f'{target} is not inside the vault at {root}')
    else:relative=str(target)
    state=vault.init(c)
    if not state.get('ready'):
        print(f"No vault history available: {state.get('reason')}")
        return 1
    versions=vault.history(c,relative,limit=args.limit)
    if not versions:
        print(f'No recorded history for {relative}. The vault repo may be newer than the file.')
        return 1
    if not args.commit:
        print(f'{relative} — {len(versions)} recorded version(s), newest first')
        for row in versions:
            print(f"  {row['commit'][:8]}  {row['at'][:16].replace('T',' ')}  {row['message']}")
        print()
        print(wiz.C.dim('  Recover one with:  companion restore <path> --commit <id>'))
        print(wiz.C.dim('  It lands beside the current file, never over it.'))
        return 0
    result=vault.restore(c,relative,args.commit)
    print(f"Wrote {result['restored']}")
    print(wiz.C.dim('  '+result['note']))
    return 0
