from __future__ import annotations

import os
import re
from datetime import datetime

import httpx

OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_TIMEOUT = 45.0
ARTICLE_CHAR_LIMIT = 1400


class BriefingGenerationError(Exception):
    pass


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _trim_text(text: str, limit: int = ARTICLE_CHAR_LIMIT) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0].strip()


def _extract_output_text(response_data: dict) -> str:
    parts: list[str] = []
    for item in response_data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _build_article_digest(articles: list[dict[str, str]]) -> str:
    sections: list[str] = []
    for index, article in enumerate(articles, start=1):
        sections.append(
            "\n".join(
                [
                    f"[기사 {index}]",
                    f"제목: {article['title']}",
                    f"출처: {article.get('source', '')}",
                    f"발행 시각: {article.get('published_at', '') or '미상'}",
                    f"URL: {article['url']}",
                    f"내용: {_trim_text(article.get('content') or article.get('snippet') or article['title'])}",
                ]
            )
        )
    return "\n\n".join(sections)


def _normalize_script(text: str) -> str:
    script = text.strip().strip('"').strip("'")
    script = re.sub(r"^```[a-zA-Z]*", "", script).strip()
    script = re.sub(r"```$", "", script).strip()
    script = re.sub(r"^[\-\*\d\.\)\s]+", "", script, flags=re.MULTILINE)
    script = re.sub(r"\s+", " ", script)
    return script.strip()


def generate_radio_script(topic: str, articles: list[dict[str, str]]) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    api_base = os.getenv("OPENAI_API_BASE", OPENAI_API_BASE).rstrip("/")
    model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
    if not api_key:
        raise BriefingGenerationError("OPENAI_API_KEY is not configured")
    if not articles:
        raise BriefingGenerationError("articles are required")

    today_label = datetime.now().strftime("%Y-%m-%d")
    article_digest = _build_article_digest(articles)

    system_prompt = (
        "당신은 한국어 라디오 뉴스 원고 작가입니다. "
        "제공된 기사만 근거로, 45초에서 60초 사이 분량의 자연스러운 오디오 브리핑 원고를 작성하세요. "
        "형식은 오프닝 1문장, 핵심 뉴스 3개 안팎, 마무리 1문장입니다. "
        "문장은 부드럽게 이어지고, 아나운서가 읽기 쉬워야 하며, 마크다운/불릿/번호/제목은 쓰지 마세요. "
        "제공된 기사에 없는 사실은 추측하지 말고 URL은 쓰지 마세요."
    )
    user_prompt = (
        f"오늘 날짜는 {today_label}입니다.\n"
        f"브리핑 주제: {topic}\n\n"
        "아래 기사들을 참고해 개인 맞춤형 1분 AI 라디오 원고를 작성하세요.\n"
        "첫 문장은 청취자를 환영하는 짧은 오프닝으로 시작하고, "
        "본문에서는 가장 중요한 흐름 위주로 3개 정도만 간결하게 엮어 주세요. "
        "마지막에는 '이상, 오늘의 브리핑이었습니다.'처럼 자연스러운 클로징 문장을 넣어 주세요.\n\n"
        f"{article_digest}"
    )

    payload = {
        "model": model,
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
        "temperature": 0.4,
        "max_output_tokens": 500,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            f"{api_base}/responses",
            headers=headers,
            json=payload,
            timeout=OPENAI_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise BriefingGenerationError("Failed to generate the radio script with OpenAI") from error

    script = _normalize_script(_extract_output_text(response.json()))
    if not script:
        raise BriefingGenerationError("OpenAI returned an empty radio script")

    return script
