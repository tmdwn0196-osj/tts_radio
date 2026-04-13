from __future__ import annotations

import html
import os
from datetime import datetime

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

api_host = os.getenv("API_HOST", "127.0.0.1")
api_port = os.getenv("API_PORT", "8000")
api_base_url = f"http://{api_host}:{api_port}"
briefing_url = f"{api_base_url}/briefing"

TOPIC_OPTIONS = [
    "AI",
    "반도체",
    "경제",
    "부동산",
    "테크",
    "K-POP",
    "스포츠",
]
VOICE_OPTIONS = {
    "anchor_female": "아나운서 톤 (여성)",
    "anchor_male": "아나운서 톤 (남성)",
    "calm": "차분한 톤",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');

        :root {
            --bg-top: #f6efe3;
            --bg-bottom: #fbfaf6;
            --panel: rgba(255, 252, 247, 0.9);
            --panel-strong: rgba(255, 255, 255, 0.95);
            --ink: #182126;
            --muted: #5f6a6f;
            --line: rgba(24, 33, 38, 0.11);
            --accent: #c56a3d;
            --accent-deep: #913d17;
            --shadow: 0 18px 40px rgba(56, 44, 35, 0.08);
        }

        html, body, [class*="css"] {
            font-family: "IBM Plex Sans KR", sans-serif;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(255, 255, 255, 0.9), transparent 28%),
                linear-gradient(180deg, var(--bg-top), var(--bg-bottom));
            color: var(--ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        .block-container {
            max-width: 960px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }

        .hero,
        .panel,
        .result-card {
            border: 1px solid var(--line);
            border-radius: 28px;
            box-shadow: var(--shadow);
        }

        .hero {
            padding: 1.55rem 1.6rem 1.4rem;
            background:
                linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(249, 238, 226, 0.88));
        }

        .hero__meta {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.8rem;
            margin-bottom: 0.9rem;
            font-size: 0.86rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--muted);
        }

        .hero__title {
            margin: 0;
            font-family: "Fraunces", serif;
            font-size: clamp(2rem, 4.8vw, 3.5rem);
            line-height: 1.02;
            letter-spacing: -0.04em;
            color: var(--ink);
        }

        .hero__body {
            max-width: 44rem;
            margin: 0.75rem 0 0;
            line-height: 1.75;
            color: rgba(24, 33, 38, 0.78);
        }

        .panel {
            padding: 1.2rem 1.2rem 1rem;
            margin-top: 1rem;
            background: var(--panel);
        }

        .panel__eyebrow {
            color: var(--accent-deep);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            font-size: 0.78rem;
            font-weight: 800;
        }

        .panel__title {
            margin: 0.4rem 0 0.2rem;
            font-size: 1.3rem;
            font-family: "Fraunces", serif;
            color: var(--ink);
        }

        .panel__body {
            margin: 0;
            line-height: 1.7;
            color: var(--muted);
        }

        .result-card {
            padding: 1.15rem 1.2rem;
            margin-top: 1rem;
            background: var(--panel-strong);
        }

        .result-card__label {
            color: var(--accent-deep);
            letter-spacing: 0.14em;
            text-transform: uppercase;
            font-size: 0.78rem;
            font-weight: 800;
        }

        .result-card__title {
            margin: 0.35rem 0 0.7rem;
            font-size: 1.2rem;
            font-family: "Fraunces", serif;
            color: var(--ink);
        }

        .script-box {
            line-height: 1.95;
            color: rgba(24, 33, 38, 0.88);
            font-size: 1rem;
        }

        .source-list {
            margin: 0;
            padding-left: 1rem;
            line-height: 1.8;
        }

        .source-list a {
            color: var(--accent-deep);
            text-decoration: none;
        }

        div[data-testid="stTextInputRootElement"] input,
        div[data-baseweb="select"] > div {
            border-radius: 16px !important;
        }

        div.stButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 3.15rem;
            border-radius: 999px;
            border: 1px solid rgba(145, 61, 23, 0.18);
            background: linear-gradient(135deg, var(--accent-deep), var(--accent));
            color: white;
            font-weight: 800;
            box-shadow: 0 12px 24px rgba(145, 61, 23, 0.14);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def current_issue_label() -> str:
    return datetime.now().strftime("%Y.%m.%d | MORNING EDITION")


def render_hero() -> None:
    st.markdown(
        f"""
        <section class="hero">
            <div class="hero__meta">
                <span>{current_issue_label()}</span>
                <span>My 1-Minute AI Radio</span>
            </div>
            <h1 class="hero__title">나만의 1분 AI 라디오</h1>
            <p class="hero__body">
                Tavily로 최신 뉴스를 가져오고, GPT-5.4-mini로 1분 대본을 만든 뒤,
                시보 느낌의 짧은 인트로와 TTS로 라디오처럼 들려주는 개인화 뉴스 서비스입니다.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_input_panel() -> bool:
    st.markdown(
        """
        <section class="panel">
            <div class="panel__eyebrow">Daily Setup</div>
            <h2 class="panel__title">오늘 듣고 싶은 주제와 목소리를 고르세요</h2>
            <p class="panel__body">
                추천 주제를 고르거나 직접 입력하면, 1분 안팎의 오디오 브리핑으로 정리해드립니다.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    with st.form("briefing_form", border=False):
        st.selectbox("추천 주제", TOPIC_OPTIONS, key="selected_topic")
        st.text_input("직접 입력", key="custom_topic", placeholder="예: 로봇, 미국 증시, 생성형 AI")
        st.selectbox(
            "목소리 프리셋",
            options=list(VOICE_OPTIONS.keys()),
            format_func=lambda value: VOICE_OPTIONS[value],
            key="voice_preset",
        )
        return st.form_submit_button("1분 브리핑 만들기", type="primary", use_container_width=True)


def resolve_topic() -> str:
    custom_topic = st.session_state.get("custom_topic", "").strip()
    return custom_topic or st.session_state.get("selected_topic", "").strip()


def request_briefing(topic: str, voice_preset: str) -> dict:
    response = httpx.post(
        briefing_url,
        json={"topic": topic, "voice_preset": voice_preset},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_audio(audio_url: str) -> bytes:
    full_audio_url = audio_url if audio_url.startswith("http") else f"{api_base_url}{audio_url}"
    response = httpx.get(full_audio_url, timeout=60.0)
    response.raise_for_status()
    return response.content


def api_error_message(error: httpx.HTTPError) -> str:
    response = getattr(error, "response", None)
    if response is None:
        return str(error)
    try:
        payload = response.json()
    except ValueError:
        return response.text or str(error)
    return payload.get("detail") or str(error)


def render_results(data: dict) -> None:
    topic = data["topic"]
    voice_preset = data["voice_preset"]
    tts_engine = data["tts_engine"]
    script = data["script"]
    articles = data.get("articles", [])

    st.markdown(
        f"""
        <section class="result-card">
            <div class="result-card__label">Radio Script</div>
            <h3 class="result-card__title">{html.escape(topic)} 브리핑 원고</h3>
            <div class="script-box">{html.escape(script)}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <section class="result-card">
            <div class="result-card__label">Audio</div>
            <h3 class="result-card__title">{VOICE_OPTIONS.get(voice_preset, voice_preset)} · {html.escape(tts_engine)}</h3>
        </section>
        """,
        unsafe_allow_html=True,
    )
    try:
        st.audio(fetch_audio(data["audio_url"]), format="audio/mp3")
    except httpx.HTTPError as error:
        st.error(f"오디오를 불러오지 못했습니다: {api_error_message(error)}")

    st.markdown(
        """
        <section class="result-card">
            <div class="result-card__label">Sources</div>
            <h3 class="result-card__title">브리핑에 반영된 기사</h3>
        </section>
        """,
        unsafe_allow_html=True,
    )
    source_items = [
        f'<li><a href="{html.escape(article["url"])}" target="_blank">{html.escape(article["title"])}</a>'
        f' <span style="color:#5f6a6f;">({html.escape(article.get("source", ""))}'
        f'{f" · {html.escape(article.get("published_at", ""))}" if article.get("published_at") else ""})</span></li>'
        for article in articles
    ]
    st.markdown(f'<ul class="source-list">{"".join(source_items)}</ul>', unsafe_allow_html=True)


st.set_page_config(page_title="나만의 1분 AI 라디오", layout="wide")
inject_styles()
render_hero()

if "briefing_data" not in st.session_state:
    st.session_state["briefing_data"] = None

submitted = render_input_panel()

if submitted:
    topic = resolve_topic()
    voice_preset = st.session_state.get("voice_preset", "anchor_female")
    if not topic:
        st.warning("주제를 하나 선택하거나 직접 입력해 주세요.")
    else:
        with st.spinner("최신 뉴스를 모아 1분 브리핑을 만드는 중입니다..."):
            try:
                st.session_state["briefing_data"] = request_briefing(topic, voice_preset)
            except httpx.HTTPError as error:
                st.session_state["briefing_data"] = None
                st.error(f"브리핑 생성에 실패했습니다: {api_error_message(error)}")

if st.session_state.get("briefing_data"):
    render_results(st.session_state["briefing_data"])
