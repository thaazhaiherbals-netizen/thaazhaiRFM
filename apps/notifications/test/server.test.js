import assert from 'node:assert/strict';
import { after, before, describe, test } from 'node:test';

import { createServer } from '../src/server.js';
import { SEND_SETTINGS, SHOP, order, postWebhook, silentLog, testConfig } from './helpers.js';

async function start(options) {
  const server = createServer({ log: silentLog, ...options });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, baseUrl: `http://127.0.0.1:${server.address().port}` };
}

describe('receive_only mode', () => {
  let app;
  const logged = [];
  before(async () => {
    app = await start({
      config: testConfig(),
      log: { info: (line) => logged.push(JSON.parse(line)), error() {} },
    });
  });
  after(() => app.server.close());

  test('health and readiness', async () => {
    assert.deepEqual(await (await fetch(`${app.baseUrl}/health`)).json(), { status: 'ok' });
    assert.deepEqual(await (await fetch(`${app.baseUrl}/health/ready`)).json(), {
      status: 'ready', mode: 'receive_only', shopify_configured: true,
    });
  });

  test('logs a signed order event without sending anything', async () => {
    const result = await postWebhook(app.baseUrl, order());
    assert.deepEqual(result, { status: 200, body: { status: 'logged' } });
    assert.equal(logged.at(-1).event, 'shopify_webhook_received');
    assert.equal(logged.at(-1).payload.name, '#1001');
  });

  test('rejects bad signatures, other stores and invalid JSON; ignores other topics', async () => {
    assert.equal((await postWebhook(app.baseUrl, order(), { 'x-shopify-hmac-sha256': 'bad' })).status, 401);
    assert.equal((await postWebhook(app.baseUrl, order(), { 'x-shopify-shop-domain': 'other.myshopify.com' })).status, 403);
    assert.equal((await postWebhook(app.baseUrl, 'not json')).status, 400);
    assert.deepEqual((await postWebhook(app.baseUrl, order(), { 'x-shopify-topic': 'orders/paid' })).body, { status: 'ignored' });
  });

  test('returns 503 until Shopify settings are entered', async () => {
    const unconfigured = await start({ config: testConfig({ SHOPIFY_WEBHOOK_SECRET: '' }) });
    assert.equal((await postWebhook(unconfigured.baseUrl, order())).status, 503);
    const ready = await (await fetch(`${unconfigured.baseUrl}/health/ready`)).json();
    assert.equal(ready.shopify_configured, false);
    unconfigured.server.close();
  });
});

describe('send mode', () => {
  // Fake pool: remembers saved rows and applies the unique (shop, order, topic) rule.
  const rows = new Map();
  const pool = {
    async query(sql, params) {
      if (sql.includes('INSERT INTO order_notifications')) {
        const key = `${params[0]}|${params[1]}|${params[3]}`;
        if (rows.has(key)) return { rowCount: 0, rows: [] };
        rows.set(key, { shop: params[0], recipient: params[5], state: params[6] });
        return { rowCount: 1, rows: [{ id: rows.size }] };
      }
      return { rowCount: 0, rows: [] };
    },
  };
  let app;
  before(async () => {
    app = await start({ config: testConfig(SEND_SETTINGS), pool, sender: { isRunning: () => true } });
  });
  after(() => app.server.close());

  test('queues an opted-in order once, even when Shopify retries the webhook', async () => {
    assert.deepEqual((await postWebhook(app.baseUrl, order())).body, { status: 'pending' });
    assert.deepEqual((await postWebhook(app.baseUrl, order(), { 'x-shopify-webhook-id': 'retry' })).body, { status: 'duplicate' });
    assert.deepEqual(rows.get(`${SHOP}|1001|orders/create`), {
      shop: SHOP, recipient: '919876543210', state: 'pending',
    });
  });

  test('records orders without opt-in as skipped', async () => {
    const result = await postWebhook(app.baseUrl, order({ id: 1002, note_attributes: [] }));
    assert.deepEqual(result.body, { status: 'skipped' });
  });

  test('shipped event is disabled until its template is configured', async () => {
    const result = await postWebhook(app.baseUrl, order({ fulfillment_status: 'fulfilled' }), {
      'x-shopify-topic': 'orders/fulfilled',
    });
    assert.deepEqual(result.body, { status: 'disabled' });
  });

  test('shipped event is queued only for fully fulfilled orders', async () => {
    const shipped = await start({
      config: testConfig({ ...SEND_SETTINGS, WA_SHIPPED_TEMPLATE: 'order_shipped' }),
      pool,
      sender: { isRunning: () => true },
    });
    const headers = { 'x-shopify-topic': 'orders/fulfilled' };
    assert.deepEqual((await postWebhook(shipped.baseUrl, order({ fulfillment_status: 'partial' }), headers)).body, {
      status: 'not_fully_fulfilled',
    });
    assert.deepEqual((await postWebhook(shipped.baseUrl, order({ fulfillment_status: 'fulfilled' }), headers)).body, {
      status: 'pending',
    });
    shipped.server.close();
  });

  test('asks Shopify to retry when the database is down', async () => {
    const broken = await start({
      config: testConfig(SEND_SETTINGS),
      pool: { query: async () => { throw new Error('connection refused'); } },
      sender: { isRunning: () => true },
    });
    assert.equal((await postWebhook(broken.baseUrl, order())).status, 503);
    assert.equal((await fetch(`${broken.baseUrl}/health/ready`)).status, 503);
    broken.server.close();
  });
});
