import { factories } from '@strapi/strapi';
import type { Core } from '@strapi/strapi';

// Core helpers (sanitizeOutput, transformResponse) are optional in the factory's `this` type.
type CoreController = Core.CoreAPI.Controller.CollectionType;

export default factories.createCoreController('api::article.article', ({ strapi }) => ({
  async related(this: CoreController, ctx) {
    await this.validateQuery(ctx);
    const query = await this.sanitizeQuery(ctx);

    const articles = await strapi.service('api::article.article').findRelated(ctx.params.id, query);

    const sanitized = await this.sanitizeOutput(articles, ctx);
    return this.transformResponse(sanitized);
  },
}));
