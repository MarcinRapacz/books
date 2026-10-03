import { factories } from '@strapi/strapi';
import type { Core } from '@strapi/strapi';

// Core helpers (sanitizeQuery, sanitizeOutput, transformResponse) are optional in the factory's `this` type.
type CoreController = Core.CoreAPI.Controller.CollectionType;

export default factories.createCoreController('api::article.article', ({ strapi }) => ({
  async mine(this: CoreController, ctx) {
    const user = ctx.state.user as { id: number } | undefined;
    if (!user) {
      return ctx.unauthorized();
    }

    await this.validateQuery(ctx);
    const query = await this.sanitizeQuery(ctx);

    // The ownership filter is added after sanitization, so the client can neither remove it
    // nor trip over the role's missing read access to the user content type.
    const { results, pagination } = await strapi.service('api::article.article').find({
      ...query,
      status: query.status ?? 'draft',
      filters: { $and: [query.filters ?? {}, { author: { id: user.id } }] },
    });

    const sanitized = await this.sanitizeOutput(results, ctx);
    return this.transformResponse(sanitized, { pagination });
  },
}));
