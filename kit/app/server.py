"""Companion workspace API with request-scoped Hermes profiles."""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import sys
import secrets

def is_blacklisted_undergarment(it) -> bool:
    """Strict undergarment blacklist (panties, thong, lingerie, underpants, boxers, briefs). Only visible at Stage 4 (Bonded)."""
    desc = it.get('description', '') if isinstance(it, dict) else str(it or '')
    wid = it.get('id', '') if isinstance(it, dict) else ''
    text = f"{wid} {desc}".lower()
    return bool(re.search(r'\b(panties|panty|thong|thongs|lingerie|underpants|undies|boxers|boxer|briefs|brief)\b', text))

def is_intimate_garment(it) -> bool:
    """General undergarment detection. Sports bras are excluded (allowed as athletic tops)."""
    desc = it.get('description', '') if isinstance(it, dict) else str(it or '')
    wid = it.get('id', '') if isinstance(it, dict) else ''
    text = f"{wid} {desc}".lower()
    if 'sports bra' in text or 'sports-bra' in text or 'sports_bra' in text:
        return False
    return bool(re.search(r'\b(panties|panty|bra|bras|bralette|underwear|undergarment|undergarments|boxers|boxer|briefs|brief|thong|thongs|lingerie|underpants|undies)\b', text))

def filter_wardrobe_items(items, stage: int):
    """Tiered wardrobe visibility:
    - Stage < 2 (Just Met / Flirting): hides all undergarments; sports bras allowed as athletic tops.
    - Stage 2-3 (Chemistry / Intimacy): shows all wardrobe items EXCEPT blacklisted undergarments.
    - Stage >= 4 (Bonded): shows all wardrobe items without restriction.
    """
    if stage >= 4:
        return items or []
    if stage >= 2:
        return [it for it in (items or []) if not is_blacklisted_undergarment(it)]
    return [it for it in (items or []) if not is_intimate_garment(it)]


from contextvars import ContextVar
from starlette.requests import Request

KIT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(KIT/'kit/scripts'))
STATIC=pathlib.Path(__file__).resolve().parent/'static'

import companion_config as cc


def _json_safe(value):
    if isinstance(value,pathlib.Path):return str(value)
    if isinstance(value,(dt.datetime,dt.date)):return value.isoformat()
    return value

def get_network_ips():
    ips = set()
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        import subprocess
        out = subprocess.run(["ip", "-br", "a"], capture_output=True, text=True, timeout=1).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "UP":
                ip = parts[2].split("/")[0]
                if not ip.startswith(("127.", "172.17.", "172.18.")):
                    ips.add(ip)
    except Exception:
        pass
    return sorted(ips)

def build(home=None,token='',state_dir=None):
    """Create a workspace; profile selection is local to each request."""
    from fastapi import Body, FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles

    from .runtime import Runtime, Operations, app_directory
    public_origin=os.environ.get('COMPANION_PUBLIC_ORIGIN','').rstrip('/')
    if public_origin:
        from urllib.parse import urlsplit
        parsed=urlsplit(public_origin)
        if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:raise ValueError('Public origin must be an HTTPS origin without a path')
    initial=cc.load(home)
    state=pathlib.Path(state_dir) if state_dir else (initial.hermes_root/'.companion-app' if home else app_directory())
    runtimes={'existing':Runtime(initial.hermes_root), 'managed':Runtime(state/'managed-hermes',managed=True)}
    selection=ContextVar('companion_selection',default=('existing',initial.profile or 'default'))

    def select():
        installation,profile=selection.get()
        if installation not in runtimes:raise ValueError('Unknown Hermes installation')
        return runtimes[installation],profile

    def load():
        # Re-read on every request. The CLI, the cron jobs and this page all
        # write the same files, and a cached config is how a page ends up
        # showing settings that were changed twenty minutes ago.
        runtime,profile=select()
        return cc.load(runtime.home(profile))

    app=FastAPI(title='tamanitomo',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.runtimes=runtimes
    import threading
    app.state.write_locks={key:threading.Lock() for key in runtimes}
    from .manage import register
    register(app,select,load,Operations(state/'operations'))
    from .content import register as register_content
    register_content(app,load)
    from .dashboard import register as register_dashboard
    register_dashboard(app,select,token)
    from .profile_editor import register as register_editor
    register_editor(app,load,select)
    from .images import register as register_images
    register_images(app,select,load)
    from .voice_chat import register as register_voice_chat
    register_voice_chat(app,select,load)
    from .updates import register as register_updates
    register_updates(app)
    from .local_models import register as register_local_models
    register_local_models(app,select)

    app.state.pin_salt=secrets.token_hex(16)

    @app.middleware('http')
    async def guard(request:Request,call_next):
        client_host=request.client.host if request.client else '127.0.0.1'
        is_local=client_host in ('127.0.0.1','::1','localhost','testclient')
        if not is_local and request.url.path.startswith(('/api','/media')) and request.url.path not in ('/api/auth/pin','/api/network'):
            try:
                c=load()
                if c.remote_pin:
                    import hashlib
                    expected=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest()
                    cookie_token=request.cookies.get('companion_pin_session','')
                    header_pin=request.headers.get('x-companion-pin','')
                    pin_ok=(bool(cookie_token) and secrets.compare_digest(cookie_token,expected)) or \
                           (bool(header_pin) and secrets.compare_digest(header_pin,c.remote_pin))
                    if not pin_ok:
                        return JSONResponse({'pin_required':True,'error':'Remote access locked. Enter 4-digit PIN.'},status_code=401)
            except Exception:pass
        # An optional shared token, for the person who does put this behind a
        # tunnel. Absent, the only protection is the localhost bind, and the
        # page says so rather than implying otherwise.
        if token and request.url.path.startswith(('/api','/media')):
            supplied=request.headers.get('x-companion-token') or request.query_params.get('token','')
            dashboard_cookie=(request.url.path.startswith('/api/hermes/') and secrets.compare_digest(
                request.cookies.get('companion_dashboard',''),app.state.dashboard_cookie))
            if not dashboard_cookie and not secrets.compare_digest(supplied.encode(),token.encode()):
                return JSONResponse({'error':'bad or missing token'},status_code=401)
        origin=request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in {str(request.base_url).rstrip('/'),public_origin}:
            return JSONResponse({'detail':'Cross-origin writes are refused'},status_code=403)
        current=selection.set((request.query_params.get('installation','existing'),
                               request.query_params.get('profile',initial.profile or 'default')))
        write_lock=None
        try:
            if request.method not in ('GET','HEAD','OPTIONS') and not request.url.path.startswith('/api/terminal/'):
                installation,_=selection.get()
                if installation not in runtimes:return JSONResponse({'detail':'Unknown installation'},status_code=400)
                write_lock=app.state.write_locks[installation]
                from starlette.concurrency import run_in_threadpool
                await run_in_threadpool(write_lock.acquire)
                runtime=runtimes[installation]
                if str(runtime.root) in app.state.operations.busy:
                    return JSONResponse({'detail':'An action is running for this installation. Wait for it to finish.'},status_code=409)
                if request.url.path!='/api/terminal' and any(row.scope[0]==str(runtime.root) and not row.finished for row in list(app.state.consoles.rows.values())):
                    return JSONResponse({'detail':'Close the native Hermes setup console before changing settings.'},status_code=409)
            response=await call_next(request)
        finally:
            if write_lock:write_lock.release()
            selection.reset(current)
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        if request.url.path.startswith(('/api','/media')):response.headers['Cache-Control']='no-store'
        return response

    @app.get('/api/overview')
    def overview():
        c=load()
        import companion_presence as presence, companion_loops as loops
        import companion_missions as missions, companion_watch as watch
        import companion_thread as thread, companion_outbox as outbox
        now=dt.datetime.now(dt.timezone.utc)
        scene=presence.current(c)
        anchor=presence.last_confirmed(c)
        import companion_intimacy
        intimacy=companion_intimacy.compute(c,now)
        stage = intimacy.get('stage', 0)
        if intimacy.get('can_intimate'): stage = max(stage, 4)
        display_scene = scene
        if scene and isinstance(scene.get('state'), dict):
            raw_outfit = scene['state'].get('outfit', [])
            if isinstance(raw_outfit, list):
                filtered_outfit = filter_wardrobe_items(raw_outfit, stage)
                display_scene = {**scene, 'state': {**scene['state'], 'outfit': filtered_outfit}}
        return {'agent':c.agent,'human':c.human,'type':c.agent_type,'home':str(c.home),
                'timezone':c.timezone,'age':c.current_age(),'birthday_in':c.birthday_in(),
                'state':display_scene,'confirmed_at':anchor['recorded_at'] if anchor else None,
                'moods':presence.mood_history(c,40),
                'loops':loops.loops(c),'missions':missions.missions(c,'open',now),
                'queued':[e for e in outbox.fold(c) if e['status']=='queued'],
                'thread':thread.read(c,now),
                'bars':(__import__('companion_bars').compute(c,now) if c.bars else None),
                'intimacy':intimacy,
                'integrity_lockout':False,
                'integrity_warning':None,
                'problems':watch.problems(c,now)}

    @app.get('/api/timeline')
    def timeline():
        c=load()
        import companion_timeline as tl, companion_intimacy
        intimacy=companion_intimacy.compute(c)
        stage = intimacy.get('stage', 0)
        if intimacy.get('can_intimate'): stage = max(stage, 4)
        rows=[];attempts=[]
        for _,row in sorted(tl.records(c),key=lambda item:item[1]['created_at'],reverse=True):
            if row.get('status')!='saved':
                from .runtime import redact
                attempts.append({'id':row['id'],'at':row.get('created_at'),'status':row.get('status'),'error':redact(row.get('error',''))[:600]})
                continue
            state=row.get('scene',{}).get('state',{})
            raw_outfit = state.get('outfit',[])
            if isinstance(raw_outfit, list):
                raw_outfit = filter_wardrobe_items(raw_outfit, stage)
            rows.append({'id':row['id'],'at':row['scene'].get('recorded_at'),
                         'image':f"/media/timeline/{row['filename']}",
                         'activity':state.get('activity',''),'location':state.get('location',''),
                         'mood':state.get('mood',''),
                         'outfit':', '.join(i['description'] for i in raw_outfit if isinstance(i,dict) and 'description' in i)})
        return {'captures':rows,'albums':tl.albums(c),
                'budget_gb':c.timeline_budget_gb,'enabled':c.image_timeline,'attempts':attempts[:30]}

    @app.get('/api/life')
    def life():
        import companion_presence as presence
        from itertools import islice
        c=load()
        from .content import life_moments
        return {'events':list(islice(life_moments(presence.events(c)),100))}

    @app.get('/media/timeline/{name}')
    def media(name:str):
        c=load()
        import companion_timeline as tl
        if not tl.IMAGE.fullmatch(name):raise HTTPException(404)
        path=tl.root(c)/'images'/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(c.data.resolve()):raise HTTPException(404)
        return FileResponse(path)

    @app.post('/api/timeline/{capture}/keep')
    def keep(capture:str,album:str='Favorites'):
        c=load()
        import companion_timeline as tl
        try:return tl.favorite(c,capture,album)
        except ValueError as exc:raise HTTPException(400,str(exc))

    @app.get('/api/closet')
    def closet_view():
        c=load()
        import companion_presence as presence
        import companion_lifestyle as lifestyle
        import companion_life as life
        now=dt.datetime.now(dt.timezone.utc)
        curr=presence.current(c)
        wardrobe=presence.wardrobe(c).get('items',[])
        if not wardrobe:
            try:
                lifestyle.seed(c)
                wardrobe=presence.wardrobe(c).get('items',[])
            except Exception:
                pass
        init_st=lifestyle.initial(curr,c) if lifestyle.enabled(c) else {'clothes':{}}
        clothes_status=dict(init_st.get('clothes',{}))
        wearing_ids={item['id'] for item in curr['state'].get('outfit',[])} if curr else set()
        for wid in wearing_ids:clothes_status[wid]='wearing'
        tomorrow=life.read_tomorrow_plan(c.life,now)
        laid_out=set(tomorrow.get('laid_out_outfit',[])) if tomorrow else set()
        items=[]
        for w in wardrobe:
            wid=w['id']
            status=clothes_status.get(wid,'clean')
            if wid in wearing_ids:eff='wearing'
            elif wid in laid_out and status!='dirty':eff='laid_out'
            elif status in ('dirty','hamper'):eff='hamper'
            elif status=='washing':eff='washing'
            else:eff='clean'
            items.append({**w,'status':eff})
        intimacy = companion_intimacy.compute(c, now)
        stage = intimacy.get('stage', 0)
        if intimacy.get('can_intimate'): stage = max(stage, 4)

        return {
            'enabled':lifestyle.enabled(c),
            'items':filter_wardrobe_items(items, stage),
            'wearing':filter_wardrobe_items([i for i in items if i['status']=='wearing'], stage),
            'laid_out':{'plan':tomorrow,'items':filter_wardrobe_items([i for i in items if i['status']=='laid_out'], stage)} if tomorrow else None,
            'hamper':filter_wardrobe_items([i for i in items if i['status']=='hamper'], stage),
            'washing':filter_wardrobe_items([i for i in items if i['status']=='washing'], stage),
            'clean':filter_wardrobe_items([i for i in items if i['status']=='clean'], stage),
            'laundry_in_progress':init_st.get('laundry')
        }

    @app.get('/api/ledgers')
    def ledgers():
        c=load()
        import companion_self as slf, companion_notes as notes
        return {'facts':slf.facts(c.human_dir),
                'standing':notes.standing(c),
                'relationship':notes.moments(c),
                'questions':slf.questions(c.life,'open'),
                'preferences':slf._read(c.life/'preferences.jsonl',kind='companion_preference')[-40:]}

    @app.post('/api/facts/{fact_id}/forget')
    def forget(fact_id:str):
        """Retire a fact the human says is wrong. It is superseded, not deleted."""
        c=load()
        import companion_self as slf
        rows=[f for f in slf.facts(c.human_dir) if f['id']==fact_id]
        if not rows:raise HTTPException(404,'no such active fact')
        slf._append(c.human_dir/'facts.jsonl',
                    {'id':fact_id+'-retired','kind':'human_fact','category':rows[0]['category'],
                     'statement':'(retired by '+c.human+')','evidence':'retired in the app',
                     'source':'app','confidence':'stated','status':'active',
                     'supersedes':fact_id,'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                     'provenance':'Retired by the human through the app; the original is retained.'})
        return {'retired':fact_id,'note':'Superseded, not deleted. The original stays in the ledger.'}

    @app.get('/api/settings')
    def get_settings():
        c=load()
        import companion_sensors as sensors
        import companion_render as render
        import companion_integrity, companion_intimacy
        integrity=companion_integrity.verify_integrity(c)
        intimacy=companion_intimacy.compute(c)
        return {'quiet_start':c.quiet_start,'quiet_end':c.quiet_end,'outreach':c.outreach,
                'outreach_per_day':c.outreach_per_day,'adaptive_quiet':c.adaptive_quiet,
                'content_permissions':{k:c.may_send(k) for k in cc.CONTENT_KINDS},
                'location':c.location,'sensors':c.sensors,
                'available_sensors':{k:v['blurb'] for k,v in sensors.REGISTRY.items()},
                'autonomy_windows':c.autonomy_windows,'share_people':c.share_people,
                'timeline_budget_gb':c.timeline_budget_gb,'image_timeline':c.image_timeline,'bars':c.bars,
                'agent_type':c.agent_type,'relationship_progression':c.relationship_progression,
                'relationship_pace':c.relationship_pace,'peer_interaction':c.peer_interaction,
                'image_style':c.image_style,'image_styles':{k:v['label'] for k,v in render.load_styles().items()},
                'explicit':c.explicit,
                'integrity_lockout':False,'integrity_warning':None,
                'intimacy':intimacy,'remote_pin':c.remote_pin}

    ALLOWED={'quiet_start','quiet_end','outreach','outreach_per_day','adaptive_quiet',
             'location','sensors','autonomy_windows','share_people','timeline_budget_gb',
             'content_permissions','image_timeline','bars','relationship_progression',
             'relationship_pace','peer_interaction','image_style','explicit','remote_pin'}

    @app.post('/api/settings')
    def set_settings(payload:dict):
        c=load()
        old=cc.dataclasses.replace(c)
        payload=dict(payload)
        import companion_integrity
        integrity=companion_integrity.verify_integrity(c)
        if payload.get('explicit') is False and c.explicit:
            # Turning OFF adult themes mid-relationship is a one-way door that locks at friendship
            companion_integrity.revoke_nsfw(c)
            payload.pop('explicit')
        elif payload.get('explicit') is True and companion_integrity.is_nsfw_revoked(c):
            raise HTTPException(400, 'Adult themes were permanently turned off for this companion and cannot be re-enabled.')
        adult_confirmed=payload.pop('adult_confirmed',False)
        if payload.get('explicit') is True and not c.explicit and adult_confirmed is not True:
            raise HTTPException(400,'Confirm that both you and the companion are adults before enabling adult themes')
        unknown=sorted(set(payload)-ALLOWED)
        if unknown:raise HTTPException(400,f'not settable from here: {", ".join(unknown)}')
        for key,value in payload.items():setattr(c,key,value)
        try:c.__post_init__()          # the same validation the CLI gets
        except ValueError as exc:raise HTTPException(400,str(exc))
        from .settings_service import validate, preserve_human_records, synchronize
        validate(c)
        with preserve_human_records(old, c):
            c.save()
            companion_integrity.sign_creation(c)
        result={'saved':sorted(payload)}
        runtime,_=select()
        operation=synchronize(app,runtime,old,c)
        if operation:result['operation']=operation
        resp=JSONResponse(result)
        if c.remote_pin:
            import hashlib
            token=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest()
            resp.set_cookie('companion_pin_session',token,max_age=86400*30,httponly=True,samesite='lax')
        elif old.remote_pin and not c.remote_pin:
            resp.delete_cookie('companion_pin_session')
        return resp

    @app.post('/api/auth/pin')
    def verify_pin(payload:dict=Body(...)):
        c=load()
        pin=str(payload.get('pin','')).strip()
        if not c.remote_pin:
            return {'ok':True,'pin_required':False}
        if secrets.compare_digest(pin,c.remote_pin):
            import hashlib
            token=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest()
            resp=JSONResponse({'ok':True})
            resp.set_cookie('companion_pin_session',token,max_age=86400*30,httponly=True,samesite='lax')
            return resp
        return JSONResponse({'ok':False,'detail':'Incorrect 4-digit PIN'},status_code=403)

    @app.get('/api/network')
    def network_info(request:Request):
        c=load()
        port=int(os.environ.get('PORT','38439'))
        client_host=request.client.host if request.client else '127.0.0.1'
        is_local=client_host in ('127.0.0.1','::1','localhost','testclient')
        network_ips=get_network_ips()
        urls=[f"http://{ip}:{port}" for ip in network_ips]
        import hashlib
        expected=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest() if c.remote_pin else ''
        cookie_token=request.cookies.get('companion_pin_session','')
        authenticated=is_local or (not c.remote_pin) or (bool(expected) and secrets.compare_digest(cookie_token,expected))
        return {
            'port':port,
            'is_local':is_local,
            'remote_pin_configured':bool(c.remote_pin),
            'authenticated':authenticated,
            'localhost_url':f"http://localhost:{port}",
            'lan_urls':urls
        }

    @app.get('/api/missions')
    def get_missions():
        c=load()
        import companion_missions as missions
        return {'missions':missions.missions(c,None)}

    @app.post('/api/missions')
    def add_mission(payload:dict):
        c=load()
        import companion_missions as missions
        try:
            row=missions.add(c,payload,dt.datetime.now(dt.timezone.utc))
        except ValueError as exc:raise HTTPException(400,str(exc))
        return row['entry']

    @app.post('/api/missions/{mission}/drop')
    def drop_mission(mission:str):
        c=load()
        import companion_missions as missions
        try:return missions.update(c,mission,'dropped','withdrawn in the app')
        except ValueError as exc:raise HTTPException(400,str(exc))

    @app.get('/api/calendar.ics')
    def calendar_ics():
        c=load()
        import companion_missions as missions
        from fastapi.responses import Response
        import hashlib
        all_missions=missions.missions(c,None)
        lines=[
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Tamanitomo//Companion Calendar//EN",
            f"X-WR-CALNAME:{c.agent}'s Calendar",
        ]
        for m in all_missions:
            wb=m.get('wanted_by')
            if not wb:continue
            clean_date=wb.replace('-','')
            uid=m.get('id',hashlib.sha256(m.get('title','').encode()).hexdigest()[:16])
            status='CONFIRMED' if m.get('status')=='open' else 'CANCELLED' if m.get('status')=='dropped' else 'COMPLETED'
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}@tamanitomo",
                f"DTSTAMP:{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART;VALUE=DATE:{clean_date}",
                f"SUMMARY:{m.get('title')}",
                f"DESCRIPTION:{m.get('detail','')}",
                f"STATUS:{status}",
                "END:VEVENT"
            ])
        lines.append("END:VCALENDAR")
        return Response(
            content="\r\n".join(lines),
            media_type="text/calendar",
            headers={"Content-Disposition":f'attachment; filename="{c.agent}-calendar.ics"'}
        )

    def document_paths(c):
        paths={'SOUL.md':pathlib.Path(c.soul).resolve()}
        for parent in (c.home,c.home/'memories'):
            if not parent.is_dir():continue
            for path in parent.glob('*.md'):
                if path.is_file() and not path.is_symlink() and path.name!='SOUL.md':paths[str(path.relative_to(c.home))]=path
        return paths

    @app.get('/api/documents')
    def documents():return {'documents':sorted(document_paths(load()))}

    @app.get('/api/soul-document')
    def soul_document(document:str='SOUL.md'):
        import hashlib
        path=document_paths(load()).get(document)
        if path is None:raise HTTPException(404,'Unknown document')
        if path.stat().st_size>2_000_000:raise HTTPException(400,'Document exceeds 2 MB')
        body=path.read_text(encoding='utf-8')
        return {'text':body,'revision':hashlib.sha256(body.encode()).hexdigest()}

    @app.post('/api/soul-document')
    def save_soul_document(payload:dict):
        import companion_identity as ident, companion_platform as cp, hashlib, uuid
        c=load();path=document_paths(c).get(payload.get('document','SOUL.md'))
        if path is None:raise HTTPException(404,'Unknown document')
        body=payload.get('text')
        if not isinstance(body,str) or len(body.encode())>2_000_000:raise HTTPException(400,'Document must be text under 2 MB')
        with cp.file_lock(path.parent/('.'+path.name+'.lock')):
            original=path.read_text(encoding='utf-8')
            if hashlib.sha256(original.encode()).hexdigest()!=payload.get('revision'):raise HTTPException(409,'Document changed. Reload before saving.')
            cp.atomic_write(pathlib.Path(c.soul_backups)/(path.name+'.'+uuid.uuid4().hex),original)
            cp.atomic_write(path,body)
        return {'saved':True}

    @app.post('/api/identity-repair')
    def repair_identity(payload:dict):
        import companion_identity as ident, companion_platform as cp, uuid
        c=load();path=pathlib.Path(c.soul).resolve()
        with cp.file_lock(path.parent/('.'+path.name+'.lock')):
            original=path.read_text(encoding='utf-8')
            try:repaired=ident.retrofit(original)
            except ValueError as exc:raise HTTPException(400,str(exc))
            found=ident.sections(repaired)
            missing=[name for name in ('core','appearance','relationship','voice') if name not in found]
            addition=''
            for name in missing:
                body=payload.get('appearance','') if name=='appearance' else ''
                if not isinstance(body,str) or ident.OPEN.search(body) or '/COMPANION-SECTION' in body:raise HTTPException(400,'Use plain section text')
                addition+='\n\n<!-- COMPANION-SECTION:'+name+(' LOCKED' if name in ('appearance','relationship') else '')+' -->\n'+body+'\n<!-- /COMPANION-SECTION:'+name+' -->'
            if addition or repaired!=original:
                cp.atomic_write(pathlib.Path(c.soul_backups)/('SOUL.md.'+uuid.uuid4().hex),original)
                cp.atomic_write(path,repaired+addition+'\n')
        return {'added':missing}

    @app.get('/api/identity')
    def identity():
        c=load()
        import companion_identity as ident
        try:
            _,text=ident.read(c)
            import companion_portrait as portrait
            import companion_render as render
            personas=render.load_personas();boundaries=render.BOUNDARIES if hasattr(render,'BOUNDARIES') else {}
            persona=personas.get(c.persona) or {}
            import companion_catalog as ckat
            frame=ckat.BOUNDARIES.get(c.boundary)
            # A profile header for the page, so Identity opens on who they are
            # rather than on the state of their configuration.
            profile={'agent':c.agent,'human':c.human,'age':c.current_age(),
                     'birthdate':c.birthdate,'pronoun_set':c.pronoun_set,
                     'agent_type':c.agent_type,'timezone':c.timezone,
                     'persona':c.persona,'persona_label':persona.get('label',c.persona),
                     'persona_blurb':persona.get('blurb',''),
                     'boundary':c.boundary,'boundary_label':frame[0] if frame else c.boundary,
                     'relationship_pace':c.relationship_pace,
                     'image_style':c.image_style}
            return {'sections':[{**s,'body':s['body']} for s in ident.sections(text).values()],
                    'portrait':portrait.compile_prompt(c),'profile':profile}
        except OSError as exc:raise HTTPException(500,str(exc))

    @app.post('/api/identity/{section}')
    def write_section(section:str,payload:dict):
        c=load()
        import companion_identity as ident
        _,text=ident.read(c)
        found=ident.sections(text).get(section)
        if not found:raise HTTPException(404,'no such section')
        # Locked means locked against the companion. A person editing their own
        # companion's boundaries in their own app is the entire point of the
        # setting, so this is allowed and is recorded like any other change.
        try:return ident.replace(c,section,payload.get('body',''))
        except ValueError as exc:raise HTTPException(400,str(exc))

    @app.get('/api/portrait')
    def portrait():
        c=load()
        import companion_portrait as pt
        path=pt.portrait_path(c)
        return {'stored':path.is_file(),'image':'/media/portrait' if path.is_file() else None,
                'filename':path.name if path.is_file() else None,
                'bytes':path.stat().st_size if path.is_file() else 0}

    @app.get('/media/portrait')
    def portrait_media():
        c=load()
        import companion_portrait as pt
        path=pt.portrait_path(c)
        if not path.is_file():raise HTTPException(404)
        return FileResponse(path)

    @app.post('/api/portrait')
    def upload_portrait(data:bytes=Body(...,media_type='application/octet-stream')):
        """The likeness itself. Raw image bytes as the body — no multipart, so the
        app needs no parser the kit would otherwise not depend on."""
        c=load()
        import companion_portrait as pt, companion_timeline as tl
        if not data:raise HTTPException(400,'no image in the request body')
        if len(data)>tl.MAX_BYTES:raise HTTPException(400,'Image exceeds 32 MB')
        import tempfile,os as _os
        handle=tempfile.NamedTemporaryFile(delete=False)
        try:
            handle.write(data);handle.close()
            try:return pt.save_reference(c,handle.name)
            except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))
        finally:
            try:_os.unlink(handle.name)
            except OSError:pass

    @app.delete('/api/portrait')
    def forget_portrait():
        c=load()
        import companion_portrait as pt
        path=pt.portrait_path(c)
        if not path.is_file():raise HTTPException(404,'no stored likeness')
        path.unlink()
        return {'removed':path.name}

    @app.post('/api/portrait/describe')
    def describe_portrait(payload:dict|None=None):
        """Ask a vision model for a proposed appearance section.

        It proposes; it does not write. What comes back goes in front of a person,
        and `POST /api/identity/appearance` is what commits it."""
        c=load()
        import companion_vision as vision
        payload=payload or {}
        try:
            return vision.describe(c,model=str(payload.get('model') or ''),
                                   provider=str(payload.get('provider') or ''))
        except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))

    @app.get('/api/health')
    def health():
        c=load()
        import companion_watch as watch, companion_memory as memory, companion_prune as prune
        import companion_vault as vault
        now=dt.datetime.now(dt.timezone.utc)
        return {'problems':watch.problems(c,now),'memory':memory.status(c),
                'storage':prune.survey(c),'vault_repo':vault.is_repo(c.vault),
                'jobs':_jobs(c)}

    @app.get('/api/cost')
    def cost():
        """Token usage, quietly. No warnings, no currency, no judgement."""
        c=load()
        path=c.home/'cron/usage_audit.jsonl'
        by_day={}
        try:
            for line in path.read_text(encoding='utf-8').splitlines()[-20000:]:
                if not line.strip():continue
                try:row=json.loads(line)
                except ValueError:continue
                day=str(row.get('timestamp') or row.get('at') or '')[:10]
                if not day:continue
                bucket=by_day.setdefault(day,{'input':0,'output':0,'runs':0})
                bucket['input']+=int(row.get('input_tokens') or 0)
                bucket['output']+=int(row.get('output_tokens') or 0)
                bucket['runs']+=1
        except OSError:pass
        return {'days':[{'day':k,**v} for k,v in sorted(by_day.items())[-30:]],
                'source':str(path),'available':bool(by_day)}

    def _jobs(c):
        try:
            rows=json.loads((c.home/'cron/jobs.json').read_text(encoding='utf-8'))['jobs']
        except (OSError,ValueError,KeyError):return []
        return [{'name':j.get('name'),'enabled':bool(j.get('enabled')),
                 'last_status':j.get('last_status'),'next_run_at':j.get('next_run_at'),
                 'no_agent':bool(j.get('no_agent'))}
                for j in rows if str(j.get('name','')).startswith(c.agent+' ')]

    @app.get('/')
    def index():
        # A refreshed page must not combine new controllers with cached older
        # helpers after a kit update. Asset URLs identify the exact file bytes.
        import hashlib
        import re
        def versioned(match):
            path=STATIC/pathlib.Path(match[2]).name
            digest=hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            return f'{match[1]}="{match[2]}?v={digest}"'
        html=(STATIC/'index.html').read_text(encoding='utf-8')
        html=re.sub(r'(src|href)="(/static/[^"?]+)"',versioned,html)
        return HTMLResponse(html,headers={'Cache-Control':'no-cache'})

    app.mount('/static',StaticFiles(directory=str(STATIC)),name='static')
    return app
