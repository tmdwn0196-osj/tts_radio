from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "45"))
OPENAI_MAX_ARTICLE_CHARS = int(os.getenv("OPENAI_MAX_ARTICLE_CHARS", "5000"))
OPENAI_SUMMARY_RETRIES = int(os.getenv("OPENAI_SUMMARY_RETRIES", "2"))


class LLMNewsSummaryError(Exception):
    pass


def openai_is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def strip_tags(text: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", str(text)))


def trim_content_for_llm(text: str, max_chars: int = OPENAI_MAX_ARTICLE_CHARS) -> str:
    cleaned = strip_tags(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0].strip()


def extract_output_text(response_data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response_data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_summary_line(text: str) -> str:
    line = clean_text(text)
    line = re.sub(r"(?:\.\.\.|…)+$", "", line).strip()
    line = re.sub(r"\s+", " ", line)
    if line and not re.search(r"[.!?]$", line):
        if re.search(r"(니다|했다|한다|된다|였다|이다|있다|없다|받았다|밝혔다|전했다|설명했다|강조했다|예정이다|방침이다)$", line):
            line += "."
    return line


def is_complete_summary_line(text: str) -> bool:
    line = normalize_summary_line(text)
    if len(line) < 12:
        return False
    if text.strip().endswith(("...", "…")):
        return False
    if re.search(r"[.!?]$", line):
        return True
    return bool(
        re.search(
            r"(니다|했다|한다|된다|였다|이다|있다|없다|받았다|밝혔다|전했다|설명했다|강조했다|예정이다|방침이다)$",
            line,
        )
    )


def extract_candidate_results(parsed: dict[str, Any]) -> dict[int, list[str]]:
    results: dict[int, list[str]] = {}
    for item in parsed.get("articles", []):
        article_index = int(item.get("article_index", 0))
        if article_index <= 0:
            continue
        lines = [
            normalize_summary_line(item.get("line1", "")),
            normalize_summary_line(item.get("line2", "")),
            normalize_summary_line(item.get("line3", "")),
        ]
        lines = [line for line in lines if line]
        if lines:
            results[article_index] = lines[:3]
    return results


def all_lines_complete(results: dict[int, list[str]], article_count: int) -> bool:
    if len(results) < article_count:
        return False
    for lines in results.values():
        if len(lines) < 3:
            return False
        if not all(is_complete_summary_line(line) for line in lines[:3]):
            return False
    return True


def build_correction_prompt(invalid_results: dict[int, list[str]]) -> str:
    serialized = []
    for index, lines in sorted(invalid_results.items()):
        serialized.append(
            "\n".join(
                [
                    f"[기사 {index} 기존 요약]",
                    f"1. {lines[0] if len(lines) > 0 else ''}",
                    f"2. {lines[1] if len(lines) > 1 else ''}",
                    f"3. {lines[2] if len(lines) > 2 else ''}",
                ]
            )
        )
    return (
        "이전 응답에는 말줄임표로 끝나거나 문장이 덜 끝난 줄이 있었습니다. "
        "이번에는 모든 줄을 반드시 완전한 한국어 문장으로 다시 작성하세요. "
        "각 줄은 '...','…'로 끝내지 말고, 문장 끝을 명확히 마무리하세요.\n\n"
        + "\n\n".join(serialized)
    )


def request_llm_article_summaries(keyword: str, articles: list[dict[str, Any]]) -> dict[int, list[str]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMNewsSummaryError("OPENAI_API_KEY is not configured")

    schema = {
        "type": "object",
        "properties": {
            "articles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "article_index": {"type": "integer"},
                        "line1": {"type": "string"},
                        "line2": {"type": "string"},
                        "line3": {"type": "string"},
                    },
                    "required": ["article_index", "line1", "line2", "line3"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["articles"],
        "additionalProperties": False,
    }

    system_prompt = (
        "당신은 한국어 뉴스 브리핑 편집자입니다. "
        "각 기사에 대해 정확히 3줄로 요약하세요. "
        "반드시 제공된 기사 내용에 근거한 사실만 쓰고 추측하지 마세요. "
        "기자 소개, 제보 문구, 구독 문구, 홍보 문구는 제외하세요. "
        "각 줄은 자연스러운 한국어 완결 문장 1개로 작성하세요. "
        "각 줄 끝은 마침표 또는 명확한 문장 종결로 마무리하고, '...' 또는 '…'로 끝내지 마세요."
    )

    article_sections: list[str] = []
    for index, article in enumerate(articles, start=1):
        article_sections.append(
            "\n".join(
                [
                    f"[기사 {index}]",
                    f"제목: {article['title']}",
                    f"언론사: {article.get('source', '')}",
                    f"작성시각: {article.get('published_at', '')}",
                    f"링크: {article['url']}",
                    "본문:",
                    trim_content_for_llm(article.get("content", "") or article.get("preview_text", "")),
                ]
            )
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_user_prompt = (
        f"검색 키워드: {keyword}\n\n"
        "아래 기사들을 각각 3줄씩 요약하세요.\n"
        "숫자, 주체, 시점이 명확하면 유지하고 정보가 부족하면 과장하지 마세요.\n"
        "중요: 세 줄 모두 완결된 문장이어야 하며 말줄임표로 끝나면 안 됩니다.\n\n"
        + "\n\n".join(article_sections)
    )

    last_results: dict[int, list[str]] = {}

    for attempt in range(OPENAI_SUMMARY_RETRIES):
        user_prompt = base_user_prompt
        if attempt > 0 and last_results:
            user_prompt += "\n\n" + build_correction_prompt(last_results)

        payload = {
            "model": OPENAI_MODEL,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "temperature": 0.1,
            "max_output_tokens": 1800,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "article_summaries",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

        try:
            response = httpx.post(
                f"{OPENAI_API_BASE}/responses",
                headers=headers,
                json=payload,
                timeout=OPENAI_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise LLMNewsSummaryError("Failed to request OpenAI summaries") from error

        output_text = extract_output_text(response.json())
        if not output_text:
            raise LLMNewsSummaryError("OpenAI response did not contain output text")

        try:
            parsed = parse_json_text(output_text)
        except json.JSONDecodeError as error:
            raise LLMNewsSummaryError("Failed to parse OpenAI JSON response") from error

        last_results = extract_candidate_results(parsed)
        if all_lines_complete(last_results, len(articles)):
            return last_results

    raise LLMNewsSummaryError("OpenAI summaries were not complete sentences")
