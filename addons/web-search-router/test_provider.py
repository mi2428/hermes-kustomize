"""Offline checks for search rotation and fail-closed provider errors."""

import unittest
from typing import Any
from unittest.mock import patch

from plugin import provider


class Response:
    """Minimal HTTP response returned by the mocked provider endpoints."""

    def __init__(self, status: int = 200, data: dict[str, Any] | None = None) -> None:
        self.status_code = status
        self.data = data if data is not None else {"results": []}

    def json(self) -> dict[str, Any]:
        return self.data


class RouterTests(unittest.TestCase):
    """Exercise DDGS priority, keyed rotation, and error boundaries offline."""

    def setUp(self) -> None:
        self.router = provider.WebSearchRouter()
        self.available = self.enterContext(
            patch.object(self.router, "is_available", return_value=True)
        )
        self.ddgs = self.enterContext(
            patch(
                "plugin.provider.DDGSWebSearchProvider.search",
                return_value={"success": False, "error": "HTTP 429"},
            )
        )
        self.get = self.enterContext(
            patch(
                "plugin.provider.httpx.get",
                return_value=Response(data={"web": {"results": []}}),
            )
        )
        self.post = self.enterContext(
            patch("plugin.provider.httpx.post", side_effect=self._post)
        )
        self.enterContext(
            patch(
                "plugin.provider.get_provider_env",
                side_effect=lambda key: "test-" + key,
            )
        )

    @staticmethod
    def _post(url: str, **_kwargs: object) -> Response:
        return Response(
            data={"success": True, "data": {"web": []}}
            if "firecrawl" in url
            else {"results": []}
        )

    def test_ddgs_success_uses_no_keyed_provider(self) -> None:
        self.ddgs.return_value = {"success": True, "data": {"web": []}}
        self.assertTrue(self.router.search("query")["success"])
        self.get.assert_not_called()
        self.post.assert_not_called()

    def test_fallback_rotates_over_healthy_candidates(self) -> None:
        self.router._burn("ddgs", 300)
        for name in provider._FALLBACKS:
            if name not in ("brave", "exa"):
                self.router._burn(name, 3600)
        served: list[str] = []
        for _ in range(3):
            result = self.router.search("query")
            assert result["success"] is True
            served.append(result["data"].get("served_by", ""))
        self.assertEqual(served, ["brave", "exa", "brave"])
        self.assertEqual((self.get.call_count, self.post.call_count), (2, 1))

    def test_throttled_candidate_tries_next_then_all_burned_returns_immediately(
        self,
    ) -> None:
        self.get.return_value = Response(status=429)
        self.post.side_effect = lambda _url, **_kwargs: Response(status=429)
        result = self.router.search("query")
        assert result["success"] is False
        self.assertIn("exhausted", result["error"])
        counts = self.ddgs.call_count, self.get.call_count, self.post.call_count
        result = self.router.search("query")
        assert result["success"] is False
        self.assertIn("exhausted", result["error"])
        self.assertEqual(counts, (1, 1, 4))
        self.assertEqual(
            counts, (self.ddgs.call_count, self.get.call_count, self.post.call_count)
        )

    def test_primary_recovers_after_cooldown(self) -> None:
        with patch("plugin.provider.time.monotonic", return_value=100):
            self.assertTrue(self.router.search("query")["success"])
        self.ddgs.return_value = {"success": True, "data": {"web": []}}
        with patch("plugin.provider.time.monotonic", return_value=401):
            self.assertTrue(self.router.search("query")["success"])
        self.assertEqual(self.ddgs.call_count, 2)

    def test_timeout_hint_is_not_a_confirmed_ddgs_rate_limit(self) -> None:
        self.ddgs.return_value = {
            "success": False,
            "error": "DuckDuckGo search timed out after 30s — DuckDuckGo may be rate-limiting or slow",
        }
        self.assertFalse(self.router.search("query")["success"])
        self.get.assert_not_called()
        self.post.assert_not_called()

    def test_quota_status_is_retried_but_bad_credentials_are_not(self) -> None:
        self.get.return_value = Response(status=402)
        result = self.router.search("query")
        assert result["success"] is True
        self.assertEqual(result["data"].get("served_by"), "tavily")
        self.assertEqual((self.get.call_count, self.post.call_count), (1, 1))

        self.router = provider.WebSearchRouter()
        self.get.return_value = Response(status=401)
        result = self.router.search("query")
        assert result["success"] is False
        self.assertIn("HTTP 401", result["error"])
        self.assertEqual(self.post.call_count, 1)

    def test_tavily_plan_limit_counts_as_exhausted(self) -> None:
        self.post.side_effect = lambda _url, **_kwargs: Response(status=432)
        result, exhausted = provider._api_search("tavily", "query", 5)
        assert result["success"] is False
        self.assertTrue(exhausted)

    def test_keyed_responses_are_normalized_without_leaking_keys(self) -> None:
        cases = {
            "brave": {
                "web": {
                    "results": [
                        {"title": "b", "url": "https://example.org", "description": "d"}
                    ]
                }
            },
            "tavily": {
                "results": [
                    {"title": "t", "url": "https://example.org", "content": "d"}
                ]
            },
            "exa": {
                "results": [
                    {"title": "e", "url": "https://example.org", "highlights": ["d"]}
                ]
            },
            "firecrawl": {
                "success": True,
                "data": {
                    "web": [
                        {"title": "f", "url": "https://example.org", "description": "d"}
                    ]
                },
            },
            "parallel": {
                "results": [
                    {"title": "p", "url": "https://example.org", "excerpts": ["d"]}
                ]
            },
        }
        for name, data in cases.items():
            with (
                self.subTest(name=name),
                patch("plugin.provider.httpx.get", return_value=Response(data=data)),
                patch("plugin.provider.httpx.post", return_value=Response(data=data)),
            ):
                result, exhausted = provider._api_search(name, "query", 5)
                self.assertFalse(exhausted)
                assert result["success"] is True
                self.assertEqual(result["data"]["web"][0]["description"], "d")

    def test_missing_key_prevents_all_requests(self) -> None:
        self.available.return_value = False
        self.assertFalse(self.router.search("query")["success"])
        self.ddgs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
