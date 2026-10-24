// Shared by the render server and the sample script: bundle the Remotion project once, render many scenes.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { bundle } from '@remotion/bundler';
import { makeCancelSignal, renderMedia, selectComposition } from '@remotion/renderer';
import { createPortPool } from './ports.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const COMPOSITION_ID = 'Scene';

// Remotion's bundled headless-shell crashes on macOS 27, so prefer a full Chrome in new headless mode.
// REMOTION_BROWSER overrides the path; set it to "bundled" to use Remotion's own download.
const SYSTEM_CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function browserOptions() {
  const configured = process.env.REMOTION_BROWSER;
  if (configured === 'bundled') return {};
  const executable = configured || (fs.existsSync(SYSTEM_CHROME) ? SYSTEM_CHROME : null);
  return executable ? { browserExecutable: executable, chromeMode: 'chrome-for-testing' } : {};
}

const BROWSER = browserOptions();

const PORTS = createPortPool(Number(process.env.REMOTION_SERVE_PORT || 3200), 16);

// Encode settings must be identical for every scene so segments concat and stream cleanly.
const ENCODE = {
  codec: 'h264',
  audioCodec: 'aac',
  imageFormat: 'jpeg',
  enforceAudioTrack: true,
  sampleRate: 48000,
  gopSize: 30,
  crf: 20,
};

export async function createBundle() {
  return bundle({
    entryPoint: path.join(ROOT, 'src', 'index.js'),
    publicDir: path.join(ROOT, 'public'),
  });
}

// Each Remotion call serves the bundle on its own port, released when the call ends.
async function withPort(fn) {
  const port = PORTS.acquire();
  try {
    return await fn(port);
  } finally {
    PORTS.release(port);
  }
}

// Failures where the page never loaded (a port problem), not a problem with the scene itself.
const PORT_FAILURE = /got no response|EADDRINUSE|ECONNREFUSED|ECONNRESET/;

// Thrown when the caller cancelled the render (e.g. the backend that asked for it went away).
export class RenderCancelled extends Error {
  constructor() {
    super('render cancelled');
  }
}

// A cancel handle the caller keeps: cancel() stops the render if it started, or stops it starting.
export function makeRenderCancel() {
  const { cancelSignal, cancel } = makeCancelSignal();
  const handle = {
    cancelled: false,
    cancelSignal,
    cancel() {
      handle.cancelled = true;
      cancel();
    },
  };
  return handle;
}

async function renderOnce({ serveUrl, props, outPath, onProgress, cancel }) {
  const composition = await withPort((port) =>
    selectComposition({ ...BROWSER, port, serveUrl, id: COMPOSITION_ID, inputProps: props }),
  );
  if (cancel?.cancelled) throw new RenderCancelled();
  await withPort((port) =>
    renderMedia({
      ...ENCODE,
      ...BROWSER,
      port,
      serveUrl,
      composition,
      inputProps: props,
      outputLocation: outPath,
      overwrite: true,
      cancelSignal: cancel?.cancelSignal,
      onProgress: onProgress ? ({ progress }) => onProgress(progress) : undefined,
    }),
  );
  return { outPath, durationInFrames: composition.durationInFrames, fps: composition.fps };
}

export async function renderScene(options) {
  try {
    return await runOnce(options);
  } catch (err) {
    if (err instanceof RenderCancelled || !PORT_FAILURE.test(String(err?.message))) throw err;
    console.warn(`Render of ${options.props?.scene?.id} hit a port problem (${err.message}); retrying on a fresh port`);
    return runOnce(options);
  }
}

// One attempt; a cancelled render leaves no half-written file behind.
async function runOnce(options) {
  try {
    return await renderOnce(options);
  } catch (err) {
    if (options.cancel?.cancelled) {
      fs.rmSync(options.outPath, { force: true });
      throw new RenderCancelled();
    }
    throw err;
  }
}
