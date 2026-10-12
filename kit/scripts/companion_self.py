#!/usr/bin/env python3
"""Evidence-backed human facts, companion preferences and curiosity records.

The provenance boundary is explicit:
  <people>/<human>/facts.jsonl: claims about the human, with required evidence;
  <life>/preferences.jsonl: the companion's own preferences and feelings;
  <life>/questions.jsonl: questions and the answers actually recorded.

A remembered claim needs an inspectable source, not merely similarity to an
embedding or a model's confident reconstruction. Structured reflection selects
trusted human transcript quotes by ID and stores the verbatim quote and source
alongside its separately marked paraphrase. That path screens obvious wording
mismatches and holds doubtful paraphrases for review; it does not prove every
paraphrase true. Direct fact callers must supply substantive stated, observed
or inferred evidence. This low-level writer cannot independently authenticate
arbitrary evidence text and does not claim to do so.

Facts are append-only. Deduplication and explicit corrections run under the
ledger lock, preserving prior claims and their evidence instead of silently
rewriting history. Context budgets limit what is presented, not what happened.
"""

from __future__ import annotations
import uuid
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import unicodedata
from zoneinfo import ZoneInfo
from companion_platform import file_lock, atomic_write

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc

BEGIN = "<!-- COMPANION-SELF-AUTHORED:BEGIN -->"
END = "<!-- COMPANION-SELF-AUTHORED:END -->"
CATEGORIES = (
    "likes",
    "dislikes",
    "people",
    "places",
    "work",
    "school",
    "health",
    "history",
    "logistics",
    "other",
)
# How much a fact matters to keep in view. A "core" fact is one whose absence breaks the
# illusion of knowing someone (a wheelchair, an allergy, a partner's name, a loss): it is
# rendered first and is never the one that gets squeezed out. Health facts are core unless
# said otherwise; anything can be raised or lowered with `weigh`.
# Names a model reaches for that already mean one of the categories above. Anything
# else lands in "other" rather than costing the fact: a check-in that wrote
# "household" or "infrastructure" used to lose the whole entry to a validation error
# it never retried, which is exactly the detail the check-in exists to keep.
CATEGORY_ALIASES = {
    "like": "likes",
    "preference": "likes",
    "preferences": "likes",
    "favorite": "likes",
    "favorites": "likes",
    "favourites": "likes",
    "dislike": "dislikes",
    "person": "people",
    "family": "people",
    "friends": "people",
    "relationships": "people",
    "place": "places",
    "location": "places",
    "home": "places",
    "job": "work",
    "career": "work",
    "employment": "work",
    "education": "school",
    "study": "school",
    "studies": "school",
    "medical": "health",
    "wellbeing": "health",
    "fitness": "health",
    "background": "history",
    "past": "history",
    "biography": "history",
    "schedule": "logistics",
    "plans": "logistics",
    "routine": "logistics",
}
WEIGHTS = ("core", "normal")
CORE_CATEGORIES = ("health",)
# Stored evidence bullets kept per fact (newest); the injected profile shows fewer.
MAX_EXTRA_EVIDENCE = 5
INJECTED_EXTRA_EVIDENCE = 2
VALENCE = ("like", "dislike", "curious", "mixed")
CONFIDENCE = ("stated", "observed", "inferred")
MIN_USEFUL = 90


def _tz(c):
    try:
        return ZoneInfo(c.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _now(tz, now=None):
    now = now or dt.datetime.now(tz)
    if now.tzinfo is None:
        raise ValueError("timezone required")
    return now.astimezone(tz)


def _read(path, kind=None):
    rows = []
    try:
        with pathlib.Path(path).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if kind and row.get("kind") != kind:
                    continue
                rows.append(row)
    except FileNotFoundError:
        pass
    return rows


# Describe how a row was written, not what it claims; a retry written by a
# newer release may describe the same row differently.
_ROW_METADATA = frozenset(
    {
        "recorded_at",
        "expires_at",
        "provenance",
        "statement_origin",
        "statement_check",
        "held_decision",
    }
)


def _append(path, row, dedupe_id=True, guard=None):
    """Append one row. `guard` runs under the same lock after the ID check; a
    dict it returns is the answer instead of a write."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock((path.parent / ("." + path.name + ".lock"))):
        if dedupe_id:
            for e in _read(path):
                if e.get("id") == row["id"]:
                    ignored = _ROW_METADATA
                    if {k: v for k, v in e.items() if k not in ignored} != {
                        k: v for k, v in row.items() if k not in ignored
                    }:
                        raise ValueError(
                            "Entry ID already exists with different content; original retained"
                        )
                    return {"written": False, "entry": e}
        if guard and (refused := guard()):
            return refused
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    return {"written": True, "entry": row}


def _mkid(prefix, *parts):
    return prefix + "-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _text(value, limit, label):
    value = (value or "").strip()
    if not value or len(value) > limit:
        raise ValueError(f"{label} required, max {limit} chars")
    return value


# ---- ledgers -------------------------------------------------------------
_QUOTES = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2033": '"',
    }
)

# Ordinary prose whitespace. Named, not \s, so Python and us.js agree exactly.
_PROSE_SPACE = re.compile("[ \t\n\r\f\v\u00a0]+")


def canonical_statement(text):
    """The form two fact statements must share to be refused as the same one.

    A refused write is a lost memory while a duplicate is only clutter, so this
    erases the least it can -- the policy, in full:

      * Unicode composition (NFC): a composed and a decomposed "e" with an
        accent are one letter. Compatibility forms are NOT folded: NFKC turns
        "x\u00b2" into "x2", which is different text.
      * Leading/trailing ordinary whitespace, and runs of it inside
        (space, tab, newline, carriage return, form feed, vertical tab,
        no-break space) collapsed to one space.

    Everything else is kept: case anywhere (including the first letter),
    every punctuation mark (a final "!" or ".", quotation marks and their
    style, spacing before a comma), signs, % and currency and unit symbols,
    "C++"/"C#"/"C", operators, apostrophes, word order and negation. There is
    no list of exceptions to grow; duplicate_facts() is the looser,
    report-only comparison.
    """
    return _PROSE_SPACE.sub(" ", unicodedata.normalize("NFC", str(text or ""))).strip(
        " "
    )


# The statement of a fact written from a reflection is the model's wording; only
# its evidence is the human's. A screen for obvious mismatches is not a proof.
STATEMENT_ORIGINS = ("recorded", "model_paraphrase")
PARAPHRASE_CHECK = (
    "screened for changed numbers, negation, certainty, names and times; "
    "the statement is not otherwise verified against its quote"
)


def record_fact(
    root,
    statement,
    evidence,
    now,
    category="other",
    confidence="stated",
    source="",
    supersedes="",
    human="the human",
    statement_origin="recorded",
    held_decision=None,
    weight="",
    confirm_distinct=False,
    user_memory=None,
    lasting=False,
    agent="",
):
    """Append one fact.

    With `user_memory` (the Companion), a statement that Hermes's USER.md or its
    overflow archive already says is not stored: that file is where Hermes keeps
    what it knows about the human, and a second copy here would only drift.

    A statement that is an active fact said again (similarity of at least
    SAME_FACT, see similar_facts) is not written as a fact: its evidence is added
    to the existing one, the way a repeat is meant to be kept, and the answer
    names it as `merged_into`. A statement that is only close to one is not
    written: the answer is {"written": False, "similar_to": [...]} naming what
    already exists. Nothing is lost by either -- re-record with `supersedes` set to
    refine or correct the existing fact, or with `confirm_distinct=True` when it
    really is a separate fact.

    A statement that is one day's news ("is setting up a projector today") is
    written with `expires_at` (see short_lived_until) and leaves the active view
    after it; the row stays in the ledger. `lasting=True` keeps it in view.

    A statement equal (by canonical_statement) to an active fact is refused
    with `duplicate_of`, unless it is an explicit correction: a valid
    `supersedes` always goes through, even when that leaves two equal
    statements, because refusing it would leave the fact it corrects active.
    The target is checked under the ledger lock, so two corrections of one
    fact cannot both land."""
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}")
    if confidence not in CONFIDENCE:
        raise ValueError(f"confidence must be one of {CONFIDENCE}")
    if statement_origin not in STATEMENT_ORIGINS:
        raise ValueError(f"statement_origin must be one of {STATEMENT_ORIGINS}")
    if weight and weight not in WEIGHTS:
        raise ValueError(f"weight must be one of {WEIGHTS}")
    statement = _text(statement, 400, "statement")
    evidence = _text(evidence, 600, "evidence")
    if misfiled := _not_about_the_human(statement, agent, human):
        return misfiled
    if user_memory is not None and not supersedes:
        known = known_in_user_memory(user_memory, statement)
        if known:
            return {"written": False, "reason": "already in Hermes USER.md", **known}
    urls_only = re.sub(r"https?://\S+", "", evidence).strip()
    if not urls_only or urls_only in (";", ",", "-", ".", "|"):
        raise ValueError(
            f"evidence cannot be only web URLs; facts about {human} require actual interaction or observation"
        )
    supersedes = (supersedes or "").strip()[:80]
    # The exact statement, not its lower case: "from the US" and "from the us"
    # are two statements, and a lower-cased ID made the second one an error.
    row = {
        "id": _mkid(
            "fact", category, statement, evidence, confidence, source, supersedes
        ),
        "kind": "human_fact",
        "category": category,
        "statement": statement,
        "evidence": evidence,
        "source": (source or "").strip()[:200],
        "confidence": confidence,
        "status": "active",
        "supersedes": supersedes,
        "recorded_at": now.isoformat(),
        "provenance": (
            f"Statement written by the companion from quoted evidence about {human}; the evidence is exact"
            if statement_origin == "model_paraphrase"
            else f"Recorded from stated or observed evidence about {human}; not imagined"
        ),
    }
    if weight:
        row["weight"] = weight
    if statement_origin == "model_paraphrase":
        row["statement_origin"] = statement_origin
        row["statement_check"] = PARAPHRASE_CHECK
    if held_decision:
        row["held_decision"] = dict(held_decision)
    expires = None if lasting else short_lived_until(statement, now)
    if expires:
        row["expires_at"] = expires.isoformat()
    names = () if human == "the human" else (human,)
    key = canonical_statement(statement)
    equal = []

    def guard():
        active = facts(root, now=now)
        if supersedes:
            if not any(f["id"] == supersedes for f in active):
                raise ValueError("supersedes must refer to an active fact")
            # An explicit correction is never cancelled by a duplicate match.
            equal.extend(
                f["id"]
                for f in active
                if f["id"] != supersedes
                and canonical_statement(f.get("statement")) == key
            )
            return None
        for f in active:
            if canonical_statement(f.get("statement")) == key:
                return {
                    "written": False,
                    "reason": "fact already recorded",
                    "duplicate_of": f["id"],
                }
        if not confirm_distinct:
            near = similar_facts(active, statement, names=names)
            if near and near[0]["similarity"] >= SAME_FACT:
                return {"written": False, "same_as": near[0]["id"], "similar_to": near}
            if near:
                return _similar_refusal(near)
        return None

    out = _append(pathlib.Path(root) / "facts.jsonl", row, guard=guard)
    if out.get("same_as"):
        # Evidence is added outside the ledger lock it takes itself; the fact can be
        # retracted in between, and then this is the ordinary refusal instead.
        target = out["same_as"]
        try:
            added = add_evidence(root, target, evidence, now)
        except ValueError:
            return _similar_refusal(out["similar_to"])
        return {
            "written": False,
            "reason": "the same fact is already recorded; this evidence was added to it",
            "merged_into": target,
            "evidence_added": added["written"],
            "similar_to": out["similar_to"],
            "next": (
                "Nothing else to do. If the new wording says something the recorded fact "
                f"does not, record it again with supersedes={target}."
            ),
        }
    notes = []
    if out["written"] and equal:
        out["equal_to"] = equal
        notes.append(
            "Correction recorded; another active fact already says the same thing. Nothing was merged."
        )
    if out["written"] and out["entry"].get("expires_at"):
        out["expires_at"] = out["entry"]["expires_at"]
        notes.append(
            f"Kept as short-lived: it reads as one day's news, so it leaves the profile "
            f"after {out['expires_at'][:10]} (the ledger keeps it). If it needs a follow-up, "
            "add an open loop; if it is lasting, record it without the day words or with "
            "lasting=true."
        )
    if notes:
        out["note"] = " ".join(notes)
    return out


# A file or a source line in a statement is a note about software, not the person.
_TECHNICAL = re.compile(
    r"\b[\w./-]+\.(?:py|js|ts|json|jsonl|ya?ml|toml|md|sh|service)(?::\d+)?\b"
)


def _not_about_the_human(statement, agent, human):
    """A refusal for a statement that is not a fact about the human, or None. Both
    kinds were in real ledgers: the companion's own day ("Nova finished reading a
    novel") and a debugging note citing companion_presence.py:101."""
    if agent and re.match(rf"\s*{re.escape(agent)}(?:'s)?\b", statement, re.I):
        return {
            "written": False,
            "reason": f"this is about {agent}, not {human}",
            "next": "Keep your own day in your journal or preferences; facts are about the person.",
        }
    if _TECHNICAL.search(statement):
        return {
            "written": False,
            "reason": "this reads as a technical note, not a fact about the person",
            "next": "Keep notes about software in the vault; record only what it says about them, in their terms.",
        }
    return None


def _similar_refusal(near):
    return {
        "written": False,
        "reason": "a similar fact is already recorded",
        "similar_to": near,
        "next": (
            "If this refines or corrects one of them, record it again with "
            "supersedes=<that id>. If it is a genuinely separate fact, record it "
            "again with confirm_distinct=true. If it adds nothing, leave it."
        ),
    }


# One day's news, and how many days after the one it was said on it stays in view.
_SHORT_LIVED = (
    (
        re.compile(
            r"\b(?:today|tonight|this (?:morning|afternoon|evening)|right now|"
            r"at the moment|just now|(?:earlier|later) today|yesterday|last night)\b"
        ),
        1,
    ),
    (re.compile(r"\btomorrow\b"), 2),
    (re.compile(r"\bthis (?:week|weekend)\b"), 7),
)


def short_lived_until(statement, now):
    """When a statement that is one day's news should leave the profile, or None.

    "Robin is setting up a projector today" is true for a day; kept as a fact, it was
    still read out to the companion a month later. Only the statement is read, never
    the evidence, which is usually dated. The end of the following local day (a
    week for "this week"), so the news is still there for a follow-up."""
    text = _loose(statement)
    days = max((d for pattern, d in _SHORT_LIVED if pattern.search(text)), default=0)
    if not days:
        return None
    return (now + dt.timedelta(days=days)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )


def _expired(row, now):
    stamp = row.get("expires_at")
    if not stamp:
        return False
    try:
        at = dt.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt.timezone.utc)
    return at <= now


_NUMBER_WORDS = {
    w: str(i)
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve".split()
    )
}
_ORDINAL_WORDS = {
    w: str(i)
    for i, w in enumerate(
        "first second third fourth fifth sixth seventh eighth ninth tenth".split(), 1
    )
}
_NEGATION = re.compile(
    r"\b(?:not|never|no|none|nobody|nothing|neither|nor|without|cannot|no longer|"
    r"\w+n't|dislike[sd]?|hate[sd]?|quit|quits|stopped)\b"
)
_LEADING_ANSWER = re.compile(r"^\W*(?:no|nope|nah|yes|yeah|yep)\b\W+")
_HEDGE = re.compile(
    r"\b(?:maybe|might|probably|perhaps|possibly|may|considering|thinking (?:about|of)|"
    r"not sure|unsure|hope|hopes|hoping|plan|plans|planning|want|wants|wanting|would like|if)\b"
)
_TIME = re.compile(
    r"\b(?:today|tonight|tomorrow|yesterday|weekend|weekends|week|weekly|month|monthly|year|yearly|"
    r"daily|morning|mornings|evening|evenings|night|nights|ago|last|next|recently|soon|always|"
    r"usually|every|currently|now|still|anymore)\b"
)
_THIRD_PARTY = re.compile(
    r"^\W*(?:(?:my|our) (sister|brother|mom|mum|mother|dad|father|wife|husband|partner|friend|"
    r"son|daughter|boss|roommate|girlfriend|boyfriend|kid|kids|cousin|aunt|uncle|grandma|grandpa|"
    r"coworker|neighbor|neighbour|teacher|doctor)|(he|she|they))\b(?! and (?:i|me)\b)",
    re.I,
)


def _numbers(text):
    text = text.casefold()
    found = {
        re.sub(r"(?<=\d),(?=\d{3}\b)", "", n)
        for n in re.findall(
            r"[-+]?\d[\d,]*(?:\.\d+)?%?(?!\d|[.,]\d)(?!(?:st|nd|rd|th)\b)", text
        )
    }
    found |= {"#" + n for n in re.findall(r"\b(\d+)(?:st|nd|rd|th)\b", text)}
    for word in re.findall(r"[a-z]+", text):
        if word in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[word])
        if word in _ORDINAL_WORDS:
            found.add("#" + _ORDINAL_WORDS[word])
    return found


def paraphrase_concerns(statement, quote, names=()):
    """Obvious ways a written statement can say more than, or other than, its
    quote: a number, polarity, certainty, name or time the quote lacks, or a
    quote about somebody else stated as the human's own. An empty answer means
    none of these were seen -- not that the statement is supported. See
    tests/test_local_reflection.py ParaphraseScreenTests for what it misses."""
    s = unicodedata.normalize("NFC", str(statement or "")).translate(_QUOTES)
    q = unicodedata.normalize("NFC", str(quote or "")).translate(_QUOTES)
    sl, ql = s.casefold(), q.casefold()
    out = []
    if extra := sorted(_numbers(s) - _numbers(q)):
        out.append("a number or position not in the quote: " + ", ".join(extra))
    if bool(_NEGATION.search(sl)) != bool(
        _NEGATION.search(_LEADING_ANSWER.sub("", ql))
    ):
        out.append("negation differs from the quote")
    if _HEDGE.search(ql) and not _HEDGE.search(sl):
        out.append("states as certain what the quote hedges")
    known = {n.casefold() for n in names if n}
    quote_words = set(re.findall(r"[\w-]+", ql))
    proper = {w for w in re.findall(r"(?<=\s)[A-Z][\w-]*", s) if w != "I"}
    new = sorted(
        w for w in proper if re.sub(r"'s$", "", w.casefold()) not in quote_words | known
    )
    if new:
        out.append("a name not in the quote: " + ", ".join(new))
    moments = lambda t: {w.removesuffix("s") for w in _TIME.findall(t)}
    if times := sorted(moments(sl) - moments(ql)):
        out.append("a time not in the quote: " + ", ".join(times))
    if (m := _THIRD_PARTY.match(q)) and not re.search(
        r"\b(?:"
        + re.escape((m.group(1) or m.group(2)).casefold())
        + r"|he|she|they|his|her|their)\b",
        sl,
    ):
        out.append("the quote is about someone else")
    return out


def hold_fact(
    root, statement, evidence, now, category, source, reasons, human="the human"
):
    """Keep a statement that failed the paraphrase screen for a person to look
    at, outside the active ledger. Nothing reads it as a memory."""
    statement = _text(statement, 400, "statement")
    evidence = _text(evidence, 600, "evidence")
    row = {
        "id": _mkid("held", category, statement, evidence, source),
        "kind": "held_fact",
        "category": category,
        "statement": statement,
        "evidence": evidence,
        "source": (source or "").strip()[:200],
        "reasons": list(reasons),
        "status": "held",
        "recorded_at": now.isoformat(),
        "provenance": f"Written by the companion about {human}; held because it may not match its quote",
    }
    return {
        **_append(pathlib.Path(root) / "facts-held.jsonl", row),
        "held": True,
        "reasons": list(reasons),
    }


def held_facts(root):
    """Held statements that have not been decided. One whose decision was
    started but not finished carries `pending_decision`; deciding it again
    (the same way) finishes it. Read-only: nothing is recovered here."""
    rows = _read(pathlib.Path(root) / "facts-held.jsonl")
    done = {r["held_id"] for r in rows if r.get("kind") == "held_fact_decision"}
    intents = {r["held_id"]: r for r in rows if r.get("kind") == "held_fact_intent"}
    return [
        (
            {**r, "pending_decision": intents[r["id"]]["decision"]}
            if r["id"] in intents
            else r
        )
        for r in rows
        if r.get("kind") == "held_fact" and r["id"] not in done
    ]


HELD_DECISIONS = ("accept", "dismiss")
HELD_OVERRIDE_NOTE = (
    "Accepted by a person after the paraphrase screen held it; this is an owner override, "
    "not a machine verification of the statement"
)


class HeldDecisionConflict(ValueError):
    """A different decision was already taken, or started, for this held fact."""


def _decision_lock(root):
    return pathlib.Path(root) / ".facts-held.decide.lock"


def decide_held(root, held_id, decision, now, human="the human", origin="owner"):
    """Settle one held fact: `accept` records it as an ordinary fact (marked as
    an owner override), `dismiss` records only the decision. The held row, its
    reasons and exact evidence are never changed.

    Recoverable protocol, serialized per human store:
      lock order: .facts-held.decide.lock -> facts.jsonl lock -> facts-held.jsonl lock
      1. intent   {held_id, decision, op_id} appended; it fixes which decision wins
      2. effect   accept: record_fact with a deterministic ID (a retry finds the
                  row it wrote; an equal active fact is reported as duplicate_of)
      3. decision {held_id, decision, op_id, fact_id|duplicate_of} appended
    A crash between steps leaves an intent; deciding the same way again resumes
    it with the same op_id. A different decision after an intent or decision is
    refused (HeldDecisionConflict) before any effect. Repeating a finished
    decision returns it unchanged, even if the fact was later retracted -- it is
    not re-recorded, and nothing else is retracted to compensate."""
    if decision not in HELD_DECISIONS:
        raise ValueError("decision must be accept or dismiss")
    path = pathlib.Path(root) / "facts-held.jsonl"
    with file_lock(_decision_lock(root)):
        rows = _read(path)
        row = next(
            (
                r
                for r in rows
                if r.get("kind") == "held_fact" and r.get("id") == held_id
            ),
            None,
        )
        if not row:
            raise ValueError("unknown held fact")
        op_id = _mkid("decide-op", held_id, decision)
        done = next(
            (
                r
                for r in rows
                if r.get("kind") == "held_fact_decision" and r.get("held_id") == held_id
            ),
            None,
        )
        if done:
            if done["decision"] != decision:
                raise HeldDecisionConflict(
                    f'held fact was already decided: {done["decision"]}'
                )
            return {
                "decision": decision,
                "op_id": done.get("op_id", op_id),
                "already_decided": True,
                **{k: done[k] for k in ("fact_id", "duplicate_of") if done.get(k)},
            }
        intent = next(
            (
                r
                for r in rows
                if r.get("kind") == "held_fact_intent" and r.get("held_id") == held_id
            ),
            None,
        )
        if intent and intent["decision"] != decision:
            raise HeldDecisionConflict(
                f'a {intent["decision"]} decision is already in progress for this held fact'
            )
        resumed = bool(intent)
        if not intent:
            _append(
                path,
                {
                    "id": op_id,
                    "kind": "held_fact_intent",
                    "held_id": held_id,
                    "decision": decision,
                    "op_id": op_id,
                    "origin": origin,
                    "recorded_at": now.isoformat(),
                },
            )
        out = {}
        if decision == "accept":
            out = record_fact(
                root,
                row["statement"],
                row["evidence"],
                now,
                row["category"],
                "stated",
                row["source"],
                human=human,
                statement_origin="model_paraphrase",
                confirm_distinct=True,
                held_decision={
                    "held_id": held_id,
                    "op_id": op_id,
                    "origin": origin,
                    "note": HELD_OVERRIDE_NOTE,
                },
            )
        result = (
            {"fact_id": out["entry"]["id"]}
            if out.get("entry")
            else (
                {"duplicate_of": out["duplicate_of"]} if out.get("duplicate_of") else {}
            )
        )
        _append(
            path,
            {
                "id": _mkid("decide", held_id),
                "kind": "held_fact_decision",
                "held_id": held_id,
                "decision": decision,
                "op_id": op_id,
                "origin": origin,
                **result,
                "recorded_at": now.isoformat(),
            },
        )
        return {
            "decision": decision,
            "op_id": op_id,
            "resumed": resumed,
            **result,
            **({"written": out["written"]} if decision == "accept" else {}),
        }


def record_pref(root, text, now, valence="like", subject="", agent="the companion"):
    if valence not in VALENCE:
        raise ValueError(f"valence must be one of {VALENCE}")
    text = _text(text, 600, "text")
    subject = (subject or text)[:120].strip()
    # Pref IDs are keyed on (valence, subject, day) -- so two different feelings filed under the
    # same subject on the same day silently collapse into one row: the first stands, the second is
    # dropped with written:false and no error. Make the collision visible rather than silent.
    row = {
        "id": _mkid("pref", valence, subject.lower(), now.date().isoformat()),
        "kind": "companion_preference",
        "valence": valence,
        "subject": subject,
        "text": text,
        "recorded_at": now.isoformat(),
        "provenance": f"{agent}'s own authored preference or feeling",
    }
    return _append(pathlib.Path(root) / "preferences.jsonl", row)


def ask(root, text, now):
    text = _text(text, 400, "question")
    has_qmark = "?" in text
    has_qword = any(
        text.lower().startswith(w)
        for w in (
            "who",
            "what",
            "when",
            "where",
            "why",
            "how",
            "is",
            "are",
            "can",
            "could",
            "would",
            "do",
            "does",
            "did",
            "will",
            "should",
            "have",
            "has",
            "if",
            "whether",
        )
    )
    if not (has_qmark or has_qword):
        raise ValueError(
            "curiosity questions must be an inquiry (end in ? or begin with a question word)"
        )
    row = {
        "id": _mkid("q", text.lower()),
        "kind": "curiosity_question",
        "text": text,
        "status": "open",
        "asked_at": "",
        "answered_at": "",
        "answer": "",
        "recorded_at": now.isoformat(),
    }
    return _append(pathlib.Path(root) / "questions.jsonl", row)


def resolve(root, qid, status, now, answer=""):
    if status not in ("asked", "answered", "dropped"):
        raise ValueError("invalid status")
    if status == "answered":
        answer = _text(answer, 800, "answer")
    path = pathlib.Path(root) / "questions.jsonl"
    if not any(r.get("id") == qid for r in _read(path, kind="curiosity_question")):
        raise ValueError("unknown question id")
    return _append(
        path,
        {
            "id": qid,
            "kind": "curiosity_question_update",
            "status": status,
            "answer": (answer or "").strip(),
            "updated_at": now.isoformat(),
        },
        dedupe_id=False,
    )


def questions(root, status=None):
    """Fold updates onto originals so the latest status wins."""
    latest = {}
    for r in _read(pathlib.Path(root) / "questions.jsonl"):
        qid = r.get("id")
        if r.get("kind") == "curiosity_question":
            latest.setdefault(qid, dict(r))
        elif r.get("kind") == "curiosity_question_update" and qid in latest:
            q = latest[qid]
            q["status"] = r.get("status", q["status"])
            if r.get("answer"):
                q["answer"] = r["answer"]
            if r.get("status") == "asked":
                q["asked_at"] = r.get("updated_at", "")
            if r.get("status") == "answered":
                q["answered_at"] = r.get("updated_at", "")
    out = list(latest.values())
    return [q for q in out if q["status"] == status] if status else out


def facts(root, category=None, now=None):
    """Active facts only; corrections and retractions retain the original history.
    A short-lived fact is active until its `expires_at`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    history = _read(pathlib.Path(root) / "facts.jsonl")
    rows = [r for r in history if r.get("kind") == "human_fact"]
    dead = {r["supersedes"] for r in rows if r.get("supersedes")}
    dead.update(
        r["fact_id"] for r in history if r.get("kind") == "human_fact_retraction"
    )
    seen = {}
    for r in rows:
        if (
            r["id"] in dead
            or r.get("status", "active") != "active"
            or _app_tombstone(r)
            or _expired(r, now)
        ):
            continue
        seen[r["id"]] = r
    # Repeats of a fact are extra evidence for it, not extra facts. Newest kept.
    # Evidence given for a fact that was later refined belongs to its successor.
    successor = {r["supersedes"]: r["id"] for r in rows if r.get("supersedes")}
    more = {}
    for r in history:
        if r.get("kind") != "human_fact_evidence":
            continue
        fid = r.get("fact_id")
        for _ in range(20):
            if fid in seen or fid not in successor:
                break
            fid = successor[fid]
        if fid in seen:
            more.setdefault(fid, []).append(r)
    rows = []
    for fid, row in seen.items():
        extra = sorted(more.get(fid, []), key=lambda e: e.get("recorded_at", ""))
        if extra:
            row = {
                **row,
                "more_evidence": [e["evidence"] for e in extra][-MAX_EXTRA_EVIDENCE:],
            }
        rows.append(row)
    return [r for r in rows if r["category"] == category] if category else rows


def _app_tombstone(r):
    """Earlier releases' "Mark incorrect" superseded a fact with an active
    placeholder, "(retired by <name>)", which then read as a memory. Those rows
    stay in the ledger; they are recognised by the fields the app wrote."""
    return (
        r.get("source") == "app"
        and r.get("evidence") == "retired in the app"
        and bool(r.get("supersedes"))
        and r.get("id") == r["supersedes"] + "-retired"
    )


def fact_statements(root, limit_chars=6000):
    """Active fact statements, newest first, within a character budget, so a
    reflection can tell whether something is actually new. Evidence is left out
    on purpose; the statement is what would be restated."""
    rows = sorted(facts(root), key=lambda f: f.get("recorded_at", ""), reverse=True)
    kept, used = [], 0
    for f in rows:
        item = {
            "id": f["id"],
            "category": f.get("category", "other"),
            "statement": f.get("statement", ""),
        }
        if f.get("statement_origin"):
            item["origin"] = f["statement_origin"]
        size = len(item["statement"]) + len(item["category"]) + 40
        if used + size > limit_chars:
            break
        kept.append(item)
        used += size
    omitted = len(rows) - len(kept)
    return {
        "facts": kept,
        "omitted": omitted,
        "note": (
            f"{omitted} older facts are not listed here for space; this list is not everything already known."
            if omitted
            else "This is every fact currently recorded."
        ),
    }


_FILLER = frozenset(
    "a an the to in into for of on at by from with and his her their its my your".split()
)
_DISTINCT = re.compile(
    r"^(\d.*|no|not|never|none|nor|doesn't|don't|didn't|isn't|wasn't|won't|can't|cannot|"
    r"first|second|third|fourth|fifth|last|next|previous|other|another|former|latter|"
    r"one|two|three|four|five|six|seven|eight|nine|ten)$"
)


def _loose(statement):
    """Generous on purpose, and only ever used to suggest a pair for review."""
    text = (
        unicodedata.normalize("NFKC", str(statement or ""))
        .translate(_QUOTES)
        .casefold()
    )
    return " ".join(re.sub(r"(?<!\w)[^\w\s]+|[^\w\s]+(?!\w)", " ", text).split())


def _words(statement):
    return {
        w for w in re.sub(r"'s\b", "", _loose(statement)).split() if w not in _FILLER
    }


_USER_STORES = ("memories/USER.md", "memory-archive/USER-archive.md")
_ARCHIVE_COMMENT = re.compile(r"<!--.*?-->", re.S)


def user_memory_entries(c):
    """(file, entry) for every entry in Hermes's USER.md and its overflow archive."""
    out = []
    for rel in _USER_STORES:
        base = c.home if rel.startswith("memories") else c.soul_dir
        path = pathlib.Path(base) / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        text = _ARCHIVE_COMMENT.sub("", text).replace("\r\n", "\n")
        out += [(path.name, e.strip()) for e in text.split("\n\xa7\n") if e.strip()]
    return out


def _windows(entry):
    """Each sentence of an entry and each adjacent pair. Matching a whole paragraph
    would let a long entry cover almost any short statement by chance."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", entry) if x.strip()]
    yield from sentences
    for one, two in zip(sentences, sentences[1:]):
        yield one + " " + two


def known_in_user_memory(c, statement, cover=0.8):
    """The USER.md entry that already says `statement`, or None.

    Matches within a sentence or two of an entry, since entries are paragraphs.
    As conservative as similar_facts: a negation, number, ordinal, name or symbol
    in the statement that the passage lacks means it is not the same fact, and a
    statement too short to be specific never matches."""
    if re.match(r"\s*[\w' -]{1,40} said:\s*[\"\u201c]", str(statement)):
        return (
            None  # a quoted remark is evidence, not a claim USER.md could already hold
        )
    ws = _words(statement)
    if len(ws) < 4:
        return None
    names = _capitalised(statement)
    symbols = _SYMBOLS.findall(statement)
    for name, entry in user_memory_entries(c):
        for passage in _windows(entry):
            we = _words(passage)
            if len(ws & we) / len(ws) < cover:
                continue
            if any(_DISTINCT.match(w) and w not in we for w in ws):
                continue
            if (ws & names) - we or any(sym not in passage for sym in symbols):
                continue
            return {"known_in": name, "entry": entry[:300]}
    return None


# Words that say nothing about what a statement is about. Only for comparing
# statements; _FILLER is unchanged for the USER.md check.
_FUNCTION_WORDS = frozenset(
    """is are was were be been being am has have had having do does did will would shall
    should can could may might must it it's this that these those there here as if then than
    so such very just also too about over under up out off he she they them him we you i me
    us who whom whose which what when where why how all any some each more most said says
    say told tells currently now still really""".split()
)
# A flipped polarity is a different fact however many words two statements share.
_POLARITY = re.compile(
    r"\b(?:not|never|no|none|nobody|nothing|neither|nor|without|cannot|\w+n't|"
    r"dislike[sd]?|hate[sd]?|stopped)\b"
)
# Weighted share of what two statements say (see _similarity). From SAME_FACT a new
# statement is the old one said again and becomes evidence for it. From SIMILAR_FACT,
# or when the smaller statement is CONTAINED_FACT inside the other, the writer is
# asked whether it refines the old fact or is a separate one. Calibrated on two
# companions' real ledgers (2026-10-10): every pair past these lines was one fact
# worded twice or a fact and its refinement; the misses had been plain word overlap
# below 0.65, "considering" against "consider", or "IT-support" read as a name.
SAME_FACT = 0.75
SIMILAR_FACT = 0.35
CONTAINED_FACT = 0.6


def _stem(word):
    """Crude on purpose: "leaving"/"leave", "considering"/"consider", "tanks"/"tank"."""
    if not word.isalpha():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for suffix in ("es", "s"):
        if (
            word.endswith(suffix)
            and not word.endswith("ss")
            and len(word) - len(suffix) >= 3
        ):
            word = word[: -len(suffix)]
            break
    for suffix in ("ing", "ed", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    return word[:-1] if word.endswith("e") and len(word) >= 4 else word


def _content(statement, names=frozenset()):
    """What a statement is about, stemmed: not its grammar, and not the people it is
    about, whose names are in nearly every fact."""
    out = set()
    for word in _words(statement):
        for part in word.split("-"):
            if part and part not in _FUNCTION_WORDS and part not in names:
                # "three" must stay a number, not become "thre".
                out.add(part if _DISTINCT.match(part) else _stem(part))
    return out


def _weigher(word_sets):
    """How much sharing a word says: "projector" in one fact, more than "work" in thirty.
    Smoothed, so a ledger of three facts does not count every new word as rare."""
    seen = collections.Counter(w for s in word_sets for w in s)
    n = len(word_sets)
    return lambda w: math.log((n + 10) / (seen[w] + 5))


def _similarity(a, b, weight):
    """(weighted overlap, weighted share of the smaller set) of two word sets."""
    shared = a & b
    if not shared:
        return 0.0, 0.0
    ws, wa, wb = (sum(map(weight, s)) for s in (shared, a, b))
    return ws / (wa + wb - ws), ws / min(wa, wb)


_QUALIFIERS = frozenset("last next previous other another former latter".split())


def _conflict(a_text, b_text, a, b):
    """Why two statements that share most of their words are still two facts, or None:
    "two cats"/"three cats", "his last job"/"his job", "likes"/"dislikes", "C++"/"C",
    "sister Alice"/"sister Beth". A number or name only one of them mentions ("married
    in 2015", "IT-support", "named Leo") is detail, not a different fact."""
    if (a ^ b) & _QUALIFIERS:
        return "a qualifier such as last, next or former differs"
    changed_a = {w for w in a - b if _DISTINCT.match(w)}
    changed_b = {w for w in b - a if _DISTINCT.match(w)}
    if changed_a and changed_b:
        return "a number, ordinal or negation differs"
    if bool(_POLARITY.search(_loose(a_text))) != bool(_POLARITY.search(_loose(b_text))):
        return "one says the opposite of the other"
    if _SYMBOLS.findall(a_text) != _SYMBOLS.findall(b_text):
        return "a symbol differs"
    names_a, names_b = _capitalised(a_text), _capitalised(b_text)
    if names_a - names_b and names_b - names_a:
        return "a name differs"
    return None


_SYMBOLS = re.compile(r"[+#%$&@=<>\u00b0/\u00d7\u2212]|(?<!\w)-(?=\d)")


def _capitalised(*texts):
    """Words written with a capital somewhere other than the start of the text: names."""
    out = set()
    for t in texts:
        for m in re.finditer(r"(?<=[\w,;:'\"] )([A-Z][\w'-]*)", str(t or "")):
            out.add(m.group(1).casefold().removesuffix("'s"))
    return out


def similar_facts(active, statement, threshold=SIMILAR_FACT, limit=3, names=()):
    """Active facts that probably say what `statement` says, best first.

    `similarity` is the weighted overlap of their content words (see _similarity);
    record_fact treats SAME_FACT and above as the same fact said again. A pair whose
    words differ by a number, an ordinal, a negation, a symbol or a swapped name
    ("Sister Alice"/"sister Beth", "likes coffee"/"does not like coffee", "has two
    cats"/"has three cats") is never similar here: those are different facts."""
    names = {str(n).casefold() for n in names if n}
    words = _content(statement, names)
    sets = [_content(f.get("statement"), names) for f in active]
    weight = _weigher(sets)
    out = []
    for f, other in zip(active, sets):
        overlap, contained = _similarity(words, other, weight)
        if overlap < threshold and not (
            contained >= CONTAINED_FACT and len(words & other) >= 2
        ):
            continue
        if _conflict(statement, f.get("statement") or "", words, other):
            continue
        out.append((overlap, contained, f))
    out.sort(key=lambda t: (-t[0], -t[1]))
    return [
        {
            "id": f["id"],
            "statement": f.get("statement"),
            "similarity": round(overlap, 3),
            "containment": round(contained, 3),
        }
        for overlap, contained, f in out[:limit]
    ]


def duplicate_facts(root, threshold=SIMILAR_FACT, names=()):
    """Pairs of active facts that may say the same thing, for a person to review.

    Report only: nothing is retracted, superseded or merged. A pair whose words
    differ by a number, an ordinal, a negation or a name is flagged as such rather
    than hidden, because "likes"/"dislikes" and "first"/"second" are the cases where
    a guess would be worst. `same_fact` marks the pairs record_fact would now merge.
    """
    rows = facts(root)
    names = {str(n).casefold() for n in names if n}
    words = [_content(f.get("statement"), names) for f in rows]
    weight = _weigher(words)
    out = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = words[i], words[j]
            if not a or not b:
                continue
            score, contained_share = _similarity(a, b, weight)
            contained = a <= b or b <= a
            if score < threshold and not (
                contained_share >= CONTAINED_FACT and len(a & b) >= 2
            ):
                continue
            differ = sorted(a ^ b)
            conflict = _conflict(
                rows[i].get("statement") or "", rows[j].get("statement") or "", a, b
            )
            reason = (
                "identical wording"
                if not differ
                else (
                    "one statement contains every word of the other"
                    if contained
                    else f"{round(score*100)}% of content words shared"
                )
            )
            if conflict:
                reason += f"; {conflict} -- probably distinct"
            out.append(
                {
                    "similarity": round(score, 3),
                    "containment": round(contained_share, 3),
                    "same_fact": score >= SAME_FACT and not conflict,
                    "reason": reason,
                    "differing_words": differ,
                    "facts": [
                        {
                            k: rows[x].get(k)
                            for k in (
                                "id",
                                "category",
                                "statement",
                                "evidence",
                                "recorded_at",
                            )
                        }
                        for x in (i, j)
                    ],
                }
            )
    out.sort(key=lambda p: (-p["similarity"], -p["containment"]))
    return {
        "candidates": out,
        "count": len(out),
        "note": "Candidates only. Nothing has been changed; retract or correct a fact yourself if it is really a duplicate.",
    }


def retract_fact(root, fact_id, reason, now):
    """Withdraw a mistaken claim without inventing a replacement claim."""
    reason = _text(reason, 600, "reason")
    path = pathlib.Path(root) / "facts.jsonl"
    if not any(r.get("id") == fact_id for r in _read(path, kind="human_fact")):
        raise ValueError("unknown fact id")
    return _append(
        path,
        {
            "id": _mkid("retract", fact_id),
            "kind": "human_fact_retraction",
            "fact_id": fact_id,
            "reason": reason,
            "recorded_at": now.isoformat(),
        },
    )


def _budget(items, limit, noun, how):
    """Fit what we can, then say plainly what is held back. Never a silent cut."""
    if limit < MIN_USEFUL:
        return (
            f"[{len(items)} {noun} recorded; no room in this context window — read with {how}]"
            if items
            else ""
        )
    kept, used = [], 0
    for line in items:
        if used + len(line) + 1 > limit:
            break
        kept.append(line)
        used += len(line) + 1
    hidden = len(items) - len(kept)
    text = "\n".join(kept)
    if hidden:
        text += f"\n[+{hidden} more {noun} not shown here — all of it is kept; read it with {how}]"
    return text


def add_evidence(root, fact_id, evidence, now):
    """Another time the human showed a fact is true. It is kept as a bullet under the
    fact, so a repeat strengthens what is known instead of duplicating it."""
    evidence = _text(evidence, 600, "evidence")
    if not re.sub(r"https?://\S+", "", evidence).strip(" ;,-.|"):
        raise ValueError("evidence cannot be only web URLs")
    path = pathlib.Path(root) / "facts.jsonl"
    row = {
        "id": _mkid("factev", fact_id, evidence),
        "kind": "human_fact_evidence",
        "fact_id": fact_id,
        "evidence": evidence,
        "recorded_at": now.isoformat(),
    }

    def guard():
        target = next((f for f in facts(root) if f["id"] == fact_id), None)
        if not target:
            raise ValueError("fact_id must refer to an active fact")
        if evidence == target.get("evidence") or evidence in target.get(
            "more_evidence", ()
        ):
            return {"written": False, "reason": "that evidence is already recorded"}
        return None

    return _append(path, row, guard=guard)


def fact_weight(f):
    return f.get("weight") or (
        "core" if f.get("category") in CORE_CATEGORIES else "normal"
    )


def weigh_fact(root, fact_id, weight, now, human="the human"):
    """Change how much a fact matters. Facts are never edited in place, so this is a
    correction of the fact to itself: same words and evidence, new weight."""
    if weight not in WEIGHTS:
        raise ValueError(f"weight must be one of {WEIGHTS}")
    old = next((f for f in facts(root) if f["id"] == fact_id), None)
    if not old:
        raise ValueError("fact_id must refer to an active fact")
    if fact_weight(old) == weight:
        return {"written": False, "reason": f"already {weight}", "fact_id": fact_id}
    return record_fact(
        root,
        old["statement"],
        old["evidence"],
        now,
        old["category"],
        old.get("confidence", "stated"),
        old.get("source", ""),
        fact_id,
        human,
        old.get("statement_origin") or "recorded",
        weight=weight,
    )


def ordered_facts(rows):
    """Core first, then category order, newest first inside each. Stable passes: one
    reverse=True over a tuple would also reverse the category index."""
    order = {k: i for i, k in enumerate(CATEGORIES)}
    rows = sorted(rows, key=lambda f: f.get("recorded_at", ""), reverse=True)
    rows.sort(key=lambda f: order.get(f["category"], 99))
    rows.sort(key=lambda f: fact_weight(f) != "core")
    return rows


def facts_index(root, human="the human"):
    """A readable index of every active fact, grouped by category, core first. It is
    what an agent (or a person) reads when the injected profile could not hold it all.
    """
    rows = ordered_facts(facts(root))
    lines = [
        f"# What is known about {human}",
        "",
        f"{len(rows)} active facts. Regenerated by `companion_self.py facts-index --write`; "
        "change facts with the ledger commands, not this file.",
    ]
    for label, group in (
        ("Core (always kept in view)", [f for f in rows if fact_weight(f) == "core"]),
        ("Everything else", [f for f in rows if fact_weight(f) != "core"]),
    ):
        if not group:
            continue
        lines += ["", f"## {label}"]
        current = None
        for f in group:
            if f["category"] != current:
                current = f["category"]
                lines += ["", f"### {current}"]
            lines.append(f"- {f['statement']}  `{f['id']}`")
            for e in [f.get("evidence")] + list(f.get("more_evidence", ())):
                if e:
                    lines.append(f"    - {e}")
    return "\n".join(lines) + "\n"


def write_facts_index(c):
    path = pathlib.Path(c.human_dir) / "facts-index.md"
    text = facts_index(c.human_dir, c.human)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return {"path": str(path), "facts": len(facts(c.human_dir))}


def summary(c, budgets=None, query=""):
    b = budgets or c.budgets()
    rows = ordered_facts(facts(c.human_dir))
    # Everything, with its evidence, when the budget allows. When it does not, the bare
    # statements, because knowing many facts beats knowing two of them well; the evidence
    # stays in the ledger. Core facts lead either way, so they are the last thing cut.
    core = lambda f: " (core)" if fact_weight(f) == "core" else ""
    also = lambda f: (
        "; also: " + "; ".join(f["more_evidence"][-INJECTED_EXTRA_EVIDENCE:])
        if f.get("more_evidence")
        else ""
    )
    full = [
        f"{f['category']} [{f['confidence']}]{core(f)}: {f['statement']} (evidence: {f['evidence']}{also(f)}; source: {f.get('source') or 'ledger'})"
        for f in rows
    ]
    brief = [f"{f['category']}{core(f)}: {f['statement']}" for f in rows]
    lines = full if sum(len(x) + 1 for x in full) <= b["facts"] else brief
    prof = _budget(
        lines,
        b["facts"],
        "facts",
        "companion_self.py profile | facts-index",
    )
    # One authoritative current-state fold now combines explicit perspective
    # revisions with old preference rows (labelled legacy, never rewritten).
    # The selector is shared with reflection and scheduled planning; this call
    # remains model-free and deterministic.
    import companion_perspectives as perspectives

    selected = perspectives.snapshot(c, query=query, budget=b["preferences"], limit=8)
    pref = (
        perspectives.render_current(c, query=query, budget=b["preferences"], limit=8)
        if b["preferences"] and selected["current"]
        else ""
    )
    openq = [q["text"] for q in questions(c.life, "open")]
    qs = _budget(
        list(reversed(openq)),
        b["questions"],
        "open questions",
        "companion_self.py wonder --status open",
    )
    return {
        "human_profile": prof,
        "preferences": pref,
        "open_questions": qs,
        "counts": {
            "facts": len(rows),
            "preferences": selected.get("total", 0),
            "open_questions": len(openq),
        },
    }


# ---- the block of SOUL.md the agent owns ---------------------------------
def _split_soul(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError(
            "SOUL.md needs exactly one self-authored block; run: companion_self.py soul --init"
        )
    head, rest = text.split(BEGIN, 1)
    body, tail = rest.split(END, 1)
    if not head.endswith("\n"):
        raise ValueError("malformed block start")
    return head, body, tail


def soul_show(c):
    size = len(c.soul.read_text(encoding="utf-8"))
    _, body, _ = _split_soul(c.soul)
    return {
        "self_authored": body.strip("\n"),
        "soul_chars": size,
        "warn_at": c.soul_warn,
        "hard_cap": c.soul_cap,
        "headroom": c.soul_warn - size,
    }


def soul_write(c, text, mode="append", now=None, backups=None):
    """Rewrite ONLY the self-authored block; everything else is verified unchanged."""
    now = now or dt.datetime.now(_tz(c))
    text = (text or "").strip()
    if mode not in ("append", "set"):
        raise ValueError("mode must be append or set")
    if mode == "append" and not text:
        raise ValueError("nothing to append")
    # Resolve first: an atomic os.replace() onto a symlink path replaces the LINK
    # with a regular file, orphaning the canonical copy in the vault.
    path = pathlib.Path(c.soul).resolve()
    backups = pathlib.Path(backups or c.soul_backups)
    backups.mkdir(parents=True, exist_ok=True)
    with file_lock(path.parent / ("." + path.name + ".lock")):
        original = path.read_text(encoding="utf-8")
        head, body, tail = _split_soul(path)
        body = body.strip("\n")
        new = (body + "\n" + text).strip("\n") if mode == "append" else text
        if BEGIN in new or END in new:
            raise ValueError("Self-authored text cannot contain block markers")
        # Some things are not hers to change. Restating them in her own block is
        # the same thing as editing them, so it is refused there too.
        try:
            import companion_identity

            tripped = companion_identity.guard(c, new)
        except (OSError, ValueError, ImportError):
            tripped = []
        if tripped:
            raise ValueError(
                "Refused: this block restates something that is not yours to change ("
                + ", ".join(tripped)
                + "). Those live in locked sections of SOUL.md. "
                "Write about who you are becoming instead."
            )
        out = head + BEGIN + "\n" + new + "\n" + END + tail
        backup = backups / (
            "SOUL.md." + now.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        )
        atomic_write(backup, original)
        if path.read_text(encoding="utf-8") != original:
            raise ValueError("SOUL changed during editing; retry")
        atomic_write(path, out)
    h2, b2, t2 = _split_soul(path)
    if (h2, t2) != (head, tail):
        raise ValueError("refused: content outside the self-authored block changed")
    size = len(path.read_text(encoding="utf-8"))
    warn = ""
    if size > c.soul_warn:
        warn = (
            f"SOUL.md is {size} chars; this model truncates a context file past {c.soul_cap}. "
            "Consolidate the block — sharpen lines rather than dropping them, the detail is safe in the ledgers."
        )
    return {
        "written": True,
        "mode": mode,
        "self_authored": b2.strip("\n"),
        "soul_chars": size,
        "warn_at": c.soul_warn,
        "warning": warn,
    }


def soul_init(c, anchor=None, backups=None):
    """Open a block the agent owns without altering a word of the existing text."""
    path = pathlib.Path(c.soul).resolve()
    with file_lock(path.parent / ("." + path.name + ".lock")):
        text = path.read_text(encoding="utf-8")
        if BEGIN in text or END in text:
            _split_soul(path)
            return {"written": False, "reason": "block already present"}
        block = (
            BEGIN
            + "\n"
            + f"_{c.agent} writes this part {c.refl()}. {c.human} does not edit it._\n"
            + END
            + "\n\n"
        )
        i = text.find(anchor) if anchor else -1
        out = (text[:i] + block + text[i:]) if i >= 0 else text + "\n\n" + block
        backups = pathlib.Path(backups or c.soul_backups)
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / "SOUL.md.pre-init"
        if backup.exists():
            backup = backup.with_name(backup.name + "-" + uuid.uuid4().hex[:8])
        atomic_write(backup, text)
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("SOUL changed during initialization; retry")
        atomic_write(path, out)
    return {"written": True, "soul_chars": len(out), "appended": i < 0}


# ---- tidying an older ledger --------------------------------------------
# Facts written before 3.0.24 were the human's words with a name in front.
_QUOTE_FACT = re.compile(r"\s*[\w' -]{1,40} said:\s*[\"“]")
TIDY_ACTIONS = ("merge", "expire", "retire", "rewrite", "review")


def _stamp(value):
    at = dt.datetime.fromisoformat(value)
    return at if at.tzinfo else at.replace(tzinfo=dt.timezone.utc)


def tidy_plan(root, now, human="the human"):
    """A one-time tidy of a ledger written before these checks, for a person to read
    before tidy_apply. Nothing is changed here.

      merge   -- one fact recorded more than once (equal, or SAME_FACT with nothing in
                 conflict). The earliest statement form stays; each later copy's
                 evidence is added to it and the copy is retracted.
      expire  -- one day's news recorded as lasting, past the time it would now stay
                 in view. Retracted; the ledger keeps it.
      rewrite -- a quote-style fact (`Name said: "..."`). Rewriting needs judgment, so
                 the item applies only once someone fills in `new_statement` (and
                 `lasting`), or changes it to `retire` when nothing in it lasts.
      review  -- two facts close enough that one may refine the other. Report only.

    Every change tidy_apply makes is appended -- evidence, a superseding fact or a
    retraction -- so the history stays readable."""
    names = set() if human == "the human" else {str(human).casefold()}
    rows = sorted(facts(root, now=now), key=lambda f: f.get("recorded_at", ""))
    sets = [_content(f.get("statement"), names) for f in rows]
    weight = _weigher(sets)
    quoted = [bool(_QUOTE_FACT.match(f.get("statement") or "")) for f in rows]
    group = list(range(len(rows)))

    def find(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    close = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = sets[i], sets[j]
            si, sj = rows[i]["statement"], rows[j]["statement"]
            same = canonical_statement(si) == canonical_statement(sj)
            if not same and a and b and not _conflict(si, sj, a, b):
                overlap, contained = _similarity(a, b, weight)
                if overlap >= SAME_FACT:
                    same = True
                elif overlap >= SIMILAR_FACT or (
                    contained >= CONTAINED_FACT and len(a & b) >= 2
                ):
                    close.append((i, j, overlap, contained))
            if same:
                group[find(j)] = find(i)
    members = collections.defaultdict(list)
    for i in range(len(rows)):
        members[find(i)].append(i)
    items, merged = [], set()
    for group_rows in members.values():
        if len(group_rows) < 2:
            continue
        keep = next((i for i in group_rows if not quoted[i]), group_rows[0])
        for i in group_rows:
            if i == keep:
                continue
            merged.add(i)
            items.append(
                {
                    "action": "merge",
                    "id": rows[i]["id"],
                    "statement": rows[i]["statement"],
                    "into": rows[keep]["id"],
                    "into_statement": rows[keep]["statement"],
                    "evidence": [
                        rows[i]["evidence"],
                        *rows[i].get("more_evidence", ()),
                    ],
                }
            )
    for i, f in enumerate(rows):
        if i in merged:
            continue
        said = _stamp(f["recorded_at"]) if f.get("recorded_at") else now
        day = short_lived_until(f["statement"], said)
        if quoted[i]:
            items.append(
                {
                    "action": "rewrite",
                    "id": f["id"],
                    "statement": f["statement"],
                    "category": f["category"],
                    "recorded_at": f.get("recorded_at"),
                    "mentions_a_day": bool(day),
                    "new_statement": "",
                    "lasting": False,
                }
            )
        elif day and not f.get("expires_at") and day <= now:
            items.append(
                {
                    "action": "expire",
                    "id": f["id"],
                    "statement": f["statement"],
                    "recorded_at": f.get("recorded_at"),
                }
            )
    for i, j, overlap, contained in close:
        # A quote-style fact is already listed for rewriting; pairing it is noise.
        if i in merged or j in merged or quoted[i] or quoted[j]:
            continue
        items.append(
            {
                "action": "review",
                "ids": [rows[i]["id"], rows[j]["id"]],
                "statements": [rows[i]["statement"], rows[j]["statement"]],
                "similarity": round(overlap, 3),
                "containment": round(contained, 3),
            }
        )
    return {
        "created_at": now.isoformat(),
        "active_facts": len(rows),
        "counts": dict(collections.Counter(item["action"] for item in items)),
        "items": items,
        "note": (
            "Nothing has been changed. merge and expire apply as listed; rewrite applies "
            "once new_statement is filled in (or the action is changed to retire); review "
            "is for reading. Apply with `tidy --apply <this file>`."
        ),
    }


def tidy_apply(root, plan, now, human="the human", agent=""):
    """Apply a tidy_plan a person has read. An item whose facts changed since the plan
    was made is skipped and reported, never forced. A rewrite whose statement the
    paraphrase screen doubts is skipped unless the item says `"reviewed": true`; the
    human's and the companion's own names are not doubts."""
    items = plan.get("items") if isinstance(plan, dict) else None
    if not isinstance(items, list):
        raise ValueError('a tidy plan holds {"items": [...]}')
    done, skipped = [], []
    for item in items:
        if not isinstance(item, dict) or item.get("action") not in TIDY_ACTIONS:
            raise ValueError(f"each tidy item needs an action from {TIDY_ACTIONS}")
        action, fid = item["action"], item.get("id")
        if action == "review":
            continue
        active = {f["id"]: f for f in facts(root, now=now)}
        f = active.get(fid)
        if not f or f.get("statement") != item.get("statement"):
            skipped.append(
                {"id": fid, "action": action, "why": "no longer active, or changed"}
            )
            continue
        if action == "merge":
            into = active.get(item.get("into"))
            if not into:
                skipped.append(
                    {"id": fid, "action": action, "why": "the fact to keep is gone"}
                )
                continue
            for evidence in item.get("evidence") or ():
                if evidence:
                    add_evidence(root, into["id"], evidence, now)
            retract_fact(
                root, fid, f"the same fact as {into['id']}; its evidence is there", now
            )
        elif action == "expire":
            retract_fact(
                root,
                fid,
                "one day's news kept as a lasting fact; out of view, kept in the ledger",
                now,
            )
        elif action == "retire":
            retract_fact(
                root,
                fid,
                item.get("reason") or "nothing lasting in it; retired in a tidy",
                now,
            )
        else:
            statement = (item.get("new_statement") or "").strip()
            if not statement:
                skipped.append(
                    {"id": fid, "action": action, "why": "no new_statement yet"}
                )
                continue
            quote = re.sub(r"^\S+:\s", "", f.get("evidence") or "", count=1)
            doubts = paraphrase_concerns(statement, quote, (human, agent))
            if doubts and item.get("reviewed") is not True:
                skipped.append({"id": fid, "action": action, "why": "; ".join(doubts)})
                continue
            out = record_fact(
                root,
                statement,
                f["evidence"],
                now,
                item.get("category") or f["category"],
                f.get("confidence", "stated"),
                f.get("source", ""),
                fid,
                human,
                statement_origin="model_paraphrase",
                weight=f.get("weight", ""),
                lasting=bool(item.get("lasting")),
                agent=agent,
            )
            if not out.get("written"):
                skipped.append(
                    {"id": fid, "action": action, "why": out.get("reason", "")}
                )
                continue
        done.append({"id": fid, "action": action})
    return {"applied": len(done), "done": done, "skipped": skipped}


# ---- batch input ---------------------------------------------------------
LEDGER_KINDS = (
    "fact",
    "fact_evidence",
    "retract_fact",
    "pref",
    "ask",
    "resolve",
    "soul",
)


def _entries(data):
    """Accept a bare list or {"entries": [...]}, and nothing else."""
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list):
        raise ValueError(
            'batch file must hold a list of entries, or {"entries": [...]}'
        )
    # An empty batch is the honest answer to "nothing durable happened", which the
    # check-in is told is normal; refusing it left the check-in reporting a failure.
    if len(data) > 200:
        raise ValueError("batch file holds more than 200 entries; split it")
    return data


def fact_category(value):
    """(category, note): a known category, an obvious synonym of one, or "other".

    The note says what happened so the model learns the names without the fact
    being lost to the lesson."""
    name = str(value or "other").strip().lower().replace(" ", "_")
    if name in CATEGORIES:
        return name, ""
    known = CATEGORY_ALIASES.get(name) or CATEGORY_ALIASES.get(name.rstrip("s"))
    landed = known or "other"
    return landed, (
        f"category {value!r} is not one of {', '.join(CATEGORIES)}; recorded under {landed!r}"
    )


def _apply(c, entry, now):
    """One batch entry through the same code paths the flags use."""
    if not isinstance(entry, dict):
        raise ValueError("each entry must be a JSON object")
    kind = (entry.get("kind") or "").strip()
    if kind not in LEDGER_KINDS:
        raise ValueError(f"kind must be one of {LEDGER_KINDS}")
    if kind == "retract_fact":
        return retract_fact(c.human_dir, entry.get("id", ""), entry.get("reason"), now)
    if kind == "fact_evidence":
        return add_evidence(
            c.human_dir, entry.get("id", ""), entry.get("evidence"), now
        )
    if kind == "fact":
        category, note = fact_category(entry.get("category", "other"))
        out = record_fact(
            c.human_dir,
            entry.get("statement"),
            entry.get("evidence"),
            now,
            category,
            entry.get("confidence", "stated"),
            entry.get("source", ""),
            entry.get("supersedes", ""),
            c.human,
            weight=entry.get("weight", ""),
            confirm_distinct=bool(entry.get("confirm_distinct")),
            user_memory=c,
            lasting=bool(entry.get("lasting")),
            agent=c.agent,
        )
        if note:
            out = {**out, "note": " ".join(x for x in (out.get("note"), note) if x)}
        return out
    if kind == "pref":
        return record_pref(
            c.life,
            entry.get("text"),
            now,
            entry.get("valence", "like"),
            entry.get("subject", ""),
            c.agent,
        )
    if kind == "ask":
        return ask(c.life, entry.get("text"), now)
    if kind == "resolve":
        return resolve(
            c.life,
            entry.get("id", ""),
            entry.get("status", ""),
            now,
            entry.get("answer", ""),
        )
    mode = entry.get("mode", "append")
    return soul_write(c, entry.get("text"), mode, now)


# What a batch result repeats from each entry's own answer. Without the reason and
# the facts it matched, "written": false was all a job saw of a refused fact, and it
# had no way to supersede, confirm or drop it as told.
_BATCH_ANSWER = (
    "reason",
    "duplicate_of",
    "similar_to",
    "merged_into",
    "evidence_added",
    "expires_at",
    "equal_to",
    "next",
    "note",
)


def ledger_batch(c, path, now):
    """Record a whole reflection from one JSON file.

    Prose written by the model never goes through a shell argument this way, so
    apostrophes and newlines survive. Entries are applied in order and every
    ledger here is append-only with de-duplicating ids, so re-running the same
    file after a partial failure records nothing twice.
    """
    entries = _entries(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
    results = []
    for i, entry in enumerate(entries):
        try:
            out = _apply(c, entry, now)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            results.append(
                {
                    "index": i,
                    "kind": (entry.get("kind") if isinstance(entry, dict) else None),
                    "ok": False,
                    "error": str(exc),
                }
            )
            return {
                "applied": sum(1 for r in results if r.get("ok")),
                "failed_at": i,
                "results": results,
                "note": "Stopped at the first bad entry. Fix it and re-run the same file; "
                "entries already recorded are not recorded twice.",
            }
        results.append(
            {
                "index": i,
                "kind": entry["kind"],
                "ok": True,
                "id": (out.get("entry") or {}).get("id") if "entry" in out else None,
                "written": out.get("written", True),
                **{k: out[k] for k in _BATCH_ANSWER if out.get(k)},
            }
        )
    if not entries:
        return {
            "applied": 0,
            "failed_at": None,
            "results": [],
            "note": "Nothing to record.",
        }
    return {"applied": len(results), "failed_at": None, "results": results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=pathlib.Path)
    s = p.add_subparsers(dest="cmd", required=True)
    f = s.add_parser("fact")
    f.add_argument("--statement", required=True)
    f.add_argument("--evidence", required=True)
    f.add_argument("--category", default="other", choices=CATEGORIES)
    f.add_argument("--confidence", default="stated", choices=CONFIDENCE)
    f.add_argument("--source", default="")
    f.add_argument("--supersedes", default="")
    f.add_argument("--weight", default="", choices=("",) + WEIGHTS)
    f.add_argument(
        "--confirm-distinct",
        action="store_true",
        help="record even though a similar fact exists (it is a separate fact)",
    )
    f.add_argument(
        "--lasting",
        action="store_true",
        help="keep it in view even though it mentions today, tomorrow or this week",
    )
    ae = s.add_parser(
        "add-evidence", help="another quote or observation for a known fact"
    )
    ae.add_argument("--id", required=True)
    ae.add_argument("--evidence", required=True)
    wg = s.add_parser("weigh", help="mark a fact core (always in view) or normal")
    wg.add_argument("--id", required=True)
    wg.add_argument("--weight", required=True, choices=WEIGHTS)
    fi = s.add_parser("facts-index", help="every active fact, grouped, core first")
    fi.add_argument("--write", action="store_true")
    rf = s.add_parser("retract-fact")
    rf.add_argument("--id", required=True)
    rf.add_argument("--reason", required=True)
    pr = s.add_parser("pref")
    pr.add_argument("--text", required=True)
    pr.add_argument("--valence", default="like", choices=VALENCE)
    pr.add_argument("--subject", default="")
    a_ = s.add_parser("ask")
    a_.add_argument("--text", required=True)
    r = s.add_parser("resolve")
    r.add_argument("--id", required=True)
    r.add_argument("--status", required=True, choices=["asked", "answered", "dropped"])
    r.add_argument("--answer", default="")
    s.add_parser("profile")
    s.add_parser("summary")
    s.add_parser(
        "held-facts",
        help="List fact statements held because they may not match their quote",
    )
    dh = s.add_parser("decide-held")
    dh.add_argument("--id", required=True)
    dh.add_argument("--decision", choices=["accept", "dismiss"], required=True)
    df = s.add_parser(
        "duplicate-facts",
        help="List likely duplicate facts for review; changes nothing",
    )
    df.add_argument("--threshold", type=float, default=SIMILAR_FACT)
    td = s.add_parser(
        "tidy",
        help="Plan a one-time tidy of the facts ledger; changes nothing without --apply",
    )
    td.add_argument("--out", type=pathlib.Path, help="write the plan to this file")
    td.add_argument(
        "--apply", type=pathlib.Path, help="apply a plan file a person has read"
    )
    w = s.add_parser("wonder")
    w.add_argument("--status", choices=["open", "asked", "answered", "dropped"])
    ph = s.add_parser("pref-history")
    ph.add_argument("--valence", choices=VALENCE)
    so = s.add_parser("soul")
    so.add_argument("--show", action="store_true")
    so.add_argument("--init", action="store_true")
    so.add_argument("--append")
    so.add_argument("--set", dest="set_", action="store_true")
    lg = s.add_parser("ledger", help="Record many entries from one JSON file")
    lg.add_argument("--file", type=pathlib.Path, required=True)
    x = p.parse_args()
    c = cc.load(x.home)
    tz = _tz(c)
    now = _now(tz)
    if x.cmd == "fact":
        out = record_fact(
            c.human_dir,
            x.statement,
            x.evidence,
            now,
            x.category,
            x.confidence,
            x.source,
            x.supersedes,
            c.human,
            weight=x.weight,
            confirm_distinct=x.confirm_distinct,
            user_memory=c,
            lasting=x.lasting,
            agent=c.agent,
        )
    elif x.cmd == "add-evidence":
        out = add_evidence(c.human_dir, x.id, x.evidence, now)
    elif x.cmd == "weigh":
        out = weigh_fact(c.human_dir, x.id, x.weight, now, c.human)
    elif x.cmd == "facts-index":
        out = (
            write_facts_index(c)
            if x.write
            else {"index": facts_index(c.human_dir, c.human)}
        )
    elif x.cmd == "retract-fact":
        out = retract_fact(c.human_dir, x.id, x.reason, now)
    elif x.cmd == "pref":
        out = record_pref(c.life, x.text, now, x.valence, x.subject, c.agent)
    elif x.cmd == "ask":
        out = ask(c.life, x.text, now)
    elif x.cmd == "resolve":
        out = resolve(c.life, x.id, x.status, now, x.answer)
    elif x.cmd == "profile":
        out = {"facts": facts(c.human_dir)}
    elif x.cmd == "held-facts":
        out = {"held": held_facts(c.human_dir)}
    elif x.cmd == "decide-held":
        out = decide_held(c.human_dir, x.id, x.decision, now, c.human)
    elif x.cmd == "duplicate-facts":
        out = duplicate_facts(c.human_dir, x.threshold, names=(c.human,))
    elif x.cmd == "tidy":
        if x.apply:
            plan = json.loads(x.apply.read_text(encoding="utf-8"))
            out = tidy_apply(c.human_dir, plan, now, c.human, c.agent)
        else:
            plan = tidy_plan(c.human_dir, now, c.human)
            if x.out:
                atomic_write(
                    x.out, json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
                )
                out = {"plan": str(x.out), "counts": plan["counts"]}
            else:
                out = plan
    elif x.cmd == "wonder":
        out = {"questions": questions(c.life, x.status)}
    elif x.cmd == "pref-history":
        rows = _read(c.life / "preferences.jsonl", kind="companion_preference")
        out = {
            "preferences": [
                r for r in rows if not x.valence or r["valence"] == x.valence
            ]
        }
    elif x.cmd == "ledger":
        out = ledger_batch(c, x.file, now)
    elif x.cmd == "soul":
        if x.init:
            out = soul_init(c)
        elif x.append:
            out = soul_write(c, x.append, "append", now)
        elif x.set_:
            out = soul_write(c, sys.stdin.read(20000), "set", now)
        else:
            out = soul_show(c)
    else:
        out = summary(c)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if out.get("failed_at") is not None:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
