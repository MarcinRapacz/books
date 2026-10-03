# Rozdział 3. Content API od strony klienta: REST, GraphQL, klient

> **Cel rozdziału:** nauczyć się pobierać i zapisywać treści Redakcji przez REST i GraphQL tak, żeby frontend dostawał dokładnie to, czego potrzebuje, a anonimowy klient nic ponad to.
>
> **Kod:** `examples/03-content-api/`. **Pakiety poza fundamentem:** `npm install @strapi/plugin-graphql` (backend); w kliencie `npm install @strapi/client qs` i `npm install -D @types/qs`.

Frontend Redakcji potrzebuje listy artykułów z okładką i kategorią, strony artykułu z całą strefą dynamiczną (dynamic zone) i danymi SEO oraz podglądu szkiców dla autorów. Pierwsze zapytanie `GET /api/articles` zwraca same tytuły i daty. Drugie, z `populate=*`, zwraca sporo, ale bez autora i obrazka SEO. Trzecie ujawnia coś gorszego: rola Public z samym uprawnieniem `find` czyta szkice, jeśli poprosi o nie w URL-u.

Wszystkie odpowiedzi w tym rozdziale pochodzą z fundamentu po `npm run seed` i skrypcie `scripts/attach-media.js` z `examples/`, który dokłada obrazek do artykułu „Policies in Strapi 5” jako okładkę, `seo.shareImage` i blok `shared.media`. Znaczniki czasu i część pól są skrócone, a długie URL-e złamane dla czytelności. Drogę żądania przez serwer opisuje rozdział 1, a obróbkę parametrów w kontrolerze rozdział 5.

## Kształt odpowiedzi i `documentId`

Odpowiedź Strapi 5 jest płaska: pola leżą bezpośrednio w `data`, a nie w `data.attributes` jak w v4.

```text
$ curl 'localhost:1303/api/articles?pagination[pageSize]=1'
{"data":[{"id":4,"documentId":"z18pcsia11q8v0uc2dr9h0lt","title":"Document Service middlewares", ...}],
 "meta":{"pagination":{"page":1,"pageSize":1,"pageCount":3,"total":3}}}
```

W URL-ach, relacjach i kodzie frontendu używasz wyłącznie `documentId`. Numeryczne `id` identyfikuje wiersz w bazie, a dokument z draft & publish ma ich kilka: „Policies in Strapi 5” ma `id` 8 w wersji opublikowanej i 1 w szkicu, przy tym samym `documentId` `e5uauilz20m1fx7eaoywnsk3`. Link albo klucz cache zbudowany na `id` rozjedzie się po pierwszej publikacji.

## `populate`: nic nie przychodzi samo

REST domyślnie nie dołącza relacji, mediów, komponentów ani stref dynamicznych, bo każde dołączenie to dodatkowe zapytanie do bazy. `populate=*` dołącza wszystko, ale tylko jeden poziom w głąb:

```text
$ curl 'localhost:1303/api/articles/e5uauilz20m1fx7eaoywnsk3?populate=*'
{"data":{"id":8, ..., "cover":{"id":1,"name":"policies-cover.png","width":64,"hash":"...","mime":"image/png", ...},
  "seo":{"id":10,"metaTitle":"Policies in Strapi 5","metaDescription":"Read about Policies in Strapi 5"},
  "category":{...}, "comments":[{...}], "content":[...]}, "meta":{}}
```

`seo` nie ma `shareImage`, bo obrazek w komponencie to drugi poziom. Nie ma też `author`: rola Public nie ma uprawnienia `find` na użytkownikach, więc `sanitizeQuery` po cichu usuwa relację z zapytania (rozdział 5). Zamiast błędu dostajesz odpowiedź bez pola, co łatwo przeoczyć. `populate=*` nadaje się do eksploracji w terminalu, nie do kodu: pobiera całe obiekty mediów i wszystkie komentarze, choć karta artykułu potrzebuje dwóch pól.

W kodzie wymieniasz dokładnie to, czego potrzebujesz. Strefa dynamiczna jest polimorficzna, więc Strapi 5 wymaga składni `on` z osobną konfiguracją dla każdego komponentu:

```text
$ curl -g 'localhost:1303/api/articles/e5uauilz20m1fx7eaoywnsk3?fields[0]=title
    &populate[cover][fields][0]=url&populate[seo][populate][shareImage][fields][0]=url
    &populate[content][on][shared.rich-text]=true
    &populate[content][on][shared.quote][fields][0]=body
    &populate[content][on][shared.media][populate][file][fields][0]=url'
{"data":{"id":8,"documentId":"e5uauilz20m1fx7eaoywnsk3","title":"Policies in Strapi 5",
  "cover":{"id":1,"documentId":"jd0w1iw84o83s7dx2uc7o5zd","url":"/uploads/policies_cover_791620a0b1.png"},
  "seo":{"id":10,"metaTitle":"...","metaDescription":"...","shareImage":{"id":1,"url":"/uploads/policies_cover_791620a0b1.png"}},
  "content":[{"id":9,"body":[{"type":"paragraph", ...}],"__component":"shared.rich-text"},
             {"id":9,"body":"Measure before you optimise.","__component":"shared.quote"},
             {"id":2,"file":{"id":1,"url":"/uploads/policies_cover_791620a0b1.png"},"__component":"shared.media"}]},
 "meta":{}}
```

Komponent `seo` to zwykły obiekt, więc jego obrazek dołączasz zagnieżdżonym `populate`. W strefie dynamicznej każdy klucz pod `on` to UID komponentu z własnymi `fields` i `populate`: cytat zwraca samo `body`, blok mediów dołącza plik, a `true` oznacza wszystkie pola skalarne. Literówka w UID daje 400 `Invalid key shared.nope at content.on.shared.nope`, nie pusty wynik.

> **Pułapka:** `populate[0]=content` zwraca bloki mediów jako `{"id":2,"__component":"shared.media"}`, bez pliku. Z kolei `on` działa jak lista dozwolonych komponentów: przy `populate[content][on][shared.quote]=true` akapity `shared.rich-text` znikają z odpowiedzi. Gdy redakcja doda do strefy nowy komponent, frontend nie zobaczy go, dopóki nie dopiszesz go do `on`.

Głębokie `populate` nie ma limitu poziomów, a jego koszt rośnie z każdym poziomem i każdą relacją „do wielu”. Pomiary i przeniesienie domyślnego `populate` na serwer opisuje rozdział 13.

## `fields`, `filters` i `sort`

`fields` ogranicza pola skalarne (`documentId` i `id` przychodzą zawsze). `filters` przyjmuje operatory z prefiksem `$` (`$eq`, `$in`, `$containsi`, `$lt`, `$null` i inne). Filtr po relacji to zagnieżdżenie jej nazwy:

```text
$ curl -g 'localhost:1303/api/articles?fields[0]=title&filters[category][slug][$eq]=backend'
{"data":[{"title":"Document Service middlewares", ...},{"title":"Policies in Strapi 5", ...}], ...}
$ curl -g 'localhost:1303/api/articles?fields[0]=title&sort=title:asc
    &filters[$or][0][title][$containsi]=policies&filters[$or][1][category][name][$eq]=Frontend'
{"data":[{"title":"Fetching Strapi from Next.js", ...},{"title":"Policies in Strapi 5", ...}], ...}
```

Klucze na jednym poziomie łączą się przez AND, a `$or` przyjmuje tablicę warunków, z których każdy może sięgać przez relację. Pierwszy artykuł pasuje przez kategorię, drugi przez tytuł. Filtry po relacji podlegają tym samym uprawnieniom co `populate`, tylko bez cichego pomijania: `filters[author][username][$eq]=anna` od anonimowego klienta daje 400 `Invalid key author`. `sort` przyjmuje `pole:asc` albo tablicę. Bez niego kolejność zależy od bazy i stronicowana lista może pokazać ten sam artykuł na dwóch stronach.

## Paginacja i limity z `config/api.ts`

Paginacja działa po stronach (`pagination[page]`, `pagination[pageSize]`) albo po przesunięciu (`pagination[start]`, `pagination[limit]`). Mieszanie trybów daje 400 `PaginationError: Cannot use both page & offset pagination in the same query`. Fundament ustawia w `config/api.ts` `rest: { defaultLimit: 25, maxLimit: 100, withCount: true, strictParams: true }`.

`defaultLimit` obowiązuje, gdy klient nie poda paginacji. `maxLimit` przycina większe żądania bez błędu: `pagination[pageSize]=500` zwraca w `meta` `"pageSize":100`, więc frontend, który zakłada, że dostał wszystko, po cichu gubi resztę. Nie usuwaj tego wpisu w przekonaniu, że 100 to wartość domyślna, jak podaje tabela w dokumentacji. W Strapi 5.56 (październik 2026) domyślny jest tylko `defaultLimit` równy 25, a bez `maxLimit` to samo żądanie zwraca `"pageSize":500`. `withCount` dokłada `total` i `pageCount`; żądanie może to wyłączyć przez `pagination[withCount]=false` i oszczędzić `COUNT` na dużej tabeli.

`strictParams: true` zamienia nieznany parametr najwyższego poziomu w błąd: `?include=author` daje 400 `Invalid key include`. Literówka nie przechodzi niezauważona, a własne parametry tras rejestrujesz w `register` (dokumentacja, „Custom Content API parameters”). Inna rozbieżność z dokumentacją: `pagination[limit]=-1` miało zwracać „wszystko do `maxLimit`”, a REST zwraca jeden rekord (`"limit":1`). Wartość z query string jest tekstem `"-1"` i porównanie z liczbą `-1` w `@strapi/utils` jej nie rozpoznaje. Potrzebujesz wszystkiego – stronicuj w pętli do `pageCount`.

## `status`: szkice i wersje opublikowane

Typ z draft & publish ma dwie wersje dokumentu. REST domyślnie zwraca opublikowane, a `status=draft` szkice, w całym żądaniu łącznie z dołączonymi relacjami. Pełny model opisuje rozdział 8; tu liczy się to, co widzi klient:

```text
$ curl -g 'localhost:1303/api/articles?status=draft&fields[0]=title&fields[1]=publishedAt'
{"data":[{"id":1,"documentId":"e5uauilz20m1fx7eaoywnsk3","title":"Policies in Strapi 5","publishedAt":null}, ...,
         {"id":7,"documentId":"vgutht82kwd2mteh07ptyka6","title":"Self-hosting Strapi with Docker","publishedAt":null}],
 "meta":{"pagination":{"page":1,"pageSize":25,"pageCount":1,"total":4}}}
```

To żądanie bez tokenu. Uprawnienie `find` nie rozróżnia wersji, więc każdy, kto zna parametr, czyta nieopublikowany tekst o Dockerze. Zapis ma odwrotną niespodziankę: w REST `published` jest domyślne także dla `POST` i `PUT`, w przeciwieństwie do Document Service. Anna tworzy szkic z `?status=draft`, a potem poprawia literówkę:

```text
POST /api/articles?status=draft                       → 201 "documentId":"xftvajm7vh2ns8f0el2rjxs6","publishedAt":null
GET  /api/articles/xftvajm7vh2ns8f0el2rjxs6 (anonim)    → 404
PUT  /api/articles/xftvajm7vh2ns8f0el2rjxs6 {"data":{"excerpt":"Typo fix"}} → 200 "publishedAt":"2026-10-03T18:37:42.613Z"
GET  /api/articles/xftvajm7vh2ns8f0el2rjxs6 (anonim)    → 200
```

> **Pułapka:** `PUT` bez `?status=draft` publikuje dokument. Edytor, który zapisuje szkic przez REST i zapomni o parametrze, wypuszcza na stronę niedokończony tekst. Klient pracujący na szkicach powinien przekazywać `status` jawnie w każdym zapisie, także w `create`.

Wyciek szkiców zamyka polityka (policy). Ma działać dla REST i, za chwilę, dla GraphQL, więc sprawdza typ kontekstu:

```ts
// src/policies/drafts-for-authors-only.ts (bez importów i typu kontekstu)
export default (policyContext: DraftPolicyContext) => {
  const requested = policyContext.is('graphql') ? policyContext.args?.status : policyContext.request.query.status;
  if (String(requested ?? '').toLowerCase() !== 'draft') return true;

  const { user, auth } = policyContext.state;
  if (user || auth?.strategy?.name === 'content-api-token') return true;

  throw new errors.PolicyError('Drafts require authentication');
};
```

W REST polityka czyta `request.query`, bo `policyContext.query` jest w politykach puste (rozdział 4 wyjaśnia dlaczego). W GraphQL argumenty leżą w `args`, a enum ma postać `DRAFT`. Strategia API tokenów nazywa się w Strapi 5.56 `content-api-token`, nie `api-token`. Po podpięciu w core routerze artykułów (`find`, `findOne`, jak w rozdziale 4) anonimowe `?status=draft` dostaje 403 `Drafts require authentication`, a z JWT Anny albo z tokenem read-only (np. podgląd w Next.js z rozdziału 11) – listę szkiców. To świadomy kompromis: każdy zalogowany użytkownik czyta wszystkie szkice, także cudze. Rozdział 7 domyka REST ostrzej, middleware trasy `published-only`, który wymusza `status=published` dla wszystkich poza API tokenem i daje autorom tylko ich własne szkice przez `/articles/mine`. Middleware tras nie obejmują jednak GraphQL, więc polityka zostaje strażnikiem dla obu API.

Jedna trasa to za mało. `GET /api/categories?status=draft&populate[articles][fields][0]=title` dalej zwracało szkic o Dockerze w kategorii DevOps, bo `status` przechodzi na dołączone relacje. Politykę trzeba podpiąć w każdym typie, z którego da się dojść do artykułów (w `examples/`: artykuły, kategorie, komentarze), albo zastąpić ją middleware globalnym z rozdziału 4. Podobnie do `status` działa `locale` (`?locale=pl`); fundament nie ma i18n, więc Strapi go ignoruje, a rozdział 8 pokazuje go na typie z tłumaczeniami.

## Zapis relacji: `connect`, `disconnect`, `set`

Relację w `POST` i `PUT` ustawiasz przez `documentId`. Dla relacji „do jednego” wystarczy skrót `"category": "<documentId>"` albo `null`. Relację „do wielu” zmieniasz trzema operacjami: `connect` dokłada, `disconnect` odłącza, `set` zastępuje listę. Anna wysyła kolejne `PUT /api/articles/xftvajm7vh2ns8f0el2rjxs6?status=draft` (`C1`–`C3` to `documentId` jej komentarzy, `FRONTEND` i `DEVOPS` – kategorii); obok stan po zapisie:

```text
{"category":{"connect":["FRONTEND"]},"comments":{"connect":["C1","C2"]}}  → Frontend ["First!","Does this work..."]
{"comments":{"connect":[{"documentId":"C3","position":{"start":true}}]}}   → Frontend ["What about i18n?","First!","Does..."]
{"category":{"disconnect":["FRONTEND"]},"comments":{"disconnect":["C1"]}}  → null     ["What about i18n?","Does..."]
{"category":"DEVOPS","comments":{"set":["C1"]}}                            → DevOps   ["First!"]
{"category":null,"comments":{"set":[]}}                                    → null     []
```

`connect` i `disconnect` to aktualizacje częściowe, więc dwa równoległe zapisy z różnymi komentarzami się nie nadpisują. Długa forma z `position` (`start`, `end`, `before`, `after`) ustala kolejność, co ma sens dla list typu „artykuły polecane”. Gołą tablicę Strapi traktuje jak `set`, ale `set` napisane wprost mówi czytelnikowi, że lista jest zastępowana. Nieistniejący `documentId` daje 400 `Document with id "..." not found`.

Pole `comments` to strona `mappedBy`, więc `connect` zmienia w rzeczywistości `article` w komentarzu i zabiera go artykułowi, do którego należał. Anna może też przepiąć cudze komentarze do swojego artykułu, bo uprawnienie `update` na artykułach nie mówi nic o komentarzach. Takie reguły należą do kontrolera albo middleware Document Service (rozdziały 5 i 6).

## Klient: fetch z `qs` albo `@strapi/client`

Zapis z nawiasami jest nieczytelny i łatwo w nim o błąd. Dokumentacja zaleca `qs`: piszesz obiekt, a `qs.stringify(..., { encodeValuesOnly: true })` buduje URL. Pełny `client/src/fetch-qs.ts` ma typy odpowiedzi i obsługę błędów:

```ts
// client/src/fetch-qs.ts (fragment)
const query = qs.stringify(
  {
    fields: ['title', 'slug', 'excerpt', 'publishedAt'],
    populate: { cover: { fields: ['url', 'alternativeText'] }, category: { fields: ['name', 'slug'] } },
    filters: { category: { slug: { $eq: categorySlug } } },
    sort: ['publishedAt:desc', 'title:asc'],
    pagination: { page, pageSize: 10 },
  },
  { encodeValuesOnly: true },
);
const response = await fetch(`${baseUrl}/api/articles?${query}`);
```

```text
$ STRAPI_URL=http://localhost:1303 node src/fetch-qs.ts backend
Policies in Strapi 5 [Backend] cover=/uploads/policies_cover_791620a0b1.png
Document Service middlewares [Backend] cover=-
```

Typ `ArticleCard` w skrypcie opisuje wynik tego konkretnego zapytania, a nie schemat typu treści. Kształt odpowiedzi zależy od `fields` i `populate`, więc jeden typ „Article” dla całego frontendu byłby fikcją; generowanie typów omawiają rozdziały 11 i 12.

`@strapi/client` (wersja 1.6, październik 2026) to oficjalna, cienka nakładka na `fetch`. Przyjmuje ten sam obiekt zapytania, dokłada nagłówek `Authorization` i zamienia odpowiedzi 4xx/5xx na wyjątki:

```ts
// client/src/strapi-client.ts (fragment)
const authorClient = strapi({ baseURL, auth: jwt });
const { data: draft } = await authorClient.collection('articles').create(
  { title: 'Typed fetching with @strapi/client', slug: 'typed-fetching-with-strapi-client', category: categoryId },
  { status: 'draft', fields: ['title', 'publishedAt'], populate: { category: { fields: ['name'] } } },
);
// update with an unknown field → HTTPBadRequestError; error.response holds Strapi's error body
```

Opcja `auth` jest opisana jako API token, ale to po prostu wartość nagłówka `Bearer`, więc działa też JWT z `/api/auth/local`. Logowanie i odświeżanie tokenów zostaje po stronie aplikacji (rozdziały 7 i 11). Wyniki mają typ `Document` z `[key: string]: any`, więc klient daje wygodę, nie bezpieczeństwo typów. Sięgnij po niego, gdy chcesz ujednolicić błędy i token w wielu miejscach; przy kilku zapytaniach w Server Components fetch z `qs` jest równie krótki.

## Specyfikacja OpenAPI

`strapi openapi generate` (funkcja eksperymentalna) tworzy specyfikację OpenAPI 3.1 całego Content API bez startu serwera HTTP. Dla fundamentu to 425 KB i 38 ścieżek: CRUD typów treści, users-permissions (`/auth/local`, `/auth/refresh`, `/users/me`), upload, i18n. Parametry są opisane dokładnie, z enumami pól dla `fields` i `sort`. Gorzej ze schematami:

```json
"servers": [{ "url": "", "description": "Default server" }],
"/articles/{id}": { "get": { "parameters": [{ "name": "id",
  "schema": { "type": "string", "format": "uuid", "description": "The document ID, represented by a UUID" } }] } },
"content": { "description": "A dynamic zone field", "type": "array", "items": {} }
```

Ścieżki nie mają prefiksu `/api`, a `servers` jest pusty, bo generator bierze adres z `server.url`. `documentId` udaje UUID, choć prawdziwe identyfikatory wyglądają jak `e5uauilz20m1fx7eaoywnsk3`, więc klient walidujący według specyfikacji odrzuci każdą odpowiedź. Strefa dynamiczna jest tablicą bez typu. Adres naprawia plik `config/openapi.ts` z kluczem `servers` (w `examples/`: `PUBLIC_URL` plus `/api`), który czyta `@strapi/openapi`, choć dokumentacja go nie opisuje. Specyfikacja przyda się do Swagger UI, Postmana i jako mapa API dla agentów AI; generatorom klientów z walidacją na razie nie ufaj. Serwowanie jej pod `/api/openapi.json` (`openapi` w `config/server.ts`) ujawnia całe API, także typy niepubliczne, więc w produkcji zostań przy CLI.

## GraphQL

Plugin GraphQL (`npm install @strapi/plugin-graphql`) dodaje endpoint `/graphql` z Apollo Server i schematem wygenerowanym z typów treści (shadow CRUD). Bez konfiguracji start kończy się ostrzeżeniem „Built-in GraphQL operation limits are unbounded or invalid for: depthLimit, maxLimit”. To pierwsza rzecz do ustawienia:

```ts
// config/plugins.ts (fragment)
graphql: {
  config: { depthLimit: 7, defaultLimit: 25, maxLimit: 100, landingPage: env('NODE_ENV') !== 'production' },
},
```

Zapytanie `articles → category → articles…` głębsze niż 7 dostaje `'' exceeds maximum operation depth of 7`. `maxLimit` przycina `pageSize: 500` do 100, ale domyślnie w GraphQL wynosi `-1`, czyli brak limitu. `landingPage` włącza Apollo Sandbox. Opcja `amountLimit` ze starych poradników w Strapi 5 nie istnieje i jest po cichu ignorowana. Strona artykułu w GraphQL:

```graphql
{ articles(filters: { category: { slug: { eq: "backend" } } }, sort: "title:asc") {
    documentId title
    seo { metaTitle shareImage { url } }
    content { __typename ... on ComponentSharedQuote { body } ... on ComponentSharedMedia { file { url } } }
} }
```

```text
{"documentId":"e5uauilz20m1fx7eaoywnsk3","title":"Policies in Strapi 5",
 "seo":{"metaTitle":"Policies in Strapi 5","shareImage":{"url":"/uploads/policies_cover_791620a0b1.png"}},
 "content":[{"__typename":"ComponentSharedRichText"},{"__typename":"ComponentSharedQuote","body":"Measure before you optimise."},
            {"__typename":"ComponentSharedMedia","file":{"url":"/uploads/policies_cover_791620a0b1.png"}}]}
```

To, co w REST wymaga `populate`, tu wynika z zapytania. Strefa dynamiczna to unia, więc pola komponentu wybierasz fragmentem `... on`, a komponenty bez fragmentu przychodzą z samym `__typename`, zamiast znikać. Identyfikatorem jest tylko `documentId`; `status: DRAFT`, `filters`, `sort` i `pagination` działają jak w REST, a metadane paginacji daje wariant `articles_connection { nodes pageInfo }`. Różni się obsługa uprawnień: `author { username }` od gościa nie znika po cichu, tylko daje `null` i błąd `Forbidden access` w `errors`. Ważniejsze jest to, czego nie widać:

```text
REST     trasa → polityki trasy → middleware trasy → kontroler → serwis → Document Service
GraphQL  /graphql → auth i resolversConfig (middlewares, policies) → resolver → Document Service
```

Resolvery shadow CRUD walidują i sanityzują zapytanie, a potem wołają `strapi.documents()` bezpośrednio (`builders/resolvers/query.js` w pluginie), z pominięciem tras, kontrolerów i serwisów.

> **Pułapka:** po instalacji GraphQL wszystko, co zabezpieczyłeś w trasach i kontrolerach, ma obejście. Polityka `is-owner` z rozdziału 4 nie chroni mutacji `updateArticle`, filtr moderacji z rozdziału 5 nie działa w zapytaniu `comments`, a Anna tworzy mutacją `createComment(data: { body: "Buy cheap pills", moderationStatus: approved })` od razu zatwierdzony komentarz. Działa tylko to, co leży w Document Service (rozdział 6) albo w `resolversConfig`.

Redakcja zamyka te drogi w `register` w `src/index.ts`:

```ts
// src/index.ts (fragment; draftGuards maps nine article/category/comment queries to the draft policy)
const extensionService = strapi.plugin('graphql').service('extension');
extensionService.shadowCRUD('api::comment.comment').disableMutations();
extensionService.shadowCRUD('api::global.global').disableMutations();

extensionService.use(() => ({
  typeDefs: `type Query { articleBySlug(slug: String!): Article }`,
  resolvers: {
    Query: {
      articleBySlug: (_parent: unknown, args: { slug: string }) =>
        strapi.documents('api::article.article').findFirst({ filters: { slug: { $eq: args.slug } }, status: 'published' }),
    },
  },
  resolversConfig: {
    'Query.articleBySlug': { auth: { scope: ['api::article.article.findOne'] } },
    ...draftGuards,
  },
}));
```

`disableMutations()` usuwa mutacje komentarzy ze schematu, więc komentarze powstają tylko przez kontroler REST z walidacją z rozdziału 5; `createComment` kończy się teraz błędem `Cannot query field "createComment" on type "Mutation"`. Węższe opcje to `disableActions(['delete'])` i `field('moderationStatus').disableInput()`.

`articleBySlug` to własny resolver, bo wbudowane `article` przyjmuje tylko `documentId`, a frontend zna slug z URL-a. Zwraca dokument z Document Service, a typ `Article` z shadow CRUD rozwiązuje zagnieżdżone pola razem z kontrolą uprawnień do relacji. Klucz `auth` jest konieczny: bez niego gość dostaje `Forbidden access`, a każdy zalogowany użytkownik dowolnej roli – wynik. `scope` wiąże resolver z uprawnieniem `findOne` artykułów, czyli z tymi samymi rolami co REST. `draftGuards` podpina politykę `drafts-for-authors-only` pod wszystkie zapytania o artykuły, kategorie i komentarze: anonimowe `articles(status: DRAFT)` zwraca `"data": null` z błędem `Drafts require authentication`, a z JWT Anny albo tokenem read-only listę szkiców.

Dla Redakcji REST zostaje domyślnym wyborem: działa bez pluginu, przechodzi przez polityki i kontrolery z rozdziałów 4 i 5 i łatwo go cache'ować po URL-u. GraphQL ma sens, gdy wiele ekranów potrzebuje różnych wycinków tych samych danych albo zespół już pracuje z Apollo. Wtedy traktuj go jak drugie, równorzędne API, z własnymi limitami, politykami w `resolversConfig` i regułami biznesowymi w Document Service.

## Podsumowanie

- Odpowiedź v5 jest płaska. W URL-ach i relacjach używaj `documentId`; `id` różni się między szkicem a wersją opublikowaną.
- REST nie dołącza niczego bez `populate`. W kodzie wymieniaj pola, a strefę dynamiczną dołączaj przez `on` z wpisem dla każdego komponentu, bo pominięte znikają z odpowiedzi.
- Relacje bez uprawnień `populate` pomija po cichu, a `filters` odrzuca błędem 400.
- `maxLimit` przycina `pageSize` bez błędu i nie ma wartości domyślnej; `strictParams` odrzuca nieznane parametry; `pagination[limit]=-1` w REST zwraca jeden rekord.
- `status=draft` czyta każdy z `find`, także przez relacje innych typów, a zapis przez REST bez `status=draft` publikuje dokument.
- `connect` i `disconnect` zmieniają relację częściowo, `set` zastępuje listę.
- `qs` i `@strapi/client` przyjmują ten sam obiekt zapytania; klient upraszcza błędy i token, ale nie daje typów.
- Specyfikacja z `strapi openapi generate` to dobra mapa API, ale bez prefiksu `/api` i z błędnym formatem `documentId`.
- GraphQL omija trasy i kontrolery REST: ustaw `depthLimit` i `maxLimit`, wyłącz zbędne mutacje i zabezpiecz zapytania w `resolversConfig`.

## Co dalej

Trasy, kontrolery i parametry REST kontrolują tylko jedną z dróg do danych, a GraphQL pokazał, że ta sama treść może przyjść inną. Rozdział 4 wraca na serwer i opisuje trasy, polityki i middleware, w tym middleware globalne – właściwe miejsce na regułę, która ma objąć wszystkie typy naraz. Rozdział 8 rozwija draft & publish i i18n, a rozdział 11 składa całość we frontend w Next.js z podglądem szkiców i rewalidacją cache.

## Źródła

- https://docs.strapi.io/cms/api/rest
- https://docs.strapi.io/cms/api/rest/populate-select
- https://docs.strapi.io/cms/api/rest/guides/understanding-populate
- https://docs.strapi.io/cms/api/rest/filters
- https://docs.strapi.io/cms/api/rest/sort-pagination
- https://docs.strapi.io/cms/api/rest/status
- https://docs.strapi.io/cms/api/rest/locale
- https://docs.strapi.io/cms/api/rest/relations
- https://docs.strapi.io/cms/configurations/api
- https://docs.strapi.io/cms/api/client
- https://docs.strapi.io/cms/api/openapi
- https://docs.strapi.io/cms/api/graphql
- https://docs.strapi.io/cms/api/graphql/advanced-policies
- https://docs.strapi.io/cms/plugins/graphql
