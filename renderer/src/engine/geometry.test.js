import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  LIMITS,
  barChartLayout,
  beforeAfterLayout,
  boxesOverlap,
  checklistLayout,
  comparisonLayout,
  contentArea,
  cycleLayout,
  flowLayout,
  insideArea,
  isPortrait,
  safeArea,
  scaleLayout,
  statLayout,
  timelineLayout,
  titleBox,
  titleCardLayout,
  vennLayout,
} from './geometry.js';
import { CANVAS, CANVAS_PORTRAIT } from '../theme.js';

// Every check runs on both canvases.
const CANVASES = [
  ['16:9', CANVAS],
  ['9:16', CANVAS_PORTRAIT],
];

function assertClean(name, { boxes }, area) {
  const entries = Object.entries(boxes);
  assert.ok(entries.length > 0, `${name}: no boxes`);
  for (const [key, box] of entries) {
    for (const v of [box.x, box.y, box.w, box.h]) {
      assert.ok(Number.isFinite(v), `${name}: ${key} has non-finite value`);
    }
    assert.ok(box.w > 0 && box.h > 0, `${name}: ${key} has empty size`);
    assert.ok(insideArea(box, area), `${name}: ${key} outside area ${JSON.stringify(box)}`);
  }
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      const [ka, a] = entries[i];
      const [kb, b] = entries[j];
      assert.ok(!boxesOverlap(a, b), `${name}: ${ka} overlaps ${kb}`);
    }
  }
}

// The segment's bounding box (a zero-width box for a vertical or horizontal line).
const segmentBox = (s) => ({
  x: Math.min(s.x1, s.x2),
  y: Math.min(s.y1, s.y2),
  w: Math.abs(s.x2 - s.x1),
  h: Math.abs(s.y2 - s.y1),
});
const segmentLength = (s) => Math.hypot(s.x2 - s.x1, s.y2 - s.y1);

function range(layout) {
  const { min, max } = LIMITS[layout];
  return Array.from({ length: max - min + 1 }, (_, i) => min + i);
}

for (const [aspect, canvas] of CANVASES) {
  test(`${aspect}: title band sits above the content area`, () => {
    const title = titleBox(canvas);
    const content = contentArea(canvas);
    assert.ok(title.y + title.h <= content.y);
    assert.ok(insideArea(title, safeArea(canvas)));
  });

  test(`${aspect}: title card, every icon/subheading combination`, () => {
    for (const hasIcon of [true, false]) {
      for (const hasSubheading of [true, false]) {
        assertClean(`title_card ${hasIcon}/${hasSubheading}`, titleCardLayout({ hasIcon, hasSubheading }, canvas), safeArea(canvas));
      }
    }
  });

  test(`${aspect}: flow, 2-4 nodes with arrows between them`, () => {
    for (const n of range('flow')) {
      const layout = flowLayout(n, canvas);
      assertClean(`flow ${n}`, layout, contentArea(canvas));
      assert.equal(layout.arrows.length, n - 1);
      for (const a of layout.arrows) {
        assert.ok(segmentLength(a) > 60, `flow ${n}: arrow too short`);
        assert.ok(insideArea(segmentBox(a), contentArea(canvas)), `flow ${n}: arrow outside`);
      }
    }
  });

  test(`${aspect}: comparison, 1-3 rows`, () => {
    for (const n of range('comparison')) {
      const layout = comparisonLayout(n, canvas);
      assertClean(`comparison ${n}`, layout, contentArea(canvas));
      assert.ok(insideArea(segmentBox(layout.divider), contentArea(canvas)));
    }
  });

  test(`${aspect}: stat`, () => {
    assertClean('stat', statLayout(canvas), contentArea(canvas));
  });

  test(`${aspect}: scale, 2-5 bands, with and without stat`, () => {
    for (const n of range('scale')) {
      for (const hasStat of [true, false]) {
        assertClean(`scale ${n} stat=${hasStat}`, scaleLayout(n, { hasStat }, canvas), contentArea(canvas));
      }
    }
  });

  test(`${aspect}: checklist, 2-5 items`, () => {
    for (const n of range('checklist')) assertClean(`checklist ${n}`, checklistLayout(n, canvas), contentArea(canvas));
  });

  test(`${aspect}: cycle, 3-5 nodes, arcs avoid nodes`, () => {
    for (const n of range('cycle')) {
      const layout = cycleLayout(n, canvas);
      assertClean(`cycle ${n}`, layout, contentArea(canvas));
      assert.equal(layout.arcs.length, n);
      for (const arc of layout.arcs) {
        assert.ok(arc.length >= 3, `cycle ${n}: arc has too few points`);
        for (const [x, y] of arc) {
          for (const [key, box] of Object.entries(layout.boxes)) {
            assert.ok(!insideArea({ x, y, w: 0, h: 0 }, box), `cycle ${n}: arc point inside ${key}`);
          }
        }
      }
    }
  });

  test(`${aspect}: timeline, 3-5 events`, () => {
    for (const n of range('timeline')) {
      const layout = timelineLayout(n, canvas);
      assertClean(`timeline ${n}`, layout, contentArea(canvas));
      assert.ok(insideArea(segmentBox(layout.line), contentArea(canvas)));
      assert.equal(layout.ticks.length, n);
    }
  });

  test(`${aspect}: venn, circles inside and labels apart`, () => {
    const layout = vennLayout(canvas);
    assertClean('venn', layout, contentArea(canvas));
    assert.equal(layout.circles.length, 2);
    for (const { cx, cy, r } of layout.circles) {
      assert.ok(insideArea({ x: cx - r, y: cy - r, w: 2 * r, h: 2 * r }, contentArea(canvas)), 'circle outside');
    }
    const [a, b] = layout.circles;
    const d = Math.hypot(b.cx - a.cx, b.cy - a.cy);
    assert.ok(d < a.r + b.r && d > 0, 'circles must overlap but not coincide');
  });

  test(`${aspect}: bar chart, 2-6 bars, heights follow the values`, () => {
    for (const n of range('bar_chart')) {
      for (const hasCaption of [true, false]) {
        const values = Array.from({ length: n }, (_, i) => (i + 1) * 10);
        const layout = barChartLayout(values, { hasCaption }, canvas);
        assertClean(`bar_chart ${n} caption=${hasCaption}`, layout, contentArea(canvas));
        const size = (r) => (layout.orientation === 'vertical' ? r.h : r.w);
        for (let i = 1; i < n; i++) assert.ok(size(layout.bars[i]) > size(layout.bars[i - 1]), 'bigger value, bigger bar');
      }
    }
    // Zero and all-equal values still lay out cleanly.
    for (const values of [[0, 0, 0], [5, 5], [0, 100, 3, 0, 50, 7]]) {
      assertClean(`bar_chart ${values}`, barChartLayout(values, {}, canvas), contentArea(canvas));
    }
  });

  test(`${aspect}: before/after, panels apart with an arrow between`, () => {
    const layout = beforeAfterLayout(canvas);
    assertClean('before_after', layout, contentArea(canvas));
    assert.ok(segmentLength(layout.arrow) > 60);
    for (const frame of layout.frames) assert.ok(insideArea(frame, contentArea(canvas)), 'frame outside');
    assert.ok(!boxesOverlap(layout.frames[0], layout.frames[1]), 'panels overlap');
  });
}

test('portrait detection', () => {
  assert.equal(isPortrait(CANVAS), false);
  assert.equal(isPortrait(CANVAS_PORTRAIT), true);
});

test('counts outside the limits are rejected', () => {
  assert.throws(() => flowLayout(1));
  assert.throws(() => flowLayout(5));
  assert.throws(() => checklistLayout(6));
  assert.throws(() => cycleLayout(2));
  assert.throws(() => barChartLayout([1]));
  assert.throws(() => barChartLayout([1, 2, 3, 4, 5, 6, 7]));
});

test('layouts are deterministic', () => {
  assert.deepEqual(cycleLayout(4), cycleLayout(4));
  assert.deepEqual(scaleLayout(5, { hasStat: true }, CANVAS_PORTRAIT), scaleLayout(5, { hasStat: true }, CANVAS_PORTRAIT));
  assert.deepEqual(barChartLayout([3, 1, 2]), barChartLayout([3, 1, 2]));
});
