# Wheelhouse for Companion Kit (Android aarch64 / Termux)

This branch contains pre-compiled Python 3.11 binary wheels for Android `aarch64` (Termux), compiled natively on Google Pixel 8 Pro (ARM64-v8a, Cortex-X3/A715/A510).

## Purpose

Termux does not have pre-built `manylinux` or `musllinux` wheels on PyPI for several heavy Rust and C extensions (`firecrawl-anydoc`, `pydantic-core`, `maturin`, `cryptography`, `uvloop`, etc.). Compiling these from source on a phone requires ~150 Rust crates and takes **25–35 minutes** with heavy thermal throttling and battery drain.

With this wheelhouse:
- The installation takes **under 10 seconds** for all binary dependencies.
- Total turnkey setup drops from ~35 minutes to **under 2.5 minutes**.

## Contents

- `wheels/`: Directory containing all `.whl` files.
- `companion-wheels-aarch64.tar.gz`: Tarball containing all wheels for single-stream download.

## License Compliance

All included packages are permissively licensed open source software (MIT, Apache 2.0, BSD-3-Clause, or HPND). See `LICENSE-NOTICE.md` for individual package licenses and attributions.
