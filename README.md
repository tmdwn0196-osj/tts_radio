# news

Streamlit + FastAPI 대시보드 프로젝트입니다.

## Project Structure

```text
news/
├─ frontend/
├─ backend/
│  ├─ api/
│  └─ data/
├─ shared/
├─ .streamlit/
├─ .env.example
├─ requirements.txt
└─ pyproject.toml
```

## Suggested Ownership

- `frontend`: 조장(UI, Streamlit 화면)
- `backend/api`: 조원 1(FastAPI API 작업)
- `backend/data`: 조원 2(데이터 처리, 로직 작업)
- `shared`: 같이 쓰는 설정이나 공통 코드

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Team Rules

- 지금은 폴더와 환경설정만 구성
- 실제 앱 코드는 역할을 나눈 뒤 각 브랜치에서 작업
- 공통 설정은 `shared`, `.env.example`, `requirements.txt`, `pyproject.toml` 기준으로 관리
