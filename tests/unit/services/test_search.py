"""Tests for HttpSearchService."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from vision_insight.services.search.http_search_service import HttpSearchService


@pytest.fixture
def service() -> HttpSearchService:
    return HttpSearchService(
        google_api_key="test-key",
        google_cse_id="test-cse",
        bing_api_key="test-bing-key",
    )


@pytest.fixture
def service_no_keys() -> HttpSearchService:
    return HttpSearchService()


# --- Google Search Tests ---


@pytest.mark.asyncio
@respx.mock
async def test_search_google_success(service: HttpSearchService):
    respx.get("https://www.googleapis.com/customsearch/v1").mock(
        return_value=Response(
            200,
            json={
                "items": [
                    {
                        "title": "Tokyo Tower",
                        "snippet": "Famous landmark in Tokyo",
                        "link": "https://example.com",
                    },
                    {
                        "title": "Shibuya 109",
                        "snippet": "Shopping mall in Shibuya",
                        "link": "https://example.com/2",
                    },
                ]
            },
        )
    )
    results = await service.search("Tokyo Tower", source="google")
    assert len(results) == 2
    assert results[0].title == "Tokyo Tower"
    assert results[0].source == "google"
    assert results[0].relevance == 0.8


@pytest.mark.asyncio
@respx.mock
async def test_search_google_http_error(service: HttpSearchService):
    respx.get("https://www.googleapis.com/customsearch/v1").mock(return_value=Response(500))
    results = await service.search("test", source="google")
    assert results == []


@pytest.mark.asyncio
async def test_search_google_no_keys(service_no_keys: HttpSearchService):
    results = await service_no_keys.search("test", source="google")
    assert results == []


# --- Bing Search Tests ---


@pytest.mark.asyncio
@respx.mock
async def test_search_bing_success(service: HttpSearchService):
    respx.get("https://api.bing.microsoft.com/v7.0/search").mock(
        return_value=Response(
            200,
            json={
                "webPages": {
                    "value": [
                        {
                            "name": "Result 1",
                            "snippet": "Snippet 1",
                            "url": "https://example.com/1",
                        },
                    ]
                }
            },
        )
    )
    results = await service.search("test", source="bing")
    assert len(results) == 1
    assert results[0].source == "bing"


@pytest.mark.asyncio
async def test_search_bing_no_key(service_no_keys: HttpSearchService):
    results = await service_no_keys.search("test", source="bing")
    assert results == []


# --- Wikipedia Tests ---


@pytest.mark.asyncio
@respx.mock
async def test_search_wikipedia_success(service: HttpSearchService):
    respx.get("https://zh.wikipedia.org/w/api.php").mock(
        return_value=Response(
            200,
            json={
                "query": {
                    "search": [
                        {"title": "涩谷109", "snippet": "<p>涩谷109是<b>东京</b>的商场</p>"},
                    ]
                }
            },
        )
    )
    results = await service.search("涩谷109", source="wikipedia")
    assert len(results) == 1
    assert results[0].source == "wikipedia"
    assert "<" not in results[0].snippet  # HTML stripped


# --- Verify Location Tests ---


@pytest.mark.asyncio
@respx.mock
async def test_verify_location_merges_sources(service: HttpSearchService):
    respx.get("https://www.googleapis.com/customsearch/v1").mock(
        return_value=Response(
            200, json={"items": [{"title": "G", "snippet": "g", "link": "https://g.com"}]}
        )
    )
    respx.get("https://api.bing.microsoft.com/v7.0/search").mock(
        return_value=Response(
            200,
            json={"webPages": {"value": [{"name": "B", "snippet": "b", "url": "https://b.com"}]}},
        )
    )
    respx.get("https://zh.wikipedia.org/w/api.php").mock(
        return_value=Response(200, json={"query": {"search": [{"title": "W", "snippet": "w"}]}})
    )
    results = await service.verify_location(["Tokyo"])
    assert len(results) == 3
    # Should be sorted by relevance
    assert results[0].relevance >= results[-1].relevance
