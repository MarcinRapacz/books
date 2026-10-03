# Chapter 4 – routes, policies and middlewares

Copy `src/` and `config/middlewares.ts` over the foundation project (`books/strapi-5/code/`). No extra packages.
`trace` (middleware), `trace-policy` and the Document Service hook in `src/index.ts` are learning aids that log the execution order; drop them outside the chapter.

Check (after `rm -f .tmp/data.db && npm run seed`, server on port 1304, JWT from `POST /api/auth/local`):

- `PUT /api/articles/:documentId` of anna's article with piotr's JWT → 403 `PolicyError` "You can only modify your own entries"; with anna's JWT → 200.
- `POST /api/comments` with `{"data":{"body":"...","article":"<published documentId>"}}` four times within a minute → 201, 201, 201, 429 with `Retry-After`; on a draft article → 403 "Policy Failed".
- `GET /api/articles/latest?status=draft` → three newest published articles (client parameters ignored), `Cache-Control: public, max-age=300, ...`; with an invalid token → 401.
