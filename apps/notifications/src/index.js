// Railway entry point: `npm start`.
// receive_only mode starts only the web server.
// send mode also connects to PostgreSQL and starts the background WhatsApp sender.
import { loadConfig } from './config.js';
import { createPool } from './queue.js';
import { startSender } from './sender.js';
import { createServer } from './server.js';

const config = loadConfig();
const pool = config.mode === 'send' ? createPool(config.database) : null;
const sender = pool ? startSender({ pool, whatsapp: config.whatsapp }) : null;
const server = createServer({ config, pool, sender });

server.listen(config.port, '0.0.0.0', () => {
  console.info(JSON.stringify({
    message: `started in ${config.mode} mode on port ${config.port}`,
    event: 'started', mode: config.mode, port: config.port,
  }));
});

// Railway sends SIGTERM on redeploy: stop taking requests, finish the current
// message, close the database connections, then exit.
async function shutdown() {
  server.close();
  await sender?.stop();
  await pool?.end();
  process.exit(0);
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
