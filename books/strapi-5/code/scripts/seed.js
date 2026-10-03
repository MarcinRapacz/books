'use strict';

// Seeds the guide project with deterministic demo data. Idempotent: skips when categories exist.
// Usage: npm run seed   (the app must not be running against the same SQLite file)
const { createStrapi, compileStrapi } = require('@strapi/strapi');

const PUBLIC_ACTIONS = [
  'api::article.article.find',
  'api::article.article.findOne',
  'api::category.category.find',
  'api::category.category.findOne',
  'api::comment.comment.find',
  'api::global.global.find',
];

const AUTHENTICATED_ACTIONS = [
  ...PUBLIC_ACTIONS,
  'api::article.article.create',
  'api::article.article.update',
  'api::article.article.delete',
  'api::comment.comment.create',
];

async function grant(strapi, roleType, actions) {
  const role = await strapi.db.query('plugin::users-permissions.role').findOne({ where: { type: roleType } });
  for (const action of actions) {
    const exists = await strapi.db.query('plugin::users-permissions.permission').findOne({ where: { action, role: role.id } });
    if (!exists) {
      await strapi.db.query('plugin::users-permissions.permission').create({ data: { action, role: role.id } });
    }
  }
  return role;
}

async function createUser(strapi, username, roleId) {
  return strapi.plugin('users-permissions').service('user').add({
    username,
    email: `${username}@example.com`,
    password: 'Passw0rd!',
    provider: 'local',
    confirmed: true,
    blocked: false,
    role: roleId,
  });
}

async function seed(strapi) {
  if ((await strapi.documents('api::category.category').count()) > 0) {
    strapi.log.info('Seed skipped: data already present');
    return;
  }
  await grant(strapi, 'public', PUBLIC_ACTIONS);
  const authenticated = await grant(strapi, 'authenticated', AUTHENTICATED_ACTIONS);
  const anna = await createUser(strapi, 'anna', authenticated.id);
  const piotr = await createUser(strapi, 'piotr', authenticated.id);

  const categories = {};
  for (const name of ['Backend', 'Frontend', 'DevOps']) {
    categories[name] = await strapi.documents('api::category.category').create({
      data: { name, slug: name.toLowerCase(), description: `Articles about ${name}` },
    });
  }

  const articles = [
    { title: 'Policies in Strapi 5', category: 'Backend', author: anna, publish: true },
    { title: 'Document Service middlewares', category: 'Backend', author: anna, publish: true },
    { title: 'Fetching Strapi from Next.js', category: 'Frontend', author: piotr, publish: true },
    { title: 'Self-hosting Strapi with Docker', category: 'DevOps', author: piotr, publish: false },
  ];
  for (const a of articles) {
    const slug = a.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    const article = await strapi.documents('api::article.article').create({
      data: {
        title: a.title,
        slug,
        excerpt: `A short introduction to ${a.title.toLowerCase()}.`,
        category: categories[a.category].documentId,
        author: a.author.id,
        seo: { metaTitle: a.title, metaDescription: `Read about ${a.title}` },
        content: [
          {
            __component: 'shared.rich-text',
            body: [{ type: 'paragraph', children: [{ type: 'text', text: `${a.title}: first paragraph.` }] }],
          },
          { __component: 'shared.quote', title: 'Note', body: 'Measure before you optimise.' },
        ],
      },
    });
    if (a.publish) {
      await strapi.documents('api::article.article').publish({ documentId: article.documentId });
      await strapi.documents('api::comment.comment').create({
        data: { body: 'Great article!', moderationStatus: 'approved', article: article.documentId, author: piotr.id },
      });
    }
  }

  await strapi.documents('api::global.global').create({
    data: { siteName: 'Redakcja', siteDescription: 'A multi-author tech magazine', defaultSeo: { metaTitle: 'Redakcja' } },
  });
  strapi.log.info('Seed done: 3 categories, 4 articles (3 published), 2 users (anna, piotr / Passw0rd!)');
}

async function main() {
  const appContext = await compileStrapi();
  const app = await createStrapi(appContext).load();
  app.log.level = 'error';
  try {
    await seed(app);
    console.log('seed: ok');
  } finally {
    await app.destroy();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
