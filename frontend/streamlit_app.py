import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

api_host = os.getenv("API_HOST", "127.0.0.1")
api_port = os.getenv("API_PORT", "8000")
api_base_url = f"http://{api_host}:{api_port}"
summarize_url = f"{api_base_url}/summarize"


def show_loading_indicator(placeholder, text: str) -> None:
    placeholder.markdown(
        f"""
        <style>
        .summary-loading {{
            display: inline-flex;
            align-items: center;
            gap: 0.2rem;
            padding: 0.45rem 0.7rem;
            border-radius: 999px;
            background: rgba(49, 51, 63, 0.08);
            font-weight: 600;
        }}
        .summary-loading__dots span {{
            display: inline-block;
            min-width: 0.35rem;
            animation: summary-loading-blink 1.2s infinite ease-in-out;
        }}
        .summary-loading__dots span:nth-child(2) {{
            animation-delay: 0.2s;
        }}
        .summary-loading__dots span:nth-child(3) {{
            animation-delay: 0.4s;
        }}
        @keyframes summary-loading-blink {{
            0%, 80%, 100% {{
                opacity: 0.2;
                transform: translateY(0);
            }}
            40% {{
                opacity: 1;
                transform: translateY(-1px);
            }}
        }}
        </style>
        <div class="summary-loading">
            <span>{text}</span>
            <span class="summary-loading__dots">
                <span>.</span><span>.</span><span>.</span>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="기사 요약봇", layout="centered")
st.title("기사 요약봇")
st.caption("키워드를 입력하면 최신순 기사 5개를 모아 기사별 3줄 요약으로 정리합니다.")

keyword = st.text_input("키워드", placeholder="예: 경제, 축구, 공지사항")

if st.button("요약하기"):
    if not keyword.strip():
        st.warning("키워드를 입력해주세요.")
    else:
        loading_placeholder = st.empty()
        show_loading_indicator(loading_placeholder, "요약중")
        try:
            response = httpx.post(summarize_url, json={"keyword": keyword}, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            loading_placeholder.empty()
            st.error(f"API 호출에 실패했습니다: {exc}")
        else:
            loading_placeholder.empty()
            audio_url = data["audio_url"]
            full_audio_url = audio_url if audio_url.startswith("http") else f"{api_base_url}{audio_url}"
            summary_provider = data.get("summary_provider", "extractive")

            st.subheader("기사별 요약")
            if summary_provider == "llm":
                st.caption("LLM 기반 요약")
            elif summary_provider == "mixed":
                st.caption("LLM 요약과 기본 요약을 함께 사용했습니다.")
            else:
                st.caption("기본 추출형 요약")
            st.markdown(data["summary"])

            st.subheader("음성")
            try:
                audio_response = httpx.get(full_audio_url, timeout=30.0)
                audio_response.raise_for_status()
            except httpx.HTTPError as exc:
                st.error(f"음성 파일을 불러오지 못했습니다: {exc}")
            else:
                st.audio(audio_response.content, format="audio/mp3")
