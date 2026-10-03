# Rozdział 1. Architektura i droga żądania

> **Cel rozdziału:** zrozumieć, przez jakie warstwy przechodzi żądanie w Strapi 5, i wiedzieć, w której z nich umieścić daną logikę.
>
> **Kod:** `examples/01-architektura/`. **Pakiety poza fundamentem:** brak.

Redakcja ma już typy treści, uprawnienia i dane z seeda. Za chwilę pojawią się prawdziwe wymagania: autor może edytować tylko swoje artykuły, komentarze czekają na moderację, slug i czas czytania mają się liczyć same, a frontend ma odświeżać cache po publikacji. Każde z nich da się napisać w Strapi na co najmniej trzy sposoby – w polityce, w middleware albo w kontrolerze – i każdy z tych sposobów zachowa się inaczej, gdy redaktorka zmieni artykuł w panelu admina zamiast przez API.

Ten rozdział jest mapą reszty książki: z czego Strapi składa się pod spodem, jak wygląda projekt na dysku i przez jakie warstwy przechodzi żądanie, zanim dotknie bazy – narysowane i sprawdzone w logach uruchomionego projektu. Na koniec dostaniesz tabelę „gdzie umieścić logikę”, do której wrócisz przy rozdziałach 4–6.

## Co jest pod spodem

Back-end Strapi to serwer HTTP oparty na Koa. Jeśli znasz Express, Koa jest jego młodszym kuzynem: każdy middleware dostaje obiekt kontekstu `ctx` (żądanie, odpowiedź i miejsce na stan) oraz funkcję `next()`, a łańcuch middleware działa jak cebula. Kod przed `await next()` wykonuje się w drodze „do środka”, kod po `await next()` – w drodze powrotnej, gdy odpowiedź jest już gotowa. Ta jedna zasada tłumaczy później, dlaczego middleware może zmierzyć czas żądania albo dopisać nagłówek, a polityka już nie.

Na Koa Strapi nakłada własne warstwy. Router zamienia pliki tras na endpointy. Rejestry trzymają kontrolery, serwisy, polityki i middleware pod identyfikatorami (UID). Document Service obsługuje dokumenty, czyli treść z wersjami roboczą i opublikowaną oraz z lokalizacjami. Pod nim leży Query Engine, który przez Knex rozmawia z bazą. Ten sam proces serwuje też panel admina – aplikację React, która komunikuje się z serwerem przez własne, administracyjne API.

Projekt w TypeScripcie nie jest wykonywany wprost ze źródeł: `strapi develop` kompiluje `config/` i `src/` do `dist/` i stamtąd ładuje aplikację, łącznie z konfiguracją. Dlatego błąd w dowolnym pliku `src/` zatrzymuje cały serwer, a nie jeden endpoint.

## Struktura projektu

Strapi ładuje kod według konwencji katalogów, a nie przez jawne importy. Plik położony we właściwym miejscu zostaje zarejestrowany pod przewidywalnym UID-em. Projekt Redakcji wygląda tak (część katalogów pojawi się dopiero w kolejnych rozdziałach; pozostałe API powtarzają układ `article`):

```text
config/            admin, api, database, middlewares, plugins, server (*.ts)
config/env/<env>/  nadpisania konfiguracji dla NODE_ENV=<env>
src/index.ts       register / bootstrap / destroy
src/api/article/
  content-types/article/schema.json   → api::article.article
  controllers/ services/ routes/      → kontroler, serwis, trasy tego API
  policies/ middlewares/              → api::article.<nazwa>
src/components/shared/*.json          → shared.seo, shared.quote ...
src/middlewares/  src/policies/       → global::<nazwa>
src/extensions/<plugin>/              → rozszerzenia wbudowanych pluginów
src/plugins/<plugin>/                 → lokalne pluginy
types/generated/                      → typy wygenerowane ze schematów
```

Katalogi `policies/` i `middlewares/` tworzysz sam, gdy są potrzebne. Typy w `types/generated/` odświeżają się przy każdym starcie `strapi develop` (w logu widać krok „Generating types”), więc nie edytujesz ich ręcznie; szczegóły w rozdziale 12. Rozszerzanie pluginów i własne pluginy to rozdział 9, panel admina – rozdział 10.

## Droga żądania

Zanim kontroler artykułów zobaczy żądanie, przechodzi ono przez kilka bramek. Kolejność poniżej nie pochodzi z dokumentacji, tylko z kodu, który składa endpoint (`@strapi/core/dist/services/server/compose-endpoint.js`), i z logów pokazanych dalej:

```text
żądanie HTTP
  → globalne middleware (config/middlewares.ts, po kolei)
    → router: dopasowanie trasy, ctx.state.route
      → authenticate: JWT użytkownika albo API token
      → authorize: czy rola ma uprawnienie do akcji (inaczej 401/403)
      → polityki trasy (true/false)
      → middleware trasy
      → kontroler → serwis
        → Document Service (+ jego middleware) → Query Engine → baza
  ← odpowiedź wraca przez middleware trasy i globalne (kod po await next())
```

Globalne middleware obsługują każde żądanie: do API, do panelu, do plików w `public/`. Uwierzytelnienie i sprawdzenie uprawnień z ról users-permissions dzieje się, zanim ruszy jakikolwiek twój kod związany z trasą – dlatego żądanie bez uprawnienia kończy się 403 i nie dociera nawet do polityki. Polityki tylko przepuszczają albo blokują, middleware trasy może zmieniać żądanie i odpowiedź, a kontroler z serwisem wykonują właściwą pracę przez Document Service.

> **Pułapka:** dokumentacja („Back-end customization”, „Routes”) opisuje polityki i middleware trasy w jednym kroku i nie mówi, co działa pierwsze, a intuicja z Koa podpowiada, że middleware owija wszystko. W Strapi 5.56 (październik 2026) najpierw wykonują się polityki, potem middleware trasy. Jeśli middleware trasy ma przygotować coś dla polityki (np. wczytać dokument do `ctx.state`), polityka tego nie zobaczy.

### Śledzenie żądania na żywo

Najprościej przekonać się o tej kolejności, dokładając do każdej warstwy jedną linię logu. Zacznij od globalnego middleware w `src/middlewares/request-trace.ts`. Plik w tym katalogu jest rejestrowany jako `global::request-trace`, ale działa dopiero po dopisaniu go do `config/middlewares.ts`.

```ts
const requestTrace: Core.MiddlewareFactory<RequestTraceConfig> = (config, { strapi }) => {
  const slowMs = config.slowMs ?? 500;

  return async (ctx, next) => {
    const startedAt = Date.now();
    strapi.log.info(`[trace] → ${ctx.method} ${ctx.url}`);

    await next();

    // The router sets ctx.state.route, so it is only readable after next() resolves
    const route = ctx.state.route;
    const target =
      typeof route?.handler === 'string' ? `${route.info.type} ${route.handler}` : 'no controller';
    const elapsed = Date.now() - startedAt;
    const level = elapsed > slowMs ? 'warn' : 'info';
    strapi.log[level](`[trace] ← ${ctx.status} ${ctx.method} ${ctx.path} (${target}, ${elapsed} ms)`);
  };
};
```

Zewnętrzna funkcja (fabryka) wykonuje się raz, przy starcie, i dostaje konfigurację z `config/middlewares.ts`; zwracana funkcja `(ctx, next)` – przy każdym żądaniu. W drodze do środka middleware nie zna jeszcze trasy, bo `ctx.state.route` ustawia router, który działa „głębiej”. Dopiero po `await next()` znamy trasę, status i czas.

Do śladu dochodzą trzy krótsze elementy: middleware Document Service zarejestrowany w `register` (`strapi.documents.use(...)`, pełny plik w `examples/`), demonstracyjna polityka `global::trace-policy`, która zawsze zwraca `true`, oraz middleware trasy, podpięte do akcji `find` w core routerze artykułów:

```ts
export default factories.createCoreRouter('api::article.article', {
  config: {
    find: {
      policies: ['global::trace-policy'],
      middlewares: [traceRouteMiddleware],
    },
  },
});
```

Po starcie (`PORT=1301 npx strapi develop --no-watch-admin --no-build-admin`) wysyłasz dwa żądania: publiczną listę artykułów i anonimową próbę utworzenia artykułu.

```text
$ curl -sg 'localhost:1301/api/articles?fields[0]=title&sort=title&pagination[pageSize]=2'
[trace] → GET /api/articles?fields[0]=title&sort=title&pagination[pageSize]=2
[trace]   route policy
[trace]   route middleware
[trace]   documents api::article.article findMany
[trace]   documents api::article.article count
[trace] ← 200 GET /api/articles (content-api api::article.article.find, 21 ms)
http: GET /api/articles?fields[0]=title&sort=title&pagination[pageSize]=2 (21 ms) 200

$ curl -s -X POST localhost:1301/api/articles \
    -H 'Content-Type: application/json' -d '{"data":{"title":"Anonymous draft"}}'
[trace] → POST /api/articles
[trace] ← 403 POST /api/articles (content-api api::article.article.create, 10 ms)
```

Pierwsze żądanie przeszło przez wszystkie warstwy w kolejności z diagramu. Kontroler `find` wywołał Document Service dwa razy: raz po dane, raz po licznik do `meta.pagination`. Linia `http:` pochodzi z wbudowanego `strapi::logger`, który stoi w konfiguracji przed naszym middleware, więc jest „bardziej na zewnątrz” cebuli i loguje jako ostatni. Drugie żądanie odbiło się na etapie `authorize`: rola Public nie ma uprawnienia `create`, więc nie wykonała się żadna polityka ani żadne zapytanie do bazy. To ważne przy projektowaniu: polityki i middleware trasy działają tylko dla żądań, które przeszły już sprawdzenie uprawnień ról.

## Content API i Admin API

Strapi wystawia dwa rodzaje tras, a log pokazuje je w polu `route.info.type`. Trasy Content API (`content-api`) to te, z których korzysta frontend Redakcji: domyślnie pod prefiksem `/api` (opcja `api.rest.prefix`), uwierzytelniane JWT użytkownika users-permissions albo API tokenem. Trasy administracyjne (`admin`) obsługują panel: `/admin/*`, `/content-manager/*`, `/upload/*` i trasy admina innych pluginów. Uwierzytelnia je osobny JWT administratora, a dostęp sprawdzają polityki RBAC panelu, takie jak `admin::hasPermissions`.

Tak wygląda ślad, gdy redaktorka otwiera listę artykułów w panelu (żądanie wysłane curl-em z tokenem administratora):

```text
[trace] → GET /content-manager/collection-types/api::article.article?page=1&pageSize=2
[trace]   documents api::article.article findMany
[trace]   documents api::article.article count
[trace] ← 200 GET /content-manager/collection-types/api::article.article (admin collection-types.find, 44 ms)
```

Globalny middleware i middleware Document Service zadziałały, ale polityka i middleware trasy artykułów – nie, bo panel nie używa tras z `src/api/article/routes`. Odpowiedź też się różni: panel widzi 4 artykuły (również ten, który ma tylko wersję roboczą), publiczne API – 3. Wniosek: reguła, która ma obowiązywać niezależnie od tego, skąd przyszła zmiana (slug, czas czytania, blokada usuwania kategorii), należy do Document Service, a nie do warstwy tras; to temat rozdziału 6. GraphQL ma własny mechanizm polityk i middleware (rozdział 3).

## register, bootstrap, destroy

Plik `src/index.ts` eksportuje trzy funkcje cyklu życia aplikacji. Strapi czeka na każdą z nich (mogą być `async`), a błąd w którejkolwiek przerywa start.

`register` wykonuje się jako pierwsza, po `register` pluginów, ale przed połączeniem z bazą, przed inicjalizacją middleware i tras. To miejsce na rejestrowanie rzeczy, które muszą istnieć, zanim aplikacja ruszy: middleware Document Service, custom fields, rozszerzenia pluginów. `bootstrap` startuje, gdy baza jest zsynchronizowana ze schematami, a middleware i trasy zainicjalizowane, tuż przed otwarciem portu – tu ustawisz uprawnienia ról kodem, utworzysz brakujące dane startowe albo zaplanujesz zadania. `destroy` wywołuje się przy zamykaniu, także przy każdym przeładowaniu w trybie develop (w logu Redakcji widać `[trace] destroy` po każdej zmianie pliku), i służy do zamykania połączeń i zatrzymywania timerów.

> **Pułapka:** zapytanie do bazy w `register` nie działa. Po dopisaniu `await strapi.documents('api::article.article').count({})` do `register` start kończy się błędem `Error: Model api::article.article not found` – modele nie są jeszcze zarejestrowane w warstwie bazy. Ten sam kod w `bootstrap` zwraca liczbę artykułów.

## Konfiguracja

Każdy plik w `config/` eksportuje obiekt albo funkcję, która dostaje `{ env }`. Funkcja `env()` czyta zmienne środowiskowe (także z `.env`) i ma warianty z rzutowaniem: `env.int`, `env.float`, `env.bool` (prawda tylko dla napisu `true`), `env.json`, `env.array`, `env.date` i `env.oneOf`. W Redakcji próg „wolnego” żądania z middleware śledzącego trafia do konfiguracji właśnie tak:

```ts
const config = ({ env }: Core.Config.Shared.ConfigParams): Core.Config.Middlewares => [
  'strapi::logger',
  { name: 'global::request-trace', config: { slowMs: env.int('TRACE_SLOW_MS', 200) } },
  'strapi::errors',
  // rest of the file unchanged
];
```

Własne pliki też są dozwolone. `config/editorial.ts` z polami `commentsPerHour: env.int('COMMENTS_PER_HOUR', 10)` i `moderationEnabled: env.bool('COMMENT_MODERATION', true)` jest dostępny w kodzie jako `strapi.config.get('editorial.commentsPerHour')`. Strapi odrzuca tylko kilka zastrzeżonych nazw plików (m.in. `environment`, `info`, `dirs`, `strapi`), ostrzegając w konsoli. Te same ścieżki z kropkami działają dla plików wbudowanych: `strapi.config.get('api.rest.maxLimit')` zwraca w Redakcji 100.

Konfigurację dla konkretnego środowiska kładziesz w `config/env/<NODE_ENV>/`. Przy `NODE_ENV=production` Strapi wczytuje najpierw `config/*`, potem `config/env/production/*` i scala je głęboko (lodash `merge`). Przydatna opcja na start: `autoOpen: false` w `config/admin.ts` wyłącza otwieranie przeglądarki przy każdym uruchomieniu `strapi develop`.

> **Pułapka:** głębokie scalanie łączy tablice element po elemencie, a nie zastępuje ich. Plik `config/env/production/middlewares.ts` z tablicą `['strapi::logger', 'strapi::errors']` nie skraca listy middleware do dwóch pozycji. W Redakcji `strapi.config.get('middlewares')` zwrócił wtedy 11 elementów, a na początku `['strapi::logger', 'strapi::errors', 'strapi::errors']` – wpis `global::request-trace` został nadpisany, a `strapi::errors` wystąpił dwa razy. Listę middleware dla produkcji podawaj w pełnej długości albo buduj ją w jednym pliku z warunkiem na `env('NODE_ENV')`.

## Obiekt strapi i UID-y

W każdym miejscu kodu serwera masz dostęp do obiektu `strapi` – przez parametr (`{ strapi }` w fabrykach, politykach, funkcjach cyklu życia) albo globalnie. To on łączy wszystkie rejestry. Najczęściej będziesz używać kilku getterów: `strapi.documents(uid)` do treści, `strapi.service(uid)` i `strapi.controller(uid)` do warstw API, `strapi.plugin(name).service(name)` do serwisów pluginów (seed Redakcji tworzy użytkowników przez `strapi.plugin('users-permissions').service('user')`), `strapi.config.get(path)` do konfiguracji i `strapi.log` do logów. `strapi.db.query(uid)` schodzi poziom niżej, do Query Engine – kiedy to ma sens, wyjaśnia rozdział 6.

Identyfikatory mają stałe prefiksy, które mówią, skąd element pochodzi: `api::article.article` (typ treści, kontroler i serwis z `src/api`), `api::article.is-owner` (polityka lub middleware w obrębie jednego API), `plugin::users-permissions.user` (element pluginu), `admin::user` (panel), `global::request-trace` (globalna polityka lub middleware z `src/`) i `strapi::cors` (wbudowane middleware). Literówka w UID-zie wychodzi dopiero przy starcie albo przy wywołaniu – sprawdzisz je narzędziami z następnej sekcji.

## CLI do introspekcji

Strapi pozwala zajrzeć do swoich rejestrów bez czytania kodu. `npx strapi routes:list` wypisuje wszystkie trasy – w Redakcji 244 wiersze, z czego tylko 18 to trasy czterech typów treści (`/api/articles`, `/api/categories` ...), a reszta należy do panelu i pluginów. `npx strapi content-types:list` pokazuje 22 typy treści, w tym `plugin::content-releases.release` i `plugin::review-workflows.workflow`, które istnieją w bazie, choć same funkcje wymagają płatnej licencji. `policies:list`, `controllers:list`, `services:list` i `hooks:list` działają analogicznie.

```text
$ npx strapi middlewares:list (fragment)   $ npx strapi policies:list
global::request-trace                      global::trace-policy
strapi::compression                        plugin::content-manager.hasPermissions
strapi::errors                             admin::isAuthenticatedAdmin
strapi::responseTime                       admin::hasPermissions
plugin::users-permissions.rateLimit        admin::isTelemetryEnabled
```

Lista middleware zawiera wszystko, co jest *zarejestrowane*, a nie to, co działa. `strapi::compression` i `strapi::responseTime` są dostępne, ale nie biorą udziału w żądaniach, dopóki nie dopiszesz ich do `config/middlewares.ts`. To samo dotyczy własnych plików z `src/middlewares/`.

Najmocniejszym narzędziem jest `npx strapi console`: kompiluje projekt, uruchamia serwer w tle (na porcie z `PORT`, więc nie obok `strapi develop` na tym samym porcie) i otwiera REPL Node.js z globalnym obiektem `strapi`. REPL obsługuje `await`, więc sprawdzisz zapytanie, zanim wpiszesz je do kodu:

```text
code > strapi.config.get('middlewares.1')
{ name: 'global::request-trace', config: { slowMs: 200 } }
code > strapi.contentType('api::article.article').options
{ draftAndPublish: true }
code > (await strapi.documents('api::article.article').findMany({ status: 'draft', fields: ['title'] })).length
[trace]   documents api::article.article findMany
4
```

## Gdzie umieścić logikę

Mapa warstw przekłada się na prostą zasadę: umieść logikę na najniższej warstwie, która widzi wszystkie potrzebne jej informacje, i na najwyższej, która obejmuje wszystkie drogi zmiany danych.

| Potrzeba w Redakcji | Miejsce | Rozdział |
|---|---|---|
| Nagłówek, czas żądania, CORS, logowanie każdego żądania | globalne middleware | 4 |
| Limit komentarzy na godzinę dla jednego endpointu | middleware trasy | 4 |
| Autor edytuje tylko swoje artykuły (tak/nie przed kontrolerem) | polityka | 4 |
| Nowy endpoint `POST /comments/:id/approve`, kształt odpowiedzi | kontroler + trasa | 5 |
| Logika biznesowa wielokrotnego użytku | serwis | 5 |
| Slug, `readingTime`, blokada usunięcia kategorii – także z panelu | middleware Document Service | 6 |
| Operacje masowe, agregaty bez warstwy dokumentów | Query Engine | 6 |
| Uprawnienia ról, dane startowe | `bootstrap` | 1, 7 |

Granica, o którą najczęściej się potkniesz, przebiega między trasami a Document Service. Wszystko powyżej Document Service dotyczy tylko żądań Content API; wszystko w Document Service dotyczy też panelu admina, skryptów i `bootstrap`.

## Podsumowanie

- Strapi to aplikacja Koa: globalne middleware działają jak cebula, kod po `await next()` widzi gotową odpowiedź.
- Projekt w TypeScripcie działa z `dist/`; pliki w `src/` są ładowane według konwencji katalogów i dostają UID-y z prefiksami `api::`, `plugin::`, `admin::`, `global::`, `strapi::`.
- Kolejność w obrębie trasy (Strapi 5.56): uwierzytelnienie, uprawnienia ról, polityki, middleware trasy, kontroler – polityki działają przed middleware trasy.
- Żądanie bez uprawnienia roli kończy się 403, zanim wykona się twoja polityka.
- Panel admina używa własnych tras; polityki i middleware tras Content API go nie dotyczą, middleware Document Service – tak.
- `register` nie ma dostępu do bazy, `bootstrap` ma; `destroy` wykonuje się przy każdym przeładowaniu w develop.
- `config/env/<env>/` scala się głęboko z `config/`, a tablice są łączone element po elemencie.
- `routes:list`, `middlewares:list`, `policies:list`, `content-types:list` i `console` pokazują, co naprawdę jest zarejestrowane.

## Co dalej

Rozdział 2 schodzi do modelu treści Redakcji: `schema.json` od środka, relacje, komponenty i różnicę między dokumentem a jego wersjami. Bramki z diagramu tej części – trasy, polityki i middleware – rozbierzemy szczegółowo w rozdziale 4, kontrolery i serwisy w rozdziale 5, a Document Service z jego middleware w rozdziale 6.

## Źródła

- https://docs.strapi.io/cms/backend-customization
- https://docs.strapi.io/cms/backend-customization/requests-responses
- https://docs.strapi.io/cms/backend-customization/routes
- https://docs.strapi.io/cms/backend-customization/middlewares
- https://docs.strapi.io/cms/backend-customization/policies
- https://docs.strapi.io/cms/api/content-api
- https://docs.strapi.io/cms/api/document-service/middlewares
- https://docs.strapi.io/cms/configurations
- https://docs.strapi.io/cms/configurations/functions
- https://docs.strapi.io/cms/configurations/environment
- https://docs.strapi.io/cms/configurations/guides/access-cast-environment-variables
- https://docs.strapi.io/cms/configurations/middlewares
- https://docs.strapi.io/cms/project-structure
- https://docs.strapi.io/cms/cli
