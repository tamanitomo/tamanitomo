"""Hermes context-engine extension: replay dialogue plus the latest Kit snapshot.

Only request copies change. Original api_content sidecars and all life ledgers
remain available for historical retrieval. Other plugins' context is retained.
"""

from __future__ import annotations
import copy
import re

BEGIN = "<!-- tamanitomo:continuity:begin -->"
END = "<!-- tamanitomo:continuity:end -->"
LEGACY_BEGIN = "<!-- companion-kit:continuity:begin -->"
LEGACY_END = "<!-- companion-kit:continuity:end -->"


def without_snapshot(sidecar, raw, agent):
    if (
        not isinstance(sidecar, str)
        or not isinstance(raw, str)
        or not sidecar.startswith(raw + "\n\n")
    ):
        return None
    prefix = sidecar[: len(raw)]
    extra = sidecar[len(raw) :]
    for b_marker, e_marker in ((BEGIN, END), (LEGACY_BEGIN, LEGACY_END)):
        if extra.count(b_marker) == 1 and extra.count(e_marker) == 1:
            head, rest = extra.split(b_marker, 1)
            body, tail = rest.split(e_marker, 1)
            if f"[{agent} — continuity" not in body:
                return None
            result = prefix + head.rstrip()
            if tail.strip():
                result += "\n\n" + tail.lstrip()
            return result
    # Earlier Kit hooks were unfenced. Recognize the complete, exact envelope;
    # ambiguous or mixed suffixes are left alone. Never match inside raw user text.
    marker = "\n\n[Current time: "
    index = extra.find(marker)
    if index < 0:
        return None
    candidate = extra[index:]
    known_end = (
        "Never treat absence of records as proof of never.",
        "Absence of records is not proof of never.",
    )
    if f"[{agent} — continuity" not in candidate or not candidate.endswith(known_end):
        return None
    return prefix + extra[:index]


def strip_text(text, agent):
    """`text` without its plain-fenced Kit snapshot, or None when there is none to take.

    Read from the message itself, not from its sidecar. A resumed session (any gateway
    restart) replays the bytes that were sent as the message, with no sidecar left to
    compare against, and the sidecar match then found nothing: every old snapshot rode
    along, 278K tokens in one request on 2026-11-26. The base and update fences of a
    conversation are a different marker and are never taken.
    """
    for b_marker, e_marker in ((BEGIN, END), (LEGACY_BEGIN, LEGACY_END)):
        if text.count(b_marker) == 1 and text.count(e_marker) == 1:
            head, rest = text.split(b_marker, 1)
            body, tail = rest.split(e_marker, 1)
            if f"[{agent} — continuity" not in body:
                return None
            result = head.rstrip()
            if tail.strip():
                result += "\n\n" + tail.lstrip()
            # A message that was nothing but its snapshot stays whole: an empty user
            # message is an error on most providers.
            return result if result.strip() else None
    return None


def _strip_content(content, agent):
    """Content without its snapshot (text, or the text parts of a multimodal message),
    or None when nothing changed."""
    if isinstance(content, str):
        return strip_text(content, agent)
    if not isinstance(content, list):
        return None
    changed, parts = False, []
    for part in content:
        if (
            isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ):
            cleaned = strip_text(part["text"], agent)
            if cleaned is not None:
                part, changed = {**part, "text": cleaned}, True
        parts.append(part)
    return parts if changed else None


def select_messages(request_messages, conversation_messages, agent):
    # Earlier hooks wrote unfenced snapshots; those are only recognisable against the
    # sidecar, so that match stays for histories old enough to have them.
    replacements = {}
    for row in conversation_messages or []:
        if row.get("role") != "user":
            continue
        sidecar = row.get("api_content")
        raw = row.get("content")
        cleaned = without_snapshot(sidecar, raw, agent)
        if cleaned is not None:
            replacements[sidecar] = cleaned
    candidates = []
    for index, row in enumerate(request_messages):
        if row.get("role") != "user":
            continue
        content = row.get("content")
        cleaned = replacements.get(content) if isinstance(content, str) else None
        if cleaned is None:
            cleaned = _strip_content(content, agent)
        if cleaned is not None:
            candidates.append((index, cleaned))
    if len(candidates) < 2:
        return None
    out = list(request_messages)
    for index, cleaned in candidates[:-1]:
        out[index] = {**request_messages[index], "content": cleaned}
    return out


def make_engine(config, agent_name, name="companion-local"):
    """Reuse Hermes's compressor; only add the documented select_context seam.

    `name` is what `context.engine` selects. "companion-local" is the name the
    first hand-installed copy used; the kit's plugin registers its own."""
    engine_name = name
    from agent.context_compressor import ContextCompressor

    class CompanionLocalContext(ContextCompressor):
        @property
        def name(self):
            return engine_name

        def __init__(self, cfg):
            self._initial_config = copy.deepcopy(cfg)
            comp = cfg.get("compression", {})
            model = cfg.get("model", {})
            super().__init__(
                model=model.get("default", ""),
                threshold_percent=comp.get("threshold", 0.75),
                summary_target_ratio=comp.get("target_ratio", 0.4),
                protect_first_n=comp.get("protect_first_n", 3),
                protect_last_n=comp.get("protect_last_n", 20),
                quiet_mode=True,
                config_context_length=model.get("context_length"),
                base_url=model.get("base_url", ""),
                provider=model.get("provider", ""),
                abort_on_summary_failure=comp.get("abort_on_summary_failure", False),
                max_tokens=cfg.get("max_tokens"),
                model_thresholds=comp.get("model_thresholds"),
                threshold_tokens_cap=comp.get("threshold_tokens"),
                proactive_prune_tokens=comp.get("proactive_prune_tokens", 0),
                proactive_prune_min_result_chars=comp.get(
                    "proactive_prune_min_result_chars", 8000
                ),
                proactive_prune_min_reclaim_tokens=comp.get(
                    "proactive_prune_min_reclaim_tokens", 4096
                ),
                min_tail_user_messages=comp.get("min_tail_user_messages", 1),
                tail_mode=comp.get("tail_mode", "lean"),
                custom_providers=cfg.get("custom_providers"),
            )

        def __deepcopy__(self, memo):
            # The general-plugin registry holds an unused factory instance. Each
            # agent needs fresh compressor locks/state, never another agent's counters.
            return type(self)(self._initial_config)

        def select_context(
            self, request_messages, *, conversation_messages=None, **kwargs
        ):
            return select_messages(request_messages, conversation_messages, agent_name)

    return CompanionLocalContext(config)
