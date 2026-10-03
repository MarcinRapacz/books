import { factories } from '@strapi/strapi';
import type { Core } from '@strapi/strapi';

// Demo only: shows where route policies and route middlewares sit in the request path
const traceRouteMiddleware: Core.MiddlewareHandler = async (ctx, next) => {
  strapi.log.info('[trace]   route middleware');
  await next();
};

export default factories.createCoreRouter('api::article.article', {
  config: {
    find: {
      policies: ['global::trace-policy'],
      middlewares: [traceRouteMiddleware],
    },
  },
});
