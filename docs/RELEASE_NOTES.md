Tamanitomo 3.0.10 fixes the Android install on phones with older kernels.

Hermes needs a package called `nemo-relay` on every platform except Android. It tells whether it is on Android by looking for the word "android" in the kernel's version string, and on older phones that word is not there. Those phones were asked to compile nemo-relay from Rust source, which a phone cannot do, and the install stopped with "Failed to build nemo-relay" — before Tamanitomo itself had been downloaded, so there was nothing to run afterwards either.

Hermes works without that package, so the installer now leaves it out on the phone. If an install stopped there, run the one-line Android installer again.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
