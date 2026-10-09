"""Web pages read on this machine, for a Tamanitomo companion.

Hermes's `web_extract` hands every page to a reading service (Firecrawl, Tavily,
Exa, Parallel), or, with none set up, to an anonymous free tier. This provider
fetches the page from its own site and turns it into text here instead
(reader.py). Hermes's own checks still run first: no secrets in URLs, no private
addresses (re-checked at connect time and on every redirect by the client used
below), website policy, caching and trimming.

It is used only where a profile names it as `web.extract_backend`, which the kit
does unless another reader was chosen (companion_routing.install). It never offers
itself for anything else: an extract-only provider that looked "available" would be
picked by Hermes's automatic search detection and leave the companion unable to
search at all. Installed and kept current by the kit.
"""

NAME = "tamanitomo-reader"


def register(ctx):
    from agent.web_search_provider import WebSearchProvider

    class LocalReader(WebSearchProvider):
        @property
        def name(self):
            return NAME

        @property
        def display_name(self):
            return "This machine (Tamanitomo)"

        def is_available(self):
            # Selected only by name; see the module docstring.
            return False

        def supports_search(self):
            return False

        def supports_extract(self):
            return True

        async def extract(self, urls, **kwargs):
            from tools.url_safety import create_ssrf_safe_async_client

            from .reader import read

            return await read(urls, client_factory=create_ssrf_safe_async_client)

        def get_setup_schema(self):
            return {
                "name": self.display_name,
                "badge": "free · local",
                "tag": "Reads pages on this machine; no reading service sees them.",
                "env_vars": [],
            }

    ctx.register_web_search_provider(LocalReader())
