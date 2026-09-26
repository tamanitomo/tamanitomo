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
import pathlib
import sys

__version__ = (
    (pathlib.Path(__file__).resolve().parents[2] / "VERSION")
    .read_text(encoding="utf-8")
    .strip()
)

# The runtime helpers are flat modules meant to be runnable on their own
# (`python companion_self.py ...` appears in every cron prompt), so they are
# imported by name rather than as a package.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
