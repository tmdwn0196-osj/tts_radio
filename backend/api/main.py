from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from backend.data.audio_pipeline import AudioGenerationError, synthesize_brief_audio
from backend.data.briefing import BriefingGenerationError, generate_radio_script
from backend.data.news import NewsSearchError, get_news

app = FastAPI(title="My 1-Minute AI Radio")

audio_dir = Path("backend/data/audio")
audio_dir.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")


class BriefingRequest(BaseModel):
    topic: str
    voice_preset: str = "anchor_female"


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/briefing")
def create_briefing(request: BriefingRequest) -> dict:
    topic = request.topic.strip()
    voice_preset = request.voice_preset.strip() or "anchor_female"

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    try:
        articles = get_news(topic)
        script = generate_radio_script(topic, articles)
        audio_url, tts_engine = synthesize_brief_audio(script, voice_preset)
    except NewsSearchError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except BriefingGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except AudioGenerationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return {
        "topic": topic,
        "articles": articles,
        "script": script,
        "tts_engine": tts_engine,
        "voice_preset": voice_preset,
        "audio_url": audio_url,
    }
