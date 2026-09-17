---
name: companion-image-workflows
description: Use the companion's saved, structured image workflows without changing identity or confusing model architectures.
---
<!-- tamanitomo managed image workflow guide -->

Use the selected companion's saved Image Studio presets. Generate with:

`{{PORTRAIT_CMD}} generate --category portrait --scene "the requested scene"`

For an explicit named recipe add `--preset ID`. Follow image delivery permissions. A generated file is not automatically permission to send it.

The prompt contract separates quality/model triggers, identity, wardrobe, scene, lighting and camera. Identity follows the appearance section of SOUL unless a recipe has a model-specific override. Change scene/outfit without rewriting identity. Leave unspecified fields to the companion's recorded presence. Do not copy another companion's face, private prompts, API keys or file paths into a new user's template.

The structured SDXL template uses positive text nodes 101–106, concatenations 111–115, negative 201, latent 301, sampler 302, decode 303 and save 304. Imported recipes may use different IDs: read their saved mappings instead of guessing. Every prompt branch must reach the sampler and final saved image.

Choose architecture before components. SDXL/Pony, SD1.5, Z-Image and Krea use different model/encoder/VAE assumptions. Shared prompt structure does not make their weights interchangeable. Inspect ComfyUI's installed node schema and model card, including LoRA base family and triggers. Unknown compatibility is not verified compatibility.

An image-to-image copy uses LoadImage → resize → VAEEncode → the existing sampler, retaining its conditioning and VAE. Start near 0.35 denoise: lower values preserve composition, higher values change it more. This is not a face-identity adapter or a promise of face consistency in arbitrary new poses. A new image requires both compatible architecture and real generation validation before replacing a working default.

Never fetch a last-used remote graph as this companion's default; it may belong to somebody else. Save separate named copies and leave the user's original working recipe intact.

## Review before delivery

Image generation now reviews the actual output before releasing a successful result. If it says held or review unavailable, do not send the file. Inspect it in Photos and regenerate with a more explicit scene/wardrobe. A safe-sounding prompt does not prove the generated picture is safe. Do not quietly switch to a direct Comfy tool to bypass a held review.

Use `--allow-nsfw` when adult content is intentionally part of the requested image — including when the human asked for it in the conversation. A casual meal or table portrait does not imply nudity. Intentional adult content is allowed; unintended nudity is a mismatch.

The companion's `explicit` setting does NOT pass this flag for you. It only shapes prompt wording, so a companion configured for adult content still holds every adult image unless this flag is on the command. If the human asked for something adult and you omit it, the generation fails rather than arriving.

The local scanner has three bands, not two: `safe`, `unknown` (uncertain) and `nsfw`. A mildly suggestive image — lingerie, partial coverage, an ambiguous pose — often lands in `unknown` rather than `nsfw`, so judge by what was *requested*, not by how explicit you expect the output to be. Both `unknown` and `nsfw` need the flag to be released.

For an image made outside the studio, run `{{PORTRAIT_CMD}} review --source /absolute/image/path --scene "the actual intended scene and clothing"` and wait for status `passed` before sending. Add `--allow-nsfw` only for an intentionally adult image. Review is fallible; use your own visual inspection too. Do not send a held or unreviewed image through another messaging path.

The app lets the user mark safe/NSFW, reveal blurred photos and delete unwanted files. Deleting a vault copy does not remove previously sent Telegram messages or Comfy output copies.
