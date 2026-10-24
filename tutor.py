"""Guru, the tutor: speech in/out, adaptive quiz, grading and doubts (all Sarvam). No login."""

import hashlib
import logging
from typing import Literal

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import sarvam
from app.config import settings
from app.models.job import Job

log = logging.getLogger("tutor")
router = APIRouter(prefix="/api/tutor", tags=["tutor"])

LEVELS = ["easy", "medium", "hard"]
Difficulty = Literal["easy", "medium", "hard"]


def _fail(exc: Exception) -> HTTPException:
    log.exception("Tutor call failed")
    return HTTPException(502, detail=f"Sarvam: {exc}"[:300])


# ---- language + speech


@router.get("/languages")
async def languages() -> list[dict]:
    return sarvam.public_languages()


class DetectIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/detect")
async def detect(body: DetectIn) -> dict:
    try:
        return {"language": await sarvam.detect(body.text)}
    except Exception as exc:
        raise _fail(exc) from exc


@router.post("/transcribe")
async def transcribe(request: Request, ext: str = "webm") -> dict:
    """Body = the raw browser recording (webm/ogg/mp4/wav); `ext` names its container."""
    raw = await request.body()
    if len(raw) < 1000:
        raise HTTPException(400, detail="Recording too short, hold the mic a little longer.")
    if len(raw) > 10_000_000:
        raise HTTPException(413, detail="Recording too long (25 seconds at most).")
    suffix = "." + (ext if ext.isalnum() else "webm")
    try:
        wav = await sarvam.to_wav16k(raw, suffix)
        transcript, code = await sarvam.stt(wav)
        language = sarvam.to_ui_lang(code)
        english = transcript
        if transcript and language != "en-IN":
            english = await sarvam.translate(transcript, "en-IN", source=language)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"transcript": transcript, "language": language, "english": english}


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = "en-IN"
    speaker: str | None = None
    pace: float = Field(1.0, ge=0.5, le=2.0)


@router.post("/speak")
async def speak(body: SpeakIn) -> FileResponse:
    info = sarvam.lang_info(body.language)
    speaker = body.speaker or info["speaker"]
    key = sarvam.dumps([body.text, info["sarvam_code"], speaker, body.pace])
    path = settings.media_dir / "tutor" / f"{hashlib.sha1(key.encode()).hexdigest()}.wav"
    if not path.exists():
        try:
            wavs = await sarvam.tts(body.text, body.language, speaker, body.pace)
            if len(wavs) == 1:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(wavs[0])
            else:
                await sarvam.wavs_to_file(wavs, path)
        except Exception as exc:
            raise _fail(exc) from exc
    return FileResponse(path, media_type="audio/wav")


# ---- lesson context


async def lesson(job_id: str) -> tuple[str, str]:
    """(topic, English script) of a video."""
    try:
        job = await Job.get(PydanticObjectId(job_id))
    except Exception:  # noqa: BLE001
        job = None
    if job is None:
        raise HTTPException(404, detail=f"No job {job_id}")
    title = job.plan.title if job.plan else job.topic
    if job.script:
        script = "\n".join(f"Scene {i + 1}: {s.narration}" for i, s in enumerate(job.script.scenes))
    elif job.plan:
        script = "\n".join(f"Scene {i + 1}: {s.model_dump_json()}" for i, s in enumerate(job.plan.scenes))
    else:
        script = "(the video is still being planned; use general knowledge of the topic)"
    return f"{job.topic} ({title})", script


def lang_rule(language: str) -> str:
    name = sarvam.lang_info(language)["prompt_name"]
    return (
        f"Write EVERY student-facing string in {name}. "
        "It is read aloud by a text-to-speech voice, so use short, warm, spoken-style sentences, "
        "no markdown, no emojis, no bullet points. Keep technical terms simple."
    )


# ---- quiz


class HistoryItem(BaseModel):
    question: str
    chosen: str | None = None
    correct: bool
    concept: str | None = None


class QuizIn(BaseModel):
    job_id: str
    language: str = "en-IN"
    history: list[HistoryItem] = Field(default_factory=list)
    difficulty: Difficulty = "easy"


class Quiz(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    concept: str
    difficulty: Difficulty


@router.post("/quiz/next")
async def quiz_next(body: QuizIn) -> Quiz:
    sarvam.lang_info(body.language)
    topic, script = await lesson(body.job_id)
    last = body.history[-1] if body.history else None
    if last is None:
        adapt = "This is the first question."
    elif last.correct:
        adapt = f"The student got the last question RIGHT (concept: {last.concept}). Move on to a different concept."
    else:
        adapt = (
            f"The student got the last question WRONG (concept: {last.concept}). "
            "Ask about the SAME concept again from a different angle, more simply."
        )
    asked = "\n".join(f"- {h.question}" for h in body.history) or "(none)"
    system = (
        "You are Guru, a friendly tutor for Indian school students. You write one multiple-choice "
        "question at a time about a whiteboard video the student just watched. "
        + lang_rule(body.language)
    )
    user = f"""Topic: {topic}

Video script (English):
{script}

Difficulty for this question: {body.difficulty} (easy = recall a fact from the video, medium = explain why/how, hard = apply it to a new everyday situation).
{adapt}
Questions already asked (never repeat or rephrase these):
{asked}

Return JSON: question (one sentence), options (exactly 4 short options, only one correct), correct_index (0-3),
explanation (1-2 short spoken sentences saying why the right answer is right), concept (2-4 English words naming the concept tested),
difficulty ("{body.difficulty}")."""
    try:
        q: Quiz = await sarvam.chat_json(system, user, Quiz)
    except Exception as exc:
        raise _fail(exc) from exc
    q.options = (q.options + ["—"] * 4)[:4]
    q.correct_index = min(max(q.correct_index, 0), 3)
    q.difficulty = body.difficulty
    return q


class GradeIn(BaseModel):
    job_id: str
    language: str = "en-IN"
    question: str
    options: list[str]
    answer_text: str
    correct_index: int | None = None


class Grade(BaseModel):
    chosen_index: int | None
    correct: bool
    feedback: str


@router.post("/grade")
async def grade(body: GradeIn) -> Grade:
    opts = "\n".join(f"{i} ({'ABCD'[i]}): {o}" for i, o in enumerate(body.options))
    key = f"\nThe correct option is index {body.correct_index}." if body.correct_index is not None else ""
    system = (
        "You grade a student's SPOKEN answer to a multiple-choice question. The answer may be a letter "
        "(A/B/C/D), an ordinal in any Indian language (e.g. 'doosra wala', 'दूसरा वाला' = index 1), or the option's words. "
        + lang_rule(body.language)
    )
    user = f"""Question: {body.question}
Options:
{opts}{key}
Student said: "{body.answer_text}"

Return JSON: chosen_index (0-3, or null if you cannot tell which option they mean), correct (true/false),
feedback (1-2 short warm spoken sentences: praise if right; if wrong, gently give the right answer and why)."""
    try:
        g: Grade = await sarvam.chat_json(system, user, Grade)
    except Exception as exc:
        raise _fail(exc) from exc
    if g.chosen_index is not None and not 0 <= g.chosen_index < len(body.options):
        g.chosen_index = None
    if body.correct_index is not None:
        g.correct = g.chosen_index == body.correct_index
    return g


# ---- doubts


class AskIn(BaseModel):
    job_id: str
    language: str = "en-IN"
    question: str = Field(min_length=1, max_length=2000)
    at_seconds: float | None = None


class Answer(BaseModel):
    answer: str


@router.post("/ask")
async def ask(body: AskIn) -> Answer:
    topic, script = await lesson(body.job_id)
    when = f"The student paused the video at {body.at_seconds:.0f} seconds." if body.at_seconds else ""
    system = (
        "You are Guru, a patient tutor answering a student's doubt about a whiteboard video. "
        "Answer in 2-3 short spoken sentences, grounded in the video's script (you may add simple "
        "everyday examples), then end with one quick check-back question. "
        + lang_rule(body.language)
    )
    user = f"""Topic: {topic}

Video script (English):
{script}

{when}
Student's doubt: "{body.question}"

Return JSON: answer."""
    try:
        return await sarvam.chat_json(system, user, Answer)
    except Exception as exc:
        raise _fail(exc) from exc
