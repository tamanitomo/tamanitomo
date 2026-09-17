"""Launch the companion workspace without requiring a configured profile first."""
from __future__ import annotations
import json
import os
import secrets
import socket
import threading
import time
import urllib.request
import urllib.parse
import webbrowser
from .common import print, resolve


def lan_addresses():
    addresses=set()
    try:addresses.update(a[4][0] for a in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))
    except OSError:pass
    # UDP connect asks the kernel for a route; no packets or external requests are sent.
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
            probe.connect(('192.0.2.1',9));addresses.add(probe.getsockname()[0])
    except OSError:pass
    return sorted(a for a in addresses if not a.startswith('127.') and a!='0.0.0.0')

def cmd_app(args):
    """Open the companion workspace and Hermes management app."""
    c=resolve(args)
    import uvicorn
    from kit.app.server import build
    from kit.app.runtime import app_directory
    import companion_platform as cp
    state=app_directory()
    state.mkdir(parents=True,exist_ok=True)
    token_file=state/'access-token'
    with cp.file_lock(state/'.token.lock'):
        if not token_file.exists():cp.atomic_write(token_file,secrets.token_urlsafe(32)+'\n')
        if os.name!='nt':token_file.chmod(0o600)
        token=getattr(args,'token','') or token_file.read_text().strip()
    if not token:raise ValueError('The access token is empty. Remove the access-token file and relaunch to generate a new one.')
    host=getattr(args,'host','0.0.0.0');port=getattr(args,'port',8770)
    browser_host='127.0.0.1' if host in ('0.0.0.0','::') else host
    if ':' in browser_host:browser_host='['+browser_host+']'
    registry=state/'workspace-server.json'
    def reuse(candidate):
        req=urllib.request.Request(f'http://{browser_host}:{candidate}/api/instance',headers={'x-tamanitomo-token':token,'x-companion-token':token})
        try:
            with urllib.request.urlopen(req,timeout=2) as response:info=json.load(response)
            if info.get('app') not in ('tamanitomo','companion-kit') or info.get('root')!=str(c.hermes_root):return False
            url=f'http://{browser_host}:{candidate}/?'+urllib.parse.urlencode({'token':token,**({'profile':c.profile} if c.profile else {})})
            print('Tamanitomo is already running: '+url)
            if not args.no_open:webbrowser.open(url)
            return True
        except (OSError,ValueError):return False
    if port==8770:
        try:
            saved=json.loads(registry.read_text())
            if saved.get('host')==host and saved.get('root')==str(c.hermes_root) and reuse(int(saved['port'])):return 0
        except (OSError,ValueError,KeyError,TypeError):pass
    sock=socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET,socket.SOCK_STREAM)
    if os.name!='nt':sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try:
        sock.bind((host,port))
    except OSError:
        if port!=8770:raise
        # Reuse only a workspace that proves it knows this installation's token.
        if reuse(port):sock.close();return 0
        sock.bind((host,0))
    port=sock.getsockname()[1]
    cp.atomic_write(registry,json.dumps({'host':host,'port':port,'root':str(c.hermes_root)}))
    url=f'http://{browser_host}:{port}/?'+urllib.parse.urlencode({'token':token,**({'profile':c.profile} if c.profile else {})})
    print('Tamanitomo · '+str(c.hermes_root))
    print(url)
    if host=='0.0.0.0':
        for address in lan_addresses():print('Local network: '+url.replace(browser_host,address,1))
        print('Other devices: use this host’s LAN IP with the same port and access token. Use --host 127.0.0.1 for host-only access.')
    print('Close with Ctrl-C. Installed Hermes gateway jobs run independently.')
    app=build(home=c.home,token=token,state_dir=state)
    @app.get('/api/instance')
    def instance():return {'app':'tamanitomo','root':str(c.hermes_root),'protocol':1}
    server=uvicorn.Server(uvicorn.Config(app,host=host,port=port,log_level='warning',access_log=False))
    def open_when_ready():
        for _ in range(200):
            if server.started:webbrowser.open(url);return
            if server.should_exit:return
            time.sleep(.1)
    if not args.no_open:threading.Thread(target=open_when_ready,daemon=True).start()
    from update_release import runtime_lock
    from pathlib import Path
    try:
        with runtime_lock(Path(__file__).resolve().parents[2]):server.run(sockets=[sock])
    finally:
        sock.close()
        app.state.dashboards.close()
        for row in app.state.consoles.rows.values():row.close()
    return 0
