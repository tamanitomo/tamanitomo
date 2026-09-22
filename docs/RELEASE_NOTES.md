Tamanitomo 3.0.6 fixes the Android installer for anyone whose phone did not already have Python 3.11.

The Android install depends on eighteen packages prebuilt for the phone, because several of Hermes's dependencies are written in Rust and compiling them on a phone takes half an hour when it works at all. Those packages exist for Python 3.11 only. The installer asked Termux for 3.11 in the same breath as seventeen other packages, and apt installs all or nothing, so one unavailable package meant no Python 3.11 and no Rust — and the error was thrown away. It then built the virtualenv on whatever Python was there, pip turned down every prebuilt package without a word, and the install ended in `error running maturin`, under a notice about a new pip that looked like the cause and was not.

Now the packages go in one at a time if they will not go in together, the installer stops with the command to run if Python 3.11 is still missing, and a virtualenv left on the wrong Python by an earlier attempt is rebuilt rather than reused. If pip fails anyway, it says which of the three things maturin needs is absent.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
