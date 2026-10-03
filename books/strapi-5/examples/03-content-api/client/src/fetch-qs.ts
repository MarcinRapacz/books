// Lists published articles of one category for an article list page, using plain fetch + qs.
// Run: STRAPI_URL=http://localhost:1303 node src/fetch-qs.ts backend
import qs from 'qs';

type Media = { url: string; alternativeText: string | null };
type ArticleCard = {
  documentId: string;
  title: string;
  slug: string;
  excerpt: string | null;
  publishedAt: string;
  cover: Media | null;
  category: { name: string; slug: string } | null;
};
type Pagination = { page: number; pageSize: number; pageCount: number; total: number };
type ListResponse<T> = { data: T[]; meta: { pagination: Pagination } };
type ErrorResponse = { data: null; error: { status: number; name: string; message: string } };

const baseUrl = process.env.STRAPI_URL ?? 'http://localhost:1337';

export async function fetchArticleCards(categorySlug: string, page = 1): Promise<ListResponse<ArticleCard>> {
  const query = qs.stringify(
    {
      fields: ['title', 'slug', 'excerpt', 'publishedAt'],
      populate: {
        cover: { fields: ['url', 'alternativeText'] },
        category: { fields: ['name', 'slug'] },
      },
      filters: { category: { slug: { $eq: categorySlug } } },
      sort: ['publishedAt:desc', 'title:asc'],
      pagination: { page, pageSize: 10 },
    },
    { encodeValuesOnly: true },
  );

  const response = await fetch(`${baseUrl}/api/articles?${query}`);
  if (!response.ok) {
    const body = (await response.json()) as ErrorResponse;
    throw new Error(`Strapi ${body.error.status} ${body.error.name}: ${body.error.message}`);
  }
  return (await response.json()) as ListResponse<ArticleCard>;
}

const { data, meta } = await fetchArticleCards(process.argv[2] ?? 'backend');
for (const article of data) {
  console.log(`${article.title} [${article.category?.name}] cover=${article.cover?.url ?? '-'}`);
}
console.log(`page ${meta.pagination.page}/${meta.pagination.pageCount}, total ${meta.pagination.total}`);
