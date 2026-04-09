import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

KST = ZoneInfo("Asia/Seoul")
DAY_LABELS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

api_host = os.getenv("API_HOST", "127.0.0.1")
api_port = os.getenv("API_PORT", "8000")
api_base_url = f"http://{api_host}:{api_port}"
summarize_url = f"{api_base_url}/summarize"


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Noto+Serif+KR:wght@500;700&display=swap');

        :root {
            --paper: #d8d8d5;
            --paper-soft: #f2f2ef;
            --panel: rgba(250, 250, 248, 0.84);
            --panel-strong: rgba(255, 255, 254, 0.92);
            --ink: #181818;
            --muted: #626262;
            --line: rgba(38, 38, 38, 0.16);
            --accent: #474747;
            --accent-deep: #1c1c1c;
            --shadow: 0 16px 34px rgba(20, 20, 20, 0.08);
        }

        html, body, [class*="css"]  {
            font-family: "IBM Plex Sans KR", sans-serif;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(255, 255, 255, 0.94), transparent 34%),
                radial-gradient(circle at top right, rgba(146, 146, 146, 0.14), transparent 22%),
                linear-gradient(180deg, #d2d2cf 0%, #e9e9e6 28%, #f5f5f3 100%);
            color: var(--ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        .block-container {
            max-width: 1180px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }

        .news-shell {
            margin-bottom: 1.35rem;
        }

        .news-masthead {
            position: relative;
            overflow: hidden;
            padding: 1.4rem 1.6rem 1.2rem 1.6rem;
            border: 1px solid var(--line);
            border-radius: 28px;
            background:
                linear-gradient(135deg, rgba(255, 255, 255, 0.97), rgba(236, 236, 233, 0.9)),
                repeating-linear-gradient(
                    0deg,
                    rgba(84, 84, 84, 0.035) 0px,
                    rgba(84, 84, 84, 0.035) 1px,
                    transparent 1px,
                    transparent 32px
                );
            box-shadow: var(--shadow);
        }

        .news-masthead::after {
            content: "";
            position: absolute;
            inset: auto -4rem -5rem auto;
            width: 16rem;
            height: 16rem;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(66, 66, 66, 0.14), transparent 68%);
            pointer-events: none;
        }

        .news-masthead__topline {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            gap: 0.85rem;
            align-items: center;
            padding-bottom: 0.9rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid rgba(36, 36, 36, 0.15);
            font-size: 0.88rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--muted);
        }

        .news-masthead__title {
            margin: 0;
            font-family: "Noto Serif KR", serif;
            font-size: clamp(2.2rem, 5vw, 4rem);
            font-weight: 700;
            line-height: 1.03;
            letter-spacing: -0.04em;
            color: var(--ink);
        }

        .news-masthead__subtitle {
            max-width: 48rem;
            margin: 0.75rem 0 0;
            font-size: 1.02rem;
            line-height: 1.75;
            color: rgba(24, 24, 24, 0.76);
        }

        .news-divider {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin: 1.25rem 0 1rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.16em;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .news-divider::before,
        .news-divider::after {
            content: "";
            flex: 1;
            height: 1px;
            background: rgba(36, 36, 36, 0.15);
        }

        .editorial-note {
            padding: 1rem 1.1rem;
            margin-bottom: 0.85rem;
            border: 1px solid var(--line);
            border-radius: 22px;
            background: var(--panel);
            box-shadow: 0 10px 24px rgba(20, 20, 20, 0.06);
        }

        .editorial-note__eyebrow {
            margin-bottom: 0.35rem;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.14em;
            font-size: 0.78rem;
            font-weight: 800;
        }

        .editorial-note__title {
            margin: 0;
            font-family: "Noto Serif KR", serif;
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--ink);
        }

        .editorial-note__body {
            margin: 0.45rem 0 0;
            color: rgba(24, 24, 24, 0.7);
            line-height: 1.7;
        }

        div[data-testid="stTextInputRootElement"] label,
        div[data-testid="stTextInputRootElement"] p {
            color: var(--muted) !important;
            font-weight: 600;
        }

        div[data-testid="stTextInputRootElement"] input {
            min-height: 3.35rem;
            border-radius: 18px;
            border: 1px solid rgba(36, 36, 36, 0.18);
            background: rgba(255, 255, 254, 0.94);
            color: var(--ink);
            font-size: 1.03rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
        }

        div[data-testid="stTextInputRootElement"] input::placeholder {
            color: rgba(98, 98, 98, 0.6);
        }

        div.stButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 3.35rem;
            border-radius: 999px;
            border: 1px solid rgba(22, 22, 22, 0.18);
            background: linear-gradient(135deg, var(--accent-deep), var(--accent));
            color: #fbfbfa;
            font-weight: 800;
            letter-spacing: 0.02em;
            box-shadow: 0 14px 24px rgba(18, 18, 18, 0.12);
        }

        div.stButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            border-color: rgba(22, 22, 22, 0.18);
            color: #fbfbfa;
        }

        .summary-loading {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.95rem 1.3rem;
            border-radius: 999px;
            border: 1px solid rgba(22, 22, 22, 0.1);
            background: rgba(255, 255, 254, 0.95);
            box-shadow: 0 12px 22px rgba(18, 18, 18, 0.08);
            font-weight: 800;
            font-size: 2rem;
            color: var(--accent-deep);
            line-height: 1.1;
        }

        .summary-loading__dots span {
            display: inline-block;
            min-width: 0.45rem;
            animation: summary-loading-blink 1.2s infinite ease-in-out;
        }

        .summary-loading__dots span:nth-child(2) {
            animation-delay: 0.2s;
        }

        .summary-loading__dots span:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes summary-loading-blink {
            0%, 80%, 100% {
                opacity: 0.22;
                transform: translateY(0);
            }
            40% {
                opacity: 1;
                transform: translateY(-2px);
            }
        }

        .brief-strip {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 0.75rem 0 1.3rem;
        }

        .brief-stat {
            padding: 1rem 1.05rem;
            border: 1px solid var(--line);
            border-radius: 22px;
            background: var(--panel-strong);
            box-shadow: 0 12px 24px rgba(20, 20, 20, 0.06);
        }

        .brief-stat__label {
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .brief-stat__value {
            margin-top: 0.45rem;
            color: var(--ink);
            font-family: "Noto Serif KR", serif;
            font-size: 1.2rem;
            font-weight: 700;
            line-height: 1.35;
        }

        .section-heading {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: end;
            gap: 0.8rem;
            margin: 1.2rem 0 0.8rem;
        }

        .section-heading__title {
            margin: 0;
            font-family: "Noto Serif KR", serif;
            font-size: clamp(1.6rem, 3vw, 2.3rem);
            color: var(--ink);
        }

        .section-heading__meta {
            color: var(--muted);
            font-size: 0.92rem;
            letter-spacing: 0.04em;
        }

        .audio-panel {
            padding: 1rem 1.1rem 0.7rem;
            margin-bottom: 1rem;
            border: 1px solid var(--line);
            border-radius: 24px;
            background:
                linear-gradient(145deg, rgba(255, 255, 254, 0.95), rgba(236, 236, 233, 0.92));
            box-shadow: var(--shadow);
        }

        .audio-panel__kicker {
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.14em;
            font-size: 0.78rem;
            font-weight: 800;
        }

        .audio-panel__title {
            margin: 0.3rem 0 0.2rem;
            font-family: "Noto Serif KR", serif;
            font-size: 1.25rem;
            color: var(--ink);
        }

        .audio-panel__body {
            margin: 0;
            color: rgba(24, 24, 24, 0.72);
            line-height: 1.65;
        }

        div[data-testid="stAudio"] {
            margin-top: 0.8rem;
            padding: 0.2rem 0 0.05rem;
        }

        .lead-story,
        .story-card,
        .empty-card {
            position: relative;
            overflow: hidden;
            min-width: 0;
            padding: 1.25rem 1.2rem;
            border: 1px solid var(--line);
            border-radius: 26px;
            background: var(--panel-strong);
            box-shadow: var(--shadow);
        }

        .lead-story {
            margin-bottom: 1rem;
            background:
                linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(236, 236, 234, 0.93));
        }

        .story-card {
            min-height: 100%;
            background:
                linear-gradient(180deg, rgba(255, 255, 254, 0.96), rgba(240, 240, 238, 0.92));
        }

        .story-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            margin-bottom: 0.8rem;
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        .story-kicker::before {
            content: "";
            width: 0.65rem;
            height: 0.65rem;
            border-radius: 50%;
            background: rgba(71, 71, 71, 0.18);
            box-shadow: inset 0 0 0 4px rgba(71, 71, 71, 0.14);
        }

        .story-rank {
            position: absolute;
            top: 1rem;
            right: 1rem;
            color: rgba(64, 64, 64, 0.18);
            font-family: "Noto Serif KR", serif;
            font-size: 2.4rem;
            font-weight: 700;
            line-height: 1;
        }

        .lead-story h3,
        .story-card h3,
        .empty-card h3 {
            margin: 0;
            font-family: "Noto Serif KR", serif;
            line-height: 1.34;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: keep-all;
        }

        .lead-story h3 {
            font-size: clamp(1.5rem, 2.5vw, 2.15rem);
            max-width: 44rem;
        }

        .story-card h3,
        .empty-card h3 {
            font-size: 1.22rem;
            padding-right: 4rem;
        }

        .lead-story h3 a,
        .story-card h3 a,
        .empty-card h3 a {
            display: block;
            white-space: inherit;
            overflow-wrap: inherit;
            word-break: inherit;
        }

        .lead-story a,
        .story-card a,
        .empty-card a {
            color: inherit;
            text-decoration: none;
        }

        .story-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem 0.75rem;
            margin: 0.8rem 0 0.95rem;
            color: var(--muted);
            font-size: 0.9rem;
        }

        .story-meta span {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .story-meta span::before {
            content: "";
            width: 0.26rem;
            height: 0.26rem;
            border-radius: 50%;
            background: rgba(98, 98, 98, 0.5);
        }

        .story-copy {
            margin: 0;
            padding-left: 1.1rem;
            color: rgba(24, 24, 24, 0.82);
            line-height: 1.8;
        }

        .story-copy li {
            margin-bottom: 0.35rem;
        }

        .story-link {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            margin-top: 0.95rem;
            color: var(--accent-deep) !important;
            font-weight: 700;
        }

        .story-link::after {
            content: "->";
            font-size: 0.95rem;
        }

        .empty-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin-top: 0.8rem;
        }

        .empty-card {
            background: rgba(255, 255, 254, 0.74);
        }

        .empty-card p {
            margin: 0.65rem 0 0;
            color: rgba(24, 24, 24, 0.7);
            line-height: 1.75;
        }

        @media (max-width: 900px) {
            .brief-strip,
            .empty-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_loading_indicator(placeholder, text: str) -> None:
    placeholder.markdown(
        f"""
        <div class="summary-loading">
            <span>{text}</span>
            <span class="summary-loading__dots">
                <span>.</span><span>.</span><span>.</span>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def request_summary(keyword: str) -> dict:
    response = httpx.post(summarize_url, json={"keyword": keyword}, timeout=90.0)
    response.raise_for_status()
    return response.json()


def provider_label(summary_provider: str) -> str:
    labels = {
        "llm": "LLM 요약",
        "mixed": "혼합 요약",
        "extractive": "추출 요약",
    }
    return labels.get(summary_provider, "기사 요약")


def current_issue_label() -> str:
    now = datetime.now(KST)
    day_label = DAY_LABELS[now.weekday()]
    return f"{now:%Y.%m.%d} {day_label} | ULSAN EDITION"


def render_masthead() -> None:
    st.markdown(
        f"""
        <section class="news-shell">
            <div class="news-masthead">
                <div class="news-masthead__topline">
                    <span>{current_issue_label()}</span>
                    <span>Keyword Desk</span>
                </div>
                <h1 class="news-masthead__title">Morning News Brief</h1>
                <p class="news-masthead__subtitle">
                    키워드 하나로 최신 기사 흐름을 정리하고, 기사별 핵심만 카드뉴스처럼 빠르게 훑어볼 수 있도록 구성했습니다.
                </p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_input_panel() -> bool:
    st.markdown('<div class="news-divider">Search Desk</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="editorial-note">
            <div class="editorial-note__eyebrow">Today&apos;s Query</div>
            <h2 class="editorial-note__title">키워드를 넣으면 최신 기사 5건을 한 번에 정리합니다.</h2>
            <p class="editorial-note__body">
                대표 기사 한 건은 크게, 나머지는 카드뉴스처럼 나눠 보여드립니다.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("keyword_form", border=False):
        input_col, action_col = st.columns([4.3, 1.2], vertical_alignment="bottom")
        with input_col:
            st.text_input(
                "키워드",
                key="keyword_input",
                placeholder="예: 반도체, 산불, 부동산, 챔피언스리그",
            )
        with action_col:
            submitted = st.form_submit_button("요약하기", type="primary", use_container_width=True)
    return submitted


def render_brief_strip(keyword: str, article_count: int, summary_provider: str) -> None:
    st.markdown(
        f"""
        <div class="brief-strip">
            <div class="brief-stat">
                <div class="brief-stat__label">Topic</div>
                <div class="brief-stat__value">{html.escape(keyword)}</div>
            </div>
            <div class="brief-stat">
                <div class="brief-stat__label">Edition</div>
                <div class="brief-stat__value">최신 기사 {article_count}건</div>
            </div>
            <div class="brief-stat">
                <div class="brief-stat__label">Summary Mode</div>
                <div class="brief-stat__value">{html.escape(provider_label(summary_provider))}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_audio_panel(audio_bytes: bytes) -> None:
    st.markdown(
        """
        <div class="audio-panel">
            <div class="audio-panel__kicker">Audio Briefing</div>
            <h3 class="audio-panel__title">기사별 요약을 음성 브리핑으로 들을 수 있습니다.</h3>
            <p class="audio-panel__body">
                상단 카드들을 보기 전에 핵심 흐름을 먼저 듣고 내려가면 훨씬 빠르게 파악할 수 있습니다.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.audio(audio_bytes, format="audio/mp3")


def story_meta(article: dict) -> str:
    parts = [article.get("source", ""), article.get("published_at", "")]
    return "".join(f"<span>{html.escape(part)}</span>" for part in parts if part)


def story_title(article: dict, variant: str) -> str:
    def trim_title(raw_title: str) -> str:
        if not raw_title:
            return ""
        head, separator, _ = raw_title.partition("<")
        cleaned = head.strip() if separator else raw_title.strip()
        return cleaned or raw_title.replace("<", "").strip()

    if variant == "lead":
        title = article.get("lead_title") or article.get("card_title") or article.get("title", "")
    else:
        title = article.get("card_title") or article.get("lead_title") or article.get("title", "")
    return trim_title(title)


def story_copy(article: dict) -> str:
    summary_lines = article.get("summary_lines") or [
        line for line in article.get("snippet", "").splitlines() if line.strip()
    ]
    items = "".join(f"<li>{html.escape(line)}</li>" for line in summary_lines[:3])
    return f'<ul class="story-copy">{items}</ul>'


def render_lead_story(article: dict) -> None:
    title = story_title(article, "lead")
    st.markdown(
        f"""
        <article class="lead-story">
            <div class="story-kicker">Lead Story</div>
            <h3>
                <a href="{html.escape(article['url'])}" target="_blank" rel="noopener noreferrer">
                    {html.escape(title)}
                </a>
            </h3>
            <div class="story-meta">{story_meta(article)}</div>
            {story_copy(article)}
            <a class="story-link" href="{html.escape(article['url'])}" target="_blank" rel="noopener noreferrer">
                원문 기사 보기
            </a>
        </article>
        """,
        unsafe_allow_html=True,
    )


def render_story_card(article: dict, index: int) -> None:
    title = story_title(article, "card")
    st.markdown(
        f"""
        <article class="story-card">
            <div class="story-kicker">Story {index:02d}</div>
            <div class="story-rank">{index:02d}</div>
            <h3>
                <a href="{html.escape(article['url'])}" target="_blank" rel="noopener noreferrer">
                    {html.escape(title)}
                </a>
            </h3>
            <div class="story-meta">{story_meta(article)}</div>
            {story_copy(article)}
            <a class="story-link" href="{html.escape(article['url'])}" target="_blank" rel="noopener noreferrer">
                원문 기사 보기
            </a>
        </article>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown('<div class="news-divider">Front Page Preview</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="empty-grid">
            <article class="empty-card">
                <div class="story-kicker">Headline</div>
                <h3>대표 기사가 이 자리에 크게 배치됩니다.</h3>
                <p>가장 먼저 읽어야 할 기사 한 건을 전면에 두고, 제목과 핵심 3줄을 바로 확인할 수 있게 구성했습니다.</p>
            </article>
            <article class="empty-card">
                <div class="story-kicker">Card News</div>
                <h3>나머지 기사들은 카드뉴스처럼 나뉘어 배치됩니다.</h3>
                <p>출처와 발행 시각, 3줄 요약, 원문 링크까지 한 장의 카드 안에서 끝나도록 정리합니다.</p>
            </article>
            <article class="empty-card">
                <div class="story-kicker">Briefing</div>
                <h3>음성 브리핑은 섹션 상단 패널로 분리됩니다.</h3>
                <p>신문 지면과 카드뉴스 사이를 이어주는 오디오 브리핑 영역을 두어 읽기 전 흐름을 먼저 잡을 수 있게 했습니다.</p>
            </article>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_articles(articles: list[dict]) -> None:
    if not articles:
        st.info("표시할 기사가 없습니다.")
        return

    lead_article, *remaining_articles = articles
    render_lead_story(lead_article)

    if not remaining_articles:
        return

    columns = st.columns(2, gap="large")
    for index, article in enumerate(remaining_articles, start=2):
        with columns[(index - 2) % 2]:
            render_story_card(article, index)


st.set_page_config(page_title="News Brief Bot", layout="wide")
inject_styles()

if "keyword_input" not in st.session_state:
    st.session_state["keyword_input"] = ""
if "summary_data" not in st.session_state:
    st.session_state["summary_data"] = None

render_masthead()
submitted = render_input_panel()

if submitted:
    keyword = st.session_state["keyword_input"].strip()
    if not keyword:
        st.warning("키워드를 입력해주세요.")
    else:
        loading_placeholder = st.empty()
        show_loading_indicator(loading_placeholder, "요약중")
        try:
            st.session_state["summary_data"] = request_summary(keyword)
        except httpx.HTTPError as exc:
            loading_placeholder.empty()
            st.error(f"API 호출에 실패했습니다: {exc}")
        else:
            loading_placeholder.empty()

data = st.session_state.get("summary_data")
if data:
    keyword = data.get("keyword", st.session_state["keyword_input"])
    articles = data.get("articles", [])
    summary_provider = data.get("summary_provider", "extractive")
    audio_url = data["audio_url"]
    full_audio_url = audio_url if audio_url.startswith("http") else f"{api_base_url}{audio_url}"

    render_brief_strip(keyword, len(articles), summary_provider)
    st.markdown(
        f"""
        <div class="section-heading">
            <h2 class="section-heading__title">기사별 요약</h2>
            <div class="section-heading__meta">{html.escape(current_issue_label())}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        audio_response = httpx.get(full_audio_url, timeout=30.0)
        audio_response.raise_for_status()
    except httpx.HTTPError as exc:
        st.error(f"음성 파일을 불러오지 못했습니다: {exc}")
    else:
        render_audio_panel(audio_response.content)

    render_articles(articles)
else:
    render_empty_state()
