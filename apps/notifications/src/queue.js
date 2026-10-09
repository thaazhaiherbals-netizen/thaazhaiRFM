// PostgreSQL queue for notifications (table order_notifications, migration 016).
// Every function runs one short statement, so each step commits on its own.
import pg from 'pg';

export function createPool(database) {
  return new pg.Pool({ ...connectionSettings(database), max: 3, connectionTimeoutMillis: 5000 });
}

// Connection string and TLS settings for pg.Pool.
// Supabase URLs end in ?sslmode=require. pg reads that as "verify the certificate
// fully", which fails on Supabase's own CA ("self-signed certificate in certificate
// chain"), and URL settings override the ssl option. So TLS parameters are removed
// from the URL and TLS is set here: encrypted, without CA verification — the same as
// libpq's sslmode=require used by the Python API.
export function connectionSettings(database) {
  // Strip a SQLAlchemy driver suffix (postgresql+psycopg://) in case the API's value is copied.
  const url = new URL(database.url.replace(/^postgres(ql)?\+\w+:\/\//, 'postgresql://'));
  const sslmode = url.searchParams.get('sslmode');
  for (const name of ['sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'uselibpqcompat']) {
    url.searchParams.delete(name);
  }
  const useTls = database.ssl || (sslmode !== null && sslmode !== 'disable');
  return {
    connectionString: url.toString(),
    ssl: useTls ? { rejectUnauthorized: false } : undefined,
  };
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
