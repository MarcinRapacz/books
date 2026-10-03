import { factories } from '@strapi/strapi';

// status=draft also applies to populated articles, so every type that can populate them is guarded.
export default factories.createCoreRouter('api::category.category', {
  config: {
    find: { policies: ['global::drafts-for-authors-only'] },
    findOne: { policies: ['global::drafts-for-authors-only'] },
  },
});
