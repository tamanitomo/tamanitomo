Tamanitomo 2.9.1 stops capping the context window, and shows the second model call a job makes.

**The window is as large as the model allows.** Nothing should cap it but the person running it. A model reached through a signed-in provider has no endpoint address to look the window up by, and the workaround introduced in the last release picked the smallest measured window for that model — which is a cap by another name. It now takes the largest, ignoring any server on your own network, because a local server is always configured with an address and a same-named model behind one may be an entirely different size. Setting `context_length` yourself is still the only thing that limits it.

**A job that makes two model calls now says so.** Several background jobs run a pre-read before the agent turn, and that pre-read calls a model of its own — chosen from the companion's model tiers rather than from the job. So changing a job's model on the settings page left untouched the call that actually writes her presence. Those jobs now show both calls and which setting governs each.

**A job the app does not recognise is no longer described as harmless.** Anything not part of the companion's own machinery was being filed as "uses a model, nothing private", which is an assertion about a prompt nobody had read. It now says plainly that what it sends depends on the prompt it was given.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
