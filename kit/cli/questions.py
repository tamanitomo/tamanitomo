"""The setup questionnaire and the small validated pickers it is built from."""

from __future__ import annotations
import companion_config as cc
import companion_platform as cp
import companion_render as cr
import json
import os
import pathlib
import re
import sys
import companion_wizard as wiz
from .common import input, print


# ---------------------------------------------------------------- questionnaire
def ask(prompt, default="", choices=None, answers=None, key=None):
    if answers and key in answers:
        value = str(answers[key])
        if choices and value not in [v for v, _ in choices]:
            raise ValueError(f"Invalid choice for {key}: {value}")
        return value
    if not cp.is_terminal(sys.stdin):
        if choices:
            return choices[int(default or 1) - 1][0]
        return default
    if choices and wiz._tty():
        return wiz.choose(
            prompt,
            [(label, val) for val, label in choices],
            allow_write=False,
            allow_skip=False,
            default=int(default or 1),
        )
    while True:
        if choices:
            print(f"\n{prompt}")
            for i, (val, label) in enumerate(choices, 1):
                print(f"  {i}) {label}")
            raw = input(f"[1-{len(choices)}, default {default or 1}]: ").strip()
            if not raw:
                raw = str(default or 1)
            if raw.isdigit() and 1 <= int(raw) <= len(choices):
                return choices[int(raw) - 1][0]
            print("  -> pick a number from the list")
            continue
        raw = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
        if raw or default:
            return raw or default
        print("  -> required")


def pick_key(prompt, pairs, answers=None, key=None, default=1, note=""):
    """Choose one of a long list of presets by key, with paging. `pairs` is
    [(key, label)]; the stored answer is the key, not the position."""
    keys = [k for k, _ in pairs]
    got = wiz.choose(
        prompt,
        [(label, k) for k, label in pairs],
        answers,
        key,
        allow_write=False,
        allow_skip=False,
        default=default,
        note=note,
    )
    if got not in keys:
        raise ValueError(f"Invalid choice for {key}: {got}")
    return got


def confirm(prompt, answers=None, key=None, default=True):
    """Ask before changing something outside the agent's own directory."""
    if answers and key in answers:
        return wiz.as_bool(answers[key])
    if not cp.is_terminal(sys.stdin):
        return default
    raw = input(f'{prompt} [{"Y/n" if default else "y/N"}]: ').strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def hhmm(value, fallback):
    v = (value or "").strip()
    m = re.fullmatch(r"(\d{1,2}):?(\d{2})", v)
    if not m:
        return fallback
    h, mi = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mi:02d}" if 0 <= h < 24 and 0 <= mi < 60 else fallback


def questionnaire(c, answers=None, vault_default=None):
    """Ask the things that make this agent a specific someone. The model window is
    detected rather than asked; everything narrative is optional and skippable."""
    a = answers or {}
    # A scripted --answers file writes booleans where a person picks a labelled
    # option, and that is the natural thing to write. Normalize rather than
    # rejecting it: a setup that fails on `true` is a setup nobody can script.
    if isinstance(a.get("cron_active"), bool):
        a = {**a, "cron_active": "active" if a["cron_active"] else "paused"}
    if isinstance(a.get("share_people"), bool):
        a = {**a, "share_people": "yes" if a["share_people"] else "no"}
    personas = cr.load_personas()
    styles = cr.load_styles()
    out = {}
    if wiz._tty():
        wiz.clear()
        wiz.banner(
            "Create your companion",
            "Identity · Appearance · Relationship · Everyday life · Setup",
        )
        print(
            wiz.C.dim(
                "Skip optional story questions; review everything before applying."
            )
        )
    # First, because it decides what the rest of these questions mean — and what
    # machinery gets installed at all.
    out["agent_type"] = ask(
        "What kind of agent is this?",
        1,
        [
            (
                "companion",
                "A companion — a life of their own, moods, a relationship, may write first",
            ),
            (
                "colleague",
                "A colleague — a personality that grows and remembers you, but never reaches "
                "out socially; it speaks first only when something is broken",
            ),
            (
                "worker",
                "A quiet worker — does the work, keeps records, no relationship layer at all",
            ),
        ],
        a,
        "agent_type",
    )
    suggested_name = c.agent if c.agent != "Companion" else "Nova"
    if c.profile and not (c.home / cc.CONFIG_NAME).exists():
        import companion_gateway as cg

        metadata = cg.read_config(c.home / "profile.yaml")
        suggested_name = str(
            metadata.get("display_name")
            or c.profile.replace("_", " ").replace("-", " ").title()
        )
    out["agent"] = ask(
        "What is your companion's name?", suggested_name, None, a, "agent"
    )
    out["pronoun_set"] = ask(
        f"What pronouns does {out['agent']} use?",
        2,
        [("he", "Male"), ("she", "Female"), ("they", "They / them")],
        a,
        "pronoun_set",
    )
    raw_names = ask("What should they call you?", "", None, a, "human_names") or a.get(
        "human", "you"
    )
    names = wiz.parse_names(str(raw_names))
    out["human"] = names[0]
    out["names"] = names
    if len(names) > 1 and wiz._tty():
        print(wiz.C.dim(f'  -> {out["agent"]} will use: ' + ", ".join(names)))
    out["human_pronoun_set"] = ask(
        "And what pronouns do you use?",
        1,
        [("he", "Male"), ("she", "Female"), ("they", "They / them")],
        a,
        "human_pronoun_set",
    )
    out["persona"] = pick_key(
        "What kind of personality?",
        [(k, f"{v['label']} — {v['blurb']}") for k, v in personas.items()],
        a,
        "persona",
        note="The manner underneath everything else. The next questions add the specifics.",
    )

    # The narrative interview: identity, appearance, boundary, flirtation, likes, essence.
    iv = wiz.interview(
        out["agent"],
        out["human"],
        out["persona"],
        {
            **a,
            "pronoun_set": out["pronoun_set"],
            "human_pronoun_set": out["human_pronoun_set"],
        },
    )
    out["interview"] = iv
    # What the human hopes this brings, in their own words, kept verbatim.
    iv["hope"] = str(a.get("hope") or "").strip()[:1000]
    # Which shared parts of the soul the human keeps to themselves, chosen at setup.
    locks = a.get("soul_locks") or {}
    if not isinstance(locks, dict):
        raise ValueError("soul_locks must map section ids to true or false")
    out["soul_locks"] = {str(k): bool(v) for k, v in locks.items()}
    out["boundary"] = iv["boundary_key"]
    out["age"] = iv["age"]
    out["explicit"] = iv["explicit"]
    out["birthdate"] = iv.get("birthdate", "")

    if wiz._tty():
        wiz.rule("05 / 05   Daily life · Time, contact and memory")
    # Image PROVIDERS are Hermes' own setup (`hermes tools`). What matters here is
    # that the agent looks like the same person wherever an image gets made.
    out["image_mode"] = "external"
    if "image_style" in a:
        out["image_style"] = pick_key(
            "If you make images of them, what style?",
            [(k, f"{v['label']} — {v['blurb']}") for k, v in styles.items()],
            a,
            "image_style",
        )
    elif iv.get("visual") == "none":
        out["image_style"] = "none"  # no visual identity was set up at all
    elif iv.get("visual") == "edit":
        out["image_style"] = "unset"  # deferred with the rest of the look
    else:
        out["image_style"] = pick_key(
            "If you make images of them, what style?",
            [
                (k, f"{v['label']} — {v['blurb']}")
                for k, v in styles.items()
                if k not in ("none", "unset")
            ]
            + [
                ("none", styles["none"]["label"] + " — " + styles["none"]["blurb"]),
                ("unset", "Skip: " + styles["unset"]["label"]),
            ],
            a,
            "image_style",
            note="Consistency matters more than the style itself; the same look every time.",
        )
    timeline_answer = a.get("image_timeline", False)
    if "image_timeline" in a:
        out["image_timeline"] = wiz.as_bool(timeline_answer)
    else:
        out["image_timeline"] = (
            wiz.choose(
                "Keep a visual timeline of their day?",
                [
                    (
                        "No automatic images — everyday life and outfits still continue",
                        "off",
                    ),
                    ("One local image every 15 minutes — retain 30 days", "on"),
                ],
                allow_write=False,
                allow_skip=False,
                note="Uses your configured Hermes image provider: up to 96 images/day, including overnight. Images stay local. Copy favorites elsewhere to keep them.",
                default=1,
            )
            == "on"
        )
    if out["image_timeline"] and out["image_style"] in ("none", "unset"):
        if not wiz._tty():
            raise ValueError("Choose an image style before enabling the image timeline")
        out["image_style"] = pick_key(
            "Choose a style for your timeline images",
            [
                (k, f"{v['label']} — {v['blurb']}")
                for k, v in styles.items()
                if k not in ("none", "unset")
            ],
        )
    if out["agent_type"] == "worker":
        out["outreach"] = "never"
    elif out["agent_type"] == "colleague":
        # A colleague speaks first only when something is broken. That is not a
        # setting it should be able to talk itself out of, so it is fixed here.
        out["outreach"] = "updates_only"
        if wiz._tty():
            print(
                wiz.C.dim(
                    "\n  A colleague writes first only when something is genuinely wrong."
                )
            )
    else:
        out["outreach"] = ask(
            "May they message you first?",
            2,
            [
                ("free", "Yes — socially, whenever they want to"),
                ("updates_only", "Only with something real to report or ask"),
                ("never", "No, replies only"),
            ],
            a,
            "outreach",
        )
    out["outreach_per_day"] = 0 if out["outreach"] == "never" else ask_outreach_cap(a)
    out["cron_active"] = (
        ask(
            "Start the scheduled background routine after setup?",
            2,
            [
                ("active", "Yes — authorize these recurring jobs"),
                (
                    "paused",
                    "Create paused (recommended); enable after hook approval and gateway restart",
                ),
            ],
            a,
            "cron_active",
        )
        == "active"
    )
    out["quiet_start"] = hhmm(
        ask(
            "Start of your do-not-disturb hours (HH:MM)",
            "23:00",
            None,
            a,
            "quiet_start",
        ),
        "23:00",
    )
    out["quiet_end"] = hhmm(
        ask("End of your do-not-disturb hours (HH:MM)", "08:00", None, a, "quiet_end"),
        "08:00",
    )
    permissions = {}
    if out["outreach"] != "never":
        out["adaptive_quiet"] = confirm(
            "Let those hours drift toward the ones you actually keep?",
            a,
            "adaptive_quiet",
            False,
        )
        if wiz._tty():
            print(
                wiz.C.dim(
                    "  If you consistently write inside the window for a fortnight, it moves by half an\n"
                    "  hour at a time toward the hours you really keep, and tells you once when it does.\n"
                    "  It never leaves you less than six hours of quiet, and replies are always allowed\n"
                    "  at any hour — quiet hours only govern messages they start."
                )
            )
        for kind, question, default in (
            ("image", "May they send a photo you did not ask for?", 2),
            ("voice", "May they send a voice note you did not ask for?", 2),
        ):
            permissions[kind] = ask(
                question,
                default,
                [
                    ("yes", "Yes, whenever it fits"),
                    ("ask", "They may mention it and offer; not attach it unasked"),
                    ("no", "No"),
                ],
                a,
                "permit_" + kind,
            )
    out["content_permissions"] = permissions
    out["share_people"] = (
        ask(
            "Should other agents here share what they learn about you?",
            1,
            [
                (
                    "yes",
                    "Yes — one shared record of me, so anything one learns, they all know",
                ),
                ("no", "No — each one gets to know me from scratch"),
            ],
            a,
            "share_people",
        )
        == "yes"
    )
    out["location"] = ask(
        "Where do you live? (a place name, for weather and daylight; blank to skip)",
        "",
        None,
        a,
        "location",
    ).strip()[:120]
    out["sensors"] = ask_sensors(a, bool(out["location"]))
    import yaml

    existing_cfg = (
        yaml.safe_load((c.home / "config.yaml").read_text(encoding="utf-8")) or {}
        if (c.home / "config.yaml").exists()
        else {}
    )
    if not isinstance(existing_cfg, dict):
        raise ValueError("config.yaml must be a mapping")
    detected_timezone = (
        existing_cfg.get("timezone") or os.environ.get("TZ") or c.timezone
    )
    if a and "timezone" in a:
        out["timezone"] = str(a["timezone"])
    elif not wiz._tty():
        out["timezone"] = detected_timezone
    else:
        out["timezone"] = pick_timezone(detected_timezone)
    from zoneinfo import ZoneInfo

    ZoneInfo(out["timezone"])

    vdef = str(vault_default or c.vault or (pathlib.Path.home() / "vault"))
    sub = (
        (pathlib.Path(vdef) / "agents" / c.profile) if c.profile else pathlib.Path(vdef)
    )
    if wiz._tty():
        print(
            "\n"
            + wiz.C.bold("Shared vault")
            + wiz.C.dim(" — the one folder every agent keeps its life in.")
        )
        print(
            wiz.C.dim(
                f'  {out["agent"]} gets its own subfolder; you are not naming that part.'
            )
        )
        print(wiz.C.dim(f'  press Enter for {vdef}  ({out["agent"]} -> {sub})'))
    out["vault"] = ask("Vault root", vdef, None, a, "vault")

    out["context_mode"] = "fixed" if "context_tokens" in a else "auto"
    if "context_tokens" in a:
        out["context_tokens"] = int(a["context_tokens"])
    else:
        tokens, how = cc.detect_context_tokens(c.home, c.hermes_root)
        out["context_tokens"] = tokens
        print(f"\nModel context window: {tokens:,} tokens (from {how}).")
        print(
            f"  -> {cc.Companion(context_tokens=tokens).budgets()['total']} chars of continuity per turn."
        )
        if wiz._tty() and not confirm("  Does that look right?", a, "context_ok", True):
            out["context_mode"] = "fixed"
            out["context_tokens"] = int(
                ask("Context window in tokens", str(tokens), None, a, "context_tokens")
            )
    if not 2048 <= out["context_tokens"] <= 10_000_000:
        raise ValueError("Context window must be between 2,048 and 10,000,000 tokens")
    for key in ("agent", "human"):
        if (
            not out[key].strip()
            or len(out[key]) > 100
            or any(ord(ch) < 32 for ch in out[key])
            or "{{" in out[key]
        ):
            raise ValueError(f"{key} must be plain text, 1–100 characters")
    wiz.review(out, c.home)
    return out


def ask_sensors(answers=None, has_location=False):
    """Which of the cheap senses to switch on.

    Every one is optional and every one degrades to silence, so this is a low-
    stakes question — but it is worth asking rather than defaulting, because a
    companion that knows the weather where you live and how long it has been
    since you wrote is a different thing from one that does not.
    """
    import companion_sensors

    if answers and "sensors" in answers:
        chosen = answers["sensors"]
        if isinstance(chosen, str):
            chosen = [x.strip() for x in chosen.split(",") if x.strip()]
        return [name for name in companion_sensors.REGISTRY if name in (chosen or [])]
    default = [
        name for name in companion_sensors.REGISTRY if name != "weather" or has_location
    ]
    if not wiz._tty():
        return default
    print(
        "\n"
        + wiz.C.bold("Senses")
        + wiz.C.dim(" — cheap, optional, and silent when they have nothing.")
    )
    chosen = []
    for name, spec in companion_sensors.REGISTRY.items():
        if name == "weather" and not has_location:
            print(wiz.C.dim(f"  weather — skipped, since no location was given"))
            continue
        print()
        print("  " + wiz.C.bold(name) + wiz.C.dim(" — " + spec["blurb"]))
        if confirm("  Switch it on?", None, None, True):
            chosen.append(name)
    return chosen


def apply_answers(c, ans):
    from .common import next_schedule_offset

    return cc.Companion(
        agent=ans["agent"],
        pronoun_set=ans["pronoun_set"],
        human=ans["human"],
        human_pronoun_set=ans["human_pronoun_set"],
        timezone=ans["timezone"],
        profile=c.profile,
        hermes_root=c.hermes_root,
        context_tokens=int(ans["context_tokens"]),
        context_mode=ans.get("context_mode", "auto"),
        image_mode=ans["image_mode"],
        image_style=ans["image_style"],
        image_timeline=ans.get("image_timeline", False),
        boundary=ans["boundary"],
        outreach=ans["outreach"],
        outreach_per_day=int(ans.get("outreach_per_day", 3)),
        names=list(ans.get("names") or []),
        age=int(ans.get("age", 24)),
        birthdate=str(ans.get("birthdate") or ""),
        explicit=bool(ans.get("explicit", False)),
        cron_active=ans.get("cron_active", True),
        persona=ans.get("persona", "warm"),
        image_interval_minutes=c.image_interval_minutes,
        schedule_offset_minutes=next_schedule_offset(c),
        relationship_pace=ans.get("relationship_pace", "natural"),
        quiet_start=ans.get("quiet_start", "23:00"),
        quiet_end=ans.get("quiet_end", "08:00"),
        soul_in_vault=c.soul_in_vault,
        agent_type=ans.get("agent_type", "companion"),
        location=str(ans.get("location") or ""),
        adaptive_quiet=bool(ans.get("adaptive_quiet", False)),
        content_permissions=dict(ans.get("content_permissions") or {}),
        sensors=list(ans.get("sensors") or []),
        share_people=bool(ans.get("share_people", False)),
        vault=pathlib.Path(ans.get("vault") or c.vault).expanduser().absolute(),
    )


# Everything --answers may legitimately carry. A key outside this set is a typo
# or a renamed question, and silently ignoring it hands back a companion built
# from defaults that nobody asked for.
SETUP_KEYS = frozenset(
    {
        "agent",
        "human",
        "human_names",
        "persona",
        "image_mode",
        "image_style",
        "outreach",
        "cron_active",
        "quiet_start",
        "quiet_end",
        "timezone",
        "vault",
        "context_tokens",
        "image_timeline",
        "context_ok",
        "soul",
        "move_soul",
        "gateway_mode",
        "gateway_action",
        "outreach_per_day",
        "location",
        "sensors",
        "adaptive_quiet",
        "permit_image",
        "permit_voice",
        "content_permissions",
        "share_people",
        "agent_type",
        "relationship_pace",
        "soul_locks",
        "hope",
    }
)


def known_answer_keys():
    return SETUP_KEYS | wiz.INTERVIEW_KEYS


OUTREACH_CAPS = [
    ("Once a day", "1"),
    ("Up to three times a day (recommended)", "3"),
    ("Up to five times a day", "5"),
    ("Up to ten times a day", "10"),
    ("No limit — trust the agent to judge", "0"),
]


def parse_cap(value):
    """A daily message cap. Words for "no limit" are accepted because that is what
    people type when the menu offered it a moment ago."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Give an explicit numeric cap or no limit")
    text = str(value).strip().lower()
    if text in ("0", "no limit", "unlimited"):
        return 0
    match = re.fullmatch(
        r"([0-9]{1,3})(?:\s*(?:a day|/day|per day|(?:times?|messages?)(?: (?:a|per) day)?))?",
        text,
    )
    if not match:
        raise ValueError(
            f"{value!r} is not a daily message cap; use 0 for no limit or replies-only for no outreach"
        )
    n = int(match.group(1))
    if not 0 <= n <= 100:
        raise ValueError("pick between 0 and 100 messages a day")
    return n


def ask_outreach_cap(answers=None):
    """Answers give the number itself, never a menu position — "10" here means ten
    messages, not the tenth option."""
    if answers and "outreach_per_day" in answers:
        return parse_cap(answers["outreach_per_day"])
    if not cp.is_terminal(sys.stdin):
        return 3
    while True:
        got = wiz.choose(
            "How many times a day may they message you first?",
            OUTREACH_CAPS,
            allow_write=True,
            allow_skip=False,
            default=2,
            write_label="some other number",
            write_hint="messages a day (0 for no limit)",
            note="Enforced in code, outside the model, along with your do-not-disturb hours.",
        )
        try:
            return parse_cap(got)
        except ValueError as e:
            print(wiz.C.red("  " + str(e)))


def read_answers(args):
    if not args.answers:
        raw = {}
    else:
        ans_str = args.answers.strip()
        ans_path = pathlib.Path(ans_str[1:] if ans_str.startswith("@") else ans_str)
        if not ans_str.startswith("{") and ans_path.is_file():
            raw = json.loads(ans_path.read_text(encoding="utf-8"))
        else:
            raw = json.loads(ans_str)
    if not isinstance(raw, dict):
        raise ValueError("--answers must be a JSON object")
    unknown = sorted(set(raw) - known_answer_keys())
    if unknown:
        raise ValueError(
            "Unknown answer key(s): "
            + ", ".join(unknown)
            + "\nAnswers are matched by name; a key nothing reads leaves that question "
            "on its default. Valid keys: " + ", ".join(sorted(known_answer_keys()))
        )
    if getattr(args, "vault", None):
        raw["vault"] = str(args.vault)
    return raw


def strict_hhmm(value):
    got = hhmm(value, "")
    if not got:
        raise ValueError(f"{value!r} is not a time of day; use HH:MM, e.g. 23:00")
    return got


def check_timezone(name):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError(
            f"{name!r} is not an IANA timezone; use one like Europe/London"
        ) from exc
    return name


# US zones first, Eastern as the default, because that is the common answer and
# the rest is a region drill-down rather than 600 rows of arrow-key scrolling.
US_TIMEZONES = [
    ("America/New_York", "Eastern — New York"),
    ("America/Chicago", "Central — Chicago"),
    ("America/Denver", "Mountain — Denver"),
    ("America/Phoenix", "Mountain, no DST — Phoenix"),
    ("America/Los_Angeles", "Pacific — Los Angeles"),
    ("America/Anchorage", "Alaska — Anchorage"),
    ("Pacific/Honolulu", "Hawaii — Honolulu"),
]
ELSEWHERE = "__elsewhere__"


def zones_by_region():
    from zoneinfo import available_timezones

    regions = {}
    for zone in sorted(available_timezones()):
        region = zone.split("/", 1)[0] if "/" in zone else "Other"
        regions.setdefault(region, []).append(zone)
    return regions


def pick_timezone(current=""):
    """Choose a zone from a list. Typing an IANA name correctly from memory is a
    silly thing to ask of anyone, and a typo here misdates every episode."""
    rows = list(US_TIMEZONES)
    if current and current not in dict(rows):
        rows.append((current, f"{current} — currently set"))
    rows.append((ELSEWHERE, "Somewhere else — choose a region"))
    got = pick_key(
        "Timezone",
        rows,
        note="Used for quiet hours, scheduled jobs and the companion’s own clock.",
    )
    if got != ELSEWHERE:
        return got
    regions = zones_by_region()
    region = pick_key(
        "Which region?",
        [(name, f"{name} ({len(zones)})") for name, zones in sorted(regions.items())],
    )
    return pick_key(f"Timezone in {region}", [(zone, zone) for zone in regions[region]])
