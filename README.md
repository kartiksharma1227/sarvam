# Mindsketch Tutor (Sarvam hackathon prototype)

A no-login tutor page. Pick a language (English / हिन्दी / ગુજરાતી / ਪੰਜਾਬੀ / Hinglish), then type or speak a topic in that language. A whiteboard video streams in with its on-screen text in your language, narrated by a Sarvam Bulbul voice. Guru, a talking avatar, then quizzes you one question at a time, adjusting the difficulty as you go. You can answer by tapping or by voice, and you can hold 🎤 on the video at any time to ask a doubt.

> Sarvam is the whole voice and language layer. Saaras hears the student in any Indian language, Text-LID picks the language, Sarvam-Translate and Mayura localize the lesson's narration and on-screen text (including Hinglish), Bulbul narrates the whiteboard and voices the tutor, and Sarvam-105B runs adaptive quizzes, grading and doubt-solving.

## What was built for this hackathon
Everything in the Sarvam and tutor layer:
- `sarvam.py`, `sarvam_tts.py`: the Sarvam client and Bulbul narration in five languages
- `tutor.py`: language detection, speech to text, Guru's voice, adaptive quizzes, grading and doubts
- `server.py`: the guest server, plus translation of each scene's on-screen text into the lesson language
- `web/`: the tutor page (video, Guru avatar, quiz, doubts, progress)

The whiteboard video pipeline it drives (`backend/app/` and `renderer/`) comes from my earlier project, Mindsketch.

## Requirements
- Python 3.12, Node 20+, ffmpeg, MongoDB on `127.0.0.1:27017`
- Google Chrome (the renderer uses it to draw frames)
- A Sarvam API key and an OpenAI API key

## Setup (once)
```bash
./setup.sh          # backend/.venv, renderer/node_modules, .env
# then fill in SARVAM_API_KEY and OPENAI_API_KEY in .env
```

## Run
```bash
cd renderer && npm run server        # terminal 1: render service on :3100
backend/.venv/bin/python server.py   # terminal 2: http://localhost:8100
```
Open http://localhost:8100. On first start, the bundled icon library (`data/icons.tar.gz`) is imported into the database.

To check the Sarvam key and every Sarvam API, run `backend/.venv/bin/python smoke.py`. You can pass `tts`, `stt`, `translate`, `detect` or `chat` to run a single check.

## Layout
| Piece | Where |
|---|---|
| Sarvam REST client and the `LANGUAGES` table (add languages here) | `sarvam.py` |
| `sarvam:<lang>:<speaker>` voices: translate the English narration, then Bulbul. Words are spread by length, so drawings fall back to even spacing | `sarvam_tts.py` |
| Guest server, `POST /api/learn/start`, `/api/jobs/{id}` and the SSE `/events`; translates on-screen scene text before rendering | `server.py` |
| `/api/tutor/{languages,detect,transcribe,speak,quiz/next,grade,ask}` | `tutor.py` |
| Page: video, Guru avatar, quiz, doubts, progress (localStorage) | `web/` |
| Video pipeline (OpenAI planner → scriptwriter → designer → TTS → render → live HLS) | `backend/app/` |
| Remotion render service (whiteboard scenes → MP4) | `renderer/` |

Finished lessons show up under "Ready-made lessons" on the page, as a demo backup.
