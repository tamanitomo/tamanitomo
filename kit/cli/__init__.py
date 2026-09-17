"""The `tamanitomo` command, split by what each part is for.

    common      where the kit lives, how a home is resolved
    questions   the setup questionnaire and its pickers
    roster      finding and choosing between the agents on a Hermes home
    scaffold    writing a profile into place
    setup       init, add, remove, upgrade
    doctor      doctor and repair
    settings    the settings screen
    ops         chat, schedule, gateway
    catalogs    the catalog browser
    timeline    the image-timeline command
    menu        the interactive roster
    main        argument parsing

`bin/tamanitomo` is a thin entry point onto `main.run()`.
"""
from __future__ import annotations
import pathlib, sys

__version__='2.2.0'

# The runtime helpers are flat modules meant to be runnable on their own
# (`python companion_self.py ...` appears in every cron prompt), so they are
# imported by name rather than as a package.
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
