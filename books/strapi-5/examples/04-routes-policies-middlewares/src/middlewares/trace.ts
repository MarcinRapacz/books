import type { Core } from '@strapi/strapi';

type TraceConfig = { label?: string };

// Learning aid: shows where in the request a middleware runs. Not meant for production.
const trace: Core.MiddlewareFactory<TraceConfig> = (config, { strapi }) => {
  const label = config.label ?? 'middleware';

  return async (ctx, next) => {
    if (!ctx.path.startsWith('/api/')) {
      return next();
    }
    strapi.log.info(`[trace] ${label}: before next()`);
    try {
      await next();
    } finally {
      strapi.log.info(`[trace] ${label}: after next(), status ${ctx.status}`);
    }
  };
};

export default trace;
