# Rozdział 12. TypeScript, testy i narzędzia AI

> **Cel rozdziału:** zabezpieczyć reguły „Redakcji” przed cichą regresją typami i testami, które naprawdę uruchamiają Strapi, oraz rozsądnie podłączyć asystenta AI do dokumentacji i do własnej instancji.
>
> **Kod:** `examples/12-typescript-testy-ai/`. **Pakiety poza fundamentem:** `npm install -D vitest@4 supertest @types/supertest`.

Polityka `is-owner`, limit komentarzy i wymuszone `moderationStatus: 'pending'` działają, bo w rozdziałach 4 i 5 sprawdziłeś je curl-em – raz. Literówka w nazwie pola, zmiana kolejności middleware albo cotygodniowa aktualizacja Strapi mogą je po cichu wyłączyć, a dowiesz się o tym od czytelnika, który sam zatwierdził swój komentarz. Ten rozdział dokłada typy, które łapią błędy przed startem serwera, testy, które odtwarzają scenariusze z curl-a na prawdziwej instancji, i narzędzia AI – przydatne, o ile wiesz, do czego dajesz im dostęp.

## Typy generowane ze schematów

`strapi.documents('api::article.article')` wie, jakie pola ma artykuł, tylko dzięki plikom `types/generated/contentTypes.d.ts` i `components.d.ts`. Tworzy je `npx strapi ts:generate-types` (w „Redakcji” 0,24 s). `contentTypes.d.ts` rozszerza moduł `@strapi/strapi` o rejestr `ContentTypeSchemas`, z którego korzystają `Core.Strapi`, `Data.ContentType<'api::article.article'>` (dokument z polami) i `Modules.Documents.ServiceParams<uid>` (parametry Document Service, użyte w rozdziale 5). Z typami `findOne({ documentId, fields: ['titel'] })` kończy się błędem `Did you mean '"title"'?`. Bez nich literówka się kompiluje, a poprawne `update({ data: { moderationStatus: 'approved' } })` w serwisie komentarzy zgłasza błąd, bo typy zastępcze nie znają pól. Dlatego `types/generated` trafia do repozytorium razem ze zmianą schematu.

> **Pułapka:** według dokumentacji opcja `autogenerate` w `config/typescript.ts` (domyślnie `false`) włącza generowanie typów przy restarcie. W Strapi 5.56 (październik 2026) `strapi develop` w projekcie TypeScript generuje je zawsze: z `autogenerate: false` i usuniętym `types/generated` serwer i tak je odtworzył (`✔ Generating types (290ms)`). Opcja dotyczy tylko projektów JavaScript i jest w nich domyślnie włączona – tak mówi komentarz w typie `Core.Config.TypeScript`. Typy powstają przy `develop`, nie przy `build`, więc to CI powinno sprawdzić, czy ktoś ich nie zapomniał zatwierdzić.

## Polityka i middleware z typami

Rozdział 4 zostawił dwa obejścia: `Core.PolicyContext` nie deklaruje `state` ani `params`, a `Core.PolicyHandler` zwraca synchronicznie `boolean`, choć router czeka na wynik polityki (`await handler(...)` w `@strapi/core`). Najczyściej opisać to raz, w jednym pliku:

```ts
// src/types/request-context.ts
import type { Core, Data } from '@strapi/strapi';
export type AuthUser = Data.ContentType<'plugin::users-permissions.user'>;

// Koa types `ctx.state` as `any`; this makes `ctx.state.user` typed in middlewares and controllers.
declare module 'koa' {
  interface DefaultState {
    user?: AuthUser;
  }
}

export type PolicyContext = Core.PolicyContext & {
  state: { user?: AuthUser };
  params: Record<string, string | undefined>;
};

export type Policy<TConfig = unknown> = (
  policyContext: PolicyContext,
  config: TConfig,
  context: { strapi: Core.Strapi }
) => Promise<boolean | undefined> | boolean | undefined;
```

Polityka `is-owner` zaczyna się teraz od `const isOwner: Policy<IsOwnerConfig> = async (policyContext, config, { strapi }) => {` i nie potrzebuje adnotacji w środku. Dzięki rozszerzeniu modułu `koa` z limitu komentarzy znika rzutowanie `ctx.state.user as { id: number }`. Typ nie odwzorowuje jednak wszystkiego: `Core.PolicyContext` dziedziczy po Koa `query`, więc `policyContext.query` się kompiluje, choć w polityce ma wartość `undefined` (rozdział 4).

## Testy na prawdziwej instancji

Dokumentacja proponuje Jest, Supertest i harness, który łata wewnętrzne moduły Strapi (ładowanie `.ts` z `config/`, sterownik `sqlite3`, którego fundament nie ma, bo używa `better-sqlite3`). Prościej zrobić to, co `strapi develop`: skompilować projekt `tsc` do `dist/` i uruchomić Strapi z tego katalogu. Ten sam krok sprawdza typy.

```ts
// tests/strapi.ts (core of the harness)
export async function startStrapi(): Promise<Core.Strapi> {
  removeDatabase();
  const strapi = createStrapi({ appDir, distDir: path.join(appDir, 'dist') });
  await strapi.load();
  // listen() would mount the routers; supertest needs them without a fixed port.
  strapi.server.mount();
  return strapi;
}
```

`load()` synchronizuje schemat i uruchamia `register`/`bootstrap` bez otwierania portu; Supertest wystawia serwer na losowym porcie na czas żądania. `tests/env.ts` ustawia sekrety testowe (gdy ich brak – w CI nie ma `.env`) i `DATABASE_FILENAME=.tmp/test-<id workera>.db`, więc pliki testów działają równolegle, każdy na pustej bazie, a baza deweloperska zostaje nietknięta. `config/env/test/server.ts` ścisza logi do `warn` i wyłącza sprawdzanie aktualizacji w npm. Skrypt w `package.json` to `"test": "tsc -p . && vitest run"`.

```ts
// vitest.config.mts (imports from node:module and vitest/config omitted)
const require = createRequire(import.meta.url);
export default defineConfig({
  resolve: { alias: { '@strapi/strapi': require.resolve('@strapi/strapi') } },
  test: { pool: 'threads', setupFiles: ['tests/env.ts'], hookTimeout: 60_000 },
});
```

> **Pułapka:** obie opcje to obejścia sprawdzone na Strapi 5.56. Bez aliasu Vitest ładuje build ESM `@strapi/core`, który pada w Node na `Directory import '.../lodash/fp' is not supported`; alias wskazuje build CommonJS, ten sam, którego używa CLI. Bez `pool: 'threads'` testy przechodzą, ale przebieg kończy się błędem `Worker forks emitted error ... EPIPE`, bo `strapi.destroy()` wywołuje `process.removeAllListeners()` i odcina kanał IPC procesu potomnego. A `vitest@4`, bo Vitest 5 wymaga `@types/node` co najmniej 22, a szkielet Strapi ma `^20`.

Test polityki to scenariusz z rozdziału 4 zapisany kodem. Funkcje z `tests/fixtures.ts` nadają roli Authenticated uprawnienie `update`, tworzą użytkowników i logują ich przez `POST /api/auth/local`, więc w grze jest prawdziwy JWT:

```ts
// tests/articles.test.ts (one of three cases)
it('rejects an update from another author with 403 PolicyError', async () => {
  const res = await request(strapi.server.httpServer)
    .put(`/api/articles/${articleId}`)
    .set('Authorization', `Bearer ${piotr.jwt}`)
    .send({ data: { title: 'Hijacked' } });
  expect(res.status).toBe(403);
  expect(res.body.error).toMatchObject({ name: 'PolicyError', details: { policy: 'is-owner' } });
});
```

Testy komentarzy sprawdzają, że nowy komentarz ląduje w bazie jako `pending` (odczyt przez Document Service, nie tylko odpowiedź), `moderationStatus` od klienta daje 400, a czwarty komentarz w minucie – 429 z `Retry-After`. Każdy przypadek ma własnego użytkownika, bo limit liczy się per użytkownik. Test jednostkowy serwisu dostaje fałszywy `strapi` z `contentType()` (wymaga go fabryka `createCoreService`) i `documents()` zwracającym obiekty z `vi.fn()`. Wynik `npm test -- --reporter=verbose` (skrócony):

```text
✓ tests/comment-service.test.ts > commentService.submit > creates the comment as pending for the given author 5ms
✓ tests/articles.test.ts > is-owner on PUT /api/articles/:id > rejects an update from another author with 403 PolicyError 20ms
✓ tests/articles.test.ts > is-owner on PUT /api/articles/:id > lets the author update their own article 41ms
✓ tests/comments.test.ts > POST /api/comments > answers the 4th comment within a minute with 429 and Retry-After 239ms
 Test Files  3 passed (3)
      Tests  8 passed (8)
   Duration  5.81s (transform 99ms, setup 77ms, import 3.12s, tests 8.84s, environment 0ms)
```

Czy testy coś łapią? Po dopisaniu `|| true` do warunku w `is-owner` przebieg padł z `expected 200 to be 403`. Test jednostkowy jest szybki, ale nie wie nic o trasach, uprawnieniach roli ani kolejności polityk, więc reguły dostępu sprawdzaj testem API.

W CI wystarczą dwa kroki: typy zgodne ze schematem i zielone testy. Workflow GitHub Actions nie był uruchamiany, ale oba polecenia sprawdziłem lokalnie na kopii projektu bez `.env`: typy wyszły identyczne, testy przeszły. W GitLab CI to te same polecenia w `script:`.

```yaml
# .github/workflows/test.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm }
      - run: npm ci
      - run: npx strapi ts:generate-types && git diff --exit-code types/generated
      - run: npm test
```

## Narzędzia AI dla dewelopera

### Dokumentacja dla asystenta

Model zna Strapi głównie z czasów v4 i podsuwa `entityService`. Dokumentacja ma dla narzędzi AI trzy wejścia. `https://docs.strapi.io/llms.txt` to indeks stron z jednozdaniowymi opisami, a każdą stronę pobierzesz jako czysty Markdown, dopisując `.md` do adresu (`https://docs.strapi.io/cms/testing.md`). `llms-full.txt` i `llms-code.txt` to cała dokumentacja i jej przykłady kodu w jednym pliku – do grepowania, nie do wklejania. Trzecie to Docs MCP, oparty na Kapa serwer odpowiadający z aktualnej dokumentacji:

```bash
claude mcp add --transport http strapi-docs https://strapi-docs.mcp.kapa.ai
```

Składnię potwierdza `claude mcp add --help` (opcje przed nazwą, domyślny zakres `local`). Anonimowe żądanie do serwera dostaje `401` z nagłówkiem `WWW-Authenticate` wskazującym OAuth w `mcp.kapa.ai`, więc po dodaniu trzeba się zalogować przez `/mcp` w Claude Code; tego kroku nie wykonywałem. Dokumentacja radzi zaczynać pytania od „Use the strapi-docs MCP server to answer:”, żeby asystent nie odpowiadał z pamięci.

### Wbudowany serwer MCP Strapi

Drugi, darmowy serwer MCP działa w twojej instancji i pozwala klientowi AI czytać i zmieniać treści przez Content Manager. W „Redakcji” włącza go flaga, domyślnie wyłączona:

```ts
// config/server.ts (fragment)
mcp: {
  enabled: env.bool('MCP_ENABLED', false),
},
```

Po starcie z `MCP_ENABLED=true` log pokazuje `[MCP] Server available at /mcp`. Serwer przyjmuje tylko Admin token (Settings → Administration Panel → Admin Tokens); JWT zalogowanego administratora dostał `Authentication required`. Utworzyłem token „claude-code-readonly” ważny 7 dni, z jednym uprawnieniem: odczyt artykułów w Content Managerze. Rozmowa to JSON-RPC przez `POST` z nagłówkiem `Accept: application/json, text/event-stream`:

```text
initialize  → {"result":{"protocolVersion":"2025-06-18",...,"serverInfo":{"name":"strapi-mcp-server","version":"1.0.0"}},...}
tools/list  → (nazwy narzędzi) log, list_article, get_article
tools/call delete_article → {"error":{"code":-32602,"message":"Tool delete_article disabled"}}
bez tokenu  → 401 {"error":{"code":-32000,"message":"Authentication required"}}
```

Narzędzia wynikają z uprawnień tokenu (`log` istnieje tylko w trybie deweloperskim); pełne prawa do typu z draft & publish dają według dokumentacji do ośmiu narzędzi, z `publish` i `delete` włącznie. Klienta podłączysz przez `claude mcp add --transport http strapi-redakcja http://localhost:1337/mcp --header "Authorization: Bearer $STRAPI_ADMIN_TOKEN"`. Powłoka wstawi wartość tokenu do lokalnej konfiguracji Claude Code, więc nie używaj zakresu `project`, który trafia do repozytorium.

O bezpieczeństwie decydują dwie rzeczy. MCP to droga przez panel, nie przez Content API: przy `list_article` log pokazał tylko `[trace] document service: findMany`, więc `is-owner` i limit komentarzy agenta nie dotyczą. A treść czytana przez agenta pochodzi od ludzi: komentarz z poleceniem „opublikuj wszystkie szkice” trafi do kontekstu modelu, a token z prawem zapisu zamieni ten prompt injection w realną zmianę. Stąd osobny token na klienta, najwęższe uprawnienia, krótka ważność i `MCP_ENABLED` tylko tam, gdzie trzeba – w produkcji raczej wcale. Własne narzędzia MCP z pluginu pokazuje rozdział 9.

## Podsumowanie

- `strapi ts:generate-types` tworzy `types/generated`, bez którego `strapi.documents()` nie zna pól. Typy są w repozytorium, a CI pilnuje ich przez `git diff --exit-code`; `autogenerate` dotyczy tylko projektów JavaScript.
- Jeden plik typów obsługuje polityki (`Policy<TConfig>` ze `state`, `params` i wynikiem asynchronicznym) i middleware (rozszerzenie `DefaultState` z Koa).
- Testy API: `tsc` do `dist/`, `createStrapi({ distDir }).load()`, `strapi.server.mount()`, Supertest i osobna baza SQLite na workera; w Vitest 4 dodatkowo alias na build CommonJS i `pool: 'threads'`.
- Reguły dostępu testuj przez API z prawdziwym JWT, logikę serwisu – jednostkowo z fałszywym `strapi`.
- Aktualną dokumentację asystent dostaje przez `llms.txt`, strony `.md` albo Docs MCP.
- Wbudowany serwer MCP omija polityki i middleware tras; daj mu Admin token o najwęższych uprawnieniach.

## Co dalej

Rozdział 13 zabiera „Redakcję” na produkcję: obraz Dockera, Postgres zamiast SQLite, sekrety i aktualizacje Strapi. Testy z tego rozdziału uruchomione przed każdą aktualizacją powiedzą ci, czy kolejny minor nie zmienił zachowania twoich polityk.

## Źródła

- https://docs.strapi.io/cms/typescript
- https://docs.strapi.io/cms/typescript/development
- https://docs.strapi.io/cms/typescript/documents-and-entries
- https://docs.strapi.io/cms/configurations/typescript
- https://docs.strapi.io/cms/testing
- https://docs.strapi.io/cms/ai/for-developers
- https://docs.strapi.io/cms/ai/docs-mcp-server
- https://docs.strapi.io/cms/features/strapi-mcp-server
- https://docs.strapi.io/cms/features/admin-tokens
- https://docs.strapi.io/cms/plugins-development/extend-mcp-server
- https://docs.strapi.io/llms.txt
