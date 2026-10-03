import { factories } from '@strapi/strapi';
import { errors } from '@strapi/utils';

const { ApplicationError, NotFoundError } = errors;

export interface CommentSubmission {
  body: string;
  articleId: string;
  authorId: number;
}

export default factories.createCoreService('api::comment.comment', ({ strapi }) => ({
  async submit({ body, articleId, authorId }: CommentSubmission) {
    const article = await strapi.documents('api::article.article').findOne({
      documentId: articleId,
      status: 'published',
    });
    if (!article) throw new NotFoundError('Article not found');

    return strapi.documents('api::comment.comment').create({
      data: { body, article: articleId, author: authorId, moderationStatus: 'pending' },
    });
  },

  async approve(documentId: string) {
    const comment = await strapi.documents('api::comment.comment').findOne({ documentId });
    if (!comment) throw new NotFoundError('Comment not found');
    if (comment.moderationStatus !== 'pending') {
      throw new ApplicationError('Only pending comments can be approved', {
        moderationStatus: comment.moderationStatus,
      });
    }
    return strapi.documents('api::comment.comment').update({
      documentId,
      data: { moderationStatus: 'approved' },
    });
  },
}));
