# 기사요약봇

키워드를 입력하면 네이버 최신 기사 5개를 불러와 요약하고,
요약 결과를 음성으로도 들을 수 있는 프로젝트입니다.

## 폴더 구조

```text
news/
|-- backend/
|   |-- api/
|   |   `-- main.py
|   `-- data/
|       `-- news.py
|-- frontend/
|   `-- streamlit_app.py
|-- shared/
|-- .streamlit/
|-- requirements.txt
|-- pyproject.toml
`-- README.md
```

## 파일 설명

- `backend/api/main.py`
  FastAPI 서버 파일입니다.

- `backend/data/news.py`
  네이버 기사 수집, 기사 요약, 음성 생성 로직이 들어있는 파일입니다.

- `frontend/streamlit_app.py`
  Streamlit 화면 파일입니다.

## 동작 흐름

1. Streamlit에서 키워드를 입력합니다.
2. FastAPI의 `/summarize`를 호출합니다.
3. FastAPI가 기사 5개, 요약문, 음성 파일 URL을 반환합니다.
4. Streamlit에서 요약과 기사 목록, 음성을 보여줍니다.

## 실행 방법

```powershell
uv sync
uv run uvicorn backend.api.main:app --reload
uv run streamlit run frontend/streamlit_app.py
```
