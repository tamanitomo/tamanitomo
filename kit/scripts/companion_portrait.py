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
    # Locations get recorded however they were written — "the kitchen" wants an
    # "in", "in the car on the highway" already has one.
    place=state.get('location','')
    if place and not re.match(r'(in|on|at|by|near|inside|outside|under|beside)\b',place.strip(),re.I):
        place='in '+place
    parts=[state.get('activity',''),place]
    if outfit:parts.append(f'wearing {outfit}')
    visual=state.get('visual') or {}
    parts.extend(f'{key}: {value}' for key,value in visual.items() if value)
    return ', '.join(p for p in parts if p),scene

# Daylight by the clock, for the times nothing recorded the light. Approximate
# on purpose: a picture wants to know it is golden hour, not the sun's azimuth.
DAYLIGHT=((5,'soft dawn light'),(8,'bright morning light'),(11,'midday daylight'),
          (16,'warm late afternoon light'),(19,'golden hour, low sun'),(21,'blue hour dusk'))
INDOOR_WORDS=('indoors','inside','room','bedroom','kitchen','living room','office','home',
              'car','bed','sofa','couch','bath','shower','studio','cafe','restaurant','shop')
OUTDOOR_WORDS=('beach','park','street','road','highway','trail','forest','garden','field',
               'mountain','coast','shore','outside','outdoors','sky','city')


def lighting_guess(c,location='',now=None):
    """What the light is probably doing, when nothing recorded it.

    A guess, and only ever used where the field would otherwise be blank: a
    recorded `visual.lighting` always wins.
    """
    import datetime as dt
    try:
        zone=dt.timezone.utc if not c.timezone else __import__('zoneinfo').ZoneInfo(c.timezone)
    except Exception:zone=dt.timezone.utc
    hour=(now or dt.datetime.now(zone)).hour
    place=str(location or '').lower()
    outdoor=any(w in place for w in OUTDOOR_WORDS)
    indoor=any(w in place for w in INDOOR_WORDS) and not outdoor
    # Before dawn and after dusk there is no daylight to describe, whatever the
    # table's last row says.
    if hour<5 or hour>=22:
        return 'warm indoor lamplight' if indoor else 'night, ambient streetlight'
    daylight=DAYLIGHT[0][1]
    for start,label in DAYLIGHT:
        if hour>=start:daylight=label
    if indoor:return daylight+' through a window'
    return daylight


def feeling_text(state):
    """Flatten mood and immediate wants without leaking Python list syntax."""
    values=[]
    mood=str(state.get('mood','')).strip()
    if mood:values.append(mood)
    wants=state.get('wants',[])
    if isinstance(wants,list):values.extend(str(value).strip() for value in wants if str(value).strip())
    elif str(wants).strip():values.append(str(wants).strip())
    return ', '.join(values)


def prompt_parts(c,record=None):
    """The recorded moment, split into the boxes a workflow actually has.

    `scene_block` joins everything into one line because a single-prompt
    workflow has nowhere else to put it. A workflow with separate conditioning
    wants the outfit in wardrobe and the light in lighting, so the scene is left
    holding only what it is: where she is and what she is doing.
    """
    from companion_presence import current
    scene=record if record is not None else current(c)
    state=(scene or {}).get('state',{}) if scene else {}
    outfit=', '.join(item['description'] for item in state.get('outfit',[]) if item.get('description'))
    visual=state.get('visual') or {}
    location=state.get('location','')
    where=', '.join(p for p in (state.get('activity',''),location) if p)
    feeling=feeling_text(state)
    return {'identity':identity_block(c),'scene':where,'wardrobe':outfit,'feeling':feeling,
            'lighting':visual.get('lighting') or lighting_guess(c,location),
            'camera':visual.get('framing') or ''}


def recorded_overrides(c,record=None):
    scene,record=scene_block(c,record)
    if not scene:raise ValueError('No recorded scene to photograph')
    # Multi-encoder workflows have a dedicated wardrobe conditioning node.
    # Replace the preset's old outfit with the actual one instead of blanking it.
    outfit=', '.join(item['description'] for item in record['state'].get('outfit',[]))
    visual=record['state'].get('visual') or {}
    state=record.get('state') or {}
    feeling=feeling_text(state)
    overrides={'scene':scene,'wardrobe':outfit,'feeling':feeling}
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
