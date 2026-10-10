Tamanitomo 3.7.2: photos that wait for ComfyUI, app helpers that work again, and a companion who knows what she already sent.

- **No paying for photos that cannot render.** The photo timeline is now checked before the model
  runs. If the photo would only be declined (asleep, a private moment, a scene already
  photographed), or the ComfyUI it would use is not answering, the run is skipped and costs
  nothing. The Photos page says photos are paused and since when, and the first run after
  ComfyUI is back takes the picture. Repair adds the check to existing installs.
- **App helpers work again.** The model test in Settings → Models, the studio's Hermes image
  providers, image review and voice in the app had all been losing their request when Hermes
  restarted them under its own Python.
- **She knows what she already sent.** Her context lists what she sent you in the last day, so a
  reply to her photo no longer surprises her when the copy into the conversation failed.
- **Steadier routines.** A damaged line in the time-away list no longer switches her feelings
  off, and a morning another routine already recorded is no longer reported as a failure.

Coming from 3.6? 3.7.0 and 3.7.1 brought cleaner memory (one fact said twice stays one fact; one
day's news does not become a permanent fact; `companion_self.py tidy` for older ledgers), her
own story and what she notices, slower and steadier feelings, chat that follows you across
devices with search, companion backups and resumable setup. See CHANGELOG.md.
