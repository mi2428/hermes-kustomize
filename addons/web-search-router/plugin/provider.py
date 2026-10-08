"""Prefer DDGS, then rotate across five keyed search providers on quota errors."""

import importlib.util
import re
import threading
import time
from typing import Any, Literal, NotRequired, TypedDict, cast

import httpx
from agent.web_search_provider import WebSearchProvider, get_provider_env
from plugins.web.ddgs.provider import DDGSWebSearchProvider


class SearchHit(TypedDict):
    """A search result in Hermes' normalized format."""

    title: str
    url: str
    description: str
    position: int


class SearchData(TypedDict):
    """Successful web results with optional routing provenance."""

    web: list[SearchHit]
    served_by: NotRequired[str]


class SearchSuccess(TypedDict):
    """Successful provider response."""

    success: Literal[True]
    data: SearchData


class SearchError(TypedDict):
    """Failure returned to the Hermes web tool."""

    success: Literal[False]
    error: str


SearchResponse = SearchSuccess | SearchError

_KEYS = {
    "brave": "BRAVE_SEARCH_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "exa": "EXA_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "parallel": "PARALLEL_API_KEY",
}
_FALLBACKS = tuple(_KEYS)
_DDGS_LIMIT = re.compile(
    r"\b429\b|ratelimit|rate[ -]?limit|too many requests", re.IGNORECASE
)


def _fail(message: str) -> SearchError:
    return {"success": False, "error": message}


def _api_search(name: str, query: str, limit: int) -> tuple[SearchResponse, bool]:
    """Return the result and whether a typed HTTP status exhausted this key."""
    key = get_provider_env(_KEYS[name])
    if name == "brave":
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": limit},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            timeout=15,
        )
    else:
        if name == "tavily":
            endpoint = "https://api.tavily.com/search"
            payload = {
                "query": query,
                "max_results": limit,
                "search_depth": "basic",
                "include_raw_content": False,
                "include_images": False,
            }
            headers = {"Authorization": f"Bearer {key}"}
        elif name == "exa":
            endpoint = "https://api.exa.ai/search"
            payload = {"query": query, "type": "instant", "numResults": limit}
            headers = {"Authorization": f"Bearer {key}"}
        elif name == "firecrawl":
            endpoint = "https://api.firecrawl.dev/v2/search"
            payload = {"query": query, "limit": limit}
            headers = {"Authorization": f"Bearer {key}"}
        else:
            endpoint = "https://api.parallel.ai/v1/search"
            payload = {
                "objective": query,
                "search_queries": [query],
                "mode": "turbo",
                "advanced_settings": {"max_results": limit},
            }
            headers = {"x-api-key": key}
        response = httpx.post(endpoint, json=payload, headers=headers, timeout=20)

    exhausted = (
        response.status_code in (402, 429)
        or name == "tavily"
        and response.status_code in (432, 433)
    )
    if response.status_code != 200:
        return _fail(f"{name} search HTTP {response.status_code}"), exhausted
    try:
        data: Any = response.json()
        if (
            not isinstance(data, dict)
            or data.get("success") is False
            or "error" in data
        ):
            raise ValueError("Invalid search response")
        if name == "brave":
            rows: Any = (data.get("web") or {}).get("results", [])
        elif name == "firecrawl":
            rows = data["data"]["web"]
        else:
            rows = data["results"]
        if not isinstance(rows, list) or not all(isinstance(hit, dict) for hit in rows):
            raise TypeError("Invalid search results")
        hits: list[SearchHit] = []
        for i, hit in enumerate(rows[:limit], 1):
            description = (
                hit.get("description")
                if name in ("brave", "firecrawl")
                else hit.get("content")
            )
            if name == "exa":
                description = " ".join(hit.get("highlights") or [])
            if name == "parallel":
                description = " ".join(hit.get("excerpts") or [])
            hits.append(
                {
                    "title": str(hit.get("title") or ""),
                    "url": str(hit.get("url") or ""),
                    "description": str(description or ""),
                    "position": i,
                }
            )
        return {"success": True, "data": {"web": hits}}, False
    except (KeyError, TypeError, ValueError, AttributeError):
        return _fail(f"{name} search returned invalid JSON"), False


class WebSearchRouter(WebSearchProvider):
    """Use DDGS first; keep per-process cooldowns and rotate healthy keyed tiers."""

    name = "web-search-router"
    display_name = "DDGS / keyed free-tier search"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocked_until: dict[str, float] = {}
        self._next = 0

    def is_available(self) -> bool:
        """Refuse a partial pool or an image missing the DDGS dependency."""
        return bool(
            importlib.util.find_spec("ddgs")
            and all(get_provider_env(key) for key in _KEYS.values())
        )

    def search(self, query: str, limit: int = 5) -> SearchResponse:
        """Search DDGS first, failing over only for confirmed rate or quota limits."""
        limit = max(1, min(limit, 20))
        if not self.is_available():
            return _fail("DDGS and all five search API keys are required")

        if not self._blocked("ddgs"):
            result = cast(SearchResponse, DDGSWebSearchProvider().search(query, limit))
            if result["success"] is True:
                return result
            error = result["error"]
            # DDGS mentions possible rate limiting even when only a timeout occurred.
            if "timed out" in error.casefold() and not re.search(
                r"\b429\b|ratelimit", error, re.IGNORECASE
            ):
                return result
            if not _DDGS_LIMIT.search(error):
                return result
            self._burn("ddgs", 300)

        with self._lock:
            start = self._next
            now = time.monotonic()
            order = [
                _FALLBACKS[(start + offset) % len(_FALLBACKS)]
                for offset in range(len(_FALLBACKS))
                if self._blocked_until.get(
                    _FALLBACKS[(start + offset) % len(_FALLBACKS)], 0
                )
                <= now
            ]
            if order:
                self._next = (_FALLBACKS.index(order[0]) + 1) % len(_FALLBACKS)

        for name in order:
            if self._blocked(name):
                continue
            try:
                result, exhausted = _api_search(name, query, limit)
            except httpx.RequestError:
                return _fail(f"{name} search unreachable")
            if result["success"] is True:
                with self._lock:
                    self._next = (_FALLBACKS.index(name) + 1) % len(_FALLBACKS)
                return {
                    "success": True,
                    "data": {"web": result["data"]["web"], "served_by": name},
                }
            if not exhausted:
                return result
            self._burn(name, 3600)
        return _fail("All keyed search providers exhausted; retry later")

    def _blocked(self, name: str) -> bool:
        with self._lock:
            return time.monotonic() < self._blocked_until.get(name, 0)

    def _burn(self, name: str, seconds: int) -> None:
        with self._lock:
            self._blocked_until[name] = max(
                self._blocked_until.get(name, 0), time.monotonic() + seconds
            )
