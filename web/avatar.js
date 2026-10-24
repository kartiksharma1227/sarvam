// Guru: an SVG tutor whose state (idle/listening/thinking/talking/celebrate/encourage) drives CSS
// animations, and whose mouth follows the live loudness of whatever Guru is saying.

const SVG = `
<svg viewBox="0 0 200 220" aria-label="Guru, your tutor">
  <circle class="ring" cx="100" cy="95" r="78" fill="none" stroke="#e5533d" stroke-width="4"/>
  <g class="confetti">
    <rect x="30" y="20" width="8" height="5" fill="#f5c518"/><rect x="160" y="30" width="8" height="5" fill="#3b82c4"/>
    <rect x="60" y="5" width="6" height="6" fill="#e5533d"/><rect x="140" y="8" width="7" height="4" fill="#7cc35a"/>
    <rect x="100" y="0" width="6" height="6" fill="#f08c2e"/><rect x="20" y="50" width="6" height="4" fill="#7cc35a"/>
  </g>
  <g class="body">
    <path d="M45 220 Q48 168 100 160 Q152 168 155 220 Z" fill="#f08c2e" stroke="#1f1f1f" stroke-width="3"/>
    <path d="M86 162 L100 182 L114 162" fill="none" stroke="#1f1f1f" stroke-width="3"/>
    <g class="arm-l"><path d="M62 168 Q40 190 46 214" fill="none" stroke="#1f1f1f" stroke-width="9" stroke-linecap="round"/><circle cx="46" cy="214" r="8" fill="#e8b48a" stroke="#1f1f1f" stroke-width="3"/></g>
    <g class="arm-r"><path d="M138 168 Q160 190 154 214" fill="none" stroke="#1f1f1f" stroke-width="9" stroke-linecap="round"/><circle cx="154" cy="214" r="8" fill="#e8b48a" stroke="#1f1f1f" stroke-width="3"/>
      <text class="thumb" x="144" y="236" font-size="22">👍</text></g>
    <g class="head">
      <ellipse cx="100" cy="95" rx="54" ry="60" fill="#e8b48a" stroke="#1f1f1f" stroke-width="3"/>
      <path d="M48 82 Q52 30 100 32 Q148 30 152 82 Q140 56 100 54 Q60 56 48 82 Z" fill="#1f1f1f"/>
      <circle cx="46" cy="100" r="9" fill="#e8b48a" stroke="#1f1f1f" stroke-width="3"/>
      <circle cx="154" cy="100" r="9" fill="#e8b48a" stroke="#1f1f1f" stroke-width="3"/>
      <circle cx="100" cy="70" r="3.5" fill="#e5533d"/>
      <g class="eyes">
        <circle cx="80" cy="92" r="13" fill="#fff" stroke="#1f1f1f" stroke-width="3"/>
        <circle cx="120" cy="92" r="13" fill="#fff" stroke="#1f1f1f" stroke-width="3"/>
        <path d="M93 92 L107 92" stroke="#1f1f1f" stroke-width="3"/>
        <g class="pupils"><circle cx="80" cy="93" r="5" fill="#1f1f1f"/><circle cx="120" cy="93" r="5" fill="#1f1f1f"/></g>
        <g class="lids"><circle cx="80" cy="92" r="12" fill="#e8b48a"/><circle cx="120" cy="92" r="12" fill="#e8b48a"/></g>
      </g>
      <path d="M70 74 Q80 69 90 74 M110 74 Q120 69 130 74" fill="none" stroke="#1f1f1f" stroke-width="3" stroke-linecap="round"/>
      <path d="M78 116 Q100 108 122 116" fill="none" stroke="#1f1f1f" stroke-width="5" stroke-linecap="round"/>
      <ellipse class="mouth" cx="100" cy="130" rx="13" ry="2" fill="#7a2a1d" stroke="#1f1f1f" stroke-width="3"/>
    </g>
  </g>
  <g class="dots3" fill="#1f1f1f"><circle cx="150" cy="30" r="5"/><circle cx="165" cy="22" r="5"/><circle cx="180" cy="14" r="5"/></g>
</svg>`;

export function createAvatar(el) {
  el.innerHTML = SVG;
  const mouth = el.querySelector('.mouth');
  let current = 'idle';
  let timer = null;

  function set(state, holdMs = 0) {
    clearTimeout(timer);
    current = state;
    el.className = `guru ${state}`;
    if (holdMs) timer = setTimeout(() => set('idle'), holdMs);
  }
  function mouthOpen(level) {
    mouth.setAttribute('ry', String(2 + Math.min(1, level) * 14));
  }
  return { set, mouthOpen, get state() { return current; } };
}

// ---- voice: fetch /speak, play it, move the mouth with an AnalyserNode

let ctx = null;
function audioCtx() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}
// Call from a click handler once, so later speech may autoplay.
export function unlockAudio() { try { audioCtx(); } catch { /* no Web Audio */ } }

const cache = new Map(); // "lang|text" -> Promise<Blob>

export function fetchSpeech(text, language) {
  const key = `${language}|${text}`;
  if (!cache.has(key)) {
    const p = fetch('/api/tutor/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language }),
    }).then((r) => {
      if (!r.ok) throw new Error(`speak failed (${r.status})`);
      return r.blob();
    });
    p.catch(() => cache.delete(key));
    cache.set(key, p);
  }
  return cache.get(key);
}

export function createVoice(avatar, onCaption) {
  let playing = null; // { audio, done }

  function stop() {
    if (!playing) return;
    playing.audio.pause();
    playing.done();
    playing = null;
  }

  async function say(text, language, { after = 'idle' } = {}) {
    stop();
    onCaption?.(text);
    if (!text) return;
    const token = {};
    playing = { audio: new Audio(), done: () => {} , token };
    const mine = playing;
    let blob;
    try {
      blob = await fetchSpeech(text, language);
    } catch (err) {
      console.warn(err);
      return;
    }
    if (playing !== mine) return; // interrupted while loading
    const audio = mine.audio;
    audio.src = URL.createObjectURL(blob);
    let analyser = null;
    try {
      const ac = audioCtx();
      const src = ac.createMediaElementSource(audio);
      analyser = ac.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      analyser.connect(ac.destination);
    } catch { analyser = null; }
    const buf = analyser ? new Uint8Array(analyser.fftSize) : null;
    let raf = 0;
    const tick = () => {
      if (analyser) {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += (v - 128) * (v - 128);
        avatar.mouthOpen(Math.sqrt(sum / buf.length) / 30);
      } else {
        avatar.mouthOpen(0.3 + 0.3 * Math.sin(performance.now() / 70));
      }
      raf = requestAnimationFrame(tick);
    };
    return new Promise((resolve) => {
      const finish = () => {
        cancelAnimationFrame(raf);
        avatar.mouthOpen(0);
        URL.revokeObjectURL(audio.src);
        if (playing === mine) playing = null;
        if (avatar.state === 'talking') avatar.set(after);
        resolve();
      };
      mine.done = finish;
      audio.onended = finish;
      audio.onerror = finish;
      if (!['celebrate', 'encourage'].includes(avatar.state)) avatar.set('talking');
      tick();
      audio.play().catch((err) => { console.warn('autoplay blocked', err); finish(); });
    });
  }

  return { say, stop, isTalking: () => !!playing };
}
