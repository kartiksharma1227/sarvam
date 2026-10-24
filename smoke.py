"""Quick Sarvam checks: backend/.venv/bin/python smoke.py [tts|stt|translate|detect|chat|all]"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "backend")]
os.chdir(HERE / "backend")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE / ".env")

import sarvam  # noqa: E402
from app.ffmpeg import probe_duration  # noqa: E402
from sarvam_tts import SarvamTTS  # noqa: E402
from tutor import Quiz  # noqa: E402

OUT = Path(tempfile.gettempdir()) / "sarvam_smoke"


async def main(which: str) -> None:
    OUT.mkdir(exist_ok=True)
    if which in ("detect", "all"):
        print("detect:", await sarvam.detect("પ્રકાશસંશ્લેષણ શું છે?"))
    if which in ("translate", "all"):
        print("translate gu:", await sarvam.translate("Plants make food from sunlight.", "gu-IN"))
        print("translate hinglish:", await sarvam.translate("Plants make food from sunlight.", "hinglish"))
        print("translate ->en:", await sarvam.translate("पौधे धूप से खाना बनाते हैं।", "en-IN", source="hi-IN"))
    if which in ("tts", "stt", "all"):
        mp3 = OUT / "hindi.mp3"
        r = await SarvamTTS().synthesize("Plants make their own food using sunlight.", mp3, "sarvam:hi-IN:shubh")
        print(f"tts: {mp3} {r.duration:.2f}s, {len(r.words)} words, first={r.words[0]}")
        print("     spoken:", mp3.with_suffix(".txt").read_text())
        wav = await sarvam.to_wav16k(mp3.read_bytes(), ".mp3")
        print("stt:", await sarvam.stt(wav))
    if which in ("chat", "all"):
        q = await sarvam.chat_json(
            "You write one quiz question in Hindi (Devanagari). Short, spoken style.",
            "Topic: photosynthesis. Difficulty easy. Return question, 4 options, correct_index, "
            "explanation, concept (English), difficulty.",
            Quiz,
        )
        print("chat:", q.model_dump())


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "all"))
