import { factories } from '@strapi/strapi';

const publishedOnly = 'api::article.published-only';

export default factories.createCoreRouter('api::article.article', {
  config: {
    find: { middlewares: [publishedOnly] },
    findOne: { middlewares: [publishedOnly] },
  },
});
