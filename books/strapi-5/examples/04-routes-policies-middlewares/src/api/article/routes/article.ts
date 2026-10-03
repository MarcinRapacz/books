import { factories } from '@strapi/strapi';

const isOwner = { name: 'global::is-owner', config: { uid: 'api::article.article' } };
const trace = { name: 'global::trace', config: { label: 'route middleware' } };

export default factories.createCoreRouter('api::article.article', {
  config: {
    update: { policies: ['global::trace-policy', isOwner], middlewares: [trace] },
    delete: { policies: [isOwner] },
  },
});
