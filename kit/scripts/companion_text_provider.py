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


def _reasoning_state(reply):
    """Did it think? True, False, or None for "this endpoint does not say".

    The three are genuinely different and were collapsed into two. A provider
    that reports nothing is not a provider that reasoned about nothing, and
    treating it as such produced a warning on every single run that no setting
    could ever silence -- which is worse than no warning, because it teaches you
    to ignore the one that means something.
    """
    choices = getattr(reply, "choices", None) or []
    if choices and getattr(
        getattr(choices[0], "message", None), "reasoning_content", None
    ):
        return True
    details = getattr(getattr(reply, "usage", None), "completion_tokens_details", None)
    if details is None:
        return None
    try:
        return int(getattr(details, "reasoning_tokens", 0) or 0) > 0
    except (TypeError, ValueError):
        return None


def _missing(text, schema):
    """What is wrong with this answer, in words a model can act on. '' if nothing."""
    try:
        data = json.loads(str(text or ""))
    except ValueError:
        return "it was not JSON at all."
    if not isinstance(data, dict):
        return "the top level was not an object."
    required = [k for k in (schema.get("required") or []) if k not in data]
    if required:
        return "these required fields were absent: " + ", ".join(sorted(required)) + "."
    props = schema.get("properties") or {}
    wrong = []
    for key, spec in props.items():
        if key not in data or not isinstance(spec, dict):
            continue
        want = spec.get("type")
        if want == "array" and not isinstance(data[key], list):
            wrong.append(f"{key} must be an array")
        elif want == "string" and not isinstance(data[key], str):
            wrong.append(f"{key} must be a string")
        elif want == "object" and not isinstance(data[key], dict):
            wrong.append(f"{key} must be an object")
    if wrong:
        return "; ".join(sorted(wrong)) + "."
    return ""


def chat(payload):
    from agent.auxiliary_client import resolve_provider_client

    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    if not provider or not model:
        raise ValueError("A worker model needs both a provider and a model")
    if provider.lower() in ("auto", "moa"):
        raise ValueError(
            "Choose a specific provider for background work, not a routing alias"
        )
    options = {
        argument: payload[field]
        for field, argument in (
            ("base_url", "explicit_base_url"),
            ("api_key", "explicit_api_key"),
            ("api_mode", "api_mode"),
        )
        if payload.get(field)
    }
    client, resolved = resolve_provider_client(
        provider=provider, model=model, **options
    )
    if client is None:
        raise ValueError(f"Provider {provider} is unavailable")
    # A reasoning model spends max_tokens on its thinking before it writes a
    # single character of the answer. At the flat default, a job that thought
    # hard about a difficult day had a few hundred tokens left for the JSON and
    # returned it cut in half -- which reads downstream as a malformed schema,
    # not as the budget problem it is. An explicit max_tokens from the caller is
    # still honoured exactly; only the default moves.
    effort = payload.get("reasoning_effort")
    default_tokens = 3600
    if str(effort or "").lower() in ("medium", "high"):
        default_tokens = 6000 if str(effort).lower() == "medium" else 8000
    request = {
        "model": resolved,
        "messages": payload["messages"],
        "max_tokens": payload.get("max_tokens", default_tokens),
        "temperature": payload.get("temperature", 0.6),
        "timeout": payload.get("timeout", 300),
    }
    if payload.get("response_format"):
        request["response_format"] = payload["response_format"]
    if effort:
        request["reasoning_effort"] = effort
    wanted = request.get("response_format") or {}
    schema = (
        (wanted.get("json_schema") or {}).get("schema")
        if wanted.get("type") == "json_schema"
        else None
    )

    def restate(req, keep_effort=True):
        """Put the schema in the prompt, for a provider that will not enforce one.

        Keeps the thinking. This began life as the retry for a provider that had
        rejected the request outright, where dropping the unusual fields is the
        point -- and then became the normal path for every schema, quietly
        stripping reasoning from the workers that need it most. These jobs hold a
        routine, a wardrobe and a continuity rule in mind and answer in one shot;
        taking their thinking away is how they start inventing anchors and
        garments, which is precisely what the warning was complaining about.
        """
        out = dict(req)
        if not keep_effort:
            out.pop("reasoning_effort", None)
        out["messages"] = [dict(m) for m in req["messages"]]
        out["messages"][-1]["content"] = str(
            out["messages"][-1].get("content", "")
        ) + "\n\nReturn one JSON object and nothing else, satisfying exactly this JSON Schema, " "including every required field and no additional properties:\n" + json.dumps(
            schema, ensure_ascii=False
        )
        out["response_format"] = {"type": "json_object"}
        return out

    # Do not ask a provider to enforce a schema it will quietly decline to
    # enforce. This one accepts `json_schema`, returns 200, and answers in prose
    # or in a shape of its own choosing -- no error, so a worker expecting a
    # record got a sentence and failed somewhere far away on a field that was
    # never there. Checking whether the reply was JSON was not enough either: a
    # well-formed object with the wrong keys passes that and fails everywhere
    # after it. The schema goes in the prompt, where the model can actually read
    # it, and the shape is checked here rather than assumed.
    if schema:
        request = restate(request)
    try:
        reply = client.chat.completions.create(**request)
    except Exception as exc:
        from companion_inference import is_transient, status_code

        if is_transient(exc) or status_code(exc) in (401, 403):
            raise
        if not (effort or wanted):
            raise
        # Only here, where the provider actually objected, is it right to drop
        # the fields it may have objected to.
        reply = client.chat.completions.create(
            **(
                restate(request, keep_effort=False)
                if schema
                else {
                    k: v
                    for k, v in request.items()
                    if k not in ("reasoning_effort", "response_format")
                }
            )
        )
    # A provider can answer 200 with no choices at all -- a content filter, a
    # cut-off stream -- and every read of choices[0] below was an IndexError
    # raised far from the cause.
    if not (getattr(reply, "choices", None) or []):
        raise ValueError(f"{provider} returned no choices for {resolved}")
    if schema:
        missing = _missing(getattr(reply.choices[0].message, "content", ""), schema)
        if missing:
            # One correction, naming what was wrong. A worker's own retry loop
            # handles anything past that; two rounds of the same complaint is a
            # model that is not going to get there.
            follow = dict(request)
            follow["messages"] = list(request["messages"]) + [
                {
                    "role": "assistant",
                    "content": str(
                        getattr(reply.choices[0].message, "content", "") or ""
                    ),
                },
                {
                    "role": "user",
                    "content": "That did not match the schema: "
                    + missing
                    + " Return the whole object again, corrected.",
                },
            ]
            # A transient failure has no usable corrected answer. Let the outer
            # provider cascade try the next configured model before the worker
            # spends its reflection or presence retry budget.
            try:
                corrected = client.chat.completions.create(**follow)
                if getattr(corrected, "choices", None) or []:
                    reply = corrected
            except Exception as exc:
                from companion_inference import is_transient

                if is_transient(exc):
                    raise
    choice = reply.choices[0]
    usage = getattr(reply, "usage", None)
    return {
        "content": choice.message.content,
        "finish_reason": choice.finish_reason,
        "reasoned": _reasoning_state(reply),
        "model": resolved,
        "provider": provider,
        "usage": (
            {
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            }
            if usage
            else {}
        ),
    }


if __name__ == "__main__":
    try:
        print("COMPANION_TEXT=" + json.dumps(chat(json.load(sys.stdin))))
    except Exception as exc:
        from companion_inference import is_transient, redact, status_code

        print(
            "COMPANION_TEXT="
            + json.dumps(
                {
                    "error": redact(f"{type(exc).__name__}: {exc}"),
                    "status_code": status_code(exc),
                    "transient": is_transient(exc),
                }
            )
        )
        sys.exit(1)
