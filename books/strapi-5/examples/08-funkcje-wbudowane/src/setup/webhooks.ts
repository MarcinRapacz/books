import type { Core } from '@strapi/strapi';

const NAME = 'frontend-revalidate';
const EVENTS = ['entry.publish', 'entry.unpublish', 'entry.delete'];

type Webhook = { id: string; name: string; url: string; headers: Record<string, string>; events: string[]; isEnabled: boolean };
type WebhookStore = {
  findWebhooks(): Promise<Webhook[]>;
  createWebhook(data: Omit<Webhook, 'id' | 'isEnabled'>): Promise<Webhook>;
  updateWebhook(id: string, data: Omit<Webhook, 'id'>): Promise<Webhook | null>;
};
type WebhookRunner = { add(webhook: Webhook): void; update(webhook: Webhook): void };

/**
 * Keeps the frontend revalidation webhook in sync with FRONTEND_WEBHOOK_URL, so every environment
 * gets it from code instead of from clicking in Settings > Webhooks.
 */
export async function ensureFrontendWebhook(strapi: Core.Strapi) {
  const url = process.env.FRONTEND_WEBHOOK_URL;
  if (!url) return;

  const store = strapi.get('webhookStore') as WebhookStore;
  const runner = strapi.get('webhookRunner') as WebhookRunner;
  const existing = (await store.findWebhooks()).find((webhook) => webhook.name === NAME);

  if (!existing) {
    // The store only saves the row; the runner must be told about it, like the admin controller does.
    runner.add(await store.createWebhook({ name: NAME, url, headers: {}, events: EVENTS }));
    strapi.log.info(`Webhook ${NAME} created for ${url}`);
  } else if (existing.url !== url || existing.events.join() !== EVENTS.join()) {
    const updated = await store.updateWebhook(existing.id, { ...existing, url, events: EVENTS });
    if (updated) runner.update(updated);
    strapi.log.info(`Webhook ${NAME} updated to ${url}`);
  }
}
