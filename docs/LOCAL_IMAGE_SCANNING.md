# Private image scanning

Open Settings → Media privacy & review → Install local scanner, then choose
Use for this companion. Installation is shared by all profiles on the host; selecting
it changes only the current profile. Installation downloads code and model weights,
never uploads images, and shows progress in the app. Alternatively, set the Media
review provider to `local-nsfw`; the model field is unused.
Both generation and delivery checks run NudeNet 3.4.2's bundled 320n ONNX model in
an isolated CPU process. No image is uploaded and no remote reviewer is used as a
fallback. This detects exposed intimate anatomy, not scene fidelity or clothed
sexual activity. A successful detection is not a guarantee that all sensitive
content was found.

Install on the Hermes host (example for the default Linux home):

```sh
uv venv --python 3.12 ~/.hermes/companion-engines/nsfw/venv
uv pip install --python ~/.hermes/companion-engines/nsfw/venv/bin/python nudenet==3.4.2 onnxruntime==1.30.0 pillow==12.3.0 numpy==2.5.3
```

The package includes the roughly 12 MiB model; runtime never downloads weights.
Profiles share this installation. A cross-process lock serializes scans, each
uses two CPU threads, and each process exits after scanning to release memory.

Exposed breast/genital/anus/buttocks detections of at least 0.5 are labeled NSFW;
0.2–0.5 is unknown. Covered anatomy, faces, bellies and armpits do not trigger
nudity labels. Failed, corrupt or animated-image scans remain unknown. Unknown
images blur by default independently of the NSFW blur preference. The viewer
still allows deliberate reveal and manual correction. Unintended nudity triggers one automatic generation retry with the requested scene
and clothing preserved. Only a scanned-safe replacement supersedes the blurred
original in Photos. The original file is retained; if the retry fails, it remains
visible and blurred. Intentional adult requests and uncertain/failed scans do not
trigger that retry. A failed scan never approves sending.

The 2026-09-11 local evaluation recovered the user's deleted two-person image
from the ComfyUI output directory and verified its original SHA-256. NudeNet
flagged the exposed breasts at 0.817 and 0.808. On 114 unique existing catalog
images, it produced no definite flags and one uncertain flag. This is a smoke
test, not a labeled accuracy benchmark. A separate ViT classifier was rejected
for confidently flagging a fully clothed sleeping portrait.

Source: https://pypi.org/project/nudenet/3.4.2/
