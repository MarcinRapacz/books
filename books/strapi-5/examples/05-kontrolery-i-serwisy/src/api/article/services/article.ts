import { factories } from '@strapi/strapi';
import type { Modules } from '@strapi/strapi';
import { errors } from '@strapi/utils';

const RELATED_LIMIT = 3;

type FindManyParams = Modules.Documents.ServiceParams<'api::article.article'>['findMany'];
type RelatedQuery = Pick<FindManyParams, 'fields' | 'populate'>;

export default factories.createCoreService('api::article.article', ({ strapi }) => ({
  async findRelated(documentId: string, { fields, populate }: RelatedQuery = {}) {
    const article = await strapi.documents('api::article.article').findOne({
      documentId,
      status: 'published',
      populate: ['category'],
    });
    if (!article) throw new errors.NotFoundError('Article not found');
    if (!article.category) return [];

    return strapi.documents('api::article.article').findMany({
      fields,
      populate,
      status: 'published',
      filters: {
        category: { documentId: article.category.documentId },
        documentId: { $ne: documentId },
      },
      sort: 'publishedAt:desc',
      limit: RELATED_LIMIT,
    });
  },
}));
