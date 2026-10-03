import type { Core } from '@strapi/strapi';

type RateLimitConfig = { max?: number; windowMs?: number };
type Window = { count: number; resetAt: number };

// In-memory fixed window: good for one instance; several replicas need a shared store (Redis).
const rateLimit: Core.MiddlewareFactory<RateLimitConfig> = (config, { strapi }) => {
  const max = config.max ?? 5;
  const windowMs = config.windowMs ?? 60_000;
  const windows = new Map<string, Window>();

  return async (ctx, next) => {
    const user = ctx.state.user;
    const key = user ? `user:${user.id}` : `ip:${ctx.request.ip}`;
    const now = Date.now();

    let window = windows.get(key);
    if (!window || window.resetAt <= now) {
      window = { count: 0, resetAt: now + windowMs };
      windows.set(key, window);
    }
    window.count += 1;

    ctx.set('X-RateLimit-Limit', String(max));
    ctx.set('X-RateLimit-Remaining', String(Math.max(0, max - window.count)));

    if (window.count > max) {
      const retryAfter = Math.ceil((window.resetAt - now) / 1000);
      ctx.set('Retry-After', String(retryAfter));
      strapi.log.warn(`[rate-limit] ${key} blocked on ${ctx.method} ${ctx.path}`);
      return ctx.tooManyRequests('Too many comments, try again later', { retryAfter });
    }

    await next();
  };
};

export default rateLimit;
