from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT = 30.0
MAX_RESULTS = 5


class NewsSearchError(Exception):
    pass


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _shorten_text(text: str, max_length: int = 280) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= max_length:
        return cleaned

    shortened = cleaned[:max_length].rstrip()
    last_break = max(shortened.rfind("."), shortened.rfind("!"), shortened.rfind("?"))
    if last_break >= max_length // 2:
        shortened = shortened[: last_break + 1]
    return shortened.rstrip(" ,") + "..."


def _extract_source_name(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or "unknown"


def _format_published_at(value: str) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""

    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return raw

    return parsed.strftime("%Y-%m-%d %H:%M")


def _normalize_article(item: dict[str, Any]) -> dict[str, str]:
    raw_content = _clean_text(item.get("raw_content"))
    snippet = _clean_text(item.get("content"))
    published_at = (
        item.get("published_date")
        or item.get("published_at")
        or item.get("published")
        or item.get("date")
        or ""
    )

    title = _clean_text(item.get("title"))
    url = _clean_text(item.get("url"))
    content = raw_content or snippet or title

    return {
        "title": title,
        "url": url,
        "source": _extract_source_name(url),
        "published_at": _format_published_at(str(published_at)),
        "snippet": _shorten_text(snippet or content, max_length=240),
        "content": _shorten_text(content, max_length=2200),
    }


def _build_query(topic: str) -> str:
    return f"{topic} 최신 뉴스"


def _search_tavily(topic: str, time_range: str) -> list[dict[str, str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise NewsSearchError("TAVILY_API_KEY is not configured")

    payload = {
        "query": _build_query(topic),
        "topic": "news",
        "search_depth": "basic",
        "time_range": time_range,
        "max_results": MAX_RESULTS,
        "include_raw_content": "text",
        "include_answer": False,
        "include_images": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(TAVILY_API_URL, headers=headers, json=payload, timeout=TAVILY_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise NewsSearchError("Failed to fetch news from Tavily") from error

    data = response.json()
    results = data.get("results", [])
    normalized: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for item in results:
        article = _normalize_article(item)
        if not article["title"] or not article["url"]:
            continue
        if article["url"] in seen_urls:
            continue
        seen_urls.add(article["url"])
        normalized.append(article)

    return normalized[:MAX_RESULTS]


def get_news(topic: str) -> list[dict[str, str]]:
    cleaned_topic = _clean_text(topic)
    if not cleaned_topic:
        raise NewsSearchError("topic is required")

    articles = _search_tavily(cleaned_topic, time_range="day")
    if len(articles) < 3:
        fallback_articles = _search_tavily(cleaned_topic, time_range="week")
        if len(fallback_articles) > len(articles):
            articles = fallback_articles

    if not articles:
        raise NewsSearchError("No recent news articles were found for this topic")

    return articles
