// Real PostgreSQL tests. Opt-in, and only against a throwaway database:
//   RUN_NOTIFICATION_DB_TESTS=1 DATABASE_URL=postgresql://.../notifications_check npm test
import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';

import { migrate } from '../src/migrate.js';
import { claimNext, createPool, enqueue } from '../src/queue.js';
import { startSender } from '../src/sender.js';
import { SEND_SETTINGS, SHOP, silentLog, testConfig } from './helpers.js';

const url = process.env.DATABASE_URL || '';
const enabled = process.env.RUN_NOTIFICATION_DB_TESTS === '1';
const sqlPath = new URL('../../../db/migrations/016_order_notifications.sql', import.meta.url);

function row(orderId, extra = {}) {
  return {
    shop: SHOP, orderId, orderName: `#${orderId}`, topic: 'orders/create',
    webhookId: `wh-${orderId}`, recipient: '919876543210', state: 'pending', error: null, ...extra,
  };
}

describe('PostgreSQL queue', { skip: !enabled && 'set RUN_NOTIFICATION_DB_TESTS=1' }, () => {
  let pool;
  before(async () => {
    // Safety: refuse anything but a disposable *_check database.
    assert.match(new URL(url).pathname, /_check$/, 'DATABASE_URL must name a *_check database');
    pool = createPool({ url, ssl: false });
    assert.equal(await migrate(pool, sqlPath), 'applied');
    assert.equal(await migrate(pool, sqlPath), 'already applied');
  });
  after(async () => {
    await pool.query('DROP TABLE order_notifications');
    await pool.query("DELETE FROM schema_migrations WHERE name = 'migrations/016_order_notifications.sql'");
    await pool.end();
  });

  test('saves each order and event only once', async () => {
    assert.equal(await enqueue(pool, row('1')), true);
    assert.equal(await enqueue(pool, row('1', { webhookId: 'retry' })), false);
    assert.equal(await enqueue(pool, row('1', { topic: 'orders/fulfilled' })), true);
  });

  test('two senders never claim the same notification', async () => {
    await pool.query('TRUNCATE order_notifications');
    for (const id of ['10', '11', '12']) await enqueue(pool, row(id));
    const claimed = await Promise.all([claimNext(pool), claimNext(pool), claimNext(pool), claimNext(pool)]);
    const ids = claimed.filter(Boolean).map((n) => n.id);
    assert.equal(ids.length, 3);
    assert.equal(new Set(ids).size, 3);
  });

  test('sender sends pending notifications and records the Meta message id', async () => {
    await pool.query('TRUNCATE order_notifications');
    await enqueue(pool, row('20'));
    await enqueue(pool, row('21', { state: 'skipped', recipient: null }));
    let calls = 0;
    const fetchImpl = async () => {
      calls += 1;
      return new Response(JSON.stringify({ messages: [{ id: `wamid.${calls}` }] }), { status: 200 });
    };
    const { whatsapp } = testConfig(SEND_SETTINGS);
    const sender = startSender({ pool, whatsapp, log: silentLog, fetchImpl });
    for (let i = 0; i < 50 && calls === 0; i += 1) await new Promise((r) => setTimeout(r, 50));
    await sender.stop();

    const { rows } = await pool.query('SELECT order_id, state, message_id, attempts FROM order_notifications ORDER BY order_id');
    assert.deepEqual(rows, [
      { order_id: '20', state: 'accepted', message_id: 'wamid.1', attempts: 1 },
      { order_id: '21', state: 'skipped', message_id: null, attempts: 0 },
    ]);
  });

  test('rate-limited notifications wait before the next attempt', async () => {
    await pool.query('TRUNCATE order_notifications');
    await enqueue(pool, row('30'));
    const fetchImpl = async () => new Response('{}', { status: 429 });
    const { whatsapp } = testConfig(SEND_SETTINGS);
    const sender = startSender({ pool, whatsapp, log: silentLog, fetchImpl });
    await new Promise((r) => setTimeout(r, 300));
    await sender.stop();
    const { rows } = await pool.query(
      "SELECT state, attempts, next_attempt_at > NOW() + interval '50 seconds' AS later FROM order_notifications",
    );
    assert.deepEqual(rows, [{ state: 'pending', attempts: 1, later: true }]);
  });
});
