import type { Core } from '@strapi/strapi';

interface RequestTraceConfig {
  slowMs?: number;
}

const requestTrace: Core.MiddlewareFactory<RequestTraceConfig> = (config, { strapi }) => {
  const slowMs = config.slowMs ?? 500;

  return async (ctx, next) => {
    const startedAt = Date.now();
    strapi.log.info(`[trace] → ${ctx.method} ${ctx.url}`);

    await next();

    // The router sets ctx.state.route, so it is only readable after next() resolves
    const route = ctx.state.route;
    const target =
      typeof route?.handler === 'string' ? `${route.info.type} ${route.handler}` : 'no controller';
    const elapsed = Date.now() - startedAt;
    const level = elapsed > slowMs ? 'warn' : 'info';
    strapi.log[level](`[trace] ← ${ctx.status} ${ctx.method} ${ctx.path} (${target}, ${elapsed} ms)`);
  };
};

export default requestTrace;
