"""One backend for local browser and private reverse-proxy access.

Run through a service manager. No token is printed or embedded in frontend files.
"""
import os
from pathlib import Path
import secrets
import socket
import uvicorn
from .server import build
from .runtime import app_directory
import companion_platform as cp


def main():
    state=app_directory();state.mkdir(parents=True,exist_ok=True)
    token = os.environ.get('COMPANION_TOKEN', '').strip()
    app=build(home=Path(os.environ.get('HERMES_HOME',str(Path.home()/'.hermes'))),token=token,state_dir=state)
    @app.get('/api/instance')
    def instance():return {'app':'companion-kit','root':str(app.state.runtimes['existing'].root),'protocol':1}
    port=int(os.environ.get('COMPANION_PORT','38439'));sockets=[]
    try:
        for host in os.environ.get('COMPANION_BIND','127.0.0.1').split(','):
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind((host.strip(),port));sockets.append(sock)
        uvicorn.Server(uvicorn.Config(app,log_level='warning',access_log=False,proxy_headers=False)).run(sockets=sockets)
    finally:
        for sock in sockets:sock.close()
        app.state.dashboards.close()
        for row in app.state.consoles.rows.values():row.close()

if __name__=='__main__':main()
