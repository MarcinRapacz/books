# Chapter 7 – users, tokens and permissions

Copy `config/` and `src/` over the foundation project (`books/strapi-5/code/`), keeping paths. No extra packages.

- `src/index.ts` – grants `api::article.article.mine` to Authenticated in `bootstrap`; configures the GitHub provider when `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are set.
- `src/api/article/` – `GET /api/articles/mine` (controller action + route) and the `published-only` route middleware on `find`/`findOne`.
- `src/extensions/users-permissions/strapi-server.ts` – `displayName` user field, `/users/me` with role name and type.
- `config/plugins.ts` – foundation config plus `register.allowedFields: ['displayName']`.
- `client/auth-fetch.ts` – browser helper for refresh mode with an httpOnly cookie (not part of the Strapi project).

Check: `npm run seed`, start the server, log in with `curl -X POST localhost:1337/api/auth/local -H 'Content-Type: application/json' -d '{"identifier":"piotr","password":"Passw0rd!"}'`, then `curl localhost:1337/api/articles/mine -H "Authorization: Bearer <jwt>"` returns Piotr's two articles, and `curl -g 'localhost:1337/api/articles?status=draft'` returns only published versions.
