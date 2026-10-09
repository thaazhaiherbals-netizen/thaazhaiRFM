import assert from 'node:assert/strict';
import { test } from 'node:test';

import { sendTemplate } from '../src/whatsapp.js';
import { SEND_SETTINGS, testConfig } from './helpers.js';

const { whatsapp } = testConfig(SEND_SETTINGS);
const notification = {
  topic: 'orders/create',
  recipient: '919876543210',
  customer_name: 'Priya',
  order_name: '#1001',
  order_status_url: 'https://thaazhai.com/81506271484/orders/abc123/authenticate?key=k9',
  attempts: 1,
};

function fakeFetch(status, body = {}) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(body), { status });
  };
  return { calls, fetchImpl };
}

test('sends name and order number in the body, status path in the button, records the message id', async () => {
  const { calls, fetchImpl } = fakeFetch(200, { messages: [{ id: 'wamid.1' }] });
  const outcome = await sendTemplate(whatsapp, notification, fetchImpl);

  assert.deepEqual(outcome, { state: 'accepted', messageId: 'wamid.1' });
  assert.equal(calls[0].url, 'https://graph.facebook.com/v21.0/123/messages');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer token');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    messaging_product: 'whatsapp',
    to: '919876543210',
    type: 'template',
    template: {
      name: 'order_confirmed',
      language: { code: 'en' },
      components: [
        {
          type: 'body',
          parameters: [
            { type: 'text', text: 'Priya' },
            { type: 'text', text: '#1001' },
          ],
        },
        {
          type: 'button',
          sub_type: 'url',
          index: '0',
          parameters: [{ type: 'text', text: 'abc123/authenticate?key=k9' }],
        },
      ],
    },
  });
});

test('sends the brand image as the header when WA_HEADER_IMAGE_URL is set', async () => {
  const image = 'https://cdn.shopify.com/s/files/1/0815/0627/1484/files/THAAZHAI_LOGO.jpg?v=1';
  const withImage = testConfig({ ...SEND_SETTINGS, WA_HEADER_IMAGE_URL: image }).whatsapp;
  const { calls, fetchImpl } = fakeFetch(200, { messages: [{ id: 'wamid.2' }] });
  await sendTemplate(withImage, notification, fetchImpl);
  const { components } = JSON.parse(calls[0].options.body).template;
  assert.deepEqual(components[0], {
    type: 'header',
    parameters: [{ type: 'image', image: { link: image } }],
  });
  assert.deepEqual(components.map((component) => component.type), ['header', 'body', 'button']);
});

test('a status link that does not match the button base URL is not sent', async () => {
  const { calls, fetchImpl } = fakeFetch(200, { messages: [{ id: 'wamid.1' }] });
  const other = { ...notification, order_status_url: 'https://other.example/orders/abc' };
  assert.deepEqual(await sendTemplate(whatsapp, other, fetchImpl), {
    state: 'failed', error: 'unexpected_order_status_url',
  });
  assert.equal(calls.length, 0);
});

test('rate limit retries later with growing delay, then fails', async () => {
  const { fetchImpl } = fakeFetch(429);
  assert.deepEqual(await sendTemplate(whatsapp, { ...notification, attempts: 1 }, fetchImpl), {
    state: 'pending', error: 'rate_limited', retryAfterSeconds: 60,
  });
  assert.equal((await sendTemplate(whatsapp, { ...notification, attempts: 3 }, fetchImpl)).retryAfterSeconds, 240);
  assert.equal((await sendTemplate(whatsapp, { ...notification, attempts: 5 }, fetchImpl)).state, 'failed');
});

test('Meta rejection fails; server errors and timeouts are unknown (never auto-retried)', async () => {
  assert.deepEqual(await sendTemplate(whatsapp, notification, fakeFetch(400).fetchImpl), {
    state: 'failed', error: 'meta_http_400',
  });
  assert.equal((await sendTemplate(whatsapp, notification, fakeFetch(503).fetchImpl)).state, 'unknown');
  const timeout = async () => {
    throw new Error('timeout');
  };
  assert.equal((await sendTemplate(whatsapp, notification, timeout)).state, 'unknown');
});
