"""Where a local companion worker is allowed to send its prompt, and in what shape.

The presence and reflection workers were written against a llama.cpp server on
loopback and assumed both facts: no credential, and llama.cpp's own request
extensions. Pointing one at a hosted API broke on both counts — the endpoint
guard refused it, and the extensions came back as `extra_forbidden`.

Loopback remains the default, because these workers carry a companion's inner
life and sending that off the machine should be a decision rather than a
default. `--allow-remote` is that decision, made per job.
"""
import os
import pathlib
import urllib.parse

# llama.cpp accepts these; a strict OpenAI-shaped API rejects the whole request
# for any one of them. The first four are optimisations, so dropping them costs
# nothing but the prompt cache that only a local server was keeping anyway.
#
# reasoning_effort is standard, but the value these workers ask for is tuned to
# llama.cpp and hosted models accept different sets — mistral-medium-3.5 takes
# only 'high' or 'none', and rejects the request outright for 'low'. Letting the
# provider pick its own default is the portable choice for a worker that is
# filling in a presence record, not reasoning hard about one.
LOCAL_ONLY_FIELDS = ('id_slot', 'cache_prompt', 'chat_template_kwargs',
                     'reasoning_budget_tokens', 'reasoning_effort')

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


def shape(payload, base_url):
    """Drop the llama.cpp-only fields when the endpoint is not llama.cpp."""
    if is_loopback(base_url):
        return payload
    return {k: v for k, v in payload.items() if k not in LOCAL_ONLY_FIELDS}


def add_arguments(parser):
    """The two flags every worker that talks to a model endpoint now shares."""
    parser.add_argument('--allow-remote', action='store_true',
        help='Permit a non-loopback model endpoint. Requires https.')
    parser.add_argument('--api-key-env', default='',
        help='Environment variable holding the bearer token for the endpoint.')
