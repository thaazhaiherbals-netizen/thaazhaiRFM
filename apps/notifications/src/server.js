// HTTP routes, using only Node's built-in http module:
//   GET  /health            liveness (process is up)
//   GET  /health/ready      readiness (settings, sender and database are OK)
//   POST /webhooks/shopify  Shopify orders/create and orders/fulfilled webhooks
import http from 'node:http';

import { TEMPLATE_VARIABLES, shopifyConfigured } from './config.js';
import { checkQueue, enqueue } from './queue.js';
import { isFullyFulfilled, isValidSignature, readOrder, statusButtonPath } from './shopify.js';

const MAX_BODY_BYTES = 2_000_000;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// pool and sender are only used in send mode; they are null in receive_only mode.
export function createServer({ config, pool = null, sender = null, log = console }) {
  return http.createServer(async (req, res) => {
    try {
      const path = new URL(req.url, 'http://localhost').pathname;
      let result;
      if (req.method === 'GET' && path === '/health') {
        result = { status: 'ok' };
      } else if (req.method === 'GET' && path === '/health/ready') {
        result = await readiness({ config, pool, sender });
      } else if (req.method === 'POST' && path === '/webhooks/shopify') {
        result = await shopifyWebhook({ req, config, pool, log });
      } else {
        throw new HttpError(404, 'Not found');
      }
      reply(res, 200, result);
    } catch (error) {
      if (!(error instanceof HttpError)) {
        log.error(JSON.stringify({ event: 'request_error', message: error.message }));
      }
      reply(res, error.status || 500, { error: error.status ? error.message : 'Internal error' });
    }
  });
}

async function readiness({ config, pool, sender }) {
  if (config.mode === 'receive_only') {
    return { status: 'ready', mode: config.mode, shopify_configured: shopifyConfigured(config) };
  }
  if (!sender?.isRunning()) throw new HttpError(503, 'Sender is not running');
  if (!shopifyConfigured(config)) throw new HttpError(503, 'Shopify is not configured');
  try {
    await checkQueue(pool);
  } catch {
    throw new HttpError(503, 'Queue database is unavailable');
  }
  return { status: 'ready', mode: config.mode };
}

async function shopifyWebhook({ req, config, pool, log }) {
  const { shopDomain, webhookSecret } = config.shopify;
  if (!shopifyConfigured(config)) throw new HttpError(503, 'Shopify is not configured');

  // 1. Only trust requests signed by Shopify for our own store.
  const rawBody = await readBody(req);
  if (!isValidSignature(rawBody, req.headers['x-shopify-hmac-sha256'], webhookSecret)) {
    throw new HttpError(401, 'Invalid signature');
  }
  if ((req.headers['x-shopify-shop-domain'] || '').toLowerCase() !== shopDomain) {
    throw new HttpError(403, 'Unexpected store');
  }

  // 2. Only order created / order fulfilled events are handled.
  const topic = req.headers['x-shopify-topic'] || '';
  if (!(topic in TEMPLATE_VARIABLES)) return { status: 'ignored' };

  let payload;
  try {
    payload = JSON.parse(rawBody.toString('utf8'));
  } catch {
    throw new HttpError(400, 'Invalid JSON payload');
  }
  const order = payload && typeof payload === 'object' ? readOrder(payload) : null;
  if (!order) throw new HttpError(400, 'Invalid order payload');
  const webhookId = req.headers['x-shopify-webhook-id'] || '';
  const buttonPath = statusButtonPath(order.statusUrl, config.whatsapp.statusButtonBaseUrl);
  const skipReason = whySkipped(order, buttonPath);

  // 3a. receive_only mode: log the event plus what WOULD be sent, without sending.
  // The payload contains customer details, so Railway log access must stay restricted.
  if (config.mode === 'receive_only') {
    log.info(JSON.stringify({
      event: 'shopify_webhook_received',
      topic,
      shop: shopDomain,
      webhookId,
      notification: { ...order, buttonPath, wouldSend: !skipReason, skipReason },
      payload,
    }));
    return { status: 'logged' };
  }

  // 3b. send mode: save a notification row; the sender delivers it in the background.
  if (!config.whatsapp.templates[topic]) return { status: 'disabled' };
  if (topic === 'orders/fulfilled' && !isFullyFulfilled(payload)) {
    return { status: 'not_fully_fulfilled' };
  }
  if (!webhookId) throw new HttpError(400, 'Missing webhook ID');

  let saved;
  try {
    saved = await enqueue(pool, {
      ...order,
      shop: shopDomain,
      topic,
      webhookId,
      state: skipReason ? 'skipped' : 'pending',
      error: skipReason,
    });
  } catch (error) {
    // A non-200 answer makes Shopify retry the webhook later, so nothing is lost.
    log.error(JSON.stringify({ event: 'enqueue_error', message: error.message }));
    throw new HttpError(503, 'Queue unavailable; retry delivery');
  }
  if (!saved) return { status: 'duplicate' };
  return { status: skipReason ? 'skipped' : 'pending' };
}

// null when the message can be sent, otherwise the reason it is not sent.
function whySkipped(order, buttonPath) {
  if (order.source !== 'web') return 'not_website_order';
  if (!order.recipient) return 'no_valid_phone';
  if (!order.statusUrl) return 'no_order_status_url';
  if (!buttonPath) return 'unexpected_order_status_url';
  return null;
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new HttpError(413, 'Payload too large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function reply(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}
