import crypto from 'node:crypto';

import { loadConfig } from '../src/config.js';

export const SECRET = 'test-secret';
export const SHOP = 'thaazhai-test.myshopify.com';

export function testConfig(overrides = {}) {
  return loadConfig({
    SHOPIFY_SHOP_DOMAIN: SHOP,
    SHOPIFY_WEBHOOK_SECRET: SECRET,
    ...overrides,
  });
}

export const SEND_SETTINGS = {
  NOTIFICATION_MODE: 'send',
  DATABASE_URL: 'postgresql://unused@localhost/unused',
  WA_ACCESS_TOKEN: 'token',
  WA_PHONE_NUMBER_ID: '123',
  WA_GRAPH_VERSION: 'v21.0',
  WA_ORDER_TEMPLATE: 'order_confirmed',
};

export function order(extra = {}) {
  return {
    id: 1001,
    name: '#1001',
    phone: '+91 98765 43210',
    note_attributes: [{ name: 'whatsapp_opt_in', value: 'true' }],
    ...extra,
  };
}

// Sends a webhook to a running test server, signed like Shopify does.
export async function postWebhook(baseUrl, body, headers = {}) {
  const raw = typeof body === 'string' ? body : JSON.stringify(body);
  const signature = crypto.createHmac('sha256', SECRET).update(raw).digest('base64');
  const response = await fetch(`${baseUrl}/webhooks/shopify`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-shopify-hmac-sha256': signature,
      'x-shopify-shop-domain': SHOP,
      'x-shopify-topic': 'orders/create',
      'x-shopify-webhook-id': 'webhook-1',
      ...headers,
    },
    body: raw,
  });
  return { status: response.status, body: await response.json() };
}

export const silentLog = { info() {}, error() {} };
