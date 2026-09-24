#!/usr/bin/env python3
"""Format-aware evidence export (review of b94caf2, R4). Tests/evidence tooling only; never shipped.

    python tools/evidence_export.py --out <new dir> --kind executed|derivative \
        --source-note "<where the inputs came from>" [--sub OLD=NEW ...] <input file or dir> ...

Why: the earlier exports redacted by plain text substitution, which wrote a raw `<host>` into
an XML attribute (junit.xml no longer parsed). Here every file is PARSED, redaction is applied
to parsed values, and the result is SERIALISED by the format's own writer, so a placeholder is
escaped wherever it lands. Then every output is re-parsed, JUnit case identities and statuses
are compared input vs output, and MANIFEST.json records the exact bytes written.

`--kind derivative` marks a format-only repair of earlier evidence (NOT a rerun). An input XML
that is already malformed only because an earlier export wrote a raw `="<placeholder>"`
attribute value is repaired by escaping exactly those attribute values before parsing; any
other malformation fails the export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

RAW_PLACEHOLDER_ATTR = re.compile(r'="(<[a-z][a-z0-9-]*>)"')


def substitute(value, subs):
    for old, new in subs:
        value = value.replace(old, new)
    return value


def scrub_json(obj, subs):
    if isinstance(obj, str):
        return substitute(obj, subs)
    if isinstance(obj, list):
        return [scrub_json(v, subs) for v in obj]
    if isinstance(obj, dict):
        return {substitute(k, subs): scrub_json(v, subs) for k, v in obj.items()}
    return obj


def junit_cases(root):
    out = []
    for case in root.iter('testcase'):
        status = 'passed'
        for tag in ('failure', 'error', 'skipped'):
            if case.find(tag) is not None:
                status = tag
        out.append((f"{case.get('classname')}::{case.get('name')}", status))
    return out


def load_xml(text):
    """(root, repaired attribute values). Only the raw-placeholder attribute defect is repaired."""
    try:
        return ET.fromstring(text), []
    except ET.ParseError:
        repaired = RAW_PLACEHOLDER_ATTR.findall(text)
        if not repaired:
            raise
        fixed = RAW_PLACEHOLDER_ATTR.sub(lambda m: '="' + m.group(1).replace('<', '&lt;').replace('>', '&gt;') + '"',
                                         text)
        return ET.fromstring(fixed), sorted(set(repaired))


def export_file(src, dst, subs):
    data = src.read_bytes()
    record = {'source': str(src), 'source_sha256': hashlib.sha256(data).hexdigest(), 'format': None,
              'repaired': [], 'validated': False}
    if src.suffix == '.xml':
        record['format'] = 'xml'
        root, record['repaired'] = load_xml(data.decode('utf-8'))
        before = junit_cases(root)
        for el in root.iter():
            el.attrib.update({k: substitute(v, subs) for k, v in el.attrib.items()})
            if el.text:
                el.text = substitute(el.text, subs)
            if el.tail:
                el.tail = substitute(el.tail, subs)
        out = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        dst.write_bytes(out)
        after = junit_cases(ET.fromstring(out))             # re-parse what was written
        if before != after:
            raise SystemExit(f'{src}: test case identities/statuses changed by the export')
        record['junit_cases'] = len(after)
        record['junit_status_counts'] = {s: sum(1 for _, x in after if x == s) for s in sorted({x for _, x in after})}
    elif src.suffix == '.json':
        record['format'] = 'json'
        obj = scrub_json(json.loads(data.decode('utf-8')), subs)
        dst.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        json.loads(dst.read_text(encoding='utf-8'))
    else:
        record['format'] = 'text'
        dst.write_text(substitute(data.decode('utf-8', errors='replace'), subs), encoding='utf-8')
    record['validated'] = True
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', required=True)
    ap.add_argument('--kind', choices=('executed', 'derivative'), required=True)
    ap.add_argument('--source-note', required=True)
    ap.add_argument('--sub', action='append', default=[], help='OLD=NEW, applied in order')
    ap.add_argument('--forbid', action='append', default=[], help='a string that must not remain in any output')
    ap.add_argument('inputs', nargs='+')
    args = ap.parse_args(argv)
    subs = [tuple(s.split('=', 1)) for s in args.sub]
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    files = {}
    for given in map(pathlib.Path, args.inputs):
        base = given if given.is_dir() else given.parent
        for src in sorted([given] if given.is_file() else [p for p in given.rglob('*') if p.is_file()]):
            rel = pathlib.Path(given.name) / src.relative_to(given) if given.is_dir() else pathlib.Path(src.name)
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            record = export_file(src, dst, subs)
            record['source'] = substitute(str(src), subs)
            files[str(rel)] = record
    leaks = []
    for rel in files:
        text = (out / rel).read_text(encoding='utf-8', errors='replace')
        leaks += [(rel, f) for f in args.forbid if f in text]
    if leaks:
        raise SystemExit(f'forbidden strings remain: {leaks[:5]}')
    for rel, record in files.items():
        data = (out / rel).read_bytes()
        record.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    manifest = {'kind': args.kind, 'source_note': args.source_note,
                'note': ('format-only derivative of earlier evidence: NOT a test rerun' if args.kind == 'derivative'
                         else 'newly executed evidence, sanitised by a format-aware export'),
                'files': files}
    text = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    leaked = [f for f in args.forbid if f in text]
    if leaked:
        raise SystemExit(f'forbidden strings remain in the manifest: {leaked}')
    (out / 'MANIFEST.json').write_text(text, encoding='utf-8')
    print(json.dumps({'out': str(out), 'files': len(files), 'all_validated': all(r['validated'] for r in files.values())}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
