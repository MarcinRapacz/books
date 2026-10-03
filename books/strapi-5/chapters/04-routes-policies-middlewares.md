# Rozdział 4. Trasy, polityki i middleware

> **Cel rozdziału:** zrozumieć, co dzieje się z żądaniem między routerem a kontrolerem, i umieć świadomie wybrać miejsce dla reguły dostępu albo obróbki żądania: politykę, middleware trasy, middleware globalne albo kod w kontrolerze.
>
> **Kod:** `examples/04-routes-policies-middlewares/`. **Pakiety poza fundamentem:** brak.

W „Redakcji” rola Authenticated ma uprawnienie `update` na artykułach. To znaczy, że Piotr, zalogowany i z poprawnym tokenem, może zmienić tytuł artykułu Anny. Panel uprawnień users-permissions odpowiada tylko na pytanie „czy ta rola może wywołać tę akcję”, a nie „czy ten użytkownik może zmienić ten konkretny dokument”. Drugie pytanie wymaga kodu, który zna zarówno użytkownika, jak i dokument, i który uruchomi się, zanim kontroler cokolwiek zapisze.

Strapi daje na to kilka miejsc: polityki (policies), middleware trasy (route middlewares), middleware globalne i middleware Document Service. W dokumentacji i na forach przeczytasz, że „polityka to taki middleware”. To prawda tylko w połowie. Polityka rzeczywiście jest funkcją wpiętą w łańcuch Koa, ale ma inną sygnaturę, widzi inny obiekt kontekstu i potrafi tylko przepuścić albo zatrzymać żądanie. Middleware owija resztę łańcucha i może zmienić zarówno żądanie, jak i odpowiedź.

Na działającym projekcie dopiszesz politykę `is-owner`, limit komentarzy na minutę i globalne nagłówki cache, a potem zobaczysz w logach, w jakiej kolejności to wszystko się wykonuje. Kontrolery i serwisy omawia rozdział 5, middleware Document Service i lifecycles – rozdział 6.

## Co dokładnie dzieje się po dopasowaniu trasy

Najdokładniejszym opisem tego, co Strapi skleja z każdej trasy, jest plik `@strapi/core/dist/services/server/compose-endpoint.js` w `node_modules`. Dla każdej trasy Strapi tworzy łańcuch Koa w stałej kolejności:

```text
config/middlewares.ts (globalne, w kolejności z tablicy)
  → router (dopasowanie metody i ścieżki)
    → routeInfo      ctx.state.route = konfiguracja trasy
    → authenticate   JWT / API token → ctx.state.user, ctx.state.auth
    → authorize      czy rola ma uprawnienie do akcji (403 Forbidden)
    → policies       config.policies, po kolei
    → middlewares    config.middlewares, po kolei
    → kontroler      zwrócona wartość trafia do ctx.body
      → serwis → Document Service (+ jego middleware) → Query Engine
```

Wynikają z tego trzy rzeczy. Polityki działają **po** sprawdzeniu uprawnień roli, więc jeśli rola Public nie ma akcji `update`, twoja polityka w ogóle się nie uruchomi. Middleware trasy działają **po** politykach, a nie przed nimi – żądanie odrzucone przez politykę albo przez `authorize` nigdy do nich nie dotrze, a middleware trasy nie przygotuje też danych dla polityki. I wreszcie: wszystko poniżej routera dotyczy tylko tras Content API. Panel admina ma własne trasy (`/content-manager/...`), na które twoje polityki i middleware tras nie są podpięte.

## Trasy

### Core router i jego konfiguracja

Każdy typ treści z fundamentu ma plik `src/api/<nazwa>/routes/<nazwa>.ts` z jedną linijką: `factories.createCoreRouter(uid)`. Ta fabryka tworzy pięć tras (`find`, `findOne`, `create`, `update`, `delete`) i przyjmuje opcjonalny obiekt konfiguracji. `only` i `except` wyłączają część tras, `prefix` dodaje przedrostek do ścieżek, a `config` pozwala każdej akcji z osobna przypiąć polityki, middleware i ustawienie `auth`.

Tak wygląda router artykułów po zmianach z tego rozdziału:

```ts
// src/api/article/routes/article.ts
import { factories } from '@strapi/strapi';

const isOwner = { name: 'global::is-owner', config: { uid: 'api::article.article' } };
const trace = { name: 'global::trace', config: { label: 'route middleware' } };

export default factories.createCoreRouter('api::article.article', {
  config: {
    update: { policies: ['global::trace-policy', isOwner], middlewares: [trace] },
    delete: { policies: [isOwner] },
  },
});
```

Polityka i middleware mogą być podane jako sama nazwa (`'global::trace-policy'`) albo jako obiekt `{ name, config }`. Drugi zapis pozwala użyć tej samej polityki z różnymi parametrami na różnych trasach – tu `is-owner` dostaje UID typu treści, którego dotyczy. Elementy z przedrostkiem `trace` to pomoce do obserwowania kolejności wykonania; wrócisz do nich w sekcji o logach.

### Trasy własne i kolejność plików

Frontend „Redakcji” potrzebuje na stronie głównej trzech najnowszych artykułów. Możesz za każdym razem wysyłać `?sort=publishedAt:desc&pagination[pageSize]=3`, ale czytelniej jest mieć trasę `GET /api/articles/latest`. Nie potrzebujesz do niej nowego kontrolera: trasa własna może wskazać istniejącą akcję `find` i ustawić zapytanie w middleware przypiętym bezpośrednio jako funkcja.

```ts
// src/api/article/routes/01-custom.ts
import type { Core } from '@strapi/strapi';

// The route owns its query: client parameters (status, filters, populate) are not passed through.
const latestQuery: Core.MiddlewareHandler = async (ctx, next) => {
  ctx.query = {
    fields: ['title', 'slug', 'excerpt', 'publishedAt'],
    sort: 'publishedAt:desc',
    pagination: { pageSize: 3 },
  };
  await next();
};

export default {
  routes: [
    {
      method: 'GET',
      path: '/articles/latest',
      handler: 'api::article.article.find',
      config: { middlewares: [latestQuery] },
    },
  ],
};
```

Przypisanie do `ctx.query` przechodzi przez setter, który Strapi instaluje w middleware `strapi::query`: obiekt zostaje zserializowany przez `qs` z powrotem do query stringa. Kontroler `find` dostaje zapytanie tak, jakby wysłał je klient, łącznie z walidacją parametrów. Trasa korzysta z uprawnienia `find` roli Public, więc działa dla anonimowych czytelników, a zalogowany z ważnym tokenem też dostaje 200.

Przedrostek `01-` w nazwie pliku nie jest ozdobą. Strapi wczytuje pliki tras alfabetycznie, a router dopasowuje trasy w kolejności rejestracji. Gdy plik nazywa się `custom.ts`, trafia za `article.ts` i `GET /api/articles/latest` dopasowuje się najpierw do `GET /api/articles/:id` z `id = "latest"`:

```text
$ curl -s 'localhost:1304/api/articles/latest'   # plik custom.ts
{"data":null,"error":{"status":404,"name":"NotFoundError","message":"Not Found","details":{}}}
```

Po zmianie nazwy na `01-custom.ts` trasa zwraca trzy artykuły. Kolejność sprawdzisz poleceniem `npx strapi routes:list`, które wypisuje trasy dokładnie w tej kolejności, w jakiej router je dopasowuje: `/api/articles/latest` musi stać nad `/api/articles/:id`.

> **Pułapka:** pierwsza wersja tej trasy miała `auth: false` i middleware `ctx.query = { ...ctx.query, sort, pagination }`. Oba skróty są ryzykowne. `auth: false` nie znaczy „dostęp dla Public”, tylko „pomiń uwierzytelnianie i sprawdzanie roli” (`compose-endpoint.js` i serwis `auth` w `@strapi/core`). Trasa przestaje podlegać uprawnieniom z panelu, więc odebranie roli Public akcji `find` jej nie zamknie. `ctx.state.user` jest zawsze pusty, a śmieciowy token przechodzi z kodem 200 zamiast 401. Z kolei rozpakowanie `ctx.query` oddaje klientowi resztę parametrów: wywołanie `/api/articles/latest?status=draft&filters[title][$startsWith]=Self` zwróciło anonimowo szkic „Self-hosting Strapi with Docker” z `publishedAt: null`. Sanityzacja zapytania nadal usuwała `populate[author]` i odrzucała filtry po autorze, ale trasa „trzy najnowsze opublikowane” robiła już coś innego, niż obiecywała. Po poprawce ten sam adres zwraca trzy opublikowane artykuły, a zły token dostaje 401. `auth: false` zostaw dla tras, które same weryfikują wywołującego (webhook z podpisem, health check), a w middleware trasy buduj zapytanie od zera.

## Polityki

### Czym jest polityka

Polityka to funkcja `(policyContext, config, { strapi })`, którą Strapi wywołuje przed kontrolerem. Jej wynik interpretuje bardzo prosto: `true` albo `undefined` przepuszcza żądanie do następnej polityki, każda inna wartość kończy je błędem `PolicyError` z kodem 403 i komunikatem „Policy Failed”. Zamiast zwracać `false`, możesz rzucić własny `PolicyError` z `@strapi/utils` – wtedy klient dostanie twój komunikat i obiekt `details`. Polityka może być asynchroniczna; Strapi czeka na jej wynik.

Obiekt `policyContext` to płytka kopia kontekstu Koa (`Object.assign({ is, type }, ctx)` w `@strapi/utils`). Dzięki temu `policyContext.state` i `policyContext.params` wskazują na te same obiekty co w kontrolerze. Ale właściwości, które Koa udostępnia przez gettery prototypu, nie zostają skopiowane. W działającym projekcie widać to od razu: w polityce `policyContext.query` i `policyContext.method` mają wartość `undefined`, a `policyContext.request.query` i `policyContext.request.method` działają poprawnie. Polityka decyduje „tak albo nie” i nic więcej.

### Polityka `is-owner`

Reguła „autor edytuje tylko swoje artykuły” jest klasycznym zadaniem dla polityki: przed zapisem trzeba pobrać dokument, porównać jego autora z zalogowanym użytkownikiem i albo przepuścić żądanie, albo je zatrzymać. 

```ts
// src/policies/is-owner.ts (skrót, pełny plik w examples/)
type IsOwnerConfig = { uid: 'api::article.article' | 'api::comment.comment' };
export default async (
  policyContext: OwnerPolicyContext,
  config: IsOwnerConfig,
  { strapi }: { strapi: Core.Strapi }
): Promise<boolean> => {
  const user = policyContext.state.user;
  const documentId = policyContext.params.id;
  if (!user || !documentId) {
    return false;
  }
  const entry = await strapi.documents(config.uid).findOne({
    documentId,
    fields: ['documentId'],
    populate: { author: { fields: ['id'] } },
  });
  // Unknown document: let the controller answer with its regular 404.
  if (!entry) {
    return true;
  }
  if (entry.author?.id === user.id) {
    return true;
  }
  throw new errors.PolicyError('You can only modify your own entries', {
    policy: 'is-owner',
  });
};
```

W Strapi 5 parametr `:id` w ścieżce REST to `documentId`, czyli identyfikator dokumentu, a nie numeryczne `id` wiersza w bazie. Dlatego polityka szuka dokumentu przez `strapi.documents(uid).findOne({ documentId })`. Autor to relacja do `plugin::users-permissions.user`, więc porównujesz jego numeryczne `id` z `ctx.state.user.id`. Pobierasz tylko `documentId` i `id` autora, bo polityka działa przy każdym zapisie. Gdy dokument nie istnieje, polityka przepuszcza żądanie, a kontroler zwraca zwykłe 404. Odpowiedź 403 zdradzałaby, że coś pod tym identyfikatorem jest.

Typ `OwnerPolicyContext` to `Core.PolicyContext` uzupełniony o `state.user` i `params.id`. W Strapi 5.56 (październik 2026) typ `Core.PolicyContext` nie deklaruje tych pól, a `Core.PolicyHandler` opisuje funkcję synchroniczną, dlatego sygnatura asynchronicznej polityki jest wypisana ręcznie. Rozdział 12 wraca do typowania.

Wynik z uruchomionego projektu (`D` to `documentId` artykułu Anny):

```text
PUT /api/articles/$D  (JWT piotra eyJhbGciOi...)  → 403
{"data":null,"error":{"status":403,"name":"PolicyError","message":"You can only modify your own entries","details":{"policy":"is-owner"}}}
PUT /api/articles/$D  (JWT anny eyJhbGciOi...)    → 200
PUT /api/articles/$D  (bez tokenu)                → 403
{"data":null,"error":{"status":403,"name":"ForbiddenError","message":"Forbidden","details":{}}}
PUT /api/articles/doesnotexist000  (JWT anny)     → 404 NotFoundError
```

Zwróć uwagę na trzecią odpowiedź: to nie `PolicyError`, tylko `ForbiddenError` z etapu `authorize`. Rola Public nie ma uprawnienia `update`, więc żądanie zostało odrzucone, zanim polityka się uruchomiła. Ta sama polityka chroni `DELETE` – Anna próbująca usunąć artykuł Piotra dostaje identyczne 403.

### Polityki globalne, API i pluginów

Miejsce pliku decyduje o nazwie polityki. Plik `src/policies/is-owner.ts` to polityka globalna `global::is-owner`, dostępna dla każdej trasy w projekcie. Plik `src/api/comment/policies/article-is-published.ts` to polityka API `api::comment.article-is-published`; na trasach tego samego API możesz ją podać krótko, jako `'article-is-published'`, bo Strapi dopisze przedrostek na podstawie `info.apiName` trasy. Polityki pluginów mają nazwy `plugin::<plugin>.<nazwa>`. Listę zarejestrowanych polityk wypisuje `npx strapi policies:list`.

Sama obecność pliku niczego nie włącza. „Globalna” znaczy „dostępna z każdego miejsca”, a nie „działa na wszystkich trasach” – każdą trasę trzeba wskazać w `config.policies`. Jeśli chcesz regułę dla wszystkich tras, potrzebujesz middleware, nie polityki.

Polityka API dla komentarzy pilnuje, żeby czytelnicy komentowali tylko opublikowane artykuły. Czyta ciało żądania, które o tej porze jest już sparsowane przez `strapi::body`:

```ts
// src/api/comment/policies/article-is-published.ts (rdzeń)
const articleId = policyContext.request.body?.data?.article;
if (typeof articleId !== 'string') {
  return false;
}
const published = await strapi.documents('api::article.article').count({
  filters: { documentId: articleId },
  status: 'published',
});
return published > 0;
```

Komentarz do szkicu artykułu kończy się teraz odpowiedzią `403` z `{"name":"PolicyError","message":"Policy Failed","details":{}}`. To domyślny komunikat po `return false`. Frontend nie odróżni go od innych polityk, dlatego w `is-owner` lepszy jest jawny `PolicyError` z `details.policy`.

> **Pułapka:** dokumentacja polityk podaje przykład `policies: ['plugin::users-permissions.isAuthenticated']`. W Strapi 5.56 plugin users-permissions nie eksportuje żadnych polityk (`npx strapi policies:list` ich nie pokazuje), a nieznana nazwa polityki wywraca start serwera: `Error creating endpoint GET /articles/mine: Policy plugin::users-permissions.isAuthenticated not found.` Jeśli potrzebujesz takiego sprawdzenia, napisz jednolinijkową politykę globalną `(ctx) => Boolean(ctx.state.user)`. Dobra strona: literówka w nazwie polityki wychodzi przy starcie.

## Middleware

### Middleware globalne i kod po `await next()`

Middleware to fabryka `(config, { strapi }) => async (ctx, next) => { ... }`. Fabryka działa raz przy starcie (tu przygotujesz stan, na przykład mapę liczników), zwrócona funkcja – przy każdym żądaniu. Wszystko, co jest przed `await next()`, dzieje się w drodze do kontrolera. Wszystko po – w drodze powrotnej, gdy status i ciało odpowiedzi są już ustalone. Ta druga połowa to zasadnicza różnica w stosunku do polityki.

„Redakcja” chce, żeby CDN i frontend mogły cache'ować anonimowe odczyty Content API, a wszystko inne było oznaczone `no-store`. Taka decyzja zależy od statusu odpowiedzi, więc musi zapaść po `await next()`:

```ts
// src/middlewares/cache-headers.ts (bez importów i typu konfiguracji)
const cacheHeaders: Core.MiddlewareFactory<CacheHeadersConfig> = (config) => {
  const maxAge = config.maxAge ?? 60;
  return async (ctx, next) => {
    await next();
    if (!ctx.path.startsWith('/api/')) {
      return;
    }
    const isPublicRead =
      ctx.method === 'GET' && ctx.status === 200 && !ctx.get('Authorization');
    ctx.set(
      'Cache-Control',
      isPublicRead ? `public, max-age=${maxAge}, stale-while-revalidate=30` : 'no-store'
    );
  };
};
```

Middleware globalne nie działa, dopóki nie wpiszesz go do `config/middlewares.ts`. Ta tablica to dosłownie stos Koa: kolejność elementów jest kolejnością wykonania w drodze „w dół”, a odwrotną kolejnością w drodze powrotnej. Wbudowane elementy `strapi::*` konfigurujesz w tym samym miejscu, zamieniając nazwę na obiekt `{ name: 'strapi::cors', config: { origin: [...] } }`. Tak samo ustawisz limity `strapi::body` (domyślnie `jsonLimit: '1mb'`) albo nagłówki CSP w `strapi::security`. Szczegóły CORS i CSP wracają w rozdziałach 8, 11 i 13.

```ts
// config/middlewares.ts
const config: Core.Config.Middlewares = [
  'strapi::logger',
  // Before strapi::errors: code after `await next()` sees the final status, also on errors.
  { name: 'global::trace', config: { label: 'global middleware' } },
  { name: 'global::cache-headers', config: { maxAge: 300 } },
  'strapi::errors',
  'strapi::security',
  // rest of the file unchanged
];
```

Anonimowe `GET /api/articles/latest` dostaje teraz `Cache-Control: public, max-age=300, stale-while-revalidate=30`, a każda odpowiedź zapisu albo z tokenem – `no-store`. Middleware globalne działa dla wszystkich żądań, także dla panelu admina i plików z `public/`. Stąd warunek na ścieżkę `/api/`.

> **Pułapka:** dokumentacja radzi dopisywać własne middleware na końcu tablicy. Przy takim ustawieniu odmowa z `is-owner` wróciła bez nagłówka `Cache-Control`, a log z bloku `finally` pokazał `status 404`, choć klient dostał 403. Polityka **rzuca** `PolicyError`, wyjątek przelatuje przez `await next()` twojego middleware i omija kod za nim. Na status 403 zamienia go dopiero `strapi::errors`, który leży wyżej na stosie. Middleware, które ma widzieć ostateczny status także przy błędach, umieść przed `strapi::errors` (albo otocz `next()` blokiem `try/finally` i pamiętaj, że status będzie jeszcze surowy).

### Middleware trasy: limit komentarzy

Jeden zalogowany użytkownik ze skryptem może zalać moderację setką komentarzy w minutę. Limit dotyczy jednej trasy (`POST /api/comments`), potrzebuje identyfikacji użytkownika i musi ustawić nagłówki odpowiedzi. To zadanie dla middleware trasy, nie dla polityki: polityka nie ustawi `Retry-After` i nie zwróci statusu 429.

```ts
// src/api/comment/middlewares/rate-limit.ts (rdzeń)
const rateLimit: Core.MiddlewareFactory<RateLimitConfig> = (config, { strapi }) => {
  const max = config.max ?? 5;
  const windowMs = config.windowMs ?? 60_000;
  const windows = new Map<string, Window>();
  return async (ctx, next) => {
    const user = ctx.state.user as { id: number } | undefined;
    const key = user ? `user:${user.id}` : `ip:${ctx.request.ip}`;
    const now = Date.now();
    let window = windows.get(key);
    if (!window || window.resetAt <= now) {
      window = { count: 0, resetAt: now + windowMs };
      windows.set(key, window);
    }
    window.count += 1;
    ctx.set('X-RateLimit-Remaining', String(Math.max(0, max - window.count)));
    if (window.count > max) {
      const retryAfter = Math.ceil((window.resetAt - now) / 1000);
      ctx.set('Retry-After', String(retryAfter));
      return ctx.tooManyRequests('Too many comments, try again later', { retryAfter });
    }
    await next();
  };
};
```

Plik w `src/api/comment/middlewares/` rejestruje middleware pod nazwą `api::comment.rate-limit`. W routerze komentarzy podpinasz je razem z polityką:

```ts
// src/api/comment/routes/comment.ts
export default factories.createCoreRouter('api::comment.comment', {
  config: {
    create: {
      policies: ['article-is-published'],
      middlewares: [
        { name: 'api::comment.rate-limit', config: { max: 3, windowMs: 60_000 } },
      ],
    },
  },
});
```

Metoda `ctx.tooManyRequests` nie pochodzi z Koa. Strapi dodaje do kontekstu pomocnika dla każdego statusu 4xx i 5xx z `node:http` (`ctx.badRequest`, `ctx.forbidden`, `ctx.tooManyRequests`...), a odpowiedź ma ten sam format błędu co reszta API. Cztery komentarze Piotra w ciągu minuty:

```text
POST /api/comments  → 201  X-RateLimit-Remaining: 2
POST /api/comments  → 201  X-RateLimit-Remaining: 1
POST /api/comments  → 201  X-RateLimit-Remaining: 0
POST /api/comments  → 429  Retry-After: 60
{"data":null,"error":{"status":429,"name":"TooManyRequestsError","message":"Too many comments, try again later","details":{"retryAfter":60}}}
POST /api/comments (anna) → 201  X-RateLimit-Remaining: 2
```

Anna ma własne okno, bo kluczem jest `id` użytkownika. Ponieważ middleware trasy działa po politykach, komentarz do szkicu odrzucony przez `article-is-published` nie zużywa limitu. Mapa w pamięci procesu wystarcza dla jednej instancji. Przy kilku replikach za load balancerem każda liczy osobno i trzeba wspólnego magazynu, na przykład Redisa. Przy dużym ruchu trzeba też okresowo usuwać wygasłe okna. Strapi stosuje ten wzorzec u siebie: trasy `/api/auth/*` pluginu users-permissions mają middleware trasy `plugin::users-permissions.rateLimit` (domyślnie 10 żądań na 60 sekund, opcja `ratelimit` w konfiguracji pluginu).

## `is-owner`: polityka czy middleware?

Strona dokumentacji o middleware zaleca, by „od Strapi v4” zastąpić politykę is-owner middleware trasy. Middleware ma realną przewagę, gdy reguła musi coś zmienić: dopisać filtr, przyciąć odpowiedź, ustawić pole. Dla decyzji „wolno albo nie” przy `update` i `delete` polityka jest prostsza i lepiej nazwana. Ma też jedną własność, której middleware nie ma: działa przed middleware trasy, więc odmowa nie zużywa na przykład limitu żądań.

Uważaj też na sam kod tego przykładu. `isOwner` z dokumentacji middleware wywołuje `strapi.documents(uid).findOne(entryId, { populate: '*' })`. To sygnatura w stylu Strapi 4. W Strapi 5 `findOne` przyjmuje jeden obiekt `{ documentId, ... }`, a wywołanie z ciągiem znaków zwraca po cichu `null`. Kod przykładu odczytuje potem `entry.author.id` i każde żądanie kończy się błędem 500. Kopiując snippety z dokumentacji, sprawdzaj sygnatury Document Service z rozdziałem 6.

Osobna sprawa to lista. Polityka `is-owner` na `find` nie ma sensu: nie ma `params.id`, a polityka nie potrafi przefiltrować listy, może ją tylko w całości odrzucić. Naturalny odruch to middleware, które dopisuje do `ctx.query` filtr `author.id`. W „Redakcji” kończy się to tak:

```text
GET /api/articles/mine  (middleware dopisuje filters[author][id]=<user.id>)
{"data":null,"error":{"status":400,"name":"ValidationError","message":"Invalid key author",...}}
```

Walidacja zapytania w kontrolerze sprawdza filtry względem uprawnień roli, a rola Authenticated nie może czytać użytkowników, więc relacja `author` jest dla niej niewidoczna. Filtr „tylko moje” należy ustawić tam, gdzie nie przechodzi przez walidację parametrów klienta: w kontrolerze (rozdział 5) albo w middleware Document Service (rozdziały 6 i 7).

## Kolejność wykonania na logach

Żeby zobaczyć cały łańcuch, w przykładach są trzy pomocnicze elementy: middleware `global::trace` (ten sam plik użyty raz globalnie, raz na trasie, z różnym `label`), polityka `global::trace-policy` i jednolinijkowe middleware Document Service w `register` z `src/index.ts`, które loguje akcję i UID (mechanizm opisuje rozdział 6). Middleware `trace` loguje w bloku `finally`, więc zapisuje się także wtedy, gdy coś niżej rzuci wyjątek.

Anna zmienia swój artykuł (`PUT /api/articles/:id`, 200):

```text
[trace] global middleware: before next()
[trace] policy: user=anna params={"id":"jwamfanw4h1oblx64jbjwk8k"}
[trace] document service: findOne api::article.article      ← is-owner pobiera autora
[trace] route middleware: before next()
[trace] document service: update api::article.article       ← kontroler → serwis
[trace] route middleware: after next(), status 200
[trace] global middleware: after next(), status 200
http: PUT /api/articles/jwamfanw4h1oblx64jbjwk8k (118 ms) 200
```

Piotr próbuje zmienić ten sam artykuł (403):

```text
[trace] global middleware: before next()
[trace] policy: user=piotr params={"id":"jwamfanw4h1oblx64jbjwk8k"}
[trace] document service: findOne api::article.article
[trace] global middleware: after next(), status 403
http: PUT /api/articles/jwamfanw4h1oblx64jbjwk8k (31 ms) 403
```

Middleware trasy w ogóle się nie uruchomiło, a kontroler nie dostał żądania. Na koniec zmiana tego samego typu treści z panelu admina, wysłana przez Admin API (`PUT /content-manager/collection-types/api::article.article/:documentId` z tokenem administratora):

```text
[trace] document service: findOne api::article.article
[trace] document service: update api::article.article
http: PUT /content-manager/collection-types/api::article.article/lgh5n19xmtzc38lwwzl2io09 (235 ms) 200
```

Ani polityka `is-owner`, ani middleware trasy nie zobaczyły tej zmiany, bo dotyczą wyłącznie tras Content API. Middleware globalne co prawda działa także dla tego żądania, ale `trace` pomija ścieżki spoza `/api/`. Jedyną warstwą, którą przechodzi zarówno REST, jak i panel, jest Document Service. Jeśli reguła ma obowiązywać niezależnie od tego, skąd przyszła zmiana (wyliczanie `readingTime`, slug, blokada usunięcia kategorii), jej miejsce jest w middleware Document Service, czyli w rozdziale 6.

## Polityka, middleware czy kontroler

| | Polityka | Middleware trasy | Middleware globalne | Middleware Document Service | Kontroler |
|---|---|---|---|---|---|
| Gdzie | `src/policies`, `src/api/*/policies` | `src/api/*/middlewares`, `src/middlewares`, funkcja w trasie | `src/middlewares` + `config/middlewares.ts` | `strapi.documents.use()` w `register` | `src/api/*/controllers` |
| Kiedy działa | po `authorize`, przed middleware trasy | po politykach, wokół kontrolera | wokół całego żądania, każdego | wokół wywołania `strapi.documents()` | na końcu łańcucha trasy |
| Co widzi | kopia `ctx`: `state`, `params`, `request` | pełny `ctx` | pełny `ctx`, także trasy admina i pliki | `uid`, `action`, `params` – bez HTTP | pełny `ctx`, serwisy |
| Co może | przepuścić albo zatrzymać (403) | zmienić żądanie i odpowiedź, zakończyć | to samo co trasy, globalnie | zmienić dane i wynik operacji | wszystko, co zwraca odpowiedź |
| Panel admina | nie | nie | tak | tak | nie |
| Przykład w „Redakcji” | `is-owner`, komentarz tylko do opublikowanych | limit komentarzy, domyślne parametry `/latest` | `Cache-Control`, pomiar czasu | `readingTime`, slug (rozdz. 6) | akcja `approve`, odpowiedź własnego kształtu (rozdz. 5) |

Praktyczna reguła wyboru jest krótka. Pytanie „czy ten użytkownik może wykonać tę akcję na tym dokumencie” to polityka. Coś, co zmienia żądanie albo odpowiedź HTTP dla wybranych tras, to middleware trasy, a dla wszystkich tras – middleware globalne. Reguła o danych, która musi działać także w panelu admina i w cronie, to middleware Document Service. Logika, która tworzy odpowiedź, to kontroler i serwis.

## Podsumowanie

- Dla każdej trasy Strapi składa łańcuch: `routeInfo` → `authenticate` → `authorize` → polityki → middleware trasy → kontroler. Polityki działają po sprawdzeniu roli, middleware trasy – po politykach.
- `createCoreRouter(uid, { only, except, prefix, config })` konfiguruje polityki, middleware i `auth` dla każdej akcji z osobna. Trasy własne wczytywane są alfabetycznie, dlatego `01-custom.ts` musi wyprzedzić `article.ts`, gdy ścieżka koliduje z `/:id`.
- `auth: false` wyłącza uwierzytelnianie i uprawnienia roli, a nie „otwiera trasę dla Public”. Middleware trasy powinno budować zapytanie od zera, a nie rozpakowywać `ctx.query` klienta.
- Polityka zwraca `true`/`undefined` albo zatrzymuje żądanie; `PolicyError` z `@strapi/utils` daje własny komunikat i `details`. `policyContext` to płytka kopia `ctx`, więc używaj `request.query` i `request.body`, nie `query` i `body`.
- `is-owner` sprawdza `documentId` z `params.id` przez Document Service. Nieznany dokument zostawia kontrolerowi (404), a cudzy blokuje (403).
- Middleware globalne trzeba wpisać do `config/middlewares.ts`. Kod po `await next()` widzi ostateczny status tylko wtedy, gdy middleware leży przed `strapi::errors`.
- Limit żądań to middleware trasy: ma dostęp do użytkownika, ustawia nagłówki i zwraca 429 przez `ctx.tooManyRequests`.
- Polityki i middleware tras nie widzą zmian z panelu admina; regułę o danych umieszczasz w middleware Document Service.

## Co dalej

Polityki i middleware decydują, czy żądanie dotrze do kontrolera i w jakiej postaci. W rozdziale 5 przejdziesz na drugą stronę tej granicy: rozszerzysz kontroler artykułów, przeniesiesz logikę do serwisu, dodasz akcję `POST /comments/:id/approve` z trasą z tego rozdziału i zobaczysz, jak `sanitizeQuery` i `sanitizeOutput` chronią przed wyciekiem danych, które właśnie zablokowały filtr `author` na liście.

## Źródła

- https://docs.strapi.io/cms/backend-customization
- https://docs.strapi.io/cms/backend-customization/routes
- https://docs.strapi.io/cms/backend-customization/policies
- https://docs.strapi.io/cms/backend-customization/middlewares
- https://docs.strapi.io/cms/configurations/middlewares
- https://docs.strapi.io/cms/backend-customization/examples/policies
- https://docs.strapi.io/cms/backend-customization/examples/routes
- https://docs.strapi.io/cms/backend-customization/examples/middlewares
- https://docs.strapi.io/cms/error-handling
- https://docs.strapi.io/cms/api/document-service/middlewares
- https://docs.strapi.io/cms/cli
