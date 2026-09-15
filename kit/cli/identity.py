"""`companion identity` — look at one part of the SOUL, or rebuild it.

A SOUL that has been lived in for six months cannot be regenerated wholesale.
This lets one section be re-rendered from the current answers while every other
byte of the file stays exactly as it was, including the parts somebody wrote by
hand at two in the morning.

Some sections are locked. Not from the person — they can edit the file with any
text editor — but from the companion, whose self-edit helper refuses to touch
them. Her build and the boundaries the human set are the two that matter: a
model that can widen its own boundary paragraph has no boundary.
"""
from __future__ import annotations
import companion_wizard as wiz
import json
from .common import print, resolve

def cmd_identity(args):
    """Show, list or re-render one section of SOUL.md."""
    import companion_identity as identity
    c=resolve(args,require_config=True)
    if not args.section:
        rows=identity.listing(c)
        if not rows:
            print('This SOUL has no section markers — it predates them, or was rewritten by hand.')
            print(wiz.C.dim('  Everything still works; only per-section re-rendering needs them.'))
            return 1
        print(f'{c.agent} — {len(rows)} sections in SOUL.md')
        for row in rows:
            mark=wiz.C.yellow('locked') if row['locked'] else '      '
            print(f"  {mark}  {row['name']:<16}{row['chars']:>6} chars")
        print()
        print(wiz.C.dim('  locked = not editable by the companion. You can still edit the file yourself.'))
        print(wiz.C.dim('  companion identity <section>            show it'))
        print(wiz.C.dim('  companion identity <section> --rerender rebuild just that one'))
        return 0
    if not args.rerender:
        _,text=identity.read(c)
        found=identity.sections(text)
        if args.section not in found:
            raise ValueError(f'no section {args.section!r}; known: {", ".join(sorted(found))}')
        section=found[args.section]
        print(f"## {args.section}"+('   (locked)' if section['locked'] else ''))
        print()
        print(section['body'])
        return 0
    body=identity.render_section(c,args.section)
    result=identity.replace(c,args.section,body)
    print(f"Re-rendered {args.section} ({result['chars']} chars).")
    print(wiz.C.dim(f"  the SOUL as it was is saved at {result['backup']}"))
    print(wiz.C.dim('  every other section is byte-for-byte unchanged; that is verified, not assumed'))
    return 0
