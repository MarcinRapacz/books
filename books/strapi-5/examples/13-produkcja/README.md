# Rozdział 13 – produkcja self-hosted

1. Skopiuj pliki do projektu fundamentu (`code/`), zachowując ścieżki; `src/index.ts` zawiera tylko indeks na `articles.slug` – scal go z własnym `bootstrap`.
2. `npm install pg`.
3. `cp .env.example .env` i wypełnij wartości (`openssl rand -base64 32`).
4. Lokalnie: `docker compose up -d --build`, potem `curl -i localhost:1313/_health` (204) i `curl localhost:1313/api/articles`.
5. Dane z SQLite: `npx strapi export --key "$KEY" -f backups/redakcja`, potem
   `docker compose run --rm -v ./backups:/backups:ro strapi node_modules/.bin/strapi import -f /backups/redakcja.tar.gz.enc --key "$KEY" --force`.
6. Na VPS z Traefikiem: `docker compose -f docker-compose.yml -f docker-compose.traefik.yml up -d` (Traefik w osobnym stosie, sieć `web`).
7. Sprzątanie lokalne: `docker compose down -v`.
