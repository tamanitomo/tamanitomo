Tamanitomo 3.0.4 is a small release with one fix that matters to anyone running a recent Hermes.

Every chat turn from the web app failed with `TypeError: run() got an unexpected keyword argument 'emitter'`, while scheduled jobs carried on working perfectly — which makes it look like the web app is broken rather than like two versions disagreeing. The streaming bridge replaces two of Hermes's own functions so a turn can stream its deltas and report its session, and it restated their signatures instead of forwarding what it was given. Hermes 0.21.3 added an argument to one of them and passed it on every call. Both wrappers now forward whatever arrives, so the next argument costs nothing.

That was reported, diagnosed and fixed by **erohtar**, who supplied the traceback, found the cause and wrote the patch. Thank you. It is worth repeating their second point: applying the fix locally made the in-app updater refuse to update, because a file someone has edited is indistinguishable from one the updater must not overwrite. Shipping it is what removes the need for the local edit.

Also fixed: the photo viewer showed nothing at all for any companion other than the first. A URL escaped for placing inside HTML was being assigned straight onto the image instead, where nothing decodes it, so the companion's name reached the server mangled and the file was looked for in somebody else's folder. The access token was being lost the same way, which would have taken viewing from another device with it.

And the viewer's arrows are a hint now rather than furniture: no pill, no border, no blur, appearing only when a pointer is near the picture, and absent entirely on a touchscreen where the swipe is the whole interaction.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
