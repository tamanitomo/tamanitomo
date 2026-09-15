"""The interactive roster menu shown when no command is given."""
from __future__ import annotations
import argparse
import companion_config as cc
import companion_platform as cp
import pathlib
import sys
import companion_wizard as wiz
from .catalogs import cmd_catalog
from .common import input, print
from .doctor import cmd_doctor
from .questions import ask
from .roster import agent_rows, confirm_removal, menu_pick, print_roster
from .settings import settings_screen
from .setup import cmd_add, cmd_remove, cmd_upgrade

def menu(hermes_root):
    while True:
        wiz.clear()
        wiz.banner()
        print(wiz.C.dim(f'  {hermes_root}'))
        rows=agent_rows(hermes_root)
        print_roster(rows)
        unset=[r for r in rows if not r['set_up']]
        print('\n  '+wiz.C.bold('What would you like to do?'))
        opts=[]
        if unset:opts.append(('adopt','Set up an existing agent'))
        opts+=[('manage','Manage an installed companion'),('add','Create a new agent'),('catalog','Explore character options'),('doctor','Check an agent'),
               ('remove','Remove an agent'),('quit','Quit')]
        descriptions={'manage':'Quiet hours, how often they message first, timezone, images.', 'catalog':'Browse the wardrobe, personality and art catalogs.', 'adopt':'Preserve an identity and add continuity.', 'add':'Build a personality in a separate Hermes profile.',
                      'doctor':'Check memory, hooks and scheduled jobs.', 'remove':'Archive a profile; keep its vault data.', 'quit':'Return to your terminal.'}
        roster='\n'.join(f"{r['agent']} ({r['name']}) — "+('installed' if r['set_up'] else 'ready to set up') for r in rows)
        action=wiz.choose('Companion setup',[(label+' — '+descriptions[key],key) for key,label in opts],
                          allow_write=False,allow_skip=False,note=roster)
        try:
            if action=='quit':return 0
            if action=='catalog':
                gender=ask('Browse male or female choices?',2,[('male','Male'),('female','Female')])
                cmd_catalog(argparse.Namespace(gender=gender,category=None))
            elif action=='adopt':
                r=menu_pick(rows,'Which agent?',only_set_up=False)
                if r:cmd_upgrade(argparse.Namespace(home=r['home'],answers=None,force=False,
                                                    soul=None,vault=None))
            elif action=='add':
                name=input('\n  '+wiz.C.bold('Short name for the new agent (lowercase): ')).strip()
                if name:cmd_add(argparse.Namespace(home=hermes_root,name=name,answers=None,vault=None))
            elif action=='manage':
                r=menu_pick(rows,'Which companion?',only_set_up=True)
                if r:settings_screen(cc.load(r['home']))
            elif action=='doctor':
                r=menu_pick(rows,'Which agent?',only_set_up=True)
                if r:cmd_doctor(argparse.Namespace(home=r['home']))
            elif action=='remove':
                r=menu_pick(rows,'Which agent?')
                if r and r['is_root']:
                    print('\n  '+wiz.C.red('  The root agent cannot be removed from here.'))
                elif r and confirm_removal(r):
                    cmd_remove(argparse.Namespace(home=hermes_root,name=r['name'],
                                                  force=True,purge=False))
                elif r:
                    print('\n  '+wiz.C.dim('  cancelled.'))
        except (ValueError,OSError) as e:
            print(wiz.C.red(f'Error: {e}'))
        except SystemExit as e:
            if e.code:print('\n  '+wiz.C.red(f'  {e}'))
        input('\n  '+wiz.C.dim('press Enter to return to the menu'))
def cmd_menu(args):
    root=pathlib.Path(args.home or cp.default_home())
    if root.parent.name=='profiles':root=root.parent.parent
    if not sys.stdin.isatty():
        for r in agent_rows(root):
            print(f"{r['name']}\t{r['agent']}\t{'set-up' if r['set_up'] else 'not-set-up'}")
        return 0
    return menu(root)
