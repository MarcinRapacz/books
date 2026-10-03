import type { Core } from '@strapi/strapi';

// The route owns its query: client parameters (status, filters, populate) are not passed through.
const latestQuery: Core.MiddlewareHandler = async (ctx, next) => {
  ctx.query = {
    fields: ['title', 'slug', 'excerpt', 'publishedAt'],
    sort: 'publishedAt:desc',
    pagination: { pageSize: 3 },
  };
  await next();
};

export default {
  routes: [
    {
      method: 'GET',
      path: '/articles/latest',
      handler: 'api::article.article.find',
      config: { middlewares: [latestQuery] },
    },
  ],
};
