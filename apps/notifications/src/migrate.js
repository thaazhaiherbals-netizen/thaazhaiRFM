// `npm run migrate`: applies ONLY db/migrations/016_order_notifications.sql and
// records it in schema_migrations, the same ledger db/migrate.py uses.
// Never run the full historical migration runner against production.
import crypto from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

import { createPool } from './queue.js';

const NAME = 'migrations/016_order_notifications.sql';
// Same advisory lock id as db/migrate.py so the two runners never overlap.
const LOCK_ID = 748192031;

export async function migrate(pool, sqlPath) {
  const sql = await readFile(sqlPath, 'utf8');
  const checksum = crypto.createHash('sha256').update(sql).digest('hex');
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query('SELECT pg_advisory_xact_lock($1)', [LOCK_ID]);
    await client.query(
      `CREATE TABLE IF NOT EXISTS schema_migrations
         (name TEXT PRIMARY KEY, checksum TEXT NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`,
    );
    const existing = await client.query('SELECT checksum FROM schema_migrations WHERE name = $1', [NAME]);
    if (existing.rows[0]) {
      if (existing.rows[0].checksum !== checksum) {
        throw new Error(`${NAME} changed after it was applied; add a new migration instead`);
      }
      await client.query('ROLLBACK');
      return 'already applied';
    }
    await client.query(sql);
    await client.query('INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)', [NAME, checksum]);
    await client.query('COMMIT');
    return 'applied';
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

// Run directly (npm run migrate), not when imported by the tests.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is required');
  const pool = createPool({
    url: process.env.DATABASE_URL,
    ssl: process.env.APP_ENV === 'production',
  });
  const sqlPath = new URL('../../../db/migrations/016_order_notifications.sql', import.meta.url);
  console.log(`${NAME}: ${await migrate(pool, sqlPath)}`);
  await pool.end();
}
