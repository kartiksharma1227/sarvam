"""Small async client for the Sarvam REST API (plain httpx, honours the HTTP proxy env vars).

LANGUAGES is the one table to extend when more languages are added.
"""

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
from pathlib import Path

import httpx
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger("sarvam")

BASE_URL = "https://api.sarvam.ai"
TTS_MODEL = "bulbul:v3"
STT_MODEL = "saaras:v3"
CHAT_MODEL = "sarvam-105b"

# code -> how we talk to Sarvam in that language
LANGUAGES: dict[str, dict] = {
    "en-IN": {
        "label": "English",
        "sarvam_code": "en-IN",
        "speaker": "priya",
        "translate_model": None,
        "translate_mode": None,
        "prompt_name": "simple Indian English",
        "greeting": "Hi, I'm Guru! Let's draw {topic} on the board together.",
        "right": "Well done, that is right!",
        "wrong": "Good try! Let us see why.",
        "retry": "Sorry, I didn't catch that. Please try again.",
        "summary": "You scored {score} out of {total}. Great work today!",
        "ready": "Video is ready! Shall we start the quiz?",
    },
    "hi-IN": {
        "label": "हिन्दी",
        "sarvam_code": "hi-IN",
        "speaker": "shubh",
        "translate_model": "sarvam-translate:v1",
        "translate_mode": "formal",
        "prompt_name": "Hindi (Devanagari script)",
        "greeting": "नमस्ते, मैं गुरु हूँ! चलो, {topic} को बोर्ड पर समझते हैं!",
        "right": "शाबाश, बिल्कुल सही!",
        "wrong": "कोई बात नहीं, चलो समझते हैं।",
        "retry": "माफ़ कीजिए, मैं समझ नहीं पाया। एक बार फिर बोलिए।",
        "summary": "आपने {total} में से {score} सही किए। बहुत बढ़िया!",
        "ready": "वीडियो तैयार है! क्या क्विज़ शुरू करें?",
    },
    "gu-IN": {
        "label": "ગુજરાતી",
        "sarvam_code": "gu-IN",
        "speaker": "kavya",
        "translate_model": "sarvam-translate:v1",
        "translate_mode": "formal",
        "prompt_name": "Gujarati (Gujarati script)",
        "greeting": "નમસ્તે, હું ગુરુ છું! ચાલો, {topic} ને બોર્ડ પર સમજીએ!",
        "right": "શાબાશ, એકદમ સાચું!",
        "wrong": "કોઈ વાંધો નહીં, ચાલો સમજીએ.",
        "retry": "માફ કરશો, હું સમજી શક્યો નહીં. ફરી એકવાર બોલો.",
        "summary": "તમે {total} માંથી {score} સાચા કર્યા. ખૂબ સરસ!",
        "ready": "વીડિયો તૈયાર છે! ક્વિઝ શરૂ કરીએ?",
    },
    "pa-IN": {
        "label": "ਪੰਜਾਬੀ",
        "sarvam_code": "pa-IN",
        "speaker": "simran",
        "translate_model": "sarvam-translate:v1",
        "translate_mode": "formal",
        "prompt_name": "Punjabi (Gurmukhi script)",
        "greeting": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਗੁਰੂ ਹਾਂ! ਚਲੋ, {topic} ਨੂੰ ਬੋਰਡ 'ਤੇ ਸਮਝੀਏ!",
        "right": "ਸ਼ਾਬਾਸ਼, ਬਿਲਕੁਲ ਸਹੀ!",
        "wrong": "ਕੋਈ ਗੱਲ ਨਹੀਂ, ਚਲੋ ਸਮਝੀਏ।",
        "retry": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਂ ਸਮਝ ਨਹੀਂ ਸਕਿਆ। ਇੱਕ ਵਾਰ ਫਿਰ ਬੋਲੋ।",
        "summary": "ਤੁਸੀਂ {total} ਵਿੱਚੋਂ {score} ਸਹੀ ਕੀਤੇ। ਬਹੁਤ ਵਧੀਆ!",
        "ready": "ਵੀਡੀਓ ਤਿਆਰ ਹੈ! ਕੀ ਕੁਇਜ਼ ਸ਼ੁਰੂ ਕਰੀਏ?",
    },
    "hinglish": {
        "label": "Hinglish",
        "sarvam_code": "hi-IN",
        "speaker": "rahul",
        "translate_model": "mayura:v1",
        "translate_mode": "code-mixed",
        "prompt_name": "Hinglish (casual Hindi-English code-mix written in Roman/Latin script)",
        "greeting": "Hello, main Guru hoon! Chalo, {topic} ko board pe samajhte hain!",
        "right": "Shabaash, bilkul sahi!",
        "wrong": "Koi baat nahi, chalo samajhte hain.",
        "retry": "Sorry, main samajh nahi paaya. Ek baar phir boliye.",
        "summary": "Aapne {total} mein se {score} sahi kiye. Bahut badhiya!",
        "ready": "Video ready hai! Quiz shuru karein?",
    },
}
TRANSLATE_LIMIT = {"sarvam-translate:v1": 1900, "mayura:v1": 950}
TTS_LIMIT = 2400


class SarvamError(RuntimeError):
    pass


def lang_info(code: str) -> dict:
    if code not in LANGUAGES:
        raise SarvamError(f"unsupported language {code!r}")
    return LANGUAGES[code]


def public_languages() -> list[dict]:
    return [
        {
            "code": c,
            **{k: v[k] for k in ("label", "speaker", "greeting", "right", "wrong", "retry", "summary", "ready")},
        }
        for c, v in LANGUAGES.items()
    ]


_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        key = os.environ.get("SARVAM_API_KEY", "")
        if not key:
            raise SarvamError("SARVAM_API_KEY is not set (put it in sarvam_ai/.env)")
        _client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=60,
            headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"},
        )
    return _client


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(
    retry=retry_if_exception(_retryable),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, max=4),
    reraise=True,
)
async def _post(path: str, **kwargs) -> dict:
    resp = await client().post(path, **kwargs)
    if resp.status_code >= 400:
        log.warning("Sarvam %s -> %s: %s", path, resp.status_code, resp.text[:500])
    resp.raise_for_status()
    return resp.json()


def chunk_text(text: str, limit: int) -> list[str]:
    """Split at sentence ends so each piece is at most `limit` chars."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    sentences = re.split(r"(?<=[.?!।॥])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        while len(s) > limit:  # one giant sentence: hard split on spaces
            cut = s.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(s[:cut].strip())
            s = s[cut:].strip()
        if cur and len(cur) + 1 + len(s) > limit:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


# ---- speech


async def tts(text: str, lang: str, speaker: str | None = None, pace: float = 1.0) -> list[bytes]:
    """WAV bytes, one per chunk of text."""
    info = lang_info(lang)
    out = []
    for piece in chunk_text(text, TTS_LIMIT):
        body = {
            "text": piece,
            "language_code": info["sarvam_code"],
            "target_language_code": info["sarvam_code"],
            "speaker": (speaker or info["speaker"]).lower(),
            "model": TTS_MODEL,
            "pace": pace,
            "speech_sample_rate": 24000,
        }
        data = await _post("/text-to-speech", json=body)
        audios = data.get("audios") or []
        if not audios:
            raise SarvamError("Sarvam TTS returned no audio")
        out.append(base64.b64decode("".join(audios)))
    return out


async def stt(wav: bytes) -> tuple[str, str]:
    """(transcript, language code like hi-IN)."""
    data = await _post(
        "/speech-to-text",
        files={"file": ("audio.wav", wav, "audio/wav")},
        data={"model": STT_MODEL, "mode": "transcribe"},
    )
    return (data.get("transcript") or "").strip(), data.get("language_code") or "en-IN"


# ---- language


def to_ui_lang(sarvam_code: str | None) -> str:
    """Map a Sarvam language code onto our table (unknown -> en-IN)."""
    return sarvam_code if sarvam_code in LANGUAGES else "en-IN"


async def detect(text: str) -> str:
    data = await _post("/text-lid", json={"input": text[:1000]})
    return to_ui_lang(data.get("language_code"))


async def translate(text: str, target: str, source: str = "en-IN") -> str:
    """Translate between our language codes. Hinglish uses Mayura code-mixed."""
    if not text.strip():
        return text
    tgt = lang_info(target)
    if source == target or (target == "en-IN" and source == "en-IN"):
        return text
    src_code = lang_info(source)["sarvam_code"] if source in LANGUAGES else source
    if target == "en-IN":
        # Into English: Mayura understands code-mixed input best.
        model, mode = "mayura:v1", "formal"
    else:
        model, mode = tgt["translate_model"], tgt["translate_mode"]
    out = []
    for piece in chunk_text(text, TRANSLATE_LIMIT[model]):
        body = {
            "input": piece,
            "source_language_code": src_code,
            "target_language_code": tgt["sarvam_code"],
            "model": model,
            "mode": mode,
        }
        data = await _post("/translate", json=body)
        out.append(data.get("translated_text", "").strip())
    return " ".join(out)


# ---- chat (tutor brain)


def _strict_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()

    def fix(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


def _extract_json(content: str) -> str:
    content = content.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if m:
        content = m.group(1).strip()
    start, end = content.find("{"), content.rfind("}")
    return content[start : end + 1] if start >= 0 and end > start else content


async def chat_json(system: str, user: str, schema_model: type[BaseModel]):
    body = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_model.__name__,
                "strict": True,
                "schema": _strict_schema(schema_model),
            },
        },
        "reasoning_effort": "low",
        "max_tokens": 3000,
        "temperature": 0.5,
    }
    last_err: Exception | None = None
    for attempt in range(3):
        data = await _post("/v1/chat/completions", json=body)
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if content.strip():
            try:
                return schema_model.model_validate_json(_extract_json(content))
            except Exception as exc:  # noqa: BLE001 - malformed JSON: ask again
                last_err = exc
                log.warning("Sarvam chat returned invalid JSON: %s", content[:300])
        else:
            last_err = SarvamError(f"empty content (finish_reason={choice.get('finish_reason')})")
        body["reasoning_effort"] = None  # reasoning may have used the token budget
    raise SarvamError(f"Sarvam chat failed: {last_err}")


# ---- audio helpers (ffmpeg)


def _ffmpeg(args: list[str]) -> None:
    from app.ffmpeg import run_ffmpeg

    run_ffmpeg(["ffmpeg", "-v", "error", "-y", *args])


async def to_wav16k(audio: bytes, suffix: str = ".webm") -> bytes:
    """Any browser recording -> 16 kHz mono WAV (what Saaras wants)."""

    def work() -> bytes:
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / f"in{suffix}", Path(d) / "out.wav"
            src.write_bytes(audio)
            _ffmpeg(["-i", str(src), "-t", "29", "-ac", "1", "-ar", "16000", str(dst)])
            return dst.read_bytes()

    return await asyncio.to_thread(work)


async def wavs_to_file(wavs: list[bytes], out: Path) -> Path:
    """Join WAV chunks into `out` (mp3 or wav, by its suffix)."""

    def work() -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as d:
            inputs = []
            for i, w in enumerate(wavs):
                p = Path(d) / f"c{i}.wav"
                p.write_bytes(w)
                inputs += ["-i", str(p)]
            n = len(wavs)
            filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
            codec = ["-c:a", "libmp3lame", "-b:a", "128k"] if out.suffix == ".mp3" else []
            _ffmpeg([*inputs, "-filter_complex", filt, "-map", "[a]", *codec, str(out)])
        return out

    return await asyncio.to_thread(work)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
