"""Lossless companion editing: current runtime values plus actual authored SOUL."""
import dataclasses
import hashlib
import json
import re
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import HTTPException
import companion_config as cc
import companion_platform as cp

FIXED={'profile','hermes_root','vault','soul_in_vault'}

def snapshot(c):
    path=c.home/cc.CONFIG_NAME
    raw=path.read_bytes()
    soul=c.soul.read_text(encoding='utf-8') if c.soul.exists() else ''
    label_path=c.home/'companion-display-name.json'
    if label_path.is_symlink():raise ValueError('Display-name file must not be a symlink')
    label_raw=label_path.read_bytes() if label_path.exists() else b''
    label=json.loads(label_raw).get('name','') if label_raw else ''
    revision=hashlib.sha256(raw+b'\0'+soul.encode()+b'\0'+label_raw).hexdigest()
    return {'config':c.to_dict(),'soul':soul,'revision':revision,'display_name':label or c.agent,
            'fixed':sorted(FIXED)}

def save(c,payload):
    original=snapshot(c)
    if payload.get('revision')!=original['revision']:raise HTTPException(409,'This companion changed. Reload the editor before saving.')
    values=payload.get('config')
    if not isinstance(values,dict) or set(values)!=set(original['config']):raise ValueError('Supply the complete companion configuration')
    if any(values[k]!=original['config'][k] for k in FIXED):raise ValueError('Profile and storage paths are read-only; use migration tools to move them')
    for key,old in original['config'].items():
        if isinstance(old,bool):valid=isinstance(values[key],bool)
        elif isinstance(old,int):valid=isinstance(values[key],int) and not isinstance(values[key],bool)
        elif isinstance(old,float):valid=isinstance(values[key],(int,float)) and not isinstance(values[key],bool)
        else:valid=isinstance(values[key],type(old))
        if not valid:raise ValueError(f'Invalid value type for {key}')
    for key in ('agent','human'):
        v=values[key]
        if not v.strip() or len(v)>100 or any(ord(x)<32 for x in v):raise ValueError(f'{key} must be 1–100 characters')
    if not 18<=values['age']<=120:raise ValueError('Age must be 18–120')
    if values['outreach'] not in ('free','updates_only','never'):raise ValueError('Invalid outreach choice')
    for key in ('quiet_start','quiet_end'):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',values[key]):raise ValueError('Use HH:MM for quiet hours')
    try:ZoneInfo(values['timezone'])
    except (KeyError,ValueError):raise ValueError('Choose a valid timezone')
    import companion_render as cr
    import companion_wizard as cw
    if values['persona'] not in cr.load_personas() or values['image_style'] not in cr.load_styles():raise ValueError('Unknown personality or image style')
    if values['boundary'] not in cw.BOUNDARY_BANK:raise ValueError('Unknown relationship frame')
    updated=cc.Companion(**values)
    soul=payload.get('soul')
    if not isinstance(soul,str) or len(soul.encode())>2_000_000:raise ValueError('SOUL must be text under 2 MB')
    label=payload.get('display_name',updated.agent)
    if not isinstance(label,str) or not label.strip() or len(label)>100 or any(ord(x)<32 for x in label):raise ValueError('Invalid display name')
    from .settings_service import validate, preserve_human_records
    validate(updated)
    with cp.file_lock(c.home/'.companion-profile-editor.lock'), preserve_human_records(c, updated):
        if snapshot(c)['revision']!=original['revision']:raise HTTPException(409,'This companion changed. Reload the editor.')
        backup=c.home/'companion-config-backups'/('editor-'+uuid.uuid4().hex)
        backup.mkdir(parents=True)
        old_raw=(c.home/cc.CONFIG_NAME).read_text()
        cp.atomic_write(backup/'companion.json',old_raw)
        cp.atomic_write(backup/'SOUL.md',original['soul'])
        # Preserve extensions the installed kit may not understand yet.
        raw=json.loads(old_raw);raw.update(updated.to_dict())
        try:
            if soul!=original['soul']:cp.atomic_write(c.soul.resolve(),soul)
            cp.atomic_write(c.home/cc.CONFIG_NAME,json.dumps(raw,indent=2,ensure_ascii=False)+'\n')
            cp.atomic_write(c.home/'companion-display-name.json',json.dumps({'name':label.strip()}))
        except Exception:
            cp.atomic_write(c.home/cc.CONFIG_NAME,old_raw)
            cp.atomic_write(c.soul.resolve(),original['soul'])
            raise
    if updated.timezone!=c.timezone:
        from .manage import save_config
        save_config(c.home,lambda cfg:cfg.update(timezone=updated.timezone))
    return {'saved':True,'backup':str(backup),'note':'Companion saved. New sessions read these settings.'}

def register(app,load,select):
    @app.get('/api/profile/editor')
    def editor():return snapshot(load())
    @app.post('/api/profile/editor')
    def update(payload:dict):
        old=load()
        result=save(old,payload)
        from .settings_service import synchronize
        operation=synchronize(app,select()[0],old,load())
        if operation:result['operation']=operation
        return result
