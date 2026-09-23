Tamanitomo 3.0.7 lets a companion see everything in her vault.

Until now she knew only the files her continuity happened to mention. A note she wrote a month ago, or a project folder you set up for her, was invisible unless she already knew to look for it. Now each session starts with a map: every note by name under its folder, and the sections inside as many notes as the model's window can carry, newest first. She can open any of them directly.

The map is sent once per session, not on every turn, so it sits in the cached part of the prompt rather than being paid for again with every message. It is sized from the window (a tenth of it, up to twenty-five thousand tokens), and `vault_index_tokens` in `companion.json` sets it by hand or switches it off. A map that had to leave something out says so, and `companion_vault_index.py show <folder>` lists any folder in full.

This release also fixes the continuity hook being registered twice when repair ran under a different Python. Every turn then carried the whole continuity block twice. Run **companion repair** after updating: it removes the duplicate and raises Hermes's hook output limit so the first turn of a session is read in full rather than written to disk.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
