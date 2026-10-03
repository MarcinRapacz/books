import type { Core } from '@strapi/strapi';

export default {
  register({ strapi }: { strapi: Core.Strapi }) {
    // Custom fields must be known before content-type schemas are loaded,
    // otherwise Strapi fails to resolve `global::seo-*` attributes at startup.
    strapi.customFields.register([
      { name: 'seo-title', type: 'string', inputSize: { default: 12, isResizable: true } },
      { name: 'seo-description', type: 'text', inputSize: { default: 12, isResizable: true } },
    ]);
  },

  bootstrap(/* { strapi }: { strapi: Core.Strapi } */) {},
};
