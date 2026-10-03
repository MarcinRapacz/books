import type { Core } from '@strapi/strapi';
import type { ModerationService } from '../services/moderation';

// Content API: used by the website.
const comments = ({ strapi }: { strapi: Core.Strapi }): Core.Controller => {
  const service = () =>
    strapi.plugin('comment-moderation').service<ModerationService>('moderation');

  return {
    async findApproved(ctx) {
      ctx.body = { data: await service().findApproved(ctx.params.articleId) };
    },
    async report(ctx) {
      // A reported comment goes back to the moderation queue.
      ctx.body = { data: await service().setStatus(ctx.params.id, 'pending') };
    },
  };
};

export default comments;
