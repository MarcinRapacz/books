# Chapter 10 – admin panel and custom fields

Copy `src/` over the foundation project (`books/strapi-5/code`) and delete `src/admin/app.example.tsx`. No extra packages.

- `src/index.ts` registers the `global::seo-title` and `global::seo-description` custom fields on the server; `src/components/shared/seo.json` uses them.
- `src/admin/app.tsx` sets the Polish locale, translations, theme, logo, the custom field inputs, a homepage widget, a Content Manager header action and an injection zone component.
- Build with the frontend URL baked in: `STRAPI_ADMIN_FRONTEND_URL=https://redakcja.example npm run build`.
- Check types: `npx tsc --noEmit -p src/admin` and `npx tsc --noEmit -p .`.
- Check the server side: `PUT /api/articles/:documentId` with `{"data":{"seo":{"metaTitle":"..."}}}` stores the value; a 71-character `metaTitle` returns `400 ValidationError`.
