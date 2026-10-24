import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createPortPool } from './ports.js';

test('a released port is not handed out again straight away', () => {
  const pool = createPortPool(3200, 4);
  const a = pool.acquire();
  pool.release(a);
  const b = pool.acquire();
  assert.equal(a, 3200);
  assert.notEqual(b, a);
});

test('ports go round the pool and skip ones in use', () => {
  const pool = createPortPool(3200, 3);
  const first = pool.acquire(); // 3200, kept busy
  const seen = [];
  for (let i = 0; i < 5; i++) {
    const port = pool.acquire();
    seen.push(port);
    pool.release(port);
  }
  assert.equal(first, 3200);
  assert.deepEqual(seen, [3201, 3202, 3201, 3202, 3201]);
});

test('a full pool fails loudly', () => {
  const pool = createPortPool(3200, 2);
  pool.acquire();
  pool.acquire();
  assert.throws(() => pool.acquire(), /All render ports 3200-3201 are busy/);
});
