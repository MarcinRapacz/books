# Rozdział 7. Użytkownicy, tokeny i uprawnienia

> **Cel rozdziału:** rozumieć, kto i czym uwierzytelnia się w Strapi (sesje users-permissions, API tokeny, konto panelu), umieć ustawić uprawnienia kodem i ograniczyć dane do tych, które należą do zalogowanego użytkownika.
>
> **Kod:** `examples/07-uwierzytelnianie/`. **Pakiety poza fundamentem:** brak.

„Redakcja” ma trzy rodzaje gości. Anna loguje się na stronie magazynu, żeby zobaczyć swoje teksty, także szkice. Serwer Next.js potrzebuje dostępu do API bez niczyjego hasła. Redaktorka moderuje komentarze w panelu admina. Każdy ma inny rodzaj tożsamości, inny token i inne miejsce, w którym ustawiasz uprawnienia.

Fundament ma też dziurę, którą widać jednym poleceniem. Rola Public ma uprawnienie `find` na artykułach, a to wystarczy, żeby anonimowo pobrać szkice:

```text
$ curl -g 'localhost:1307/api/articles?status=draft&fields[0]=title&fields[1]=publishedAt'
{"data":[ ... {"title":"Self-hosting Strapi with Docker","publishedAt":null}],
 "meta":{"pagination":{"total":4}}}
```

Artykuł Piotra, który nigdy nie został opublikowany, jest publicznie dostępny. Na końcu rozdziału go zamkniesz. Wcześniej poznasz sesje z refresh tokenami, które są domyślne w nowym projekcie, uprawnienia ustawiane kodem i rozszerzanie pluginu users-permissions.

## Dwa światy: panel i aplikacja

Administratorzy panelu i użytkownicy aplikacji żyją w osobnych tabelach (`admin_users` i `up_users`), logują się na osobnych trasach i dostają tokeny, których druga strona nie akceptuje. JWT Anny wysłany do `/admin/users/me` kończy się 401, tak samo jak token administratora wysłany do `/api/users/me`.

Uprawnieniami w panelu rządzi RBAC (Role-Based Access Control), dostępny w wersji darmowej. Domyślne role to Super Admin, Editor i Author. Możesz dodać własne, także przez Admin API, z którego korzysta formularz ról. Rola Moderator dostała w ten sposób (`PUT /admin/roles/:id/permissions`) odczyt komentarzy i `explorer.update` z `properties.fields: ["moderationStatus"]`, czyli edycję jednego pola. Nie myl roli Author z polem `author` artykułu: ona ogranicza administratora do wpisów, które sam utworzył w panelu. SSO dla panelu wymaga płatnej licencji. Tokeny dla Admin API (admin tokens, np. dla serwera MCP) omawia rozdział 12.

## Logowanie w trybie sesji

Plugin users-permissions ma dwa tryby wydawania tokenów (opcja `jwtManagement`). Dokumentacja i kod pluginu podają jako domyślny `legacy-support`, ale projekt utworzony przez `create-strapi-app` ma w `config/plugins.ts` tryb `refresh` z `sessions.httpOnly: true` – tak jak fundament „Redakcji”. Zobacz, co zwraca logowanie:

```text
$ curl -i -X POST localhost:1307/api/auth/local -H 'Content-Type: application/json' \
    -d '{"identifier":"anna","password":"Passw0rd!"}'
HTTP/1.1 200 OK
X-RateLimit-Limit: 10
Set-Cookie: strapi_up_refresh=eyJhbGciOi...; path=/; samesite=lax; httponly
Set-Cookie: strapi_up_refresh.sig=INHz5o...; path=/; samesite=lax; httponly
{"jwt":"eyJhbGciOi...","user":{"id":1,"documentId":"afvh6pf0...","username":"anna",...}}
```

W ciele są tylko `jwt` i `user`. `jwt` to krótko żyjący token dostępu (access token): jego payload to `{ userId: '1', sessionId: '1e8c61f3...', type: 'access' }`, a różnica `exp - iat` wynosi 600 sekund. Token odświeżania (refresh token) trafił do ciasteczka `httpOnly`, którego JavaScript w przeglądarce nie odczyta. 

Domyślne wartości (Strapi 5.56, październik 2026): token dostępu 10 minut (`accessTokenLifespan: 600`), token odświeżania wygasa po 14 dniach bez użycia (`idleRefreshTokenLifespan`) i najpóźniej po 30 dniach od zalogowania (`maxRefreshTokenLifespan`). Ciasteczko jest sesyjne (bez `maxAge`), `SameSite=Lax` i dostaje flagę `Secure` automatycznie przy `NODE_ENV=production`. Logowanie ma limit 10 żądań na minutę (`X-RateLimit-Limit: 10`), choć strona REST API dokumentacji podaje „5 na 5 minut”.

### Odświeżanie i rotacja

Gdy token dostępu wygaśnie, klient wywołuje `POST /api/auth/refresh`. Strapi szuka tokenu odświeżania najpierw w ciasteczku, potem w polu `refreshToken` ciała. Każde odświeżenie wydaje nowy token odświeżania (rotacja), a stary oznacza jako `rotated`:

```text
POST /api/auth/refresh  (bez ciasteczka)       → 400 "Missing refresh token"
POST /api/auth/refresh  (ciasteczko z logowania) → 200 {"jwt":"eyJhbGciOi..."} + nowy Set-Cookie
POST /api/auth/refresh  (to samo stare ciasteczko) → 401 "Invalid refresh token"
```

Ponowne użycie starego tokenu nie unieważnia całej rodziny – nowe ciasteczko działa dalej. W kliencie ma to jedną konsekwencję: dwa równoległe odświeżenia z tym samym ciasteczkiem dają `200` i `401`, a drugi wynik wygląda jak wylogowanie.

```ts
// client/auth-fetch.ts (fragment)
let pendingRefresh: Promise<boolean> | null = null;

// Single flight: a rotated refresh token is invalid, so two parallel refreshes would log the user out.
function refresh(): Promise<boolean> {
  pendingRefresh ??= (async () => {
    const res = await fetch(`${API_URL}/auth/refresh`, { method: 'POST', credentials: 'include' });
    accessToken = res.ok ? ((await res.json()) as { jwt: string }).jwt : null;
    return res.ok;
  })().finally(() => {
    pendingRefresh = null;
  });
  return pendingRefresh;
}
```

Token dostępu trzymasz w pamięci, a żądanie z odpowiedzią 401 powtarzasz raz po odświeżeniu (pełny plik w `examples/`). `credentials: 'include'` wysyła ciasteczko na inny origin, co wymaga też poprawnego `strapi::cors` (rozdział 11, razem z wersją dla Next.js). Przykład z dokumentacji („Authentication flow with JWT”) zapisuje `refreshToken` w `localStorage` – dokładnie tam, skąd ciasteczko `httpOnly` miało go zabrać.

### Wylogowanie i to, czego ono nie cofa

`POST /api/auth/logout` z tokenem dostępu usuwa bieżącą sesję i czyści ciasteczko. Body `{"scope":"all"}` wylogowuje ze wszystkich urządzeń, a `GET /api/auth/sessions` i `DELETE /api/auth/sessions/:id` pozwalają zbudować ekran „zalogowane urządzenia”:

```text
POST /api/auth/logout                → 200 {"ok":true}, Set-Cookie: strapi_up_refresh=; expires=1970
GET  /api/users/me (ten sam token)   → 200
POST /api/auth/refresh (ciasteczko)  → 401 "Invalid refresh token"
```

Token dostępu jest bezstanowy: Strapi sprawdza tylko podpis, czas i to, czy użytkownik istnieje. Po wylogowaniu działa więc aż do wygaśnięcia. Natychmiast odcina użytkownika dopiero `blocked: true`, bo strategia users-permissions przy każdym żądaniu pobiera użytkownika z bazy (`401 "Invalid credentials"`). Zmiana hasła (`/auth/change-password`) i reset hasła unieważniają wszystkie tokeny odświeżania użytkownika.

> **Pułapka:** „po restarcie serwera token przestał działać” prawie zawsze znaczy „minęło 10 minut”. Token dostępu jest podpisany sekretem `JWT_SECRET` (a gdy go brak – `admin.auth.secret`), więc przeżywa restart, a nawet skasowanie bazy i ponowny seed – w obu przypadkach `GET /api/users/me` zwróciło 200. Ten sam token po 10 minutach dał `401 "Missing or invalid credentials"`. Tokeny tracą ważność także po zmianie sekretu i po przełączeniu `jwtManagement`: token z trybu `refresh` w trybie legacy i odwrotnie kończy się 401, więc zmiana trybu wylogowuje wszystkich.

Uwaga na niespójność: `httpOnly: true` nie obejmuje wszystkich tras. `POST /api/auth/local/register` i `/auth/change-password` zwracają `{"jwt","refreshToken","user"}` w ciele i nie ustawiają ciasteczka (sprawdzone w 5.56, widać to w `controllers/auth.js` pluginu). Po rejestracji najprościej od razu wywołać logowanie i zignorować `refreshToken` z odpowiedzi.

### Tryb legacy

Po zmianie na `jwtManagement: 'legacy-support'` logowanie zwraca `{ jwt, user }` bez ciasteczka, a payload tokenu to `{ id: 1, iat, exp }` z ważnością 30 dni (`jwt.expiresIn`). `/api/auth/refresh`, `/logout` i `/sessions` odpowiadają 404. Skradziony token odetniesz tylko blokadą użytkownika albo zmianą sekretu dla wszystkich. Tryb legacy zostaw istniejącym klientom; nowe aplikacje pisz pod `refresh`.

## Uprawnienia w kodzie

Uprawnienie users-permissions to wiersz `{ action, role }`, np. `api::article.article.find` dla roli `public`. Klikanie w panelu działa lokalnie, ale na produkcji nikt nie pamięta, które pola zaznaczyć po wdrożeniu nowej akcji. Lepiej trzymać uprawnienia w `bootstrap`, który działa przy każdym starcie:

```ts
// src/index.ts (fragment)
const ROLE_PERMISSIONS: Record<string, string[]> = {
  authenticated: ['api::article.article.mine'],
};

const ensureRolePermissions = async (strapi: Core.Strapi) => {
  const roles = strapi.db.query('plugin::users-permissions.role');
  const permissions = strapi.db.query('plugin::users-permissions.permission');
  for (const [type, actions] of Object.entries(ROLE_PERMISSIONS)) {
    const role = await roles.findOne({ where: { type } });
    if (!role) throw new Error(`users-permissions role "${type}" does not exist`);
    for (const action of actions) {
      if ((await permissions.count({ where: { action, role: role.id } })) === 0) {
        await permissions.create({ data: { action, role: role.id } });
        strapi.log.info(`Granted ${action} to role ${type}`);
      }
    }
  }
};
```

Kod jest idempotentny: log `Granted api::article.article.mine to role authenticated` pojawia się tylko przy pierwszym starcie, a brak roli zatrzymuje start zamiast cicho pominąć uprawnienie. Plugin przy każdym starcie usuwa uprawnienia do akcji, których nie ma już w żadnym kontrolerze (`syncPermissions`), więc po zmianie nazwy akcji `bootstrap` nada je od nowa. Własną rolę (np. Editor) utworzysz w tym samym miejscu serwisem `strapi.plugin('users-permissions').service('role').createRole({ name, description })`, który sam wylicza `type` z nazwy (`editor`).

Rejestracja przyjmuje domyślnie tylko `username`, `email` i `password`. Próba ustawienia roli przez `POST /api/auth/local/register` z `"role":3` kończy się `400 "Invalid parameters: role"`, a nowy użytkownik dostaje rolę domyślną z ustawień pluginu. Własne pola dopuszczasz jawnie w `config/plugins.ts`: `register: { allowedFields: ['displayName'] }`.

## Rozszerzanie users-permissions

Trasy i kontrolery pluginu nie pochodzą z `createCoreRouter`, więc zmieniasz je w `src/extensions/users-permissions/strapi-server.ts`. Plik eksportuje funkcję, która dostaje obiekt pluginu przed rejestracją i musi go zwrócić. Frontend „Redakcji” chce wiedzieć, czy zalogowana osoba jest zwykłym czytelnikiem, czy redaktorem, ale `GET /api/users/me?populate=role` zwraca użytkownika bez roli – sanityzacja usuwa relację, do której rola Authenticated nie ma uprawnień.

```ts
// src/extensions/users-permissions/strapi-server.ts (bez typów)
export default (plugin: UsersPermissionsPlugin) => {
  // Public profile name; accepted on registration thanks to register.allowedFields.
  plugin.contentTypes.user.schema.attributes.displayName = { type: 'string', maxLength: 60 };

  const originalMe = plugin.controllers.user.me;
  plugin.controllers.user.me = async (ctx) => {
    await originalMe(ctx);
    const role = (ctx.state.user as { role?: RoleSummary } | undefined)?.role;
    if (ctx.body && role) {
      ctx.body = { ...ctx.body, role: { name: role.name, type: role.type } };
    }
  };

  return plugin;
};
```

Wrapper najpierw wywołuje oryginalny `me`, więc walidacja i sanityzacja zostają, a rolę bierze z `ctx.state.user`, który strategia ładuje razem z `role`. Nowe pole `displayName` dodane programowo trafia do schematu jak każde inne; rejestracja z `"displayName":"Ewa K."` tworzy użytkownika z tym polem, a `/users/me` zwraca teraz `"displayName":null,"role":{"name":"Authenticated","type":"authenticated"}`. Kontroler `user` to zwykły obiekt, ale `auth` (logowanie, rejestracja) jest fabryką `({ strapi }) => ({ ... })`. Żeby nadpisać jego akcję, owijasz całą fabrykę, co pokazuje przewodnik z dokumentacji.

## Tylko moje artykuły

Rozdział 4 pokazał, że polityka nie przefiltruje listy, a filtr `author` dopisany do `ctx.query` odpada na walidacji (`Invalid key author`). Filtr musi powstać po walidacji zapytania klienta, czyli w kontrolerze:

```ts
// src/api/article/controllers/article.ts
export default factories.createCoreController('api::article.article', ({ strapi }) => ({
  async mine(this: CoreController, ctx) {
    const user = ctx.state.user as { id: number } | undefined;
    if (!user) {
      return ctx.unauthorized();
    }
    await this.validateQuery(ctx);
    const query = await this.sanitizeQuery(ctx);

    // The ownership filter is added after sanitization, so the client can neither remove it
    // nor trip over the role's missing read access to the user content type.
    const { results, pagination } = await strapi.service('api::article.article').find({
      ...query,
      status: query.status ?? 'draft',
      filters: { $and: [query.filters ?? {}, { author: { id: user.id } }] },
    });
    const sanitized = await this.sanitizeOutput(results, ctx);
    return this.transformResponse(sanitized, { pagination });
  },
}));
```

Trasa `GET /articles/mine` leży w `routes/01-mine.ts`, żeby wyprzedzić `/articles/:id` (rozdział 4), a uprawnienie `mine` nadaje roli Authenticated `bootstrap` z poprzedniej sekcji. Rdzeniowy serwis `find` woła Document Service i zwraca `pagination` dla `meta`. Domyślnie lista pokazuje wersje robocze, bo autor chce widzieć także szkice; `?status=published` daje tylko opublikowane.

```text
GET /api/articles/mine?fields[0]=title&fields[1]=publishedAt   (JWT piotra)
{"data":[{"title":"Fetching Strapi from Next.js","publishedAt":null},
         {"title":"Self-hosting Strapi with Docker","publishedAt":null}],
 "meta":{"pagination":{"page":1,"pageSize":25,"pageCount":1,"total":2}}}
GET /api/articles/mine?filters[author][id]=2   (JWT anny)  → 400 "Invalid key author"
GET /api/articles/mine                         (bez tokenu) → 403 Forbidden
```

`publishedAt: null` oznacza tu wersję roboczą, a nie „nieopublikowany”; jeśli frontend ma pokazać status, pobierz go osobnym zapytaniem z `status: 'published'`. Alternatywą jest middleware Document Service (rozdział 6), ale działałoby ono przy każdym `findMany` – także w panelu, cronie i skryptach – i ukryłoby redakcji cudze artykuły. Reguła dotyczy jednej trasy HTTP, więc należy do kontrolera.

## Szkice tylko dla uprawnionych

Teraz dziura z początku rozdziału. Uprawnienie `find` nie rozróżnia `status=draft` i `status=published`, więc trzeba wymusić wersję opublikowaną dla każdego, kto nie ma prawa do podglądu. „Redakcja” daje to prawo tylko API tokenom (podgląd w Next.js, rozdział 11), a autorom – przez `/articles/mine`. Middleware trasy wpięte w `find` i `findOne`:

```ts
// src/api/article/middlewares/published-only.ts
const publishedOnly: Core.MiddlewareFactory = () => {
  return async (ctx, next) => {
    const strategy = (ctx.state.auth as { strategy?: { name?: string } } | undefined)?.strategy?.name;
    if (strategy !== 'content-api-token') {
      ctx.query = { ...ctx.query, status: 'published' };
    }
    await next();
  };
};
```

Tym razem rozpakowanie `ctx.query` jest celowe: zostawiasz klientowi filtry, sortowanie i paginację, a nadpisujesz tylko `status`. Router artykułów podpina je w `config` akcji `find` i `findOne`. Anonimowe `?status=draft` zwraca teraz trzy opublikowane artykuły z ustawionym `publishedAt`, `GET /api/articles/<documentId szkicu>?status=draft` daje 404, a API token nadal widzi cztery wersje robocze. Szczegóły draft & publish są w rozdziale 8.

> **Pułapka:** strategia API tokenów nazywa się w Strapi 5.56 `content-api-token`, nie `api-token`. Pierwsza wersja middleware porównywała z `'api-token'` i token podglądu dostawał po cichu wersje opublikowane, bez żadnego błędu. Nazwę sprawdzisz w `@strapi/admin/dist/server/server/src/strategies/content-api-token.js`, a uwierzytelniony użytkownik ma strategię `users-permissions` – tę samą co anonimowy gość, tylko z `credentials` różnym od `null`.

## API tokeny

API token to klucz dla programu, nie dla osoby: serwer Next.js, skrypt importu, build statycznej strony. Nie ma użytkownika (`ctx.state.user` jest pusty), więc `/api/users/me` i `/api/articles/mine` zwracają z nim 401. Token tworzysz w *Settings → API Tokens* albo przez Admin API, z którego korzysta ten formularz:

```text
$ npx strapi admin:create-user -e admin@example.com -p '...' -f Ada -l Admin
$ curl -X POST localhost:1307/admin/login ...   → {"data":{"token":"eyJhbGciOi...",...}}
$ curl -X POST localhost:1307/admin/api-tokens -H "Authorization: Bearer eyJhbGciOi..." \
    -H 'Content-Type: application/json' -d '{"name":"frontend-read-only","type":"read-only","lifespan":null}'
  → {"data":{"kind":"content-api","type":"read-only","accessKey":"da7ceba808...",...}}
```

Nowy projekt ma już dwa tokeny, „Read Only” i „Full Access”. Dzięki `secrets.encryptionKey` w `config/admin.ts` klucze da się później odczytać w panelu; bez niego tylko raz, przy tworzeniu. Zmiana `API_TOKEN_SALT` unieważnia wszystkie tokeny. Z tokenem read-only `POST /api/articles` daje 403, z full-access – 201.

> **Pułapka:** read-only znaczy „wszystkie akcje `find` i `findOne`”, także na użytkownikach. Token read-only zwrócił `GET /api/users?fields[0]=username&fields[1]=email` z adresami e-mail wszystkich trzech użytkowników, a full-access z `populate[author]=true` dołącza do artykułu pełny rekord autora. Token, który trafia do frontendu albo do zmiennej środowiskowej wielu serwisów, twórz jako typ Custom z zaznaczonymi tylko potrzebnymi akcjami i nigdy nie wysyłaj go do przeglądarki.

## Logowanie przez GitHub

Frontend kieruje użytkownika na `/api/connect/github`, GitHub po zalogowaniu wraca do Strapi, a Strapi przekazuje `access_token` na adres frontendu. Ten wymienia go na sesję przez `GET /api/auth/github/callback?access_token=...`; konto jest dopasowane po e-mailu albo utworzone. Konfiguracja leży w magazynie pluginu (klucz `grant`) i zwykle ustawia się ją w panelu. Możesz ją pisać w `bootstrap` ze zmiennych środowiskowych:

```ts
// src/index.ts (fragment; key and secret come from GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET)
const store = strapi.store({ type: 'plugin', name: 'users-permissions', key: 'grant' });
const grant = (await store.get()) as Record<string, GrantProvider>;
grant.github = { ...grant.github, enabled: true, key, secret, callback: frontendCallback };
await store.set({ value: grant });
```

Z fikcyjnym `client_id` lokalnie sprawdzisz tylko pierwszy krok: `GET /api/connect/github` odpowiada `302` na `https://github.com/login/oauth/authorize?client_id=dummy-client-id&...&redirect_uri=http://localhost:1307/api/connect/github/callback&scope=user,user:email`. Reszta wymaga aplikacji OAuth w GitHubie i publicznego adresu (GitHub nie akceptuje `localhost`). Callback w trybie `refresh` odpowiada tą samą funkcją co logowanie hasłem (`sendRefreshAuthResponse`). Przykładowy wynik: `{"jwt":"eyJhbGciOi...","user":{"username":"anna-gh","provider":"github",...}}` plus ciasteczko `strapi_up_refresh`.

Reset hasła (`/auth/forgot-password` → e-mail z kodem → `/auth/reset-password`) i potwierdzanie adresu e-mail (*Advanced settings → Enable email confirmation*) wymagają działającego providera e-maila, który konfiguruje rozdział 8. Przy włączonym potwierdzaniu rejestracja zwraca samego `user` bez tokenu, a niepotwierdzone konto nie zaloguje się.

## Podsumowanie

- Administratorzy panelu (RBAC, darmowe własne role) i użytkownicy aplikacji (users-permissions) mają osobne tabele, trasy i tokeny.
- Nowy projekt działa w trybie `refresh`: token dostępu na 10 minut w ciele odpowiedzi, token odświeżania w ciasteczku `httpOnly`, rotowany przy każdym `/auth/refresh`. Klient odświeża jednym, wspólnym żądaniem.
- Wylogowanie i usunięcie sesji nie unieważniają wydanego tokenu dostępu; natychmiast działa tylko `blocked: true`. „401 po restarcie” to zwykle wygasły token.
- Uprawnienia ról nadawaj idempotentnym kodem w `bootstrap`; users-permissions rozszerzasz w `src/extensions/users-permissions/strapi-server.ts`, owijając oryginalne akcje.
- Lista „tylko moje” to akcja kontrolera z filtrem dopisanym po `sanitizeQuery`, a nie polityka ani filtr w `ctx.query`.
- Uprawnienie `find` obejmuje `status=draft`; middleware trasy wymusza wersję opublikowaną dla wszystkich poza API tokenem podglądu.
- API token read-only czyta także użytkowników; dla frontendu twórz token Custom.

## Co dalej

Masz już komplet narzędzi do kontroli dostępu: uprawnienia ról, polityki, kontrolery i tokeny. Rozdział 8 przechodzi do funkcji wbudowanych, które z nich korzystają: draft & publish od strony API, i18n, media, e-mail (którego potrzebuje reset hasła), webhooki i cron.

## Źródła

- https://docs.strapi.io/cms/features/users-permissions
- https://docs.strapi.io/cms/features/users-permissions/rest-api
- https://docs.strapi.io/cms/backend-customization/guides/customizing-users-permissions-plugin-routes
- https://docs.strapi.io/cms/backend-customization/examples/authentication
- https://docs.strapi.io/cms/plugins-development/plugins-extension
- https://docs.strapi.io/cms/features/api-tokens
- https://docs.strapi.io/cms/features/admin-tokens
- https://docs.strapi.io/cms/features/rbac
- https://docs.strapi.io/cms/configurations/users-and-permissions-providers
- https://docs.strapi.io/cms/configurations/users-and-permissions-providers/github
