# Rozdział 6. Document Service, Query Engine i reagowanie na zmiany

> **Cel rozdziału:** nauczysz się czytać i zapisywać treść przez Document Service, świadomie schodzić do Query Engine i umieszczać reguły „przy każdym zapisie” w middleware Document Service zamiast w lifecycle hookach.
>
> **Kod:** `examples/06-document-service/`. **Pakiety poza fundamentem:** brak.

Redakcja ma kilka reguł, które muszą działać zawsze, niezależnie od tego, kto zapisuje artykuł. Czas czytania (`readingTime`) ma się liczyć sam z treści. Slug ma powstać z tytułu, jeśli autor go nie poda. Kategorii, do której należą artykuły, nie wolno usunąć, bo artykuły straciłyby przypisanie. A artykuł utworzony przez zalogowaną autorkę ma mieć ją jako autora – bez względu na to, co przyśle klient.

Kontroler z rozdziału 5 albo middleware trasy z rozdziału 4 obsłużą te reguły tylko dla REST-a, a redaktor pracuje w panelu, skrypt importu zaś woła serwisy bezpośrednio. Potrzebujesz warstwy, przez którą przechodzi każdy zapis treści – w Strapi 5 to Document Service.

## Document Service: pracujesz na dokumentach, nie na wierszach

Dokument to jeden artykuł z punktu widzenia redakcji, identyfikowany stabilnym `documentId`. W bazie ten jeden artykuł to kilka wierszy: wersja robocza (draft), wersja opublikowana, a przy włączonym i18n – po parze na każdy język. Każdy wiersz ma własne numeryczne `id`. Document Service (`strapi.documents(uid)`) ukrywa tę różnicę: pytasz o dokument, podajesz `status` i `locale`, a serwis sam wybiera właściwe wiersze, synchronizuje relacje między wersjami i odpala zdarzenia dla webhooków.

Metody dzielą się na dwie grupy. Odczyt: `findOne`, `findFirst`, `findMany`, `count`. Zapis: `create`, `update`, `delete` oraz – tylko dla typów z draft & publish – `publish`, `unpublish` i `discardDraft`. Parametry wyglądają znajomo, jeśli znasz REST z rozdziału 3, ale są obiektami JavaScript, a nie query stringiem. Lista najnowszych opublikowanych artykułów z kategorii Backend:

```ts
const latest = await strapi.documents('api::article.article').findMany({
  status: 'published',
  filters: { category: { slug: 'backend' } },
  fields: ['title', 'slug', 'publishedAt'],
  populate: { category: { fields: ['name'] }, author: { fields: ['username'] } },
  sort: 'publishedAt:desc',
  limit: 2,
});
```

```json
[{ "publishedAt": "2026-10-03T18:07:59.298Z", "id": 4, "documentId": "j9i5dhs1wiefz0bco65zsw26",
   "title": "Document Service middlewares", "slug": "document-service-middlewares",
   "category": { "id": 1, "documentId": "wfyue085i2lzb8vin2zk3mju", "name": "Backend" },
   "author": { "id": 1, "documentId": "p4k39xc7ey2k9puf6xy0ynaq", "username": "anna" } }]
```

Wynik jest płaski, jak w REST v5, ale **nieprzefiltrowany przez uprawnienia**. Document Service to warstwa dostępu do danych: nie wie nic o rolach. `populate: ['author']` bez `fields` zwrócił mi dla Anny pola `password` i `resetPasswordToken`. Gdy zwracasz taki wynik z własnego kontrolera, musisz go zsanityzować – szczegóły w rozdziale 5.

Domyślny `status` to `draft` (Strapi 5.56, październik 2026), więc bez niego czytasz wersje robocze – także dokumentów opublikowanych, bo każdy ma też draft. Dlatego `count({ status: 'draft' })` zwróciło w moim projekcie 13, a `count({ status: 'published' })` – 9. `status` działa tylko w korzeniu zapytania i obowiązuje też dla relacji z `populate`; próba `populate: { category: { status: 'draft' } }` kończy się błędem `Invalid key status at category`. Domyślnie nie jest populowane nic: ani relacje, ani media, komponenty czy dynamic zones.

Przy zapisie `create()` tworzy draft, `publish({ documentId })` kopiuje go do nowej wersji opublikowanej, `unpublish()` ją usuwa, a `discardDraft()` nadpisuje draft treścią opublikowaną. `status: 'published'` w `create()` lub `update()` zapisuje i od razu publikuje. Wersja opublikowana jest tylko do odczytu – edytujesz zawsze draft. Draft & publish i i18n (parametr `locale`) rozwija rozdział 8.

> **Pułapka:** `strictParams: true` w sekcji `documents` pliku `config/api.ts` fundamentu nie odrzuca nieznanych kluczy, wbrew opisowi w dokumentacji. Kod w `node_modules/@strapi/core` po prostu je wycina. Kod przeniesiony ze Strapi 4 z `publicationState: 'live'` przejdzie bez błędu i zwróci… same drafty (u mnie 13 z 13). Błędem kończy się tylko nieprawidłowa wartość znanego parametru, np. `status: 'live'`: `Invalid parameter at 'status'. Expected 'published' or 'draft'`. Po migracji z v4 przeszukaj kod pod kątem `publicationState` i `entityService` – Entity Service API jest w Strapi 5 przestarzałe i zastąpione przez Document Service.

## Query Engine: piętro niżej i czego tam nie ma

Pod Document Service leży Query Engine (`strapi.db.query(uid)`). Operuje na wierszach, nie na dokumentach: używa `where` zamiast `filters`, `select` zamiast `fields`, `orderBy`, `offset` i `limit`, i nie wie nic o draft & publish ani o i18n. Różnicę najlepiej widać na jednym opublikowanym artykule z seeda:

```ts
// strapi.documents(...).findMany({ filters: { slug: ... } }) returns 1 document
await strapi.db.query('api::article.article').findMany({
  where: { slug: 'policies-in-strapi-5' },
  select: ['id', 'documentId', 'publishedAt'],
});
// → [{ id: 1, documentId: 'r8ef...', publishedAt: null },
//    { id: 2, documentId: 'r8ef...', publishedAt: '2026-10-03T18:07:59.255Z' }]
```

Query Engine zwrócił oba wiersze, a jego `count()` policzył w tej samej bazie 20 wierszy artykułów wobec 11 dokumentów. Gdybyś zaktualizował nim tylko wiersz opublikowany, następna publikacja z panelu nadpisałaby zmianę treścią draftu.

Po co więc schodzić niżej? Przede wszystkim po operacje masowe: `createMany`, `updateMany`, `deleteMany`, których Document Service nie ma. Przykład z Redakcji: zadanie porządkowe odrzuca komentarze, które za długo czekają na moderację. Komentarz nie ma draft & publish ani tłumaczeń, więc jeden wiersz to jeden dokument i Query Engine jest tu bezpieczny:

```ts
const { count } = await strapi.db.query('api::comment.comment').updateMany({
  where: { moderationStatus: 'pending', createdAt: { $lt: cutoff } },
  data: { moderationStatus: 'rejected' },
});
// → { count: 2 }
```

Jedno zapytanie `UPDATE` zamiast pętli po dokumentach. Cena: żaden middleware Document Service się nie odpali, nie pójdą zdarzenia `entry.update` do webhooków, a z lifecycle hooków zadziała tylko `beforeUpdateMany`/`afterUpdateMany`, nie `beforeUpdate`. Nie dostaniesz też walidacji ze schematu, którą Document Service robi przy każdym zapisie: Query Engine bez mrugnięcia zapisał mi komentarz z 2500 znakami (limit to 2000) i `moderationStatus: 'nonsense'` spoza enumeracji. Schodź więc niżej dla operacji masowych na typach bez draft & publish i i18n oraz dla tabel technicznych (seed tak nadaje uprawnienia rolom). Jeszcze niżej jest knex (`strapi.db.connection`), gdzie nie działają nawet lifecycle hooki.

## Transakcje: wszystko albo nic

Import z zewnętrznego systemu tworzy kategorię i jej pierwsze artykuły. Bez transakcji błąd walidacji drugiego artykułu (`title must be at most 160 characters`) zostawił mi w bazie osieroconą kategorię. Rozwiązaniem jest `strapi.db.transaction()` – dokumentacja oznacza ją jako funkcję eksperymentalną, ale to ten sam mechanizm, którego Strapi używa wewnętrznie.

```ts
export default factories.createCoreService('api::category.category', ({ strapi }) => ({
  // Imports a category with its first articles: all of them land in the database or none does.
  async importWithArticles(name: string, titles: string[]) {
    return strapi.db.transaction(async ({ onCommit }) => {
      const category = await strapi.documents('api::category.category').create({
        data: { name, slug: name.toLowerCase() },
      });
      for (const title of titles) {
        await strapi.documents('api::article.article').create({
          data: { title, slug: slugify(title), category: category.documentId },
        });
      }
      onCommit(() => strapi.log.info(`Imported ${name} with ${titles.length} article(s)`));
      return category;
    });
  },
}));
```

```text
before: 3
import failed: ValidationError title must be at most 160 characters
after failed import: 3 0
[2026-10-03 20:16:11.964] info: Imported Security with 2 article(s)
after good import: 4
```

Nie przekazujesz obiektu transakcji do `strapi.documents()` ani `strapi.db.query()`. Strapi trzyma go w `AsyncLocalStorage` i każde wywołanie wewnątrz funkcji automatycznie go używa; jawne `.transacting(trx)` jest potrzebne tylko w surowym knexie. Wyjątek cofa wszystko, a `onCommit` uruchamia efekt uboczny dopiero po zatwierdzeniu. Zagnieżdżone `transaction()` dołącza do zewnętrznej.

`slug: slugify(title)` jest tu mimo middleware generującego slug, bo typy ze schematu wymagają `slug` i `tsc` nie przepuści `create()` bez niego. Transakcji nie dodawaj „na wszelki wypadek”: każda metoda Document Service i tak działa we własnej, a długa transakcja trzyma blokady.

## Lifecycle hooks czy middleware Document Service

Strapi daje dwa miejsca, w których możesz zareagować na zapis. Lifecycle hooki (`beforeCreate`, `afterUpdate` itd., w pliku `src/api/article/content-types/article/lifecycles.ts` albo przez `strapi.db.lifecycles.subscribe()`) są częścią warstwy bazy: odpalają się dla każdego **wiersza**, który Query Engine tworzy, zmienia lub usuwa. Middleware Document Service, rejestrowany przez `strapi.documents.use()` w `register()`, owija wywołanie **metody** Document Service: widzi akcję (`create`, `publish`…), uid typu i parametry, zanim cokolwiek trafi do bazy, a po `await next()` – wynik.

W Strapi 5 jedna operacja na dokumencie to kilka operacji na wierszach. Zamiast wierzyć tabeli z dokumentacji, zmierzyłem to.

### Pomiar: ile razy co się odpala

Do projektu dodałem dwa liczniki, oba włączane zmienną `TRACE_ARTICLE_EVENTS=true`. Plik `lifecycles.ts` artykułu podpina jedną funkcję `trace(event: Event)` pod `beforeCreate`, `afterCreate`, `beforeUpdate`, `afterUpdate`, `beforeDelete` i `afterDelete`; loguje akcję, `id` wiersza, wersję (draft czy published) i wynik `strapi.db.inTransaction()`. Middleware Document Service (`src/debug/trace-documents.ts`) loguje każde wywołanie na artykułach przed i po `next()`. Pierwszy test: Anna tworzy artykuł przez REST, `POST /api/articles`. Kontroler REST domyślnie tworzy dokument od razu opublikowany:

```text
[document]  create status=published trx=false
[lifecycle] beforeCreate id=- version=draft trx=true
[lifecycle] afterCreate  id=8 version=draft trx=true
[lifecycle] beforeCreate id=- version=published trx=true
[lifecycle] afterCreate  id=9 version=published trx=true
[document]  create done trx=false
http: POST /api/articles (61 ms) 201
```

Jedno wywołanie Document Service, dwa wiersze, cztery lifecycle hooki. Kolejne testy dały taki obraz (pomijam hooki `find*`, które publikacja też odpala, bo czyta draft z bazy):

| Operacja | Middleware DS | Lifecycle hooki (zapis) |
|---|---|---|
| REST `POST /api/articles` (create + publish) | 1 × `create` | 2 × Create (draft, published) |
| REST `POST ?status=draft` | 1 × `create` | 1 × Create |
| pierwsza publikacja: REST `PUT` | 1 × `update` | 1 × Update (draft) + 1 × Create (published) |
| ponowna publikacja: REST `PUT` | 1 × `update` | 1 × Update + 1 × Delete (stara wersja) + 1 × Create |
| panel: „Publish” | `findOne` ×2, `update`, `publish` | 1 × Update + 1 × Create |

(każde „×1” w ostatniej kolumnie to para `before…` i `after…`). `readingTime` liczony w `beforeCreate` policzy się drugi raz dla kopii, a `afterCreate` wysyłający e-mail „nowy artykuł” wyśle go przy każdej publikacji. Wersja opublikowana dostaje też za każdym razem nowe `id` (u mnie 11, potem 12). Middleware widzi jedną intencję: „utwórz”, „zaktualizuj”, „opublikuj”.

### Middleware Document Service łapie też panel admina

Middleware trasy z rozdziału 4 działa tylko dla Content API; panel ma własne trasy pluginu Content Manager. Sprawdziłem, czy middleware DS je widzi, na dwa sposoby. W `node_modules/@strapi/content-manager/dist/server/services/document-manager.js` każda akcja panelu (create, update, publish, unpublish, discard, delete, clone) woła `strapi.documents(uid)`. Potem zarejestrowałem pierwszego administratora przez `POST /admin/register-admin`, dostałem JWT admina i z curl-a utworzyłem oraz opublikowałem artykuł przez Admin API panelu (`/content-manager/collection-types/api::article.article`):

```text
# after… and "done" lines omitted
[document]  create status=draft trx=false
http: POST /content-manager/collection-types/api::article.article (55 ms) 201
[document]  findOne status=- trx=true
[document]  findOne status=draft trx=true
[document]  update status=draft trx=true
[lifecycle] beforeUpdate id=10 version=draft trx=true
[document]  publish status=- trx=true
[lifecycle] beforeCreate id=- version=published trx=true
http: POST /content-manager/.../gvak.../actions/publish (71 ms) 200
```

Przycisk „Publish” w panelu to w rzeczywistości zapis draftu (`update`) i dopiero potem `publish` – bo formularz wysyła aktualną treść razem z prośbą o publikację. Middleware zobaczył obie operacje, więc reguły z następnej sekcji działają też dla redaktora w panelu. To jest główny argument za middleware Document Service: jedno miejsce dla REST-a, panelu, skryptów i pluginów.

```text
Content API (REST) → middleware → polityki → kontroler → serwis ─┐
Panel (Content Manager) → trasy admina → document-manager ─────────┤
Skrypt, cron, plugin ──────────────────────────────────────────────┤
                                                                   ▼
                    strapi.documents(uid)  ← middleware DS (strapi.documents.use)
                                │
                    Query Engine (strapi.db.query)  ← lifecycle hooki (per wiersz)
                                │
                              baza
```

Lifecycle hooki mają jedną przewagę: łapią też zapisy przez Query Engine. Używaj ich do reakcji na zmianę wiersza (np. audyt techniczny tabeli); regułę biznesową o dokumencie umieszczaj w middleware Document Service. Pełne porównanie z politykami i middleware tras jest w tabeli w rozdziale 4.

## Trzy reguły Redakcji jako middleware

Middleware dostaje `(context, next)`: `context.uid`, `context.action` i `context.params`, które wolno zmieniać przed `next()`. Jest globalny – odpala się dla każdego typu i akcji – więc zaczynasz od warunku i dla reszty od razu zwracasz `next()`. Dokumentacja podkreśla, że wynik `next()` trzeba zwrócić – zgubiony `return` psuje całą aplikację, bo każda metoda zwróci `undefined`. Rejestracja w `src/index.ts`:

```ts
register({ strapi }: { strapi: Core.Strapi }) {
  registerDocumentTrace(strapi);
  strapi.documents.use(articleAuthor(strapi));
  strapi.documents.use(articleDerivedFields(strapi));
  strapi.documents.use(categoryDeleteGuard(strapi));
},
```

Middleware wykonują się w kolejności rejestracji. `register()` gwarantuje, że są na miejscu, zanim jakikolwiek `bootstrap()` zapisze pierwszy dokument.

### Czas czytania i slug

```ts
export const articleDerivedFields = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    if (context.uid !== 'api::article.article') return next();
    if (context.action !== 'create' && context.action !== 'update') return next();

    const data = context.params.data as Record<string, unknown> | undefined;
    if (data) {
      if (Array.isArray(data.content)) {
        data.readingTime = readingTimeOf(data.content as ContentBlock[]);
      }
      if (context.action === 'create' && !data.slug && typeof data.title === 'string') {
        data.slug = await uniqueSlug(strapi, slugify(data.title));
      }
    }
    return next();
  };
};
```

`readingTimeOf` przechodzi po dynamic zone, zlicza słowa w blokach `shared.rich-text` i cytatach i dzieli przez 200 słów na minutę; `uniqueSlug` dokleja `-2`, `-3`, jeśli slug jest zajęty (pełny plik w `examples/`). Czas czytania liczy się tylko wtedy, gdy zapis zawiera `content`, więc aktualizacja samego `excerpt` nie zeruje go. Dwa identyczne żądania REST bez sluga, z tytułem „Łódź meetup: Strapi i Postgres” i treścią o 450 słowach, dostały `lodz-meetup-strapi-i-postgres` i `lodz-meetup-strapi-i-postgres-2`, oba z `readingTime: 3`. Artykuł utworzony w panelu bez sluga dostał `written-in-the-admin-panel`. Slug powstaje tylko przy `create`: zmiana tytułu po publikacji nie zmienia adresu, który ktoś już udostępnił.

### Kategoria z artykułami jest nieusuwalna

```ts
export const categoryDeleteGuard = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    if (context.uid !== 'api::category.category' || context.action !== 'delete') return next();

    const { documentId } = context.params;
    const articles = await strapi.documents('api::article.article').count({
      filters: { category: { documentId } },
    });
    if (articles > 0) {
      throw new errors.ApplicationError(
        `Category has ${articles} article(s). Move them to another category first.`,
        { documentId, articles }
      );
    }
    return next();
  };
};
```

Rzucony błąd z `@strapi/utils` przerywa łańcuch przed `next()`, więc nic nie zostaje usunięte. `DELETE` kategorii Backend przez Admin API panelu (rola Authenticated nie ma prawa usuwać kategorii) zwrócił 400 z `"name": "ApplicationError"`, komunikatem `Category has 2 article(s)...` i `details: { documentId, articles: 2 }`. Pusta kategoria usuwa się normalnie (200). Masowe usuwanie w Content Managerze też woła `delete` dla każdego dokumentu (w jednej transakcji), więc blokada działa i tam. Polityka z rozdziału 4 nie dałaby tego efektu: chroniłaby tylko trasę `DELETE /api/categories/:id`.

### Autor z kontekstu żądania

Middleware Document Service nie dostaje `ctx` Koa, ale Strapi trzyma bieżące żądanie w `strapi.requestContext` (to również `AsyncLocalStorage`). Stamtąd bierzesz zalogowanego użytkownika:

```ts
type AuthState = { auth?: { strategy?: { name?: string } }; user?: { id: number } };

export const articleAuthor = (strapi: Core.Strapi): Modules.Documents.Middleware.Middleware => {
  return async (context, next) => {
    if (context.uid !== 'api::article.article' || context.action !== 'create') return next();

    // Only Content API users are article authors; admin panel users are a different table.
    const state = strapi.requestContext.get()?.state as AuthState | undefined;
    if (state?.auth?.strategy?.name === 'users-permissions' && state.user) {
      const data = context.params.data as Record<string, unknown>;
      data.author = state.user.id;
    }
    return next();
  };
};
```

Sprawdzenie strategii jest kluczowe. W panelu `ctx.state.user` to administrator z tabeli `admin_users`, a relacja `author` wskazuje na `plugin::users-permissions.user`; przypisanie jego `id` podpięłoby artykuł do przypadkowego użytkownika aplikacji o tym samym numerze. W skrypcie albo cronie `requestContext.get()` zwraca `undefined`. Po utworzeniu artykułu przez Annę oba wiersze mają w `articles_author_lnk` jej identyfikator. Przysłanie `"author": 2` w body REST i tak kończy się błędem `Invalid key author` (Authenticated nie ma uprawnień do typu użytkownika), więc dla REST-a middleware to druga linia obrony. Ustawienie autora w kontrolerze (rozdział 5) zadziała tylko dla jednej trasy.

## Pułapki: rekurencja i transakcja, w której siedzi hook

Najczęstszy błąd to zapis przez Document Service do tego samego typu i akcji, którą middleware obsługuje – np. „dopisanie” `readingTime` osobnym `update()`. Uruchomiłem taki kod w `npm run console`, z bezpiecznikiem po pięciu wywołaniach:

```ts
strapi.documents.use(async (context, next) => {
  if (context.uid === 'api::article.article' && context.action === 'update') {
    console.log(`update middleware, call #${++calls}`);
    if (calls > 5) throw new Error('safety stop after 5 nested updates');
    // wrong: writing through the Document Service re-enters this middleware
    await strapi.documents(context.uid).update({ documentId: context.params.documentId, data: { readingTime: 5 } });
  }
  return next();
});
```

```text
update middleware, call #1
update middleware, call #2
...
update middleware, call #6
error: safety stop after 5 nested updates
```

> **Pułapka:** zapis z wnętrza middleware do tej samej akcji tego samego typu wpada w nieskończoną rekurencję – bez bezpiecznika żądanie wisi, aż skończy się stos. Zmieniaj `context.params.data` przed `next()` zamiast robić drugi zapis. Odczyty (`count`, `findFirst`) i zapisy do innych typów są bezpieczne, o ile ich middleware nie wraca do pierwszego typu. To samo dotyczy lifecycle hooków: `afterUpdate`, który woła `strapi.documents().update()` na tym samym artykule, odpala `afterUpdate` ponownie.

Druga rzecz widoczna w logach to kolumna `trx`. Lifecycle hooki zawsze mają `trx=true`: działają wewnątrz transakcji, którą Document Service otwiera dla każdej metody. Middleware przed `next()` i po nim, przy wywołaniu z REST, ma `trx=false`. Panel jest inny: akcja „Publish” opakowuje `update` i `publish` we własną transakcję, więc tam middleware też ma `trx=true`.

> **Pułapka:** `afterCreate` wywołuje się przed zatwierdzeniem transakcji. Wysłany stamtąd e-mail czy żądanie do frontendu może dotyczyć danych, których jeszcze nie ma, a wyjątek w hooku cofa cały zapis – sprawdziłem: rzucenie błędu w `afterCreate` wersji opublikowanej nie zostawiło w bazie nawet draftu. Efekty uboczne przenieś do middleware Document Service za `await next()` albo zarejestruj je przez `onCommit` we własnej transakcji. Do odświeżania cache po publikacji służą też webhooki `entry.publish` (rozdziały 8 i 11).

## Podsumowanie

- Document Service (`strapi.documents(uid)`) pracuje na dokumentach z `documentId`; `status` (domyślnie `draft`) i `locale` wybierają wersję, a nic nie jest populowane domyślnie.
- Wynik Document Service nie jest sanityzowany – z własnego kontrolera zwracaj go dopiero po sanityzacji z rozdziału 5.
- Query Engine (`strapi.db.query`) widzi wiersze: draft i wersję opublikowaną osobno, bez middleware DS, webhooków i walidacji. Używaj go do operacji masowych na typach bez draft & publish i do tabel technicznych.
- `strapi.db.transaction()` spina kilka zapisów w całość bez przekazywania obiektu transakcji; efekty uboczne odkładaj do `onCommit`.
- Lifecycle hooki odpalają się per wiersz: utworzenie opublikowanego artykułu to cztery hooki, ponowna publikacja – sześć, a wersja opublikowana za każdym razem dostaje nowe `id`.
- Middleware Document Service (`strapi.documents.use()` w `register()`) odpala się raz na operację i łapie REST, panel admina i skrypty.
- W middleware zmieniaj `context.params` przed `next()`, zawsze zwracaj wynik `next()` i nie zapisuj do tej samej akcji tego samego typu.
- `publicationState` i `entityService` to relikty Strapi 4; to pierwsze jest po cichu ignorowane.

## Co dalej

Masz już komplet miejsc na logikę po stronie serwera: trasy, polityki i middleware z rozdziału 4, kontrolery i serwisy z rozdziału 5 oraz Document Service z tego rozdziału. W rozdziale 7 zajmiesz się tym, kim jest `state.user`, z którego korzystał middleware autora: użytkownikami aplikacji, tokenami z odświeżaniem i uprawnieniami ról, a także tym, jak filtrować listy po właścicielu – również w middleware Document Service.

## Źródła

- https://docs.strapi.io/cms/api/document-service
- https://docs.strapi.io/cms/api/document-service/status
- https://docs.strapi.io/cms/api/document-service/populate
- https://docs.strapi.io/cms/api/document-service/sort-pagination
- https://docs.strapi.io/cms/api/document-service/middlewares
- https://docs.strapi.io/cms/api/query-engine
- https://docs.strapi.io/cms/api/query-engine/bulk-operations
- https://docs.strapi.io/cms/database-transactions
- https://docs.strapi.io/cms/backend-customization/models (sekcja „Lifecycle hooks”)
- https://docs.strapi.io/cms/migration/v4-to-v5/breaking-changes/lifecycle-hooks-document-service
- https://docs.strapi.io/cms/configurations/api
