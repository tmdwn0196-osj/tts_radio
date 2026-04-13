# 나만의 1분 AI 라디오

사용자가 관심 있는 주제를 선택하면 Tavily로 최신 뉴스를 수집하고, GPT-5.4-mini로 핵심만 짧게 요약해 라디오 대본 형태로 만드는 프로젝트입니다. 이후 시보 느낌의 짧은 인트로를 붙이고, `edge-tts`를 기본으로 사용해 음성을 생성합니다. `edge-tts`가 실패하면 `gTTS`로 자동 fallback 됩니다.

발표용 한 줄 소개:

> Tavily로 최신 뉴스를 가져오고, GPT-5.4-mini로 1분 대본을 만든 뒤, 시보 느낌의 인트로와 TTS로 라디오처럼 들려주는 개인화 뉴스 서비스입니다.

## 구조

```text
tts_radio/
├─ backend/
│  ├─ api/
│  │  └─ main.py
│  └─ data/
│     ├─ news.py
│     ├─ briefing.py
│     ├─ audio_pipeline.py
│     └─ audio/
├─ frontend/
│  └─ streamlit_app.py
├─ .streamlit/
├─ shared/
├─ .env.example
├─ pyproject.toml
└─ README.md
```

## 핵심 흐름

1. 사용자가 Streamlit에서 주제와 목소리 프리셋을 고릅니다.
2. FastAPI가 Tavily Search API로 최신 뉴스 최대 5건을 수집합니다.
3. GPT-5.4-mini가 기사들을 바탕으로 45초에서 60초 분량의 라디오 대본을 생성합니다.
4. 오리지널 3-pip 시보형 인트로를 붙인 뒤 `edge-tts` 또는 `gTTS`로 오디오를 생성합니다.
5. Streamlit이 대본, 오디오, 출처 기사 목록을 함께 보여줍니다.

## 사용 기술

- FastAPI
- Streamlit
- Tavily Search API
- OpenAI Responses API with `gpt-5.4-mini`
- `edge-tts` with `gTTS` fallback
- `pydub` for signal intro and audio stitching

## 환경 변수

`.env.example`를 참고해 `.env`를 만들어 주세요.

```env
API_HOST=127.0.0.1
API_PORT=8000
STREAMLIT_PORT=8501
TAVILY_API_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
```

## 실행 방법

```powershell
uv venv
uv sync
uv run uvicorn backend.api.main:app --reload
uv run streamlit run frontend/streamlit_app.py --server.port 8501
```

## 주의 사항

- `pydub`가 최종 MP3를 합칠 때 `ffmpeg`가 필요합니다. 시스템 PATH에 `ffmpeg`가 잡혀 있어야 합니다.
- `MiniMax`, voice cloning, XTTS/Coqui 같은 기능은 이번 버전에서 제외했습니다.
- 시그널 송은 방송 시보의 느낌만 참고한 짧은 오리지널 톤이며, 특정 방송사의 시보음을 그대로 복제하지 않습니다.

## API

### `GET /health`

```json
{
  "status": "ok"
}
```

### `POST /briefing`

요청:

```json
{
  "topic": "AI",
  "voice_preset": "anchor_female"
}
```

응답 예시:

```json
{
  "topic": "AI",
  "articles": [
    {
      "title": "기사 제목",
      "url": "https://example.com/article",
      "source": "example.com",
      "published_at": "2026-04-13 09:00",
      "snippet": "짧은 요약",
      "content": "브리핑 생성에 사용된 본문 일부"
    }
  ],
  "script": "안녕하세요. 오늘의 AI 1분 브리핑입니다...",
  "tts_engine": "edge-tts",
  "voice_preset": "anchor_female",
  "audio_url": "/audio/xxxxxxxx.mp3"
}
```

지원하는 `voice_preset`:

- `anchor_female`
- `anchor_male`
- `calm`
