"""Argument parsing and the top-level error handling.

The help text below is what `tamanitomo --help` prints, so it lives here rather
than in the entry point script."""

from __future__ import annotations

USAGE="""tamanitomo — set up, adopt, inspect and remove Hermes companion agents.

    tamanitomo init                first-time setup on this Hermes home
    tamanitomo add <name>          another agent alongside an existing one
    tamanitomo remove <name>       archive an agent (never the root without --force)
    tamanitomo upgrade             adopt an EXISTING Hermes agent into the kit
    tamanitomo doctor              check an install and report context budgets
"""

from . import __version__
import argparse
import pathlib
import sys
from .common import print
from .catalogs import cmd_catalog
from .doctor import cmd_doctor, cmd_repair
from .menu import cmd_menu
from .models import cmd_models
from .status import cmd_status
from .vault import cmd_restore
from .identity import cmd_identity
from .app import cmd_app
from .ops import cmd_chat, cmd_gateway, cmd_schedule
from .settings import SETTINGS_KEYS, cmd_settings
from .setup import cmd_add, cmd_init, cmd_remove, cmd_upgrade
from .timeline import cmd_timeline

def main():
    p=argparse.ArgumentParser(prog='tamanitomo',description=USAGE,
                              formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path,help='Hermes home or profile dir')
    p.add_argument('--version',action='version',version=f'tamanitomo {__version__}')
    sub=p.add_subparsers(dest='cmd')
    for name,fn in (('init',cmd_init),('add',cmd_add),('remove',cmd_remove),
                    ('upgrade',cmd_upgrade),('repair',cmd_repair),('doctor',cmd_doctor),('catalog',cmd_catalog),('schedule',cmd_schedule),('settings',cmd_settings),('gateway',cmd_gateway),('chat',cmd_chat),('timeline',cmd_timeline),('models',cmd_models),('status',cmd_status),('restore',cmd_restore),('identity',cmd_identity),('app',cmd_app)):
        s=sub.add_parser(name,help=fn.__doc__)
        s.set_defaults(fn=fn)
        # Accepted on either side of the subcommand. SUPPRESS so that omitting it
        # here leaves the global value alone instead of overwriting it with None.
        s.add_argument('--home',type=pathlib.Path,default=argparse.SUPPRESS,
                       help='Hermes home or profile dir')
        if name=='timeline':s.add_argument('state',choices=['status','on','off','prune'],nargs='?',default='status')
        if name=='gateway':
            s.add_argument('--mode',choices=['shared','dedicated','later'])
            s.add_argument('--action',choices=['status','setup','install','start','restart','preflight'])
            s.add_argument('--root-restarted',action='store_true',help='Confirm the existing root gateway was restarted after routing changes')
        if name=='catalog':
            from companion_catalog import load as load_catalog
            s.add_argument('--gender',choices=['male','female'],default='female')
            s.add_argument('--category',choices=list(load_catalog()['categories'])+['personas','images','boundaries'])
        if name=='app':
            s.add_argument('--host',default='0.0.0.0',help='Listening address (default: local network; use 127.0.0.1 for host-only access)')
            s.add_argument('--port',type=int,default=8770)
            s.add_argument('--token',default='',help='require this token; generated if you bind wider')
            s.add_argument('--no-open',action='store_true',help='serve without opening a browser')
        if name=='identity':
            s.add_argument('section',nargs='?',help='which section; omit to list them')
            s.add_argument('--rerender',action='store_true',
                help='replace it with what setup would write today, backing up first')
        if name=='restore':
            s.add_argument('path',help='a file inside the vault, relative or absolute')
            s.add_argument('--commit',help='the version to recover; omit to list them')
            s.add_argument('--limit',type=int,default=20)
        if name=='status':s.add_argument('--json',action='store_true')
        if name=='models':
            s.add_argument('--show',action='store_true',help='print the current choices as JSON')
            s.add_argument('--apply',action='store_true',help='apply model choices to existing jobs without recreating them')
        if name=='repair':s.add_argument('--prompts',choices=['auto','force','skip'],default='auto',
            help="auto: re-render only the job prompts this kit wrote and you have not edited. "
                 "force: re-render them all, saving your version first. skip: leave every prompt alone.")
        if name=='schedule':s.add_argument('state',choices=['status','active','paused','history'],nargs='?',default='status')
        if name=='settings':s.add_argument('--set',action='append',metavar='KEY=VALUE',
            help='non-interactive change, repeatable: '+', '.join(sorted(SETTINGS_KEYS)))
        if name in ('add','remove'):s.add_argument('name')
        if name in ('init','add','upgrade'):s.add_argument('--answers',help='JSON, for non-interactive setup')
        if name in ('init','upgrade'):s.add_argument('--force',action='store_true')
        if name in ('init','add','upgrade'):s.add_argument('--vault',help='data root (default ~/vault)')
        if name=='upgrade':s.add_argument('--soul',choices=['append','replace','keep'])
        if name=='remove':
            s.add_argument('--force',action='store_true',help='required; archives the profile')
            s.add_argument('--purge',action='store_true',help='delete instead of archiving')
    a=p.parse_args()
    if not getattr(a,'fn',None):a.fn=cmd_menu
    sys.exit(a.fn(a) or 0)


def run():
    """The entry point. Every expected failure leaves the tree as it was and says why."""
    try:
        import yaml
        main()
    except ImportError:
        print('Missing dependency. Install requirements.txt using the Python interpreter '
              'that runs this kit.',file=sys.stderr);sys.exit(1)
    except yaml.YAMLError:
        print('Invalid YAML configuration; setup stopped. Correct config.yaml and retry.',
              file=sys.stderr);sys.exit(1)
    except (ValueError,OSError,KeyError) as exc:
        print(f'Error: {exc}',file=sys.stderr);sys.exit(1)
    except (KeyboardInterrupt,EOFError):
        print('\nCancelled. Completed setup steps are retained; use doctor to inspect them.',
              file=sys.stderr);sys.exit(130)

if __name__ == '__main__':
    run()
