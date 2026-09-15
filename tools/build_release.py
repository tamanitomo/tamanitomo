#!/usr/bin/env python3
"""Build a source-only ZIP. Include files explicitly; never export a profile."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SECRET=re.compile(rb'(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{24,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bAKIA[A-Z0-9]{16}\b)')

def build(output):
    names=json.loads((ROOT/'release-files.json').read_text(encoding='utf-8'))
    if len(names)!=len(set(names)):raise ValueError('Duplicate release path')
    files={}
    for name in names:
        parts=PurePosixPath(name).parts
        if not parts or PurePosixPath(name).is_absolute() or any(p in ('.','..','.git','.env','.venv','__pycache__') for p in parts):
            raise ValueError(f'Unsafe release path: {name}')
        path=ROOT/name
        if any((ROOT.joinpath(*parts[:i])).is_symlink() for i in range(1,len(parts)+1)):
            raise ValueError(f'Release path is a symlink: {name}')
        if not path.is_file() or not path.resolve().is_relative_to(ROOT):raise ValueError(f'Missing or escaping release file: {name}')
        data=path.read_bytes()
        if SECRET.search(data):raise ValueError(f'Likely secret value in {name}; inspect before sharing')
        files[name]=data
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())}
    files['SHA256SUMS.json']=(json.dumps(hashes,indent=2)+'\n').encode()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo('companion-kit/'+name,date_time=(2026,1,1,0,0,0))
            info.create_system=3
            mode=0o755 if name in ('companion','bin/companion') else 0o644
            info.external_attr=(0o100000|mode)<<16
            archive.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED)
    print(f'Built {output.name}: {len(hashes)} source files + integrity manifest')
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/companion-kit.zip')
    build(p.parse_args().output)
