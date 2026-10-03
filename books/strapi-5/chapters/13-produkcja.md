# Rozdział 13. Produkcja self-hosted: Docker, Postgres, dane, aktualizacje

> **Cel rozdziału:** zbudować z „Redakcji” obraz Dockera, uruchomić go z Postgresem za Traefikiem, przenieść dane z SQLite, robić kopie i bezpiecznie aktualizować Strapi.
>
> **Kod:** `examples/13-produkcja/`. **Pakiety poza fundamentem:** `npm install pg`.

„Redakcja” działa lokalnie na SQLite i `strapi develop`. Produkcja to VPS z Traefikiem, kontener ze Strapi i kontener z Postgresem. Kod przychodzi z repozytorium, konfiguracja ze zmiennych środowiskowych, a dane – z kopii, którą trzeba przenieść. Content-Type Builder jest w produkcji wyłączony, więc każda zmiana modelu przechodzi przez repo i wdrożenie (rozdział 2).

Wszystko poniżej uruchomiłem lokalnie z Postgresem 17, poza Traefikiem i prawdziwą domeną – zachowanie za proxy zasymulowałem nagłówkiem.

```text
Internet ──443──→ Traefik (TLS, Let's Encrypt)
                     │ sieć "web", X-Forwarded-Proto: https
                     ▼
              strapi:1337  (node, uid 1000) ── wolumen public/ (uploads)
                     │ sieć projektu
                     ▼
              db:5432  (postgres:17) ── wolumen db-data
```

## Konfiguracja produkcyjna

Rozdział 1 pokazał, że przy `NODE_ENV=production` Strapi scala `config/*` z `config/env/production/*`. W pliku produkcyjnym trzymasz więc tylko różnice. Dla bazy różnica jest zasadnicza – zawsze Postgres, niezależnie od `DATABASE_CLIENT`:

```ts
// config/env/production/database.ts (fragment)
const required = (name: string): string => {
  const value = env(name);
  if (!value) {
    throw new Error(`${name} is required in production`);
  }
  return value;
};

return {
  connection: {
    client: 'postgres',
    connection: {
      host: env('DATABASE_HOST', 'db'),
      port: env.int('DATABASE_PORT', 5432),
      database: required('DATABASE_NAME'),
      user: required('DATABASE_USERNAME'),
      password: required('DATABASE_PASSWORD'),
      ssl: env.bool('DATABASE_SSL', false),
    },
    // Docker drops idle connections, so the pool must be allowed to shrink to zero.
    pool: { min: 0, max: env.int('DATABASE_POOL_MAX', 10) },
  },
};
```

Brak hasła zatrzymuje start z czytelnym komunikatem, zamiast próbować domyślnego `strapi:strapi` z pliku bazowego. Kontener nie dostał zmiennej `DATABASE_CLIENT`, a log startowy i tak pokazał `Database: postgres`. Driver `pg` dodajesz sam – fundament ma tylko `better-sqlite3`.

Plik `config/env/production/server.ts` ustawia publiczny adres (`url: env('PUBLIC_URL')`, z tą samą kontrolą obecności) i zaufanie do proxy (`proxy: { koa: true, maxIpsCount: 1 }`) – do tego wrócimy przy Traefiku. Nie kładź obok `middlewares.ts` z tablicą: scalanie tablic element po elemencie (pułapka z rozdziału 1) daje listę, której nie zamierzałeś.

Sekrety pochodzą z pliku `.env` na serwerze, generowanego raz przez `openssl rand -base64 32`, i nigdy nie trafiają do obrazu. Każdy ma inny koszt zmiany:

| Zmienna | Co psuje jej zmiana |
|---|---|
| `APP_KEYS` | podpisy ciasteczek (`strapi_up_refresh.sig`), więc odświeżanie sesji |
| `JWT_SECRET` | wszystkie tokeny dostępu users-permissions (rozdział 7) |
| `ADMIN_JWT_SECRET` | sesje panelu admina |
| `API_TOKEN_SALT` | wszystkie API tokeny – frontend dostaje 401 (rozdział 7) |
| `TRANSFER_TOKEN_SALT` | tokeny transferu danych |
| `ENCRYPTION_KEY` | odczyt zapisanych w bazie kluczy API tokenów w panelu |

`APP_KEYS` to lista, bo Koa podpisuje pierwszym kluczem, a weryfikuje każdym: nowy klucz dopisujesz na początek, stary usuwasz, gdy wygasną podpisane nim sesje. Pozostałe sekrety rotujesz jednorazowo, wiedząc, kogo to wyloguje.

## Obraz Dockera

Strapi nie publikuje oficjalnego obrazu. Przykład z dokumentacji kopiuje do obrazu końcowego cały katalog z etapu budowania. Wersja dla „Redakcji” ma trzy etapy i bierze tylko to, czego Strapi używa w czasie działania:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /opt/app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NODE_ENV only after npm ci, otherwise npm skips devDependencies needed by the build.
ENV NODE_ENV=production
# `strapi build` loads the whole config, so the fail-fast checks in config/env/production need values.
RUN PUBLIC_URL=http://build.invalid DATABASE_NAME=build DATABASE_USERNAME=build DATABASE_PASSWORD=build \
    npm run build

FROM node:22-alpine AS deps
WORKDIR /opt/app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /opt/app
COPY --from=deps --chown=node:node /opt/app/node_modules ./node_modules
COPY --from=build --chown=node:node /opt/app/dist ./dist
COPY --chown=node:node package.json package-lock.json tsconfig.json favicon.png ./
# Sources stay in the image: CLI commands (import, export, console) recompile TypeScript before they run.
COPY --chown=node:node config ./config
COPY --chown=node:node src ./src
COPY --chown=node:node types ./types
COPY --chown=node:node database ./database
COPY --chown=node:node public ./public
USER node
EXPOSE 1337
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:1337/_health || exit 1
CMD ["node_modules/.bin/strapi", "start"]
```

Bazą jest `node:22-alpine` jak w dokumentacji (wspierane są Node 22, 24 i 26). Etap `build` instaluje wszystko i kompiluje TypeScript (2,6 s) oraz panel admina (40 s). Etap `deps` instaluje osobno same zależności produkcyjne, a obraz końcowy składa się z nich, z `dist/` i z kilku plików. `.dockerignore` wyklucza `node_modules`, `dist`, `.tmp`, `.env*`, `backups/` i zawartość `public/uploads`, więc lokalna baza ani sekrety nie trafiają do kontekstu budowania. Obraz zajmuje 1,15 GB, z czego 725 MB to produkcyjne `node_modules` samego Strapi (m.in. `typescript` i pakiety panelu).

Pierwszy build padł z błędem `Could not load js config file .../config/env/production/database.js: DATABASE_NAME is required in production`. `strapi build` tworzy pełną instancję Strapi i wczytuje całą konfigurację, więc kontrole obecności zmiennych potrzebują wartości także przy budowaniu. Stąd wartości zastępcze w `RUN` – nie zostają w obrazie. Do paczki panelu trafia tylko ścieżka z `PUBLIC_URL` (tu `/`, kod `create-build-context.js`), więc jeden obraz obsłuży staging i produkcję pod różnymi domenami. Obraz zbudowany z `build.invalid` i uruchomiony z innym adresem zwrócił na `/admin` 200; w przeglądarce panelu nie klikałem.

Wcześniejsza wersja obrazu nie miała źródeł, tylko `dist/`. `strapi start` działał, ale `strapi import` w kontenerze skończył się `error TS18003: No inputs were found in config file '/opt/app/tsconfig.json'`. Komendy CLI (`import`, `export`, `transfer`, `console`) przed startem kompilują projekt TypeScript, więc źródła `config/`, `src/` i `types/` (razem ok. 300 KB) zostają w obrazie.

`CMD` uruchamia binarkę bezpośrednio, bez `npm run start`. Strapi jest wtedy procesem PID 1 i sam obsługuje `SIGTERM`: wywołuje `destroy()` (rozdział 1) i kończy pracę. `docker compose stop` zatrzymał kontener w 0,27 s, zamiast czekać 10 s na `SIGKILL`. Kontener działa jako `uid=1000(node)`.

## Compose z Postgresem

```yaml
services:
  strapi:
    build: .
    env_file: .env
    environment:
      NODE_ENV: production
      DATABASE_HOST: db
    ports:
      - "127.0.0.1:1313:1337"     # local test only
    volumes:
      - public:/opt/app/public    # not public/uploads, see the pitfall below
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: ${DATABASE_NAME}
      POSTGRES_USER: ${DATABASE_USERNAME}
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD}
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
volumes:
  db-data:
  public:
```

Ten sam `.env` zasila Strapi (`env_file`) i podstawianie `${DATABASE_NAME}` w pliku compose, więc hasło do bazy istnieje w jednym miejscu. `$$` przekazuje zmienną do powłoki kontenera, a `service_healthy` czeka na `pg_isready`, nie tylko na start procesu. Nazwany wolumen dostaje przy tworzeniu zawartość katalogu z obrazu razem z właścicielem `node`, więc Strapi zapisuje pliki bez `chown`. Pełny plik w `examples/` ma jeszcze `restart: unless-stopped`, interwał healthchecku i port 15432 dla `psql` z hosta, tylko na `127.0.0.1`.

Po `docker compose up -d` health check odpowiedział po kilku sekundach, a log pokazał `Launched in 3075 ms`, `Environment: production`, `Process PID: 1`, `Database: postgres`:

```text
$ curl -i localhost:1313/_health
HTTP/1.1 204 No Content
Content-Security-Policy: connect-src 'self' https:;img-src 'self' data: blob: https://market-assets.strapi.io;...
Strict-Transport-Security: max-age=31536000; includeSubDomains
$ curl localhost:1313/api/articles
{"data":null,"error":{"status":403,"name":"ForbiddenError","message":"Forbidden","details":{}}}
```

403 na pustej bazie to przypomnienie z rozdziału 7: uprawnienia ról to dane, a nie kod. Nowa baza ma role Public i Authenticated bez żadnych uprawnień, dopóki nie nada ich `bootstrap` albo import.

## Za Traefikiem

Traefik czyta reguły z etykiet kontenerów. Plik `docker-compose.traefik.yml` nakłada je na lokalną konfigurację i kasuje mapowania portów (`ports: !reset []`), bo na VPS-ie jedynym publicznym wejściem jest Traefik. Tej części nie uruchamiałem – sprawdziłem tylko scaloną konfigurację `docker compose -f docker-compose.yml -f docker-compose.traefik.yml config`.

```yaml
services:
  strapi:
    ports: !reset []
    labels:
      - traefik.enable=true
      - traefik.docker.network=web
      - traefik.http.routers.redakcja.rule=Host(`cms.redakcja.example`)
      - traefik.http.routers.redakcja.entrypoints=websecure
      - traefik.http.routers.redakcja.tls.certresolver=letsencrypt
      - traefik.http.services.redakcja.loadbalancer.server.port=1337
    networks: [default, web]   # plus "db: ports: !reset []" and the external network "web"
```

Strapi mówi zwykłym HTTP, a TLS kończy się na Traefiku. Żeby Strapi wiedział, że klient przyszedł po HTTPS, musi ufać nagłówkom `X-Forwarded-*` – to robi `proxy.koa: true`. `maxIpsCount: 1` każe brać adres klienta tylko z ostatniego wpisu `X-Forwarded-For`, dopisanego przez twojego Traefika. Od tego zależy też limit logowania z rozdziału 7, którego klucz to login, ścieżka i IP. Bez zaufania do proxy wszyscy mają adres Traefika, więc ktoś, kto zgaduje hasło Anny, blokuje logowanie samej Annie.

> **Pułapka:** w produkcji users-permissions ustawia ciasteczko odświeżania z flagą `Secure`, a Koa odmawia wysłania go po nieszyfrowanym połączeniu. Logowanie do kontenera po zwykłym HTTP zwróciło `500 Internal Server Error`, a w logu: `Cannot send secure cookie over unencrypted connection` z `sendRefreshAuthResponse`. To samo żądanie z nagłówkiem `X-Forwarded-Proto: https` dało `200` i `Set-Cookie: strapi_up_refresh...; secure; httponly`. Za Traefikiem bez `proxy.koa: true` Koa ignoruje ten nagłówek, więc logowanie pada mimo HTTPS, a hasło zostało już sprawdzone. Jeśli testujesz obraz produkcyjny lokalnie po HTTP, dodaj nagłówek ręcznie albo licz się z tym 500.

Strapi wysyła własną politykę CSP i HSTS (`strapi::security`, nagłówki powyżej). Nie dokładaj drugiej CSP w middleware `headers` Traefika: przeglądarka egzekwuje wszystkie otrzymane polityki naraz, więc łatwo zablokować panelowi skrypty albo obrazy. Gdy media wychodzą z S3 albo CDN (rozdział 8), rozszerz `img-src` i `media-src` w konfiguracji `strapi::security` w bazowym `config/middlewares.ts`. Limit rozmiaru uploadu ustawia `formidable.maxFileSize` w `strapi::body`, bo Traefik domyślnie nie ogranicza ciała żądania.

## Dane: eksport, import, kopie

`strapi export` pakuje treść, relacje, pliki z `public/uploads`, konfigurację i schematy. Z kopii roboczej na SQLite, z jednym obrazkiem w okładce artykułu:

```text
$ npx strapi export --key "$EXPORT_KEY" -f backups/redakcja
entities       49   17.3 KB   (api::article.article 7, plugin::users-permissions.user 2, ...)
assets          1    411.0 B
links         105   21.3 KB
configuration  37  125.6 KB
Export archive is in backups/redakcja.tar.gz.enc        # 17 KB, 4.5 s
$ npx strapi export --no-encrypt -f backups/redakcja-plain   # redakcja-plain.tar.gz
```

Archiwum nieszyfrowane rozpakowałem: rekordy użytkowników zawierają e-maile i hashe bcrypt haseł, a konfiguracja – klucz `plugin_users-permissions_grant` z danymi providerów OAuth. Eksport to dane osobowe i sekrety, więc trzymaj go zaszyfrowany (`--key`, AES-128 według dokumentacji) albo nie trzymaj wcale. Nie są eksportowane konta panelu admina ani API tokeny.

Import do kontenera robisz osobnym, jednorazowym kontenerem z tym samym obrazem, wolumenami i siecią:

```text
$ docker compose run --rm -v ./backups:/backups:ro strapi \
    node_modules/.bin/strapi import -f /backups/redakcja.tar.gz.enc --key "$EXPORT_KEY" --force
✔ entities: 49 transferred   ✔ assets: 1 transferred   ✔ links: 105 transferred
Import process has been completed successfully!                         # 8.6 s
$ curl -g 'localhost:1313/api/articles?fields[0]=title&populate[cover][fields][0]=url'
... {"id":7,"documentId":"nywq7zs8hidicead440io6t2","title":"Policies in Strapi 5",
     "cover":{"url":"/uploads/docker_cover_e94270a82c.png"}} ...   "total":3
$ curl -s localhost:1313/admin/init
{"data":{"uuid":"0e98cbca-...","hasAdmin":false,"menuLogo":null,"authLogo":null}}
```

`--force` pomija pytanie o skasowanie danych – import zastępuje całą bazę i katalog uploads. `documentId` przeżył przeniesienie, numeryczne `id` nie (8 w SQLite, 7 w Postgresie; rozdział 2). Okładkę serwuje kontener z wolumenu (`200 image/png`), Anna loguje się starym hasłem, a działający serwer pokazał nowe dane bez restartu.

`hasAdmin: false` oznacza, że pierwsza osoba, która otworzy `/admin`, założy konto Super Admina. Zaraz po imporcie utwórz administratora z CLI: `docker compose exec strapi node_modules/.bin/strapi admin:create-user` z tymi samymi opcjami co w rozdziale 7.

> **Pułapka:** dokumentacja Dockera radzi zamontować wolumen na `public/uploads`. Z takim wolumenem import padł: `The backup folder for the assets could not be created inside the public folder. Please ensure Strapi has write permissions on the public directory`. Uprawnienia były w porządku. Import przenosi `uploads/` do katalogu kopii obok (`fs.move`), a punktu montowania nie da się przenieść – ręczne `mv` w kontenerze dało `Resource busy`. Montuj wolumen na całym `public/`. Koszt: zmiany w `public/robots.txt` z nowego obrazu nie przykryją kopii w istniejącym wolumenie.

`strapi transfer --to https://cms.redakcja.example/admin --to-token <token>` przesyła to samo strumieniowo do działającej instancji (`strapi start`, token transferu z jej panelu). Tego wariantu nie uruchamiałem. Jeśli go nie używasz, wyłącz go w produkcji: `transfer.remote.enabled: false` w konfiguracji serwera.

Eksport Strapi przenosi dane między silnikami baz, ale na codzienną kopię lepszy jest `pg_dump`: obejmuje całą bazę z kontami admina i tokenami. Sprawdziłem kopię odtworzeniem do osobnej bazy w tym samym kontenerze:

```text
$ docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/redakcja-2026-10-03.dump
$ docker compose exec -T db sh -c '... createdb restore_check; pg_restore -d restore_check --no-owner;
    psql -d restore_check -tAc "select ... from articles"; dropdb restore_check' < backups/redakcja-2026-10-03.dump
7 articles, 3 published
```

Do zrzutu bazy dołóż archiwum wolumenu `public` (albo bucket z rozdziału 8) i oba wynoś poza serwer.

## Zmiany schematu i migracje

Rozdział 2 pokazał, że zmiana nazwy pola kasuje kolumnę przy starcie, a migracja w `database/migrations` ratuje dane, bo działa przed synchronizacją schematu. Ta kolejność ma drugą stronę, ważną przy wdrażaniu na pustą bazę.

> **Pułapka:** na świeżej bazie migracje też się uruchamiają i też przed synchronizacją, czyli zanim powstaną tabele. Migracja testowa wypisała `articles table exists = false`, a Strapi oznaczył ją jako wykonaną (`migrated 2026.10.03T00.00.00.probe.js`). Migracja, która zakłada istnienie tabeli, wywali więc start nowej instancji (nowy staging, odtworzenie z eksportu). Każdą migrację zaczynaj od `knex.schema.hasTable(...)` i `hasColumn(...)`, tak jak przykład z rozdziału 2.

`settings.forceMigration: false` w konfiguracji bazy wyłącza usuwanie tabel i kolumn przy synchronizacji, ale pominięte obiekty przestają być śledzone (dokumentacja). Pewniejszy jest prosty rytuał: `pg_dump` przed każdym wdrożeniem, które zmienia `schema.json`, i próba na stagingu z kopią produkcji.

## Aktualizacje

Strapi wydaje nową wersję co tydzień, zwykle w środę: w 2026 roku do 30 września było to 43 wydania, w tym 24 minory (dane z npm, październik 2026). Wszystkie pakiety `@strapi/*` muszą mieć tę samą wersję, więc podbija je razem `@strapi/upgrade`. Fundament jest na najnowszej 5.56.0 (`The project is already up-to-date (minor)`), więc pokaz zrobiłem na kopii `package.json` z wersją 5.40.0:

```text
$ npx @strapi/upgrade minor --dry -y
[INFO]  Upgrading from v5.40.0 to v5.56.0
[WARN]  Running the upgrade in dry mode. No files will be modified during the process.
[WARN]  Repository is not clean. Please commit or stash any changes before upgrading
[INFO]  (2/4) Applying the latest code modifications...
[INFO]  (4/4) Installing dependencies...
```

Bez `-y` narzędzie zatrzymuje się na pytaniu o brudne repozytorium. `npx @strapi/upgrade codemods ls` pokazał 13 codemodów, wszystkie dla wersji 5.0.0 i 5.1.0. W obrębie Strapi 5 aktualizacja to więc podbicie wersji i reinstalacja, a ryzyko leży w zmianach zachowania, których codemod nie wyłapie. Sekwencja: gałąź, `npx @strapi/upgrade minor`, `npm run build`, testy z rozdziału 12, nowy obraz, staging z kopią produkcyjnej bazy, wdrożenie. Nie musisz brać każdego wydania; rozsądny rytm to co kilka tygodni i od razu przy poprawkach bezpieczeństwa.

## Wydajność w skrócie

Strapi tworzy indeksy na `document_id`, `locale`, `published_at` i na tabelach relacji, ale nie na polach `uid`. Frontend „Redakcji” szuka każdego artykułu po `slug`. Migracja nie nadaje się tu przez pułapkę z pustą bazą, więc indeks zakładasz w `bootstrap`, który działa po synchronizacji schematu:

```ts
// src/index.ts
async bootstrap({ strapi }: { strapi: Core.Strapi }) {
  await strapi.db.connection.raw('CREATE INDEX IF NOT EXISTS articles_slug_idx ON articles (slug)');
},
```

Na SQLite indeks pojawił się po pierwszym starcie; w Postgresie składnia jest ta sama, ale tam tego kodu nie uruchamiałem. Reszta to zasady z wcześniejszych rozdziałów: `populate` tylko dla potrzebnych pól (rozdział 3) i `maxLimit: 100` w `config/api.ts`. Strapi nie ma cache odpowiedzi, więc cache leży we frontendzie z rewalidacją po webhooku (rozdział 11). Pula połączeń razy liczba replik musi się zmieścić w `max_connections` Postgresa (domyślnie 100).

## Checklista bezpieczeństwa

- Publicznie wystawiony jest tylko Traefik; Strapi i Postgres nie mają `ports` na VPS-ie, `.env` ma prawa `600` i nie trafia do obrazu.
- Konto admina z CLI zaraz po pierwszym starcie albo imporcie (`hasAdmin: false` to otwarte drzwi).
- `proxy.koa: true` z `maxIpsCount` równym liczbie twoich proxy, `server.url` z publicznym HTTPS.
- Uprawnienia Public nadawane kodem; dla frontendu token Custom, bo read-only czyta `/api/users` (rozdział 7).
- `allow_register` jest domyślnie `true` – wyłącz rejestrację w *Advanced settings*, jeśli czytelnicy nie zakładają kont.
- `strapi::cors` z listą originów frontendu (rozdział 11), jedna CSP – ze Strapi.
- Webhooki do sąsiednich kontenerów tylko z kodu, bo panel odrzuca w produkcji adresy prywatne (rozdział 8). Transfer wyłączony, jeśli go nie używasz.
- Eksporty szyfrowane, kopie `pg_dump` poza serwerem i regularnie odtwarzane.

## Podsumowanie

- `config/env/production/` zawiera tylko różnice: Postgres z kontrolą wymaganych zmiennych, `url` i `proxy`. Tablic middleware tam nie dokładaj.
- `strapi build` wczytuje całą konfigurację, więc kontrole zmiennych potrzebują przy budowaniu wartości zastępczych.
- Obraz wieloetapowy, `npm ci --omit=dev`, użytkownik `node`, `strapi start` jako PID 1; źródła TS zostają dla komend CLI.
- Postgres za healthcheckiem, wolumen na całym `public/`, inaczej import plików padnie.
- Za Traefikiem `proxy.koa: true` jest obowiązkowe – bez niego logowanie zwraca 500.
- `strapi export --key` przenosi dane między bazami, ale zawiera hashe haseł i pomija konta admina. Codzienną kopią jest `pg_dump`, sprawdzany odtworzeniem.
- Migracje działają przed synchronizacją także na pustej bazie, indeksy zakładaj w `bootstrap`, a aktualizacje przepuszczaj przez testy i staging.

## Co dalej

Masz całą drogę „Redakcji”: od modelu i trasy żądania, przez polityki, Document Service i pluginy, po obraz wdrażany na własny serwer. Następny krok to staging: drugi stos compose z kopią produkcyjnej bazy odtwarzaną co noc z `pg_dump`. Na nim sprawdzisz każdą aktualizację i migrację, zanim zobaczą je czytelnicy.

## Źródła

- https://docs.strapi.io/cms/installation/docker
- https://docs.strapi.io/cms/deployment
- https://docs.strapi.io/cms/deployment/guides/traefik
- https://docs.strapi.io/cms/configurations/database
- https://docs.strapi.io/cms/configurations/server
- https://docs.strapi.io/cms/configurations/environment
- https://docs.strapi.io/cms/features/data-management
- https://docs.strapi.io/cms/features/data-management/export
- https://docs.strapi.io/cms/features/data-management/import
- https://docs.strapi.io/cms/features/data-management/transfer
- https://docs.strapi.io/cms/database-migrations
- https://docs.strapi.io/cms/upgrade-tool
- https://docs.strapi.io/cms/upgrades
