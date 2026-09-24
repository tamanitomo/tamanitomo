"""A controllable, deterministic, local-only model provider (Phase 1A.6).

BOUNDARY: the *provider transport* -- an OpenAI-compatible
POST /v1/chat/completions over HTTP with Server-Sent Events, the wire Hermes
speaks to a model. It is not a fake Hermes CLI (tests/fake_hermes.py) and not
the workspace's own stream bridge (kit/app/hermes_stream.py); a test that uses
those is not a provider-transport test.

The scenario is chosen by the request's `model` field. Bytes are written in
exactly the chunks each scenario lists, flushed one by one, so a test can cut a
UTF-8 character or an SSE line across transport writes. The bearer token is
generated per run and never read from settings. The server binds 127.0.0.1
only. `hermes_config()` points a synthetic Hermes home at it with every
fallback disabled, for the later integration phase.

    with MockProvider() as provider:
        consume(provider.url, provider.token, 'deltas')
"""
from __future__ import annotations

import codecs
import http.client
import http.server
import json
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit

PUBLIC_TEXT = 'Hello there. I kept the kettle warm.'


def _chunk(delta=None, finish=None, ident='chatcmpl-mock'):
    choice = {'index': 0, 'delta': delta or {}, 'finish_reason': finish}
    return {'id': ident, 'object': 'chat.completion.chunk', 'model': 'mock', 'choices': [choice]}


def _sse(obj):
    return b'data: ' + json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\n\n'


DONE = b'data: [DONE]\n\n'


def _deltas(text, size):
    return [_sse(_chunk({'content': text[i:i + size]})) for i in range(0, len(text), size)]


def _tool_call(name, arguments, ident='call_c1'):
    return _sse(_chunk({'tool_calls': [{'index': 0, 'id': ident, 'type': 'function',
                                        'function': {'name': name, 'arguments': json.dumps(arguments)}}]}))


# Phase 1B activation evidence: commands the pinned `terminal` tool runs in the synthetic
# home (its cwd). Harmless, deterministic, local only; pids are written for the test to observe.
TOOL_COMMANDS = {
    'tool_echo': 'echo c1-tool-ok > c1_tool_output.txt && cat c1_tool_output.txt',
    'tool_sleep': 'echo $$ > c1_tool.pid; exec sleep 45',
}
# Two tool calls in one turn: a Hermes-managed background process (`background: true`, the
# route the pinned tool offers: it refuses a foreground `&` and nohup/disown/setsid wrappers,
# and blocks `sh -c` in single-query mode), then a foreground run of a fixture script that
# detaches its own child with os.setsid() (the test writes c1_detach.py into the home).
TOOL_CHILDREN = [{'command': 'echo $$ > c1_child.pid; exec sleep 45', 'background': True},
                 {'command': 'python3 c1_detach.py'}]
DETACH_SCRIPT = """import os, sys, time
if os.fork() == 0:
    os.setsid()
    if os.fork() == 0:
        fd = os.open(os.devnull, os.O_RDWR)
        for n in (0, 1, 2):
            os.dup2(fd, n)
        open('c1_escaped.pid', 'w').write(str(os.getpid()))
        time.sleep(45)
    os._exit(0)
os.wait()
print('c1-escaped-started')
"""


def scenarios():
    """name -> list of steps. A step is bytes to write, ('sleep', s), or
    ('close',) to drop the connection without finishing."""
    role = _sse(_chunk({'role': 'assistant'}))
    stop = _sse(_chunk(finish='stop'))
    moon = 'Café at night \U0001F319 — done.'
    moon_bytes = b''.join([role, _sse(_chunk({'content': moon})), stop, DONE])
    cut = moon_bytes.index('\U0001F319'.encode()) + 2          # inside the 4-byte moon
    tools_done = _sse(_chunk(finish='tool_calls'))
    final = [role, *_deltas(PUBLIC_TEXT, 7), stop, DONE]
    tool_turns = {name: {'by': 'stream', 1: [role, _tool_call('terminal', {'command': command}), tools_done, DONE],
                         'default': final} for name, command in TOOL_COMMANDS.items()}
    tool_turns['tool_children'] = {'by': 'stream', 'default': final, **{
        i + 1: [role, _tool_call('terminal', args, ident=f'call_c1_{i}'), tools_done, DONE]
        for i, args in enumerate(TOOL_CHILDREN)}}
    return {
        **tool_turns,
        'deltas': [role, *_deltas(PUBLIC_TEXT, 7), stop, DONE],
        'delayed_first_delta': [role, ('sleep', 0.3), *_deltas(PUBLIC_TEXT, 12), stop, DONE],
        'single': [role, _sse(_chunk({'content': PUBLIC_TEXT})), stop, DONE],
        'mixed_fields': [role,
                         _sse(_chunk({'reasoning_content': 'PRIVATE: the owner seems tired'})),
                         _sse(_chunk({'reasoning': 'PRIVATE: plan the reply'})),
                         _sse(_chunk({'tool_calls': [{'index': 0, 'id': 'call_1', 'type': 'function',
                                                      'function': {'name': 'memory', 'arguments': '{"q":"PRIVATE"}'}}]})),
                         *_deltas(PUBLIC_TEXT, 10), stop, DONE],
        'unicode_split': [moon_bytes[:cut], moon_bytes[cut:cut + 1], moon_bytes[cut + 1:]],
        'line_split': [role, *[bytes([b]) for b in _sse(_chunk({'content': 'byte by byte'}))], stop, DONE],
        'truncated': [role, *_deltas(PUBLIC_TEXT[:15], 5), _sse(_chunk(finish='length')), DONE],
        'malformed': [role, *_deltas('Before the bad line. ', 8), b'data: {"choices": [\n\n', DONE],
        'disconnect_before_done': [role, *_deltas(PUBLIC_TEXT, 7)[:3], ('close',)],
        'disconnect_after_done': [role, *_deltas(PUBLIC_TEXT, 7), stop, DONE, ('close',)],
        # Phase 1B C0: a stream that stalls after two deltas (stop/deadline tests), and a
        # provider that fails before sending any stream byte.
        'hang': [role, *_deltas(PUBLIC_TEXT, 7)[:2], ('sleep', 30), *_deltas(PUBLIC_TEXT, 7)[2:], stop, DONE],
        'error_before_first_byte': [('status', 500)],
        # The first request drops mid-stream; the retry completes (recovery).
        'recover': {1: [role, *_deltas(PUBLIC_TEXT, 7)[:2], ('close',)], 'default': [role, *_deltas(PUBLIC_TEXT, 7), stop, DONE]},
        # Phase 1B C1: like `recover`, but the drop is counted over STREAMING requests only, so
        # it always hits the main reply stream (an auxiliary non-stream request cannot absorb it).
        # Phase 1B activation evidence: the first main stream is refused as a context overflow
        # (structured code), so the real CLI runs its reactive compression, then the retry replies.
        'overflow_once': {'by': 'stream', 1: [('status', 400, {
            'code': 'context_length_exceeded', 'type': 'invalid_request_error',
            'message': "This model's maximum context length is 64000 tokens. Please reduce the length of the messages."})],
            'default': [role, *_deltas(PUBLIC_TEXT, 7), stop, DONE]},
        'recover_stream': {'by': 'stream', 1: [role, *_deltas(PUBLIC_TEXT, 7)[:2], ('close',)],
                           'default': [role, *_deltas(PUBLIC_TEXT, 7), stop, DONE]},
    }


class MockProvider:
    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.requests = []           # (scenario, stream, attempt) per request, in order
        self.bodies = []             # request bodies, in order (in memory only; synthetic content)
        self.request_times = []      # time.time() at each request's arrival, same order
        self._counts = {}
        self._lock = threading.Lock()
        self.server = None

    def __enter__(self):
        provider = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *a):pass

            def do_POST(self):
                if urlsplit(self.path).path != '/v1/chat/completions':
                    return self._json(404, {'error': 'not found'})
                if self.headers.get('Authorization') != 'Bearer ' + provider.token:
                    return self._json(401, {'error': 'bad token'})
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                name = body.get('model', '')
                table = scenarios()
                if name not in table:
                    return self._json(400, {'error': f'unknown scenario {name!r}'})
                with provider._lock:
                    attempt = provider._counts[name] = provider._counts.get(name, 0) + 1
                    provider.requests.append((name, bool(body.get('stream')), attempt))
                    provider.bodies.append(body)
                    provider.request_times.append(time.time())
                    if body.get('stream'):
                        streamed = provider._counts[(name, 'stream')] = provider._counts.get((name, 'stream'), 0) + 1
                steps = table[name]
                if isinstance(steps, dict):
                    key = streamed if steps.get('by') == 'stream' and body.get('stream') else attempt
                    steps = steps.get(key, steps['default'])
                if steps and isinstance(steps[0], tuple) and steps[0][0] == 'status':
                    error = steps[0][2] if len(steps[0]) > 2 else {'message': 'mock provider error', 'type': 'server_error'}
                    return self._json(steps[0][1], {'error': error})
                if not body.get('stream'):
                    return self._json(200, provider.completion(name))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                for step in steps:
                    if isinstance(step, tuple) and step[0] == 'sleep':
                        time.sleep(step[1]);continue
                    if isinstance(step, tuple) and step[0] == 'close':
                        self.connection.shutdown(socket.SHUT_RDWR);self.close_connection = True;return
                    self.wfile.write(step);self.wfile.flush()
                self.close_connection = True

            def _json(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers();self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown();self.server.server_close()

    @property
    def url(self):
        host, port = self.server.server_address
        return f'http://{host}:{port}/v1'

    @staticmethod
    def completion(name):
        text = PUBLIC_TEXT[:15] if name == 'truncated' else PUBLIC_TEXT
        return {'id': 'chatcmpl-mock', 'object': 'chat.completion', 'model': 'mock',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
                             'finish_reason': 'length' if name == 'truncated' else 'stop'}]}

    def hermes_config(self, scenario='deltas'):
        """config.yaml text for a SYNTHETIC Hermes home that uses only this
        provider. No fallback model, no fallback providers, no transport
        fallback: a failure here is a failure, not a quiet switch to a real
        service. The key goes in that home's .env as MOCK_PROVIDER_KEY."""
        return ('model:\n'
                f'  default: {scenario}\n'
                '  provider: custom\n'
                f'  base_url: {self.url}\n'
                '  api_key_env: MOCK_PROVIDER_KEY\n'
                '  transport_fallback: deny\n'
                'fallback_providers: []\n')


def consume(url, token, scenario, timeout=5):
    """Reference reader for this fixture: incremental UTF-8 decoding of the
    byte stream, SSE framing, and only `delta.content` treated as public.
    It exists to prove what the fixture emits; it is not the app's transport.

    Returns {'public': [...], 'hidden': {...}, 'finish': reason|None,
             'done': bool, 'error': None|'disconnected'|'malformed:<line>'}"""
    parts = urlsplit(url)
    con = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    body = json.dumps({'model': scenario, 'stream': True, 'messages': [{'role': 'user', 'content': 'hi'}]})
    con.request('POST', parts.path + '/chat/completions', body,
                {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    response = con.getresponse()
    out = {'status': response.status, 'public': [], 'hidden': {}, 'finish': None, 'done': False, 'error': None,
           'first_delta_after': None}
    if response.status != 200:
        response.read();con.close();return out
    decoder = codecs.getincrementaldecoder('utf-8')()
    buffer = '';started = time.monotonic()
    try:
        while True:
            raw = response.read1(65536) if hasattr(response, 'read1') else response.read(1)
            if not raw:
                break
            buffer += decoder.decode(raw)
            while '\n\n' in buffer:
                event, buffer = buffer.split('\n\n', 1)
                data = '\n'.join(line[5:].lstrip() for line in event.split('\n') if line.startswith('data:'))
                if data == '[DONE]':
                    # The stream is over; what the server does to the socket next
                    # (a reset on Windows, a FIN elsewhere) is not part of it.
                    out['done'] = True
                    return out
                try:
                    chunk = json.loads(data)
                except ValueError:
                    out['error'] = 'malformed:' + data[:40];return out
                for choice in chunk.get('choices', []):
                    delta = choice.get('delta') or {}
                    if isinstance(delta.get('content'), str) and delta['content']:
                        if out['first_delta_after'] is None:
                            out['first_delta_after'] = time.monotonic() - started
                        out['public'].append(delta['content'])
                    for key, value in delta.items():
                        if key not in ('content', 'role'):
                            out['hidden'].setdefault(key, []).append(value)
                    if choice.get('finish_reason'):
                        out['finish'] = choice['finish_reason']
        decoder.decode(b'', final=True)
    except (http.client.IncompleteRead, ConnectionError, socket.timeout, UnicodeDecodeError):
        out['error'] = 'disconnected'
    finally:
        con.close()
    if not out['done'] and out['error'] is None:
        out['error'] = 'disconnected'
    return out
