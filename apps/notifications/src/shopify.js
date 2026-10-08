// Shopify webhook helpers: signature check and reading what the WhatsApp message
// needs from an order. No database or network access here, so it is easy to test.
import crypto from 'node:crypto';

// Shopify signs the raw request body with HMAC-SHA256 and sends it base64-encoded
// in the X-Shopify-Hmac-Sha256 header. The body must be checked before JSON parsing.
export function isValidSignature(rawBody, signatureHeader, secret) {
  if (!signatureHeader || !secret) return false;
  const expected = crypto.createHmac('sha256', secret).update(rawBody).digest();
  const received = Buffer.from(signatureHeader, 'base64');
  // timingSafeEqual throws on different lengths, so compare lengths first.
  return received.length === expected.length && crypto.timingSafeEqual(received, expected);
}

// Everything the notification needs from one order. Returns null when the payload
// has no usable order id (the webhook is then rejected as invalid).
export function readOrder(order) {
  const orderId = readOrderId(order);
  if (!orderId) return null;
  return {
    orderId,
    // Template variable {{1}}: customer's first name.
    customerName: readCustomerName(order),
    // Template variable {{2}}: the order number customers see, e.g. #1001.
    orderNumber: String(order.name || `#${order.order_number || orderId}`),
    // Template variable {{3}}: Shopify order status page for this order.
    statusUrl: typeof order.order_status_url === 'string' ? order.order_status_url : null,
    ...readContact(order),
  };
}

// JavaScript numbers lose digits above 2^53, and Shopify ids can be larger
// (e.g. 820982911946154508 parses as ...500). admin_graphql_api_id is a string,
// "gid://shopify/Order/820982911946154508", so the exact id is read from there.
function readOrderId(order) {
  const fromGid = /^gid:\/\/shopify\/Order\/(\d+)$/.exec(order.admin_graphql_api_id || '');
  if (fromGid) return fromGid[1];
  return Number.isSafeInteger(order.id) ? String(order.id) : null;
}

function readCustomerName(order) {
  const name =
    order.customer?.first_name ||
    order.shipping_address?.first_name ||
    order.billing_address?.first_name ||
    '';
  // Meta rejects empty template variables, so fall back to a neutral word.
  return String(name).trim() || 'Customer';
}

// recipient: phone in WhatsApp format (digits only, country code first) or null.
// consent: true only when checkout saved the note attribute whatsapp_opt_in=true.
// SMS/email marketing consent is NOT treated as WhatsApp consent.
export function readContact(order) {
  const noteAttributes = Array.isArray(order.note_attributes) ? order.note_attributes : [];
  const consent = noteAttributes.some(
    (attribute) =>
      attribute?.name === 'whatsapp_opt_in' && String(attribute.value).toLowerCase() === 'true',
  );

  const rawPhone = order.phone || order.shipping_address?.phone || '';
  const phone = String(rawPhone).replace(/[\s().-]/g, '');
  // International format only (+ country code + number). Without a country code we
  // cannot be sure who we would be messaging, so the order is skipped instead.
  const recipient = /^\+[1-9]\d{7,14}$/.test(phone) ? phone.slice(1) : null;

  return { recipient, consent };
}

// The "shipped" message is only for fully fulfilled orders.
export function isFullyFulfilled(order) {
  return order.fulfillment_status === 'fulfilled';
}
