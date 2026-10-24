import { createAvatar, createVoice, fetchSpeech, unlockAudio } from './avatar.js';

const $ = (id) => document.getElementById(id);
const QUESTIONS_PER_SESSION = 5;
const LEVELS = ['easy', 'medium', 'hard'];
const PROGRESS_KEY = 'mindsketch_progress';

const state = {
  languages: [],
  lang: 'en-IN',
  englishTopic: null, // set when the topic came from the mic (already translated)
  jobId: null,
  topic: '',
  title: '',
  events: null,
  hls: null,
  videoSrc: null,
  quiz: null,
  readyAnnounced: false,
};

const avatar = createAvatar($('guru'));
const voice = createVoice(avatar, (text) => { $('caption').textContent = text; });
const L = () => state.languages.find((l) => l.code === state.lang) || {};

// ---------- helpers

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`);
  return data;
}

function hint(text, error = false) {
  $('hint').textContent = text || '';
  $('hint').classList.toggle('err', error);
}

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Hold-to-talk on a button. Calls onStart, then onAudio(blob, filename) on release (25 s cap).
function holdMic(button, { onStart, onAudio, onCancel }) {
  let rec = null;
  let chunks = [];
  let timer = null;
  let stream = null;

  async function start(e) {
    e.preventDefault();
    if (rec) return;
    unlockAudio();
    voice.stop();
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      hint('Microphone permission is needed for voice input.', true);
      return;
    }
    chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const type = rec.mimeType || 'audio/webm';
      const ext = type.includes('mp4') ? 'mp4' : type.includes('ogg') ? 'ogg' : 'webm';
      const blob = new Blob(chunks, { type });
      rec = null;
      button.classList.remove('rec');
      if (blob.size < 1500) { onCancel?.(); hint('Hold the 🎤 while you speak, then let go.'); return; }
      onAudio(blob, `speech.${ext}`);
    };
    rec.start();
    button.classList.add('rec');
    onStart?.();
    timer = setTimeout(stop, 25000);
    // If the button was released while permission was being asked, stop right away.
    if (!pressed) stop();
  }
  function stop() {
    clearTimeout(timer);
    if (rec && rec.state === 'recording') rec.stop();
  }
  let pressed = false;
  button.addEventListener('pointerdown', (e) => { pressed = true; start(e); });
  ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => button.addEventListener(ev, () => {
    if (!pressed) return;
    pressed = false;
    stop();
  }));
  button.addEventListener('contextmenu', (e) => e.preventDefault());
}

async function transcribe(blob, filename) {
  const ext = filename.split('.').pop();
  const res = await fetch(`/api/tutor/transcribe?ext=${ext}`, {
    method: 'POST', headers: { 'Content-Type': blob.type || 'application/octet-stream' }, body: blob,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Could not hear that');
  return data; // {transcript, language, english}
}

// ---------- languages

function setLang(code, { announce = false } = {}) {
  if (!state.languages.some((l) => l.code === code)) return;
  state.lang = code;
  document.querySelectorAll('#langs .pill').forEach((b) => b.classList.toggle('active', b.dataset.code === code));
  if (announce) hint(`Language switched to ${L().label}`);
}

async function loadLanguages() {
  state.languages = await api('/api/tutor/languages');
  $('langs').innerHTML = state.languages
    .map((l) => `<button class="pill" data-code="${l.code}">${escapeHtml(l.label)}</button>`)
    .join('');
  $('langs').querySelectorAll('.pill').forEach((b) => b.addEventListener('click', () => setLang(b.dataset.code)));
  setLang(state.lang);
}

// Map a detected language onto the picker; Hinglish speakers are detected as Hindi or English.
function adoptDetected(code) {
  if (state.lang === 'hinglish' && (code === 'hi-IN' || code === 'en-IN')) return;
  if (code && code !== 'en-IN' && code !== state.lang) setLang(code, { announce: true });
}

// ---------- topic input

let detectTimer = null;
$('topic').addEventListener('input', () => {
  state.englishTopic = null;
  clearTimeout(detectTimer);
  const text = $('topic').value.trim();
  if (text.length < 3 || /^[\x00-\x7F]*$/.test(text)) return; // plain ASCII: keep the picked language
  detectTimer = setTimeout(async () => {
    try { adoptDetected((await api('/api/tutor/detect', { text })).language); } catch { /* optional */ }
  }, 600);
});
$('topic').addEventListener('keydown', (e) => { if (e.key === 'Enter') generate(); });

holdMic($('topicMic'), {
  onStart: () => { avatar.set('listening'); hint('Listening… let go when done.'); },
  onCancel: () => avatar.set('idle'),
  onAudio: async (blob, name) => {
    avatar.set('thinking');
    hint('Understanding…');
    try {
      const r = await transcribe(blob, name);
      if (!r.transcript) throw new Error("I couldn't hear any words.");
      $('topic').value = r.transcript;
      state.englishTopic = r.english;
      adoptDetected(r.language);
      hint('');
      avatar.set('idle');
    } catch (err) {
      avatar.set('idle');
      hint(err.message, true);
    }
  },
});

document.querySelectorAll('.suggest').forEach((b) => b.addEventListener('click', () => {
  $('topic').value = b.textContent;
  state.englishTopic = b.textContent;
  generate();
}));

$('go').addEventListener('click', () => generate());

async function generate(topicText) {
  unlockAudio();
  const topic = (topicText ?? $('topic').value).trim();
  if (topic.length < 2) { hint('Type or speak a topic first.', true); return; }
  if (topicText) { $('topic').value = topicText; state.englishTopic = topicText; }
  $('go').disabled = true;
  hint('Starting your lesson…');
  try {
    const r = await api('/api/learn/start', {
      topic,
      language: state.lang,
      english_topic: state.englishTopic || undefined,
    });
    hint('');
    openJob(r.job_id, topic);
    voice.say((L().greeting || '').replace('{topic}', topic), state.lang);
  } catch (err) {
    hint(err.message, true);
  } finally {
    $('go').disabled = false;
  }
}

// ---------- job + video

function resetVideo() {
  state.hls?.destroy();
  state.hls = null;
  state.videoSrc = null;
  const v = $('video');
  v.pause();
  v.removeAttribute('src');
  v.load();
}

function openJob(jobId, topic, lang) {
  state.events?.close();
  resetVideo();
  if (lang) setLang(lang);
  Object.assign(state, { jobId, topic, title: topic, quiz: null, readyAnnounced: false });
  $('quiz').classList.add('hidden');
  $('videoEmpty').classList.remove('hidden');
  $('videoEmpty').textContent = 'Guru is drawing your lesson…';
  $('doubtMic').classList.remove('hidden');
  $('quizMe').disabled = false;
  $('stage').classList.remove('hidden');
  $('stageBar').parentElement.classList.remove('done');

  const es = new EventSource(`/api/jobs/${jobId}/events`);
  state.events = es;
  const on = (type, fn) => es.addEventListener(type, (m) => fn(JSON.parse(m.data)));
  on('snapshot', (s) => {
    // The plan title is English; other languages keep the learner's own wording.
    if (state.lang === 'en-IN') state.title = s.title || state.title;
    showStage(s.stage === 'done' ? 'Ready' : s.stage, s.progress);
    $('sceneDots').innerHTML = s.scenes.map((sc) => `<span class="${sc.status}" title="${escapeHtml(sc.title || '')}"></span>`).join('');
    if (s.status === 'completed' && s.video_url) playVideo(s.video_url, false);
    else if (s.playlist_url) playVideo(s.playlist_url, true);
    if (s.status === 'completed') finished();
    if (s.status === 'failed') failed(s.error?.message);
    if (s.status === 'completed' || s.status === 'failed') es.close();
  });
  on('stage', (e) => showStage(e.label, e.progress));
  on('scene', (e) => {
    const dot = $('sceneDots').children[e.index];
    if (dot) dot.className = e.status;
  });
  on('stream_ready', (e) => playVideo(new URL(e.playlist_url, location.href).pathname, true));
  on('completed', () => { showStage('Ready', 1); finished(); });
  on('failed', (e) => failed(e.message));
}

function showStage(label, progress) {
  $('stageLabel').textContent = label;
  $('stagePct').textContent = `${Math.round((progress || 0) * 100)}%`;
  $('stageBar').style.width = `${(progress || 0) * 100}%`;
}

function finished() {
  $('stageBar').parentElement.classList.add('done');
  showStage('Ready', 1);
}

function failed(message) {
  showStage(`Failed: ${message || 'unknown error'}`, 0);
  hint('The video failed. Try another topic (or check the server log).', true);
}

function playVideo(src, live) {
  if (state.videoSrc) return; // already playing (live stream keeps growing on its own)
  state.videoSrc = src;
  $('videoEmpty').classList.add('hidden');
  const v = $('video');
  if (live && window.Hls && Hls.isSupported()) {
    const hls = new Hls({ startPosition: 0 });
    let recoveries = 0;
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (!data.fatal) return;
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
      else if (data.type === Hls.ErrorTypes.MEDIA_ERROR && recoveries++ < 3) hls.recoverMediaError();
    });
    hls.loadSource(src);
    hls.attachMedia(v);
    state.hls = hls;
  } else {
    v.src = src;
  }
  v.play().catch(() => {});
}

$('video').addEventListener('ended', () => {
  if (!state.jobId || state.quiz) return;
  avatar.set('talking');
  voice.say(L().ready || '', state.lang).then(() => startQuiz());
});

// ---------- doubts

holdMic($('doubtMic'), {
  onStart: () => {
    const v = $('video');
    state.resumeAfterDoubt = !v.paused && !v.ended;
    v.pause();
    avatar.set('listening');
    $('caption').textContent = '…';
  },
  onCancel: () => avatar.set('idle'),
  onAudio: async (blob, name) => {
    avatar.set('thinking');
    try {
      const heard = await transcribe(blob, name);
      if (!heard.transcript) throw new Error(L().retry);
      const lang = heard.language !== 'en-IN' && state.languages.some((l) => l.code === heard.language) && state.lang !== 'hinglish'
        ? heard.language : state.lang;
      $('caption').textContent = `“${heard.transcript}”`;
      const { answer } = await api('/api/tutor/ask', {
        job_id: state.jobId, language: lang, question: heard.transcript, at_seconds: $('video').currentTime || null,
      });
      await voice.say(answer, lang);
    } catch (err) {
      avatar.set('idle');
      hint(err.message, true);
    }
    if (state.resumeAfterDoubt) $('video').play().catch(() => {});
  },
});

// ---------- quiz

$('quizMe').addEventListener('click', () => { unlockAudio(); startQuiz(); });
$('stopTalk').addEventListener('click', () => voice.stop());

function newQuiz() {
  return { n: 0, score: 0, difficulty: 'easy', history: [], weak: [], current: null, next: null, answered: false, lang: state.lang };
}

function fetchQuestion(quiz) {
  const p = api('/api/tutor/quiz/next', {
    job_id: state.jobId, language: quiz.lang, history: quiz.history, difficulty: quiz.difficulty,
  });
  // Have Guru's lines ready before they are needed, so feedback is instant.
  p.then((q) => {
    fetchSpeech(q.question, quiz.lang).catch(() => {});
    fetchSpeech(`${L().right} ${q.explanation}`, quiz.lang).catch(() => {});
    fetchSpeech(`${L().wrong} ${q.explanation}`, quiz.lang).catch(() => {});
  }).catch(() => {});
  return p;
}

async function startQuiz() {
  if (!state.jobId) return;
  if (!$('video').paused) $('video').pause();
  state.quiz = newQuiz();
  $('quiz').classList.remove('hidden');
  await nextQuestion(fetchQuestion(state.quiz));
}

async function nextQuestion(promise) {
  const quiz = state.quiz;
  avatar.set('thinking');
  $('quiz').innerHTML = '<p class="q">Guru is thinking of a question…</p>';
  let q;
  try {
    q = await promise;
  } catch (err) {
    avatar.set('idle');
    $('quiz').innerHTML = `<p class="q">Could not get a question: ${escapeHtml(err.message)}</p><div class="row"><button class="btn" id="retryQ">Try again</button></div>`;
    $('retryQ').onclick = () => nextQuestion(fetchQuestion(quiz));
    return;
  }
  if (state.quiz !== quiz) return;
  quiz.current = q;
  quiz.answered = false;
  quiz.n += 1;
  renderQuestion(q);
  avatar.set('idle');
  voice.say(q.question, quiz.lang);
}

function renderQuestion(q) {
  const quiz = state.quiz;
  $('quiz').innerHTML = `
    <div class="meta"><span>Question ${quiz.n} / ${QUESTIONS_PER_SESSION}</span><span class="level ${q.difficulty}">${q.difficulty}</span></div>
    <p class="q">${escapeHtml(q.question)}</p>
    <div class="opts">${q.options.map((o, i) => `<button class="opt" data-i="${i}"><b>${'ABCD'[i]}</b>${escapeHtml(o)}</button>`).join('')}</div>
    <div class="row"><button class="mic" id="answerMic">🎤 answer by voice</button></div>
    <p class="feedback" id="feedback"></p>`;
  $('quiz').querySelectorAll('.opt').forEach((b) => b.addEventListener('click', () => answer(Number(b.dataset.i))));
  holdMic($('answerMic'), {
    onStart: () => avatar.set('listening'),
    onCancel: () => avatar.set('idle'),
    onAudio: async (blob, name) => {
      if (quiz.answered) return;
      avatar.set('thinking');
      try {
        const heard = await transcribe(blob, name);
        $('feedback').textContent = `“${heard.transcript}”`;
        const g = await api('/api/tutor/grade', {
          job_id: state.jobId, language: quiz.lang, question: q.question, options: q.options,
          answer_text: heard.transcript, correct_index: q.correct_index,
        });
        if (g.chosen_index === null || g.chosen_index === undefined) {
          avatar.set('idle');
          voice.say(L().retry, quiz.lang);
          return;
        }
        answer(g.chosen_index, g.feedback);
      } catch (err) {
        avatar.set('idle');
        $('feedback').textContent = err.message;
      }
    },
  });
}

async function answer(i, spokenFeedback) {
  const quiz = state.quiz;
  const q = quiz.current;
  if (!q || quiz.answered) return;
  quiz.answered = true;
  voice.stop();
  const correct = i === q.correct_index;

  // Instant, local feedback.
  const buttons = $('quiz').querySelectorAll('.opt');
  buttons.forEach((b) => { b.disabled = true; });
  buttons[q.correct_index]?.classList.add('right');
  if (!correct) buttons[i]?.classList.add('wrong');
  avatar.set(correct ? 'celebrate' : 'encourage', 2600);

  quiz.history.push({ question: q.question, chosen: q.options[i], correct, concept: q.concept });
  if (correct) quiz.score += 1; else quiz.weak.push(q.concept);
  recordAnswer(correct);
  const level = LEVELS.indexOf(quiz.difficulty);
  quiz.difficulty = LEVELS[Math.max(0, Math.min(2, level + (correct ? 1 : -1)))];

  const more = quiz.n < QUESTIONS_PER_SESSION;
  const next = more ? fetchQuestion(quiz) : null; // fetch while Guru talks
  const text = spokenFeedback || `${correct ? L().right : L().wrong} ${q.explanation}`;
  $('feedback').textContent = text;
  $('quiz').querySelector('.row').innerHTML = more
    ? '<button class="btn primary" id="nextQ">Next question →</button>'
    : '<button class="btn primary" id="nextQ">See my score</button>';
  let moved = false;
  const go = () => {
    if (moved || state.quiz !== quiz) return;
    moved = true;
    if (more) nextQuestion(next); else summary();
  };
  $('nextQ').onclick = () => { voice.stop(); go(); };
  await voice.say(text, quiz.lang, { after: 'idle' });
  setTimeout(go, 700);
}

function summary() {
  const quiz = state.quiz;
  const weak = [...new Set(quiz.weak)];
  saveTopic({ topic: state.title || state.topic, language: quiz.lang, score: quiz.score, total: QUESTIONS_PER_SESSION, weak });
  const line = (L().summary || '').replace('{score}', quiz.score).replace('{total}', QUESTIONS_PER_SESSION);
  $('quiz').innerHTML = `
    <p class="q">⭐ ${quiz.score} / ${QUESTIONS_PER_SESSION}</p>
    ${weak.length ? `<p>Revise: ${weak.map(escapeHtml).join(', ')}</p>` : '<p>No weak spots this time!</p>'}
    <div class="row"><button class="btn" id="again">Quiz me again</button></div>`;
  $('again').onclick = () => startQuiz();
  avatar.set(quiz.score >= 3 ? 'celebrate' : 'encourage', 3000);
  voice.say(line, quiz.lang);
}

// ---------- progress (localStorage, per browser)

function loadProgress() {
  try {
    const p = JSON.parse(localStorage.getItem(PROGRESS_KEY) || 'null');
    if (p && Array.isArray(p.topics)) return p;
  } catch { /* storage blocked */ }
  return { topics: [], answered: 0, correct: 0, days: [] };
}
function saveProgress(p) {
  try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(p)); } catch { /* storage blocked */ }
  renderProgress(p);
}
const today = () => new Date().toISOString().slice(0, 10);

function recordAnswer(correct) {
  const p = loadProgress();
  p.answered += 1;
  if (correct) p.correct += 1;
  if (!p.days.includes(today())) p.days.push(today());
  saveProgress(p);
}
function saveTopic(entry) {
  const p = loadProgress();
  p.topics.unshift({ ...entry, date: today() });
  p.topics = p.topics.slice(0, 20);
  saveProgress(p);
}
function streak(days) {
  const set = new Set(days);
  let n = 0;
  const d = new Date();
  if (!set.has(today())) d.setDate(d.getDate() - 1); // yesterday still counts
  while (set.has(d.toISOString().slice(0, 10))) { n += 1; d.setDate(d.getDate() - 1); }
  return n;
}
function renderProgress(p = loadProgress()) {
  const acc = p.answered ? Math.round((100 * p.correct) / p.answered) : 0;
  const s = streak(p.days);
  $('progressChip').textContent = `${acc}% · 🔥${s}`;
  $('stats').innerHTML = `<div><b>${acc}%</b>accuracy</div><div><b>🔥${s}</b>day streak</div><div><b>${p.topics.length}</b>topics</div>`;
  const weak = [...new Set(p.topics.flatMap((t) => t.weak || []))].slice(0, 6);
  $('weak').innerHTML = weak.map((w) => `<button class="pill revise">↻ ${escapeHtml(w)}</button>`).join('');
  $('weak').querySelectorAll('.revise').forEach((b, k) => b.addEventListener('click', () => generate(weak[k])));
  $('history').innerHTML = p.topics.slice(0, 8)
    .map((t) => `<li><span>${escapeHtml(t.topic)} <small>${escapeHtml(t.language)} · ${t.date}</small></span><b>${t.score}/${t.total}</b></li>`)
    .join('');
}

// ---------- ready-made lessons (demo backup)

async function loadRecent() {
  try {
    const list = await api('/api/learn/recent');
    if (!list.length) return;
    $('recentWrap').classList.remove('hidden');
    $('recent').innerHTML = list
      .map((j) => `<button class="pill" data-id="${j.job_id}" data-lang="${j.language}">${escapeHtml(j.title)} · ${escapeHtml(j.language)}</button>`)
      .join('');
    $('recent').querySelectorAll('.pill').forEach((b) => b.addEventListener('click', () => {
      unlockAudio();
      openJob(b.dataset.id, b.textContent.split(' · ')[0], b.dataset.lang);
    }));
  } catch { /* optional */ }
}

// ---------- boot

renderProgress();
loadLanguages().catch((err) => hint(`Server not reachable: ${err.message}`, true));
loadRecent();
