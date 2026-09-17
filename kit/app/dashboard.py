"""Authenticated same-origin bridge to the installed Hermes dashboard.

The installed UI and API travel together; no partial copy of Hermes settings.
Only private child backends owned by this workspace are proxy targets.
"""
from __future__ import annotations
import asyncio
import atexit
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from urllib.parse import urlencode
import httpx
from fastapi import Request, WebSocket, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

class Dashboards:
    def __init__(self):
        self.rows={};self.lock=threading.Lock()
        atexit.register(self.close)

    def close(self):
        for row in self.rows.values():
            proc=row['process']
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill()
            row['log'].close()
        self.rows.clear()

    def start(self,rt):
        with self.lock:
            key=str(rt.root)
            old=self.rows.get(key)
            if old and old['process'].poll() is None:return old
            if old:old['log'].close()
            python=rt.root/'hermes-agent'/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            if not python.is_file():
                python=Path(rt.command()[0]).resolve().parent/('python.exe' if os.name=='nt' else 'python')
            if not python.is_file():raise ValueError('Hermes Python is unavailable. Install Hermes first.')
            folder=rt.root/'.companion-dashboard';folder.mkdir(exist_ok=True)
            import tempfile
            log=tempfile.TemporaryFile(mode='w+b')
            session=secrets.token_urlsafe(32)
            env=rt.env(rt.root)
            env.update(HERMES_DASHBOARD_SESSION_TOKEN=session,HERMES_PARENT_PID=str(os.getpid()))
            for key in ('HERMES_SERVE_HEADLESS','HERMES_DESKTOP','HERMES_DASHBOARD_READY_FILE'):
                env.pop(key,None)
            script='from hermes_cli.web_server import start_server; start_server(host="127.0.0.1",port=0,open_browser=False)'
            proc=subprocess.Popen([str(python),'-c',script],env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL)
            row={'process':proc,'token':session,'log':log,'port':None}
            self.rows[str(rt.root)]=row
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                log.seek(0);output=log.read().decode('utf-8',errors='replace')
                match=re.search(r'HERMES_DASHBOARD_READY port=(\d+)',output)
                if match:
                    row['port']=int(match[1]);return row
                if proc.poll() is not None:break
                time.sleep(.2)
            proc.terminate()
            from .runtime import redact
            raise ValueError('Hermes dashboard could not start. '+redact(output)[-2000:])


def register(app,select,access_token=''):
    dashboards=Dashboards();app.state.dashboards=dashboards
    app.state.dashboard_cookie=secrets.token_urlsafe(32)

    @app.post('/api/dashboard/start')
    async def start(request:Request):
        rt,profile=select()
        row=await asyncio.to_thread(dashboards.start,rt)
        installation=next(k for k,v in app.state.runtimes.items() if v is rt)
        prefix='/api/hermes/'+installation
        response=JSONResponse({'prefix':prefix,'profile':profile,'running':True})
        response.set_cookie('tamanitomo_dashboard',app.state.dashboard_cookie,httponly=True,
                            samesite='strict',secure=request.url.scheme=='https',path='/api/hermes/',max_age=86400)
        response.set_cookie('companion_dashboard',app.state.dashboard_cookie,httponly=True,
                            samesite='strict',secure=request.url.scheme=='https',path='/api/hermes/',max_age=86400)
        return response

    def backend(installation):
        rt=app.state.runtimes.get(installation)
        row=dashboards.rows.get(str(rt.root)) if rt else None
        if not row or row['process'].poll() is not None or not row['port']:
            raise HTTPException(503,'Open Hermes settings to start the dashboard')
        return row

    @app.api_route('/api/hermes/{installation}/{path:path}',methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'])
    async def proxy(installation:str,path:str,request:Request):
        row=backend(installation)
        prefix='/api/hermes/'+installation
        headers={k:v for k,v in request.headers.items() if k.lower() in ('content-type','accept','range','if-none-match','x-hermes-session-token')}
        headers.update(Authorization='Bearer '+row['token'])
        headers['x-forwarded-prefix']=prefix
        # The backend receives its own loopback origin; external origin validation
        # remains at the companion boundary.
        base=f'http://127.0.0.1:{row["port"]}'
        headers['origin']=base
        query=urlencode([(k,v) for k,v in request.query_params.multi_items() if k!='token'])
        client=httpx.AsyncClient(timeout=httpx.Timeout(180,connect=10),follow_redirects=False)
        try:
            upstream=await client.send(client.build_request(request.method,base+'/'+path,params=query,
                                       headers=headers,content=await request.body()),stream=True)
        except Exception:
            await client.aclose();raise
        response_headers={k:v for k,v in upstream.headers.items() if k.lower() in ('content-type','cache-control','etag','content-disposition','content-range','accept-ranges')}
        if 'location' in upstream.headers:
            location=upstream.headers['location']
            response_headers['location']=prefix+location if location.startswith('/') else location
        async def close():await upstream.aclose();await client.aclose()
        return StreamingResponse(upstream.aiter_bytes(),status_code=upstream.status_code,
                                 headers=response_headers,background=BackgroundTask(close))

    @app.websocket('/api/hermes/{installation}/{path:path}')
    async def websocket_proxy(websocket:WebSocket,installation:str,path:str):
        dash_cookie=websocket.cookies.get('tamanitomo_dashboard') or websocket.cookies.get('companion_dashboard','')
        cookie_ok=secrets.compare_digest(dash_cookie,app.state.dashboard_cookie)
        ws_token=websocket.headers.get('x-tamanitomo-token') or websocket.headers.get('x-companion-token','')
        proxy_ok=bool(access_token) and secrets.compare_digest(ws_token,access_token)
        if not cookie_ok and not proxy_ok:
            await websocket.close(code=1008);return
        from urllib.parse import urlsplit
        origin=websocket.headers.get('origin','')
        if not origin or urlsplit(origin).netloc!=websocket.headers.get('host'):
            await websocket.close(code=1008);return
        row=backend(installation)
        import websockets
        query=[(k,v) for k,v in websocket.query_params.multi_items() if k not in ('token','session_token')]
        query.append(('token',row['token']))
        uri=f'ws://127.0.0.1:{row["port"]}/{path}?'+urlencode(query)
        async with websockets.connect(uri,origin=f'http://127.0.0.1:{row["port"]}',max_size=16_000_000) as upstream:
            await websocket.accept()
            async def incoming():
                while True:
                    message=await websocket.receive()
                    if message['type']=='websocket.disconnect':return
                    await upstream.send(message.get('text') if message.get('text') is not None else message['bytes'])
            async def outgoing():
                async for message in upstream:
                    if isinstance(message,bytes):await websocket.send_bytes(message)
                    else:await websocket.send_text(message)
            tasks=[asyncio.create_task(incoming()),asyncio.create_task(outgoing())]
            try:
                done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:task.result()
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
