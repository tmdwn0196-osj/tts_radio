from __future__ import annotations

import asyncio
import os
import re
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FFMPEG_BIN = PROJECT_ROOT / "tools" / "ffmpeg" / "bin"


def _bootstrap_ffmpeg_path() -> None:
    env_bin_dir = os.getenv("FFMPEG_BIN_DIR")
    for raw_dir in (env_bin_dir, str(DEFAULT_FFMPEG_BIN)):
        if not raw_dir:
            continue

        bin_dir = Path(raw_dir).expanduser()
        if not bin_dir.exists():
            continue

        current_path = os.environ.get("PATH", "")
        entries = current_path.split(os.pathsep) if current_path else []
        bin_dir_str = str(bin_dir)
        if bin_dir_str not in entries:
            os.environ["PATH"] = bin_dir_str if not current_path else f"{bin_dir_str}{os.pathsep}{current_path}"
        return


_bootstrap_ffmpeg_path()

import edge_tts
from gtts import gTTS
from pydub import AudioSegment
from pydub.generators import Sine

AUDIO_DIR = Path("backend/data/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

VOICE_PRESETS = {
    "anchor_female": {
        "voice": "ko-KR-SunHiNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
    },
    "anchor_male": {
        "voice": "ko-KR-InJoonNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
    },
    "calm": {
        "voice": "ko-KR-SunHiNeural",
        "rate": "-12%",
        "pitch": "-5Hz",
    },
}


class AudioGenerationError(Exception):
    pass


def _resolve_binary(bin_dir: Path, name: str) -> Path | None:
    for candidate_name in (f"{name}.exe", name):
        candidate = bin_dir / candidate_name
        if candidate.exists():
            return candidate
    return None


def _prepend_to_path(bin_dir: Path) -> None:
    current_path = os.environ.get("PATH", "")
    entries = current_path.split(os.pathsep) if current_path else []
    bin_dir_str = str(bin_dir)
    if bin_dir_str in entries:
        return
    os.environ["PATH"] = bin_dir_str if not current_path else f"{bin_dir_str}{os.pathsep}{current_path}"


def _configure_ffmpeg() -> None:
    candidate_dirs: list[Path] = []
    env_bin_dir = os.getenv("FFMPEG_BIN_DIR")
    if env_bin_dir:
        candidate_dirs.append(Path(env_bin_dir).expanduser())
    candidate_dirs.append(DEFAULT_FFMPEG_BIN)

    for bin_dir in candidate_dirs:
        ffmpeg_path = _resolve_binary(bin_dir, "ffmpeg")
        ffprobe_path = _resolve_binary(bin_dir, "ffprobe")
        if not ffmpeg_path and not ffprobe_path:
            continue

        _prepend_to_path(bin_dir)
        if ffmpeg_path:
            ffmpeg_str = str(ffmpeg_path)
            AudioSegment.converter = ffmpeg_str
            AudioSegment.ffmpeg = ffmpeg_str
        if ffprobe_path:
            AudioSegment.ffprobe = str(ffprobe_path)
        return


_configure_ffmpeg()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _split_script(text: str, max_chars: int = 160) -> list[str]:
    normalized = _clean_text(text)
    if not normalized:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
            continue

        if current:
            chunks.append(current)
        current = sentence

    if current:
        chunks.append(current)

    if not chunks:
        return [normalized]

    return chunks


def _resolve_voice_preset(voice_preset: str) -> dict[str, str]:
    if voice_preset not in VOICE_PRESETS:
        raise AudioGenerationError(f"Unsupported voice preset: {voice_preset}")
    return VOICE_PRESETS[voice_preset]


async def _edge_synthesize_chunk(text: str, output_path: Path, voice_config: dict[str, str]) -> None:
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_config["voice"],
                rate=voice_config["rate"],
                pitch=voice_config["pitch"],
            )
            await communicate.save(str(output_path))
            return
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(3 * (attempt + 1))


def _gtts_synthesize_chunk(text: str, output_path: Path) -> None:
    gTTS(text=text, lang="ko").save(str(output_path))


def _build_signal_intro() -> AudioSegment:
    pip_gain = -10
    short_pip = Sine(1046).to_audio_segment(duration=120).apply_gain(pip_gain).fade_in(8).fade_out(30)
    long_pip = Sine(784).to_audio_segment(duration=260).apply_gain(pip_gain - 1).fade_in(8).fade_out(45)
    gap = AudioSegment.silent(duration=85)
    final_gap = AudioSegment.silent(duration=110)

    return short_pip + gap + short_pip + gap + short_pip + final_gap + long_pip


def _load_segment(path: Path) -> AudioSegment:
    try:
        return AudioSegment.from_file(path)
    except Exception as error:
        raise AudioGenerationError(
            "Failed to read generated audio. Ensure ffmpeg is installed and available in PATH."
        ) from error


def _combine_segments(paths: list[Path], output_path: Path) -> None:
    combined = _build_signal_intro() + AudioSegment.silent(duration=180)

    for index, path in enumerate(paths):
        combined += _load_segment(path)
        if index < len(paths) - 1:
            combined += AudioSegment.silent(duration=240)

    try:
        combined.export(output_path, format="mp3")
    except Exception as error:
        raise AudioGenerationError(
            "Failed to export the final MP3. Ensure ffmpeg is installed and available in PATH."
        ) from error


def _synthesize_with_edge(chunks: list[str], voice_config: dict[str, str], output_path: Path) -> None:
    with tempfile.TemporaryDirectory(dir=AUDIO_DIR) as temp_dir:
        temp_paths: list[Path] = []
        for index, chunk in enumerate(chunks):
            chunk_path = Path(temp_dir) / f"edge_{index:02d}.mp3"
            asyncio.run(_edge_synthesize_chunk(chunk, chunk_path, voice_config))
            temp_paths.append(chunk_path)
        _combine_segments(temp_paths, output_path)


def _synthesize_with_gtts(chunks: list[str], output_path: Path) -> None:
    with tempfile.TemporaryDirectory(dir=AUDIO_DIR) as temp_dir:
        temp_paths: list[Path] = []
        for index, chunk in enumerate(chunks):
            chunk_path = Path(temp_dir) / f"gtts_{index:02d}.mp3"
            _gtts_synthesize_chunk(chunk, chunk_path)
            temp_paths.append(chunk_path)
        _combine_segments(temp_paths, output_path)


def synthesize_brief_audio(script: str, voice_preset: str) -> tuple[str, str]:
    cleaned_script = _clean_text(script)
    if not cleaned_script:
        raise AudioGenerationError("script is required")

    voice_config = _resolve_voice_preset(voice_preset)
    chunks = _split_script(cleaned_script)
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = AUDIO_DIR / filename

    try:
        _synthesize_with_edge(chunks, voice_config, output_path)
        engine = "edge-tts"
    except Exception:
        try:
            _synthesize_with_gtts(chunks, output_path)
            engine = "gtts"
        except Exception as fallback_error:
            raise AudioGenerationError("Failed to generate the audio briefing") from fallback_error

    return f"/audio/{filename}", engine
