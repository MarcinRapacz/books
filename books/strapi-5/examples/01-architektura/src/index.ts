import type { Core } from '@strapi/strapi';

export default {
  register({ strapi }: { strapi: Core.Strapi }) {
    // Document Service middlewares must be registered before the app boots
    strapi.documents.use(async (context, next) => {
      strapi.log.info(`[trace]   documents ${context.uid} ${context.action}`);
      return next();
    });
  },

  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    const published = await strapi.documents('api::article.article').count({ status: 'published' });
    strapi.log.info(`[trace] bootstrap: ${published} published articles`);
  },

  destroy({ strapi }: { strapi: Core.Strapi }) {
    strapi.log.info('[trace] destroy: closing resources');
  },
};
