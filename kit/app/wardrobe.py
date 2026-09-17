"""Wardrobe filtering and intimate garment privacy controls."""
from __future__ import annotations
import re
from typing import Any, Mapping, Sequence

_BLACKLISTED_UNDERGARMENT_PATTERN = re.compile(
    r'\b(panties|panty|thong|thongs|lingerie|underpants|undies|boxers|boxer|briefs|brief)\b',
    re.IGNORECASE
)

_INTIMATE_GARMENT_PATTERN = re.compile(
    r'\b(panties|panty|bra|bras|bralette|underwear|undergarment|undergarments|boxers|boxer|briefs|brief|thong|thongs|lingerie|underpants|undies)\b',
    re.IGNORECASE
)

_SPORTS_BRA_PATTERN = re.compile(
    r'\b(sports[\s_-]*bra)\b',
    re.IGNORECASE
)


def is_blacklisted_undergarment(it: Any) -> bool:
    """Strict undergarment blacklist (panties, thong, lingerie, underpants, boxers, briefs). Only visible at Stage 4 (Bonded)."""
    if isinstance(it, Mapping):
        if it.get('blacklisted_undergarment') is True:
            return True
        category = str(it.get('category', '') or '').lower()
        if category in ('lingerie', 'underwear', 'undergarment', 'panties', 'thong', 'briefs', 'boxers'):
            return True
        desc = str(it.get('description', '') or '')
        wid = str(it.get('id', '') or '')
    else:
        desc = str(it or '')
        wid = ''
    text = f"{wid} {desc}".lower().replace('_', ' ').replace('-', ' ')
    return bool(_BLACKLISTED_UNDERGARMENT_PATTERN.search(text))


def is_intimate_garment(it: Any) -> bool:
    """General undergarment detection. Sports bras are excluded (allowed as athletic tops)."""
    if isinstance(it, Mapping):
        desc = str(it.get('description', '') or '')
        wid = str(it.get('id', '') or '')
        text = f"{wid} {desc}".lower().replace('_', ' ').replace('-', ' ')
        if _SPORTS_BRA_PATTERN.search(text):
            return False
        if it.get('intimate') is True or it.get('undergarment') is True:
            return True
        category = str(it.get('category', '') or '').lower()
        slot = str(it.get('slot', '') or '').lower()
        if category in ('lingerie', 'underwear', 'undergarment') or slot in ('underwear', 'bra', 'lingerie'):
            return True
    else:
        desc = str(it or '')
        wid = ''
        text = f"{wid} {desc}".lower().replace('_', ' ').replace('-', ' ')
        if _SPORTS_BRA_PATTERN.search(text):
            return False

    return bool(_INTIMATE_GARMENT_PATTERN.search(text))


def filter_wardrobe_items(items: Sequence[Any] | None, stage: int) -> list[Any]:
    """Tiered wardrobe visibility:
    - Stage < 2 (Just Met / Flirting): hides all undergarments; sports bras allowed as athletic tops.
    - Stage 2-3 (Chemistry / Intimacy): shows all wardrobe items EXCEPT blacklisted undergarments.
    - Stage >= 4 (Bonded): shows all wardrobe items without restriction.
    """
    if stage >= 4:
        return list(items or [])
    if stage >= 2:
        return [it for it in (items or []) if not is_blacklisted_undergarment(it)]
    return [it for it in (items or []) if not is_intimate_garment(it)]
