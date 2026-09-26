"""Derived Vault link index: parsed links, headings, block ids, properties, search text
and safe embeds, incrementally maintained (LINK-01 through LINK-04).

`/api/vault/links/*` registers the health, backlinks+properties (LINK-04) and embed
(LINK-03) routes; the Vault editor's Info panel (vault-editor.js) reads backlinks and
properties from the same route, alongside its own client-side outline. Safe file
operations, link-aware rename, the command palette and a local graph (LINK-05 through
LINK-09) are later work.

Reuses `kit/app/vault.py`'s authorization boundary: `vault.files()` for the walk
(hidden/symlink/secret exclusion already applied per file via `vault.resolve()`), so
this index can never see a path the vault browser itself would refuse to serve.
`kit/scripts/companion_vault_index.py` (the Hermes prompt map) was inspected first, per
LINK-01: its cache is a single rendered STRING for context injection, with no link,
heading-id, property or search-text structure, so nothing here duplicates it -- the
directory-walk-with-exclusion approach it established is reused (through `vault.files`),
its cache file is not.

Storage: one JSON file, `<home>/cache/vault-link-index.json`, keyed by relative path.
Rebuilt incrementally: a note is re-parsed only when its (mtime_ns, size) signature
changed since the last build; removed notes are dropped. This is a cache, never
authoritative storage -- deleting it just costs one full rebuild.

Parsing is a fence- and inline-code-aware line scanner, not a full CommonMark AST
(LINK-02 asks for "parsed syntax nodes with source ranges, not regex replacements
across prose/code"; this delivers the fence/code-span safety that matters for
correctness -- no link or tag is ever extracted from inside a code block or span --
without a bundled Markdown parser dependency). That is a stated, real limitation, not
implied full-parser parity.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import unquote

import yaml

from . import vault
from companion_platform import atomic_write

CACHE_NAME = 'vault-link-index.json'

_FENCE = re.compile(r'^\s*(```|~~~)')
_FRONTMATTER = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n?', re.S)
_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
_BLOCK_ID = re.compile(r'\^([A-Za-z0-9_-]+)\s*$')
_INLINE_TAG = re.compile(r'(?<![\w#/])#([A-Za-z][\w/-]*)')
# [[Note]], [[Note#Heading]], [[Note^block]], [[Note|Label]], and any combination;
# a leading ! marks an embed. Label, heading and block are mutually exclusive in
# practice but the pattern does not enforce ordering beyond Obsidian's own.
_WIKILINK = re.compile(r'(!?)\[\[([^\]|#^]+?)(?:#([^\]|^]+))?(?:\^([A-Za-z0-9_-]+))?(?:\|([^\]]+))?\]\]')
_MDLINK = re.compile(r'(!?)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
_CODE_SPAN = re.compile(r'`[^`]*`')
_EXTERNAL = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*://|^mailto:|^#')


def cache_path(c):
    return c.home / 'cache' / CACHE_NAME


def _strip_code(line, fenced):
    """(cleaned_line_or_None, new_fenced_state). None means "skip this line"."""
    if _FENCE.match(line):
        return None, not fenced
    if fenced:
        return None, fenced
    return _CODE_SPAN.sub('', line), fenced


def parse_frontmatter(text):
    """(properties dict, body). Malformed YAML keeps the note indexed (title/links/
    tags from the body still work) with `_malformed: True` rather than failing closed."""
    m = _FRONTMATTER.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {'_malformed': True}, text[m.end():]
    return (data if isinstance(data, dict) else {}), text[m.end():]


def parse_note(text):
    """Everything the index needs from one note's text. Never reads from disk itself
    (the caller owns I/O), so it is directly unit-testable on a string."""
    props, body = parse_frontmatter(text)
    aliases = props.get('aliases') or []
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = sorted({str(a) for a in aliases if isinstance(a, (str, int, float))})
    tags = set()
    for t in (props.get('tags') or ([props['tags']] if isinstance(props.get('tags'), str) else [])):
        if isinstance(t, str) and t.strip():
            tags.add(t.strip().lstrip('#'))
    headings, block_ids, outbound = [], [], []
    fenced = False
    search_lines = []
    for line in body.splitlines():
        clean, fenced = _strip_code(line, fenced)
        if clean is None:
            continue
        for tm in _INLINE_TAG.finditer(clean):
            tags.add(tm.group(1))
        hm = _HEADING.match(clean)
        if hm:
            headings.append({'level': len(hm.group(1)), 'text': hm.group(2).strip()})
        bm = _BLOCK_ID.search(clean)
        if bm:
            block_ids.append(bm.group(1))
        for wm in _WIKILINK.finditer(clean):
            embed, target, heading, block, label = wm.groups()
            outbound.append({'kind': 'wiki', 'embed': bool(embed), 'target': target.strip(),
                              'heading': (heading or '').strip() or None,
                              'block': (block or '').strip() or None,
                              'label': (label or '').strip() or None})
        for lm in _MDLINK.finditer(clean):
            embed, href = lm.groups()
            if _EXTERNAL.match(href):
                continue
            outbound.append({'kind': 'md', 'embed': bool(embed), 'target': href,
                              'heading': None, 'block': None, 'label': None})
        search_lines.append(clean)
    title = props.get('title') if isinstance(props.get('title'), str) else None
    title = title or (headings[0]['text'] if headings else None)
    return {'title': title, 'aliases': aliases, 'tags': sorted(tags), 'properties': props,
            'headings': headings, 'block_ids': block_ids, 'outbound': outbound,
            'search_text': '\n'.join(search_lines)[:20_000]}


# --- Resolution (LINK-02: aliases/duplicate basenames need a chooser, not a guess) ----

def _basename(rel):
    return Path(rel).stem


def build_lookup(entries):
    by_name, by_alias, by_path = {}, {}, {}
    for rel, e in entries.items():
        by_path[rel.lower()] = rel
        # Both the stem ("Note" for a wikilink to a .md note) and the full filename
        # ("photo.png" for an embed target, which always carries its extension) --
        # a note is normally linked without one, an asset normally with one.
        for key in {_basename(rel).lower(), Path(rel).name.lower()}:
            names = by_name.setdefault(key, [])
            if rel not in names:
                names.append(rel)
        for a in e.get('aliases', ()):
            by_alias.setdefault(a.lower(), []).append(rel)
    return {'by_name': by_name, 'by_alias': by_alias, 'by_path': by_path}


def resolve_wiki(target, lookup):
    """List of candidate relative paths: empty (unresolved), one (resolved), or many
    (ambiguous -- a caller must offer a chooser, never pick the first)."""
    t = target.strip()
    if not t:
        return []
    if '/' in t:
        candidate = t if t.lower().endswith('.md') else t + '.md'
        rel = lookup['by_path'].get(candidate.lower())
        return [rel] if rel else []
    key = t.lower()
    seen, out = set(), []
    for rel in list(lookup['by_alias'].get(key, ())) + list(lookup['by_name'].get(key, ())):
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def resolve_md(href, source_rel, lookup):
    href = unquote(href.split('#', 1)[0])
    if not href:
        return []
    if href.startswith('/'):
        candidate = href.lstrip('/')
    else:
        candidate = os.path.normpath(str(Path(source_rel).parent / href)).replace(os.sep, '/')
    if candidate in ('.', ''):
        return []
    rel = lookup['by_path'].get(candidate.lower())
    return [rel] if rel else []


def resolve(link, source_rel, lookup):
    return resolve_wiki(link['target'], lookup) if link['kind'] == 'wiki' else resolve_md(link['target'], source_rel, lookup)


# --- Embeds (LINK-03: safe, non-recursive depth-1 `![[...]]`) -------------------------

IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}
EMBED_EXCERPT_LIMIT = 4_000


def resolve_asset(c, target):
    """Resolve a non-note embed target (an image, normally linked with its extension) by
    exact filename. A live walk, not index-backed -- LINK-09 is where a large vault's
    asset lookup gets its own cache; this stays correct and simple until then.

    An explicit path (one containing '/') goes through vault.resolve() directly, same as
    every other vault route -- a hidden or traversal target is refused (ValueError), not
    quietly reported as "missing"."""
    target = target.strip()
    if not target:
        return []
    if '/' in target:
        full = vault.resolve(c, target)
        return [target] if full.is_file() else []
    name = target.lower()
    out = []
    for full, rel in vault.files(c):
        if full.suffix.lower() == '.md':
            continue
        if Path(rel).name.lower() == name:
            out.append(rel)
    return out


def heading_section(body, heading):
    """Lines of `body` under a heading matching `heading` (case-insensitive), up to the
    next heading of equal or shallower level. None when no such heading exists."""
    needle = heading.strip().casefold()
    lines = body.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(2).strip().casefold() == needle:
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        return None
    out = []
    for line in lines[start:]:
        m = _HEADING.match(line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return '\n'.join(out).strip()


def resolve_embed(c, raw_target):
    """What a `![[Target]]` or `![[Target#Heading]]` embed should show: an image, a note
    excerpt (whole note, or one heading's section), unresolved, or ambiguous.

    Depth-1 only: any `![[...]]` embed markers inside a returned note excerpt are defanged
    to plain `[[...]]` links (never re-expanded), and the excerpt is length-capped -- an
    embed can never pull in another embed's content, nor an unbounded amount of text."""
    target = raw_target.strip()
    heading = None
    if '#' in target:
        head, _, rest = target.rpartition('#')
        if head.strip():
            target, heading = head.strip(), rest.strip() or None
    if not target:
        return {'kind': 'missing', 'target': raw_target}
    entries, incomplete = build(c)
    lookup = build_lookup(entries)
    note_key = target[:-3] if target.lower().endswith('.md') else target
    note_candidates = resolve_wiki(note_key, lookup)
    asset_candidates = [] if note_candidates else resolve_asset(c, target)
    candidates = note_candidates or asset_candidates
    if len(candidates) > 1:
        return {'kind': 'ambiguous', 'target': raw_target, 'candidates': candidates}
    if not candidates:
        return {'kind': 'missing', 'target': raw_target}
    rel = candidates[0]
    if asset_candidates:
        if Path(rel).suffix.lower() not in IMAGE_EXT:
            return {'kind': 'unsupported', 'target': raw_target, 'path': rel}
        return {'kind': 'image', 'path': rel}
    try:
        full = vault.resolve(c, rel)
        body = full.read_text(encoding='utf-8')
    except (ValueError, OSError, UnicodeError):
        return {'kind': 'missing', 'target': raw_target}
    _, body = parse_frontmatter(body)
    if heading:
        section = heading_section(body, heading)
        if section is None:
            return {'kind': 'missing', 'target': raw_target, 'path': rel}
        excerpt = section
    else:
        excerpt = body.strip()
    truncated = len(excerpt) > EMBED_EXCERPT_LIMIT
    excerpt = excerpt[:EMBED_EXCERPT_LIMIT].replace('![[', '[[')
    return {'kind': 'note', 'path': rel, 'heading': heading, 'excerpt': excerpt, 'truncated': truncated}


# --- Index build (incremental) --------------------------------------------------------

def _read_cache(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data.get('entries', {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def build(c, force=False):
    """(entries, incomplete). Only notes whose (mtime_ns, size) signature changed since
    the cached build are re-parsed; a note this pass could not stat or read leaves its
    previous entry in place (stale, not dropped) and sets `incomplete` -- a transient
    read failure must never make an indexed note vanish from backlinks."""
    path = cache_path(c)
    entries = {} if force else _read_cache(path)
    seen = set()
    changed = force
    incomplete = False
    for full, rel in vault.files(c):
        if full.suffix.lower() != '.md':
            continue
        seen.add(rel)
        try:
            st = full.stat()
        except OSError:
            incomplete = True
            continue
        sig = f'{st.st_mtime_ns}:{st.st_size}'
        prev = entries.get(rel)
        if prev and prev.get('sig') == sig:
            continue
        try:
            text = full.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            incomplete = True
            continue
        entries[rel] = {**parse_note(text), 'sig': sig, 'mtime': st.st_mtime}
        changed = True
    removed = set(entries) - seen
    for rel in removed:
        del entries[rel]
        changed = True
    if changed:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, json.dumps({'entries': entries}, ensure_ascii=False))
        except OSError:
            incomplete = True
    return entries, incomplete


# --- Queries ---------------------------------------------------------------------------

def properties(entries, target_rel):
    """A note's own YAML frontmatter, for the properties panel (LINK-04) -- empty for a
    note not in the index (non-.md, or one this build could not read). `_malformed` is an
    internal marker (see parse_frontmatter), never shown to the panel."""
    note = entries.get(target_rel)
    if not note:
        return {}
    return {k: v for k, v in note.get('properties', {}).items() if k != '_malformed'}


def backlinks(entries, target_rel):
    """Linked references to `target_rel`: only where resolution is UNAMBIGUOUS (LINK-02).
    An ambiguous link that COULD point here is reported separately, never silently
    counted -- a wrong backlink is worse than a missing one."""
    lookup = build_lookup(entries)
    linked, ambiguous = [], []
    for rel, e in entries.items():
        if rel == target_rel:
            continue
        for link in e.get('outbound', ()):
            candidates = resolve(link, rel, lookup)
            if candidates == [target_rel]:
                linked.append({'path': rel, 'label': link.get('label') or link['target'],
                               'embed': link['embed'], 'heading': link.get('heading')})
            elif target_rel in candidates and len(candidates) > 1:
                ambiguous.append({'path': rel, 'label': link.get('label') or link['target'],
                                  'candidates': candidates})
    return {'linked': linked, 'ambiguous': ambiguous}


def unlinked_mentions(entries, target_rel, limit=50):
    """Notes whose plain search text names this note (by title, basename or an alias)
    without an actual resolved link -- optional, surfaced separately (LINK-04)."""
    target = entries.get(target_rel)
    if not target:
        return []
    names = {n.casefold() for n in [target.get('title'), _basename(target_rel), *target.get('aliases', ())] if n}
    linked_paths = {row['path'] for row in backlinks(entries, target_rel)['linked']}
    out = []
    for rel, e in entries.items():
        if rel == target_rel or rel in linked_paths:
            continue
        text = e.get('search_text', '').casefold()
        if any(name in text for name in names):
            out.append({'path': rel})
            if len(out) >= limit:
                break
    return out


def unresolved(entries):
    """(source_path, link) pairs whose target resolves to nothing (LINK-01)."""
    lookup = build_lookup(entries)
    out = []
    for rel, e in entries.items():
        for link in e.get('outbound', ()):
            if not resolve(link, rel, lookup):
                out.append({'path': rel, 'target': link['target'], 'kind': link['kind']})
    return out


def search(entries, query, limit=50):
    needle = (query or '').casefold()
    if not needle:
        return []
    matches = []
    for rel, e in entries.items():
        text = e.get('search_text', '')
        idx = text.casefold().find(needle)
        title = e.get('title') or ''
        if idx < 0 and needle not in rel.casefold() and needle not in title.casefold():
            continue
        excerpt = text[max(0, idx - 80):idx + 200] if idx >= 0 else text[:200]
        matches.append({'path': rel, 'title': title, 'excerpt': excerpt})
        if len(matches) >= limit:
            break
    return matches


def health(c):
    entries, incomplete = build(c)
    return {'notes': len(entries), 'unresolved': len(unresolved(entries)), 'incomplete': incomplete}
