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


## Companion routing on beta

Settings → Models offers **Configure ChatGPT throughout** after a Codex OAuth
sign-in. This keeps the configured fallback chain, removes stale primary endpoint
credentials, saves the worker tiers and updates installed shipped jobs without
changing their IDs, history or paused state. Models can still be overridden per
job afterward. A partial cron-edit failure is reported and can be retried.
Restart an already-running gateway after applying routing so it loads the adapter.
Image synthesis and live speech retain their own providers: Codex text OAuth does
not supply a ComfyUI image workflow or a speech connection.

| Work | Model | Reasoning |
| --- | --- | --- |
| Chat | GPT-5.6 Sol | none |
| Pulse, wake, check-in | GPT-5.6 Luna | none |
| Autonomy and wind-down | GPT-5.6 Sol | low |
| Daily reflection and independent work window | GPT-5.6 Sol | medium |
| Weekly and monthly reflection | GPT-5.6 Sol | high |
| Hygiene | GPT-5.6 Luna | none |

These are explicit product defaults, not a claim that every account has access
to every model. Account access and actual requests remain Hermes's responsibility;
the model probe can check the selected route without companion context.

Hermes versions that isolate pinned jobs suppress their inherited fallback chain.
The bundled `tamanitomo-routing` Hermes plugin explicitly enrolls shipped companion
jobs in the profile's chain. It operates at credential resolution and within the
same native agent turn. Unrelated jobs and profiles keep Hermes's behavior. An
explicit job fallback list (including an empty one) takes precedence. The adapter
uses the `_job_fallback_chain` seam and must be verified when updating Hermes.
Setup/repair and applying models install it; existing installations do not change
merely because the source repository is updated.

An `openrouter/free` bundle refreshes the public catalogue at use time with a
six-hour on-disk cache, retaining the last good catalogue on outage and backing
off failed catalogue checks for five minutes. Runtime bundle expansion tries
preferred available tool-capable free models, then OpenRouter's free router,
without displacing an explicitly configured final route. Explicit non-bundle
routes retain their order, including local models. Worker transport failures
advance the chain; invalid requests and credentials remain visible.

The preference list is a quality heuristic, not an automatically measured
leaderboard: preferred models first, then unassessed models ordered by context
capacity and name. Larger context is not proof of better output. Only listed free
variants advertising tool support and zero text pricing qualify. The live API
cannot by itself establish a universal quality ranking. See OpenRouter's
[free variants documentation](https://openrouter.ai/docs/guides/routing/model-variants/free).

Native cron usage is shown using both current (`ts`, `prompt_tokens`,
`completion_tokens`) and older audit fields. Per-job totals also show input and
output separately. Missing counters remain unknown; there is no new spending cap.
