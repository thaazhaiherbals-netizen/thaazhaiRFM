import { statusButtonPath } from './shopify.js';

// Sends one approved WhatsApp template through the Meta Cloud API and turns the
// response into a queue outcome. No database access here.

const MAX_ATTEMPTS = 5;

// The approved templates take two body variables, {{1}} customer first name and
// {{2}} order number (#1001), and the FIRST button is a "Track order" URL button whose
// link ends in {{1}}: the order status path after WA_STATUS_BUTTON_BASE_URL.
// Any other button (e.g. "Call us") is static and needs no parameter.
export function buildMessage({ recipient, templateName, language, customerName, orderNumber, buttonPath }) {
  return {
    messaging_product: 'whatsapp',
    to: recipient,
    type: 'template',
    template: {
      name: templateName,
      language: { code: language },
      components: [
        {
          type: 'body',
          parameters: [
            { type: 'text', text: customerName },
            { type: 'text', text: orderNumber },
          ],
        },
        {
          type: 'button',
          sub_type: 'url',
          index: '0',
          parameters: [{ type: 'text', text: buttonPath }],
        },
      ],
    },
  };
}

// Returns { state, messageId?, error?, retryAfterSeconds? } for queue.finish().
export async function sendTemplate(whatsapp, notification, fetchImpl = fetch) {
  const url =
    `https://graph.facebook.com/${whatsapp.graphVersion}/${whatsapp.phoneNumberId}/messages`;
  const buttonPath = statusButtonPath(
    notification.order_status_url,
    whatsapp.statusButtonBaseUrl,
  );
  // Only possible if WA_STATUS_BUTTON_BASE_URL changed after the row was queued.
  if (!buttonPath) return { state: 'failed', error: 'unexpected_order_status_url' };

  const body = buildMessage({
    recipient: notification.recipient,
    templateName: whatsapp.templates[notification.topic],
    language: whatsapp.language,
    customerName: notification.customer_name,
    orderNumber: notification.order_name,
    buttonPath,
  });

  let response;
  try {
    response = await fetchImpl(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${whatsapp.accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    // Timeout or network drop: Meta may or may not have sent it. Do NOT retry
    // automatically — check in Meta first, to avoid a duplicate customer message.
    return { state: 'unknown', error: 'unknown_send_result' };
  }

  if (response.status === 429) {
    // Rate limited: try again later (1, 2, 4, 8 minutes), give up after 5 attempts.
    if (notification.attempts >= MAX_ATTEMPTS) {
      return { state: 'failed', error: 'rate_limited' };
    }
    const retryAfterSeconds = Math.min(3600, 60 * 2 ** (notification.attempts - 1));
    return { state: 'pending', error: 'rate_limited', retryAfterSeconds };
  }
  if (response.status >= 400 && response.status < 500) {
    // Definite rejection (bad token, template, number...). Fix settings, then requeue.
    return { state: 'failed', error: `meta_http_${response.status}` };
  }
  if (response.status >= 500) {
    // Meta server error: same as a timeout, the result is unknown.
    return { state: 'unknown', error: `unknown_meta_http_${response.status}` };
  }

  try {
    const data = await response.json();
    return { state: 'accepted', messageId: data.messages[0].id };
  } catch {
    return { state: 'unknown', error: 'unknown_send_result' };
  }
}
