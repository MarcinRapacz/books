import type { Core } from '@strapi/strapi';

export default {
  register() {},

  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    // Strapi indexes documentId and relations, but not uid fields, and the frontend
    // resolves every article page by slug. Runs after the schema sync, so the table exists.
    await strapi.db.connection.raw('CREATE INDEX IF NOT EXISTS articles_slug_idx ON articles (slug)');
  },
};
