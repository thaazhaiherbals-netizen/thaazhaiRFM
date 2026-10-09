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
    // Only storefront orders get a message ("web"); POS, draft and app orders do not.
    source: typeof order.source_name === 'string' ? order.source_name : null,
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

// The shipping address is who receives the parcel, so its name is used first.
function readCustomerName(order) {
  const shipping = order.shipping_address;
  const name =
    shipping?.first_name ||
    String(shipping?.name || '').trim().split(/\s+/)[0] ||
    order.customer?.first_name ||
    order.billing_address?.first_name ||
    '';
  // Meta rejects empty template variables, so fall back to a neutral word.
  return String(name).trim() || 'Customer';
}

// recipient: see toWhatsAppNumber() below; phoneSource: the field it came from.
// consent: true only when checkout saved the note attribute whatsapp_opt_in=true.
// SMS/email marketing consent is NOT treated as WhatsApp consent.
export function readContact(order) {
  const noteAttributes = Array.isArray(order.note_attributes) ? order.note_attributes : [];
  const consent = noteAttributes.some(
    (attribute) =>
      attribute?.name === 'whatsapp_opt_in' && String(attribute.value).toLowerCase() === 'true',
  );

  // First valid number wins, so a blank or mistyped number in one place falls through.
  const shipping = order.shipping_address;
  const billing = order.billing_address;
  const saved = order.customer?.default_address;
  // order.phone has no address of its own; use the shipping, then billing country.
  const orderCountry = shipping?.country_code || billing?.country_code;
  const candidates = [
    // Contact number the buyer typed at checkout for order updates.
    ['phone', order.phone, orderCountry],
    ['shipping_address', shipping?.phone, shipping?.country_code],
    ['billing_address', billing?.phone, billing?.country_code],
    // Saved on the customer profile, so possibly older than this order.
    ['customer_default_address', saved?.phone, saved?.country_code],
  ];
  let recipient = null;
  let phoneSource = null;
  for (const [source, phone, countryCode] of candidates) {
    recipient = toWhatsAppNumber(phone, countryCode);
    if (recipient) {
      phoneSource = source;
      break;
    }
  }

  return { recipient, phoneSource, consent };
}

// Phone in WhatsApp format (digits only, country code first) or null.
// Shopify keeps address phones as typed, e.g. "9243023483" without +91. For an Indian
// address a 10-digit mobile (optionally with a leading 0 or 91) is given the 91 prefix.
// Any other number without a country code is rejected rather than guessed.
export function toWhatsAppNumber(rawPhone, countryCode) {
  const phone = String(rawPhone || '').replace(/[\s().-]/g, '');
  if (/^\+[1-9]\d{7,14}$/.test(phone)) return phone.slice(1);
  if (String(countryCode || '').toUpperCase() === 'IN') {
    const mobile = /^(?:0|91)?([6-9]\d{9})$/.exec(phone);
    if (mobile) return `91${mobile[1]}`;
  }
  return null;
}

// The "shipped" message is only for fully fulfilled orders.
export function isFullyFulfilled(order) {
  return order.fulfillment_status === 'fulfilled';
}
