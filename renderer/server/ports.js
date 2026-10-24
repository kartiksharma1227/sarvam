// Ports Remotion serves the bundle on during renders. Its automatic choice can land on a running
// Remotion Studio (:3000, IPv6), so each Remotion call takes its own port from this pool instead.
//
// Ports are handed out round-robin: a port that was just released is reused last, because
// Remotion's static server on it may still be shutting down. Reusing it at once made Chrome
// connect to the closing server ("Visited .../index.html but got no response").
export function createPortPool(base, size) {
  const inUse = new Set();
  let next = 0;

  return {
    acquire() {
      for (let tried = 0; tried < size; tried++) {
        const port = base + ((next + tried) % size);
        if (!inUse.has(port)) {
          inUse.add(port);
          next = (port - base + 1) % size;
          return port;
        }
      }
      throw new Error(`All render ports ${base}-${base + size - 1} are busy`);
    },
    release(port) {
      inUse.delete(port);
    },
    get inUse() {
      return new Set(inUse);
    },
  };
}
