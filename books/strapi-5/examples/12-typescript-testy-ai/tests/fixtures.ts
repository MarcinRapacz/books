import request from 'supertest';
import type { Core } from '@strapi/strapi';

const PASSWORD = 'Passw0rd!';

/** Grants Content API actions to a users-permissions role, as the panel would. */
export async function grant(strapi: Core.Strapi, roleType: 'public' | 'authenticated', actions: string[]) {
  const role = await strapi.db.query('plugin::users-permissions.role').findOne({ where: { type: roleType } });
  for (const action of actions) {
    await strapi.db.query('plugin::users-permissions.permission').create({ data: { action, role: role.id } });
  }
}

/** Creates a confirmed Authenticated user and returns it with a JWT obtained through /api/auth/local. */
export async function createUser(strapi: Core.Strapi, username: string) {
  const role = await strapi.db.query('plugin::users-permissions.role').findOne({ where: { type: 'authenticated' } });
  const user = await strapi.plugin('users-permissions').service('user').add({
    username,
    email: `${username}@example.com`,
    password: PASSWORD,
    provider: 'local',
    confirmed: true,
    blocked: false,
    role: role.id,
  });
  const login = await request(strapi.server.httpServer)
    .post('/api/auth/local')
    .send({ identifier: username, password: PASSWORD })
    .expect(200);
  return { id: user.id as number, jwt: login.body.jwt as string };
}

export async function createPublishedArticle(strapi: Core.Strapi, title: string, authorId: number) {
  const article = await strapi.documents('api::article.article').create({
    data: { title, slug: title.toLowerCase().replace(/\W+/g, '-'), author: authorId },
  });
  await strapi.documents('api::article.article').publish({ documentId: article.documentId });
  return article;
}
