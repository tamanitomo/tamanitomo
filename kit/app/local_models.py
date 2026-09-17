"""Host-local inference provisioning, hardware status, and live model management."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile

BASE = 'http://127.0.0.1:11434'
MODELS = [
    {'id': 'qwen3:4b-q4_K_M', 'name': 'Qwen3 4B · compact', 'gb': 2.6, 'memory': '8 GB RAM minimum; 12+ GB preferred for the full stack', 'context': 8192},
    {'id': 'qwen3:8b-q4_K_M', 'name': 'Qwen3 8B · balanced', 'gb': 5.2, 'memory': '16+ GB RAM; roughly 8 GB free GPU memory for acceleration', 'context': 8192},
    {'id': 'qwen3:14b-q4_K_M', 'name': 'Qwen3 14B · more capable', 'gb': 9.3, 'memory': '24–32+ GB RAM; roughly 12–16 GB free GPU memory for acceleration', 'context': 8192},
]

def request(path, payload=None, timeout=5):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
        value = json.load(response)
    if isinstance(value, dict) and value.get('error'):
        raise ValueError(str(value['error']))
    return value

def directory(rt): return rt.root / 'companion-engines' / 'ollama'

def binary(rt):
    root = directory(rt) / 'runtime'
    for path in (root / 'bin/ollama', root / 'ollama', root / 'ollama.exe'):
        if path.is_file():
            return str(path)
    return shutil.which('ollama')

def _service_status(unit_name=None):
    if not unit_name:
        unit_name = os.environ.get('COMPANION_LLAMA_SERVICE', 'companion-llama')
    try:
        res = subprocess.run(
            ["systemctl", "--user", "show", unit_name,
             "--property=ActiveState,SubState,MainPID,MemoryCurrent,ExecStart,LoadState"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode != 0:
            return {'found': False}
        props = dict(line.split('=', 1) for line in res.stdout.splitlines() if '=' in line)
        if props.get('LoadState') != 'loaded':
            return {'found': False}
        mem_bytes = int(props.get('MemoryCurrent', '0') or 0)
        mem_mb = round(mem_bytes / (1024 * 1024), 1) if mem_bytes > 0 else 0
        return {
            'found': True,
            'unit': unit_name,
            'active_state': props.get('ActiveState', 'inactive'),
            'sub_state': props.get('SubState', 'dead'),
            'main_pid': int(props.get('MainPID', '0') or 0),
            'memory_mb': mem_mb,
            'exec_start': props.get('ExecStart', ''),
        }
    except Exception:
        return {'found': False}

def _scan_available_models():
    dirs = [Path('/mnt/nvme2/models'), Path.home() / 'models', Path('/models')]
    results = []
    seen = set()
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            for p in d.rglob('*.gguf'):
                try:
                    if not p.is_file() or 'mmproj' in p.name.lower():
                        continue
                    rp = str(p.resolve())
                    if rp in seen:
                        continue
                    seen.add(rp)
                    size_gb = round(p.stat().st_size / (1024**3), 2)
                    family = 'GGUF Model'
                    nl = p.name.lower()
                    if 'gemma' in nl: family = 'Gemma'
                    elif 'qwen' in nl: family = 'Qwen'
                    elif 'ornith' in nl: family = 'Ornith'
                    elif 'llama' in nl: family = 'Llama'
                    elif 'mistral' in nl: family = 'Mistral'
                    elif 'phi' in nl: family = 'Phi'

                    mmprojs = [m for m in p.parent.glob('*.gguf') if 'mmproj' in m.name.lower()]
                    mmproj_path = str(mmprojs[0].resolve()) if mmprojs else None

                    results.append({
                        'id': rp,
                        'name': p.name,
                        'path': rp,
                        'size_gb': size_gb,
                        'family': family,
                        'mmproj': mmproj_path,
                    })
                except OSError:
                    pass
        except OSError:
            pass
    results.sort(key=lambda x: (x['family'], -x['size_gb']))
    return results

def status(rt):
    online = False
    engine_type = "None"
    loaded_model = None
    server_props = {}
    models = []
    error = ""

    # Probe llama-server /props
    try:
        props = request('/props', timeout=2)
        online = True
        engine_type = "llama.cpp (Vulkan)"
        server_props = {
            'build': props.get('build_info', ''),
            'is_sleeping': props.get('is_sleeping', False),
        }
    except Exception:
        pass

    # Probe /v1/models (llama-server or OpenAI endpoint)
    try:
        m_list = request('/v1/models', timeout=2)
        online = True
        if engine_type == "None":
            engine_type = "OpenAI-compatible server"
        data = m_list.get('data') or m_list.get('models') or []
        if data:
            first = data[0]
            meta = first.get('meta') or {}
            loaded_model = {
                'id': first.get('id') or first.get('name') or first.get('model'),
                'ctx_size': meta.get('n_ctx', 0),
                'params': meta.get('n_params', 0),
                'quant': meta.get('ftype') or (first.get('details') or {}).get('quantization_level') or '',
                'size': meta.get('size', 0),
            }
    except Exception:
        pass

    # Probe Ollama tags if not llama-server
    if not online:
        try:
            val = request('/api/tags', timeout=2)
            models = val.get('models', [])
            online = True
            engine_type = "Ollama"
        except Exception:
            pass

    if not online:
        error = 'Local model server is offline. Use Start to launch the background engine.'

    # Systemd service status
    service_name = os.environ.get('COMPANION_LLAMA_SERVICE', 'companion-llama')
    srv = _service_status(service_name)
    if not srv.get('found'):
        srv = _service_status('llama-server')
    if not srv.get('found'):
        srv = _service_status('ollama')

    # Available models on disk
    disk_models = _scan_available_models()
    exec_start = srv.get('exec_start', '')
    for m in disk_models:
        alias = m['name'].lower().replace('-it', '').replace('-abliterated', '').replace('-uncensored', '')[:24]
        m['alias'] = alias
        m['active'] = bool(m['path'] in exec_start or (loaded_model and loaded_model.get('id') == alias))

    return {
        'online': online,
        'engine': engine_type,
        'error': error,
        'endpoint': BASE,
        'loaded_model': loaded_model,
        'server_props': server_props,
        'service': srv,
        'available_models': disk_models,
        'models': models,
        'installed': bool(srv.get('found') or binary(rt)),
        'directory': str(directory(rt)),
        'recommendations': MODELS,
        'platform': platform.system(),
    }

def asset_name():
    system = platform.system()
    arch = {'x86_64': 'amd64', 'AMD64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if arch is None: raise ValueError('This processor needs a manual Ollama installation from ollama.com/download')
    if system == 'Linux': return f'ollama-linux-{arch}.tar.zst'
    if system == 'Windows': return f'ollama-windows-{arch}.zip'
    if system == 'Darwin': return 'ollama-darwin.tgz'
    raise ValueError('Install Ollama manually on this operating system, then use Start / refresh here.')

def extract(archive, dest):
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                target = (dest / item.filename).resolve()
                if not target.is_relative_to(dest.resolve()) or '\\' in item.filename: raise ValueError('Unsafe archive path')
                if (item.external_attr >> 16) & 0o170000 == 0o120000: raise ValueError('Archive contains a symbolic link')
            bundle.extractall(dest)
    else:
        import contextlib
        with contextlib.ExitStack() as stack:
            stream = stack.enter_context(archive.open('rb'))
            if archive.name.endswith('.zst'):
                import zstandard
                stream = stack.enter_context(zstandard.ZstdDecompressor().stream_reader(stream))
                mode = 'r|'
            else:
                mode = 'r|gz'
            bundle = stack.enter_context(tarfile.open(fileobj=stream, mode=mode))
            for item in bundle:
                bundle.extract(item, dest, filter='data')

def install(rt, report):
    if binary(rt): return {'note': 'Ollama is already installed. Use Start / refresh, then choose model weights.'}
    name = asset_name(); root = directory(rt); root.mkdir(parents=True, exist_ok=True)
    report('Finding the official Ollama release for this host')
    req = urllib.request.Request('https://api.github.com/repos/ollama/ollama/releases/latest', headers={'User-Agent': 'tamanitomo'})
    with urllib.request.urlopen(req, timeout=30) as response: release = json.load(response)
    asset = next((a for a in release['assets'] if a['name'] == name), None)
    if not asset: raise ValueError('No official Ollama archive for this host. See ollama.com/download.')
    digest = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest): raise ValueError('The official release has no SHA-256 digest; install it manually instead.')
    url = asset['browser_download_url']
    if not url.startswith('https://github.com/ollama/ollama/releases/download/'): raise ValueError('Unexpected Ollama release source')
    size = int(asset['size'])
    if shutil.disk_usage(root).free < size * 4: raise ValueError('Free more disk space before installing Ollama (archive plus extracted runtime).')
    with tempfile.TemporaryDirectory(prefix='.install-', dir=root) as temp:
        temp = Path(temp); archive = temp / name; sha = hashlib.sha256(); total = 0; last = -1
        with urllib.request.urlopen(url, timeout=60) as response, archive.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > size: raise ValueError('Ollama archive is larger than its release metadata')
                sha.update(chunk); out.write(chunk)
                progress = total * 100 // size
                if progress // 10 != last: report(f'Downloading Ollama {release["tag_name"]}: {progress}%'); last = progress // 10
        if total != size or sha.hexdigest() != digest[7:]: raise ValueError('Ollama archive integrity check failed; retry the download')
        report('Verified SHA-256. Extracting Ollama beside Hermes')
        stage = temp / 'runtime'; stage.mkdir(); extract(archive, stage)
        if not any((stage / p).is_file() for p in ('bin/ollama', 'ollama', 'ollama.exe')): raise ValueError('Ollama archive has an unexpected layout')
        stage.rename(root / 'runtime')
    return {'note': 'Ollama installed on the Hermes host. Start it, then download a recommended model.'}

def start(rt, report):
    service_name = os.environ.get('COMPANION_LLAMA_SERVICE', 'companion-llama')
    srv = _service_status(service_name)
    if not srv.get('found'):
        srv = _service_status('llama-server')
    if srv.get('found'):
        return server_control(rt, 'start', report)
    if status(rt)['online']: return {'note': 'Using the local model server already running on this host.'}
    executable = binary(rt)
    if not executable: raise ValueError('Install Ollama or configure a local model service first')
    root = directory(rt); root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1', OLLAMA_CONTEXT_LENGTH='8192')
    if Path(executable).is_relative_to(root): env['OLLAMA_MODELS'] = str(root / 'models')
    with (root / 'server.log').open('ab') as log:
        proc = subprocess.Popen([executable, 'serve'], env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                start_new_session=os.name != 'nt', creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
    report('Starting local server on the Hermes host')
    for _ in range(60):
        if status(rt)['online']: return {'note': 'Local server is ready.'}
        if proc.poll() is not None: raise ValueError('Local server could not start. Check ' + str(root / 'server.log'))
        time.sleep(1)
    raise ValueError('Local server startup timed out.')

def server_control(rt, action: str, report=None):
    if action not in ('start', 'stop', 'restart'):
        raise ValueError(f"Invalid server action {action!r}")
    service_name = os.environ.get('COMPANION_LLAMA_SERVICE', 'companion-llama')
    srv = _service_status(service_name)
    if not srv.get('found'):
        srv = _service_status('llama-server')
    if srv.get('found'):
        unit = srv['unit']
        if report: report(f"Running systemctl --user {action} {unit}")
        res = subprocess.run(["systemctl", "--user", action, unit], capture_output=True, text=True)
        if res.returncode != 0:
            raise ValueError(f"Failed to {action} {unit}: {res.stderr.strip()}")
        if action in ('start', 'restart'):
            if report: report("Waiting for model server to initialize on Vulkan...")
            for _ in range(35):
                time.sleep(1)
                try:
                    m = request('/v1/models', timeout=2)
                    if m: return {'ok': True, 'action': action, 'note': f'{unit} is online and serving models.'}
                except Exception:
                    pass
            return {'ok': True, 'action': action, 'note': f'{unit} command issued; server is initializing.'}
        return {'ok': True, 'action': action, 'note': f'{unit} stopped successfully.'}
    elif action == 'start':
        return start(rt, report or (lambda msg: None))
    raise ValueError("No managed local model service detected on this host.")

def switch_model(rt, model_path: str, alias: str = '', ctx_size: int = 131072, report=None):
    src = Path(model_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Model file not found at {src}")
    if src.suffix.lower() != '.gguf':
        raise ValueError("Selected model must be a .gguf file")

    if not alias:
        alias = src.stem.lower().replace('-it', '').replace('-abliterated', '').replace('-uncensored', '')[:24]

    mmprojs = [m for m in src.parent.glob('*.gguf') if 'mmproj' in m.name.lower()]
    mmproj_arg = f" --mmproj {mmprojs[0]}" if mmprojs else ""

    service_name = os.environ.get('COMPANION_LLAMA_SERVICE', 'companion-llama')
    dropin_dir = Path.home() / f'.config/systemd/user/{service_name}.service.d'
    dropin_dir.mkdir(parents=True, exist_ok=True)
    dropin_file = dropin_dir / '98-companion-model.conf'

    llama_bin = os.environ.get('LLAMA_SERVER_BIN') or shutil.which('llama-server') or 'llama-server'
    content = f"""[Service]
ExecStart=
ExecStart={llama_bin} --model {src} --alias {alias} --host 127.0.0.1 --port 11434 --ctx-size {ctx_size} --parallel 2 --n-gpu-layers 99 --threads 8 --threads-batch 8 --batch-size 1024 --ubatch-size 256 --cache-ram 0 --ctx-checkpoints 1 --jinja --chat-template-kwargs '{{"enable_thinking":false}}' --reasoning off --cache-type-k q4_0 --cache-type-v q4_0 --flash-attn on --predict 4096 --no-warmup{mmproj_arg}
Restart=no
MemoryHigh=22G
MemoryMax=24G
MemorySwapMax=1G
LimitCORE=0
KillMode=control-group
TimeoutStopSec=20
"""
    if report: report(f"Configuring local server for {alias}...")
    dropin_file.write_text(content, encoding='utf-8')

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    if report: report("Restarting model server on Vulkan GPU...")
    subprocess.run(["systemctl", "--user", "restart", service_name], check=True)

    online = False
    for _ in range(40):
        time.sleep(1)
        try:
            m = request('/v1/models', timeout=2)
            if m:
                online = True
                break
        except Exception:
            pass

    return {
        'ok': True,
        'model': alias,
        'path': str(src),
        'online': online,
        'note': f"Switched active model to {alias}. {'Server is ready.' if online else 'Server is initializing.'}"
    }

def pull(rt, ident, report):
    choice = next((m for m in MODELS if m['id'] == ident), None)
    if not choice: raise ValueError('Choose a recommended model weight variant')
    start(rt, report)
    root = directory(rt); root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < choice['gb'] * 1_000_000_000 * 1.2: raise ValueError('Not enough free disk space for these model weights')
    req = urllib.request.Request(BASE + '/api/pull', data=json.dumps({'model': ident, 'stream': True}).encode(), headers={'Content-Type': 'application/json'})
    last = ''; success = False
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=1800) as response:
        for line in response:
            row = json.loads(line)
            if row.get('error'): raise ValueError(str(row['error']))
            message = row.get('status', 'Downloading')
            if row.get('total'): message += f' · {int(row.get("completed", 0) * 100 / row["total"])}%'
            if message != last: report(message); last = message
            success = row.get('status') == 'success'
    if not success: raise ValueError('Model download was interrupted; retry to resume it')
    return {'note': ident + ' downloaded. Select Use for this companion to change its model.'}

def assign(rt, home, ident):
    import companion_config as cc
    import companion_platform as cp
    import uuid
    from .manage import save_config

    is_ollama = False
    try:
        tags = request('/api/tags')
        names = {m.get('name') for m in tags.get('models', [])}
        if ident in names or any(m['id'] == ident for m in MODELS):
            is_ollama = True
    except Exception:
        pass

    if is_ollama:
        names = {m.get('name') for m in request('/api/tags').get('models', [])}
        if not isinstance(ident, str) or ident not in names or ident.endswith(('-cloud', ':cloud')):
            raise ValueError('Choose an installed local model')
        info = request('/api/show', {'model': ident})
        if info.get('remote_host') or info.get('remote_model'):
            raise ValueError('Choose local weights, not a cloud model')
        if 'tools' not in info.get('capabilities', []):
            raise ValueError('This model does not advertise tool calling, which Hermes needs. Choose a recommended model.')
        # A small real inference confirms the weights can load before editing any profile.
        request('/api/chat', {'model': ident, 'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                              'stream': False, 'think': False, 'keep_alive': 0, 'options': {'num_predict': 8, 'num_ctx': 8192}}, timeout=180)
        def mutate(cfg):
            cfg['model'] = {'default': ident, 'provider': 'ollama', 'base_url': BASE + '/v1', 'context_length': 8192}
            cfg['fallback_providers'] = []
        with cp.file_lock(home / '.companion-profile-editor.lock'):
            path = home / cc.CONFIG_NAME
            raw = json.loads(path.read_text()) if path.exists() else None
            if raw is not None:
                cp.atomic_write(home / 'companion-config-backups' / ('local-model-' + uuid.uuid4().hex + '.json'), path.read_text())
            save_config(home, mutate)
            if raw is not None:
                raw.update(models={}, context_mode='fixed', context_tokens=8192)
                cp.atomic_write(path, json.dumps(raw, indent=2, ensure_ascii=False) + '\n')
        return {'note': 'Local model tested and saved for this profile; cloud fallbacks cleared. Review background job models and use Apply job models, then restart the gateway to reload workers.'}

    with cp.file_lock(home / '.companion-profile-editor.lock'):
        path = home / cc.CONFIG_NAME
        if path.exists():
            cfg = json.loads(path.read_text(encoding='utf-8'))
            cfg.setdefault('models', {})
            cfg['models']['chat'] = {
                'provider': 'custom:local_llama',
                'model': ident,
                'reasoning_effort': 'none'
            }
            cfg['models']['loops'] = {
                'provider': 'custom:local_llama',
                'model': ident,
                'reasoning_effort': 'none'
            }
            cfg['models']['reflection'] = {
                'provider': 'custom:local_llama',
                'model': ident,
                'reasoning_effort': 'none'
            }
            cp.atomic_write(path, json.dumps(cfg, indent=2, ensure_ascii=False) + '\n')
    return {'note': f"Model {ident} assigned to this companion for chat, loops, and reflection."}

def register(app, select):
    def op(label, fn):
        rt, p = select(); home = rt.home(p)
        return app.state.operations.submit(str(rt.root), label, lambda report: fn(rt, home, report), profile=p)

    @app.get('/api/local-models')
    def get(): return status(select()[0])

    @app.post('/api/local-models/server/control')
    def control_route(payload: dict):
        action = payload.get('action', 'restart')
        return op(f'{action.title()} model server', lambda rt, h, r: server_control(rt, action, r))

    @app.post('/api/local-models/server/switch')
    def switch_route(payload: dict):
        path = payload.get('path', '')
        alias = payload.get('alias', '')
        ctx_size = int(payload.get('ctx_size', 131072))
        return op('Switch model weights', lambda rt, h, r: switch_model(rt, path, alias, ctx_size, r))

    @app.post('/api/local-models/install')
    def install_route(): return op('Install Ollama', lambda rt, h, r: install(rt, r))

    @app.post('/api/local-models/start')
    def start_route(): return op('Start local server', lambda rt, h, r: start(rt, r))

    @app.post('/api/local-models/pull')
    def pull_route(payload: dict): return op('Download local model', lambda rt, h, r: pull(rt, payload.get('model'), r))

    @app.post('/api/local-models/assign')
    def assign_route(payload: dict): return op('Use local model', lambda rt, h, r: assign(rt, h, payload.get('model')))
