import { factories } from '@strapi/strapi';
import type { Core } from '@strapi/strapi';
import { validateZodSchema, z } from '@strapi/utils';

// Core helpers (sanitizeOutput, transformResponse) are optional in the factory's `this` type.
type CoreController = Core.CoreAPI.Controller.CollectionType;

const parseCommentInput = validateZodSchema(
  z.strictObject({
    body: z.string().trim().min(1).max(2000),
    article: z.string().min(1),
  }),
);

export default factories.createCoreController('api::comment.comment', ({ strapi }) => ({
  async find(ctx) {
    const filters = ctx.query.filters ?? {};
    ctx.query = { ...ctx.query, filters: { $and: [filters, { moderationStatus: 'approved' }] } };
    return super.find(ctx);
  },

  async create(this: CoreController, ctx) {
    const user = ctx.state.user;
    if (!user) return ctx.unauthorized();

    const input = parseCommentInput(ctx.request.body?.data);
    const comment = await strapi.service('api::comment.comment').submit({
      body: input.body,
      articleId: input.article,
      authorId: user.id,
    });

    ctx.status = 201;
    return this.transformResponse(await this.sanitizeOutput(comment, ctx));
  },

  async approve(this: CoreController, ctx) {
    const comment = await strapi.service('api::comment.comment').approve(ctx.params.id);
    return this.transformResponse(await this.sanitizeOutput(comment, ctx));
  },
}));
