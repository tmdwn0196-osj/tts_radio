import os

import httpx
import streamlit as st


api_host = os.getenv("API_HOST", "127.0.0.1")
api_port = os.getenv("API_PORT", "8000")
api_base_url = f"http://{api_host}:{api_port}"
summarize_url = f"{api_base_url}/summarize"


st.set_page_config(page_title="기사요약봇", layout="centered")
st.title("기사요약봇")
st.caption("네이버 상위 기사 5개를 짧게 요약하고 음성으로 들려줍니다.")

keyword = st.text_input("키워드", placeholder="예: 경제, 축구, 인공지능")

if st.button("요약하기"):
    if not keyword.strip():
        st.warning("키워드를 입력하세요.")
    else:
        try:
            response = httpx.post(summarize_url, json={"keyword": keyword}, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            st.error(f"API 호출에 실패했습니다: {exc}")
        else:
            audio_url = data["audio_url"]
            full_audio_url = audio_url if audio_url.startswith("http") else f"{api_base_url}{audio_url}"

            st.subheader("전체 요약")
            st.write(data["summary"])

            st.subheader("음성")
            try:
                audio_response = httpx.get(full_audio_url, timeout=30.0)
                audio_response.raise_for_status()
            except httpx.HTTPError as exc:
                st.error(f"음성 파일을 불러오지 못했습니다: {exc}")
            else:
                st.audio(audio_response.content, format="audio/mp3")

            st.subheader("기사별 한줄 요약")
            for index, article in enumerate(data["articles"], start=1):
                st.markdown(f"**{index}. {article['title']}**")
                meta_parts = [article["source"]]
                if article["published_at"]:
                    meta_parts.append(article["published_at"])
                meta_parts.append(article["url"])
                st.caption(" | ".join(meta_parts))
                st.write(article["snippet"])
