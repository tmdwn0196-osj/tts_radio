from __future__ import annotations

import html
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from gtts import gTTS
from backend.data.llm_summary import openai_is_configured, request_llm_article_summaries

DEFAULT_TIMEOUT = 10
DEFAULT_LIMIT = 5
SEARCH_RESULT_LIMIT = 10
KST = ZoneInfo("Asia/Seoul")
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
NAVER_SEARCH_URL = (
    "https://search.naver.com/search.naver"
    "?where=news"
    "&query={query}"
    "&sort=1"
    "&pd=-1"
    "&photo=0"
    "&field=0"
    "&nso=so:dd,p:all,a:all"
)
ARTICLE_BODY_IDS = {"dic_area", "articleBodyContents", "articeBody"}
ARTICLE_BODY_CLASSES = {
    "_article_body_contents",
    "newsct_article",
    "article_body",
    "article-body",
    "article-view-content-div",
}
BLOCK_TAGS = {"p", "div", "br", "li", "section", "article"}
SKIP_TAGS = {"script", "style", "button", "noscript", "svg", "figure", "figcaption"}
PUBLISHED_META_FIELDS = {
    "article:published_time",
    "og:article:published_time",
    "og:regdate",
    "article:modified_time",
    "pubdate",
    "publishdate",
    "date",
    "dc.date.issued",
    "dc.date.created",
    "parsely-pub-date",
    "citation_publication_date",
    "article.created",
    "article.createdat",
}
STOPWORDS = {
    "기자",
    "뉴스",
    "기사",
    "사진",
    "제공",
    "연합뉴스",
    "뉴시스",
    "이데일리",
    "머니투데이",
    "서울",
    "대해",
    "위해",
    "이번",
    "관련",
    "통해",
    "지난",
    "오늘",
    "오전",
    "오후",
    "현재",
    "이날",
    "정도",
    "경우",
    "때문",
    "있다",
    "했다",
    "한다",
    "이며",
    "대한",
}
NOISY_SENTENCE_MARKERS = {
    "글자크기",
    "이 기사를 공유",
    "본문 내용은",
    "기사 본문 내용은",
    "공유합니다",
    "카카오톡",
    "이메일",
    "기사제보",
    "제보",
    "구독",
    "좋아요",
    "댓글",
    "투표",
    "무단전재",
    "재배포",
    "저작권자",
    "CBS노컷뉴스는 여러분의 제보로",
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


def strip_tags(text: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", text))


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


def looks_like_published_label(text: str) -> bool:
    return bool(
        re.search(
            r"(방금 전|어제|\d+\s*분 전|\d+\s*시간 전|\d+\s*일 전|"
            r"\d{4}[./-]\d{1,2}[./-]\d{1,2}|"
            r"(오전|오후)\s*\d{1,2}:\d{2}|\d{1,2}:\d{2})",
            text,
        )
    )


def parse_published_at(text: str, *, now: datetime | None = None) -> datetime | None:
    value = clean_text(text)
    if not value:
        return None

    current = now or datetime.now(KST)
    lowered = value.lower()

    if lowered == "방금 전":
        return current
    if lowered == "어제":
        return current - timedelta(days=1)

    relative_patterns = (
        (r"(\d+)\s*분 전", "minutes"),
        (r"(\d+)\s*시간 전", "hours"),
        (r"(\d+)\s*일 전", "days"),
    )
    for pattern, unit in relative_patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        amount = int(match.group(1))
        if unit == "minutes":
            return current - timedelta(minutes=amount)
        if unit == "hours":
            return current - timedelta(hours=amount)
        return current - timedelta(days=amount)

    iso_candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)

    compact_match = re.search(r"\b(\d{14}|\d{8})\b", value)
    if compact_match:
        digits = compact_match.group(1)
        fmt = "%Y%m%d%H%M%S" if len(digits) == 14 else "%Y%m%d"
        return datetime.strptime(digits, fmt).replace(tzinfo=KST)

    date_match = re.search(
        r"(\d{4})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})\.?"
        r"(?:\s*((?:오전|오후))?\s*(\d{1,2}):(\d{2}))?",
        value,
    )
    if date_match:
        year, month, day, meridiem, hour_text, minute_text = date_match.groups()
        hour = int(hour_text or 0)
        minute = int(minute_text or 0)
        if meridiem == "오후" and hour < 12:
            hour += 12
        if meridiem == "오전" and hour == 12:
            hour = 0
        return datetime(
            int(year),
            int(month),
            int(day),
            hour,
            minute,
            tzinfo=KST,
        )

    time_only_match = re.search(r"((?:오전|오후))\s*(\d{1,2}):(\d{2})", value)
    if time_only_match:
        meridiem, hour_text, minute_text = time_only_match.groups()
        hour = int(hour_text)
        minute = int(minute_text)
        if meridiem == "오후" and hour < 12:
            hour += 12
        if meridiem == "오전" and hour == 12:
            hour = 0
        return current.replace(hour=hour, minute=minute, second=0, microsecond=0)

    time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", value)
    if time_match:
        hour, minute = map(int, time_match.groups())
        return current.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return None


def format_published_at(published_at: datetime | None, fallback: str = "") -> str:
    if published_at is None:
        return fallback
    return published_at.astimezone(KST).strftime("%Y-%m-%d %H:%M")


class NaverSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.articles: list[dict[str, Any]] = []
        self.current_anchor: dict[str, Any] | None = None
        self.current_article: dict[str, Any] | None = None
        self.pending_naver_link = ""
        self.pending_meta_texts: list[str] = []
        self.profile_subtext_depth = 0
        self.profile_subtext_parts: list[str] = []
        self.skip_depth = 0
        self.seen_links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth > 0:
            self.skip_depth += 1
            return

        attr_map = dict(attrs)
        class_names = set((attr_map.get("class") or "").split())

        if "sds-comps-profile-info-subtexts" in class_names:
            self.profile_subtext_depth = 1
            self.profile_subtext_parts = []
            return
        if self.profile_subtext_depth > 0:
            self.profile_subtext_depth += 1

        if tag != "a":
            return

        target = attr_map.get("data-heatmap-target")
        href = html.unescape(attr_map.get("href") or "")
        if target in {".nav", ".tit", ".body"} and href.startswith("http"):
            self.current_anchor = {"target": target, "href": href, "text_parts": []}

    def handle_data(self, data: str) -> None:
        if self.skip_depth > 0:
            return
        if self.current_anchor is not None:
            self.current_anchor["text_parts"].append(data)
            return
        if self.profile_subtext_depth > 0:
            cleaned = clean_text(data)
            if cleaned:
                self.profile_subtext_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth > 0:
            self.skip_depth -= 1
            return

        if self.profile_subtext_depth > 0:
            self.profile_subtext_depth -= 1
            if self.profile_subtext_depth == 0:
                self._consume_profile_subtexts()

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
                "published_at": self._pick_published_text(),
                "published_dt": parse_published_at(self._pick_published_text()),
            }
            self.pending_naver_link = ""
            self.pending_meta_texts = []
            return

        if target == ".body" and self.current_article is not None and not self.current_article["preview_text"]:
            self.current_article["preview_text"] = strip_tags(text)

    def close(self) -> None:
        super().close()
        self._flush_current_article()

    def _consume_profile_subtexts(self) -> None:
        for text in self.profile_subtext_parts:
            if text not in self.pending_meta_texts:
                self.pending_meta_texts.append(text)
        self.profile_subtext_parts = []

    def _pick_published_text(self) -> str:
        for text in reversed(self.pending_meta_texts):
            if looks_like_published_label(text):
                return text
        return ""

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


class ArticleMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description = ""
        self.published_candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)

        if tag == "meta":
            content = clean_text(attr_map.get("content") or "")
            name = (attr_map.get("name") or "").lower()
            prop = (attr_map.get("property") or "").lower()
            itemprop = (attr_map.get("itemprop") or "").lower()

            if content and not self.description and (name == "description" or prop == "og:description"):
                self.description = content

            keys = {name, prop, itemprop}
            if content and keys & PUBLISHED_META_FIELDS:
                self.published_candidates.append(content)

        if tag == "time":
            datetime_attr = clean_text(attr_map.get("datetime") or attr_map.get("content") or "")
            if datetime_attr:
                self.published_candidates.append(datetime_attr)


def looks_like_template_text(text: str) -> bool:
    template_markers = ("{{", "}}", "<div", "</", "구독", "NAVER 뉴스")
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

    meta_parser = ArticleMetaParser()
    meta_parser.feed(article_html)
    meta_parser.close()
    if is_usable_article_text(meta_parser.description):
        return meta_parser.description

    return ""


def extract_article_published_at(article_html: str) -> datetime | None:
    meta_parser = ArticleMetaParser()
    meta_parser.feed(article_html)
    meta_parser.close()

    for candidate in meta_parser.published_candidates:
        published_at = parse_published_at(candidate)
        if published_at is not None:
            return published_at
    return None


def tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower())


def split_sentences(text: str) -> list[str]:
    normalized = strip_tags(text)
    if not normalized:
        return []

    parts = re.split(r"(?<=[.!?])\s+|(?<=…)\s+", normalized)
    sentences = [part.strip(" \"'") for part in parts if len(part.strip()) >= 20]
    if sentences:
        return sentences

    return [normalized] if normalized else []


def normalize_summary_sentence(sentence: str) -> str:
    sentence = strip_tags(sentence)
    sentence = re.sub(r"\[[^\]]+\]", " ", sentence)
    sentence = re.sub(r"\([^)]*기자[^)]*\)", " ", sentence)
    sentence = re.sub(r"(사진|이미지)\s*=\s*[^.]+", " ", sentence)
    sentence = re.sub(r"\s+", " ", sentence)
    return sentence.strip(" ,;")


def is_noisy_sentence(sentence: str) -> bool:
    cleaned = normalize_summary_sentence(sentence)
    if not cleaned:
        return True
    if "http" in cleaned.lower() or "@" in cleaned:
        return True
    return any(marker in cleaned for marker in NOISY_SENTENCE_MARKERS)


def score_article_text(text: str) -> int:
    cleaned = strip_tags(text)
    if not cleaned:
        return -1

    score = min(len(cleaned), 4000)
    score += cleaned.count(". ") * 15
    score += cleaned.count("다.") * 10
    if cleaned.endswith("..."):
        score -= 80
    if any(marker in cleaned for marker in NOISY_SENTENCE_MARKERS):
        score -= 120
    if "기자" in cleaned[:30]:
        score -= 15
    return score


def score_sentences(sentences: list[str], keyword: str) -> list[tuple[float, int, str]]:
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
        if index == 0:
            score += 1.5
        elif index == 1:
            score += 0.5
        scored.append((score, index, sentence))

    return scored


def summarize_text_lines(text: str, keyword: str, line_count: int = 3) -> list[str]:
    sentences = split_sentences(text)
    filtered_sentences = [sentence for sentence in sentences if not is_noisy_sentence(sentence)]
    if filtered_sentences:
        sentences = filtered_sentences[:8]
    elif sentences:
        sentences = sentences[:5]
    if not sentences:
        cleaned = normalize_summary_sentence(text)
        return [shorten_text(cleaned, 120)] if cleaned else []

    scored = score_sentences(sentences, keyword)
    selected: list[tuple[int, str]] = []
    seen_normalized: set[str] = set()

    def add_sentence(index: int, sentence: str) -> None:
        normalized = normalize_summary_sentence(sentence)
        if not normalized:
            return
        dedupe_key = re.sub(r"\W+", "", normalized.lower())
        if dedupe_key in seen_normalized:
            return
        seen_normalized.add(dedupe_key)
        selected.append((index, normalized))

    add_sentence(0, sentences[0])
    for _, index, sentence in sorted(scored, key=lambda item: (-item[0], item[1])):
        if len(selected) >= line_count:
            break
        add_sentence(index, sentence)

    if len(selected) < line_count:
        for index, sentence in enumerate(sentences[1:], start=1):
            if len(selected) >= line_count:
                break
            add_sentence(index, sentence)

    selected.sort(key=lambda item: item[0])
    return [sentence for _, sentence in selected[:line_count]]


def summarize_text(text: str, keyword: str, sentence_count: int = 1) -> str:
    return " ".join(summarize_text_lines(text, keyword, line_count=sentence_count))


def build_search_url(keyword: str) -> str:
    return NAVER_SEARCH_URL.format(query=quote_plus(keyword))


def parse_search_results(html_text: str) -> list[dict[str, Any]]:
    parser = NaverSearchParser()
    parser.feed(html_text)
    parser.close()
    return parser.articles[:SEARCH_RESULT_LIMIT]


def extract_source_name(article_url: str) -> str:
    host = urlparse(article_url).netloc.lower().replace("www.", "")
    return host or "unknown"


def sort_articles_by_recency(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed_articles: list[tuple[int, dict[str, Any]]] = list(enumerate(articles))

    def sort_key(item: tuple[int, dict[str, Any]]) -> tuple[datetime, int]:
        index, article = item
        published_at = article.get("published_dt")
        if published_at is None:
            published_at = parse_published_at(article.get("published_at", ""))
        if published_at is None:
            published_at = datetime.min.replace(tzinfo=KST)
        return published_at, -index

    indexed_articles.sort(key=sort_key, reverse=True)
    return [article for _, article in indexed_articles]


def escape_markdown_label(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def apply_llm_summaries(keyword: str, articles: list[dict[str, Any]]) -> str:
    if not openai_is_configured():
        return "extractive"

    try:
        llm_summaries = request_llm_article_summaries(keyword, articles)
    except Exception:
        return "extractive"

    used_llm = False
    for index, article in enumerate(articles, start=1):
        llm_lines = llm_summaries.get(index)
        if not llm_lines:
            continue

        cleaned_lines = [normalize_summary_sentence(line) for line in llm_lines]
        cleaned_lines = [line for line in cleaned_lines if line]
        if not cleaned_lines:
            continue

        article["summary_lines"] = cleaned_lines[:3]
        article["summary"] = "\n".join(article["summary_lines"])
        article["summary_provider"] = "llm"
        used_llm = True

    if not used_llm:
        return "extractive"
    if all(article.get("summary_provider") == "llm" for article in articles):
        return "llm"
    return "mixed"


def enrich_article(article: dict[str, Any], keyword: str) -> dict[str, Any]:
    content = article.get("preview_text", "")
    published_dt = article.get("published_dt")
    candidate_urls = [article.get("naver_link", ""), article["url"]]
    seen_candidates: set[str] = set()

    for candidate_url in candidate_urls:
        if not candidate_url or candidate_url in seen_candidates:
            continue
        seen_candidates.add(candidate_url)
        try:
            article_html = fetch_html(candidate_url)
        except NewsCrawlerError:
            continue

        extracted = extract_article_text(article_html)
        if extracted and score_article_text(extracted) > score_article_text(content):
            content = extracted

        extracted_published_at = extract_article_published_at(article_html)
        if extracted_published_at is not None:
            published_dt = extracted_published_at

        if content and published_dt is not None:
            break

    content = content or article["title"]
    summary_lines = summarize_text_lines(content, f"{keyword} {article['title']}", line_count=3)
    if not summary_lines:
        summary_lines = [article["title"]]

    article["content"] = content
    article["source"] = extract_source_name(article["url"])
    article["published_dt"] = published_dt
    article["published_at"] = format_published_at(published_dt, article.get("published_at", ""))
    article["summary_lines"] = summary_lines
    article["summary"] = "\n".join(summary_lines)
    article["summary_provider"] = "extractive"
    return article


def get_news(keyword: str) -> list[dict[str, Any]]:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("keyword is required")

    search_html = fetch_html(build_search_url(keyword))
    articles = parse_search_results(search_html)
    if not articles:
        raise NewsCrawlerError("No news articles were found for the keyword")

    sorted_articles = sort_articles_by_recency(articles)
    enriched_articles = [enrich_article(article, keyword) for article in sorted_articles]
    enriched_articles = sort_articles_by_recency(enriched_articles)[:DEFAULT_LIMIT]
    summary_provider = apply_llm_summaries(keyword, enriched_articles)

    return [
        {
            "title": article["title"],
            "source": article["source"],
            "url": article["url"],
            "published_at": article["published_at"],
            "snippet": article["summary"],
            "summary_lines": article["summary_lines"],
            "summary_provider": article.get("summary_provider", summary_provider),
            "content": article["content"],
        }
        for article in enriched_articles
    ]


def summarize_articles(articles: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, article in enumerate(articles, start=1):
        lines = article.get("summary_lines") or summarize_text_lines(
            article.get("content", "") or article.get("snippet", ""),
            article.get("title", ""),
            line_count=3,
        )
        bullet_lines = "\n".join(f"- {line}" for line in lines[:3])
        title = escape_markdown_label(article["title"])
        meta_parts = [article.get("source", "")]
        if article.get("published_at"):
            meta_parts.append(article["published_at"])
        meta_text = " | ".join(part for part in meta_parts if part)
        block = f"### {index}. [{title}](<{article['url']}>)"
        if meta_text:
            block += f"\n_{meta_text}_"
        if bullet_lines:
            block += f"\n{bullet_lines}"
        blocks.append(block)
    return "\n\n".join(blocks)


def build_tts_script(keyword: str, summary_text: str, articles: list[dict[str, Any]]) -> str:
    parts = [f"{keyword} 기사 브리핑입니다."]

    for index, article in enumerate(articles[:DEFAULT_LIMIT]):
        ordinal = ORDINALS[index] if index < len(ORDINALS) else f"{index + 1}번째"
        lines = article.get("summary_lines") or article.get("snippet", "").splitlines()
        line_text = " ".join(clean_text(line) for line in lines if clean_text(line))
        parts.append(f"{ordinal} 기사입니다. 제목은 {article['title']}입니다. {line_text}")

    return " ".join(parts)


def make_tts(keyword: str, summary_text: str, articles: list[dict[str, Any]]) -> str:
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = AUDIO_DIR / filename
    tts_script = build_tts_script(keyword, summary_text, articles)
    gTTS(text=tts_script, lang="ko").save(output_path)
    return f"/audio/{filename}"
