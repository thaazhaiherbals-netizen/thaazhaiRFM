import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { test } from 'node:test';

import { loadConfig } from '../src/config.js';
import { isFullyFulfilled, isValidSignature, readContact } from '../src/shopify.js';
import { SEND_SETTINGS, order } from './helpers.js';

test('accepts only the exact Shopify signature', () => {
  const body = Buffer.from('{"id":1}');
  const good = crypto.createHmac('sha256', 'secret').update(body).digest('base64');
  assert.equal(isValidSignature(body, good, 'secret'), true);
  assert.equal(isValidSignature(body, good, 'other-secret'), false);
  assert.equal(isValidSignature(Buffer.from('{"id":2}'), good, 'secret'), false);
  assert.equal(isValidSignature(body, 'short', 'secret'), false);
  assert.equal(isValidSignature(body, undefined, 'secret'), false);
});

test('reads an opted-in international phone', () => {
  assert.deepEqual(readContact(order()), { recipient: '919876543210', consent: true });
});

test('falls back to the shipping address phone', () => {
  const contact = readContact(order({ phone: null, shipping_address: { phone: '+91-98765-43210' } }));
  assert.equal(contact.recipient, '919876543210');
});

test('no recipient without a country code, no consent without the opt-in attribute', () => {
  assert.equal(readContact(order({ phone: '98765 43210' })).recipient, null);
  assert.equal(readContact(order({ note_attributes: [] })).consent, false);
  assert.equal(
    readContact(order({ note_attributes: [{ name: 'whatsapp_opt_in', value: 'false' }] })).consent,
    false,
  );
  assert.equal(readContact(order({ note_attributes: undefined })).consent, false);
});

test('shipped message only for fully fulfilled orders', () => {
  assert.equal(isFullyFulfilled({ fulfillment_status: 'fulfilled' }), true);
  assert.equal(isFullyFulfilled({ fulfillment_status: 'partial' }), false);
});

test('send mode refuses to start with missing or invalid settings', () => {
  assert.throws(() => loadConfig({ NOTIFICATION_MODE: 'send' }), /DATABASE_URL/);
  assert.throws(() => loadConfig({ ...SEND_SETTINGS, WA_GRAPH_VERSION: '21' }), /WA_GRAPH_VERSION/);
  assert.throws(() => loadConfig({ NOTIFICATION_MODE: 'live' }), /NOTIFICATION_MODE/);
  assert.equal(loadConfig({}).mode, 'receive_only');
  assert.equal(loadConfig(SEND_SETTINGS).mode, 'send');
});
