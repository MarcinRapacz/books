// Reads published articles and creates a draft as an authenticated author, using @strapi/client.
// Run: STRAPI_URL=http://localhost:1303 STRAPI_USER=anna STRAPI_PASSWORD=... node src/strapi-client.ts
import { strapi, HTTPError } from '@strapi/client';

const baseURL = `${process.env.STRAPI_URL ?? 'http://localhost:1337'}/api`;

async function login(identifier: string, password: string): Promise<string> {
  const response = await fetch(`${baseURL}/auth/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  });
  if (!response.ok) throw new Error(`Login failed with ${response.status}`);
  const { jwt } = (await response.json()) as { jwt: string };
  return jwt;
}

// Public reads need no token; the same query object as with qs, serialized by the client.
const publicClient = strapi({ baseURL });
const articles = publicClient.collection('articles');

const { data: latest, meta } = await articles.find({
  fields: ['title', 'slug'],
  populate: { category: { fields: ['name'] } },
  sort: 'publishedAt:desc',
  pagination: { page: 1, pageSize: 2 },
});
console.log('latest:', latest.map((a) => `${a.title} [${a.category?.name}]`), meta.pagination);

// Writes run as a users-permissions user; the JWT goes into `auth` like an API token.
const jwt = await login(process.env.STRAPI_USER ?? 'anna', process.env.STRAPI_PASSWORD ?? '');
const authorClient = strapi({ baseURL, auth: jwt });
const { data: categories } = await authorClient.collection('categories').find({
  filters: { slug: { $eq: 'frontend' } },
  fields: ['name'],
});

const { data: draft } = await authorClient.collection('articles').create(
  { title: 'Typed fetching with @strapi/client', slug: 'typed-fetching-with-strapi-client', category: categories[0].documentId },
  { status: 'draft', fields: ['title', 'publishedAt'], populate: { category: { fields: ['name'] } } },
);
console.log('draft:', draft.documentId, draft.title, draft.publishedAt, draft.category?.name);

try {
  await authorClient.collection('articles').update(draft.documentId, { views: 10 }, { status: 'draft' });
} catch (error) {
  if (!(error instanceof HTTPError)) throw error;
  const body = (await error.response.json()) as { error: { message: string } };
  console.log(`${error.name} ${error.response.status}: ${body.error.message}`);
}
