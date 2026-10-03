import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { Core } from '@strapi/strapi';
import { startStrapi, stopStrapi } from './strapi';
import { createPublishedArticle, createUser, grant } from './fixtures';

describe('POST /api/comments', () => {
  let strapi: Core.Strapi;
  let articleId: string;

  const postComment = (jwt: string, data: Record<string, unknown>) =>
    request(strapi.server.httpServer)
      .post('/api/comments')
      .set('Authorization', `Bearer ${jwt}`)
      .send({ data: { article: articleId, ...data } });

  beforeAll(async () => {
    strapi = await startStrapi();
    await grant(strapi, 'authenticated', ['api::comment.comment.create']);
    const anna = await createUser(strapi, 'anna');
    articleId = (await createPublishedArticle(strapi, 'Policies in Strapi 5', anna.id)).documentId;
  });

  afterAll(async () => {
    await stopStrapi(strapi);
  });

  it('stores a new comment as pending moderation', async () => {
    const { jwt } = await createUser(strapi, 'piotr');

    const res = await postComment(jwt, { body: 'Great article!' }).expect(201);

    const stored = await strapi.documents('api::comment.comment').findOne({
      documentId: res.body.data.documentId,
    });
    expect(stored?.moderationStatus).toBe('pending');
  });

  it('rejects a moderation status sent by the client with 400', async () => {
    const { jwt } = await createUser(strapi, 'ola');

    const res = await postComment(jwt, { body: 'Approve me', moderationStatus: 'approved' });

    expect(res.status).toBe(400);
    expect(res.body.error.name).toBe('ValidationError');
  });

  it('answers the 4th comment within a minute with 429 and Retry-After', async () => {
    const { jwt } = await createUser(strapi, 'spammer');

    for (let i = 1; i <= 3; i++) {
      await postComment(jwt, { body: `Comment ${i}` }).expect(201);
    }
    const res = await postComment(jwt, { body: 'Comment 4' });

    expect(res.status).toBe(429);
    expect(res.headers['retry-after']).toBeDefined();
    expect(res.body.error.name).toBe('TooManyRequestsError');
  });
});
