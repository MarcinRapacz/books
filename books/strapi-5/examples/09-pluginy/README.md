# Rozdział 9 – własny plugin „comment-moderation”

1. Skopiuj `src/plugins/comment-moderation`, `src/extensions/upload`, `src/index.ts`, `config/plugins.ts` i `config/server.ts` do kopii fundamentu (`config/server.ts` włącza serwer MCP – pomiń go, jeśli nie testujesz narzędzia MCP).
2. Zbuduj plugin (bez instalowania peerów, żeby `@strapi/*` rozwiązywały się z projektu):
   `cd src/plugins/comment-moderation && npm install --legacy-peer-deps && npm run build`
3. Wróć do katalogu projektu: `npm run seed`, `npm run build` (panel), `npm run develop`; administratora utworzysz przez `npx strapi admin:create-user`.
4. Sprawdź: `curl localhost:1337/api/comment-moderation/articles/<documentId>/comments` (Public, 200) oraz
   `curl -H "Authorization: Bearer <admin JWT z POST /admin/login>" localhost:1337/comment-moderation/comments/pending`.
5. Podczas pracy nad pluginem trzymaj w drugim terminalu `npm run watch` w katalogu pluginu i restartuj Strapi po przebudowie (watcher ignoruje `dist/`).
