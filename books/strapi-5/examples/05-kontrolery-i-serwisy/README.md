# Chapter 5 – controllers, services, validation and errors

Copy `src/` and `scripts/grant-ch05.js` over the foundation project (`code/`). No extra packages: `z`, `validateZodSchema` and `errors` come from `@strapi/utils`, installed with `@strapi/strapi`.

With the server stopped: `rm -f .tmp/data.db && npm run seed && node scripts/grant-ch05.js` (grants `related` to Public/Authenticated and creates the Editor role with user `ewa` / `Passw0rd!`).

Check:
- `curl localhost:1337/api/articles/<documentId>/related` – sanitized related articles, no `author` fields.
- `POST /api/comments` as `anna` with `"moderationStatus":"approved"` – 400 `Unrecognized key`; without it – 201 with `"moderationStatus":"pending"`.
- `POST /api/comments/<documentId>/approve` – 403 for `anna`, 200 for `ewa`, 400 when repeated.
