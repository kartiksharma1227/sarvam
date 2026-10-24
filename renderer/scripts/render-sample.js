// Usage: node scripts/render-sample.js [credit-scores|extra-layouts|new-layouts] [--aspect 9:16]
// Renders every scene of a sample to out/<sample>[-9x16]/sNN.mp4, then joins them into one MP4.
// --aspect 9:16 renders the same scenes as vertical (1080x1920) video.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createBundle, renderScene } from '../server/render-core.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const aspectAt = args.indexOf('--aspect');
const aspect = aspectAt === -1 ? '16:9' : args[aspectAt + 1];
const sample = args.find((a, i) => !a.startsWith('--') && (aspectAt === -1 || i !== aspectAt + 1)) || 'credit-scores';
const SIZES = { '16:9': { width: 1920, height: 1080 }, '9:16': { width: 1080, height: 1920 } };
if (!SIZES[aspect]) throw new Error(`Unknown aspect ${aspect} (use 16:9 or 9:16)`);
const scenes = JSON.parse(fs.readFileSync(path.join(ROOT, 'src', 'samples', `${sample}.json`), 'utf8')).map((props) => ({
  ...props,
  options: { ...props.options, aspect, ...SIZES[aspect] },
}));
const outDir = path.join(ROOT, 'out', aspect === '16:9' ? sample : `${sample}-9x16`);
fs.mkdirSync(outDir, { recursive: true });

console.log('Bundling...');
const serveUrl = await createBundle();

const files = [];
for (const [i, props] of scenes.entries()) {
  const outPath = path.join(outDir, `s${String(i + 1).padStart(2, '0')}.mp4`);
  const started = Date.now();
  const { durationInFrames, fps } = await renderScene({ serveUrl, props, outPath });
  console.log(`${props.scene.id} (${props.scene.layout}): ${(durationInFrames / fps).toFixed(1)}s video in ${((Date.now() - started) / 1000).toFixed(1)}s -> ${path.relative(ROOT, outPath)}`);
  files.push(outPath);
}

const listPath = path.join(outDir, 'concat.txt');
fs.writeFileSync(listPath, files.map((f) => `file '${f}'`).join('\n'));
const joined = path.join(outDir, `${path.basename(outDir)}.mp4`);
execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listPath, '-c', 'copy', joined]);
console.log(`Joined -> ${path.relative(ROOT, joined)}`);
