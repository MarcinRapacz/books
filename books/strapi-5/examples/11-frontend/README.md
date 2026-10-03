# Chapter 11 – Next.js frontend

Strapi side: the foundation with `examples/07-uwierzytelnianie` and `examples/08-funkcje-wbudowane` applied (published-only middleware, webhook, preview handler), plus `config/middlewares.ts` from here (`strapi::cors` limited to `CORS_ORIGINS`).
Start Strapi with `CLIENT_URL=http://localhost:3000 CORS_ORIGINS=http://localhost:3000 FRONTEND_WEBHOOK_URL=http://localhost:3000/api/revalidate WEBHOOK_SECRET=... PREVIEW_SECRET=...`.

Next side: create a project with `npx create-next-app@latest redakcja-next --ts --app --empty --no-tailwind`, copy `next/` over it, `npm install qs && npm install -D @types/qs`, fill `.env.local` from `.env.example` (API token of type Custom with find/findOne on articles and categories), then `npm run build && npm start`.

Check:
- `curl localhost:3000/` lists published articles; publishing an article (`PUT /api/articles/:documentId` without `status`) logs `[revalidate] entry.publish ...` in Next and the next request shows the new title.
- `curl -X POST localhost:3000/api/revalidate` without `X-Webhook-Secret` returns 401.
- The preview URL from Strapi (`/api/preview?url=...&secret=...&status=draft`) sets `__prerender_bypass` and the page shows the draft.
- `curl -i -X POST localhost:3000/api/auth/login -H 'Content-Type: application/json' -d '{"identifier":"anna","password":"Passw0rd!"}'` sets the httpOnly `redakcja_refresh` cookie; `POST /api/auth/refresh` rotates it.
