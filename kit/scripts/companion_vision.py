#!/usr/bin/env python3
"""Read a face out of a photograph, and nothing else.

This is the one module in the kit that calls a model, and it exists for one
job: turning an uploaded likeness into the locked appearance section, so the
words and the picture describe the same person. Everywhere else a photo is
handed *to* a provider; here one is read.

Three rules make it safe to have around.

**It never writes.** `describe()` returns a proposal. The write goes through
`companion_identity.replace`, which backs the SOUL up and proves no other
section moved — the same path the app's section editor already uses. A locked
section is not rewritten because a model said something; it is rewritten
because a person read what the model said and agreed.

**It renders through the interview, not around it.** The model returns the same
fields the setup interview asks for, and `physical_paragraph` assembles them in
the same fixed order. A description that arrived from a photograph and one that
was typed by hand come out identically shaped, which is the property the image
pipeline depends on: the same person described the same way every time.

**It does not guess age.** Age is computed from the birthdate and is not the
model's to estimate. The field is not requested and is discarded if offered.

The call runs with `--ignore-rules`, so the companion's own SOUL and memory are
not injected: this asks a model to look at a picture, not to be somebody
looking at a picture of herself.
"""
from __future__ import annotations
import argparse, json, os, pathlib, subprocess, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_portrait as portrait
from companion_platform import hermes_command

# The interview's own keys, minus age. Order is portrait.IDENTITY_ORDER's order,
# because that is the order a stable likeness is described in.
FIELDS=tuple(f for f in portrait.IDENTITY_ORDER if f!='age')
TIMEOUT=180

PROMPT="""Look at the attached photograph and describe only the person's fixed physical appearance.

Answer with a single JSON object and nothing else. No prose before or after, no code fence.

Keys, all optional — omit any key you cannot see clearly rather than guessing:
{fields}

Each value is ONE complete sentence beginning with "{Poss}", as if it were written into a
description of this person: "{Poss} hair is copper red." · "{Poss} build is slight and
narrow-shouldered." Keep each under twenty words.

Rules:
- Describe only what is visible. Do not invent, flatter or interpret.
- Never describe the absence of something. If there is no facial hair, omit the key; do not write
  that there is none. A description made of negatives is not a description.
- Do not estimate age, and do not include an age key.
- Do not name the person, guess who they are, or comment on the photograph itself.
- "style" means how they dress in general terms, not this one outfit.
- "marks" means lasting features: freckles, scars, glasses, piercings, tattoos.
- If the image shows no person, or the face is not visible, answer {{"error":"no visible face"}}.
"""

# A negation is not a description, and in an image prompt it is worse than
# nothing: "no visible facial hair" is a phrase a generator will happily draw
# around. The prompt says not to, and this is what happens when it does anyway.
NEGATIONS=('no ','none','not ','without ','absent','n/a','unknown','cannot','unclear')


def _extract(text):
    """The first balanced JSON object in the reply.

    Asking for bare JSON gets bare JSON most of the time. A model that wraps it
    in a fence or a sentence of preamble has still done the work, and throwing
    that away to be strict about punctuation helps nobody.
    """
    start=text.find('{')
    while start!=-1:
        depth=0;quoted=False;escaped=False
        for i in range(start,len(text)):
            ch=text[i]
            if escaped:escaped=False;continue
            if ch=='\\' and quoted:escaped=True;continue
            if ch=='"':quoted=not quoted;continue
            if quoted:continue
            if ch=='{':depth+=1
            elif ch=='}':
                depth-=1
                if depth==0:
                    try:return json.loads(text[start:i+1])
                    except ValueError:break
        start=text.find('{',start+1)
    raise ValueError('the model did not return JSON; nothing was written')


def ask(c,image,model='',provider='',timeout=TIMEOUT):
    """Run the vision call and return the raw reply."""
    image=pathlib.Path(image)
    if not image.is_file():raise ValueError(f'no image at {image}')
    argv=list(hermes_command('chat','--image',str(image),'--oneshot','-Q',
                             '--ignore-rules','--max-turns','1'))
    if model:argv+=['--model',model]
    if provider:argv+=['--provider',provider]
    handle=tempfile.NamedTemporaryFile('w',suffix='.txt',encoding='utf-8',delete=False)
    try:
        handle.write(PROMPT.format(fields='\n'.join('- '+f for f in FIELDS),
                                   Poss=c.poss().capitalize()));handle.close()
        argv+=['--query-file',handle.name]
        try:
            result=subprocess.run(argv,capture_output=True,text=True,encoding='utf-8',
                                  timeout=timeout,
                                  env={**os.environ,'HERMES_HOME':str(c.home),
                                       'HERMES_TIMEZONE':c.timezone})
        except FileNotFoundError:
            raise ValueError('Hermes is not on PATH, so no model can be reached from here')
        except subprocess.TimeoutExpired:
            raise ValueError(f'the model did not answer within {timeout}s; nothing was written')
    finally:
        try:os.unlink(handle.name)
        except OSError:pass
    if result.returncode:
        # Hermes wraps its reasons over several lines and puts the useful half
        # first, so the last line alone reads as a non-sequitur.
        lines=[l.strip() for l in (result.stderr or result.stdout or '').splitlines() if l.strip()]
        detail=' '.join(lines[-3:])[:300] if lines else 'no output'
        raise ValueError('Hermes refused the vision call: '+detail)
    return result.stdout


def fields_from(reply):
    """The described fields, filtered to the ones the interview knows."""
    data=_extract(reply)
    if data.get('error'):raise ValueError(str(data['error']))
    out={}
    for key in FIELDS:
        value=data.get(key)
        if not isinstance(value,str):continue
        value=' '.join(value.split())
        if value.lower().startswith(NEGATIONS):continue
        # A model that writes an essay into one field produces an appearance
        # block nobody will read and a prompt that describes a document.
        if value and len(value)<=200:out[key]=value
    if not out:raise ValueError('the model described nothing usable; nothing was written')
    return out


def proposal(c,fields):
    """What the appearance section would say, rendered the way setup renders it."""
    import companion_wizard as wiz
    import companion_identity as identity
    iv=dict(fields)
    iv['physical']=wiz.physical_paragraph(iv,c.agent,c.pronouns,age=c.current_age())
    return identity.render_section(c,'appearance',interview=iv)


def describe(c,image=None,model='',provider='',timeout=TIMEOUT):
    """Photo in, proposed section out. Nothing is written."""
    image=pathlib.Path(image) if image else portrait.portrait_path(c)
    reply=ask(c,image,model=model,provider=provider,timeout=timeout)
    fields=fields_from(reply)
    return {'image':str(image),'fields':fields,'body':proposal(c,fields),
            'written':False,
            'note':'Read it before you keep it. appearance is a locked section: '
                   'nothing here reaches SOUL.md until a person accepts it.'}


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--home',type=pathlib.Path)
    s=p.add_subparsers(dest='cmd',required=True)
    d=s.add_parser('describe',help='propose the appearance section from a photo')
    d.add_argument('--image',help='defaults to the stored reference portrait')
    d.add_argument('--model',default='');d.add_argument('--provider',default='')
    d.add_argument('--apply',action='store_true',help='write it without reading it first')
    a=p.parse_args();c=cc.load(a.home)
    out=describe(c,a.image,model=a.model,provider=a.provider)
    if a.apply:
        import companion_identity as identity
        out.update(identity.replace(c,'appearance',out['body']))
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print(json.dumps({'error':str(e)}),file=sys.stderr);sys.exit(1)
