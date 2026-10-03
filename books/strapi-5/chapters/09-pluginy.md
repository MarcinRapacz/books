# Rozdział 9. Własny plugin

> **Cel rozdziału:** zbudować plugin „comment-moderation” ze stroną serwerową i ekranem w panelu admina, zrozumieć, jak Strapi ładuje plugin lokalny, i wiedzieć, kiedy plugin jest lepszy od kodu w `src/api`.
>
> **Kod:** `examples/09-pluginy/`. **Pakiety poza fundamentem:** `npx @strapi/sdk-plugin init` (SDK 6.1.1) i `npm install --legacy-peer-deps` w katalogu pluginu.

W rozdziale 5 zatwierdzanie komentarza stało się akcją `POST /api/comments/:id/approve`. Działa, ale redaktorka nie pracuje w curl-u, tylko w panelu admina. Chce jednego ekranu: lista komentarzy czekających na moderację, przy każdym „Approve” i „Reject”. Czytelnik ma też móc zgłosić opublikowany komentarz, a zgłoszony wraca do kolejki.

Drugi powód jest organizacyjny. Wydawnictwo planuje drugi magazyn na osobnej instancji Strapi i chce tam tej samej moderacji. Kopiowanie kontrolerów, tras i ekranu między repozytoriami kończy się dwiema wersjami, które rozjadą się po pierwszej poprawce. Plugin pakuje serwer i panel w jedną paczkę z własną konfiguracją i wersją.

Zbudujesz plugin `comment-moderation` od szkieletu z Plugin SDK do działającej kolejki, a potem rozszerzysz wbudowany plugin przez `src/extensions`, dodasz narzędzie do serwera MCP i przygotujesz paczkę do publikacji.

## Plugin czy kod w `src/api`

Plugin nie daje mocy, której nie ma kod aplikacji: trasy, kontrolery, serwisy i polityki działają jak w rozdziałach 4 i 5, z przedrostkiem `plugin::comment-moderation.` zamiast `api::`, a ekran w panelu dodasz też w `src/admin/app.tsx` (rozdział 10). Różnica leży w granicach: plugin ma własny `package.json`, build, konfigurację i uprawnienia, a projekt widzi go jako jedną zależność.

Logika jednego projektu zostaje więc w `src/api`. Plugin opłaca się, gdy kod ma żyć w kilku projektach, łączy serwer z ekranem w panelu albo ma mieć własny cykl wydań. Uproszczenie Redakcji: plugin pracuje na typie `api::comment.comment` z aplikacji; plugin dla obcych projektów dostarczyłby własny typ w `server/src/content-types`.

## Szkielet z Plugin SDK

Dokumentacja zaleca tworzenie pluginów przez Plugin SDK. Polecenie zadaje kilkanaście pytań (nazwa, opis, admin i serwer, TypeScript, ESLint) i generuje szkielet:

```text
$ npx @strapi/sdk-plugin init src/plugins/comment-moderation
src/plugins/comment-moderation/
  package.json   exports: ./strapi-server → dist/server, ./strapi-admin → dist/admin
  server/src/    index.ts, register.ts, bootstrap.ts, config/, routes/, controllers/,
                 services/, policies/, middlewares/, content-types/
  admin/src/     index.ts (menu, rejestracja), pages/, components/, translations/
```

Na koniec SDK podpowiada wpis do `config/plugins.ts`. Dodajesz go z konfiguracją pluginu:

```ts
// config/plugins.ts (fragment)
'comment-moderation': {
  enabled: true,
  // Strapi loads the built files from package.json "exports" (dist/), not the sources.
  resolve: './src/plugins/comment-moderation',
  config: { pageSize: 10 },
},
```

Przewodnik dokumentacji opisuje głównie plugin jako osobną paczkę: w jej katalogu działa `npm run watch:link`, który przebudowuje kod i publikuje go do lokalnego magazynu `yalc`, a projekt dołącza go przez `npx yalc add --link comment-moderation`, bez `resolve`. Dla pluginu w `src/plugins` kroki są według dokumentacji „takie same”, poza wpisem z `resolve`. Tę wersję wybiera Redakcja: plugin jest wersjonowany z aplikacją, a globalny `yalc` nie jest potrzebny.

Kluczowe jest pole `exports`. Loader w `@strapi/core` szuka wejścia serwera pod `./strapi-server`, czyli w `dist/server/index.js`, a build panelu importuje `./strapi-admin` z `dist/admin`. Strapi nie czyta `server/src` ani `admin/src`, więc plugin trzeba zbudować:

```text
server/src/*.ts ──┐                                  ┌→ strapi develop (serwer)
                  ├─ npm run build / npm run watch ──┤
admin/src/*.tsx ──┘    (strapi-plugin, w pluginie)   └→ strapi build (Vite panelu)
```

> **Pułapka:** plugin włączony w `config/plugins.ts`, ale niezbudowany, jest pomijany bez słowa – loader sprawdza, czy plik z `exports` istnieje, i jeśli nie, przechodzi dalej. Bez `dist/` polecenie `npx strapi routes:list` nie pokazało żadnej trasy pluginu, po `npm run build` – pięć. Do tego watcher `strapi develop` ignoruje `**/dist/**`, ale reaguje na zmiany w `server/src`. Restart po zapisie pliku źródłowego potrafi wyprzedzić `npm run watch`: w logu serwer wstał 0,4 s przed zapisem nowego `dist/server/index.js` i działał na starym kodzie. Po przebudowie zrestartuj Strapi ręcznie.

### Zależności pluginu w projekcie

Szkielet ma w `devDependencies` i `peerDependencies` `@strapi/strapi`, Reacta i Design System. Dokumentacja radzi usunąć `@strapi/strapi` z `devDependencies`, ale npm od wersji 7 i tak instaluje zależności typu peer: `npm install` w katalogu pluginu dodał 1627 pakietów (1,1 GB), w tym drugą kopię `@strapi/strapi` i `@strapi/utils`. To nie tylko strata miejsca. Middleware `strapi::errors` rozpoznaje błędy przez `instanceof errors.ApplicationError`, a klasa z kopii pluginu jest inną klasą niż ta z projektu. `NotFoundError` rzucony przez serwis pluginu dla `PUT /comment-moderation/comments/nope000/approve` wrócił jako `500 InternalServerError`, a `PolicyError` – też jako 500.

Dla pluginu lokalnego rozwiązaniem jest `@strapi/utils` w `peerDependencies` i instalacja bez peerów: `npm install --legacy-peer-deps`. Zostaje 412 pakietów (246 MB) – SDK, TypeScript i typy – a `@strapi/*` rozwiązują się z `node_modules` projektu. Ten sam błąd daje wtedy poprawne `404 NotFoundError`. Po stronie panelu duplikaty bolą mniej, bo konfiguracja Vite w Strapi 5.56 (październik 2026) deduplikuje Reacta, Design System i `@strapi/strapi`.

## Strona serwerowa

`server/src/index.ts` eksportuje obiekt z kluczami `register`, `bootstrap`, `destroy`, `config`, `controllers`, `routes`, `services`, `contentTypes`, `policies` i `middlewares`. Nazwa elementu staje się częścią UID-u: serwis `moderation` to `plugin::comment-moderation.moderation`. W pluginie sięgasz po niego przez `strapi.plugin('comment-moderation').service('moderation')`, z aplikacji także przez `strapi.service('plugin::comment-moderation.moderation')`.

### Konfiguracja z walidacją

Plugin ma dwie opcje: rozmiar strony kolejki i długość podglądu komentarza. Strapi łączy `default` z `config` z `config/plugins.ts` i przekazuje wynik do `validator`, który może zatrzymać start. Zod z `@strapi/utils` (rozdział 5) daje walidację i typ w jednym:

```ts
// server/src/config/index.ts (bez importu)
const configSchema = z.object({
  pageSize: z.number().int().min(1).max(100),
  previewLength: z.number().int().min(20),
});
export type PluginConfig = z.infer<typeof configSchema>;

export default {
  default: { pageSize: 20, previewLength: 200 } satisfies PluginConfig,
  validator(config: unknown) {
    configSchema.parse(config);
  },
};
```

`pageSize: 500` w `config/plugins.ts` kończy start błędem `Error regarding comment-moderation config: [... "code": "too_big", "maximum": 100, "path": ["pageSize"] ...]` – przy wdrożeniu, a nie przy pierwszym kliknięciu moderatora. Wartości czytasz w serwisie przy każdym wywołaniu, przez `strapi.plugin('comment-moderation').config('pageSize')`, a nie raz przy imporcie modułu.

### Serwis na Document Service

Serwis `moderation` pobiera kolejkę, zmienia status i zwraca zatwierdzone komentarze artykułu. Rdzeń kolejki:

```ts
// server/src/services/moderation.ts (fragment findPending)
const [rows, total] = await Promise.all([
  comments().findMany({
    filters,
    sort: 'createdAt:asc',
    fields: ['body', 'createdAt'],
    populate: { article: { fields: ['title'] }, author: { fields: ['username'] } },
    start: (page - 1) * pageSize,
    limit: pageSize,
  }),
  comments().count({ filters }),
]);
return {
  results: commentRows.parse(rows).map((row) => ({
    documentId: row.documentId,
    body: preview(row.body),
    createdAt: row.createdAt,
    article: row.article?.title ?? null,
    author: row.author?.username ?? null,
  })),
  pagination: { page, pageSize, total },
};
```

`comments()` to `strapi.documents('api::comment.comment')`, a `commentRows` – schemat Zod z polami, których plugin oczekuje od komentarza. Plugin kompiluje się osobno i nie widzi `types/generated` aplikacji, więc wynik `findMany` to dla niego `AnyDocument`, a `tsc` odrzucił pierwszą wersję z rzutowaniem na własny typ. Parsowanie na granicy zastępuje rzutowanie i sprawdza, czy aplikacja ma komentarz w oczekiwanym kształcie. Odpowiedź składa się z jawnie wybranych pól (z autora tylko `username`), więc nie potrzebuje sanityzacji z rozdziału 5.

### Trasy admina i Content API

Szkielet eksportuje nazwane routery – format, który dokumentacja zaleca, gdy plugin ma oba rodzaje tras:

```ts
// server/src/routes/admin/index.ts (fragment)
const canModerate = {
  name: 'admin::hasPermissions',
  config: { actions: ['plugin::comment-moderation.moderate'] },
};
const onlyPending = {
  name: 'plugin::comment-moderation.comment-in-status',
  config: { statuses: ['pending'] },
};
// one of the routes of the { type: 'admin' } router
{ method: 'PUT' as const, path: '/comments/:id/approve', handler: 'moderation.approve',
  config: { policies: ['admin::isAuthenticatedAdmin', canModerate, onlyPending] } },
```

Router `content-api` ma `GET /articles/:articleId/comments` i `POST /comments/:id/report`. `npx strapi routes:list` pokazuje, gdzie Strapi je zamontował:

```text
GET   /api/comment-moderation/articles/:articleId/comments
POST  /api/comment-moderation/comments/:id/report
GET   /comment-moderation/comments/pending
PUT   /comment-moderation/comments/:id/approve
PUT   /comment-moderation/comments/:id/reject
```

Tylko Content API stoi za `/api`. Trasy admina uwierzytelnia JWT administratora i sprawdzają polityki RBAC. Trasy Content API podlegają users-permissions z akcjami w rodzaju `plugin::comment-moderation.comments.findApproved` (plugin, kontroler, akcja). Redakcja nadaje je rolom w `bootstrap` aplikacji wzorcem z seeda (rozdział 7) – o otwarciu tras dla Public decyduje projekt, nie plugin.

### Polityka pluginu

Zatwierdzić i odrzucić można tylko komentarz z kolejki, a zgłosić – tylko zatwierdzony. To jedna reguła z różnym parametrem, więc jedna polityka z konfiguracją per trasa:

```ts
// server/src/policies/comment-in-status.ts (rdzeń)
const allowed = config.statuses ?? [];
const documentId = policyContext.params.id;
if (!documentId || allowed.length === 0) return false;
const status = await strapi.plugin('comment-moderation')
  .service<ModerationService>('moderation').getStatus(documentId);
// Unknown comment: the controller answers with its regular 404.
if (status === null || allowed.includes(status)) return true;
throw new errors.PolicyError('Comment is not in an allowed moderation status', {
  policy: 'comment-in-status', moderationStatus: status, allowed,
});
```

Polityka trafia do obiektu `policies` pod kluczem `comment-in-status` i ma pełną nazwę `plugin::comment-moderation.comment-in-status`, której dokumentacja każe używać także wewnątrz pluginu. Middleware pluginu deklarujesz tak samo, w obiekcie `middlewares`; mechanika jest ta z rozdziału 4.

> **Pułapka:** strony dokumentacji o trasach i politykach pluginów zapisują konfigurację polityki jako `{ name, options: { ... } }`. W Strapi 5.56 walidator tras przepuszcza `options`, ale rejestr polityk (`registries/policies.js`) przekazuje polityce tylko pole `config`. Z `options` polityka dostała pusty obiekt, odrzuciła każde zgłoszenie i klient zobaczył ogólne `403 "Policy Failed"`. Pisz `config`, jak w rozdziale 4 – także dla `admin::hasPermissions`.

### Uprawnienia RBAC w `bootstrap`

W panelu o dostępie decydują role administratorów (RBAC), a nie role users-permissions. Plugin rejestruje akcje w `bootstrap`, gdy serwis uprawnień admina jest gotowy:

```ts
// server/src/bootstrap.ts (fragment)
await strapi.admin.services.permission.actionProvider.registerMany([
  { section: 'plugins', displayName: 'Read the moderation queue', uid: 'read', pluginName: 'comment-moderation' },
  { section: 'plugins', displayName: 'Approve and reject comments', uid: 'moderate', pluginName: 'comment-moderation' },
]);
```

Akcje `plugin::comment-moderation.read` i `.moderate` pojawiają się w Settings → Roles → Plugins; podział pozwala dać stażyście podgląd kolejki bez prawa decyzji. Test z Ewą jako Super Admin i Olą z rolą Editor – to konta panelu, niezależne od kont aplikacji (dwa światy użytkowników opisuje rozdział 7):

```text
GET /comment-moderation/comments/pending  bez tokenu / JWT Anny (users-permissions) → 401
GET ...   JWT Ewy (admin)       → 200 {"results":[...3...],"pagination":{"page":1,"pageSize":10,"total":3}}
GET ...   Ola, Editor           → 403 PolicyError "Policy Failed";  po nadaniu Editorowi akcji read → 200
PUT /comment-moderation/comments/:id/approve   Ola (tylko read)               → 403 "Policy Failed"
PUT ...approve   Ewa, komentarz odrzucony → 403 {"policy":"comment-in-status","moderationStatus":"rejected","allowed":["pending"]}
PUT ...approve   Ewa, nieznany documentId → 404 NotFoundError "Comment not found"
POST /api/comment-moderation/comments/:id/report   bez tokenu → 403;  Piotr → 200 {"moderationStatus":"pending"}
```

`pageSize` równe 10 pochodzi z `config/plugins.ts` projektu. Token users-permissions na trasie admina daje 401, a nie 403, bo trasy panelu nie znają strategii JWT aplikacji.

> **Pułapka:** uprawnienia RBAC pluginu żyją w bazie tylko tak długo, jak plugin jest ładowany. Przy każdym starcie `bootstrap` panelu (`cleanPermissionsInDatabase`) usuwa z ról i tokenów administratora akcje, których nikt nie zarejestrował. Wystarczyło jedno `npx strapi routes:list` z niezbudowanym pluginem, żeby z tabeli `admin_permissions` zniknęły wszystkie cztery wpisy `plugin::comment-moderation.*`: akcja `read` roli Editor, uprawnienie tokenu MCP i obie akcje Super Admina. Super Admin odzyskuje je po przywróceniu pluginu, role i tokeny – nie. Wdrożenie z niezbudowanym albo chwilowo wyłączonym pluginem kasuje ręczną konfigurację uprawnień.

## Strona admina

Wejście panelu (`admin/src/index.ts`) w `register` wywołuje `app.addMenuLink()` z adresem `plugins/comment-moderation`, leniwie ładowanym komponentem `() => import('./pages/App')` i `permissions: PERMISSIONS.read`, więc rola bez akcji `read` nie zobaczy linku. `PERMISSIONS` to plik z tablicami `[{ action: 'plugin::comment-moderation.read', subject: null }]`, wspólny dla menu, strony i przycisków. Ukryty link to wygoda, a nie zabezpieczenie: `App` owija trasy w `<Page.Protect permissions={PERMISSIONS.read}>`, bo adres strony można wpisać ręcznie, a ostatnią linią obrony są polityki tras serwera. Strona kolejki rozmawia z serwerem przez `useFetchClient`, który dokleja token administratora, odświeża go przy 401 i anuluje żądania przy odmontowaniu. Ścieżki tras admina pluginu podajesz bez `/api`:

```tsx
// admin/src/pages/HomePage.tsx (fragment)
const { get, put } = useFetchClient();
const { toggleNotification } = useNotification();
const {
  isLoading: isLoadingPermissions,
  allowedActions: { canModerate },
} = useRBAC({ moderate: PERMISSIONS.moderate });
// load() calls get('/comment-moderation/comments/pending') and stores the result in state

const decide = async (documentId: string, decision: Decision) => {
  try {
    await put(`/comment-moderation/comments/${documentId}/${decision}`);
    toggleNotification({ type: 'success', message: decision === 'approve' ? 'Comment approved' : 'Comment rejected' });
  } catch {
    toggleNotification({ type: 'danger', message: 'The comment could not be updated' });
  }
  await load();
};
```

Reszta to Design System: `Layouts.Header` z tytułem i liczbą komentarzy w kolejce, `Table` z kolumnami Comment, Article, Author, Created i Decision, a w ostatniej przyciski „Approve” i „Reject” z `disabled={!canModerate}` – Editor z samą akcją `read` widzi kolejkę, ale nie podejmie decyzji. Pusta kolejka pokazuje `EmptyStateLayout`, a po decyzji pojawia się powiadomienie i lista pobiera się od nowa.

Ten opis pochodzi z kodu i buildu, nie z klikania. Przeszły `tsc` pluginu, jego build i `npm run build` projektu (panel w 25–30 s), a bundle panelu zawiera chunk pluginu z adresem `/comment-moderation/comments/pending`. Usuń ze szkieletu `admin/custom.d.ts`: deklaruje `@strapi/design-system` jako moduł bez typów, a bez niego `tsc` sprawdza prawdziwe propsy komponentów.

## Rozszerzanie wbudowanego pluginu: `src/extensions`

Czasem potrzebujesz innego zachowania istniejącego pluginu. Redakcja pozwala zalogowanym wgrywać pliki przez `POST /api/upload`, ale nie chce stu plików w jednym żądaniu. Trasa należy do pluginu Upload, więc nie podepniesz do niej middleware w `src/api`. Plik `src/extensions/<plugin>/strapi-server.ts` dostaje obiekt pluginu po załadowaniu i zwraca zmieniony:

```ts
// src/extensions/upload/strapi-server.ts (rdzeń; limitFiles to middleware trasy z ctx.badRequest)
export default (plugin: UploadPlugin) => {
  const uploadRoute = plugin.routes['content-api'].routes.find(
    (route) => route.method === 'POST' && route.path === '/'
  );
  // Internal structure of a built-in plugin: fail loudly after an upgrade instead of silently.
  if (!uploadRoute) {
    throw new Error('upload extension: content-api route POST / not found');
  }
  uploadRoute.config = {
    ...uploadRoute.config,
    middlewares: [...(uploadRoute.config?.middlewares ?? []), limitFiles],
  };
  return plugin;
};
```

Anna wysyła cztery pliki i dostaje `400 {"name":"BadRequestError","message":"Upload at most 3 files at once","details":{"count":4}}`, pojedynczy plik przechodzi z 201. W Upload 5.56 `routes['content-api']` jest fabryką z getterem `routes`, dzięki któremu zapis z dokumentacji (`routes['content-api'].routes.push(...)`) i powyższe `find` działają. Rozszerzenie opiera się jednak na wewnętrznej strukturze pluginu, której przewodniki migracji nie obejmują – dlatego kod rzuca błąd, gdy trasy nie znajdzie. Rozszerzenia users-permissions opisuje rozdział 7, a panel wbudowanych pluginów zmienisz tylko łatką `patch-package`.

## Narzędzie MCP z pluginu

Strapi 5.56 ma wbudowany serwer MCP (Model Context Protocol), włączany w `config/server.ts` opcją `mcp: { enabled: true }` i uwierzytelniany tokenami administratora. To funkcja darmowa: usługa `strapi.ai.mcp` siedzi w `@strapi/core` i nie sprawdza licencji; konfigurację i podłączenie klienta opisuje rozdział 12. Plugin może dołożyć narzędzie, ale tylko w `register()`, póki serwer MCP jest bezczynny:

```ts
// server/src/register.ts (fragment)
strapi.ai.mcp.registerTool({
  name: 'list_pending_comments',
  title: 'List pending comments',
  description: 'Returns the oldest comments waiting for moderation in the Redakcja magazine.',
  auth: { policies: [{ action: 'plugin::comment-moderation.read' }] },
  resolveInputSchema: () => z.object({ page: z.number().int().min(1).default(1) }),
  resolveOutputSchema: () => z.object({ total: z.number(), comments: z.array(commentSchema) }),
  createHandler: (strapi) => async ({ args }) => {
    const { results, pagination } = await strapi
      .plugin('comment-moderation').service<ModerationService>('moderation').findPending(args.page);
    const comments = results.map(({ documentId, body, article }) => ({ documentId, body, article }));
    return {
      content: [{ type: 'text', text: JSON.stringify(comments) }],
      structuredContent: { total: pagination.total, comments },
    };
  },
});
```

Narzędzie używa tej samej akcji RBAC co ekran w panelu. Token z akcją `read` widzi je w `tools/list` obok narzędzia `log` (dostępnego tylko w trybie develop), a `tools/call` zwraca `{"total":3,"comments":[{"documentId":"hb8mrlw5of8ysd93lyrst7y4","body":"Great article!",...}]}`. Token bez tej akcji widzi tylko `log`, a wywołanie kończy się błędem JSON-RPC `-32602 "Tool list_pending_comments disabled"`.

## Publikacja na npm

Gdy drugi magazyn ma zainstalować plugin z rejestru, `npm run build && npm run verify` buduje `dist/` i sprawdza, czy `exports` wskazuje na istniejące pliki. `files: ["dist"]` ze szkieletu trzyma źródła poza paczką, biblioteki aplikacji (`@strapi/*`, React, Design System) zostają w `peerDependencies`, a wersja dla Strapi 5 powinna mieć inny numer główny niż wersja dla Strapi 4. `verify` przeszedł bez uwag; `npm publish` nie był uruchamiany. Po instalacji z npm wpis w `config/plugins.ts` traci `resolve`, a dalszą pracę prowadzisz z `watch:link`.

## Podsumowanie

- Plugin to te same trasy, kontrolery, serwisy i polityki co w `src/api`, z przedrostkiem `plugin::<nazwa>.` i własnym `package.json`, buildem, konfiguracją oraz uprawnieniami. Opłaca się przy współdzieleniu między projektami i przy połączeniu serwera z ekranem w panelu.
- `npx @strapi/sdk-plugin init src/plugins/<nazwa>` tworzy szkielet. Plugin lokalny włączasz przez `resolve` w `config/plugins.ts`, paczkę rozwijasz przez `watch:link` i `yalc`.
- Strapi ładuje plugin z `dist/` według `exports`. Niezbudowany plugin jest pomijany po cichu, a watcher `develop` ignoruje `dist/`.
- W `src/plugins` instaluj zależności pluginu z `--legacy-peer-deps` i trzymaj `@strapi/*` w `peerDependencies`; druga kopia `@strapi/utils` zamienia 404 i 403 w 500.
- Konfiguracja to `default` i `validator`; walidacja Zodem zatrzymuje start z czytelnym błędem.
- Router `admin` trafia pod `/<plugin>` i podlega RBAC, router `content-api` – pod `/api/<plugin>` i rolom users-permissions. Konfiguracja polityki w trasie to `config`, nie `options`.
- Akcje RBAC rejestrujesz w `bootstrap` pluginu i chronisz nimi menu, stronę (`Page.Protect`) i przyciski (`useRBAC`). Start aplikacji bez pluginu usuwa te akcje z ról i tokenów.
- `src/extensions/<plugin>/strapi-server.ts` zmienia wbudowany plugin kosztem zależności od jego wnętrza. Narzędzie MCP rejestrujesz w `register()` przez `strapi.ai.mcp.registerTool`, z akcją RBAC jako bramką.

## Co dalej

Plugin dodał do panelu własną stronę, ale panel da się zmieniać także bez pluginu i w miejscach, które już istnieją. W rozdziale 10 zajmiesz się `src/admin/app.tsx`, strefami wstrzykiwania w widoku edycji artykułu, API Content Managera i custom fields – polami z własnym komponentem React, rejestrowanymi po stronie serwera i panelu podobnie jak akcje i link w menu tego pluginu.

## Źródła

- https://docs.strapi.io/cms/plugins-development/developing-plugins
- https://docs.strapi.io/cms/plugins-development/create-a-plugin
- https://docs.strapi.io/cms/plugins-development/plugin-sdk
- https://docs.strapi.io/cms/plugins-development/plugin-structure
- https://docs.strapi.io/cms/plugins-development/server-api
- https://docs.strapi.io/cms/plugins-development/server-configuration
- https://docs.strapi.io/cms/plugins-development/server-routes
- https://docs.strapi.io/cms/plugins-development/server-policies-middlewares
- https://docs.strapi.io/cms/plugins-development/server-controllers-services
- https://docs.strapi.io/cms/plugins-development/server-getters-usage
- https://docs.strapi.io/cms/plugins-development/server-lifecycle
- https://docs.strapi.io/cms/plugins-development/admin-panel-api
- https://docs.strapi.io/cms/plugins-development/admin-navigation-settings
- https://docs.strapi.io/cms/plugins-development/admin-fetch-client
- https://docs.strapi.io/cms/plugins-development/guides/admin-permissions-for-plugins
- https://docs.strapi.io/cms/plugins-development/plugins-extension
- https://docs.strapi.io/cms/plugins-development/extend-mcp-server
- https://docs.strapi.io/cms/features/strapi-mcp-server
- https://docs.strapi.io/cms/configurations/plugins
