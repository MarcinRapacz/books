import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { Core } from '@strapi/strapi';
import { startStrapi, stopStrapi } from './strapi';
import { createPublishedArticle, createUser, grant } from './fixtures';

describe('is-owner on PUT /api/articles/:id', () => {
  let strapi: Core.Strapi;
  let anna: { id: number; jwt: string };
  let piotr: { id: number; jwt: string };
  let articleId: string;

  beforeAll(async () => {
    strapi = await startStrapi();
    await grant(strapi, 'authenticated', ['api::article.article.update']);
    anna = await createUser(strapi, 'anna');
    piotr = await createUser(strapi, 'piotr');
    articleId = (await createPublishedArticle(strapi, 'Policies in Strapi 5', anna.id)).documentId;
  });

  afterAll(async () => {
    await stopStrapi(strapi);
  });

  it('rejects an update from another author with 403 PolicyError', async () => {
    const res = await request(strapi.server.httpServer)
      .put(`/api/articles/${articleId}`)
      .set('Authorization', `Bearer ${piotr.jwt}`)
      .send({ data: { title: 'Hijacked' } });

    expect(res.status).toBe(403);
    expect(res.body.error).toMatchObject({ name: 'PolicyError', details: { policy: 'is-owner' } });
  });

  it('lets the author update their own article', async () => {
    const res = await request(strapi.server.httpServer)
      .put(`/api/articles/${articleId}`)
      .set('Authorization', `Bearer ${anna.jwt}`)
      .send({ data: { title: 'Policies in Strapi 5, revised' } });

    expect(res.status).toBe(200);
    expect(res.body.data.title).toBe('Policies in Strapi 5, revised');
  });

  it('answers 404 for an unknown document instead of revealing a policy decision', async () => {
    await request(strapi.server.httpServer)
      .put('/api/articles/doesnotexist000')
      .set('Authorization', `Bearer ${piotr.jwt}`)
      .send({ data: { title: 'x' } })
      .expect(404);
  });
});
