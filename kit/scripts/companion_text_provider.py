#!/usr/bin/env python3
"""Isolated bridge, executed with the selected Hermes Python and HERMES_HOME.

The background workers speak plain OpenAI-over-HTTP, which is why they have only
ever been able to reach a model with a URL and a bearer token. The provider a
companion is actually configured with is often one Hermes holds an OAuth session
for, and there is no URL to give: it had to be a second, separately configured
model on some other machine, which is how a companion ended up thinking with a
3B model on a box across the room while her own setting said otherwise.

Hermes can already resolve any of its providers to an OpenAI-shaped client. This
hands one back across a subprocess boundary so a worker can use the model the
companion is set to, whatever kind of provider it is.
"""
import json
import sys


def chat(payload):
    from agent.auxiliary_client import resolve_provider_client
    provider=str(payload.get('provider') or '').strip()
    model=str(payload.get('model') or '').strip()
    if not provider or not model:raise ValueError('A worker model needs both a provider and a model')
    if provider.lower() in ('auto','moa'):
        raise ValueError('Choose a specific provider for background work, not a routing alias')
    client,resolved=resolve_provider_client(provider=provider,model=model)
    if client is None:raise ValueError(f'Provider {provider} is unavailable')
    request={'model':resolved,'messages':payload['messages'],
             'max_tokens':payload.get('max_tokens',3600),
             'temperature':payload.get('temperature',0.6),
             'timeout':payload.get('timeout',300)}
    if payload.get('response_format'):request['response_format']=payload['response_format']
    effort=payload.get('reasoning_effort')
    if effort:request['reasoning_effort']=effort
    try:
        reply=client.chat.completions.create(**request)
    except Exception as exc:
        # A strict provider rejects the whole request for one unsupported field
        # rather than ignoring it, so the retry drops what it is most likely to
        # be objecting to instead of reporting a failure the worker cannot act on.
        if not (effort or request.get('response_format')):raise
        request.pop('reasoning_effort',None)
        fmt=request.pop('response_format',None)
        if fmt and fmt.get('type')=='json_schema':
            request['messages']=[dict(m) for m in request['messages']]
            request['messages'][-1]['content']=(str(request['messages'][-1].get('content',''))+
                '\n\nReturn one JSON object and nothing else, satisfying exactly this JSON Schema, '
                'including every required field and no additional properties:\n'+
                json.dumps((fmt.get('json_schema') or {}).get('schema'),ensure_ascii=False))
            request['response_format']={'type':'json_object'}
        reply=client.chat.completions.create(**request)
    choice=reply.choices[0]
    usage=getattr(reply,'usage',None)
    return {'content':choice.message.content,'finish_reason':choice.finish_reason,
            'reasoned':bool(getattr(choice.message,'reasoning_content',None)),
            'model':resolved,'provider':provider,
            'usage':{'completion_tokens':getattr(usage,'completion_tokens',0),
                     'prompt_tokens':getattr(usage,'prompt_tokens',0)} if usage else {}}


if __name__=='__main__':
    try:
        print('COMPANION_TEXT='+json.dumps(chat(json.load(sys.stdin))))
    except Exception as exc:
        print('COMPANION_TEXT='+json.dumps({'error':f'{type(exc).__name__}: {exc}'}));sys.exit(1)
