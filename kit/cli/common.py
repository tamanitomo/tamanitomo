"""Shared plumbing for the command modules: where the kit lives, how a home is resolved,
and the few helpers every command needs."""
from __future__ import annotations
import companion_config as cc
import companion_platform as cp
import companion_render as cr
import json
import os
import pathlib
import re
import sys
import companion_wizard as wiz

KIT=pathlib.Path(__file__).resolve().parents[2]
T=KIT/'kit/templates'
PULSE_MINUTES=15
# Render CLI text through the same ASCII/Unicode policy as the questionnaire.
print=wiz.print
input=wiz.input
def resolve(args,require_config=False):
    home=args.home or os.environ.get('COMPANION_HOME') or os.environ.get('HERMES_HOME')
    c=cc.load(home)
    # Defence in depth: never act on a home other than the one asked for.
    if home and pathlib.Path(home).resolve()!=c.home.resolve():
        sys.exit(f'refusing to act: asked for {home}, resolved to {c.home}')
    if require_config and not (c.home/cc.CONFIG_NAME).exists():
        sys.exit(f'no companion.json in {c.home} — run `companion init` or `companion upgrade` first')
    return c
# ---------------------------------------------------------------- scaffolding
def write(path,text,overwrite=False):
    path=pathlib.Path(path)
    if path.exists() and not overwrite:return False
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return True
# ---------------------------------------------------------------- commands
def edit_count(text):
    """Count actionable placeholders, not the template's explanatory HTML comment."""
    return re.sub(r'<!--.*?-->','',text,flags=re.S).count('✎ EDIT')
def _read_jobs(path):
    if not path.exists():return {'jobs':[]}
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('jobs'),list) or not all(isinstance(j,dict) for j in data['jobs']):
        raise ValueError('Invalid Hermes job store; repair it with Hermes before installing jobs')
    return data
def load_manifest(c=None):
    data=json.loads((T/'cron/manifest.json').read_text(encoding='utf-8'))
    def wanted(spec):
        # An agent type decides what machinery exists at all: a quiet worker has
        # no present to advance and no mornings to have.
        types=spec.get('types')
        if types and c is not None and c.agent_type not in types:return False
        if types and c is None:return False
        optional=spec.get('optional')
        if not optional:return True
        if c is None:return False
        if optional=='image_timeline':return c.image_timeline
        return c.image_timeline or (c.data/'image-timeline').exists()
    return {'jobs':[spec for spec in data['jobs'] if wanted(spec)]}

def script_job_names(c,m=None):
    """Jobs that run without a model.

    They cost nothing, they are what keeps the present honest when the model is
    unavailable, and pausing the schedule must not switch them off — so both
    doctor and `schedule` treat them as always-on rather than naming one job."""
    m=m or {'AGENT':c.agent}
    return {cr.render(spec['name'],m) for spec in load_manifest(c)['jobs'] if spec.get('no_agent')}
def mapping(c,ans):
    iv=dict(ans.get('interview') or {})
    if iv:
        iv['physical']=wiz.physical_paragraph(iv,c.agent,c.pronouns,age=c.current_age())
        iv['names_sentence']=wiz.names_sentence(c.all_names)
    m=cr.mapping_for(c,ans.get('persona',c.persona),ans.get('image_style',c.image_style),
                     kit=str(KIT),hook=cp.python_command(c.home/'hooks/companion-context.py'),
                     pulse_minutes=PULSE_MINUTES,interview=iv)
    if iv.get('boundary_oneline'):m['BOUNDARY_ONELINE']=iv['boundary_oneline']
    m.update({'SOUL':str(c.soul),'HERMES':'hermes','AUTONOMY_PATH':cp.terminal_command([c.soul_dir/'continuity/Autonomy.md']),'JOB_COUNT':str(len(load_manifest(c)['jobs']))})
    return m
