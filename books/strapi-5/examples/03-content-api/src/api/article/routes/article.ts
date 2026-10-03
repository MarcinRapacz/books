import { factories } from '@strapi/strapi';

export default factories.createCoreRouter('api::article.article', {
  config: {
    find: { policies: ['global::drafts-for-authors-only'] },
    findOne: { policies: ['global::drafts-for-authors-only'] },
  },
});
