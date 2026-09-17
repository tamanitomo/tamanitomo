# Third-party notices

tamanitomo itself is licensed under [PolyForm Noncommercial 1.0.0](LICENSE). This file covers
everything third-party that is **included in this repository**, and — separately — the things the
kit talks to or installs for you but does not redistribute.

---

## Included in this repository

### Icons — Feather (MIT) and Lucide (ISC)

The interface icons are inline SVG path data in `kit/app/static/product.js`. Several are the same
geometry as icons from Feather, and from Lucide, which forked from Feather. They are reproduced
here under those licenses.

```
The MIT License (MIT)

Copyright (c) 2013-2023 Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT).
All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

MIT and ISC both permit relicensing the combined work, so the kit's own PolyForm Noncommercial
terms are unaffected. The only obligation is that these notices travel with the code, which is
what this file is for.

No fonts are bundled. The interface uses whatever sans-serif the operating system provides.

---

## Installed or contacted, but not redistributed

Nothing below ships in this repository or in a release archive. The kit downloads these from their
own publishers, on your instruction, or simply talks to them over the network. Their licenses bind
your copy of them, not this project.

| Project | License | Relationship |
| --- | --- | --- |
| [Hermes](https://hermes-agent.nousresearch.com/) | MIT (© 2025 Nous Research) | The agent runtime the kit is built on. Fetched by the official installer at `hermes-agent.nousresearch.com/install.sh`. |
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | GPL-3.0 | Optional image backend. Installed into `companion-engines/comfyui` at your request, and otherwise reached over its HTTP API. No ComfyUI code is copied into this project. |
| [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Supplies `UnetLoaderGGUF`. Only needed if you build a workflow around a `.gguf` model; install it yourself as a ComfyUI custom node. |
| [Ollama](https://ollama.com) | MIT | Optional local model runtime. Official release archives are fetched from `github.com/ollama/ollama/releases`. |
| Model weights (Civitai, Hugging Face, …) | **Per model** | Checkpoints, LoRAs, VAEs and text encoders are downloaded by you, under whatever terms their publisher set. See below. |

**ComfyUI's GPL-3.0 does not reach this project.** The kit generates workflow JSON that names
ComfyUI's node classes and posts it to the API. Interoperating with a program over a network
interface, and naming its node types, does not make this a derivative work of it. If you ever
vendor ComfyUI source into the repository, that changes, and PolyForm Noncommercial would no
longer be compatible.

### Model weights are licensed individually

This matters more than any of the above, because it is the part that varies per download. Many
Civitai models carry terms that restrict commercial use, derivatives, or redistribution, and some
forbid generating images for hire regardless of what license this kit carries. The workflow
downloader reads each model's `allowCommercialUse`, `allowDerivatives`, `allowNoCredit` and
`allowDifferentLicense` flags and shows them before you download. Read the model card as well —
the flags are a summary, not the license.

The kit ships no weights, no LoRAs, no cloned voices and no reference images.

---

## Python dependencies

Installed from PyPI into a local `.venv`; none are vendored, and release archives are source-only.

| Package | License |
| --- | --- |
| PyYAML | MIT |
| tzdata | Apache-2.0 |
| prompt_toolkit | BSD-3-Clause |
| Pillow | MIT-CMU |
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| httpx | BSD-3-Clause |
| websockets | BSD-3-Clause |
| zstandard | BSD-3-Clause |
| pytest | MIT |
| pywinpty (Windows only) | MIT |
| **pyte** | **LGPL-3.0** |

`pyte` drives the embedded terminal view. It is imported as an unmodified library installed
separately by pip, which is the arrangement LGPL-3.0 §4 is written for, and it is never copied
into this repository or into a release archive.

**If you ever ship a bundle that includes `site-packages`** — a frozen executable, an installer, a
ZIP with the virtualenv inside — you would then be distributing `pyte`, and LGPL-3.0 obligations
attach: include its license text and keep the user able to substitute their own build of it.
Today's `./tamanitomo` launcher installs dependencies at runtime, so this does not apply.
