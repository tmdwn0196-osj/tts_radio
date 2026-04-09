from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from backend.data.news import get_news, make_tts, summarize_articles


app = FastAPI(title="News Brief Bot")

audio_dir = Path("backend/data/audio")
audio_dir.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")


class SummarizeRequest(BaseModel):
    keyword: str


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/summarize")
def summarize(request: SummarizeRequest) -> dict:
    keyword = request.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")

    articles = get_news(keyword)
    summary = summarize_articles(articles)
    audio_url = make_tts(keyword, summary, articles)
    summary_provider = articles[0].get("summary_provider", "extractive") if articles else "extractive"

    return {
        "keyword": keyword,
        "articles": articles,
        "summary": summary,
        "summary_provider": summary_provider,
        "audio_url": audio_url,
    }
