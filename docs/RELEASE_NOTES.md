Tamanitomo 3.0.8 fixes a false warning in `companion doctor`.

The doctor measured the per-turn continuity block including the two markers that fence it, which the budget does not cover. A block written exactly to its budget therefore always showed as "over budget", and the doctor reported itself incomplete on a healthy install. It now measures the block alone.

3.0.7, released just before this, gives each companion a map of the whole vault at the start of every session: every folder, how many notes it holds, and a few of the files that say what it is. If you are updating from 3.0.6 or earlier, run **companion repair** afterwards, which removes a duplicated continuity hook if repair ever ran under a second Python and raises Hermes's hook output limit so the map is read rather than written to disk.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
