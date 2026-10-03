import type { Core } from '@strapi/strapi';

type CacheHeadersConfig = { maxAge?: number };

// Lets a CDN or the frontend cache anonymous Content API reads; everything else stays private.
const cacheHeaders: Core.MiddlewareFactory<CacheHeadersConfig> = (config) => {
  const maxAge = config.maxAge ?? 60;

  return async (ctx, next) => {
    await next();

    // Status and body are known only after the rest of the stack has finished.
    if (!ctx.path.startsWith('/api/')) {
      return;
    }
    const isPublicRead =
      ctx.method === 'GET' && ctx.status === 200 && !ctx.get('Authorization');

    ctx.set(
      'Cache-Control',
      isPublicRead ? `public, max-age=${maxAge}, stale-while-revalidate=30` : 'no-store'
    );
  };
};

export default cacheHeaders;
