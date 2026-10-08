"""Register the opt-in search-only backend without replacing Hermes' tools."""

from typing import Protocol

from agent.web_search_provider import WebSearchProvider

from .provider import WebSearchRouter


class PluginContext(Protocol):
    """The Hermes plugin hook used by this add-on."""

    def register_web_search_provider(self, provider: WebSearchProvider) -> None:
        """Register a search backend with Hermes."""
        ...


def register(ctx: PluginContext) -> None:
    """Register with Hermes' plugin context at discovery time."""
    ctx.register_web_search_provider(WebSearchRouter())
