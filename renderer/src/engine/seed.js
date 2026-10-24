// Stable positive integer seed from a string, so Rough.js wobble is identical on every render.
export function seedFrom(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % 2147483646 + 1;
}
