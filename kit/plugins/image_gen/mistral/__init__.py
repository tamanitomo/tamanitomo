"""Mistral AI FLUX 1.1 Pro Ultra image generation backend via Conversations API."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO, resolve_aspect_ratio, success_response
from agent.secret_scope import get_secret
from plugins.image_gen._common import (
    StaticImageGenProvider, catalog_rows, error_factory, materialize_image, post_json, prompt_required_error)

logger = logging.getLogger(__name__)

MODELS: Dict[str, Dict[str, Any]] = {
    "flux-1.1-pro-ultra": {
        "display": "FLUX 1.1 Pro Ultra (via Mistral)",
        "speed": "~5-10s",
        "strengths": "Frontier photorealism, typography, and prompt adherence via Mistral Agent",
    },
}
DEFAULT_MODEL = "flux-1.1-pro-ultra"


def _resolve_key() -> str:
    key = get_secret("MISTRAL_API_KEY") or os.environ.get("MISTRAL_API_KEY", "").strip()
    if key:
        return key
    homes = []
    if os.environ.get("HERMES_HOME"):
        homes.append(Path(os.environ["HERMES_HOME"]))
    homes.append(Path.home() / ".hermes")
    for home in homes:
        for env_file in [home / ".env"]:
            try:
                if env_file.is_file():
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("export "):
                            line = line[7:].lstrip()
                        if line.startswith("MISTRAL_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except OSError:
                continue
    return ""


class MistralImageGenProvider(StaticImageGenProvider):
    """Mistral image generation provider using FLUX 1.1 Pro Ultra via Conversations API."""

    provider_id = "mistral"
    label = "Mistral AI (FLUX)"
    models = MODELS
    default_model_id = DEFAULT_MODEL
    setup = dict(
        name="Mistral AI",
        badge="paid",
        tag="FLUX 1.1 Pro Ultra via Mistral Conversations API — uses MISTRAL_API_KEY",
        key="MISTRAL_API_KEY",
        prompt="Mistral API Key",
        url="https://console.mistral.ai/api-keys",
    )

    def is_available(self) -> bool:
        return bool(_resolve_key())

    def list_models(self) -> List[Dict[str, Any]]:
        return catalog_rows(self.models, ("display", "speed", "strengths"))

    def default_model(self) -> Optional[str]:
        return self.default_model_id

    def capabilities(self) -> Dict[str, Any]:
        return {"modalities": ["text"], "max_reference_images": 0}

    def generate(
        self, prompt: str, aspect_ratio: str = DEFAULT_ASPECT_RATIO, *,
        image_url: Optional[str] = None, reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)
        if not prompt:
            return prompt_required_error(self.provider_id, aspect)

        api_key = _resolve_key()
        fail = error_factory(self.provider_id, aspect, model=DEFAULT_MODEL, prompt=prompt)
        if not api_key:
            return fail(
                "MISTRAL_API_KEY not set. Add your Mistral API key in Settings or .env.",
                "auth_required",
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Format prompt with aspect ratio instruction if non-standard
        aspect_text = f" (aspect ratio {aspect})" if aspect and aspect != "1:1" else ""
        payload = {
            "model": "mistral-small-latest",
            "tools": [{"type": "image_generation"}],
            "inputs": [{"role": "user", "content": f"Generate an image: {prompt}{aspect_text}"}],
        }

        result, failure = post_json(
            "https://api.mistral.ai/v1/conversations",
            headers=headers,
            payload=payload,
            timeout=120,
            label="Mistral",
        )
        if failure:
            return fail(failure.error, failure.error_type)

        image_url_found = None
        for entry in (result.get("outputs") or []):
            if entry.get("type") == "tool.execution" and entry.get("name") == "image_generation":
                info = entry.get("info") or {}
                res_str = info.get("result") or "{}"
                try:
                    res_json = json.loads(res_str) if isinstance(res_str, str) else res_str
                    image_url_found = res_json.get("url")
                except Exception:
                    pass
                if image_url_found:
                    break

        if not image_url_found:
            return fail("Mistral returned no image data from image_generation tool", "empty_response")

        image_ref, err = materialize_image(
            None,
            image_url_found,
            prefix="mistral_flux",
            label="Mistral",
            provider=self.provider_id,
            model=DEFAULT_MODEL,
            prompt=prompt,
            aspect=aspect,
            log=logger,
        )
        if err:
            return err

        return success_response(
            image=image_ref,
            model=DEFAULT_MODEL,
            prompt=prompt,
            aspect_ratio=aspect,
            provider=self.provider_id,
            modality="text",
        )


def register(ctx: Any) -> None:
    """Register this provider with the image gen registry."""
    ctx.register_image_gen_provider(MistralImageGenProvider())
