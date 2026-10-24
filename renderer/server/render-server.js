// Render service: POST /render {props, outPath} -> renders one scene MP4. Bundles once at startup.
import fs from 'node:fs';
import path from 'node:path';
import express from 'express';
import { RenderCancelled, createBundle, makeRenderCancel, renderScene } from './render-core.js';

const PORT = Number(process.env.PORT || 3100);
const CONCURRENCY = Number(process.env.RENDER_CONCURRENCY || 2);

// Minimal semaphore so only CONCURRENCY renders run at once; the rest queue in order.
let active = 0;
const waiting = [];
async function withSlot(fn) {
  if (active >= CONCURRENCY) await new Promise((resolve) => waiting.push(resolve));
  active++;
  try {
    return await fn();
  } finally {
    active--;
    waiting.shift()?.();
  }
}

console.log('Bundling Remotion project...');
const serveUrl = await createBundle();

const app = express();
app.use(express.json({ limit: '5mb' }));

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', active, queued: waiting.length, concurrency: CONCURRENCY });
});

app.post('/render', async (req, res) => {
  const { props, outPath } = req.body || {};
  if (!props?.scene || typeof outPath !== 'string' || !path.isAbsolute(outPath)) {
    return res.status(400).json({ error: 'Body must be {props: {scene, ...}, outPath: <absolute path>}' });
  }
  // If the backend that asked goes away (crashed, killed, stalled job cancelled), stop rendering:
  // nobody will record the result, and the slot is needed for the resumed job.
  const cancel = makeRenderCancel();
  res.on('close', () => {
    if (!res.writableFinished && !cancel.cancelled) {
      console.warn(`Client went away; cancelling render of ${props.scene.id}`);
      cancel.cancel();
    }
  });
  try {
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    const started = Date.now();
    const result = await withSlot(() => {
      if (cancel.cancelled) throw new RenderCancelled(); // gave up while queued
      return renderScene({ serveUrl, props, outPath, cancel });
    });
    console.log(`Rendered ${props.scene.id} in ${((Date.now() - started) / 1000).toFixed(1)}s -> ${outPath}`);
    res.json(result);
  } catch (err) {
    if (err instanceof RenderCancelled) {
      console.warn(`Cancelled render of ${props.scene.id}`);
      return;
    }
    console.error(`Render failed for ${props.scene.id}:`, err);
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => console.log(`Render service listening on http://localhost:${PORT}`));
