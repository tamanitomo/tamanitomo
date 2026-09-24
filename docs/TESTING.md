# Testing

```bash
python -m pytest -q -rs          # everything; -rs lists every skip and why
```

Run it with `hermes` off your `PATH` at least once before a release: a test that
passes only because a real Hermes is installed will fail on a clean runner.

## Browser-script regressions

`tests/*.js` drive the shipped static files inside a Node VM. They are not a
browser. The authoritative runner is pytest:

```bash
python -m pytest -q tests/test_reliability.py::BrowserScriptRegressionTests
```

Without Node these tests skip visibly. With `TAMANITOMO_REQUIRE_NODE=1` (as in
CI) a missing Node fails them. A new `tests/test_*.js` must be added to that class;
a test there fails if one is not.

## CI

`.github/workflows/test.yml` runs on every push and pull request: the full suite
on Linux under Python 3.11, 3.13 and 3.14, and a smaller smoke run (ledgers,
locks, files, browser scripts) on Windows and macOS. It does not gate a release.
`release.yml` runs its own Linux gate.

## Looking at a change in a browser

```bash
python tools/preview_fixture.py --port 38500
```

This serves the workspace against an invented companion in a temporary
directory, with a random token printed once and a fake Hermes. The data is
removed on exit. Use it for screenshots. Never use a live profile, a real vault or
a live access token in fixtures or screenshots.
