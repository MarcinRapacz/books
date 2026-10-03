import type { Core } from '@strapi/strapi';

// Merged over config/server.ts when NODE_ENV=production, so only the differences live here.
const config = ({ env }: Core.Config.Shared.ConfigParams): Partial<Core.Config.Server> => {
  const publicUrl = env('PUBLIC_URL');
  if (!publicUrl) {
    throw new Error('PUBLIC_URL is required in production (e.g. https://api.example.com)');
  }

  return {
    // Absolute URLs (password reset, OAuth callbacks) are built from it, not from the request.
    url: publicUrl,
    proxy: {
      // Trust X-Forwarded-* only from the proxies we run, so a client cannot spoof its IP.
      koa: true,
      maxIpsCount: env.int('PROXY_MAX_IPS', 1),
    },
  };
};

export default config;
