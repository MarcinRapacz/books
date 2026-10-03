import type { Core } from '@strapi/strapi';
import type { ModerationService } from '../services/moderation';

// Admin API: used by the plugin page in the admin panel.
const moderation = ({ strapi }: { strapi: Core.Strapi }): Core.Controller => {
  const service = () =>
    strapi.plugin('comment-moderation').service<ModerationService>('moderation');

  return {
    async pending(ctx) {
      const page = Math.max(1, Number(ctx.query.page) || 1);
      ctx.body = await service().findPending(page);
    },
    async approve(ctx) {
      ctx.body = await service().setStatus(ctx.params.id, 'approved');
    },
    async reject(ctx) {
      ctx.body = await service().setStatus(ctx.params.id, 'rejected');
    },
  };
};

export default moderation;
