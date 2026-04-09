from __future__ import annotations

import html
import re
import uuid
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from gtts import gTTS

DEFAULT_TIMEOUT = 10
DEFAULT_LIMIT = 5
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
NAVER_SEARCH_URL = "https://search.naver.com/search.naver?where=news&sort=1&query={query}"
ARTICLE_BODY_IDS = {"dic_area", "articeBody", "articleBodyContents"}
ARTICLE_BODY_CLASSES = {"_article_body_contents"}
BLOCK_TAGS = {"p", "div", "br", "li", "section", "article"}
SKIP_TAGS = {"script", "style", "button", "noscript"}
STOPWORDS = {
    "기자",
    "뉴스",
    "관련",
    "이번",
    "통해",
    "위해",
    "대한",
    "지난",
    "이날",
    "오전",
    "오후",
    "현재",
    "가운데",
    "가장",
    "모습",
    "경우",
    "때문",
    "보도",
    "기사",
    "있다",
    "했다",
    "했다고",
    "있다고",
    "한다",
    "합니다",
    "된다",
    "등의",
    "에서",
    "으로",
    "하며",
    "있는",
}
ORDINALS = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째"]
AUDIO_DIR = Path("backend/data/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class NewsCrawlerError(Exception):
    pass


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def shorten_text(text: str, max_length: int) -> str:
    text = clean_text(text)
    if len(text) <= max_length:
        return text

    shortened = text[:max_length].rstrip()
    last_break = max(shortened.rfind("."), shortened.rfind("!"), shortened.rfind("?"))
    if last_break >= max_length // 2:
        return shortened[: last_break + 1].strip()
    return shortened.rstrip(" ,") + "..."


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return raw.decode(encoding, errors="ignore")
    except (HTTPError, URLError) as error:
        raise NewsCrawlerError(f"Failed to fetch URL: {url}") from error


class NaverSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.articles: list[dict[str, str]] = []
        self.current_anchor: dict[str, Any] | None = None
        self.current_article: dict[str, str] | None = None
        self.pending_naver_link = ""
        self.seen_links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return

        attr_map = dict(attrs)
        target = attr_map.get("data-heatmap-target")
        href = html.unescape(attr_map.get("href") or "")

        if target in {".nav", ".tit", ".body"} and href.startswith("http"):
            self.current_anchor = {"target": target, "href": href, "text_parts": []}

    def handle_data(self, data: str) -> None:
        if self.current_anchor is not None:
            self.current_anchor["text_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self.current_anchor is None:
            return

        target = self.current_anchor["target"]
        href = self.current_anchor["href"]
        text = clean_text("".join(self.current_anchor["text_parts"]))
        self.current_anchor = None

        if target == ".nav":
            self.pending_naver_link = href
            return

        if target == ".tit":
            self._flush_current_article()
            self.current_article = {
                "title": text,
                "url": href,
                "naver_link": self.pending_naver_link,
                "preview_text": "",
                "content": "",
            }
            self.pending_naver_link = ""
            return

        if target == ".body" and self.current_article is not None and not self.current_article["preview_text"]:
            self.current_article["preview_text"] = text

    def close(self) -> None:
        super().close()
        self._flush_current_article()

    def _flush_current_article(self) -> None:
        if self.current_article is None:
            return

        article = self.current_article
        self.current_article = None

        if not article["title"] or not article["url"]:
            return
        if article["url"] in self.seen_links:
            return

        self.seen_links.add(article["url"])
        self.articles.append(article)


class ArticleBodyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        element_id = attr_map.get("id") or ""
        class_names = set((attr_map.get("class") or "").split())
        is_target = element_id in ARTICLE_BODY_IDS or bool(ARTICLE_BODY_CLASSES & class_names)

        if self.capture_depth == 0 and is_target:
            self.capture_depth = 1
            return

        if self.capture_depth > 0:
            if tag in SKIP_TAGS:
                self.skip_depth += 1
                return
            if self.skip_depth > 0:
                self.skip_depth += 1
                return

            self.capture_depth += 1
            if tag in BLOCK_TAGS:
                self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.capture_depth == 0:
            return
        if self.skip_depth > 0:
            self.skip_depth -= 1
            return

        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        self.capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.capture_depth > 0 and self.skip_depth == 0:
            self.parts.append(data)

    def get_text(self) -> str:
        text = clean_text(" ".join(self.parts))
        text = re.sub(r"\[[^\]]+\]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


class MetaDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta" or self.description:
            return

        attr_map = dict(attrs)
        name = attr_map.get("name", "")
        prop = attr_map.get("property", "")
        content = attr_map.get("content", "")
        if content and (name == "description" or prop == "og:description"):
            self.description = clean_text(content)


def looks_like_template_text(text: str) -> bool:
    template_markers = ("{{", "}}", "<div", "</", "구독하고", "NAVER 뉴스")
    return any(marker in text for marker in template_markers)


def is_usable_article_text(text: str) -> bool:
    return len(text) >= 80 and not looks_like_template_text(text)


def extract_article_text(article_html: str) -> str:
    parser = ArticleBodyParser()
    parser.feed(article_html)
    parser.close()

    article_text = parser.get_text()
    if is_usable_article_text(article_text):
        return article_text

    meta_parser = MetaDescriptionParser()
    meta_parser.feed(article_html)
    meta_parser.close()
    if is_usable_article_text(meta_parser.description):
        return meta_parser.description

    return ""


def tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower())


def split_sentences(text: str) -> list[str]:
    normalized = clean_text(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", normalized)
    return [part.strip() for part in parts if len(part.strip()) >= 15]


def summarize_text(text: str, keyword: str, sentence_count: int = 1) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return clean_text(text)
    if len(sentences) <= sentence_count:
        return " ".join(sentences)

    tokens = [token for token in tokenize(" ".join(sentences)) if token not in STOPWORDS]
    frequencies = Counter(tokens)
    keyword_tokens = set(tokenize(keyword))
    scored: list[tuple[float, int, str]] = []

    for index, sentence in enumerate(sentences):
        sentence_tokens = [token for token in tokenize(sentence) if token not in STOPWORDS]
        if not sentence_tokens:
            continue

        score = sum(frequencies[token] for token in sentence_tokens) / len(sentence_tokens)
        if keyword_tokens & set(sentence_tokens):
            score += 3
        scored.append((score, index, sentence))

    if not scored:
        return " ".join(sentences[:sentence_count])

    top_sentences = sorted(scored, key=lambda item: (-item[0], item[1]))[:sentence_count]
    top_sentences.sort(key=lambda item: item[1])
    return " ".join(sentence for _, _, sentence in top_sentences)


def build_search_url(keyword: str) -> str:
    return NAVER_SEARCH_URL.format(query=quote_plus(keyword))


def parse_search_results(html_text: str) -> list[dict[str, str]]:
    parser = NaverSearchParser()
    parser.feed(html_text)
    parser.close()
    return parser.articles[:DEFAULT_LIMIT]


def extract_source_name(article_url: str) -> str:
    host = urlparse(article_url).netloc.lower().replace("www.", "")
    return host or "unknown"


def enrich_article(article: dict[str, str], keyword: str) -> dict[str, str]:
    content = article.get("preview_text", "")
    naver_link = article.get("naver_link", "")

    if naver_link:
        try:
            article_html = fetch_html(naver_link)
            extracted = extract_article_text(article_html)
            if extracted:
                content = extracted
        except NewsCrawlerError:
            pass

    content = content or article["title"]
    article_summary = summarize_text(content, keyword, sentence_count=1)

    article["content"] = content
    article["source"] = extract_source_name(article["url"])
    article["published_at"] = ""
    article["summary"] = shorten_text(article_summary or article["title"], 120)
    return article


def get_news(keyword: str) -> list[dict[str, Any]]:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("keyword is required")

    search_html = fetch_html(build_search_url(keyword))
    articles = parse_search_results(search_html)
    if not articles:
        raise NewsCrawlerError("No news articles were found for the keyword")

    enriched_articles = [enrich_article(article, keyword) for article in articles]
    return [
        {
            "title": article["title"],
            "source": article["source"],
            "url": article["url"],
            "published_at": article["published_at"],
            "snippet": article["summary"],
            "content": article["content"],
        }
        for article in enriched_articles
    ]


def summarize_articles(articles: list[dict[str, Any]]) -> str:
    article_summaries = [article.get("snippet", "") for article in articles if article.get("snippet")]
    combined_text = " ".join(article_summaries)
    summary = summarize_text(combined_text, combined_text, sentence_count=2)
    return shorten_text(summary or combined_text, 130)


def build_tts_script(keyword: str, summary_text: str, articles: list[dict[str, Any]]) -> str:
    parts = [f"{keyword} 기사 요약입니다.", f"전체 요약입니다. {summary_text}"]

    for index, article in enumerate(articles[:DEFAULT_LIMIT]):
        ordinal = ORDINALS[index] if index < len(ORDINALS) else f"{index + 1}번째"
        parts.append(
            f"{ordinal} 기사입니다. 제목은 {article['title']} 입니다. 요약하면, {article['snippet']}"
        )

    return " ".join(parts)


def make_tts(keyword: str, summary_text: str, articles: list[dict[str, Any]]) -> str:
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = AUDIO_DIR / filename
    tts_script = build_tts_script(keyword, summary_text, articles)
    gTTS(text=tts_script, lang="ko").save(output_path)
    return f"/audio/{filename}"
