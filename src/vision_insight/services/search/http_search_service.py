"""HTTP-based search service supporting Google, Bing, and Wikipedia."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from vision_insight.models.schemas import SearchResult
from vision_insight.services import SearchService

logger = logging.getLogger(__name__)

# Timeout for external search requests (seconds)
_SEARCH_TIMEOUT = 10.0

# Wikipedia API endpoint
_WIKIPEDIA_API = "https://zh.wikipedia.org/w/api.php"


class HttpSearchService(SearchService):
    """Search service backed by Google Custom Search, Bing, and Wikipedia via httpx."""

    def __init__(
        self,
        google_api_key: str | None = None,
        google_cse_id: str | None = None,
        bing_api_key: str | None = None,
        timeout: float = _SEARCH_TIMEOUT,
    ) -> None:
        self._google_api_key = google_api_key or os.getenv("VIA_GOOGLE_API_KEY", "")
        self._google_cse_id = google_cse_id or os.getenv("VIA_GOOGLE_CSE_ID", "")
        self._bing_api_key = bing_api_key or os.getenv("VIA_BING_API_KEY", "")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: str, source: str = "google") -> list[SearchResult]:
        """Dispatch to the appropriate search backend."""
        if source == "google":
            return await self._search_google(query)
        if source == "bing":
            return await self._search_bing(query)
        if source == "wikipedia":
            return await self._search_wikipedia(query)
        logger.warning("Unsupported search source '%s', falling back to wikipedia", source)
        return await self._search_wikipedia(query)

    async def verify_location(self, keywords: list[str]) -> list[SearchResult]:
        """Verify a location hypothesis by searching multiple sources."""
        query = " ".join(keywords)
        tasks = [
            self._search_google(query),
            self._search_bing(query),
            self._search_wikipedia(query),
        ]
        # Run searches concurrently; swallow individual failures
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[SearchResult] = []
        for result in raw_results:
            if isinstance(result, BaseException):
                logger.warning("Search sub-task failed: %s", result)
                continue
            merged.extend(result)
        # Sort by relevance descending
        merged.sort(key=lambda r: r.relevance, reverse=True)
        return merged

    # ------------------------------------------------------------------
    # Google Custom Search
    # ------------------------------------------------------------------

    async def _search_google(self, query: str) -> list[SearchResult]:
        if not self._google_api_key or not self._google_cse_id:
            logger.debug("Google CSE credentials not configured, skipping")
            return []
        params = {
            "key": self._google_api_key,
            "cx": self._google_cse_id,
            "q": query,
            "num": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Google search failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for item in data.get("items", []):
            results.append(
                SearchResult(
                    query=query,
                    source="google",
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    url=item.get("link", ""),
                    relevance=0.8,  # Google results are generally high-quality
                )
            )
        return results

    # ------------------------------------------------------------------
    # Bing Web Search
    # ------------------------------------------------------------------

    async def _search_bing(self, query: str) -> list[SearchResult]:
        if not self._bing_api_key:
            logger.debug("Bing API key not configured, skipping")
            return []
        headers = {"Ocp-Apim-Subscription-Key": self._bing_api_key}
        params = {"q": query, "count": 5}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Bing search failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for item in data.get("webPages", {}).get("value", []):
            results.append(
                SearchResult(
                    query=query,
                    source="bing",
                    title=item.get("name", ""),
                    snippet=item.get("snippet", ""),
                    url=item.get("url", ""),
                    relevance=0.75,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Wikipedia (no key required)
    # ------------------------------------------------------------------

    async def _search_wikipedia(self, query: str) -> list[SearchResult]:
        """Search Chinese Wikipedia for relevant articles."""
        # Step 1: search for matching titles
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 5,
            "format": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(_WIKIPEDIA_API, params=search_params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Wikipedia search failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            # Strip HTML tags from snippet
            snippet = _strip_html(snippet)
            page_url = f"https://zh.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append(
                SearchResult(
                    query=query,
                    source="wikipedia",
                    title=title,
                    snippet=snippet,
                    url=page_url,
                    relevance=0.6,
                )
            )
        return results


def _strip_html(text: str) -> str:
    """Remove simple HTML tags from a string."""
    import re

    return re.sub(r"<[^>]+>", "", text)
