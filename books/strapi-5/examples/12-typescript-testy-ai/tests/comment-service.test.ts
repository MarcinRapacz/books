import { describe, expect, it, vi } from 'vitest';
import { errors } from '@strapi/utils';
import type { Core } from '@strapi/strapi';
import createCommentService from '../src/api/comment/services/comment';

// Only what the service touches: strapi.contentType() for the core factory, strapi.documents().
function fakeStrapi(publishedArticle: { documentId: string } | null) {
  const articles = { findOne: vi.fn().mockResolvedValue(publishedArticle) };
  const comments = { create: vi.fn(async ({ data }) => ({ documentId: 'c1', ...data })) };
  const strapi = {
    contentType: vi.fn(() => ({ kind: 'collectionType' })),
    documents: vi.fn((uid: string) => (uid === 'api::article.article' ? articles : comments)),
  };
  return { strapi: strapi as unknown as Core.Strapi, articles, comments };
}

describe('commentService.submit', () => {
  it('creates the comment as pending for the given author', async () => {
    const { strapi, comments } = fakeStrapi({ documentId: 'a1' });
    const service = createCommentService({ strapi });

    const comment = await service.submit({ body: 'Nice', articleId: 'a1', authorId: 7 });

    expect(comments.create).toHaveBeenCalledTimes(1);
    expect(comments.create).toHaveBeenCalledWith({
      data: { body: 'Nice', article: 'a1', author: 7, moderationStatus: 'pending' },
    });
    expect(comment.moderationStatus).toBe('pending');
  });

  it('refuses comments on articles without a published version', async () => {
    const { strapi, articles, comments } = fakeStrapi(null);
    const service = createCommentService({ strapi });

    await expect(
      service.submit({ body: 'Nice', articleId: 'draft', authorId: 7 })
    ).rejects.toBeInstanceOf(errors.NotFoundError);
    expect(articles.findOne).toHaveBeenCalledWith({ documentId: 'draft', status: 'published' });
    expect(comments.create).not.toHaveBeenCalled();
  });
});
