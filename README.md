
# 기사 요약봇

키워드를 입력하면 최신 뉴스 기사를 수집하고, 기사별 요약과 음성 파일을 함께 제공하는
`Streamlit + FastAPI` 기반 대시보드 프로젝트입니다.

# 타겟층
바쁜 현대 사회를 살아가며 아침 시간에 핵심 이슈를 빠르고 간편하게 확인하고자 하는 직장인

# 서비스 목적
출근 준비와 이동으로 바쁜 직장인들에게 최근 주요 소식을 빠르고 간결하게 전달하여, 짧은 시간 안에 필요한 정보만 효율적으로 파악할 수 있도록 돕는 것

# 기획 의도
직장인들은 아침 시간에 뉴스 여러 개를 직접 확인할 여유가 부족하므로, 기사요약봇이 핵심 뉴스만 선별하고 짧게 요약해 음성 또는 텍스트로 제공함으로써 출근길 정보 소비를 더욱 편리하게 만들어주는 서비스

## 프로젝트 구조

```text
news/
├─ backend/
│  ├─ api/
│  │  └─ main.py
│  └─ data/
│     └─ news.py
├─ frontend/
│  └─ streamlit_app.py
├─ shared/
├─ .streamlit/
├─ .env.example
├─ pyproject.toml
├─ requirements.txt
└─ uv.lock
```

## 역할 기준

- `frontend/streamlit_app.py`: Streamlit UI
- `backend/api/main.py`: FastAPI 서버와 API 엔드포인트
- `backend/data/news.py`: 뉴스 수집, 기사 요약, TTS 생성 로직
- `shared/`: 공통 모듈 확장용 폴더

## 주요 기능

- 키워드 기반 뉴스 검색
- 최신 기사 최대 5건 정리
- 기사별 3줄 요약 생성
- 요약 결과 음성(mp3) 생성
- FastAPI API와 Streamlit 화면 분리

## 동작 흐름

1. Streamlit에서 키워드를 입력합니다.
2. 프론트엔드가 FastAPI의 `/summarize`를 호출합니다.
3. 백엔드가 뉴스 기사를 수집하고 요약을 생성합니다.
4. 요약 내용을 바탕으로 음성 파일을 생성합니다.
5. Streamlit에서 기사 요약과 오디오를 함께 보여줍니다.

## 로컬 실행

이 프로젝트는 `uv` 기준으로 관리합니다.

```powershell
uv venv
uv sync
uv run uvicorn backend.api.main:app --reload
uv run streamlit run frontend/streamlit_app.py --server.port 8501
(.env는 .env.example을 참고하여 API_KEY 활용할 것)
```

## 환경 변수

`.env.example` 기준:

```env
APP_ENV=local
API_HOST=127.0.0.1
API_PORT=8000
STREAMLIT_PORT=8501
```

## API

### `GET /health`

서버 상태 확인용 엔드포인트입니다.

응답 예시:

```json
{
  "status": "ok"
}
```

### `POST /summarize`

키워드를 받아 기사 요약 결과와 음성 파일 URL을 반환합니다.

요청 예시:

```json
{
  "keyword": "경제"
}
```

응답 항목:

- `keyword`
- `articles`
- `summary`
- `summary_provider`
- `audio_url`

## 참고

- 가상환경은 `uv sync`로 맞춥니다.
- 오디오 파일은 백엔드에서 생성되며 `/audio/...` 경로로 서빙됩니다.
- README는 현재 저장소에 있는 파일 기준으로 작성되어 있습니다.
