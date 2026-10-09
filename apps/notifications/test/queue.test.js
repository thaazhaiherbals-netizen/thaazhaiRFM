import assert from 'node:assert/strict';
import { test } from 'node:test';

import { connectionSettings } from '../src/queue.js';

const SUPABASE =
  'postgresql://postgres.abc:p%40ss@aws-0-ap-south-1.pooler.supabase.com:5432/postgres';

test('sslmode=require in a Supabase URL means encrypted without CA verification', () => {
  const settings = connectionSettings({ url: `${SUPABASE}?sslmode=require`, ssl: true });
  assert.equal(settings.connectionString, SUPABASE);
  assert.deepEqual(settings.ssl, { rejectUnauthorized: false });
});

test('TLS stays on when the URL asks for it even without APP_ENV=production', () => {
  assert.deepEqual(connectionSettings({ url: `${SUPABASE}?sslmode=require`, ssl: false }).ssl, {
    rejectUnauthorized: false,
  });
});

test('local URLs without sslmode connect without TLS; driver suffix and other params kept', () => {
  const settings = connectionSettings({
    url: 'postgresql+psycopg://thaazhai:secret@localhost:5432/thaazhai?application_name=notify',
    ssl: false,
  });
  assert.equal(
    settings.connectionString,
    'postgresql://thaazhai:secret@localhost:5432/thaazhai?application_name=notify',
  );
  assert.equal(settings.ssl, undefined);
});
