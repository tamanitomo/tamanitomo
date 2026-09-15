#!/usr/bin/env python3
"""Compile a scene prompt that produces the same person every time.

Consistent character generation does not come from a seed or a model; it comes
from describing the same person the same way in every single prompt. The parts
that must never vary — age, hair, eyes, build, complexion — are compiled from
the locked appearance section of SOUL.md, in a fixed order, and prepended to
whatever the scene happens to be. The scene comes from the recorded presence
state, so a photo is a glimpse of a moment that actually happened rather than a
staged one.

A reference portrait is stored in the vault for deliberate reuse. Ordinary
photos use the appearance description and current scene without an input image.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, re, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
from companion_platform import atomic_write

# The order matters. A description read in a stable order produces a stable
# person; the same facts shuffled produce a different one.
IDENTITY_ORDER=('age','complexion','eyes','hair_color','hair_style','facial_hair',
                'marks','build','height','style')

PORTRAIT_EXTS=('png','jpg','webp')
EXCLUDE='COMPANION-PROMPT-EXCLUDE'

def portrait_path(c):
    """The stored likeness, whatever it was uploaded as.

    A JPEG saved as `reference-portrait.jpg` used to be invisible here, because
    this only ever looked for the `.png` — so the reference existed and was
    never passed to anything.
    """
    base=c.data/'soul'/'reference-portrait'
    for ext in PORTRAIT_EXTS:
        candidate=base.with_suffix('.'+ext)
        if candidate.is_file():return candidate
    return base.with_suffix('.png')

def identity_block(c,use_override=True):
    """The unvarying description of this person, from the locked SOUL section."""
    import companion_media as media
    override=media.effective(c).get('identity_override')
    if use_override and override is not None:return override
    import companion_identity as identity
    try:
        _,text=identity.read(c)
        section=identity.sections(text).get('appearance')
    except (OSError,ValueError):section=None
    if not section or not section['body'].strip():
        # Adopted Hermes profiles often have a hand-authored SOUL without kit
        # markers. Read an explicitly named appearance section without rewriting it.
        try:
            match=re.search(r'^#{1,3}\s+(?:Physical Description|Appearance|Visual Identity)\s*\n(.*?)(?=^#{1,3}\s|\Z)',text,re.M|re.S|re.I)
        except UnboundLocalError:match=None
        if not match:return ''
        section={'body':match.group(1)}
    # The section ends with instructions addressed to her — how to maintain a
    # wardrobe, and the command that does it. Marked in the template so it can
    # be cut here; in a SOUL written before the marker existed, the paragraph
    # holding the first inline code span is where the description stopped and
    # the instructions began. Cut by paragraph, not by line: the sentence above
    # the command belongs to the command, and a line is not a thought.
    kept=[]
    for block in re.split(r'\n\s*\n',section['body']):
        if EXCLUDE in block or '`' in block:break
        kept.append(block)
    lines=[l.strip() for l in '\n'.join(kept).splitlines() if l.strip() and '✎ EDIT' not in l]
    # Headings and comments are how the file is organized for a reader; a prompt
    # that carries "## Physical Description" is describing a document.
    lines=[l for l in lines if not l.startswith('<!--') and not l.startswith('#')]
    return ' '.join(lines).strip()

def scene_block(c,record=None):
    """What she is actually doing, from the recorded state."""
    from companion_presence import current
    scene=record if record is not None else current(c)
    if not scene:return '',None
    state=scene['state']
    outfit=', '.join(item['description'] for item in state.get('outfit',[]))
    parts=[state.get('activity',''),f"in {state.get('location','')}" if state.get('location') else '']
    if outfit:parts.append(f'wearing {outfit}')
    visual=state.get('visual') or {}
    parts.extend(f'{key}: {value}' for key,value in visual.items() if value)
    return ', '.join(p for p in parts if p),scene

def recorded_overrides(c,record=None):
    scene,record=scene_block(c,record)
    if not scene:raise ValueError('No recorded scene to photograph')
    # Multi-encoder workflows have a dedicated wardrobe conditioning node.
    # Replace the preset's old outfit with the actual one instead of blanking it.
    outfit=', '.join(item['description'] for item in record['state'].get('outfit',[]))
    visual=record['state'].get('visual') or {}
    overrides={'scene':scene,'wardrobe':outfit}
    if visual.get('framing'):overrides['camera']=visual['framing']
    if visual.get('lighting'):overrides['lighting']=visual['lighting']
    return overrides

def style_block(c):
    from companion_render import load_styles
    style=load_styles().get(c.image_style) or {}
    return style.get('soul','')

def compile_prompt(c,extra='',use_reference=False):
    """The whole prompt: who, then what, then how it should look."""
    identity=identity_block(c)
    scene,record=scene_block(c)
    style=style_block(c)
    if not identity:
        return {'ready':False,
                'reason':'no appearance description in SOUL.md — a photo of nobody in particular '
                         'produces a different person every time. Fill in the appearance section '
                         'first: companion identity appearance'}
    if not scene:
        return {'ready':False,
                'reason':'no recorded state, so there is no moment to photograph. A scene invented '
                         'for the camera is exactly what this pipeline exists to prevent.'}
    pieces=[identity,scene]
    if extra.strip():pieces.append(extra.strip())
    if style:pieces.append(style)
    prompt=' '.join(p.rstrip('.')+'.' for p in pieces if p)
    reference=portrait_path(c)
    import companion_media as media
    recipe=media.effective(c)
    selected=recipe.get('routes',{}).get('portrait') or recipe.get('default_preset')
    return {'ready':True,'prompt':prompt,'image_preset':selected or None,
            'generation_command':('companion_portrait.py --home '+str(c.home)+' generate') if selected else None,
            'identity':identity,'scene':scene,'style':style,
            'reference_image':str(reference) if use_reference and reference.is_file() else None,
            'recorded_at':record['recorded_at'] if record else None,
            'note':('Generate a fresh image from the appearance description and scene. '
                    'Do not attach the stored portrait unless reference reuse was explicitly requested. '
                    'Keep the identity wording unchanged.')}

def save_reference(c,source):
    """Store a likeness as the canonical reference."""
    import companion_timeline as timeline
    data,ext=timeline.load_image(str(source))
    target=(c.data/'soul'/'reference-portrait').with_suffix('.'+ext)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)
    # One canonical likeness: replacing a PNG with a JPEG must not leave the old
    # face behind for portrait_path to find first.
    for other in PORTRAIT_EXTS:
        stale=target.with_suffix('.'+other)
        if stale!=target and stale.is_file():stale.unlink()
    return {'saved':str(target),'bytes':len(data),
            'note':'Stored in the vault, so it is covered by the same history as everything else.'}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    pr=s.add_parser('prompt',help='compile the scene prompt for right now')
    pr.add_argument('--use-reference',action='store_true',help='Explicitly reuse the saved portrait as an input image')
    pr.add_argument('--extra',default='',help='anything specific to this shot')
    gp=s.add_parser('generate',help='generate using the saved Image Studio category/workflow')
    gp.add_argument('--category',default='portrait')
    gp.add_argument('--preset',default='')
    gp.add_argument('--scene')
    gp.add_argument('--allow-nsfw',action='store_true',help='The intended image explicitly includes adult content')
    gp.add_argument('--recorded',action='store_true',help='Use the current recorded scene and wardrobe exactly')
    rv=s.add_parser('review',help='Review an externally generated image before delivery')
    rv.add_argument('--source',required=True)
    rv.add_argument('--scene',required=True)
    rv.add_argument('--allow-nsfw',action='store_true')
    rf=s.add_parser('reference',help='store a likeness as the canonical reference')
    rf.add_argument('--source',required=True)
    s.add_parser('show')
    a=p.parse_args();c=cc.load(a.home)
    if a.cmd=='prompt':out=compile_prompt(c,a.extra,a.use_reference)
    elif a.cmd=='generate':
        import companion_media as media
        overrides={'scene':a.scene} if a.scene else None
        if a.recorded:
            overrides=recorded_overrides(c)
        out=media.generate(c,a.preset,a.category,overrides,allow_nsfw=a.allow_nsfw)
    elif a.cmd=='review':
        import companion_media_review as review
        out=review.inspect(c,pathlib.Path(a.source),a.scene,a.allow_nsfw)
    elif a.cmd=='reference':out=save_reference(c,a.source)
    else:
        ref=portrait_path(c)
        out={'identity':identity_block(c),'style':style_block(c),
             'reference_image':str(ref) if ref.is_file() else None}
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
