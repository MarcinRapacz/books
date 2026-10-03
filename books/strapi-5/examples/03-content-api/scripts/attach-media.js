'use strict';

// Chapter 3 helper: attaches one image (favicon.png) to the first published article as cover,
// seo.shareImage and a shared.media block, so populate examples have real media to show.
// Usage: node scripts/attach-media.js   (run after `npm run seed`, with the server stopped)
const fs = require('fs');
const path = require('path');
const { createStrapi, compileStrapi } = require('@strapi/strapi');

async function attach(strapi) {
  const article = await strapi.documents('api::article.article').findFirst({
    filters: { slug: 'policies-in-strapi-5' },
    populate: ['content', 'seo'],
  });
  const filepath = path.join(__dirname, '..', 'favicon.png');
  const [image] = await strapi.plugin('upload').service('upload').upload({
    data: { fileInfo: { name: 'policies-cover.png', alternativeText: 'Policies diagram' } },
    files: { filepath, originalFilename: 'policies-cover.png', mimetype: 'image/png', size: fs.statSync(filepath).size },
  });

  const content = article.content.map(({ id, ...block }) => block);
  await strapi.documents('api::article.article').update({
    documentId: article.documentId,
    data: {
      cover: image.id,
      seo: { metaTitle: article.seo.metaTitle, metaDescription: article.seo.metaDescription, shareImage: image.id },
      content: [...content, { __component: 'shared.media', file: image.id }],
    },
  });
  await strapi.documents('api::article.article').publish({ documentId: article.documentId });
}

async function main() {
  const app = await createStrapi(await compileStrapi()).load();
  app.log.level = 'error';
  try {
    await attach(app);
    console.log('attach-media: ok');
  } finally {
    await app.destroy();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
