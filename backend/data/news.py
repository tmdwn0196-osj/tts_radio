from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT = 20.0
MAX_RESULTS = 5
SEARCH_BATCH_SIZE = 7
MIN_GOOD_RESULTS = 3
SEARCH_TIME_RANGES = ("day", "week")
KOREAN_PRIORITY_DOMAINS = (
    "yna.co.kr",
    "yonhapnewstv.co.kr",
    "newsis.com",
    "news1.kr",
    "mk.co.kr",
    "hankyung.com",
    "sedaily.com",
    "mt.co.kr",
    "edaily.co.kr",
    "asiae.co.kr",
    "fnnews.com",
    "joongang.co.kr",
    "donga.com",
    "chosun.com",
    "biz.chosun.com",
    "hani.co.kr",
    "khan.co.kr",
    "segye.com",
    "kmib.co.kr",
    "kbs.co.kr",
    "imbc.com",
    "sbs.co.kr",
    "ytn.co.kr",
    "zdnet.co.kr",
    "etnews.com",
    "bloter.net",
)


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


def _contains_hangul(text: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def _extract_source_name(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or "unknown"


def _canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return _clean_text(url)

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    normalized_path = parsed.path.rstrip("/") or parsed.path or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            "",
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def _normalize_key(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", _clean_text(text).lower())


def _parse_published_datetime(value: str) -> datetime | None:
    raw = _clean_text(value)
    if not raw:
        return None

    candidates = [
        raw.replace("Z", "+00:00"),
        raw.replace(" UTC", "+00:00"),
    ]
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
    )

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None

        if parsed is None:
            for fmt in formats:
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue

        if parsed is None:
            continue

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return None


def _format_published_at(value: str) -> str:
    parsed = _parse_published_datetime(value)
    if parsed is None:
        return _clean_text(value)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _normalize_article(item: dict[str, Any]) -> dict[str, Any]:
    raw_content = _clean_text(item.get("raw_content"))
    snippet = _clean_text(item.get("content"))
    published_value = (
        item.get("published_date")
        or item.get("published_at")
        or item.get("published")
        or item.get("date")
        or ""
    )

    title = _clean_text(item.get("title"))
    url = _clean_text(item.get("url"))
    content = raw_content or snippet or title
    published_at = _parse_published_datetime(str(published_value))

    return {
        "title": title,
        "url": url,
        "canonical_url": _canonicalize_url(url),
        "source": _extract_source_name(url),
        "published_at": _format_published_at(str(published_value)),
        "snippet": _shorten_text(snippet or content, max_length=240),
        "content": _shorten_text(content, max_length=2200),
        "_published_ts": published_at.timestamp() if published_at else 0.0,
        "_title_key": _normalize_key(title),
    }


def _extract_topic_terms(topic: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\+\.]{1,}|[\uac00-\ud7a3]{2,}", topic.lower())
    ordered_terms = [topic.lower(), *tokens]
    unique_terms: list[str] = []

    for term in ordered_terms:
        normalized = term.strip()
        if normalized and normalized not in unique_terms:
            unique_terms.append(normalized)

    return unique_terms


def _text_matches_term(text: str, term: str) -> bool:
    if not term:
        return False
    if _contains_hangul(term) or " " in term or "-" in term or "+" in term:
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _build_query_variants(topic: str) -> list[str]:
    cleaned_topic = _clean_text(topic)
    if not cleaned_topic:
        return []

    if _contains_hangul(cleaned_topic):
        candidates = [
            cleaned_topic,
            f"{cleaned_topic} \ucd5c\uc2e0 \ub274\uc2a4",
            f"{cleaned_topic} \uc8fc\uc694 \uc774\uc288",
            f"{cleaned_topic} \uad6d\ub0b4 \ub274\uc2a4",
        ]
    else:
        candidates = [
            cleaned_topic,
            f"{cleaned_topic} latest news",
            f"{cleaned_topic} breaking updates",
        ]

    unique_queries: list[str] = []
    for query in candidates:
        normalized = _clean_text(query)
        if normalized and normalized not in unique_queries:
            unique_queries.append(normalized)

    return unique_queries


def _build_search_specs(topic: str) -> list[dict[str, Any]]:
    query_variants = _build_query_variants(topic)
    search_specs: list[dict[str, Any]] = []
    prefer_korean_sources = _contains_hangul(topic)

    for time_range in SEARCH_TIME_RANGES:
        if prefer_korean_sources:
            search_specs.append(
                {
                    "query": query_variants[0],
                    "time_range": time_range,
                    "include_domains": KOREAN_PRIORITY_DOMAINS,
                }
            )

        for query in query_variants:
            search_specs.append(
                {
                    "query": query,
                    "time_range": time_range,
                    "include_domains": None,
                }
            )

    return search_specs


def _search_tavily(
    client: httpx.Client,
    api_key: str,
    query: str,
    time_range: str,
    include_domains: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    payload = {
        "query": query,
        "topic": "news",
        "search_depth": "advanced",
        "max_results": SEARCH_BATCH_SIZE,
        "time_range": time_range,
        "include_raw_content": "text",
        "include_answer": False,
        "include_images": False,
    }
    if include_domains:
        payload["include_domains"] = list(include_domains)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = client.post(TAVILY_API_URL, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise NewsSearchError("Failed to fetch news from Tavily") from error

    results = response.json().get("results", [])
    normalized: list[dict[str, Any]] = []

    for item in results:
        article = _normalize_article(item)
        if not article["title"] or not article["url"]:
            continue
        normalized.append(article)

    return normalized


def _matches_domain(source: str, domain: str) -> bool:
    normalized_source = source.lower()
    normalized_domain = domain.lower()
    return normalized_source == normalized_domain or normalized_source.endswith(f".{normalized_domain}")


def _is_priority_korean_source(source: str) -> bool:
    return any(_matches_domain(source, domain) for domain in KOREAN_PRIORITY_DOMAINS)


def _article_score(
    article: dict[str, Any],
    topic_terms: list[str],
    now_ts: float,
    prefer_korean_sources: bool,
) -> float:
    title_text = article["title"].lower()
    body_text = f"{article['snippet']} {article['content']}".lower()
    combined_text = f"{title_text} {body_text}"

    score = 0.0
    title_matches = sum(1 for term in topic_terms if _text_matches_term(title_text, term))
    body_matches = sum(1 for term in topic_terms if _text_matches_term(body_text, term))
    full_topic_bonus = 6.0 if topic_terms and _text_matches_term(combined_text, topic_terms[0]) else 0.0

    score += title_matches * 7.0
    score += body_matches * 3.0
    score += full_topic_bonus
    score += min(len(article["content"]), 1800) / 180.0
    score += min(len(article["snippet"]), 240) / 120.0

    if prefer_korean_sources:
        if _is_priority_korean_source(article["source"]):
            score += 22.0
        elif article["source"].endswith(".kr"):
            score += 14.0

        if _contains_hangul(article["title"]):
            score += 6.0
        if _contains_hangul(article["snippet"]) or _contains_hangul(article["content"]):
            score += 4.0

    published_ts = float(article.get("_published_ts") or 0.0)
    if published_ts > 0:
        age_hours = max((now_ts - published_ts) / 3600.0, 0.0)
        score += max(0.0, 48.0 - age_hours) * 0.8

    return score


def _strip_internal_fields(article: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(article["title"]),
        "url": str(article["url"]),
        "source": str(article["source"]),
        "published_at": str(article["published_at"]),
        "snippet": str(article["snippet"]),
        "content": str(article["content"]),
    }


def _rank_articles(articles: list[dict[str, Any]], topic: str) -> list[dict[str, str]]:
    if not articles:
        return []

    now_ts = datetime.now(timezone.utc).timestamp()
    topic_terms = _extract_topic_terms(topic)
    prefer_korean_sources = _contains_hangul(topic)
    scored_articles = sorted(
        articles,
        key=lambda article: (
            _article_score(article, topic_terms, now_ts, prefer_korean_sources),
            float(article.get("_published_ts") or 0.0),
            len(article.get("content", "")),
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_sources: set[str] = set()

    for article in scored_articles:
        url_key = article["canonical_url"] or article["url"]
        title_key = article["_title_key"] or _normalize_key(article["title"])
        if url_key in seen_urls or title_key in seen_titles:
            continue
        if article["source"] in seen_sources and len(selected) < MIN_GOOD_RESULTS:
            continue

        selected.append(article)
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        seen_sources.add(article["source"])

        if len(selected) == MAX_RESULTS:
            return [_strip_internal_fields(item) for item in selected]

    for article in scored_articles:
        if len(selected) == MAX_RESULTS:
            break

        url_key = article["canonical_url"] or article["url"]
        title_key = article["_title_key"] or _normalize_key(article["title"])
        if url_key in seen_urls or title_key in seen_titles:
            continue

        selected.append(article)
        seen_urls.add(url_key)
        seen_titles.add(title_key)

    return [_strip_internal_fields(item) for item in selected[:MAX_RESULTS]]


def get_news(topic: str) -> list[dict[str, str]]:
    cleaned_topic = _clean_text(topic)
    if not cleaned_topic:
        raise NewsSearchError("topic is required")

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise NewsSearchError("TAVILY_API_KEY is not configured")

    collected_articles: list[dict[str, Any]] = []
    last_error: NewsSearchError | None = None
    had_success = False

    with httpx.Client(timeout=TAVILY_TIMEOUT) as client:
        for search_spec in _build_search_specs(cleaned_topic):
            try:
                collected_articles.extend(
                    _search_tavily(
                        client,
                        api_key,
                        query=search_spec["query"],
                        time_range=search_spec["time_range"],
                        include_domains=search_spec["include_domains"],
                    )
                )
                had_success = True
            except NewsSearchError as error:
                last_error = error

            ranked_articles = _rank_articles(collected_articles, cleaned_topic)
            if len(ranked_articles) >= MIN_GOOD_RESULTS:
                return ranked_articles

    ranked_articles = _rank_articles(collected_articles, cleaned_topic)
    if ranked_articles:
        return ranked_articles
    if not had_success and last_error is not None:
        raise last_error

    raise NewsSearchError("No recent news articles were found for this topic")
