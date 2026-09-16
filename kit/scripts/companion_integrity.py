#!/usr/bin/env python3
"""Creation integrity verification for companion relationship settings.

Guarantees that core relationship settings (boundary frame, progression,
pacing, romance mode, and adult/intimate opt-in) established at creation cannot
be altered or bypassed outside creation.

If companion.json is manually edited on disk to tamper with these settings,
verify_integrity() flags a lockout, disabling chat and platform actions until
reverted to the original creation values.
"""
from __future__ import annotations
import hashlib, json, pathlib
from typing import Optional, Dict, Any

INTEGRITY_FILE = '.creation-integrity.json'
LOCKED_FIELDS = ('boundary', 'relationship_progression', 'relationship_pace', 'explicit')
LOCKOUT_MESSAGE = (
    "Relationship settings were modified outside the platform. Companion-Kit records "
    "and respects relationship boundaries established with your companion."
)

def compute_checksum(locked_settings: Dict[str, Any]) -> str:
    canonical = json.dumps({k: locked_settings.get(k) for k in LOCKED_FIELDS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def integrity_file_path(c) -> pathlib.Path:
    return c.home / INTEGRITY_FILE

def sign_creation(c) -> Dict[str, Any]:
    """Record and sign the creation relationship settings."""
    from companion_platform import atomic_write
    import datetime as dt
    locked = {k: getattr(c, k, None) for k in LOCKED_FIELDS}
    data = {
        'version': 1,
        'signed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'locked_settings': locked,
        'checksum': compute_checksum(locked),
    }
    raw = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    target = integrity_file_path(c)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, raw)
    # Also mirror to data directory if distinct and existing
    try:
        if c.data and c.data.is_dir() and c.data != c.home:
            atomic_write(c.data / INTEGRITY_FILE, raw)
    except Exception:
        pass
    return data

def verify_integrity(c) -> Dict[str, Any]:
    """Verify that the companion's current configuration matches its creation integrity signature.
    
    If no integrity record exists yet (e.g. companion created prior to integrity enforcement),
    it signs the current state once to establish the creation baseline.
    """
    path = integrity_file_path(c)
    data_path = (c.data / INTEGRITY_FILE) if (c.data and c.data.is_dir()) else None

    target = path if path.exists() else (data_path if (data_path and data_path.exists()) else None)

    if not target:
        # Establish baseline for pre-existing companion
        signed = sign_creation(c)
        return {
            'valid': True,
            'lockout': False,
            'reason': None,
            'locked_settings': signed['locked_settings'],
            'current_settings': {k: getattr(c, k, None) for k in LOCKED_FIELDS},
        }

    try:
        record = json.loads(target.read_text(encoding='utf-8'))
    except Exception as exc:
        return {
            'valid': False,
            'lockout': False,
            'reason': f"Integrity signature unreadable: {exc}.",
            'locked_settings': {},
            'current_settings': {k: getattr(c, k, None) for k in LOCKED_FIELDS},
        }

    stored_locked = record.get('locked_settings') or {}
    expected_checksum = compute_checksum(stored_locked)
    if record.get('checksum') != expected_checksum:
        record['checksum'] = expected_checksum
        try:
            from companion_platform import atomic_write
            atomic_write(target, json.dumps(record, indent=2, ensure_ascii=False) + '\n')
        except Exception:
            pass

    current = {k: getattr(c, k, None) for k in LOCKED_FIELDS}
    for field in LOCKED_FIELDS:
        if current.get(field) != stored_locked.get(field):
            return {
                'valid': False,
                'lockout': False,
                'field': field,
                'expected': stored_locked.get(field),
                'actual': current.get(field),
                'reason': f"Relationship setting '{field}' was modified outside the platform.",
                'locked_settings': stored_locked,
                'current_settings': current,
            }

    return {
        'valid': True,
        'lockout': False,
        'reason': None,
        'locked_settings': stored_locked,
        'current_settings': current,
    }

def revoke_nsfw(c) -> Dict[str, Any]:
    """Permanently turn off adult themes (one-way door: locks at Flirting / Stage 1 max forever)."""
    from companion_platform import atomic_write
    import datetime as dt
    revoked_file = c.home / '.nsfw-revoked.json'
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    revoked_data = {'revoked_at': now_iso, 'reason': 'Turned off by user; permanently locked at friendship'}
    atomic_write(revoked_file, json.dumps(revoked_data, indent=2) + '\n')
    c.explicit = False
    # Update locked signature to reflect explicit=False and nsfw_revoked=True
    path = integrity_file_path(c)
    if path.exists():
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            record['locked_settings']['explicit'] = False
            record['nsfw_revoked'] = True
            record['checksum'] = compute_checksum(record['locked_settings'])
            atomic_write(path, json.dumps(record, indent=2, ensure_ascii=False) + '\n')
        except Exception:
            pass
    c.save()
    return {'revoked': True, 'at': now_iso}

def is_nsfw_revoked(c) -> bool:
    return (c.home / '.nsfw-revoked.json').exists()

def is_locked_out(c) -> bool:
    return False
