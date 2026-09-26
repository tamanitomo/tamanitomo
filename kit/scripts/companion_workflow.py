"""Portable structured Comfy recipes; no companion identity or credentials embedded."""

from __future__ import annotations
import copy
import re

# One node per part of the contract in companion_media.PARTS, in that order.
# `feeling` was absent here, so every workflow built from this template -- and
# every one imported through it -- resolved how she felt on each render and had
# nowhere to put it.
PROMPT_NODES = {
    "quality": "101",
    "identity": "102",
    "wardrobe": "103",
    "scene": "104",
    "feeling": "107",
    "lighting": "105",
    "camera": "106",
}
CONCAT_ORDER = ("102", "103", "104", "107", "105", "106")

# What a new workflow keeps clothed by default. This is the only bucket a
# companion may set aside, and only at full closeness readiness; the always-on
# floor lives in companion_media.SAFETY_FLOOR and is never part of this.
MODESTY_DEFAULT = "nude, topless, nsfw, explicit, nipples, genitalia"


def modular_template():
    """A standard-node SDXL scaffold with stable semantic slots."""
    graph = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "CHOOSE_YOUR_CHECKPOINT.safetensors"},
        },
        "8": {
            "class_type": "CLIPSetLastLayer",
            "inputs": {"clip": ["1", 1], "stop_at_clip_layer": -2},
        },
        "201": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["8", 0], "text": ""},
        },
        "301": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 832, "height": 1216, "batch_size": 1},
        },
        "302": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": [str(110 + len(CONCAT_ORDER)), 0],
                "negative": ["201", 0],
                "latent_image": ["301", 0],
                "seed": 0,
                "steps": 22,
                "cfg": 5.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "303": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["302", 0], "vae": ["1", 2]},
        },
        "304": {
            "class_type": "SaveImage",
            "inputs": {"images": ["303", 0], "filename_prefix": "Companion"},
        },
    }
    for node in PROMPT_NODES.values():
        graph[node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["8", 0], "text": ""},
        }
    for index, node in enumerate(CONCAT_ORDER):
        graph[str(111 + index)] = {
            "class_type": "ConditioningConcat",
            "inputs": {
                "conditioning_to": ["101" if index == 0 else str(110 + index), 0],
                "conditioning_from": [node, 0],
            },
        }
    return {
        "id": "modular-sdxl",
        "name": "Structured SDXL workflow",
        "category": "portrait",
        "provider": "comfyui",
        "endpoint": "http://127.0.0.1:8188",
        "family": "sdxl",
        "parts": {"quality": "high quality, detailed"},
        "negative": "low quality, blurry, malformed hands",
        "modesty_negative": MODESTY_DEFAULT,
        "width": 832,
        "height": 1216,
        "steps": 22,
        "cfg": 5,
        "seed": -1,
        "workflow": graph,
        "mappings": {
            **{k: [v, "text"] for k, v in PROMPT_NODES.items()},
            "negative": ["201", "text"],
            "width": ["301", "width"],
            "height": ["301", "height"],
            "seed": ["302", "seed"],
            "steps": ["302", "steps"],
            "cfg": ["302", "cfg"],
        },
    }


def image_to_image(preset, denoise=0.35):
    """Derive a separate image-to-image recipe, retaining its model and conditioning."""
    if preset.get("provider") != "comfyui":
        raise ValueError("Choose a ComfyUI recipe")
    if (
        isinstance(denoise, bool)
        or not isinstance(denoise, (int, float))
        or not 0 < denoise <= 1
    ):
        raise ValueError("Denoise must be above 0 and at most 1")
    p = copy.deepcopy(preset)
    graph = p.get("workflow", {})
    samplers = [(k, n) for k, n in graph.items() if n.get("class_type") == "KSampler"]
    decoders = [n for n in graph.values() if n.get("class_type") == "VAEDecode"]
    if len(samplers) != 1 or len(decoders) != 1:
        raise ValueError(
            "Automatic conversion requires one KSampler and one VAEDecode; use an architecture-specific template for multi-stage workflows"
        )
    sid, sampler = samplers[0]
    latent = sampler.get("inputs", {}).get("latent_image")
    if not isinstance(latent, list) or graph.get(str(latent[0]), {}).get(
        "class_type"
    ) not in ("EmptyLatentImage", "EmptySD3LatentImage"):
        raise ValueError("This recipe does not begin with a plain empty latent")
    vae = decoders[0]["inputs"].get("vae")
    if not isinstance(vae, list):
        raise ValueError("The decoder must have a connected VAE")
    next_id = max([int(k) for k in graph if str(k).isdigit()] + [400]) + 1
    load, scale, encode = map(str, range(next_id, next_id + 3))
    graph[load] = {
        "class_type": "LoadImage",
        "inputs": {"image": "reference-portrait.png"},
    }
    graph[scale] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": [load, 0],
            "upscale_method": "lanczos",
            "width": p.get("width", 832),
            "height": p.get("height", 1216),
            "crop": "center",
        },
    }
    graph[encode] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": [scale, 0], "vae": copy.deepcopy(vae)},
    }
    sampler["inputs"].update(latent_image=[encode, 0], denoise=float(denoise))
    p.setdefault("mappings", {}).update(
        reference_image=[load, "image"],
        width=[scale, "width"],
        height=[scale, "height"],
        denoise=[sid, "denoise"],
    )
    p.update(
        id=p["id"][:52] + "-img2img",
        name=(p["name"][:75] + " · Image to image"),
        denoise=float(denoise),
        requires_reference=True,
    )
    return p


POWER_LORA_NODE = "Power Lora Loader (rgthree)"


def create_recipe(spec):
    """Build known architectures from explicit slots; never infer family from a filename."""
    import math
    import uuid
    from pathlib import PurePosixPath

    family = spec.get("family", "sdxl")
    if family not in ("sdxl", "sd15", "zimage", "krea2"):
        raise ValueError("Choose a supported architecture")

    def weight(item, label):
        if not isinstance(item, dict):
            raise ValueError("Choose " + label)
        name = item.get("filename", "")
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 300
            or name.startswith("/")
            or "\\" in name
            or ".." in PurePosixPath(name).parts
            or "\0" in name
        ):
            raise ValueError("Choose an installed " + label + " filename")
        tagged = item.get("family", "unknown")
        if tagged not in ("unknown", family):
            raise ValueError(label + " belongs to " + str(tagged) + ", not " + family)
        if tagged == "unknown" and not item.get("confirm_family"):
            raise ValueError(
                "Confirm the model card family for "
                + label
                + "; filename alone is not compatibility evidence"
            )
        return name

    model = weight(spec.get("model"), "model")
    p = modular_template()
    p["family"] = family
    g = p["workflow"]
    p["id"] = "workflow-" + uuid.uuid4().hex[:12]
    name = spec.get("name", "Structured workflow")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Name the workflow")
    p["name"] = name.strip()
    p["parts"]["quality"] = spec.get("quality", "high quality, detailed")
    model_ref = ["1", 0]
    clip_ref = ["8", 0]
    if family in ("sdxl", "sd15"):
        if not model.endswith(".safetensors"):
            raise ValueError("Checkpoint templates require safetensors weights")
        g["1"]["inputs"]["ckpt_name"] = model
        skip = spec.get("clip_skip", -2)
        if isinstance(skip, bool) or not isinstance(skip, int) or not -24 <= skip <= -1:
            raise ValueError("CLIP last layer must be -24 to -1")
        g["8"]["inputs"]["stop_at_clip_layer"] = skip
        if family == "sd15":
            p.update(width=512, height=768, cfg=7.0)
    else:
        encoder = weight(spec.get("clip"), "text encoder")
        vae = weight(spec.get("vae"), "VAE")
        g["1"] = (
            {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": model}}
            if model.endswith(".gguf")
            else {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": model, "weight_dtype": "default"},
            }
        )
        del g["8"]
        g["9"] = {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": encoder,
                "type": "krea2" if family == "krea2" else "lumina2",
                "device": "default",
            },
        }
        g["10"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae}}
        g["307"] = {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": model_ref, "shift": 3.0},
        }
        model_ref = ["307", 0]
        clip_ref = ["9", 0]
        g["301"]["class_type"] = "EmptySD3LatentImage"
        g["303"]["inputs"]["vae"] = ["10", 0]
        p.update(width=1024, height=1024, steps=9, cfg=1.0)
        g["302"]["inputs"].update(sampler_name="dpmpp_2m_sde", scheduler="beta")
    # Settings recovered from a workflow we are adapting. Each is checked the
    # same way a typed one would be; nothing is trusted because it arrived in
    # somebody's PNG.
    for key, low, high in (
        ("steps", 1, 300),
        ("width", 64, 4096),
        ("height", 64, 4096),
    ):
        value = spec.get(key)
        if value is None:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise ValueError(f"{key} must be a whole number between {low} and {high}")
        p[key] = value
    if spec.get("cfg") is not None:
        cfg = spec["cfg"]
        if (
            isinstance(cfg, bool)
            or not isinstance(cfg, (int, float))
            or not math.isfinite(cfg)
            or not 0 <= cfg <= 100
        ):
            raise ValueError("CFG must be between 0 and 100")
        p["cfg"] = float(cfg)
    for key in ("sampler_name", "scheduler"):
        value = spec.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", value):
            raise ValueError("Invalid " + key)
        g["302"]["inputs"][key] = value
    if spec.get("shift") is not None and "307" in g:
        shift = spec["shift"]
        if (
            isinstance(shift, bool)
            or not isinstance(shift, (int, float))
            or not math.isfinite(shift)
            or not 0 < shift <= 100
        ):
            raise ValueError("Sampling shift must be between 0 and 100")
        g["307"]["inputs"]["shift"] = float(shift)
    if spec.get("negative") is not None:
        if not isinstance(spec["negative"], str) or len(spec["negative"]) > 20000:
            raise ValueError("Invalid negative prompt")
        p["negative"] = spec["negative"]

    loras = spec.get("loras", [])
    if not isinstance(loras, list) or len(loras) > 24:
        raise ValueError("At most 24 LoRAs")
    # One stack node when the host has it, a chain of stock loaders when it does
    # not. The stack is what makes a second LoRA a click rather than a rewire,
    # but a lane that will not load on a plain ComfyUI is worse than a verbose
    # one, so the caller says which is available.
    rows = []
    for item in loras:
        if not isinstance(item, dict) or not isinstance(
            item.get("enabled", True), bool
        ):
            raise ValueError("Invalid LoRA slot")
        # A switched-off LoRA is not part of this recipe, so it is neither
        # checked against the family nor carried into the stack. Turning one on
        # later goes through here again.
        if not item.get("enabled", True):
            continue
        filename = weight(item, "LoRA")
        if not filename.endswith(".safetensors"):
            raise ValueError("Use safetensors LoRA weights")
        strengths = {
            key: item.get(key, 1.0) for key in ("strength_model", "strength_clip")
        }
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not -5 <= v <= 5
            for v in strengths.values()
        ):
            raise ValueError("LoRA strengths must be between -5 and 5")
        rows.append((filename, strengths, True))
    if spec.get("lora_stack") and rows:
        # The stack names its rows LORA_1..LORA_n directly in `inputs`, each a
        # record of its own. `strengthTwo` stays null, as the node writes it
        # when a single strength is in use.
        inputs = {"model": model_ref, "clip": clip_ref}
        for index, (filename, strengths, enabled) in enumerate(rows, start=1):
            inputs[f"LORA_{index}"] = {
                "on": enabled,
                "lora": filename,
                "strength": strengths["strength_model"],
                "strengthTwo": None,
            }
        g["500"] = {"class_type": POWER_LORA_NODE, "inputs": inputs}
        model_ref = ["500", 0]
        clip_ref = ["500", 1]
    else:
        for index, (filename, strengths, _) in enumerate(rows):
            node = str(500 + index)
            g[node] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": model_ref,
                    "clip": clip_ref,
                    "lora_name": filename,
                    **strengths,
                },
            }
            model_ref = [node, 0]
            clip_ref = [node, 1]
    for node in [*PROMPT_NODES.values(), "201"]:
        g[node]["inputs"]["clip"] = copy.deepcopy(clip_ref)
    g["302"]["inputs"].update(model=model_ref, steps=p["steps"], cfg=p["cfg"])
    g["301"]["inputs"].update(width=p["width"], height=p["height"])
    p["builder"] = copy.deepcopy(spec)
    return p


SOCKET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN"}
WIDE_NODES = {
    "CLIPTextEncode",
    "CLIPTextEncodeSDXL",
    "String",
    "PrimitiveStringMultiline",
}


def _slot_kind(spec):
    """Whether a declared input is a widget the user types into, or a socket."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return "socket"
    head = spec[0]
    if isinstance(head, list):
        return "widget"
    if isinstance(head, str) and head in SOCKET_TYPES:
        return "widget"
    return "socket"


def _default(spec):
    """What the editor shows in a widget that currently has no value of its own."""
    if (
        isinstance(spec, (list, tuple))
        and len(spec) > 1
        and isinstance(spec[1], dict)
        and "default" in spec[1]
    ):
        return spec[1]["default"]
    head = spec[0] if isinstance(spec, (list, tuple)) and spec else ""
    if isinstance(head, list):
        return head[0] if head else ""
    return {"INT": 0, "FLOAT": 0.0, "BOOLEAN": False}.get(head, "")


def _multiline(spec):
    return bool(
        isinstance(spec, (list, tuple))
        and len(spec) > 1
        and isinstance(spec[1], dict)
        and spec[1].get("multiline")
    )


def interactive_graph(graph, schema, name="Companion workflow"):
    """Rebuild ComfyUI's editor format from an API prompt.

    The API format keeps only what the server needs: a class name, widget values
    and link tuples. The editor additionally needs each node's declared slot
    order, numbered links and positions. Only `/object_info` knows the declared
    order, so the schema is a required argument rather than something guessed
    from the graph — a workflow rebuilt from guesswork opens with its widgets
    shifted by one, which is worse than refusing.
    """
    if not isinstance(graph, dict) or not graph:
        raise ValueError("That workflow has no nodes")
    if not isinstance(schema, dict) or not schema:
        raise ValueError("ComfyUI did not describe its nodes")
    ids = sorted(graph, key=lambda k: (0, int(k)) if str(k).isdigit() else (1, str(k)))
    missing = sorted({graph[i].get("class_type") for i in ids} - set(schema))
    if missing:
        raise ValueError(
            "This ComfyUI has no " + ", ".join(str(m) for m in missing if m)
        )

    plan = {}
    for nid in ids:
        node = graph[nid]
        cls = node.get("class_type")
        entry = schema.get(cls, {}) or {}
        declared = []
        for section in ("required", "optional"):
            for key, spec in (entry.get("input", {}) or {}).get(section, {}).items():
                declared.append((key, spec))
        given = node.get("inputs", {}) or {}
        sockets, widgets, values = [], [], []
        for key, spec in declared:
            supplied = given.get(key)
            linked = (
                isinstance(supplied, list)
                and len(supplied) == 2
                and not isinstance(supplied[0], list)
            )
            kind = _slot_kind(spec)
            if kind == "socket" or linked:
                slot = {
                    "name": key,
                    "type": (
                        spec[0]
                        if isinstance(spec, (list, tuple)) and isinstance(spec[0], str)
                        else "*"
                    ),
                    "link": None,
                }
                if kind == "widget":
                    slot["widget"] = {"name": key}
                sockets.append(slot)
                if kind == "socket":
                    continue
            if kind != "widget":
                continue
            # A widget converted to an input keeps its place in widgets_values;
            # dropping it shifts every later widget by one.
            widgets.append((key, spec))
            values.append(_default(spec) if linked else supplied)
            # ComfyUI pairs every seed with a control widget, whose value sits
            # immediately after the seed.
            if key in ("seed", "noise_seed"):
                values.append("randomize")
        outputs = []
        types = list(entry.get("output", ()) or ())
        names = list(entry.get("output_name", ()) or ())
        for index, otype in enumerate(types):
            outputs.append(
                {
                    "name": names[index] if index < len(names) else str(otype),
                    "type": otype,
                    "links": [],
                    "slot_index": index,
                }
            )
        plan[nid] = {
            "class": cls,
            "sockets": sockets,
            "widgets": widgets,
            "values": values,
            "outputs": outputs,
        }

    links = []
    link_id = 0
    for nid in ids:
        for index, slot in enumerate(plan[nid]["sockets"]):
            supplied = (graph[nid].get("inputs", {}) or {}).get(slot["name"])
            if not (isinstance(supplied, list) and len(supplied) == 2):
                continue
            source, source_slot = str(supplied[0]), int(supplied[1])
            if source not in plan:
                raise ValueError("A node points at missing node " + source)
            link_id += 1
            slot["link"] = link_id
            outs = plan[source]["outputs"]
            if source_slot < len(outs):
                outs[source_slot]["links"].append(link_id)
                wire = outs[source_slot]["type"]
            else:
                wire = slot["type"]
            links.append(
                [
                    link_id,
                    int(source) if source.isdigit() else source,
                    source_slot,
                    int(nid) if nid.isdigit() else nid,
                    index,
                    wire,
                ]
            )

    depth = {}
    visiting = set()

    def rank(nid):
        if nid in depth:
            return depth[nid]
        if nid in visiting:
            raise ValueError("That workflow contains a loop")
        visiting.add(nid)
        upstream = [
            str(v[0])
            for v in (graph[nid].get("inputs", {}) or {}).values()
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in plan
        ]
        depth[nid] = 1 + max((rank(u) for u in upstream), default=-1)
        visiting.discard(nid)
        return depth[nid]

    for nid in ids:
        rank(nid)
    order = sorted(ids, key=lambda n: (depth[n], ids.index(n)))
    column = {}
    nodes = []
    for position, nid in enumerate(order):
        info = plan[nid]
        level = depth[nid]
        row = column.get(level, 0)
        column[level] = row + 1
        tall = sum(4 if _multiline(spec) else 1 for _, spec in info["widgets"])
        width = (
            400
            if info["class"] in WIDE_NODES
            or any(_multiline(s) for _, s in info["widgets"])
            else 280
        )
        height = 46 + 26 * tall + 22 * max(len(info["sockets"]), len(info["outputs"]))
        nodes.append(
            {
                "id": int(nid) if str(nid).isdigit() else nid,
                "type": info["class"],
                "pos": [level * 460, row * (height + 60)],
                "size": [width, height],
                "flags": {},
                "order": position,
                "mode": 0,
                "inputs": info["sockets"],
                "outputs": info["outputs"],
                "properties": {"Node name for S&R": info["class"]},
                "widgets_values": info["values"],
            }
        )

    numeric = [n["id"] for n in nodes if isinstance(n["id"], int)]
    return {
        "id": None,
        "revision": 0,
        "last_node_id": max(numeric, default=0),
        "last_link_id": link_id,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {
            "ds": {"scale": 0.8, "offset": [0, 0]},
            "companion_kit": {"name": name},
        },
        "version": 0.4,
    }
