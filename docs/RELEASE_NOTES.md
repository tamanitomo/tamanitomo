Tamanitomo 2.3.8 fixes deleting a picture that shares a moment with others.

When a moment holds several renders, switching between them in the viewer repointed at the new picture but kept the previous one's version marker. Every delete that followed described two different files at once and was refused as a conflict, so the picture stayed and nothing said why.

Behind that, a delete that did go through could not finish: the moment was looked up from the picture's own filename, which is not the name of the moment it belongs to, so the file went and the moment carried on listing it.

Both now go through one place. Deleting one render of a moment removes just that render, promotes another to take its place if it was the one on display, and retires the moment only when nothing is left. A record left behind by an earlier failed attempt is tidied rather than refused.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
