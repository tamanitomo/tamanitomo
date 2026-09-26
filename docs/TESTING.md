# Tests

Install the application dependencies, then run the complete domain suite:

```sh
python -m pip install -r requirements.txt
python -m pytest -q
```

The seven collected suites cover presence/settings/platform behavior, evidence
memory, outbox limits, vault files, journals/photos, floating chat, and model
routing/probes. Fixtures use temporary homes and vaults; tests never operate on a
live companion. `tests/support.py` contains fixture helpers, not additional tests.
No legacy suites are hidden behind collection exclusions.

Run the source formatting checks with the development dependencies:

```sh
python -m pip install -r requirements-dev.txt
python -m black --check kit/scripts kit/cli kit/app launch.py update_release.py
python -m ruff check kit/scripts kit/cli kit/app
```

CI runs the full pytest suite on Linux, Windows and macOS. The Linux job also
checks installer syntax. Node is required for browser-script contract tests.

For a manual browser preview, use the synthetic fixture:

```sh
python tools/preview_fixture.py --port 38500
```

The command prints its local URL and temporary token. Its generated profiles,
notes and conversations contain invented data. They are removed when the preview
stops. Check at 390px and 1440px: all five destinations, auxiliary links, vault
editing, dock open/minimize/close, chat streaming, navigation during a reply,
reconnection and profile isolation. A real browser check is separate from pytest;
no browser download or live provider is needed for the fast suite.
