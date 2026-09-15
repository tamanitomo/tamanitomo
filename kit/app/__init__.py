"""The local web app: everything the kit knows, in one page you can actually use.

Standalone FastAPI rather than a Hermes plugin, decided in review round 3 for two
reasons. It survives Hermes updates, and the same HTTP API can serve a phone app
later without anything here changing.

It reads the same files the hook reads and writes only what a person owns —
settings, missions, albums, the identity sections that are not locked. It never
writes a file the model owns: not the state ledger, not the SOUL block the
companion writes itself, not any ledger's history. Where the app can change
something, it changes it through the same helper the CLI uses, so there is one
implementation of every rule rather than two that drift.

Binds to localhost by default. Remote access is the user's reverse proxy or
Tailscale, deliberately: this page shows somebody's private life and the kit is
not going to be the thing that puts it on an interface by accident.
"""
