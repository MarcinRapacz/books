import type { Core } from '@strapi/strapi';

const config: Core.Config.Middlewares = [
  'strapi::logger',
  // Before strapi::errors: code after `await next()` sees the final status, also on errors.
  { name: 'global::trace', config: { label: 'global middleware' } },
  { name: 'global::cache-headers', config: { maxAge: 300 } },
  'strapi::errors',
  'strapi::security',
  'strapi::cors',
  'strapi::poweredBy',
  'strapi::query',
  'strapi::body',
  'strapi::session',
  'strapi::favicon',
  'strapi::public',
];

export default config;
