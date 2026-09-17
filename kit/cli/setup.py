"""The lifecycle commands: init, add, remove and upgrade."""
from __future__ import annotations
import companion_config as cc
import companion_platform as cp
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid
import companion_wizard as wiz
from .common import input, print, resolve
from .doctor import cmd_doctor
from .questions import apply_answers, ask, questionnaire, read_answers
from .roster import existing_vault, pick_agent
from .scaffold import finish, scaffold

def cmd_init(args):
    c=resolve(args)
    if (c.home/cc.CONFIG_NAME).exists() and not args.force:
        sys.exit(f'{c.home} is already a companion — use `tamanitomo doctor`, or --force to re-scaffold')
    raw=read_answers(args)
    ans=questionnaire(c,raw)
    c=apply_answers(c,ans)
    if getattr(args,'vault',None):c=cc.dataclasses.replace(c,vault=pathlib.Path(args.vault).expanduser().absolute())
    report=[f'{ans["agent"]} — {c.home}']
    scaffold(c,ans,report,soul_mode='create',raw=raw)
    finish(c,report)
def hermes_create_profile(name,hermes_root,report,description=''):
    """Let Hermes create the profile. It does more than mkdir: canonicalises and
    validates the name, refuses reserved ones, bootstraps skills, installs the
    wrapper script, and seeds a 0600 .env so the profile does not silently
    inherit shell API keys. Reimplementing that would drift from Hermes."""
    cmd=cp.hermes_command('profile','create',name)
    if os.environ.get('COMPANION_APP_CLIENT')=='1':cmd+=['--no-alias']
    if description:cmd+=['--description',description]
    # Hermes anchors the profiles root to HERMES_HOME, so pin it or it will create
    # the profile under the real ~/.hermes no matter which home we were given.
    env={**os.environ,'HERMES_HOME':str(hermes_root)}
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=180,env=env)
    except (OSError,subprocess.SubprocessError) as e:
        report.append(f'  ! could not run `hermes profile create` ({e}); setup stopped')
        return False
    expected=pathlib.Path(hermes_root)/'profiles'/name
    if r.returncode==0 and expected.is_dir():
        report.append(f'  profile: created by `hermes profile create {name}`')
        return True
    if r.returncode==0:
        report.append(f'  ! `hermes profile create` reported success but {expected} does not exist;')
        report.append('    setup stopped')
        return False
    err=(r.stderr or r.stdout or '').strip().splitlines()
    report.append('  ! `hermes profile create` failed: '+(err[-1] if err else f'exit {r.returncode}'))
    report.append('    setup stopped; run `hermes profile create` yourself if')
    report.append('    you want the wrapper script and seeded .env')
    return False
def cmd_add(args):
    base=resolve(args)
    name=cp.profile_name(args.name)
    home=cp.profile_path(base.hermes_root,name)
    if home.exists():sys.exit(f'{name} already exists at {home}; use upgrade to adopt it')
    c=cc.Companion(profile=name,hermes_root=base.hermes_root,vault=base.vault)
    shared=existing_vault(base.hermes_root)
    raw=read_answers(args)
    ans=questionnaire(c,raw,vault_default=shared)
    c=apply_answers(c,ans)
    if args.vault:c=cc.dataclasses.replace(c,vault=pathlib.Path(args.vault).expanduser().absolute())
    report=[f'{ans["agent"]} — new profile {name} at {c.home}']
    if c.canonical_soul.exists():raise ValueError(f'A vault identity already exists at {c.canonical_soul}; resolve it before reusing this profile name')
    if not home.exists():
        if not hermes_create_profile(name,base.hermes_root,report,f"{ans['agent']}: companion agent"):
            raise ValueError("Hermes profile creation failed; no companion scaffold was written. Check your Hermes installation.")
    scaffold(c,ans,report,soul_mode='create',raw=raw)
    finish(c,report)
def removal_plan(home):
    """Where this agent's life is kept, and whether it sits inside the directory
    removal would take. A vault under the profile home turns an archive into a
    silent data loss and a purge into an unrecoverable one."""
    if not (home/cc.CONFIG_NAME).exists():return None,None,None
    try:c=cc.load(home)
    except (ValueError,OSError):return None,None,None
    inside=None
    try:
        c.data.resolve().relative_to(home.resolve());inside=c.data
    except (ValueError,OSError):pass
    return c.data,c.vault,inside
def removal_screen(name,agent,home,data,inside,purge):
    """Say exactly what goes and what stays before anything is touched."""
    wiz.rule('Remove '+(agent or name))
    print('  '+wiz.C.dim('profile   ')+str(home))
    if data:print('  '+wiz.C.dim('its life  ')+str(data)+('' if inside else '   '+wiz.C.dim('(outside the profile)')))
    print()
    if purge:
        print('  '+wiz.C.red(wiz.C.bold('PURGE — this deletes the profile permanently.')))
        print('  '+wiz.C.red('  Its SOUL, memories, sessions and ledgers go with it.'))
        print('  '+wiz.C.red('  There is no archive and no undo.'))
    else:
        print('  '+wiz.C.yellow(wiz.C.bold('ARCHIVE — the profile is moved aside, not deleted.')))
        print('  '+wiz.C.dim('  You can move it back, or delete it yourself once you are sure.'))
    if data and not inside:
        print('  '+wiz.C.dim('  Vault data at the path above is left where it is.'))
    print()
def cmd_remove(args):
    base=resolve(args)
    name=cp.profile_name(args.name)
    home=cp.profile_path(base.hermes_root,name)
    if not home.exists():sys.exit(f'no profile at {home}')
    if not args.force:
        sys.exit(f'refusing to remove {name} without --force.\n'
                 f'  This holds its SOUL, memories, sessions and ledgers at {home}')
    data,vault,inside=removal_plan(home)
    agent=''
    try:agent=cc.load(home).agent
    except (ValueError,OSError):pass
    if inside is not None:
        sys.exit(f'refusing to remove {name}: its vault data lives inside the profile.\n'
                 f'  {inside}\n'
                 f'  Removing the profile would take the ledgers, episodes and people files with\n'
                 f'  it. Move the vault outside {home} first, or copy it somewhere safe.')
    removal_screen(name,agent,home,data,inside,args.purge)
    if args.purge and sys.stdin.isatty():
        typed=input('  '+wiz.C.bold(f'Type {name} to purge it permanently, or anything else to cancel: ')).strip()
        if typed!=name:
            print('\n  '+wiz.C.dim('cancelled. Nothing was removed.'));return 1
    stamp=dt.datetime.now().strftime('%Y%m%dT%H%M%S')
    dest=base.hermes_root/'profiles-removed'/f'{name}-{stamp}-{uuid.uuid4().hex[:8]}'
    dest.parent.mkdir(parents=True,exist_ok=True)
    if args.purge:
        shutil.rmtree(home);print(f'purged {home}')
    else:
        shutil.move(str(home),str(dest))
        print(f'archived {name} -> {dest}\nNothing was deleted. Remove that directory yourself when sure.')
    if data:print(f'its life is still at {data}')
def cmd_upgrade(args):
    if not args.home and not os.environ.get('COMPANION_HOME'):
        root=pathlib.Path(cp.default_home())
        args.home=pick_agent(root,json.loads(args.answers) if args.answers else None,'upgrade')
    c=resolve(args)
    if not c.soul.exists():
        sys.exit(f'no SOUL.md at {c.soul} — this does not look like a Hermes agent.\n'
                 f'Make the agent in Hermes first, then run upgrade.')
    if (c.home/cc.CONFIG_NAME).exists() and not args.force:
        print(f'{c.home} is already a companion. Nothing to do.')
        return cmd_doctor(args)
    print(f'Adopting the existing agent at {c.home}')
    print(f'Its SOUL.md is {len(c.soul.read_text(encoding="utf-8"))} chars and will NOT be overwritten by default.')
    shared=existing_vault(c.hermes_root,exclude=c.home)
    raw=read_answers(args)
    ans=questionnaire(c,raw,vault_default=shared)
    mode=args.soul or ask('What should happen to the existing SOUL.md?',3,
        [('append','Append the kit scaffold below it, then merge by hand'),
         ('replace','Replace it entirely with a fresh scaffold (a backup is kept)'),
         ('keep','Keep your SOUL text (recommended; only the self-authored block marker is added)')],
        json.loads(args.answers) if args.answers else None,'soul')
    c=apply_answers(c,ans)
    if args.vault:c=cc.dataclasses.replace(c,vault=pathlib.Path(args.vault).expanduser().absolute())
    report=[f'{ans["agent"]} — upgraded {c.home}']
    scaffold(c,ans,report,soul_mode={'append':'append','replace':'replace','keep':'keep'}[mode],raw=raw)
    extra=[]
    if mode=='append':
        extra.append(('Merge the appended scaffold into your original SOUL by hand — two identities '
                      'in one file will read as an inconsistent character',c.soul))
    finish(c,report,extra)
