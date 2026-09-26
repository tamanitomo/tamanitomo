"""Companion workspace API with request-scoped Hermes profiles."""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import sys
import secrets

from .wardrobe import (
    filter_wardrobe_items,
    is_blacklisted_undergarment,
    is_intimate_garment,
)


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
    from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
    from fastapi.staticfiles import StaticFiles

    from .runtime import Runtime, Operations, app_directory
    public_origin=(os.environ.get('TAMANITOMO_PUBLIC_ORIGIN') or os.environ.get('COMPANION_PUBLIC_ORIGIN','')).rstrip('/')
    if public_origin:
        from urllib.parse import urlsplit
        parsed=urlsplit(public_origin)
        if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:raise ValueError('Public origin must be an HTTPS origin without a path')
    initial=cc.load(home)
    default_home_state = initial.hermes_root/'.companion-app' if (initial.hermes_root/'.companion-app').exists() and not (initial.hermes_root/'.tamanitomo-app').exists() else initial.hermes_root/'.tamanitomo-app'
    state=pathlib.Path(state_dir) if state_dir else (default_home_state if home else app_directory())
    runtimes={'existing':Runtime(initial.hermes_root), 'managed':Runtime(state/'managed-hermes',managed=True)}
    linked_file=state/'linked-installations.json'
    if linked_file.exists():
        linked=json.loads(linked_file.read_text(encoding='utf-8'))
        for ident,root in linked.items():
            if re.fullmatch(r'linked-[a-f0-9]{12}',ident) and isinstance(root,str):runtimes[ident]=Runtime(root)
    selection=ContextVar('companion_selection',default=('existing',initial.profile or 'default'))

    def select():
        installation,profile=selection.get()
        if installation not in runtimes:raise ValueError('Unknown Hermes installation')
        return runtimes[installation],profile

    from companion_config import access_pin, save_access_pin

    def load():
        # Re-read on every request. The CLI, the cron jobs and this page all
        # write the same files, and a cached config is how a page ends up
        # showing settings that were changed twenty minutes ago.
        runtime,profile=select()
        c=cc.load(runtime.home(profile))
        c.remote_pin=access_pin(initial.hermes_root,c.remote_pin)
        return c

    app=FastAPI(title='tamanitomo',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.runtimes=runtimes
    app.state.linked_installations_file=linked_file
    import threading
    app.state.write_locks={key:threading.Lock() for key in runtimes}
    from .manage import register
    register(app,select,load,Operations(state/'operations'))
    from .content import register as register_content
    register_content(app,load)
    from .journal_archive import register as register_journal_archive
    register_journal_archive(app,load)
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

    pin_attempts={}
    pin_attempt_lock=threading.Lock()

    def check_pin(pin,expected,client):
        import time
        now=time.monotonic()
        with pin_attempt_lock:
            for host,(_,expiry) in list(pin_attempts.items()):
                if expiry<=now:pin_attempts.pop(host,None)
            count,expiry=pin_attempts.get(client,(0,now+60))
            if count>=5 or (client not in pin_attempts and len(pin_attempts)>=1024):return None
            if secrets.compare_digest(pin,expected):
                pin_attempts.pop(client,None)
                return True
            pin_attempts[client]=(count+1,expiry)
            return False

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
                    cookie_token=request.cookies.get('tamanitomo_pin_session') or request.cookies.get('companion_pin_session','')
                    header_pin=request.headers.get('x-tamanitomo-pin') or request.headers.get('x-companion-pin','')
                    pin_ok=(bool(cookie_token) and secrets.compare_digest(cookie_token,expected)) or \
                           (bool(header_pin) and check_pin(header_pin,c.remote_pin,client_host) is True)
                    if not pin_ok:
                        return JSONResponse({'pin_required':True,'error':'Remote access locked. Enter 4-digit PIN.'},status_code=401)
            except Exception:
                return JSONResponse({'error':'Workspace access configuration could not be read'},status_code=503)
        # An optional shared token, for the person who does put this behind a
        # tunnel. Absent, the only protection is the localhost bind, and the
        # page says so rather than implying otherwise.
        if token and request.url.path.startswith(('/api','/media')):
            supplied=request.headers.get('x-tamanitomo-token') or request.headers.get('x-companion-token') or request.query_params.get('token','')
            dash_cookie=request.cookies.get('tamanitomo_dashboard') or request.cookies.get('companion_dashboard','')
            dashboard_cookie=(request.url.path.startswith('/api/hermes/') and secrets.compare_digest(
                dash_cookie,app.state.dashboard_cookie))
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
        if request.url.path.startswith(('/api','/media')) and 'Cache-Control' not in response.headers:
            response.headers['Cache-Control']='no-store'
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
        setup_pending = []
        if not getattr(c, 'location', '') and not getattr(c, 'sensors', []):
            setup_pending.append('sensors')
        if getattr(c, 'image_style', 'none') == 'none' and getattr(c, 'image_mode', 'none') == 'none':
            setup_pending.append('images')
        import yaml
        cfg_path = c.home / 'config.yaml'
        has_voice = False
        if cfg_path.is_file():
            try:
                cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
                if (cfg.get('tts') or {}).get('provider'):
                    has_voice = True
            except Exception:
                pass
        if not has_voice:
            setup_pending.append('voice')

        state = display_scene.get('state', {}) if isinstance(display_scene, dict) else {}
        commitments = [dict(item) for item in state.get('commitments', [])
                       if isinstance(item, dict)]

        return {'agent':c.agent,'human':c.human,'type':c.agent_type,'home':str(c.home),
                'timezone':c.timezone,'age':c.current_age(),'birthday_in':c.birthday_in(),
                'state':display_scene,'confirmed_at':anchor['recorded_at'] if anchor else None,
                'moods':presence.mood_history(c,40),
                'loops':loops.loops(c),'missions':missions.missions(c,'open',now),
                'commitments':commitments,
                'queued':[e for e in outbox.fold(c) if e['status']=='queued'],
                'thread':thread.read(c,now),
                'bars':(__import__('companion_bars').compute(c,now) if c.bars else None),
                'intimacy':intimacy,
                'level_event':(companion_intimacy.level_event(c,intimacy)
                               if c.bars and c.relationship_progression!='off' else None),
                'integrity_lockout':False,
                'integrity_warning':None,
                'problems':watch.problems(c,now),
                'setup_pending':setup_pending}

    @app.post('/api/closeness/seen')
    def closeness_seen(payload:dict):
        """The level-change pop-up was shown; do not show it again."""
        import companion_intimacy
        stage=payload.get('stage')
        if not isinstance(stage,int) or not 0<=stage<=4:raise HTTPException(400,'stage must be 0 to 4')
        return companion_intimacy.acknowledge_level(load(),stage)

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
                         'filename':row['filename'],
                         'primary_filename':row.get('primary_filename',row['filename']),
                         'variants':row.get('variants',[]),
                         'prompts':row.get('prompts'),
                         'active_prompt_type':row.get('active_prompt_type'),
                         'activity':state.get('activity',''),'location':state.get('location',''),
                         'mood':state.get('mood',''),
                         'outfit':', '.join(i['description'] for i in raw_outfit if isinstance(i,dict) and 'description' in i)})
        return {'captures':rows,'albums':tl.albums(c),'agent':c.agent,
                'interval_minutes':c.image_interval_minutes,
                'budget_gb':c.timeline_budget_gb,'enabled':c.image_timeline,'attempts':attempts[:30]}

    @app.get('/api/schedule')
    def schedule(day:str=''):
        """What the companion expects a given day to look like.

        The calendar only ever knew about events somebody had entered, so a
        companion with a full imagined week showed an empty month -- and there was
        nowhere to look before asking her about her plans.
        """
        import datetime as _dt
        from zoneinfo import ZoneInfo
        import companion_life as life
        c=load()
        try:tz=ZoneInfo(c.timezone or 'UTC')
        except Exception:tz=_dt.timezone.utc
        now=_dt.datetime.now(tz)
        try:target=_dt.date.fromisoformat(day) if day else now.date()
        except ValueError:raise HTTPException(400,'Use a YYYY-MM-DD date')
        try:return life.expected_day(c.life,target,now)
        except ValueError as exc:raise HTTPException(400,str(exc))

    @app.get('/api/life')
    def life():
        import companion_presence as presence
        from itertools import islice
        c=load()
        from .content import life_moments
        return {'events':list(islice(life_moments(presence.events(c)),100))}

    # How long a picture may be reused without asking. A rendered capture is
    # written once and never edited in place -- a re-render lands under a new
    # name -- so a day is safe and makes scrolling back through a library cost
    # nothing at all.
    MEDIA_MAX_AGE=86400

    @app.get('/media/timeline/{name}')
    def media(name:str,request:Request):
        c=load()
        import companion_timeline as tl
        if not tl.IMAGE.fullmatch(name):raise HTTPException(404)
        path=tl.root(c)/'images'/name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(c.data.resolve()):raise HTTPException(404)
        # A gallery scrolls past the same pictures over and over, and these are
        # multi-megabyte files. The middleware stamps `no-store` on everything
        # under /api and /media, which forbids keeping them even briefly, so
        # every pass re-fetched the whole library -- on a phone, repeatedly.
        #
        # They are private to this companion, so they stay out of shared caches,
        # but this browser may hold them. The 304 is answered here: the version
        # of Starlette in use sets an ETag and then serves the body anyway, so a
        # revalidation cost exactly as much as having no cache at all.
        stat=path.stat()
        etag=f'"{int(stat.st_mtime)}-{stat.st_size}"'
        headers={'Cache-Control':f'private, max-age={MEDIA_MAX_AGE}','ETag':etag}
        if etag in [x.strip() for x in (request.headers.get('if-none-match') or '').split(',')]:
            return Response(status_code=304,headers=headers)
        return FileResponse(path,headers=headers)

    @app.post('/api/timeline/{capture}/keep')
    def keep(capture:str,album:str='Favorites'):
        c=load()
        import companion_timeline as tl
        try:return tl.favorite(c,capture,album)
        except ValueError as exc:raise HTTPException(400,str(exc))

    @app.post('/api/timeline/{capture}/rerender')
    def rerender_timeline(capture:str,payload:dict|None=None):
        c=load()
        import companion_timeline as tl, companion_media as media, companion_portrait as pt
        path=tl.capture_path(c,capture)
        if not path.exists():raise HTTPException(404,'Capture not found')
        row=json.loads(path.read_text(encoding='utf-8'))
        if row.get('status')!='saved':raise HTTPException(400,'Can only rerender a saved capture')
        payload=payload or {}
        preset_id=payload.get('preset_id') or payload.get('preset')
        recipe=media.effective(c)
        presets=media.load(c).get('presets',[])
        preset=next((p for p in presets if p['id']==preset_id),None)
        if not preset:
            preset_id=recipe.get('routes',{}).get('portrait') or recipe.get('default_preset')
            preset=next((p for p in presets if p['id']==preset_id),None)
        if not preset:
            raise HTTPException(400,'No valid image preset available')
        scene=row.get('scene',{})
        overrides=pt.recorded_overrides(c,record=scene)
        if payload.get('seed') is not None:
            try:overrides['seed']=int(payload['seed'])
            except (ValueError,TypeError):pass
        # Rendering took as long as rendering takes while the request sat open,
        # so pressing Generate did nothing visible at all: no progress, no wheel,
        # nothing in the status toast that follows you around the site, and on a
        # slow provider the connection gave out before the picture arrived. It
        # goes through the same operation queue as every other long job now, so
        # the toast reports it wherever you happen to be.
        def run(rt,companion,report):
            # Another version of a moment is still that moment, not a new creation.
            generated=media.generate(companion,preset['id'],'portrait',overrides,report,purpose='capture')
            try:
                updated=tl.add_variant(companion,capture,generated['path'],generated['provider'],prompts=generated.get('prompts'))
            finally:
                media.discard_scratch(generated['path'])
            variant=updated.get('variants',[])[-1] if updated.get('variants') else None
            if variant:
                from .content import with_etags
                variant=with_etags(companion,[variant])[0]
                updated=dict(updated,variants=with_etags(companion,updated.get('variants',[])))
            return {'status':'saved','capture_id':capture,'variant':variant,'capture':updated,
                    'note':'New version ready for this moment.'}
        runtime,profile_name=select()
        return app.state.operations.submit(str(runtime.root),'Regenerate photo',
                                           lambda report:run(runtime,c,report),profile=profile_name)

    @app.post('/api/timeline/{capture}/select-variant')
    def select_timeline_variant(capture:str,payload:dict):
        c=load()
        import companion_timeline as tl
        filename=payload.get('filename')
        if not filename:raise HTTPException(400,'Filename is required')
        try:
            updated=tl.select_variant(c,capture,filename)
            return {'status':'saved','capture_id':capture,'filename':updated['filename'],'primary_filename':updated['primary_filename'],'capture':updated}
        except ValueError as exc:
            raise HTTPException(400,str(exc))

    @app.get('/api/closet')
    def closet_view():
        c=load()
        import companion_presence as presence
        import companion_lifestyle as lifestyle
        import companion_life as life
        import companion_intimacy
        now=dt.datetime.now(dt.timezone.utc)
        curr=presence.current(c)
        # Reading the closet changes nothing. Seeding it here used to switch on the
        # whole clothing-care regime -- routine choices and care rules on every
        # presence update -- for anyone who merely opened the tab.
        wardrobe=presence.wardrobe(c).get('items',[])
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
        """Retire a fact the human says is wrong. It is retracted, not deleted,
        and nothing takes its place: earlier releases wrote an active
        "(retired by …)" fact here, which then read as a memory."""
        c=load()
        import companion_self as slf
        if not any(f['id']==fact_id for f in slf.facts(c.human_dir)):raise HTTPException(404,'no such active fact')
        slf.retract_fact(c.human_dir,fact_id,'Marked incorrect by '+c.human+' in the app',dt.datetime.now(dt.timezone.utc))
        return {'retired':fact_id,'note':'Retracted, not deleted. The original stays in the ledger.'}

    @app.get('/api/facts/held')
    def held_facts_list():
        """Statements the reflection held for a person to review. Viewing one
        never makes it a memory."""
        c=load()
        import companion_self as slf
        return {'held':[{k:r.get(k) for k in ('id','statement','evidence','source','category','reasons','recorded_at','pending_decision')}
                        for r in slf.held_facts(c.human_dir)]}

    @app.post('/api/facts/held/{held_id}/decide')
    def held_fact_decide(held_id:str,body:dict=Body(...)):
        """Accept (record as a memory, marked as the owner's override) or
        dismiss one held statement. Repeating a decision is safe; the opposite
        decision afterwards is a conflict."""
        c=load()
        import companion_self as slf
        decision=(body or {}).get('decision')
        if decision not in slf.HELD_DECISIONS:raise HTTPException(400,'decision must be accept or dismiss')
        try:return slf.decide_held(c.human_dir,held_id,decision,dt.datetime.now(dt.timezone.utc),c.human,origin='owner-app')
        except slf.HeldDecisionConflict as exc:raise HTTPException(409,str(exc))
        except ValueError as exc:raise HTTPException(404,str(exc))

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
                'image_interval_minutes':c.image_interval_minutes,'schedule_offset_minutes':c.schedule_offset_minutes,
                'timeline_budget_gb':c.timeline_budget_gb,'image_timeline':c.image_timeline,'bars':c.bars,
                'agent_type':c.agent_type,'relationship_progression':c.relationship_progression,
                'relationship_pace':c.relationship_pace,'peer_interaction':c.peer_interaction,
                'image_style':c.image_style,'image_styles':{k:v['label'] for k,v in render.load_styles().items()},
                'explicit':c.explicit,'adult_images':c.adult_images,
                # The choice exists only once the relationship has reached Bonded.
                'adult_images_available':bool((intimacy or {}).get('can_intimate')),
                'integrity_lockout':False,'integrity_warning':None,
                'intimacy':intimacy,'remote_pin':c.remote_pin}

    ALLOWED={'quiet_start','quiet_end','outreach','outreach_per_day','adaptive_quiet',
             'location','sensors','autonomy_windows','share_people','timeline_budget_gb',
             'content_permissions','image_timeline','image_interval_minutes','bars','relationship_progression',
             'relationship_pace','peer_interaction','image_style','explicit','adult_images','remote_pin'}

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
        # Romance is the prerequisite, so switching it off takes adult imagery with it
        # rather than leaving a permission behind that nothing can act on.
        if payload.get('explicit') is False or companion_integrity.is_nsfw_revoked(c):
            payload['adult_images']=False
        # Adult images are a choice offered at Bonded, not before: the setting is hidden
        # until then and cannot be switched on from here either.
        if payload.get('adult_images') is True and not c.adult_images:
            import companion_intimacy
            if not companion_intimacy.compute(c).get('can_intimate'):
                raise HTTPException(400,'Adult images become available once your relationship reaches Bonded.')
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
        if 'remote_pin' in payload:save_access_pin(initial.hermes_root,c.remote_pin)
        result={'saved':sorted(payload)}
        runtime,_=select()
        operation=synchronize(app,runtime,old,c)
        if operation:result['operation']=operation
        resp=JSONResponse(result)
        if c.remote_pin:
            import hashlib
            token=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest()
            resp.set_cookie('tamanitomo_pin_session',token,max_age=86400*30,httponly=True,samesite='lax')
            resp.set_cookie('companion_pin_session',token,max_age=86400*30,httponly=True,samesite='lax')
        elif old.remote_pin and not c.remote_pin:
            resp.delete_cookie('tamanitomo_pin_session')
            resp.delete_cookie('companion_pin_session')
        return resp

    @app.post('/api/auth/pin')
    def verify_pin(request:Request,payload:dict=Body(...)):
        c=load()
        pin=str(payload.get('pin','')).strip()
        if not c.remote_pin:
            return {'ok':True,'pin_required':False}
        matched=check_pin(pin,c.remote_pin,request.client.host if request.client else 'unknown')
        if matched is None:
            return JSONResponse({'ok':False,'detail':'Too many attempts. Try again in a minute.'},status_code=429,headers={'Retry-After':'60'})
        if matched:
            import hashlib
            token=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest()
            resp=JSONResponse({'ok':True})
            resp.set_cookie('tamanitomo_pin_session',token,max_age=86400*30,httponly=True,samesite='lax')
            resp.set_cookie('companion_pin_session',token,max_age=86400*30,httponly=True,samesite='lax')
            return resp
        return JSONResponse({'ok':False,'detail':'Incorrect 4-digit PIN'},status_code=403)

    @app.get('/api/network')
    def network_info(request:Request):
        c=load()
        port=request.url.port or int(os.environ.get('TAMANITOMO_PORT') or os.environ.get('COMPANION_PORT') or os.environ.get('PORT','38439'))
        client_host=request.client.host if request.client else '127.0.0.1'
        is_local=client_host in ('127.0.0.1','::1','localhost','testclient')
        network_ips=get_network_ips()
        urls=[f"http://{ip}:{port}" for ip in network_ips]
        import hashlib
        expected=hashlib.sha256(f"{c.remote_pin}:{app.state.pin_salt}".encode()).hexdigest() if c.remote_pin else ''
        cookie_token=request.cookies.get('tamanitomo_pin_session') or request.cookies.get('companion_pin_session','')
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
            import companion_soul
            keepers=companion_soul.status(c)
            by={row['id']:row for row in keepers['sections']}
            return {'sections':[{**s,'body':s['body'],'keeper':(by.get(s['name']) or {}).get('keeper'),
                                 'lockable':(by.get(s['name']) or {}).get('lockable',False),
                                 'her_locked':(by.get(s['name']) or {}).get('locked',True),
                                 'guide':(by.get(s['name']) or {}).get('guide',''),
                                 'her':(by.get(s['name']) or {}).get('her'),
                                 'changes':companion_soul.changes(c,s['name'],20)}
                                for s in ident.sections(text).values()
                                # Hermes reads it; the page does not show it.
                                if not (companion_soul.SECTIONS.get(s['name']) or {}).get('hidden')],
                    # Private notes: that they exist and when they open, never what they say.
                    'private':[{'id':r['id'],'title':r['title'],'opens':r.get('opens'),'open':r['her']['can'] or
                                'cooldown' in r['her'] or r['id'] in companion_soul.private_notes(c),
                                'written':r['id'] in companion_soul.private_notes(c)}
                               for r in keepers['sections'] if r['keeper']=='private'],
                    'stage_name':keepers['stage_name'],'days_together':keepers['days_together'],
                    'portrait':portrait.compile_prompt(c),'profile':profile}
        except OSError as exc:raise HTTPException(500,str(exc))

    @app.post('/api/identity-lock')
    def lock_section(payload:dict):
        """The human's switch: keep a shared section exactly as it is, or let it grow."""
        import companion_soul
        try:return companion_soul.set_lock(load(),str(payload.get('section','')),payload.get('locked') is True)
        except ValueError as exc:raise HTTPException(400,str(exc))

    @app.post('/api/identity/{section}')
    def write_section(section:str,payload:dict):
        c=load()
        import companion_soul
        keeper=(companion_soul.SECTIONS.get(section) or {}).get('keeper')
        # Her own words are hers, and the fixed section is the app's.
        if keeper=='hers':raise HTTPException(403,f'{c.agent} writes this section; it can be read but not edited here.')
        if keeper in ('fixed','system'):raise HTTPException(403,'This section is maintained by the app.')
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
        stat=path.stat()
        return FileResponse(path,headers={'Cache-Control':'private, max-age=604800',
                                          'ETag':f'"{int(stat.st_mtime)}-{stat.st_size}"'})

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

    @app.post('/api/portrait/from-content')
    def portrait_from_content(payload:dict):
        """Copy an existing vault image to become the companion's reference portrait."""
        c=load()
        from .content import resolve, KINDS
        import companion_portrait as pt, companion_timeline as tl
        path_str=payload.get('path','')
        p=resolve(c,path_str)
        if KINDS[p.suffix.lower()]!='image':raise HTTPException(400,'Choose an image file')
        if p.stat().st_size>tl.MAX_BYTES:raise HTTPException(400,'Image exceeds 32 MB')
        try:return pt.save_reference(c,str(p))
        except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))

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

    @app.get('/api/image-identity')
    def image_block():
        """The stable description sent to image models, and whether it is current."""
        import companion_image_identity as block
        return block.state(load())

    @app.post('/api/image-identity')
    def set_image_block(payload:dict|None=None):
        """Keep a block, or go back to sending the SOUL prose.

        A block typed or edited by hand is stamped against the appearance as it
        stands now: editing it is how a person says this is the one I want.
        """
        import companion_image_identity as block
        payload=payload or {}
        c=load()
        try:
            if payload.get('follow'):return block.follow(c)
            return block.save(c,str(payload.get('text') or ''))
        except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))
        except FileExistsError as exc:raise HTTPException(409,str(exc))

    @app.post('/api/image-identity/propose')
    def propose_image_block(payload:dict|None=None):
        """Ask a model to derive the block from the appearance section.

        It proposes; it does not write. `POST /api/image-identity` commits.
        """
        import companion_image_identity as block
        payload=payload or {}
        try:
            return block.propose(load(),model=str(payload.get('model') or ''),
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
