# Rozdział 5. Kontrolery, serwisy, walidacja i błędy

> **Cel rozdziału:** nauczyć się rozszerzać kontrolery i serwisy tak, żeby nowe endpointy nie wypuszczały prywatnych danych, nie ufały ciału żądania i zwracały czytelne błędy.
>
> **Kod:** `examples/05-kontrolery-i-serwisy/`. **Pakiety poza fundamentem:** brak (`zod` i `yup` są reeksportowane przez `@strapi/utils`).

Redakcja dostaje pierwsze prośby, których nie da się wyklikać w panelu. Pod artykułem ma się pojawić blok „podobne artykuły”, komentarze mają czekać na moderację, a redaktor zatwierdza je jednym przyciskiem. Wszystko to ląduje w kontrolerach (controllers) i serwisach (services), czyli w warstwie, która w fundamencie składa się z trzech linijek `factories.createCore...`.

Kod w tej warstwie pisze się szybko i równie szybko psuje bezpieczeństwo. Zobaczysz w curl-u dwa prawdziwe problemy z typowego projektu: endpoint zwracający hash hasła autora i formularz komentarza, przez który użytkownik sam zatwierdza swój spam. Oba wynikają z założenia „Strapi to za mnie sprawdzi”. Trasy i polityki opisuje rozdział 4, Document Service rozdział 6; tutaj zajmujemy się tym, co pomiędzy: kontrolerem, który rozmawia z HTTP, i serwisem, który zna reguły biznesowe.

## Co robi rdzeń

`factories.createCoreController('api::comment.comment')` tworzy kontroler z pięcioma akcjami: `find`, `findOne`, `create`, `update` i `delete`. Core router z fundamentu kieruje na nie trasy `GET /api/comments`, `POST /api/comments` i pozostałe. Warto raz zajrzeć do implementacji w `node_modules/@strapi/core/dist/core-api/controller/collection-type.js`, bo każda akcja to ten sam schemat:

```text
create(ctx)
  validateQuery(ctx)          → 400, gdy query zawiera niedozwolone pola
  sanitizeQuery(ctx)          → usuwa z query to, czego rola nie może czytać
  validateInput(data, ctx)    → 400 przy nieznanych kluczach i zabronionych relacjach
  sanitizeInput(data, ctx)    → usuwa pola tylko do odczytu
  strapi.service(uid).create  → core service → strapi.documents(uid).create
  sanitizeOutput(entity, ctx) → usuwa pola prywatne i relacje bez uprawnień
  transformResponse(...)      → { data, meta }
```

Core service jest jeszcze cieńszy: dokłada `status: 'published'` jako wartość domyślną i woła Document Service. Cała ochrona danych siedzi więc w kontrolerze. Walidacja (validate) sprawdza i rzuca błąd 400, sanityzacja (sanitize) po cichu wycina to, czego nie powinno być. Obie korzystają ze schematu typu treści i z uprawnień roli, która wykonuje żądanie (`ctx.state.auth`).

## Rozszerzanie z `super`

Pierwsze zadanie: publiczna lista komentarzy ma zwracać tylko zatwierdzone. Nie piszesz `find` od zera, tylko modyfikujesz wejście i oddajesz sterowanie rdzeniowi:

```ts
// src/api/comment/controllers/comment.ts (fragment)
export default factories.createCoreController('api::comment.comment', ({ strapi }) => ({
  async find(ctx) {
    const filters = ctx.query.filters ?? {};
    ctx.query = { ...ctx.query, filters: { $and: [filters, { moderationStatus: 'approved' }] } };
    return super.find(ctx);
  },
}));
```

Filtry klienta trafiają do `$and` razem z warunkiem moderacji, więc nie da się go nadpisać parametrem w URL-u. Próba wyciągnięcia oczekujących komentarzy daje pustą listę:

```text
$ curl -g 'localhost:1305/api/comments?filters[moderationStatus]=pending'
{"data":[],"meta":{"pagination":{"page":1,"pageSize":25,"pageCount":0,"total":0}}}
```

`super.find` wykonuje całą sekwencję z diagramu, więc walidację i sanityzację dostajesz za darmo – dlatego dokumentacja zaleca rozszerzanie core controllera zamiast pisania własnego. Gdy akcję nadpisujesz w całości albo dodajesz nową, sekwencję odtwarzasz sam. Gdyby filtr miał działać także dla zapytań z kodu serwera, lepszym miejscem jest middleware Document Service z rozdziału 6.

## Sanityzacja: wyciek, który widać w curl-u

Blok „podobne artykuły” to nowa akcja `related`. Najprostsza wersja, jaką pisze się w pośpiechu, woła Document Service i zwraca wynik:

```ts
async related(ctx) {
  const article = await strapi.documents('api::article.article').findOne({
    documentId: ctx.params.id, status: 'published', populate: ['category'],
  });
  if (!article?.category) return ctx.notFound();
  return strapi.documents('api::article.article').findMany({
    status: 'published',
    filters: { category: { documentId: article.category.documentId }, documentId: { $ne: article.documentId } },
    populate: ['author', 'category'],
    limit: 3,
  });
},
```

Anonimowe żądanie (rola Public ma uprawnienie do `related`, o czym za chwilę):

```text
$ curl localhost:1305/api/articles/fn3wajqrwfq0k9pifujh59er/related
[{"documentId":"e8nmfxdpzlhpts6e85ftz6ia","title":"Document Service middlewares",
  "author":{"id":1,"username":"anna","email":"anna@example.com",
    "password":"$2a$10$BwxtogY6E0gkgOEqfmNyaOcF.yqBdF4ZMBmqR/P6Ww6...",
    "resetPasswordToken":null,"confirmed":true,"blocked":false, ...}, ...}]
```

Każdy odwiedzający widzi e-mail i hash hasła autorki. Document Service działa z uprawnieniami serwera: zwraca wszystkie pola, także prywatne (`password` w użytkowniku users-permissions), i każdą relację, o którą poprosisz. Pola prywatne i relacje, do których rola nie ma dostępu, wycina dopiero `sanitizeOutput`. Rola Public nie ma uprawnienia `find` na użytkownikach, więc po sanityzacji relacja `author` znika z odpowiedzi. Brakuje też koperty `{ data, meta }`, której oczekuje frontend.

> **Pułapka:** zwracanie surowego wyniku `strapi.documents()` albo `strapi.db.query()` z kontrolera. Kod przechodzi testy, bo testujesz go zwykle jako właściciel danych, a wyciek widać dopiero z perspektywy anonimowego klienta. Każda akcja, która nie kończy się na `super.*`, powinna kończyć się na `sanitizeOutput`.

Poprawiona wersja ma pięć linii logiki i resztę oddaje serwisowi:

```ts
// src/api/article/controllers/article.ts
import { factories } from '@strapi/strapi';
import type { Core } from '@strapi/strapi';

// Core helpers (sanitizeOutput, transformResponse) are optional in the factory's `this` type.
type CoreController = Core.CoreAPI.Controller.CollectionType;

export default factories.createCoreController('api::article.article', ({ strapi }) => ({
  async related(this: CoreController, ctx) {
    await this.validateQuery(ctx);
    const query = await this.sanitizeQuery(ctx);

    const articles = await strapi.service('api::article.article').findRelated(ctx.params.id, query);

    const sanitized = await this.sanitizeOutput(articles, ctx);
    return this.transformResponse(sanitized);
  },
}));
```

Adnotacja `this: CoreController` nie jest ozdobnikiem. W typach Strapi metody pomocnicze w `this` są opcjonalne (`Partial`), więc przy `strict: true` z fundamentu `this.sanitizeOutput(...)` kończy się błędem `TS2722: Cannot invoke an object which is possibly 'undefined'`. Przykłady TS w dokumentacji tego nie pokazują.

Teraz `?populate=author` od anonimowego klienta zwraca 200 bez pola `author`, a `?fields[0]=title&populate=category` działa normalnie. `validateQuery` nie sprawdza `populate`, więc zabroniona relacja jest cicho usuwana przez `sanitizeQuery`, a nie odrzucana błędem. Helpery `this.*` działają na modelu kontrolera. Jeśli w kontrolerze artykułów zwracasz kategorie, użyj `strapi.contentAPI.sanitize.output(data, strapi.contentType('api::category.category'), { auth: ctx.state.auth })`, inaczej sanityzacja pójdzie według złego schematu.

## Cienki kontroler, logika w serwisie

Kontroler zna HTTP: parametry, query, użytkownika, status odpowiedzi. Serwis zna Redakcję: czym są „podobne artykuły” i kiedy komentarz da się zatwierdzić. Serwis nie dostaje `ctx`, tylko zwykłe argumenty, dzięki czemu wywołasz go z crona, z innego kontrolera albo z testu.

```ts
// src/api/article/services/article.ts
type FindManyParams = Modules.Documents.ServiceParams<'api::article.article'>['findMany'];
type RelatedQuery = Pick<FindManyParams, 'fields' | 'populate'>;

export default factories.createCoreService('api::article.article', ({ strapi }) => ({
  async findRelated(documentId: string, { fields, populate }: RelatedQuery = {}) {
    const article = await strapi.documents('api::article.article').findOne({
      documentId, status: 'published', populate: ['category'],
    });
    if (!article) throw new errors.NotFoundError('Article not found');
    if (!article.category) return [];

    return strapi.documents('api::article.article').findMany({
      fields, populate, status: 'published',
      filters: { category: { documentId: article.category.documentId }, documentId: { $ne: documentId } },
      sort: 'publishedAt:desc',
      limit: RELATED_LIMIT,
    });
  },
}));
```

Serwis przejmuje z zapytania klienta tylko `fields` i `populate`; filtry, sortowanie i limit definiują „podobne artykuły”, więc klient ich nie zmienia. Brak artykułu to `NotFoundError` z `@strapi/utils`, który Strapi zamienia na 404 bez kodu w kontrolerze. Typ parametrów z `Modules.Documents` sprawia, że literówka w nazwie pola wychodzi w `tsc`.

Nowa akcja potrzebuje trasy. Wystarczy plik obok core routera:

```ts
// src/api/article/routes/01-custom-article.ts
export default {
  routes: [
    { method: 'GET', path: '/articles/:id/related', handler: 'api::article.article.related' },
  ],
};
```

Konfigurację tras, kolejność plików i `auth: false` omawia rozdział 4. Tu zapamiętaj dwie rzeczy. Po pierwsze, nowa akcja pojawia się w users-permissions jako osobne uprawnienie i dopóki go nie nadasz roli, każde żądanie dostaje 403. W `examples/` jest skrypt `scripts/grant-ch05.js`, który nadaje `related` rolom Public i Authenticated oraz tworzy rolę Editor z uprawnieniem `approve` (ustawianie uprawnień kodem rozwija rozdział 7). Po drugie, trasa wskazująca na nieistniejący handler nie daje 404, tylko zatrzymuje start serwera błędem `Handler not found "api::comment.comment.approve"`.

## Kontroler nie ufa ciału żądania

Fundament daje roli Authenticated uprawnienie `create` na komentarzach i zostawia domyślny kontroler. Schemat komentarza ma pole `moderationStatus` z wartością domyślną `pending`. Wartość domyślna działa jednak tylko wtedy, gdy klient pola nie poda:

```text
$ curl -X POST localhost:1305/api/comments -H "Authorization: Bearer eyJhbGciOi..." \
    -H 'Content-Type: application/json' \
    -d '{"data":{"body":"Buy cheap pills","moderationStatus":"approved","article":"fn3wajqrwfq0k9pifujh59er"}}'
{"data":{"id":4,"documentId":"g4uxdiiiissq016wvx5exp66","body":"Buy cheap pills",
  "moderationStatus":"approved", ...},"meta":{}}
```

Spam jest od razu na publicznej liście. To klasyczne masowe przypisanie (mass assignment): klient ustawia pole, które powinien kontrolować serwer. Z polem `author` jest podobnie. Przy uprawnieniach z seeda `"author":2` kończy się błędem 400 `Invalid key author`, bo rola nie może czytać użytkowników. Wystarczy jednak nadać jej `find` na użytkownikach (typowe, gdy pod komentarzem chcesz pokazać autora), a Anna publikuje zatwierdzony komentarz jako Piotr.

`sanitizeInput` i `validateInput` tu nie pomogą. Pilnują schematu i uprawnień do relacji, a `moderationStatus` to zwykłe, zapisywalne pole. Strapi nie wie, że w Twojej domenie zmienia je tylko redaktor. Rozwiązanie: kontroler przyjmuje jawną listę pól, a serwis sam ustawia autora i status.

```ts
// src/api/comment/controllers/comment.ts (fragment)
const parseCommentInput = validateZodSchema(
  z.strictObject({
    body: z.string().trim().min(1).max(2000),
    article: z.string().min(1),
  }),
);

async create(this: CoreController, ctx) {
  const user = ctx.state.user;
  if (!user) return ctx.unauthorized();

  const input = parseCommentInput(ctx.request.body?.data);
  const comment = await strapi.service('api::comment.comment').submit({
    body: input.body, articleId: input.article, authorId: user.id,
  });

  ctx.status = 201;
  return this.transformResponse(await this.sanitizeOutput(comment, ctx));
},
```

```ts
// src/api/comment/services/comment.ts (fragment)
async submit({ body, articleId, authorId }: CommentSubmission) {
  const article = await strapi.documents('api::article.article').findOne({
    documentId: articleId, status: 'published',
  });
  if (!article) throw new NotFoundError('Article not found');

  return strapi.documents('api::comment.comment').create({
    data: { body, article: articleId, author: authorId, moderationStatus: 'pending' },
  });
},
```

`z.strictObject` odrzuca każdy klucz spoza listy, więc atak kończy się czytelnym 400, a poprawny komentarz zawsze trafia do kolejki:

```text
{"data":null,"error":{"status":400,"name":"ValidationError",
  "message":"Unrecognized key: \"moderationStatus\"","details":{"errors":[...]}}}

{"data":{"id":4,"documentId":"x3ojuffzks86bfo2oqq8e36p","body":"Thanks, very useful",
  "moderationStatus":"pending", ...},"meta":{}}
```

Autor pochodzi z `ctx.state.user`, a nie z ciała żądania, więc nie da się go podrobić niezależnie od uprawnień roli. Serwis przy okazji pilnuje reguły, której nie wyrazisz w schemacie: komentować można tylko opublikowane artykuły. Nie da się tego zrobić przez `ctx.request.body.data.author = user.id` przed `super.create(ctx)`, bo `validateInput` w rdzeniu odrzuci klucz `author` tym samym `Invalid key author`. Alternatywą bez własnej akcji `create` jest middleware Document Service ustawiający autora (rozdział 6). Ograniczenie, kto może edytować i usuwać czyje artykuły, to polityka `is-owner` z rozdziału 4.

Ta ochrona obowiązuje tylko na trasie REST. Resolvery GraphQL i panel admina wołają Document Service z pominięciem kontrolera, więc po instalacji GraphQL ten sam atak wraca przez mutację `createComment` (rozdział 3). Regułę, która ma działać niezależnie od wejścia, przenieś do middleware Document Service (rozdział 6).

## Akcja niestandardowa: zatwierdzanie komentarza

`POST /comments/:id/approve` składa się z tych samych klocków: trasa w `routes/01-custom-comment.ts`, akcja w kontrolerze, która woła serwis i kończy się na `sanitizeOutput` i `transformResponse` jak `related`, oraz reguła w serwisie:

```ts
// src/api/comment/services/comment.ts (fragment)
async approve(documentId: string) {
  const comment = await strapi.documents('api::comment.comment').findOne({ documentId });
  if (!comment) throw new NotFoundError('Comment not found');
  if (comment.moderationStatus !== 'pending') {
    throw new ApplicationError('Only pending comments can be approved', {
      moderationStatus: comment.moderationStatus,
    });
  }
  return strapi.documents('api::comment.comment').update({ documentId, data: { moderationStatus: 'approved' } });
},
```

Kto może zatwierdzać, decyduje uprawnienie `approve` w roli, a nie kod akcji:

```text
anna (Authenticated):   403 {"name":"ForbiddenError","message":"Forbidden"}
ewa (Editor):           200 {"data":{"documentId":"x3ojuffzks86bfo2oqq8e36p","moderationStatus":"approved",...}}
ewa, drugi raz:         400 {"name":"ApplicationError","message":"Only pending comments can be approved",
                             "details":{"moderationStatus":"approved"}}
ewa, /comments/nope:    404 {"name":"NotFoundError","message":"Comment not found"}
```

## `ctx` w kontrolerze

Kontroler dostaje kontekst Koa rozszerzony przez Strapi. W praktyce używasz kilku pól: `ctx.params` (parametry ścieżki; `id` to `documentId`), `ctx.query` (query sparsowane do obiektu z zagnieżdżonymi `filters` i `populate`), `ctx.request.body` (ciało, w Content API w kopercie `data`), `ctx.state.user` (zalogowany użytkownik users-permissions z rolą), `ctx.state.auth` (strategia uwierzytelnienia, którą przekazujesz do sanityzacji) i `ctx.state.route` (konfiguracja trasy). Wartość zwrócona z akcji staje się ciałem odpowiedzi, status ustawiasz przez `ctx.status`. Skróty `ctx.badRequest()`, `ctx.notFound()` i pokrewne (nazwy z http-errors w camelCase) przyjmują komunikat i `details`. Jest też `strapi.requestContext.get()` dostępne z serwisu, ale to wyjście awaryjne: serwis zależny od żądania HTTP nie zadziała w cronie ani w skrypcie.

## Błędy i ich format

Każdy błąd Content API ma ten sam kształt:

```json
{ "data": null, "error": { "status": 404, "name": "NotFoundError", "message": "Comment not found", "details": {} } }
```

Strapi buduje go z klas w `errors` z `@strapi/utils` (`import { errors } from '@strapi/utils'`). W serwisach i lifecycle'ach rzucasz klasy, w kontrolerach i middleware możesz też użyć skrótów `ctx.*`. Tak wyglądały odpowiedzi z tymczasowej trasy testowej (Strapi 5.56, październik 2026):

| Źródło | Status | `name` | Twój `message` w odpowiedzi |
|---|---|---|---|
| `ApplicationError`, `ValidationError` | 400 | jak klasa | tak, z `details` |
| `ctx.badRequest('...', details)` | 400 | `BadRequestError` | tak |
| `NotFoundError`, `ctx.notFound('...')` | 404 | `NotFoundError` | tak |
| `PolicyError` | 403 | `PolicyError` | tak |
| `ForbiddenError` | 403 | `ForbiddenError` | nie, zawsze `Forbidden` |
| `UnauthorizedError` | 401 | `UnauthorizedError` | nie, zawsze `Unauthorized` |
| zwykły `throw new Error(...)` | 500 | `InternalServerError` | nie; pełny komunikat i stos tylko w logu serwera |

Ostatni wiersz oznacza, że przypadkowy wyjątek z treścią zapytania SQL nie trafi do klienta, ale frontend dostaje bezużyteczne 500. Każdy przewidywalny przypadek (brak rekordu, zły stan, niepoprawne dane) zamieniaj więc na klasę z `errors`.

> **Pułapka:** `throw new errors.ForbiddenError('You are not the author')` zwraca klientowi samo `Forbidden`. Dokumentacja wspomina o tym w notatce przy `ForbiddenError`, ale to samo dotyczy `UnauthorizedError`, o czym już nie pisze. Gdy frontend ma pokazać powód odmowy, użyj `PolicyError` (w polityce) albo `ApplicationError` z kodem w `details`.

## Walidacja wejścia: schemat, yup czy zod

Walidacja w Strapi ma trzy piętra. Schemat (`required`, `maxLength`, `enum`) sprawdza Document Service przy każdym zapisie, także z panelu: za długi tytuł daje 400 `title must be at most 160 characters`. Kontroler rdzenia sprawdza strukturę: nieznane pole w `data` daje 400 `Invalid key views`. Trzecie piętro to reguły, których schemat nie wyrazi – które pola wolno podać na danym endpoincie, format, zależności między polami. To piszesz sam, w kontrolerze.

`@strapi/utils` reeksportuje oba popularne narzędzia: `yup` z `validateYupSchema` oraz `z` (Zod 4) z `validateZodSchema`. Oba helpery zamieniają błąd biblioteki na `ValidationError` z listą `details.errors`, więc format odpowiedzi jest identyczny jak dla błędów rdzenia. W nowym kodzie wybierz Zod: daje typ wyniku bez dodatkowej deklaracji (`input.body` jest `string`), a Strapi 5 sam używa go do parametrów Content API. Yup ma sens, gdy rozszerzasz kod pluginu, który już go używa. Importuj `z` z `@strapi/utils`, a nie z osobno zainstalowanego `zod`, żeby nie mieć w projekcie dwóch wersji biblioteki.

> **Pułapka:** strona `strapi-utils` w dokumentacji opisuje helper `validateZod`. W Strapi 5.56 taki eksport nie istnieje; funkcja nazywa się `validateZodSchema` (sprawdzone w `node_modules/@strapi/utils/dist/zod.d.ts`). Import według dokumentacji kończy się błędem kompilacji.

## Podsumowanie

- Core controller w każdej akcji wykonuje `validateQuery`, `sanitizeQuery`, `validateInput`, `sanitizeInput` i `sanitizeOutput`. Rozszerzając go przez `super`, zachowujesz tę ochronę; pisząc akcję od zera, odtwarzasz ją sam.
- Document Service zwraca dane z uprawnieniami serwera, łącznie z polami prywatnymi. Bez `sanitizeOutput` anonimowy klient widzi e-mail i hash hasła autora.
- Kontroler tłumaczy HTTP na wywołanie serwisu; reguły biznesowe i rzucanie błędów domenowych należą do serwisu, który nie dostaje `ctx`.
- Nowa akcja wymaga trasy i nadania uprawnienia roli; trasa wskazująca na nieistniejący handler blokuje start serwera.
- Sanityzacja wejścia nie chroni pól biznesowych. Pola takie jak `moderationStatus` czy `author` ustawia serwer, a kontroler przyjmuje jawną listę pól (`z.strictObject`).
- Błędy rzucaj klasami z `errors` z `@strapi/utils`; `ForbiddenError` i `UnauthorizedError` ukrywają Twój komunikat, a zwykły `Error` daje 500.
- W TypeScripcie oznacz akcje używające `this.*` typem `this: Core.CoreAPI.Controller.CollectionType`.

## Co dalej

Kontroler działa tylko dla żądań, które przyszły przez REST. Gdy redaktor zmieni komentarz w panelu admina albo skrypt zapisze artykuł przez `strapi.documents()`, żaden z pokazanych tu kodów się nie wykona. Rozdział 6 schodzi piętro niżej, do Document Service i Query Engine, i pokazuje, jak reagować na zmiany danych niezależnie od tego, skąd przyszły: od wyliczania `readingTime` po ustawianie autora z kontekstu.

## Źródła

- https://docs.strapi.io/cms/backend-customization/controllers
- https://docs.strapi.io/cms/backend-customization/services
- https://docs.strapi.io/cms/backend-customization/requests-responses
- https://docs.strapi.io/cms/error-handling
- https://docs.strapi.io/cms/strapi-utils
- https://docs.strapi.io/cms/migration/v4-to-v5/breaking-changes/default-input-validation
- https://docs.strapi.io/cms/configurations/api
