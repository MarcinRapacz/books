# Chapter 6 – Document Service, Query Engine and reacting to changes

Copy `src/` over the foundation project (`books/strapi-5/code/`); `src/index.ts` and `src/api/category/services/category.ts` replace the foundation files. No extra packages (`@strapi/utils` and `@strapi/database` already come with Strapi).

- `src/document-middlewares/` – Document Service middlewares registered in `src/index.ts`: readingTime + slug, author from the request, guard against deleting a category with articles.
- `src/api/category/services/category.ts` – `importWithArticles()`, a transaction example (`strapi.db.transaction`).
- `src/debug/trace-documents.ts` and `src/api/article/content-types/article/lifecycles.ts` – the counting experiment; they log only with `TRACE_ARTICLE_EVENTS=true`.

Check: `TRACE_ARTICLE_EVENTS=true npm run develop`, log in as `anna` (`POST /api/auth/local`), then
`curl -X POST localhost:1337/api/articles -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' -d '{"data":{"title":"Hello Strapi"}}'`
– the response has `slug: "hello-strapi"`; the log shows one Document Service `create` call and four `[lifecycle]` lines (draft and published row, before and after).
Transaction: `npm run console`, then `await strapi.service('api::category.category').importWithArticles('Security', ['OWASP', 'x'.repeat(200)])` fails and leaves no `Security` category behind.
