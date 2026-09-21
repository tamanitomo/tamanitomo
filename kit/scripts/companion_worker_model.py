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

TIERS=('loops','reflection','chat')


def _hermes_default(c):
    try:
        import yaml
        cfg=yaml.safe_load((c.home/'config.yaml').read_text(encoding='utf-8')) or {}
    except Exception:
        return {}
    model=cfg.get('model') if isinstance(cfg.get('model'),dict) else {}
    return {'provider':str(model.get('provider') or ''),
            'model':str(model.get('default') or model.get('model') or ''),
            'base_url':str(model.get('base_url') or '')}


def resolve(c,tier='loops'):
    """The provider, model and endpoint this tier of background work should use."""
    if tier not in TIERS:raise ValueError(f'Unknown model tier {tier!r}; expected {list(TIERS)}')
    chosen=dict((getattr(c,'models',None) or {}).get(tier) or {})
    fallback=_hermes_default(c)
    out={'provider':chosen.get('provider') or fallback.get('provider',''),
         'model':chosen.get('model') or fallback.get('model',''),
         'base_url':chosen.get('base_url') or '',
         'reasoning_effort':chosen.get('reasoning_effort') or ''}
    if not out['model']:
        raise ValueError(f'No model configured for the {tier} tier, and Hermes has no default')
    # Only a tier that names its own URL is called over plain HTTP. Everything
    # else goes through Hermes, which holds the session.
    out['direct']=bool(out['base_url'])
    return out


def _bridge(c,payload):
    from companion_gateway import _env_values
    checkout=c.hermes_root/'hermes-agent'
    python=checkout/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
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
        raise ValueError('Hermes text provider is unavailable; inspect its setup'+
                         (f' ({run.stderr.strip()[:200]})' if run.stderr.strip() else ''))
    if isinstance(reply,dict) and reply.get('error'):raise ValueError(str(reply['error']))
    if run.returncode:raise ValueError('Hermes text provider failed')
    return reply


def complete(c,payload,route,api_key_env='',allow_remote=False,timeout=300,what='This worker'):
    """Run one completion against the resolved route.

    Returns the same three things whichever way it went, so a caller never has
    to know which kind of provider answered: the text, whether the model
    actually reasoned, and the usage.
    """
    if route['direct']:
        import urllib.request
        import companion_endpoint
        companion_endpoint.verify(route['base_url'],allow_remote,what)
        body={**payload,'model':route['model']}
        if route.get('reasoning_effort'):body.setdefault('reasoning_effort',route['reasoning_effort'])
        request=urllib.request.Request(route['base_url'].rstrip('/')+'/chat/completions',
                 data=json.dumps(companion_endpoint.shape(body,route['base_url'])).encode(),
                 headers=companion_endpoint.headers(api_key_env))
        with urllib.request.urlopen(request,timeout=timeout) as response:reply=json.load(response)
        choice=reply['choices'][0]
        return {'content':choice['message']['content'],'finish_reason':choice.get('finish_reason'),
                'reasoned':companion_endpoint.confirm_thinking(reply,route['base_url']),
                'usage':reply.get('usage') or {}}
    return _bridge(c,{'provider':route['provider'],'model':route['model'],
                      'messages':payload['messages'],'max_tokens':payload.get('max_tokens',3600),
                      'temperature':payload.get('temperature',0.6),
                      'response_format':payload.get('response_format'),
                      'reasoning_effort':route.get('reasoning_effort') or payload.get('reasoning_effort'),
                      'timeout':timeout})


if __name__=='__main__':
    import argparse
    import companion_config as cc
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=pathlib.Path)
    parser.add_argument('--tier',default='loops',choices=TIERS)
    args=parser.parse_args()
    print(json.dumps(resolve(cc.load(args.home),args.tier),indent=2))
