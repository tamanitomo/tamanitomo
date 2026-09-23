Tamanitomo 3.0.11 keeps Hermes updates working on the phones 3.0.10 fixed.

3.0.10 installed Hermes without `nemo-relay` on phones whose kernels Hermes does not recognise as Android. But `hermes update` works out Hermes's dependencies again from scratch, and would have tried to compile that package all over. The installer now leaves a standing instruction for uv, which Hermes uses to update itself, to skip that one package, and sets it everywhere Hermes might update from. An update may mention the package as missing; that is expected, and the update finishes.

The phone also now remembers its Android API level, which any future source build of a Rust package needs.

Already installed on a phone? Run the one-line Android installer again and choose **Upgrade**.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
