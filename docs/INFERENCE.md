# Inference recovery

Workers and chat use an ordered, configured chain: the selected primary, secondary
providers, then configured local models. There is no automatic enrollment in a
cloud service or selection of an uninstalled local model.

## One chain for everything

**Settings → AI models → Models & fallbacks** edits that chain as an ordered list:
the first model answers, and each one after it answers when the one before is busy
or fails. A step is one account and model, or the **OpenRouter free cascade**
(OpenRouter's free router, then specific free models). **Use this chain for
everything** writes the first model as Hermes's `model` and the rest as
`fallback_providers`, clears per-tier overrides so the workers follow it, and pins
every model-backed scheduled job to the first model.

Jobs are pinned rather than left unpinned on purpose. Hermes skips an unpinned job
once the default model differs from the one it was created with, while a pinned job
always runs and still falls back through `fallback_providers`. A job pinned to
something else is listed with a **Use the chain** button. The gateway reads the
chain when it starts, so restart it afterwards for Telegram and other chats.

## Where the chain is stored

The native Hermes `config.yaml` key `fallback_providers` is authoritative when
present, including an empty list. Otherwise the companion's `models.fallbacks`
provides the chain. For example:

```yaml
model:
  provider: openrouter
  default: your-primary-model
fallback_providers:
  - provider: deepseek
    model: deepseek-chat
  - provider: ollama
    model: your-installed-local-model
```

Ollama defaults to `http://127.0.0.1:11434/v1`; LM Studio defaults to
`http://127.0.0.1:1234/v1`. An explicit `base_url` can select a different local
server. Each route keeps its own credentials (`api_key_env` or native `key_env`);
primary credentials are never forwarded to a different fallback endpoint.

Worker requests advance on HTTP 429, 500, 502, 503, 504, connection errors and
timeouts. Request and credential errors remain visible. Existing remote-worker
consent and TLS checks still apply: a loopback-only task cannot fail over to a
cloud provider without authorization. A failed reflection keeps its pending
evidence and retry state.

Chat hands this chain to Hermes's native recovery loop inside the current turn.
Hermes changes API clients while retaining session and tool history. The workspace
never replays an entire chat turn to recover from a provider failure. The bridge
reports a provider switch and continues streaming. Older Hermes versions without
the native recovery seam retain their own quiet-CLI behavior.

The model probe tests one requested route with a small synthetic prompt, never
falls back, and changes no saved configuration or vault content. It is a real
provider request, so normal provider usage applies.
