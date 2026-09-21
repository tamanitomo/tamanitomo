Tamanitomo 2.4.1 fixes deleting a photo, and makes a render say how far along it is.

Deleting a photo did not delete it. Every picture is saved in two places at once, and the library correctly shows the two as one photo — but deleting it removed only one of them, reported success, and left the other on disk, so the picture came straight back on the next refresh. Deleting a photo now removes the photo. Copies you deliberately kept in an album are still left alone, exactly as the confirmation says.

Pressing Generate on a new version of a moment gave no sign that anything was happening. It now goes through the same status toast as every other long job, which follows you around the site, and carries a wheel that fills as the render progresses — a real step count where the provider reports one, and a turning ring where it does not. If it is waiting behind something else, it says so rather than sitting silent.

A blurred picture stays blurred. The strip of versions under a photo showed every one of them in the clear beneath the blurred picture above it, and picking a version took the blur off — which made it impossible to choose one, or delete it, without first being shown the thing you were trying not to look at. Versions in the strip are blurred like anything else now, and choosing one no longer reveals it. A version that nobody has reviewed yet is treated as unreviewed rather than assumed safe, including a version that has only just been made.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
