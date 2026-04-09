from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

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
NAVER_SEARCH_URL = (
    "https://search.naver.com/search.naver?where=news&sort=1&query={query}"
)
ARTICLE_BODY_IDS = {
    "dic_area",
    "articeBody",
    "articleBodyContents",
}
ARTICLE_BODY_CLASSES = {
    "_article_body_contents",
}
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
    "정도",
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
    "합니다",
    "된다",
    "등의",
    "에서",
    "으로",
    "했다며",
    "있는",
}


class NewsCrawlerError(Exception):
    """Raised when news collection or parsing fails."""


def clean_text(text: str) -> str:
    """Normalize whitespace and decode HTML entities."""
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_tags(text: str) -> str:
    """Remove HTML tags from a short fragment."""
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Fetch a web page and return decoded HTML."""
    request = Request(url, headers=DEFAULT_HEADERS)

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return raw.decode(encoding, errors="ignore")
    except (HTTPError, URLError) as error:
        raise NewsCrawlerError(f"Failed to fetch URL: {url}") from error


class NaverSearchParser(HTMLParser):
    """
    Parse current Naver news search HTML.

    Naver search cards expose useful anchors through data-heatmap-target:
    - .nav: Naver news link
    - .tit: original article title link
    - .body: search result preview text
    """

    def __init__(self) -> None:
        super().__init__()
        self.articles: list[dict[str, str]] = []
        self.current_anchor: dict[str, Any] | None = None
        self.current_article: dict[str, str] | None = None
        self.pending_naver_link = ""
        self.seen_links: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "a":
            return

        attr_map = dict(attrs)
        target = attr_map.get("data-heatmap-target")
        href = html.unescape(attr_map.get("href") or "")

        if target in {".nav", ".tit", ".body"} and href.startswith("http"):
            self.current_anchor = {
                "target": target,
                "href": href,
                "text_parts": [],
            }

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
                "link": href,
                "naver_link": self.pending_naver_link,
                "preview_text": "",
                "content": "",
                "summary": "",
            }
            self.pending_naver_link = ""
            return

        if target == ".body" and self.current_article is not None:
            if not self.current_article["preview_text"]:
                self.current_article["preview_text"] = text

    def close(self) -> None:
        super().close()
        self._flush_current_article()

    def _flush_current_article(self) -> None:
        if self.current_article is None:
            return

        article = self.current_article
        self.current_article = None

        if not article["title"] or not article["link"]:
            return

        if article["link"] in self.seen_links:
            return

        self.seen_links.add(article["link"])
        self.articles.append(article)


class ArticleBodyParser(HTMLParser):
    """Extract readable text from a Naver news article page."""

    def __init__(self) -> None:
        super().__init__()
        self.capture_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attr_map = dict(attrs)
        element_id = attr_map.get("id") or ""
        class_names = set((attr_map.get("class") or "").split())
        is_target = (
            element_id in ARTICLE_BODY_IDS
            or bool(ARTICLE_BODY_CLASSES & class_names)
        )

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
    """Fallback parser for pages where the body area cannot be found."""

    def __init__(self) -> None:
        super().__init__()
        self.description = ""

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "meta" or self.description:
            return

        attr_map = dict(attrs)
        name = attr_map.get("name", "")
        prop = attr_map.get("property", "")
        content = attr_map.get("content", "")

        if content and (
            name == "description" or prop == "og:description"
        ):
            self.description = clean_text(content)


def parse_search_results(html_text: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
    """Extract top news cards from Naver news search HTML."""
    parser = NaverSearchParser()
    parser.feed(html_text)
    parser.close()

    filtered_articles = [
        article
        for article in parser.articles
        if article["title"] and article["link"]
    ]
    return filtered_articles[:limit]


def extract_article_text(article_html: str) -> str:
    """Try to extract the article body, then fall back to meta description."""
    parser = ArticleBodyParser()
    parser.feed(article_html)
    parser.close()

    article_text = parser.get_text()
    if is_usable_article_text(article_text):
        return article_text

    meta_parser = MetaDescriptionParser()
    meta_parser.feed(article_html)
    meta_parser.close()
    meta_description = meta_parser.description
    if is_usable_article_text(meta_description):
        return meta_description

    return ""


def looks_like_template_text(text: str) -> bool:
    """Detect broken extraction results that clearly came from page templates."""
    template_markers = ("{{", "}}", "<div", "</", "구독이 완료되었습니다")
    return any(marker in text for marker in template_markers)


def is_usable_article_text(text: str) -> bool:
    """Keep only body text that looks like real article content."""
    if len(text) < 80:
        return False

    if looks_like_template_text(text):
        return False

    low_quality_markers = (
        "구독하고 메인에서 만나보세요",
        "주요 뉴스를 메인에서 만나보세요",
        "기사 본문과 직접 관련 없는",
        "NAVER 뉴스",
    )
    return not any(marker in text for marker in low_quality_markers)


def tokenize(text: str) -> list[str]:
    """Tokenize Korean and English words in a lightweight way."""
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower())


def split_sentences(text: str) -> list[str]:
    """Split text into readable sentences."""
    normalized = clean_text(text)
    if not normalized:
        return []

    pieces = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", normalized)
    sentences = [piece.strip() for piece in pieces if len(piece.strip()) >= 10]

    if sentences:
        return sentences

    if normalized:
        return [normalized]

    return []


def summarize_text(
    text: str,
    keyword: str,
    sentence_count: int = 2,
) -> str:
    """Create a short extractive summary from a body of text."""
    sentences = split_sentences(text)
    if not sentences:
        return ""

    if len(sentences) <= sentence_count:
        return join_summary_sentences(sentences)

    all_tokens = [
        token for token in tokenize(" ".join(sentences)) if token not in STOPWORDS
    ]
    frequencies = Counter(all_tokens)
    keyword_tokens = set(tokenize(keyword))
    scored_sentences: list[tuple[float, int, str]] = []

    for index, sentence in enumerate(sentences):
        sentence_tokens = [
            token for token in tokenize(sentence) if token not in STOPWORDS
        ]
        if not sentence_tokens:
            continue

        score = sum(frequencies[token] for token in sentence_tokens)
        if keyword_tokens & set(sentence_tokens):
            score += 5

        # Light length normalization so very long sentences do not always win.
        score = score / max(len(sentence_tokens), 1)
        scored_sentences.append((score, index, sentence))

    if not scored_sentences:
        return join_summary_sentences(sentences[:sentence_count])

    top_sentences = sorted(
        scored_sentences,
        key=lambda item: (-item[0], item[1]),
    )[:sentence_count]
    top_sentences.sort(key=lambda item: item[1])
    return join_summary_sentences(
        [sentence for _, _, sentence in top_sentences]
    )


def join_summary_sentences(sentences: list[str]) -> str:
    """Join selected sentences and drop a clearly truncated tail fragment."""
    cleaned_sentences = [sentence.strip() for sentence in sentences if sentence.strip()]

    if len(cleaned_sentences) >= 2 and looks_truncated_sentence(cleaned_sentences[-1]):
        cleaned_sentences = cleaned_sentences[:-1]

    return " ".join(cleaned_sentences)


def looks_truncated_sentence(sentence: str) -> bool:
    """Detect preview snippets that end mid-sentence."""
    if not sentence:
        return False

    if sentence.endswith(("...", ".", "!", "?", "…")):
        return False

    return len(sentence) < 40


def build_search_url(keyword: str) -> str:
    """Build the Naver news search URL."""
    return NAVER_SEARCH_URL.format(query=quote_plus(keyword))


def enrich_article_content(article: dict[str, str]) -> dict[str, str]:
    """
    Fill the article content.

    If a Naver news detail page exists, use it because it is easier to parse.
    If not, keep the preview text from the search result page.
    """
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

    article["content"] = content or article["title"]
    return article


def collect_news(keyword: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, str]]:
    """Collect top Naver news results for the given keyword."""
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("keyword is required")

    search_html = fetch_html(build_search_url(keyword))
    articles = parse_search_results(search_html, limit=limit)

    if not articles:
        raise NewsCrawlerError("No news articles were found for the keyword")

    return [enrich_article_content(article) for article in articles]


def build_news_summary(keyword: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """
    Run the full news pipeline up to the final combined summary.

    Returned shape is ready to connect to a later FastAPI endpoint.
    """
    articles = collect_news(keyword, limit=limit)

    for article in articles:
        source_text = article.get("content") or article.get("preview_text") or ""
        article["summary"] = summarize_text(
            text=source_text,
            keyword=keyword,
            sentence_count=2,
        )

    final_source = ". ".join(
        article.get("content") or article.get("preview_text") or ""
        for article in articles
    )
    final_summary = summarize_text(
        text=final_source,
        keyword=keyword,
        sentence_count=3,
    )

    return {
        "keyword": keyword,
        "articles": [
            {
                "title": article["title"],
                "link": article["link"],
                "summary": article["summary"],
            }
            for article in articles
        ],
        "final_summary": final_summary,
    }


def parse_args() -> argparse.Namespace:
    """Parse a keyword for quick local testing."""
    parser = argparse.ArgumentParser(
        description="Collect Naver news and build short summaries.",
    )
    parser.add_argument("keyword", help="News keyword to search")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Number of articles to collect",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    result = build_news_summary(arguments.keyword, limit=arguments.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
