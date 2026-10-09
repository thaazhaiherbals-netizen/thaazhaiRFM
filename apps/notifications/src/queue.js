// PostgreSQL queue for notifications (table order_notifications, migration 016).
// Every function runs one short statement, so each step commits on its own.
import pg from 'pg';

export function createPool(database) {
  // Railway/Supabase URLs are plain postgres:// URLs. Strip a SQLAlchemy driver
  // suffix (postgresql+psycopg://) in case the API's value is copied over.
  const connectionString = database.url.replace(/^postgres(ql)?\+\w+:\/\//, 'postgresql://');
  return new pg.Pool({
    connectionString,
    // Encrypt like the Python API (sslmode=require), without CA verification.
    ssl: database.ssl ? { rejectUnauthorized: false } : undefined,
    max: 3,
    connectionTimeoutMillis: 5000,
  });
}

// Saves a notification. Returns false when this order+event was already saved
// (Shopify retried the webhook), so nobody gets the same message twice.
export async function enqueue(pool, notification) {
  const result = await pool.query(
    `INSERT INTO order_notifications
       (shop, order_id, order_name, customer_name, order_status_url,
        topic, webhook_id, recipient, state, error)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
     ON CONFLICT (shop, order_id, topic) DO NOTHING
     RETURNING id`,
    [
      notification.shop,
      notification.orderId,
      notification.orderNumber,
      notification.customerName,
      notification.statusUrl,
      notification.topic,
      notification.webhookId,
      notification.recipient,
      notification.state,
      notification.error,
    ],
  );
  return result.rowCount === 1;
}

// Takes the next due notification and marks it 'sending' BEFORE calling Meta.
// SKIP LOCKED lets two running copies of the service (e.g. during a deploy)
// work safely without picking the same row.
export async function claimNext(pool) {
  const result = await pool.query(
    `UPDATE order_notifications
     SET state = 'sending', attempts = attempts + 1, updated_at = NOW()
     WHERE id = (
       SELECT id FROM order_notifications
       WHERE state = 'pending' AND next_attempt_at <= NOW()
       ORDER BY id
       FOR UPDATE SKIP LOCKED
       LIMIT 1
     )
     RETURNING id, topic, recipient, customer_name, order_name, order_status_url, attempts`,
  );
  return result.rows[0] || null;
}

// Records what happened after calling Meta.
export async function finish(pool, id, outcome) {
  await pool.query(
    `UPDATE order_notifications
     SET state = $2, message_id = $3, error = $4,
         next_attempt_at = NOW() + make_interval(secs => $5), updated_at = NOW()
     WHERE id = $1`,
    [id, outcome.state, outcome.messageId || null, outcome.error || null, outcome.retryAfterSeconds || 0],
  );
}

// Used by /health/ready to prove the table exists and the database is reachable.
export async function checkQueue(pool) {
  await pool.query('SELECT 1 FROM order_notifications LIMIT 1');
}
