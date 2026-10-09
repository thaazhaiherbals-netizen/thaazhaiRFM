import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { test } from 'node:test';

import { loadConfig } from '../src/config.js';
import {
  isFullyFulfilled,
  isValidSignature,
  readContact,
  readOrder,
  toWhatsAppNumber,
} from '../src/shopify.js';
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

test('reads the exact order id even when it is too large for a JS number', () => {
  // Shopify's sample order: JSON.parse turns this id into 820982911946154500.
  const payload = JSON.parse(
    '{"id":820982911946154508,"admin_graphql_api_id":"gid://shopify/Order/820982911946154508"}',
  );
  assert.equal(readOrder(payload).orderId, '820982911946154508');
  assert.equal(readOrder({ id: 820982911946154508 }), null);
  assert.equal(readOrder({ id: 42 }).orderId, '42');
});

test('customer name: shipping first name, shipping name, customer, then "Customer"', () => {
  assert.equal(readOrder(order()).customerName, 'Priya');
  assert.equal(readOrder(order({ shipping_address: { first_name: 'Arun' } })).customerName, 'Arun');
  assert.equal(readOrder(order({ shipping_address: { name: ' Meena K ' } })).customerName, 'Meena');
  assert.equal(readOrder(order({ customer: { first_name: '  ' } })).customerName, 'Customer');
  assert.equal(readOrder(order({ order_status_url: undefined })).statusUrl, null);
});

test('Indian address phones without +91 get the 91 prefix; others need a country code', () => {
  assert.equal(toWhatsAppNumber('9243023483', 'IN'), '919243023483');
  assert.equal(toWhatsAppNumber('09243023483', 'IN'), '919243023483');
  assert.equal(toWhatsAppNumber('919243023483', 'IN'), '919243023483');
  assert.equal(toWhatsAppNumber('+44 7700 900123', 'IN'), '447700900123');
  assert.equal(toWhatsAppNumber('9243023483', 'US'), null);
  assert.equal(toWhatsAppNumber('12345', 'IN'), null);
  assert.equal(toWhatsAppNumber(null, 'IN'), null);
});

test('shipping address phone is used before the order phone', () => {
  const contact = readContact(order({
    phone: '+919000000001',
    shipping_address: { phone: '9243023483', country_code: 'IN' },
  }));
  assert.equal(contact.recipient, '919243023483');
});

// Fields copied from the first live website order (#1021, 2026-10-09), customer data replaced.
test('reads the first live website order the same way it will be sent', () => {
  const live = {
    id: 18921794109692,
    admin_graphql_api_id: 'gid://shopify/Order/18921794109692',
    name: '#1021',
    source_name: 'web',
    phone: '+919876543210',
    order_status_url: 'https://thaazhai.com/81506271484/orders/token/authenticate?key=key',
    note_attributes: [{ name: 'GoKwik-Cart', value: 'true' }, { name: '_gk_route', value: 'native' }],
    customer: { first_name: 'Kavya', phone: '+919876543210' },
    shipping_address: { first_name: 'Kavya', name: 'Kavya R', phone: '9876543210', country_code: 'IN' },
  };
  assert.deepEqual(readOrder(live), {
    orderId: '18921794109692',
    source: 'web',
    customerName: 'Kavya',
    orderNumber: '#1021',
    statusUrl: live.order_status_url,
    recipient: '919876543210',
    // The live checkout does not yet ask for WhatsApp opt-in.
    consent: false,
  });
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
