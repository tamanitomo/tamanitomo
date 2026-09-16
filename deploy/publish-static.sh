#!/usr/bin/env bash
# Publish the workspace front end to the host that actually serves it.
#
# her.example.com is an nginx container on TamanitomoHost. It proxies /api/ and
# /media/ to the Python app over Tailscale, but serves / and /static/ from its
# own filesystem — a separate copy of kit/app/static. Restarting the app
# therefore ships the backend and nothing a person can see, which is how the
# settings rewrite sat finished and invisible for an afternoon: the API had the
# new endpoints while the browser was still loading a build from lunchtime.
#
# This is the missing half of that deploy. It also checks, because a sync that
# reports success while nginx serves something else is the failure being fixed.
#
#   deploy/publish-static.sh              publish
#   deploy/publish-static.sh --dry-run    show what would change
#   deploy/publish-static.sh --no-backup  skip the snapshot
set -euo pipefail

REMOTE="${COMPANION_STATIC_REMOTE:-tamanitomo-host}"
REMOTE_DIR="${COMPANION_STATIC_DIR:-/mnt/user/appdata/companion-kit/static}"
CONTAINER="${COMPANION_WEB_CONTAINER:-companion-web}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../kit/app/static" && pwd)"

dry_run=0; backup=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --no-backup) backup=0 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say(){ printf '  %s\n' "$*"; }

echo "Publishing $LOCAL_DIR -> $REMOTE:$REMOTE_DIR"

# A file listed in the release manifest but missing locally means a build that
# never ran. Better to stop than to publish half a front end.
for required in index.html product.js product.css settings.js; do
  [ -f "$LOCAL_DIR/$required" ] || { echo "missing $required — nothing published" >&2; exit 1; }
done

if [ "$dry_run" = 1 ]; then
  echo "Would change:"
  rsync -a --itemize-changes --dry-run "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/" | sed 's/^/  /'
  exit 0
fi

if [ "$backup" = 1 ]; then
  stamp="$(date +%Y%m%d-%H%M)"
  # Matches the snapshots already sitting beside it, so the history reads as one
  # sequence rather than two conventions.
  ssh "$REMOTE" "cp -a '$REMOTE_DIR' '$REMOTE_DIR.before-$stamp'"
  say "snapshot: $REMOTE_DIR.before-$stamp"
fi

changed="$(rsync -a --itemize-changes "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/" | grep -v '^\.d' || true)"
if [ -z "$changed" ]; then say "already current"; else printf '%s\n' "$changed" | sed 's/^/  /'; fi

# Verify against the bytes on the serving host, not against what rsync believes
# it sent. This is the check whose absence caused the problem.
echo "Verifying:"
fail=0
for f in index.html settings.js product.js product.css workspace.js studios.js; do
  [ -f "$LOCAL_DIR/$f" ] || continue
  local_sum="$(sha256sum "$LOCAL_DIR/$f" | cut -d' ' -f1)"
  remote_sum="$(ssh "$REMOTE" "sha256sum '$REMOTE_DIR/$f' 2>/dev/null | cut -d' ' -f1" || true)"
  if [ "$local_sum" = "$remote_sum" ]; then say "$f ok"; else say "$f MISMATCH"; fail=1; fi
done

# index.html must actually reference the scripts beside it; a stale index is how
# a correctly-copied settings.js still never loads.
missing="$(ssh "$REMOTE" "grep -o 'static/[a-z-]*\.js' '$REMOTE_DIR/index.html' | sort -u" || true)"
for script in settings.js product.js; do
  printf '%s\n' "$missing" | grep -q "$script" || { say "index.html does not load $script"; fail=1; }
done

# nginx reads through a read-only bind mount; confirm the container sees it too.
if ssh "$REMOTE" "docker inspect '$CONTAINER' >/dev/null 2>&1"; then
  seen="$(ssh "$REMOTE" "docker exec '$CONTAINER' sha256sum /usr/share/nginx/html/settings.js 2>/dev/null | cut -d' ' -f1" || true)"
  [ "$seen" = "$(sha256sum "$LOCAL_DIR/settings.js" | cut -d' ' -f1)" ] \
    && say "$CONTAINER serves the same settings.js" \
    || { say "$CONTAINER does not see the new settings.js"; fail=1; }
fi

[ "$fail" = 0 ] || { echo "Published with problems — see above." >&2; exit 1; }
echo "Published. Reload with cache bypass (Ctrl-Shift-R); index.html is no-store but a loaded tab keeps its old copy."
