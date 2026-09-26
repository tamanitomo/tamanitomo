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
    state = app_directory()
    state.mkdir(parents=True, exist_ok=True)
    token = (
        os.environ.get("TAMANITOMO_TOKEN") or os.environ.get("COMPANION_TOKEN", "")
    ).strip()
    app = build(home=cp.default_home(), token=token, state_dir=state)

    @app.get("/api/instance")
    def instance():
        return {
            "app": "tamanitomo",
            "root": str(app.state.runtimes["existing"].root),
            "protocol": 1,
        }

    port = int(
        os.environ.get("TAMANITOMO_PORT") or os.environ.get("COMPANION_PORT", "38439")
    )
    sockets = []
    try:
        bind_hosts = os.environ.get("TAMANITOMO_BIND") or os.environ.get(
            "COMPANION_BIND", "127.0.0.1"
        )
        for host in bind_hosts.split(","):
            host = host.strip()
            sock = socket.socket(
                socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM
            )
            sockets.append(sock)
            if os.name != "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if ":" in host and hasattr(socket, "IPV6_V6ONLY"):
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind((host, port))
        uvicorn.Server(
            uvicorn.Config(
                app, log_level="warning", access_log=False, proxy_headers=False
            )
        ).run(sockets=sockets)
    finally:
        for sock in sockets:
            sock.close()
        app.state.dashboards.close()
        for row in app.state.consoles.rows.values():
            row.close()


if __name__ == "__main__":
    main()
