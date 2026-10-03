# Rozdział 2. Modelowanie treści

> **Cel rozdziału:** zrozumieć, jak `schema.json` zamienia się w tabele i odpowiedzi API, żeby projektować typy treści świadomie: wybierać między komponentem, relacją i dynamic zone oraz wiedzieć, co zmiana schematu robi z istniejącymi danymi.
>
> **Kod:** `examples/02-modelowanie-tresci/`. **Pakiety poza fundamentem:** brak.

W Redakcji model danych powstał w kilkanaście minut w Content-Type Builderze i od tamtej pory działa. Problem zaczyna się przy pierwszej zmianie: ktoś chce przemianować `excerpt` na `lead`, ktoś inny dodać do komentarza pole `status`, a frontendowiec pyta, dlaczego po edycji artykułu jego `id` się zmieniło. Odpowiedzi na te pytania nie ma w panelu. Leżą w plikach `schema.json` i w tym, co Strapi 5 robi z nimi w bazie.

Ten rozdział czyta schematy fundamentu linijka po linijce i tłumaczy, dlaczego wyglądają tak, a nie inaczej. Potem schodzi do bazy SQLite i pokazuje, że jeden dokument to dwa wiersze, a przemianowanie pola potrafi po cichu skasować dane. Zapytania REST (`populate`, `filters`) opisuje rozdział 3, a zapisy przez Document Service rozdział 6; tutaj interesuje nas kształt danych.

## Schemat od środka

Typ treści to katalog `src/api/<nazwa>/content-types/<nazwa>/` z jednym plikiem `schema.json`. Strapi czyta go przy starcie, buduje z niego model bazy, trasy i uprawnienia, a w trybie developerskim generuje też typy TypeScript. Panel (Content-Type Builder) jest tylko edytorem tych plików. Oto komentarz (comment) z fundamentu, w skrócie:

```json
{
  "kind": "collectionType",
  "collectionName": "comments",
  "info": { "singularName": "comment", "pluralName": "comments", "displayName": "Comment" },
  "options": { "draftAndPublish": false },
  "attributes": {
    "body": { "type": "text", "required": true, "maxLength": 2000 },
    "moderationStatus": {
      "type": "enumeration",
      "enum": ["pending", "approved", "rejected"],
      "default": "pending",
      "required": true
    },
    "article": { "type": "relation", "relation": "manyToOne", "target": "api::article.article", "inversedBy": "comments" },
    "author": { "type": "relation", "relation": "manyToOne", "target": "plugin::users-permissions.user" }
  }
}
```

`kind` wybiera między kolekcją (`collectionType`, wiele dokumentów) a pojedynczym typem (`singleType`, dokładnie jeden, jak `global` z ustawieniami strony). `singularName` i `pluralName` wyznaczają adresy (`/api/comments`) i UID `api::comment.comment`, a `collectionName` nazwę tabeli. Wartości `required`, `maxLength`, `min`, `unique` i `default` są walidacjami na poziomie schematu, więc obowiązują każde wejście: REST, panel i kod serwera. Sprawdź, jak wyglądają z zewnątrz:

```text
$ curl -X POST localhost:1302/api/comments -H "authorization: Bearer eyJhbGciOi..." \
    -d '{"data":{"body":"hi","moderationStatus":"spam"}}'
400 ValidationError: moderationStatus must be one of the following values: pending, approved, rejected
```

Enumeracja odrzuca wartość spoza listy, a `default: "pending"` sprawia, że komentarz bez tego pola trafia do kolejki moderacji. Dlatego pole nazywa się `moderationStatus`, a nie `status`. W Strapi 5 `status` jest parametrem zapytania (`?status=draft`) i argumentem Document Service, więc nazwa jest zarezerwowana. Obok niej lista zawiera między innymi `meta`, `locale`, `localizations`, `document`, `entryId` i wszystko z przedrostkiem `strapi`.

> **Pułapka:** zarezerwowane nazwy pilnuje Content-Type Builder, nie sam serwer. Gdy dopiszesz `status` do `schema.json` artykułu ręcznie, Strapi 5.56 wystartuje i tylko ostrzeże w logu: „The attribute name 'status' on content type 'api::article.article' is reserved when 'draftAndPublish' is enabled”. Kolumna powstanie, ale w żądaniach `?status=` i `filters[status]` pole i parametr zaczną się mylić. Dokumentacja opisuje tę regułę jako błąd w panelu, a zachowanie serwera jest łagodniejsze, więc w kodzie nie masz siatki bezpieczeństwa. Nazwę `meta` serwer przyjął u mnie bez słowa, mimo że lista ją zabrania. Nazywaj pola od razu inaczej: `moderationStatus`, `approvalState`.

Kilka typów pól wymaga komentarza. `uid` z `targetField: "title"` to unikalny, przyjazny adresom identyfikator, ale generuje go panel, nie API. Wysłany przez REST artykuł bez `slug` dostaje 400 (`slug must be a string type, but the final value was: null`), bo pole jest `required`. Automatyczny slug po stronie serwera to temat rozdziału 6. `blocks` to edytor z blokami w JSON-ie (akapity, nagłówki, listy), który frontend musi samodzielnie wyrenderować; `richtext` to starszy Markdown w jednym polu tekstowym. Pole `media` przechowuje relację do pliku z biblioteki mediów, a `allowedTypes` zawęża je do obrazów, wideo albo plików. Wreszcie `private: true` usuwa atrybut z każdej odpowiedzi API, co przydaje się przy danych wewnętrznych.

## Komponent, relacja czy dynamic zone

Fundament używa wszystkich trzech sposobów łączenia danych i warto wiedzieć, dlaczego w tych miejscach. **Komponent** (component) to nazwana grupa pól bez własnej tożsamości: `shared.seo` ma `metaTitle`, `metaDescription` i `shareImage`, a artykuł zawiera dokładnie jedną jego kopię. Nie ma własnego adresu API ani uprawnień, nie da się go współdzielić między artykułami (każdy ma swoją kopię), za to jest tani w odczycie i edytuje się go razem z rodzicem. **Relacja** (relation) wskazuje na osobny dokument z własnym `documentId`, który żyje niezależnie: kategoria istnieje, nawet gdy nie ma w niej artykułów, i można ją edytować w jednym miejscu. **Dynamic zone** to uporządkowana lista komponentów różnych typów.

Reguła kciuka: jeśli dane należą tylko do jednego rodzica i nie potrzebujesz ich wyszukiwać ani chronić osobno, użyj komponentu; jeśli wiele rekordów ma je współdzielić albo rola ma mieć do nich osobne uprawnienia, użyj relacji. Dlatego SEO jest komponentem, a kategoria i komentarz są relacjami.

Pole `content` artykułu to dynamic zone z trzema komponentami: `shared.rich-text`, `shared.quote` i `shared.media`. Można było zrobić jedno pole `blocks`, ale `blocks` ogranicza się do tego, co umie edytor. Dynamic zone pozwala redaktorowi ułożyć tekst, cytat i obraz w dowolnej kolejności, a frontend przełącza się po `__component`. Cena jest realna. Komponenty trafiają do osobnych tabel, a kolejność trzyma tabela łącząca; sprawdź ją w bazie:

```text
articles_cmps
 entity_id  cmp_id  component_type      field    order
 1          1       shared.rich-text    content  1
 1          1       shared.quote        content  2
 1          1       shared.seo          seo      null
```

Każdy typ komponentu w dynamic zone to dodatkowe złączenie przy `populate`, a odpowiedź ma strukturę, którą frontend musi rozpoznać po `__component`. Głębokie populate dynamic zone opisuje rozdział 3. Dla treści o stałym kształcie (tytuł, lead, okładka) dynamic zone to przesada; zostaw ją dla ciała artykułu.

Ostatni wybór: kategorie nie mają Draft & Publish (`draftAndPublish: false`), bo to słownik, który nie wymaga szkiców. Komentarze też nie: moderacja ma własne pole stanu, a nie dwie wersje dokumentu.

## Relacje i użytkownik

Relacja ma właściciela. Strona z `inversedBy` jest właścicielem (komentarz wskazuje artykuł), a strona z `mappedBy` jedynie odbija ją z drugiej strony (artykuł zbiera swoje komentarze). Do wyboru jest pięć rodzajów: `oneToOne`, `oneToMany`, `manyToOne`, `manyToMany` i `oneWay` (bez drugiej strony). Fundament używa `manyToOne` / `oneToMany` dla pary artykuł–komentarz i artykuł–kategoria.

`author` jest inny, bo celem jest `plugin::users-permissions.user`, czyli typ treści z pluginu. Pole nie ma `inversedBy`, więc użytkownik nie dostaje listy swoich artykułów; to relacja jednokierunkowa w sensie modelu, choć zapisana jako `manyToOne`. Autor jest użytkownikiem aplikacji (rozdział 7), a nie kontem panelu admina, i dlatego komentarz może dostać autora z JWT bez żadnego mapowania. Konsekwencja: odpowiedź z populate `author` zawiera wszystkie pola użytkownika, jeśli nie przejdzie przez sanityzację (rozdział 5 pokazuje, jak łatwo wyciekają e-mail i hash hasła).

## Dokument i jego wersje

W Strapi 5 wpis w panelu to **dokument** (document): jeden `documentId` i do kilku wierszy w bazie, po jednym na wersję. Artykuł z włączonym Draft & Publish ma wiersz szkicu (`published_at IS NULL`) i wiersz opublikowany; z i18n dochodzi jeszcze wiersz na każdy język. Zajrzyj do bazy świeżo zasianego projektu (`.tmp/data.db`, tabela `articles`):

```text
id  document_id                 title                          published
1   aku2wykoymjqm3e7amenfjxp    Policies in Strapi 5           0
2   aku2wykoymjqm3e7amenfjxp    Policies in Strapi 5           1
3   pw48hejujtw1vtmoh4579pa9    Document Service middlewares   0
4   pw48hejujtw1vtmoh4579pa9    Document Service middlewares   1
...
7   (czwarty artykuł)           Self-hosting Strapi with Docker 0
```

Cztery artykuły dają siedem wierszy, bo czwarty nigdy nie został opublikowany. Relacje i komponenty są kopiowane per wersja: tabela `articles_category_lnk` ma osobny wiersz łączący dla szkicu (`article_id = 1`) i dla opublikowanej wersji (`article_id = 2`), a komponent `shared.seo` osobne wiersze dla obu. Dlatego draft i published mogą mieć różne relacje, a dwa artykuły nie dzielą komponentu.

Trzeba też wiedzieć, jakie zachowanie widzi klient. REST domyślnie zwraca wersję opublikowaną, a `?status=draft` szkic. Ta sama odpowiedź ma w obu przypadkach ten sam `documentId` i różne `id`:

```text
GET /api/articles?status=published&fields[0]=title   →  id 2, 4, 6
GET /api/articles?status=draft&fields[0]=title       →  id 1, 3, 5, 7
GET /api/articles/aku2wykoymjqm3e7amenfjxp           →  200 (documentId)
GET /api/articles/2                                  →  404 NotFound
```

Adres z numerycznym `id` w Strapi 5 nie istnieje, a pod `documentId` odpowiada wersja zależna od `status`. Rozstrzyga to zapis. Po `PUT` na artykuł (jako `anna`) opublikowany wiersz dostał **nowy** `id`:

```text
PUT /api/articles/aku2wykoymjqm3e7amenfjxp  {"data":{"title":"Policies in Strapi 5, revised"}}
id  document_id                 title                           published
1   aku2wykoymjqm3e7amenfjxp    Policies in Strapi 5, revised   0
8   aku2wykoymjqm3e7amenfjxp    Policies in Strapi 5, revised   1
```

> **Pułapka:** numeryczne `id` w Strapi 5 nie jest trwałym kluczem. Opublikowana wersja zmieniła `id` z 2 na 8 po zwykłej edycji, a `id` komponentów w szkicu i w wersji opublikowanej też są różne. Do tożsamości używaj wyłącznie `documentId`, także w kluczach cache i w relacjach po stronie frontendu. `id` zostaje wewnętrzną sprawą bazy. Pamiętaj też, że `PUT` na dokumencie z Draft & Publish w REST zmienił obie wersje naraz; sterowanie nimi osobno opisuje rozdział 8.

Przy okazji zwróć uwagę na jedną rzecz z seeda: żądanie anonimowe z `?status=draft` zwróciło szkice, w tym artykuł, który nigdy nie został opublikowany. Uprawnienie `find` roli Public otwiera oba parametry, więc szkice są publiczne, dopóki nie zablokujesz ich polityką albo middleware (rozdział 4). Komentarze, które nie mają Draft & Publish, mają w bazie jeden wiersz i `published_at` ustawione na datę utworzenia.

## Panel w developmentcie, pliki w produkcji

Content-Type Builder działa tylko w trybie developerskim (`strapi develop`). W produkcji (`strapi start`) jest wyłączony, co jest zamierzone: schemat to kod, który wchodzi do repozytorium, przechodzi review i jedzie obrazem Dockera. Zmiana typu w panelu na serwerze produkcyjnym nie miałaby gdzie się zapisać, bo pliki w kontenerze znikają przy redeployu. Praca wygląda więc tak: edytujesz model lokalnie (panelem albo plikiem), commitujesz `schema.json` razem z kodem, a produkcja po starcie sama dopasowuje bazę. Podział na środowiska opisuje rozdział 13.

Panel generuje także `types/generated/contentTypes.d.ts` z typami takimi jak `ApiCommentComment`. Dzięki nim `strapi.documents('api::comment.comment')` wie, jakie pola istnieją. Generowanie i użycie typów opisuje rozdział 12; tu wystarczy wiedza, że plik odświeża się przy zmianie schematu i warto go commitować.

## Zmiana schematu a dane

To najważniejsza praktyczna wiedza o modelu. Przy każdym starcie Strapi porównuje schematy z bazą i **synchronizuje** ją: dodaje nowe kolumny i tabele, a tabele i kolumny, których już nie ma w schematach, usuwa. Bez ostrzeżenia i bez pytania, w developmencie i w produkcji tak samo. Zmiana nazwy pola dla Strapi to więc usunięcie jednego pola i dodanie drugiego.

Sprawdź to. Przemianuj w `schema.json` artykułu `excerpt` na `lead` i uruchom serwer:

```text
$ sed -i 's/"excerpt"/"lead"/' src/api/article/content-types/article/schema.json
$ strapi develop ...
articles columns: id, document_id, title, slug, reading_time, ..., locale, lead
GET /api/articles?fields[0]=lead  →  "lead": null
```

Kolumna `excerpt` zniknęła razem z treścią wszystkich leadów, a `lead` powstała pusta. Log startowy nie zawierał żadnego ostrzeżenia.

> **Pułapka:** zmiana nazwy pola w panelu albo w pliku kasuje dane przy następnym starcie, na każdym środowisku, które dostanie ten kod. Najgorzej, gdy zmiana jedzie na produkcję w zwykłym wdrożeniu. Przed zmianą nazwy zrób kopię bazy, a samą zmianę przeprowadź migracją.

Migracje trzymasz w `database/migrations/`. To pliki JavaScript nazwane datą (kolejność alfabetyczna to kolejność wykonania), każdy z funkcją `up(knex)`, uruchamiane raz, **przed** synchronizacją schematu. Dzięki temu migracja widzi jeszcze starą kolumnę:

```js
// database/migrations/2026.10.03T12.00.00.rename-article-excerpt-to-lead.js
'use strict';

// Runs before the schema sync, so it still sees the old `excerpt` column.
async function up(knex) {
  const hasOld = await knex.schema.hasColumn('articles', 'excerpt');
  const hasNew = await knex.schema.hasColumn('articles', 'lead');
  if (hasOld && !hasNew) {
    await knex.schema.alterTable('articles', (table) => {
      table.renameColumn('excerpt', 'lead');
    });
  }
}

module.exports = { up };
```

Po przywróceniu bazy sprzed eksperymentu log pokazał `migrating 2026.10.03T12.00.00.rename-article-excerpt-to-lead.js`, a po starcie `lead` zawierała oryginalne teksty (`A short introduction to policies in strapi 5.`). Funkcja `up` działa w transakcji, więc błąd wycofuje całą migrację. Dokumentacja oznacza mechanizm jako eksperymentalny i zaznacza, że nie ma migracji w dół, więc cofnięcie robisz ręcznie. Strategię migracji na produkcji, kopie zapasowe i `forceMigration` omawia rozdział 13.

## Podsumowanie

- `schema.json` jest źródłem prawdy: z niego powstają tabele, trasy i typy. Panel to tylko edytor, a w produkcji jest wyłączony, więc zmiany modelu przechodzą przez repozytorium.
- Walidacje (`required`, `maxLength`, `min`, enum, `default`) w schemacie obowiązują każde wejście. Pole `uid` generuje panel, API wymaga podania wartości.
- Nazwy `status`, `meta`, `locale`, `document` i przedrostek `strapi` są zarezerwowane. Serwer ich w plikach nie blokuje (najwyżej ostrzega), więc pilnuj tego sam i nazywaj pola jak `moderationStatus`.
- Komponent dla danych jednego rodzica (SEO), relacja dla rekordów żyjących własnym życiem (kategoria, komentarz), dynamic zone dla elastycznej listy bloków, ale z kosztem złączeń i populate.
- `inversedBy` oznacza stronę właściciela relacji, `mappedBy` stronę odbitą. Relacja do `plugin::users-permissions.user` bywa jednokierunkowa, a jej populate wymaga sanityzacji.
- Dokument to jeden `documentId` i wiele wierszy: szkic, wersja opublikowana, locale. `id` zmienia się przy edycji, więc tożsamością jest `documentId`.
- Zmiana nazwy pola kasuje dane przy starcie. Chroni przed tym migracja w `database/migrations/` uruchamiana przed synchronizacją schematu.

## Co dalej

Masz model, który wiesz, jak czytać i bezpiecznie zmieniać. Rozdział 3 pokazuje, jak klient pobiera te dane przez REST i GraphQL: `populate` dynamic zone, `filters` po relacji i paginację. Do tego czasu możesz sprawdzić własny projekt: zajrzyj do tabel w bazie i policz, ile wierszy ma każdy dokument, oraz zastanów się, które pola w Twoich schematach wymagają migracji, zanim ktoś je przemianuje.

## Źródła

- https://docs.strapi.io/cms/backend-customization/models
- https://docs.strapi.io/cms/features/content-type-builder
- https://docs.strapi.io/cms/api/document
- https://docs.strapi.io/cms/migration/v4-to-v5/breaking-changes/attributes-and-content-types-names-reserved
- https://docs.strapi.io/cms/migration/v4-to-v5/breaking-changes/reserved-attributes-status
- https://docs.strapi.io/cms/migration/v4-to-v5/breaking-changes/use-document-id
- https://docs.strapi.io/cms/database-migrations
