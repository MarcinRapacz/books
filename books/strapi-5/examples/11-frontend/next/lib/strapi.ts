import 'server-only';
import qs from 'qs';
import { draftMode } from 'next/headers';

// Shapes of the queries below, not of the whole content type: fields and populate decide the shape.
export type Media = { url: string; alternativeText: string | null; width: number; height: number };

export type ArticleCard = {
  documentId: string;
  title: string;
  slug: string;
  excerpt: string | null;
  publishedAt: string | null;
  cover: Media | null;
  category: { name: string; slug: string } | null;
};

// Strapi "blocks" field, reduced to what this site renders.
export type RichTextBlock = { type: string; children: { type: string; text?: string }[] };

export type ArticleBlock =
  | { __component: 'shared.rich-text'; id: number; body: RichTextBlock[] }
  | { __component: 'shared.quote'; id: number; title: string | null; body: string }
  | { __component: 'shared.media'; id: number; file: Media | null };

export type ArticleDetail = ArticleCard & { content: ArticleBlock[] };

type Collection<T> = { data: T[]; meta: { pagination: { total: number } } };

export const ARTICLES_TAG = 'strapi:article';

const STRAPI_URL = requireEnv('STRAPI_URL');
const API_TOKEN = requireEnv('STRAPI_API_TOKEN');

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing environment variable ${name}`);
  return value;
}

async function strapiGet<T>(path: string, query: object, tags: string[]): Promise<T> {
  const { isEnabled: isDraft } = await draftMode();
  const search = qs.stringify({ ...query, status: isDraft ? 'draft' : 'published' }, { encodeValuesOnly: true });
  const response = await fetch(`${STRAPI_URL}/api/${path}?${search}`, {
    headers: { Authorization: `Bearer ${API_TOKEN}` },
    // Published content is cached until the webhook revalidates the tag; the timer is a fallback,
    // because Strapi does not retry a webhook that failed. Draft mode skips this cache anyway.
    cache: 'force-cache',
    next: { tags, revalidate: 300 },
  });
  if (!response.ok) {
    throw new Error(`Strapi ${response.status} for /api/${path}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

const cardQuery = {
  fields: ['title', 'slug', 'excerpt', 'publishedAt'],
  populate: {
    cover: { fields: ['url', 'alternativeText', 'width', 'height'] },
    category: { fields: ['name', 'slug'] },
  },
};

export async function getArticles(): Promise<ArticleCard[]> {
  const query = { ...cardQuery, sort: ['publishedAt:desc'], pagination: { pageSize: 20 } };
  return (await strapiGet<Collection<ArticleCard>>('articles', query, [ARTICLES_TAG])).data;
}

export async function getArticle(slug: string): Promise<ArticleDetail | null> {
  const query = {
    ...cardQuery,
    filters: { slug: { $eq: slug } },
    populate: {
      ...cardQuery.populate,
      content: {
        on: {
          'shared.rich-text': true,
          'shared.quote': true,
          'shared.media': { populate: { file: { fields: ['url', 'alternativeText', 'width', 'height'] } } },
        },
      },
    },
  };
  const { data } = await strapiGet<Collection<ArticleDetail>>('articles', query, [ARTICLES_TAG]);
  return data[0] ?? null;
}

export function mediaUrl(media: Media): string {
  // The local upload provider returns relative URLs; S3-like providers return absolute ones.
  return media.url.startsWith('http') ? media.url : `${STRAPI_URL}${media.url}`;
}
