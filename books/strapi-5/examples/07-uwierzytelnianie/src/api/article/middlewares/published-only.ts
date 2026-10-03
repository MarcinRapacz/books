import type { Core } from '@strapi/strapi';

/**
 * Public reads always get the published version. Drafts are available only to API tokens
 * (preview, server-side rendering) and to authors through GET /articles/mine.
 */
const publishedOnly: Core.MiddlewareFactory = () => {
  return async (ctx, next) => {
    const strategy = (ctx.state.auth as { strategy?: { name?: string } } | undefined)?.strategy?.name;
    if (strategy !== 'content-api-token') {
      ctx.query = { ...ctx.query, status: 'published' };
    }
    await next();
  };
};

export default publishedOnly;
