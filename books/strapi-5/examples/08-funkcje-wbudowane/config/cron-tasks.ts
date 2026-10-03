import type { Core } from '@strapi/strapi';

const DAY_MS = 24 * 60 * 60 * 1000;
const pendingDays = Number(process.env.COMMENT_PENDING_DAYS ?? 30);

export default {
  rejectStaleComments: {
    async task({ strapi }: { strapi: Core.Strapi }) {
      const cutoff = new Date(Date.now() - pendingDays * DAY_MS);
      // Comments have no draft & publish nor i18n, so one row is one document
      // and a single bulk UPDATE is safe (see chapter 6).
      const { count } = await strapi.db.query('api::comment.comment').updateMany({
        where: { moderationStatus: 'pending', createdAt: { $lt: cutoff } },
        data: { moderationStatus: 'rejected' },
      });
      strapi.log.info(`[cron] rejectStaleComments: ${count} comment(s) older than ${pendingDays} days rejected`);
    },
    options: {
      rule: process.env.COMMENT_REJECT_RULE ?? '0 0 3 * * *',
      tz: 'Europe/Warsaw',
    },
  },
};
