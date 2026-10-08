// All settings come from environment variables (Railway variables in production).
// Read them once at startup through loadConfig() so the rest of the code never
// touches process.env directly.

// Shopify topic -> name of the variable holding the approved WhatsApp template.
export const TEMPLATE_VARIABLES = {
  'orders/create': 'WA_ORDER_TEMPLATE',
  'orders/fulfilled': 'WA_SHIPPED_TEMPLATE',
};

export function loadConfig(env = process.env) {
  const mode = env.NOTIFICATION_MODE || 'receive_only';
  if (mode !== 'receive_only' && mode !== 'send') {
    throw new Error('NOTIFICATION_MODE must be receive_only or send');
  }

  const config = {
    port: Number(env.PORT || 8080),
    // receive_only: verify and log Shopify webhooks, never send WhatsApp messages.
    // send: queue notifications in PostgreSQL and send them through WhatsApp.
    mode,
    shopify: {
      shopDomain: (env.SHOPIFY_SHOP_DOMAIN || '').toLowerCase(),
      webhookSecret: env.SHOPIFY_WEBHOOK_SECRET || '',
    },
    whatsapp: {
      accessToken: env.WA_ACCESS_TOKEN || '',
      phoneNumberId: env.WA_PHONE_NUMBER_ID || '',
      graphVersion: env.WA_GRAPH_VERSION || '',
      language: env.WA_TEMPLATE_LANGUAGE || 'en',
      templates: {
        'orders/create': env.WA_ORDER_TEMPLATE || '',
        // Optional: leave unset until the shipped template is approved.
        'orders/fulfilled': env.WA_SHIPPED_TEMPLATE || '',
      },
    },
    database: {
      url: env.DATABASE_URL || '',
      // Same rule as the Python API: production connections must use TLS.
      ssl: env.APP_ENV === 'production',
    },
  };

  if (mode === 'send') {
    validateSendSettings(config);
  }
  return config;
}

// Fail at startup, not on the first customer order, when send mode is misconfigured.
function validateSendSettings(config) {
  const missing = [];
  if (!config.database.url) missing.push('DATABASE_URL');
  if (!config.whatsapp.accessToken) missing.push('WA_ACCESS_TOKEN');
  if (!config.whatsapp.phoneNumberId) missing.push('WA_PHONE_NUMBER_ID');
  if (!config.whatsapp.graphVersion) missing.push('WA_GRAPH_VERSION');
  if (!config.whatsapp.templates['orders/create']) missing.push('WA_ORDER_TEMPLATE');
  if (missing.length > 0) {
    throw new Error(`Send mode needs these variables: ${missing.join(', ')}`);
  }
  if (!/^v\d+\.\d+$/.test(config.whatsapp.graphVersion)) {
    throw new Error('WA_GRAPH_VERSION must look like v21.0');
  }
}

export function shopifyConfigured(config) {
  return Boolean(config.shopify.shopDomain && config.shopify.webhookSecret);
}
