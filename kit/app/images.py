"""Image studio HTTP boundary; the generation recipe also runs outside the app."""
import os
from pathlib import Path
import subprocess
import sys
import uuid
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
import companion_media as media
import companion_portrait as portrait


def register(app,select,load):
    from .workflows import register as register_workflows
    register_workflows(app,select,load)

    def operation(label,fn):
        rt,p=select();c=load()
        return app.state.operations.submit(str(rt.root),label,lambda report:fn(rt,c,report),profile=p)

    @app.get('/api/images')
    def settings():
        c=load();data=media.load(c)
        warning=''
        try:connected=media.discovered_presets(c)
        except Exception as exc:connected=[];warning=str(exc)
        # Offer connected providers as editable drafts; GET never writes profile files.
        pinned={p.get('hermes_provider') for p in data['presets'] if p.get('provider')=='hermes'}
        for preset in connected:
            if preset['hermes_provider'] not in pinned and preset['id'] not in {p['id'] for p in data['presets']}:
                data['presets'].append(preset)
                if preset['active'] and not data.get('default_preset'):data['default_preset']=preset['id']
        import companion_identity as identity
        soul=identity.sections(c.soul.read_text()).get('appearance',{}).get('body','') if c.soul.exists() else ''
        scene,_=portrait.scene_block(c)
        import companion_config as cc
        root_settings=media.load(cc.load(c.hermes_root))
        return {'connected_providers':connected,'provider_warning':warning,'settings':data,'effective':media.effective(c),'installation_presets':root_settings.get('presets',[]),'revision':media.revision(c),'identity':portrait.identity_block(c),
                'appearance':soul or portrait.identity_block(c,use_override=False),'scene':scene,'categories':media.CATEGORIES,'parts':media.PARTS}

    @app.post('/api/images')
    def save(payload:dict):
        try:media.save(load(),payload.get('settings'),payload.get('revision'))
        except FileExistsError as exc:raise HTTPException(409,str(exc))
        return {'saved':True,'revision':media.revision(load())}

    @app.get('/api/images/template')
    def template():
        return JSONResponse(media.template(),headers={'Content-Disposition':'attachment; filename="comfy-plantmilk-template.json"'})

    @app.post('/api/images/prompt')
    def prompt(payload:dict):
        return media.compile(load(),payload.get('preset',''),payload.get('category','portrait'),payload.get('parts'))

    FORBIDDEN_NSFW_TERMS = {'nude', 'naked', 'nsfw', 'erotic', 'undressed', 'lingerie', 'nipple', 'explicit', 'sex', 'pussy', 'penis', 'breasts', 'boobs', 'orgasm', 'porn'}

    @app.post('/api/images/generate')
    def generate(payload:dict):
        parts = payload.get('parts') or {}
        combined = ' '.join(str(v) for v in parts.values()).lower()
        if any(term in combined for term in FORBIDDEN_NSFW_TERMS):
            raise HTTPException(400, 'Manual generation of intimate/NSFW media of your companion without their agency and consent is strictly disallowed.')
        def run(rt,c,report):
            result=media.generate(c,payload.get('preset',''),payload.get('category','portrait'),
                payload.get('parts'),report,allow_nsfw=False,draft=payload.get('draft'))
            return {**result,'image':'/api/images/file?name='+result['file'],'note':'Image saved to Creations / image-studio.'}
        return operation('Generate image',run)

    @app.get('/api/images/file')
    def file(name:str):
        if Path(name).name!=name or Path(name).suffix not in ('.png','.jpg','.webp'):raise HTTPException(404,'Image not found')
        root=(load().data/'creations'/'image-studio').resolve();path=(root/name).resolve()
        if path.parent!=root or not path.is_file():raise HTTPException(404,'Image not found')
        return FileResponse(path)

    @app.get('/api/images/modular-template')
    def modular_template():
        from companion_workflow import modular_template
        return modular_template()

    @app.post('/api/images/img2img')
    def img2img(payload:dict):
        from companion_workflow import image_to_image
        data=media.load(load())
        preset=next((p for p in data['presets'] if p['id']==payload.get('preset')),None)
        if preset is None:raise ValueError('Save and select a ComfyUI preset first')
        return image_to_image(preset,payload.get('denoise',.35))

    @app.post('/api/images/check')
    def check(payload:dict):
        base=media.endpoint(payload.get('endpoint',''))
        info=media.request_json(base+'/object_info')
        models={}
        for node in ('CheckpointLoaderSimple','LoraLoader','UpscaleModelLoader','UnetLoaderGGUF','UNETLoader','CLIPLoader','VAELoader'):
            for key,spec in info.get(node,{}).get('input',{}).get('required',{}).items():
                if isinstance(spec[0],list):models[key]=list(dict.fromkeys(models.get(key,[])+spec[0]))
        return {'connected':True,'nodes':list(info),'models':models}

    @app.post('/api/images/install')
    def install():
        def run(rt,c,report):
            root=rt.root/'companion-engines'/'comfyui';root.parent.mkdir(parents=True,exist_ok=True)
            def command(argv,timeout=1200):
                from .runtime import redact
                result=subprocess.run(argv,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=timeout)
                if result.returncode:raise ValueError(redact(result.stderr or result.stdout)[-4000:])
            if not root.exists():
                report('Downloading ComfyUI to the Hermes host')
                command(['git','clone','--depth','1','https://github.com/Comfy-Org/ComfyUI.git',str(root)],180)
            if not (root/'main.py').is_file():raise ValueError('The ComfyUI directory is incomplete; inspect it before retrying')
            python=root/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            if not python.exists():command([sys.executable,'-m','venv',str(root/'venv')],120)
            report('Installing ComfyUI dependencies. Checkpoints and LoRAs are selected separately.')
            command([str(python),'-m','pip','install','-r',str(root/'requirements.txt')])
            return {'note':'ComfyUI installed beside Hermes. Start it here, add your models, then test the saved endpoint.'}
        return operation('Install ComfyUI',run)

    @app.post('/api/images/start')
    def start(payload:dict):
        def run(rt,c,report):
            root=rt.root/'companion-engines'/'comfyui';python=root/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            if not python.is_file():raise ValueError('Install ComfyUI first')
            try:
                media.request_json('http://127.0.0.1:8188/system_stats')
                return {'note':'ComfyUI is already running at http://127.0.0.1:8188'}
            except Exception:pass
            log=open(root/'companion-server.log','ab')
            args=[str(python),str(root/'main.py'),'--listen','127.0.0.1','--port','8188','--disable-api-nodes']
            if payload.get('cpu'):args.append('--cpu')
            proc=subprocess.Popen(args,env={**os.environ,'HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1'},cwd=root,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=os.name!='nt');log.close()
            import time
            for _ in range(60):
                if proc.poll() is not None:raise ValueError('ComfyUI could not start. See '+str(root/'companion-server.log'))
                try:media.request_json('http://127.0.0.1:8188/system_stats');return {'note':'ComfyUI is ready at http://127.0.0.1:8188'}
                except Exception:time.sleep(1)
            return {'note':'ComfyUI is still starting. Test the endpoint shortly; startup log: '+str(root/'companion-server.log')}
        return operation('Start ComfyUI',run)
