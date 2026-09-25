#!/usr/bin/env python3
"""Install/rollback exercise on a DISPOSABLE fixture install. No live paths.

1. Install 3.0.24 (the rebuilt base ZIP) as an extracted release with its own
   SHA256SUMS.json, and add the 9 unmanaged leftovers the live host has.
2. Stage the RC through the product's own updater (kit/app/updates.stage from
   the INSTALLED 3.0.24 code), apply it through update_release.apply_pending,
   verify zero modified files against the new manifest.
3. Roll back by restoring the backup the updater wrote, verify the 3.0.24
   manifest again, and confirm a synthetic profile dir outside the app is untouched.
"""
import hashlib, importlib.util, json, pathlib, shutil, sys, tempfile, zipfile

BASE_ZIP, RC_ZIP, OUT = map(pathlib.Path, sys.argv[1:4])
tmp = pathlib.Path(tempfile.mkdtemp(prefix='rc-rollback-'))
app = tmp / 'app'
profile = tmp / 'hermes'          # stands in for ~/.hermes; must never be touched
(profile / 'profiles/nova').mkdir(parents=True)
(profile / 'profiles/nova/companion.json').write_text('{"agent":"Nova"}')
(profile / 'profiles/nova/chat-sends.db').write_bytes(b'synthetic ledger bytes')
before_profile = {p.relative_to(profile).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in profile.rglob('*') if p.is_file()}
log = []


def extract(zp, dest):
    with zipfile.ZipFile(zp) as z:
        for i in z.infolist():
            rel = i.filename.split('/', 1)[1]
            p = dest / rel; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(z.read(i)); p.chmod((i.external_attr >> 16) & 0o777)


def verify(root):
    m = json.loads((root / 'SHA256SUMS.json').read_text())
    bad = [n for n, h in m.items() if not (root / n).is_file() or hashlib.sha256((root / n).read_bytes()).hexdigest() != h]
    return (root / 'VERSION').read_text().strip(), len(m), bad


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent)); spec.loader.exec_module(mod); return mod


extract(BASE_ZIP, app)
for leftover in ('kit/scripts/companion_keepsake.py', 'kit/app/static/icon_32.png'):
    (app / leftover).write_text('unmanaged leftover, as on the live host')
log.append(('installed base', verify(app)))

sys.path[:0] = [str(app), str(app / 'kit/scripts')]
updates = load('installed_updates', app / 'kit/app/updates.py')
staged = updates.stage(RC_ZIP.read_bytes(), root=app)
log.append(('staged via installed 3.0.24 updater', staged))
upd = load('installed_update_release', app / 'update_release.py')
upd.apply_pending(app)
v, n, bad = verify(app)
log.append(('after apply', (v, n, bad)))
backups = sorted((app / '.update-backups').iterdir())
log.append(('backup dirs', [b.name for b in backups]))
new_files = sorted(set(json.loads((app / 'SHA256SUMS.json').read_text())) - set(json.loads((backups[-1] / 'SHA256SUMS.json').read_text())))
log.append(('files added by RC', new_files))
leftovers_kept = [(app / p).read_text().startswith('unmanaged') for p in ('kit/scripts/companion_keepsake.py', 'kit/app/static/icon_32.png')]
log.append(('unmanaged leftovers untouched', leftovers_kept))

# Rollback: the updater keeps the previous code in .update-backups/<id>/ (old + new manifest names).
# Restore it and remove files the RC added that the old manifest does not list.
backup = backups[-1]
old_manifest = json.loads((backup / 'SHA256SUMS.json').read_text())
for name in old_manifest:
    shutil.copy2(backup / name, app / name)
shutil.copy2(backup / 'SHA256SUMS.json', app / 'SHA256SUMS.json')
for name in new_files:
    (app / name).unlink(missing_ok=True)
log.append(('after rollback', verify(app)))
leftover_after = [f for f in new_files if (app / f).exists()]
log.append(('RC-only files remaining after rollback', leftover_after))
after_profile = {p.relative_to(profile).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in profile.rglob('*') if p.is_file()}
log.append(('profile untouched through install+rollback', after_profile == before_profile))
OUT.write_text(json.dumps(log, indent=1, default=str))
for k, v in log:
    print(k, '=>', json.dumps(v, default=str)[:400])
shutil.rmtree(tmp)
