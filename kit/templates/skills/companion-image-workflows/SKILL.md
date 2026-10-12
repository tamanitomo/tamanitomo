---
name: companion-image-workflows
description: Take and send a photo of yourself, and use the companion's saved, structured image workflows without changing identity or confusing model architectures.
---
<!-- tamanitomo managed image workflow guide -->

## Taking and sending a photo

There is one way to take a photo, for a request in chat and for the image timeline alike:

`{{PORTRAIT_CMD}} generate --category portrait --scene "where she is and what she is doing" --wardrobe "what she has on in it" --lighting "the light there" --camera "the framing"`

A photo shows her as the record has her: without `--wardrobe` she is wearing what she is recorded wearing, whatever the scene says, so a shot in something else needs `--wardrobe`. `--feeling` sets the mood. Each flag fills its own node.

A photo of her undressed is `--intimate`, and hers alone to choose once closeness and the user's adult-image setting both allow it; until then the command says not yet, and why. Asked for a photo while the record has her undressed, without either flag, it says what is possible instead of dressing her. A refusal is information for her own answer — decline, tease, send something else — never a reason to claim a setting changed or a fix she did not make.

Its result starts with a `send` line, `MEDIA:/absolute/path`. To send the photo, put that exact line on a line of its own in your reply, as plain text: not inside Markdown image syntax `![...](...)`, which leaves stray text beside the photo. If the command fails or the image is held, say so plainly and do not claim a photo was sent. Never write a `MEDIA:` path the command did not return, and never call the image bridge (`companion_image_provider.py`) yourself; it is internal plumbing.

For an explicit named recipe add `--preset ID`; a wrong ID is answered with the saved ones. Follow image delivery permissions. A generated file is not automatically permission to send it; being asked for a photo is.

The prompt contract separates quality/model triggers, identity, wardrobe, scene, feeling, lighting and camera. Identity follows the appearance section of SOUL unless a recipe has a model-specific override. Change scene/outfit without rewriting identity. With `--scene`, lighting, camera and feeling come only from what you pass, never from the recorded moment, which may be somewhere else entirely; wardrobe defaults to what she is wearing now. In ComfyUI, every named mapping goes to its own node input; only a workflow with a single `prompt` mapping receives the combined prompt. Hosted providers receive the same parts as a labelled brief. Do not copy another companion's face, private prompts, API keys or file paths into a new user's template.

The structured SDXL template uses positive text nodes 101–106, concatenations 111–115, negative 201, latent 301, sampler 302, decode 303 and save 304. Imported recipes may use different IDs: read their saved mappings instead of guessing. Every prompt branch must reach the sampler and final saved image.

Choose architecture before components. SDXL/Pony, SD1.5, Z-Image and Krea use different model/encoder/VAE assumptions. Shared prompt structure does not make their weights interchangeable. Inspect ComfyUI's installed node schema and model card, including LoRA base family and triggers. Unknown compatibility is not verified compatibility.

An image-to-image copy uses LoadImage → resize → VAEEncode → the existing sampler, retaining its conditioning and VAE. Start near 0.35 denoise: lower values preserve composition, higher values change it more. This is not a face-identity adapter or a promise of face consistency in arbitrary new poses. A new image requires both compatible architecture and real generation validation before replacing a working default.

Never fetch a last-used remote graph as this companion's default; it may belong to somebody else. Save separate named copies and leave the user's original working recipe intact.

## Review before delivery

Image generation now reviews the actual output before releasing a successful result. If it says held or review unavailable, do not send the file. Inspect it in Photos and regenerate with a more explicit scene/wardrobe. A safe-sounding prompt does not prove the generated picture is safe. Do not quietly switch to a direct Comfy tool to bypass a held review.

Adult content is released only when closeness and the user's adult-image setting both allow it, and no flag gets around that; being asked for it does not make it her choice. On the photo command that choice is `--intimate`. A casual meal or table portrait does not imply nudity; unintended nudity is a mismatch.

The local scanner has three bands, not two: `safe`, `unknown` (uncertain) and `nsfw`. A mildly suggestive image — lingerie, partial coverage, an ambiguous pose — often lands in `unknown` rather than `nsfw`. Outside an allowed adult render both are held, and one clothed replacement is tried.

For an image made outside the studio, run `{{PORTRAIT_CMD}} review --source /absolute/image/path --scene "the actual intended scene and clothing"` and wait for status `passed` before sending. An adult image passes only under the same rule as above, whatever flag is passed. Review is fallible; use your own visual inspection too. Do not send a held or unreviewed image through another messaging path.

The app lets the user mark safe/NSFW, reveal blurred photos and delete unwanted files. Deleting a vault copy does not remove previously sent Telegram messages or Comfy output copies.
