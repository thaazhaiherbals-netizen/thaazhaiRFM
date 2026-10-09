// Background loop that drains the queue: claim one notification, send it, record
// the result, repeat. When the queue is empty it waits 2 seconds before looking again.
import { claimNext, finish } from './queue.js';
import { sendTemplate } from './whatsapp.js';

const IDLE_WAIT_MS = 2000;

export function startSender({ pool, whatsapp, log = console, fetchImpl = fetch }) {
  let running = true;
  let wakeUp = () => {};

  async function sendNext() {
    const notification = await claimNext(pool);
    if (!notification) return false;
    const outcome = await sendTemplate(whatsapp, notification, fetchImpl);
    await finish(pool, notification.id, outcome);
    // Railway shows the "message" field as the log text; the rest are searchable attributes.
    log.info(JSON.stringify({
      message: `WhatsApp ${outcome.state} for ${notification.order_name}`
        + (outcome.error ? ` (${outcome.error})` : ''),
      event: 'whatsapp_send',
      id: notification.id,
      orderNumber: notification.order_name,
      ...outcome,
    }));
    return true;
  }

  const done = (async () => {
    while (running) {
      let sent = false;
      try {
        sent = await sendNext();
      } catch (error) {
        log.error(JSON.stringify({ message: `sender error: ${error.message}`, event: 'sender_error' }));
      }
      if (!sent && running) {
        await new Promise((resolve) => {
          const timer = setTimeout(resolve, IDLE_WAIT_MS);
          wakeUp = () => {
            clearTimeout(timer);
            resolve();
          };
        });
      }
    }
  })();

  return {
    isRunning: () => running,
    // Finishes the message in progress (if any), then stops.
    async stop() {
      running = false;
      wakeUp();
      await done;
    },
  };
}
