# Guided image workflows

Open Image Studio → Workflow creator. Configure the ComfyUI endpoint and its installation directory. For another machine, select SSH and use a host alias already configured on the Hermes host. The account must be able to write to ComfyUI’s model directories.

Connect to list installed weights, choose an architecture, and select a checkpoint or diffusion model. Separate model architectures also need a text encoder and VAE. Add LoRAs with individual enable switches and model/CLIP strengths. Family badges prevent known architecture mismatches; existing untagged weights require checking their model card. Pony and Illustrious share SDXL architecture but their training and recommended settings can differ.

The first version supports SDXL, SD 1.5, Z-Image and Krea 2 recipes. Required node classes and installed weight choices are checked against the running ComfyUI instance. It is a guided recipe builder, not a general node editor. Test a preview before setting a generated preset as default.

## Prompt structure

Each recipe has six mapped positive prompt sections: quality/model triggers, identity, wardrobe, scene, lighting and framing (camera). Identity comes from the companion profile when left blank. Negative conditioning is separate. New installations receive the companion-image-workflows skill describing this contract; installing hooks also adds it to existing profiles without overwriting an existing skill.

## Civitai

Paste a https://civitai.com/models/ page, select the version and weight file, then choose its slot. A personal API key is recommended for downloads that require authentication or accepted access terms; configure it under Comfy host and Civitai account. Review the linked model card and license. Keys remain in private installation settings and are omitted from presets and browser responses.

Downloads run on the selected Comfy host, use SafeTensors/GGUF files, check available disk space and the published SHA-256, and refuse to overwrite different files. Completed downloads retain family metadata. Public metadata inspection can work without a key; access-restricted files still need an authorized account. Custom folder symlinks are not supported by this first downloader.

## Image to image

Save a working Comfy preset, then use its image-to-image action. This creates a separate preset, preserving the original model and conditioning. The initial converter supports a single KSampler and VAEDecode with a simple empty latent. Supply a reference image and adjust denoise: lower values retain more of the source; higher values allow more change. The reference is resized and center-cropped to the output dimensions. This is VAE image-to-image, not a face-identity adapter. Complex multi-stage workflows still require manual editing.

## Privacy

Companion-managed Comfy launches include --disable-api-nodes, HF_HUB_DISABLE_TELEMETRY=1 and DO_NOT_TRACK=1. Existing externally managed installations need the same flags in their service configuration. These settings disable supported API-node/frontend network features and opt out of supported telemetry. Independently installed custom nodes can have their own networking behavior; these flags are not a network firewall.
