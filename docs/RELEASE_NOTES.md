Tamanitomo 3.0.1 makes the reasoning setting mean something, and stops a warning that could never be right.

Background jobs are told how hard to think, and one of the paths that talks to a model was quietly removing that instruction. It began as the retry for a provider that had rejected the request outright — where dropping the unusual fields is the point — and then became the ordinary path for every job that asks for a structured answer. So the workers that most need to think, the ones holding a routine and a wardrobe and a continuity rule in mind at once, were being told not to. They are told properly now.

The accompanying warning was worse than useless. "Did it think?" has three answers, not two: it did, it did not, or the provider does not say. Several providers never report the accounting at all, so a job running exactly as configured was warned about on every single run, under every setting, with nothing that could be changed to silence it — which teaches you to ignore the warning that does mean something. The warning now fires only when a provider actually reports that it did no thinking, and where reasoning cannot be confirmed the jobs page says so rather than leaving the setting looking broken.

### Install

Download **tamanitomo-release.zip** below, extract it into its own application folder, and run the Tamanitomo launcher. Keep your Hermes home and vault outside that folder. The automatically generated GitHub source archives are for development; use the attached release ZIP for in-app updates.
