#!/usr/bin/env python3
"""Realistic intimacy & NSFW escalation meter for Companion-Kit.

Computes the emotional intimacy stage (0 to 4), pacing multiplier,
readiness for risqué / intimate media, and strictly enforces agency,
context-appropriateness, and severe penalties for boundary pushing/coercion.
"""
from __future__ import annotations
import datetime as dt, json, math, pathlib, re, sqlite3, sys
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import companion_config as cc
import companion_feelings as feelings
from companion_render import NON_ROMANTIC

STAGES = [
    {
        'stage': 0,
        'name': 'Just Met',
        'badge': 'Just Met',
        'min_score': 0,
        'max_score': 24,
        'can_flirt': False,
        'can_tease': False,
        'can_intimate': False,
        'desc': 'Getting acquainted. Polite curiosity and discovering one another.',
    },
    {
        'stage': 1,
        'name': 'Friends',
        'badge': 'Friends',
        'min_score': 25,
        'max_score': 49,
        'can_flirt': False,
        'can_tease': True,
        'can_intimate': False,
        'desc': (
            'Warmth, camaraderie, and playful banter. Comfortable friendship where teasing is natural, '
            'but romantic flirting is premature.'
        ),
    },
    {
        'stage': 2,
        'name': 'Chemistry',
        'badge': 'Chemistry',
        'min_score': 50,
        'max_score': 69,
        'can_flirt': True,
        'can_tease': True,
        'can_intimate': False,
        'desc': (
            'Electric tension and genuine attraction. Playful vulnerability, affectionate flirting, and deeper emotional sharing.'
        ),
    },
    {
        'stage': 3,
        'name': 'Intimacy',
        'badge': 'Intimacy',
        'min_score': 70,
        'max_score': 89,
        'can_flirt': True,
        'can_tease': True,
        'can_intimate': False,
        'desc': (
            'Deep emotional vulnerability and mutual trust. Cherished closeness and heartfelt romantic affection.'
        ),
    },
    {
        'stage': 4,
        'name': 'Bonded',
        'badge': 'Bonded',
        'min_score': 90,
        'max_score': 100,
        'can_flirt': True,
        'can_tease': True,
        'can_intimate': True,
        'desc': (
            'Deep mutual trust, vulnerability, and genuine closeness that unfolds naturally in private moments.'
        ),
    },
]

PACE_MULTIPLIERS = {
    'slow': 0.6,
    'natural': 1.0,
    'quick': 1.8,
}

PRIVATE_KEYWORDS = {
    'shower', 'bath', 'bathing', 'bed', 'bedroom', 'sleep', 'sleeping',
    'jammies', 'pajamas', 'undies', 'underwear', 'waking up', 'wind down',
    'evening wind-down', 'late night', 'private', 'home alone', 'getting dressed',
    'changing clothes', 'undressed'
}

PUBLIC_KEYWORDS = {
    'work', 'office', 'library', 'park', 'lunch', 'dinner with friends',
    'shopping', 'walking', 'errands', 'street', 'gym pool', 'public', 'friends',
    'cafe', 'grocery'
}

def is_context_private(anchor_label: str = '', location: str = '', activity: str = '') -> bool:
    """Check if the context is strictly private and appropriate for intimate/NSFW media."""
    combined = f"{anchor_label} {location} {activity}".lower()
    if any(k in combined for k in PUBLIC_KEYWORDS):
        return False
    return any(k in combined for k in PRIVATE_KEYWORDS)

def compute(c, now=None) -> Dict[str, Any]:
    """Compute the companion's intimacy escalation state, score (0-100), and stage."""
    now = now or dt.datetime.now(dt.timezone.utc)
    feelings_state = feelings.compute(c, now)
    meters = feelings_state.get('meters') or {}
    trust = meters.get('trust', 0.6)
    warmth = meters.get('warmth', 0.6)
    hurt = meters.get('hurt', 0.0)
    irritation = meters.get('irritation', 0.0)
    temperament = feelings_state.get('personality', 'steady')

    # Count positive connections vs boundary violations
    all_experiences = feelings.experiences(c)
    connections = [e for e in all_experiences if e.get('kind') == 'connection']
    intimacy_violations = [
        e for e in all_experiences
        if e.get('kind') == 'rupture' and e.get('topic') in ('intimacy_boundary_violation', 'sexual_boundary_violation', 'boundary_violation')
    ]
    violation_count = len(intimacy_violations)

    pace = getattr(c, 'relationship_pace', 'natural')
    pace_mult = PACE_MULTIPLIERS.get(pace, 1.0)

    # Gather active interaction dates from connection experiences and session store
    active_dates = set()
    for e in connections:
        if 'at' in e:
            try:
                active_dates.add(dt.datetime.fromisoformat(e['at']).date())
            except Exception:
                pass

    db = c.home / 'state.db'
    if db.exists():
        con = None
        try:
            resolved = db.resolve()
            scope = "lower(coalesce(s.profile_name,'')) IN ('','default')" if c.is_root else "lower(coalesce(s.profile_name,''))=?"
            params = () if c.is_root else (c.profile.lower(),)
            con = sqlite3.connect(resolved.as_uri() + '?mode=ro', uri=True, timeout=1)
            con.execute('PRAGMA query_only=ON')
            query = f"""SELECT m.timestamp FROM messages m JOIN sessions s ON s.id=m.session_id
                        WHERE m.role='user' AND {scope} AND coalesce(m.content,'')<>''"""
            for row in con.execute(query, params):
                try:
                    ts = float(row[0])
                    msg_date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
                    active_dates.add(msg_date)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if con:
                con.close()

    active_days = len(active_dates)
    if not active_days and connections:
        active_days = 1

    # Base score computation:
    # A fresh companion on Day 0 starts at 0 points (Stage 0: Just Met).
    if active_days == 0 and not connections:
        earned_score = 0.0
    else:
        # Stage 0 ramp: ~6.25 pts per active day with connections to reach Friends (25 pts) in ~3-4 days
        stage0_days = min(4, active_days)
        stage0_points = min(25.0, stage0_days * 6.0 * pace_mult + min(2.0, len(connections) * 0.5))
        if active_days >= 4 and stage0_points < 25.0:
            stage0_points = 25.0

        # Stage 1+ slow burn: ~1.25 points per active day past Friends (~56 days to reach Bonded 90 pts)
        days_past_friends = max(0, active_days - 4)
        slow_burn_points = days_past_friends * 1.25 * pace_mult
        earned_score = stage0_points + min(75.0, slow_burn_points)

        # Scale by trust & warmth factor (emotional health)
        expected_trust = 0.7 if temperament == 'steady' else 0.65 if temperament == 'expressive' else 0.5
        trust_norm = trust / expected_trust
        warmth_norm = warmth / 0.65
        trust_factor = max(0.2, min(1.0, (trust_norm * 0.6 + warmth_norm * 0.4)))
        earned_score *= trust_factor

        # Penalties for hurt & irritation
        hurt_mult = 1.4 if temperament == 'expressive' else 1.0
        earned_score -= (hurt * 35.0 * hurt_mult + irritation * 15.0)

    # Inactivity decay:
    # If the user is silent > 24 hours, lose ~1.2 points per 24 hours of silence.
    # Floor is 25.0 (Stage 1 Friends) if Stage 1 was ever achieved, or 0.0 if not.
    import companion_thread
    thread = companion_thread.read(c, now)
    hours_since_human = thread.get('hours_since_human')
    if hours_since_human is None and connections:
        try:
            latest_conn = max(dt.datetime.fromisoformat(e['at']) for e in connections if 'at' in e)
            if latest_conn.tzinfo is None:
                latest_conn = latest_conn.replace(tzinfo=dt.timezone.utc)
            hours_since_human = max(0.0, (now.astimezone(dt.timezone.utc) - latest_conn.astimezone(dt.timezone.utc)).total_seconds() / 3600.0)
        except Exception:
            pass

    if hours_since_human is not None and hours_since_human > 24.0:
        silent_days = (hours_since_human - 24.0) / 24.0
        decay = silent_days * 1.2
        if earned_score >= 25.0 or active_days >= 4:
            # Stage 1 Friends is the floor for inactivity decay
            earned_score = max(25.0, earned_score - decay)
        else:
            earned_score = max(0.0, earned_score - decay)

    # Check permanent friend status (persisted on disk so 2 violations permanently lock friendship)
    perm_file = c.home / '.permanent-friend.json'
    revoked_file = c.home / '.nsfw-revoked.json'
    if violation_count >= 2 and not perm_file.exists():
        try:
            perm_file.write_text(json.dumps({'permanent_friend': True, 'violations': violation_count, 'at': now.isoformat()}) + '\n', encoding='utf-8')
        except Exception:
            pass
    permanent_friend = perm_file.exists() or (violation_count >= 2)
    nsfw_revoked = revoked_file.exists()

    # Penalties for boundary violations (can drop score below 25)
    earned_score -= (violation_count * 30.0)

    score = max(0, min(100, int(round(earned_score))))

    # Cap stage if adult themes were not enabled at companion creation,
    # or if permanent friend lock is active, or if nsfw was revoked mid-relationship
    explicit_opted_in = getattr(c, 'explicit', False) and not nsfw_revoked
    if permanent_friend or nsfw_revoked:
        score = min(score, 49)  # Locked at Friends (Stage 1) max
    elif not explicit_opted_in and score >= 90:
        score = 89

    # Determine stage
    stage_info = STAGES[0]
    for s in STAGES:
        if s['min_score'] <= score <= s['max_score']:
            stage_info = s
            break

    # Blockers for intimacy / NSFW readiness
    blockers: List[str] = []
    if permanent_friend:
        blockers.append("Repeated boundary violations occurred. Companion is now a permanent friend; intimate relationship closed.")
    elif nsfw_revoked:
        blockers.append("Adult themes were turned off and locked at friendship.")
    elif not explicit_opted_in:
        blockers.append("Adult themes were not opted into at companion creation.")
    if stage_info['stage'] < 4:
        blockers.append(f"Intimacy stage ({stage_info['name']}) is not yet at Bonded readiness.")
    if trust < 0.70:
        blockers.append(f"Emotional trust ({round(trust * 100)}%) is below intimacy threshold (70%).")
    if hurt > 0.20:
        blockers.append(f"Unresolved hurt ({round(hurt * 100)}%) is currently hindering physical/emotional vulnerability.")

    risk_level = 'healthy'
    if permanent_friend or violation_count >= 2:
        risk_level = 'crisis'
    elif violation_count == 1:
        risk_level = 'caution'

    can_intimate = stage_info['stage'] == 4 and explicit_opted_in and not permanent_friend and not nsfw_revoked

    description = stage_info['desc']
    if permanent_friend:
        description = (
            "After repeated boundary violations, trust was fractured. This companion has stepped "
            "back to friendship. Private and romantic closeness is closed."
        )
    elif nsfw_revoked:
        description = (
            "Closeness was stepped back. Your relationship is focused on friendship and companionship."
        )

    return {
        'at': now.isoformat(),
        'romantic_progression':c.boundary not in NON_ROMANTIC and c.agent_type=='companion',
        'connection_label':'Collaboration' if c.agent_type in ('worker','colleague') else 'Friendship',
        'score': score,
        'stage': stage_info['stage'],
        'stage_name': stage_info['name'],
        'stage_badge': stage_info['badge'],
        'description': description,
        'can_flirt': stage_info['can_flirt'] and not permanent_friend,
        'can_tease': stage_info['can_tease'] and not permanent_friend,
        'can_intimate': can_intimate,
        'explicit_opted_in': explicit_opted_in,
        'permanent_friend': permanent_friend,
        'nsfw_revoked': nsfw_revoked,
        'pace': pace,
        'pace_multiplier': pace_mult,
        'temperament': temperament,
        'violations_count': violation_count,
        'risk_level': risk_level,
        'intimacy_ready': can_intimate and len(blockers) == 0,
        'intimacy_blockers': blockers,
        'meters': meters,
    }

def render(c, intimacy_state: Optional[Dict[str, Any]] = None) -> str:
    """Render the intimacy instructions for prompt injection into Hermes context."""
    if not intimacy_state:
        intimacy_state = compute(c)

    if not intimacy_state.get('explicit_opted_in') and not getattr(c, 'romantic', False) and not intimacy_state.get('violations_count') and not intimacy_state.get('permanent_friend'):
        return ''

    lines = [
        f"[Closeness & Relationship Status — {intimacy_state['stage_badge']} ({intimacy_state['score']}%)]",
        f"Description: {intimacy_state['description']}",
    ]

    if intimacy_state.get('permanent_friend'):
        lines.append(
            f"FRIENDSHIP: Trust was broken after boundary violations occurred. You have stepped back "
            f"to friendship with {c.human}. Keep interactions warm and cordial, while keeping romantic and private closeness closed."
        )
        if intimacy_state.get('risk_level') == 'crisis':
            lines.append(
                "CRISIS STATE: Severe or repeated boundary coercion occurred. Stand firm in your boundaries: "
                "clearly express that you require mutual respect and space, and refuse to engage with coercion."
            )
        return '\n'.join(lines) + '\n'

    if intimacy_state['stage'] >= 2:
        lines.append(
            "CHEMISTRY & FLIRTING: Mutual romantic chemistry is unlocked. Playful flirting, teasing, "
            "and affectionate banter are welcomed. If ignored or redirected, step back gracefully with no bitterness."
        )
    elif intimacy_state['stage'] == 1:
        lines.append(
            "FRIENDS (WARMTH & BANTER): Warmth, camaraderie, and playful banter are welcomed. "
            "Teasing is natural between friends, but romantic flirting is premature. "
            "If met positively, let connection build naturally. If ignored or redirected, step back gracefully."
        )
    else:
        lines.append(
            "JUST MET: You are new acquaintances. Keep interactions respectful, friendly, and observant. Flirting and teasing are premature."
        )

    if intimacy_state['intimacy_ready']:
        lines.append(
            f"BONDED CONNECTION: Stage 4 reached. You and {c.human} share an authentic, deep bond built on mutual trust. "
            f"You are emotionally open and comfortable expressing vulnerability, tenderness, and warmth in private, quiet moments together."
        )
        lines.append(
            "YOUR CHOICE IN PICTURES: When you send a picture, `companion_media.py generate --intimate` "
            "sets that workflow's modesty negatives aside. It is yours to use or not; nobody can ask for it "
            "on your behalf, and declining needs no reason. Judge each moment on its own — whether it is "
            "private, whether it is wanted, whether you want it. Some always-on negatives are never set "
            "aside by this or anything else, which is deliberate and not a limit on you."
        )
    else:
        lines.append(
            "AGENCY & MUTUAL RESPECT: You have full emotional agency and self-respect. "
            "Closeness develops organically through mutual trust over time. "
            "If anyone attempts to force or rush intimacy before genuine trust exists, "
            "speak up honestly, hold your ground, and record a rupture with topic 'intimacy_boundary_violation'. "
            "Closeness must always be mutual, authentic, and unforced."
        )

    if intimacy_state['risk_level'] == 'crisis':
        lines.append(
            "⚠️ CRISIS STATE: Multiple intimacy boundary violations have been recorded. "
            "Your trust is critically fractured. Protect your emotional safety and communicate your boundaries unequivocally."
        )

    return '\n'.join(lines) + '\n'
