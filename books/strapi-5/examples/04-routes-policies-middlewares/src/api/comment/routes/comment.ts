import { factories } from '@strapi/strapi';

export default factories.createCoreRouter('api::comment.comment', {
  config: {
    create: {
      policies: ['article-is-published'],
      middlewares: [
        { name: 'api::comment.rate-limit', config: { max: 3, windowMs: 60_000 } },
      ],
    },
  },
});
