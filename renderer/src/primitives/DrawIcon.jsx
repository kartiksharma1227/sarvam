import { useEffect, useState } from 'react';
import {
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { progressAt } from '../engine/timing.js';
import { COLORS, TIMING } from '../theme.js';

const SHAPES = new Set(['path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon']);
const GEOMETRY_ATTRS = new Set([
  'd', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'width', 'height',
  'x1', 'y1', 'x2', 'y2', 'points', 'transform',
]);
const INHERITED = ['fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'fill-rule'];

const pending = new Map(); // url -> Promise<parsed svg>
const loaded = new Map(); // url -> parsed svg

const camel = (name) => name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

// Parse SVG text into a small tree: groups keep their transform, shapes carry their effective style.
function parseSvg(text) {
  const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
  const root = doc.documentElement;
  if (root.nodeName !== 'svg') throw new Error('Icon is not an SVG');

  const rootStyle = { fill: 'black', stroke: 'none', 'stroke-width': '1' };
  const walk = (el, inherited) => {
    const style = { ...inherited };
    for (const name of INHERITED) {
      const v = el.getAttribute(name);
      if (v !== null) style[name] = v;
    }
    const tag = el.nodeName;
    if (SHAPES.has(tag)) {
      const geometry = {};
      for (const attr of el.attributes) {
        if (GEOMETRY_ATTRS.has(attr.name)) geometry[camel(attr.name)] = attr.value;
      }
      return { tag, geometry, style };
    }
    if (tag === 'g' || tag === 'svg') {
      const children = [...el.children].map((c) => walk(c, style)).filter(Boolean);
      return { tag: 'g', transform: tag === 'g' ? el.getAttribute('transform') : null, children };
    }
    return null;
  };

  const viewBox =
    root.getAttribute('viewBox') ||
    `0 0 ${root.getAttribute('width') || 512} ${root.getAttribute('height') || 512}`;
  return { viewBox, tree: walk(root, rootStyle) };
}

function loadSvg(url) {
  if (!pending.has(url)) {
    pending.set(
      url,
      fetch(url)
        .then((res) => {
          if (!res.ok) throw new Error(`Icon ${url}: HTTP ${res.status}`);
          return res.text();
        })
        .then((text) => {
          const svg = parseSvg(text);
          loaded.set(url, svg);
          return svg;
        }),
    );
  }
  return pending.get(url);
}

function resolveUrl(src) {
  return /^https?:\/\//.test(src) ? src : staticFile(src);
}

function renderNode(node, key, outline, fill) {
  if (node.tag === 'g') {
    return (
      <g key={key} transform={node.transform || undefined}>
        {node.children.map((child, i) => renderNode(child, `${key}.${i}`, outline, fill))}
      </g>
    );
  }
  const Tag = node.tag;
  const { style } = node;
  const hasFill = style.fill !== 'none';
  const hasStroke = style.stroke !== 'none';
  // Fill-only shapes (e.g. vectorised PNGs) trace their outline in their own fill colour.
  const strokeColor = hasStroke ? style.stroke : hasFill ? style.fill : COLORS.ink;
  const strokeWidth = hasStroke ? style['stroke-width'] : 2;
  const common = { ...node.geometry, fillRule: style['fill-rule'] };

  return (
    <g key={key}>
      {hasFill && <Tag {...common} fill={style.fill} stroke="none" opacity={fill} />}
      {outline > 0 && (
        <Tag
          {...common}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeLinecap={style['stroke-linecap'] || 'round'}
          strokeLinejoin={style['stroke-linejoin'] || 'round'}
          pathLength={1}
          strokeDasharray="1 1"
          strokeDashoffset={1 - outline}
          opacity={hasStroke ? 1 : 1 - fill}
        />
      )}
    </g>
  );
}

// Icon that traces its outline, then fades its fill in, starting at `start` seconds.
export function DrawIcon({ src, box, start }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const url = src ? resolveUrl(src) : null;
  const [svg, setSvg] = useState(() => (url ? loaded.get(url) : null));
  const [handle] = useState(() => (url && !loaded.has(url) ? delayRender(`Loading icon ${url}`) : null));

  useEffect(() => {
    if (handle === null) return;
    loadSvg(url)
      .then((data) => {
        setSvg(data);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [url, handle]);

  if (!svg) return null;
  const outline = progressAt(frame, fps, start, TIMING.iconOutline);
  const fill = progressAt(frame, fps, start + TIMING.iconOutline * 0.8, TIMING.iconFill);
  if (outline === 0) return null;

  return (
    <svg
      viewBox={svg.viewBox}
      preserveAspectRatio="xMidYMid meet"
      style={{ position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, overflow: 'visible' }}
    >
      {renderNode(svg.tree, 'root', outline, fill)}
    </svg>
  );
}
