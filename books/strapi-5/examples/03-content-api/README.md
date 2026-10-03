# Chapter 3 – Content API from the client side

Backend: copy `config/`, `src/` and `scripts/attach-media.js` over the foundation project (`code/`) and run `npm install @strapi/plugin-graphql@5.56.0`. The route files and `src/index.ts` replace the foundation ones; `config/plugins.ts` only adds the `graphql` block.

With the server stopped: `rm -f .tmp/data.db && npm run seed && node scripts/attach-media.js` (adds one image as cover, `seo.shareImage` and a `shared.media` block of "Policies in Strapi 5"). Spec: `PUBLIC_URL=http://localhost:1337 npx strapi openapi generate -o specification.json`.

`client/` is a separate Node 24 project – keep it outside the Strapi directory (Strapi compiles every `.ts` file under its root). `cd client && npm install && npm run typecheck`, then `STRAPI_URL=http://localhost:1337 node src/fetch-qs.ts backend` and `STRAPI_URL=http://localhost:1337 STRAPI_USER=anna STRAPI_PASSWORD='Passw0rd!' node src/strapi-client.ts`.

Check:
- `curl -g 'localhost:1337/api/articles?status=draft'` – 403 `PolicyError`; with anna's JWT – 200 with drafts.
- `curl -g 'localhost:1337/api/articles?populate[content][on][shared.media][populate]=file'` – media blocks with `file`.
- `POST /graphql` with `{ articleBySlug(slug: "policies-in-strapi-5") { title } }` – works for Public; `createComment` is not in the schema.
