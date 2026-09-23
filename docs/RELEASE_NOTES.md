Tamanitomo 3.0.9 makes running the installer again a way to update.

Until now the Linux and Android installers skipped the download when Tamanitomo was already there, so installing again to fix a problem left the old code, and the problem, in place. Now the installer asks: **upgrade**, which keeps everything and moves to the newest release, or **fresh install**, which sets the old program folder aside and installs a clean copy with a new Python environment. Your companion, your setup answers and your vault live outside the program folder, so neither choice repeats setup.

New installs now get the newest published release rather than the development branch. A checkout with its own code changes is never touched.

On Windows or macOS, update from **Settings → Updates** in the app, or run `git pull` in the Tamanitomo folder.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
