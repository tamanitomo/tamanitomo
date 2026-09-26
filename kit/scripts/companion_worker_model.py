#!/usr/bin/env python3
"""Which model a background worker should use: the one the companion is set to.

Every worker took a `--base-url` and a `--model` on its command line, so the
model a companion actually thinks with was whatever each cron job had been
handed when it was written. There was no relationship between that and her
configured model at all -- the wind-down job pointed at a 3B model on another
machine while her settings said something else entirely, and because a plain
HTTP worker cannot hold an OAuth session, that was the only kind of endpoint it
could reach.

A tier is resolved here instead: her own `models.<tier>` first, then Hermes'
default. A provider with a URL is called directly, as before. A provider Hermes
owns the session for is reached through `companion_text_provider`.
"""
from __future__ import annotations
import json
import os
import pathlib
import subprocess

import companion_platform as cp

TIERS=('loops','reflection','chat')


def resolve(c,tier='loops'):
    """The provider, model and endpoint this tier of background work should use."""
    import companion_inference as inference
    if tier not in TIERS:
        raise ValueError(f'Unknown model tier {tier!r}; expected {list(TIERS)}')
    route = inference.configured_routes(c, tier=tier)[0]
    if not route['model']:
        raise ValueError(f'No model configured for the {tier} tier, and Hermes has no default')
    return route


def _bridge(c,payload):
    from companion_gateway import _env_values
    from companion_inference import ProviderFailure
    checkout=c.hermes_root/'hermes-agent'
    python=cp.venv_executable(checkout)
    if not python.is_file():raise ValueError('Hermes Python is unavailable')
    env=dict(os.environ,**_env_values(c.home));env.update(HERMES_HOME=str(c.home),PYTHONPATH=str(checkout))
    env.pop('HERMES_PROFILE',None)
    script=pathlib.Path(__file__).with_name('companion_text_provider.py')
    run=subprocess.run([str(python),str(script)],input=json.dumps(payload),env=env,cwd=checkout,
                       capture_output=True,text=True,timeout=payload.get('timeout',300)+60)
    try:
        reply=json.loads(next(line.split('=',1)[1] for line in run.stdout.splitlines()
                              if line.startswith('COMPANION_TEXT=')))
    except (StopIteration,ValueError):
        raise ProviderFailure('Hermes text provider is unavailable; inspect its setup'+
                         (f' ({run.stderr.strip()[:200]})' if run.stderr.strip() else ''))
    if isinstance(reply,dict) and reply.get('error'):
        raise ProviderFailure(reply['error'], reply.get('status_code'), reply.get('transient'))
    if run.returncode:raise ValueError('Hermes text provider failed')
    return reply


def complete(c,payload,route,api_key_env='',allow_remote=False,timeout=300,what='This worker', *, allow_fallback=True, require_thinking=True):
    """Complete with configured failover while keeping each route's consent and key."""
    import urllib.request
    import companion_endpoint
    import companion_inference as inference

    routes = inference.configured_routes(c, primary=route) if allow_fallback else [inference.normalize(route)]
    primary = routes[0]
    # Choosing a named Hermes model already authorizes its configured account.
    # An explicitly local job still requires --allow-remote before leaving host.
    local_only = not allow_remote and inference.is_local(primary)
    permitted = [primary]
    for fallback in routes[1:]:
        if local_only and not inference.is_local(fallback):
            continue
        if fallback['direct']:
            try:
                companion_endpoint.verify(fallback['base_url'], allow_remote, what)
            except ValueError:
                continue
        permitted.append(fallback)

    def attempt(selected):
        if selected['direct']:
            companion_endpoint.verify(selected['base_url'], allow_remote, what)
        key = inference.credential(c, selected, api_key_env if selected is primary else '')
        if selected['direct'] and selected.get('api_mode') in (None, '', 'chat_completions'):
            body = {**payload, 'model': selected['model']}
            if selected.get('reasoning_effort'):
                body['reasoning_effort'] = selected['reasoning_effort']
            headers = {'Content-Type': 'application/json'}
            if key:
                headers['Authorization'] = 'Bearer ' + key
            request = urllib.request.Request(selected['base_url'].rstrip('/')+'/chat/completions',
                      data=json.dumps(companion_endpoint.shape(body,selected['base_url'],require_thinking=require_thinking)).encode(), headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                reply = json.load(response)
            if not reply.get('choices'):
                raise ValueError('The model returned no choices')
            choice = reply['choices'][0]
            details = (reply.get('usage') or {}).get('completion_tokens_details')
            reasoned = companion_endpoint.confirm_thinking(reply, selected['base_url'])
            if not reasoned and not details and not companion_endpoint.is_loopback(selected['base_url']):
                reasoned = None
            return {'content': choice['message']['content'], 'finish_reason': choice.get('finish_reason'),
                    'reasoned': reasoned, 'usage': reply.get('usage') or {},
                    'provider': selected['provider'], 'model': selected['model']}
        return _bridge(c, {'provider': selected['provider'] or ('custom' if selected['base_url'] else ''),
                          'model': selected['model'], 'base_url': selected['base_url'],
                          'api_key': key, 'api_mode': selected.get('api_mode') or '',
                          'messages': payload['messages'], 'max_tokens': payload.get('max_tokens', 3600),
                          'temperature': payload.get('temperature', .6),
                          'response_format': payload.get('response_format'),
                          'reasoning_effort': selected.get('reasoning_effort') or payload.get('reasoning_effort'),
                          'timeout': timeout})

    return inference.cascade(permitted, attempt)


if __name__=='__main__':
    import argparse
    import companion_config as cc
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=pathlib.Path)
    parser.add_argument('--tier',default='loops',choices=TIERS)
    args=parser.parse_args()
    route=resolve(cc.load(args.home),args.tier)
    print(json.dumps({key:value for key,value in route.items() if key!='api_key'},indent=2))
