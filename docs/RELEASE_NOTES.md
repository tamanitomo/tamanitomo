Tamanitomo 3.5.0: persistent Chat, a real note editor, and three reported fixes.

- **A chat that stays with you.** Chat is now a persistent page, dock and mobile sheet across
  the app, with live streaming replies and a proper send/recover flow — not just the one-shot
  box from before.
- **A real place to write.** The Vault gets an actual editor: syntax-aware source and reading
  modes, tabs, autosave, and offline/conflict handling that never silently loses a draft.
- **Check-ins stopped waking themselves up.** A background job could keep re-triggering itself
  even when nothing new had happened; it now only wakes for a real conversation.
- **Fewer unnecessary check-ins from wording alone.** The daily/pulse jobs no longer treat a
  reworded (but otherwise identical) scene description as something new to react to.
- **Memory duplication:** the existing protection against writing the same memory twice was
  checked and confirmed working; nothing new needed to ship here.

### What's not in this release

Tool processes a chat turn starts are supervised the same way as before (by process group, not
by a stronger per-attempt boundary), Journal's older Timeline view is still around alongside
the newer Day/Reflection archive, and the Vault editor does not yet have backlinks, a note
graph, or link-aware rename. None of that is silently missing — see CHANGELOG.md for specifics.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run
the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically
generated GitHub source archives are for development; use the attached release ZIP for in-app
updates. See the owner upgrade/rollback guide before updating a live installation with a running
dispatcher.
