// Shopify webhook helpers: signature check and reading the customer contact
// from an order. No database or network access here, so it is easy to test.
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

// Returns { recipient, consent }.
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

// orders/fulfilled also fires for orders that are only partly fulfilled in some
// setups; the "shipped" message is only for fully fulfilled orders.
export function isFullyFulfilled(order) {
  return order.fulfillment_status === 'fulfilled';
}
