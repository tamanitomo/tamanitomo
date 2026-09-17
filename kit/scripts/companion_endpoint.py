"""Where a local companion worker is allowed to send its prompt, and in what shape.

The presence and reflection workers were written against a llama.cpp server on
loopback and assumed both facts: no credential, and llama.cpp's own request
extensions. Pointing one at a hosted API broke on both counts — the endpoint
guard refused it, and the extensions came back as `extra_forbidden`.

Loopback remains the default, because these workers carry a companion's inner
life and sending that off the machine should be a decision rather than a
default. `--allow-remote` is that decision, made per job.
"""
import json
import os
import pathlib
import urllib.parse

# llama.cpp accepts these; a strict OpenAI-shaped API rejects the whole request
# for any one of them. They are optimisations, so dropping them costs nothing
# but the prompt cache that only a local server was keeping anyway.
#
# reasoning_effort is deliberately NOT here. These workers are asked to hold a
# routine, a wardrobe and a continuity rule in mind at once and answer in one
# shot; stripping their thinking is how they started inventing anchors and
# garments. A provider that will not take the value we ask for gets one it will.
LOCAL_ONLY_FIELDS = ('id_slot', 'cache_prompt', 'chat_template_kwargs', 'reasoning_budget_tokens')

# What each hosted API actually accepts, learned by asking it rather than
# assuming. DeepSeek reasons natively and takes only these two efforts;
# mistral-medium-3.5 rejects the request outright for 'low'.
EFFORTS = {
    'api.deepseek.com': ('none', 'high'),
    'api.mistral.ai': ('none', 'high'),
}

# Providers that refuse response_format json_schema. They still honour
# json_object, so the schema moves into the prompt instead of being enforced.
NO_JSON_SCHEMA = ('api.deepseek.com',)

# Reasoning tokens are billed against max_tokens, so a budget sized for a
# non-thinking model gets spent thinking and the answer arrives truncated —
# which surfaces as "response was incomplete", not as anything about thinking.
# A presence record with a routine, a wardrobe and a continuity rule to reason
# over spends thousands before it writes anything, and these models carry a
# context measured in hundreds of thousands, so the headroom is cheap.
THINKING_HEADROOM = 12000

LOOPBACK = ('127.0.0.1', 'localhost', '::1')


def is_loopback(base_url):
    url = urllib.parse.urlsplit(base_url)
    return url.hostname in LOOPBACK


def verify(base_url, allow_remote=False, what='This worker'):
    """Raise unless base_url is somewhere this worker may send a companion's prompt."""
    url = urllib.parse.urlsplit(base_url)
    if is_loopback(base_url):
        if url.scheme != 'http':
            raise ValueError(f'{what} expects http on loopback')
        return True
    if not allow_remote:
        raise ValueError(
            f'{what} requires a loopback model endpoint. '
            'Pass --allow-remote to send this companion\'s prompts to a hosted API.')
    if url.scheme != 'https':
        raise ValueError(f'{what} refuses to send prompts to a remote host without TLS')
    return False


def _from_env_file(name):
    """Read one variable out of the profile's .env.

    Hermes loads .env inside its own process rather than exporting it, so a
    worker it spawns as a subprocess inherits nothing. These workers are
    standalone scripts, so they read the file themselves. The value never
    travels through argv, where `ps` would show it to every user on the box.
    """
    homes = []
    if os.environ.get('HERMES_HOME'):
        homes.append(pathlib.Path(os.environ['HERMES_HOME']))
    homes.append(pathlib.Path.home() / '.hermes')
    for home in homes:
        path = home / '.env'
        try:
            for line in path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                if key.strip() == name:
                    return value.strip().strip('"').strip("'")
        except OSError:
            continue
    return ''


def resolve_key(api_key_env):
    """The bearer token for this endpoint: the environment first, then .env."""
    if not api_key_env:
        return ''
    return os.environ.get(api_key_env, '').strip() or _from_env_file(api_key_env)


def headers(api_key_env=''):
    """Request headers, carrying a bearer token when one can be found."""
    out = {'Content-Type': 'application/json'}
    key = resolve_key(api_key_env)
    if key:
        out['Authorization'] = 'Bearer ' + key
    return out


def _host(base_url):
    return (urllib.parse.urlsplit(base_url).hostname or '').lower()


def thinking_effort(base_url, requested='high'):
    """The strongest thinking this endpoint will actually accept.

    Asking a provider for an effort it does not publish is a 400, not a
    downgrade, so the request never runs at all.
    """
    allowed = EFFORTS.get(_host(base_url))
    if allowed is None:
        return requested
    return requested if requested in allowed else allowed[-1]


def shape(payload, base_url, require_thinking=True):
    """Make one payload acceptable to this endpoint without losing its meaning.

    Three things differ between a llama.cpp server and a hosted API: the
    optimisation fields it tolerates, whether it enforces a JSON schema, and
    what it calls thinking. None of them should change what the worker is
    asking for.
    """
    if is_loopback(base_url):
        return payload
    out = {k: v for k, v in payload.items() if k not in LOCAL_ONLY_FIELDS}

    if require_thinking:
        out['reasoning_effort'] = thinking_effort(base_url, payload.get('reasoning_effort') or 'high')
        # Thinking is spent from the same budget as the answer. Without room for
        # both, the JSON arrives cut off mid-object and reads as a model that
        # cannot follow instructions.
        out['max_tokens'] = max(int(out.get('max_tokens') or 0), 0) + THINKING_HEADROOM
    elif 'reasoning_effort' in out:
        out.pop('reasoning_effort')

    fmt = out.get('response_format') or {}
    if fmt.get('type') == 'json_schema' and _host(base_url) in NO_JSON_SCHEMA:
        # The schema stops being enforced, so it has to be stated. Dropping it
        # silently is how a worker starts returning a shape nothing validates.
        schema = (fmt.get('json_schema') or {}).get('schema')
        out['response_format'] = {'type': 'json_object'}
        if schema and out.get('messages'):
            messages = [dict(m) for m in out['messages']]
            messages[-1]['content'] = (
                str(messages[-1].get('content', '')) +
                '\n\nReturn one JSON object and nothing else. It must satisfy exactly this JSON Schema, '
                'including every required field and no additional properties:\n' +
                json.dumps(schema, ensure_ascii=False))
            out['messages'] = messages
    return out


def confirm_thinking(reply, base_url):
    """Whether the model actually thought, rather than being asked to.

    A provider can accept reasoning_effort and return nothing reasoned. These
    jobs are the reason the setting exists, so a silent downgrade is worth
    seeing in the cron log rather than discovering through bad output.
    """
    if is_loopback(base_url):
        return True
    try:
        details = (reply.get('usage') or {}).get('completion_tokens_details') or {}
        if int(details.get('reasoning_tokens') or 0) > 0:
            return True
        return bool((reply.get('choices') or [{}])[0].get('message', {}).get('reasoning_content'))
    except Exception:
        return False


def add_arguments(parser):
    """The two flags every worker that talks to a model endpoint now shares."""
    parser.add_argument('--allow-remote', action='store_true',
        help='Permit a non-loopback model endpoint. Requires https.')
    parser.add_argument('--api-key-env', default='',
        help='Environment variable holding the bearer token for the endpoint.')
