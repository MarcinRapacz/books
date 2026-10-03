import type { Core } from '@strapi/strapi';

// status=DRAFT also applies to nested relations, so every query that can reach articles is guarded.
const draftGuards = Object.fromEntries(
  ['article', 'articles', 'articles_connection', 'category', 'categories', 'categories_connection', 'comment', 'comments', 'comments_connection']
    .map((query) => [`Query.${query}`, { policies: ['global::drafts-for-authors-only'] }]),
);

export default {
  register({ strapi }: { strapi: Core.Strapi }) {
    const extensionService = strapi.plugin('graphql').service('extension');

    // Comments are created only through the REST controller, which validates input (chapter 5).
    extensionService.shadowCRUD('api::comment.comment').disableMutations();
    // The single type is edited in the admin panel only.
    extensionService.shadowCRUD('api::global.global').disableMutations();

    extensionService.use(() => ({
      typeDefs: `
        type Query {
          articleBySlug(slug: String!): Article
        }
      `,
      resolvers: {
        Query: {
          articleBySlug: (_parent: unknown, args: { slug: string }) =>
            strapi.documents('api::article.article').findFirst({
              filters: { slug: { $eq: args.slug } },
              status: 'published',
            }),
        },
      },
      resolversConfig: {
        // Without `auth`, a custom query is open to every logged-in user and closed to guests;
        // the scope ties it to the role permission used by REST findOne.
        'Query.articleBySlug': { auth: { scope: ['api::article.article.findOne'] } },
        ...draftGuards,
      },
    }));
  },

  bootstrap() {},
};
