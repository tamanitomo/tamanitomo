"""Mistral AI provider profile."""

from hermes_cli import __version__ as _HERMES_VERSION
from providers import register_provider
from providers.base import ProviderProfile

mistral = ProviderProfile(
    name="mistral",
    aliases=("mistralai", "mistral-ai"),
    api_mode="chat_completions",
    display_name="Mistral AI",
    description="Mistral AI (frontier & open models, direct API)",
    signup_url="https://console.mistral.ai/",
    env_vars=("MISTRAL_API_KEY",),
    base_url="https://api.mistral.ai/v1",
    models_url="https://api.mistral.ai/v1/models",
    auth_type="api_key",
    supports_vision=True,
    fallback_models=(
        "mistral-large-latest",
        "mistral-medium-latest",
        "mistral-small-latest",
        "ministral-14b-latest",
        "ministral-8b-latest",
        "codestral-latest",
    ),
    default_aux_model="mistral-small-latest",
    default_headers={"User-Agent": f"Hermes-Agent/{_HERMES_VERSION}"},
)

register_provider(mistral)
