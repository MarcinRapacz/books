# Brief dla autorów rozdziałów – „Strapi 5 od środka”

Książka: **„Strapi 5 od środka. Praktyczny przewodnik dewelopera”**. Samodzielna pozycja, nie część serii AI. Zasady języka i typografii są wspólne z `books/ai-engineer/BRIEF.md` (sekcja „Język i styl”), ale wszystko inne jest opisane tutaj. Nie czytaj pozostałych plików z `books/ai-engineer/` ani z `books/rag-w-produkcji/`.

## Odbiorca i cel

Programista full-stack, który ma kilka działających aplikacji na Strapi 5 (TypeScript, self-hosted na Dockerze, Postgres w produkcji), ale nauczył się go „z panelu i z tutoriali”. Zna Content-Type Builder, REST, users-permissions na poziomie klikania. Ma luki w tym, co dzieje się pod spodem: cykl życia żądania, polityki, middleware, Document Service, rozszerzanie pluginów, testy, produkcja. Po lekturze ma rozumieć, **gdzie w Strapi umieścić daną logikę i dlaczego właśnie tam**, i umieć to napisać.

Płatne funkcje (Strapi Cloud, plany Growth/Enterprise: Releases, Review Workflows, Content History, SSO, Audit Logs itd.) są poza zakresem. Wolno o nich wspomnieć jednym zdaniem, jeśli czytelnik może na nie trafić w dokumentacji, z informacją, że wymagają licencji. Nie opisujemy ich działania.

## Ton (najważniejsze)

Proza, która tłumaczy, a nie suchy katalog API. Autor serii powiedział o poprzedniej książce: „wolę prostsze podejście, które tłumaczy, niż suche laboratorium, które odrzuci po pięciu stronach”. W praktyce:

- Każdy mechanizm w stałym rytmie: **po co** (jaki problem rozwiązuje, na przykładzie z projektu przewodniego) → **jak działa** (2–4 zdania, intuicja przed szczegółem) → **kod** → **co się stało** (akapit po snippecie) → **kiedy tak, kiedy nie** (1–2 zdania, często porównanie z alternatywą: polityka czy middleware, lifecycle czy middleware Document Service).
- Przykłady z życia aplikacji, nie „foo/bar”: autor edytuje tylko swoje artykuły, komentarze czekają na moderację, slug generuje się sam, frontend odświeża cache po publikacji.
- Pułapki i „dlaczego to nie działa” są cenniejsze niż kolejna opcja konfiguracji. Ramka `> **Pułapka:** ...` tam, gdzie dokumentacja albo praktyka pokazuje typowy błąd (maksymalnie 2–3 na rozdział).
- Akapity 3–6 zdań, jedna myśl. Druga osoba liczby pojedynczej. Bez marketingu, bez „w tej sekcji omówimy”, bez emoji. Półpauza „–”, nie dywiz. Cudzysłowy „tak”.
- Terminy: angielski przy pierwszym użyciu w nawiasie, potem po polsku, jeśli istnieje naturalne tłumaczenie (polityka, middleware zostaje middleware, kontroler, serwis, trasa). Nazwy z API (Document Service, Query Engine, `documentId`) zostają oryginalne.

## Projekt przewodni: „Redakcja”

Magazyn technologiczny pisany przez wielu autorów. Fundament leży w `books/strapi-5/code/` (Strapi 5.56.0, TypeScript, SQLite, npm). **Przeczytaj go przed pisaniem**: `src/api/*/content-types/*/schema.json`, `src/components/shared/*.json`, `scripts/seed.js`, `config/*.ts`.

- `api::article.article` – draft & publish; `title`, `slug` (uid), `excerpt`, `cover` (media), `content` (dynamic zone: `shared.rich-text`, `shared.quote`, `shared.media`), `seo` (komponent `shared.seo`), `readingTime` (integer, do wyliczania), `category` (manyToOne), `author` (manyToOne → `plugin::users-permissions.user`), `comments` (oneToMany).
- `api::category.category` – bez D&P; `name`, `slug`, `description`, `articles`.
- `api::comment.comment` – bez D&P; `body`, `moderationStatus` (`pending|approved|rejected`), `article`, `author` (user).
- `api::global.global` – single type; `siteName`, `siteDescription`, `defaultSeo`.
- Seed (`npm run seed`): kategorie Backend/Frontend/DevOps, 4 artykuły (3 opublikowane), użytkownicy `anna` i `piotr` (hasło `Passw0rd!`, rola Authenticated), uprawnienia Public: find/findOne na artykułach, kategoriach, komentarzach i global; Authenticated dodatkowo create/update/delete artykułów i create komentarzy. Celowo bez polityk – ich dodanie to praca rozdziałów.

## Jak pracujesz z kodem (obowiązkowe)

Każdy snippet, który da się uruchomić, uruchamiasz. Nie zgadujesz API.

1. **Własna kopia projektu.** Nie edytuj `books/strapi-5/code/`. Zrób kopię: `cp -a books/strapi-5/code books/strapi-5/work/chNN` (NN = numer rozdziału; `work/` jest ignorowany przez git). W kopii możesz wszystko, łącznie z `npm install` dodatkowych pakietów.
2. **Własny port.** Uruchamiaj z `PORT=13NN` (np. rozdział 4 → `13NN` = 1304), żeby nie kolidować z innymi agentami. Tryb samego API (szybki, bez panelu): `PORT=1304 node_modules/.bin/strapi develop --no-watch-admin --no-build-admin` (panel zwraca wtedy błąd – to normalne). Pełny tryb z panelem (tylko rozdziały 9 i 10): `PORT=13NN node_modules/.bin/strapi develop`. Fundament ma `autoOpen: false` w `config/admin.ts` – nie zmieniaj tego, inaczej każdy start otwiera przeglądarkę użytkownika.
3. **Uruchamiaj w tle i sprzątaj.** Start bezpośrednio przez `node_modules/.bin/strapi` (nie przez `npx` – wtedy `$!` łapie PID `npx`, a nie serwera): `nohup env PORT=13NN node_modules/.bin/strapi develop --no-watch-admin --no-build-admin > dev.log 2>&1 & echo $! > dev.pid`, czekaj na `curl -s -o /dev/null -w '%{http_code}' localhost:13NN/_health` = 204. Stop: `pkill -P $(cat dev.pid); kill $(cat dev.pid)`, potem `ss -ltnp | grep 13NN` musi być puste (jeśli nie, zabij PID z `ss` po sprawdzeniu w `ps`, że to twój proces z `work/chNN`). **Nigdy `pkill -f` z wzorcem** – zabija też twoją własną powłokę. Nie zostawiaj serwera po skończonej pracy. Jedna instancja Strapi na agenta naraz.
4. **Świeża baza:** `rm -f .tmp/data.db && npm run seed` (serwer musi być zatrzymany).
5. **Weryfikacja:** curl z wynikami (pokazuj w książce prawdziwe odpowiedzi, skrócone do istoty, jako blok ```text albo ```json), testy (rozdział 12 ustala sposób), `npx tsc --noEmit -p .` dla kodu TS. Wynik, którego nie uruchomiłeś (np. wysyłka maila, S3, prawdziwy deploy), oznaczasz zdaniem „Przykładowy wynik:” i mówisz w prozie, czego nie dało się sprawdzić lokalnie.
6. **Kod do repo:** pliki, które twój rozdział tworzy lub zmienia, kopiujesz na koniec do `books/strapi-5/examples/NN-slug/` z zachowaniem ścieżek projektu (np. `examples/04-routes-policies-middlewares/src/policies/is-owner.ts`) plus `README.md` (3–10 linii: co skopiować do projektu fundamentu, jakie pakiety doinstalować, jak sprawdzić curl-em). Snippet w książce to istota (10–40 linii); pełny plik jest w `examples/`.
7. **Bez sekretów:** nie czytaj ani nie wypisuj `.env*`. Tokenów JWT i API nie wklejaj w całości do książki ani do raportu – skracaj do `eyJhbGciOi...`.

Kod: TypeScript (warianty `.ts` z dokumentacji), identyfikatory i komentarze po angielsku, importy typów `import type { Core } from '@strapi/strapi'`. Bez `any` tam, gdzie da się podać typ. Snippet bez `...` w środku kodu, chyba że to jawny skrót istniejącego pliku poprzedzony komentarzem `// rest of the file unchanged`.

## Research (obowiązkowy, przed pisaniem)

Źródłem prawdy jest **aktualna** dokumentacja Strapi 5 (stan: październik 2026, Strapi 5.56.0) i kod w `node_modules/@strapi/*` twojej kopii.

- Indeks wszystkich stron: `https://docs.strapi.io/llms.txt` (kopia: `books/strapi-5/research/llms.txt`). Grepuj go po swoim temacie, potem pobieraj strony w Markdown, dopisując `.md` do URL-a, np. `curl -s https://docs.strapi.io/cms/backend-customization/policies.md`.
- `llms-full.txt` (2,4 MB) – nigdy w całości do kontekstu, tylko grep.
- Ścieżki dokumentacji są pod `/cms/` (stare `/dev-docs/` nie istnieją). Uważaj na treści z Strapi 4 (blogi, odpowiedzi na forach, `entityService`, `attributes` w odpowiedzi, `publicationState`) – nie przenoś ich do książki.
- Gdy dokumentacja jest niejasna, rozstrzyga zachowanie uruchomionego projektu i kod w `node_modules`. Rozbieżność docs ↔ zachowanie to dobry materiał na ramkę „Pułapka”.
- Liczby i wartości domyślne (limity, czasy życia tokenów, domyślny `pageSize`) podawaj tylko sprawdzone, z dopiskiem „(Strapi 5.56, październik 2026)” przy pierwszym wystąpieniu w rozdziale.

## Struktura pliku rozdziału

Plik `chapters/NN-slug.md`, zaczyna się od `# Rozdział N. Tytuł`, potem blok:

```
> **Cel rozdziału:** jedno zdanie.
>
> **Kod:** `examples/NN-slug/`. **Pakiety poza fundamentem:** `npm install ...` albo „brak”.
```

Dalej 2–3 akapity wprowadzenia z problemem z projektu przewodniego, sekcje `##` (nagłówki do `###`, bez ręcznej numeracji), na końcu `## Podsumowanie` (5–8 punktów), `## Co dalej` (jeden akapit), `## Źródła` (URL-e oficjalnej dokumentacji Strapi, z których korzystałeś; bez blogów).

Odwołania między rozdziałami: „rozdział 4” wg numeracji z `PLAN.md`. Nie tłumacz od nowa tematu, który ma własny rozdział – odeślij jednym zdaniem.

Diagramy: proste, jako blok ```text z ASCII (strzałki `→`, ramki z `+--+`), maks. 15 linii. Jeden–dwa na rozdział, tylko gdy pokazują przepływ (np. kolejność middleware → polityk → kontrolera).

## Objętość

Około 400 słów prozy albo 45 linii kodu na stronę. Docelowe strony w `PLAN.md`, ±20%.

## Czego nie robić

- Nie wymyślaj API, opcji konfiguracji ani nazw hooków. Każde wywołanie z kodu albo uruchomione, albo sprawdzone w docs/`node_modules`.
- Nie przepisuj dokumentacji. Książka wybiera, porządkuje i tłumaczy, kiedy czego użyć.
- Nie twórz plików poza: swoim rozdziałem, `work/chNN/`, `examples/NN-slug/`. Nie edytuj `PLAN.md`, `BRIEF.md`, `code/`.

## Raport końcowy agenta

W odpowiedzi (nie w pliku): liczba słów prozy i szacowana liczba stron, lista plików w `examples/NN-slug/`, co zostało uruchomione i zweryfikowane (komendy), czego nie dało się uruchomić lokalnie, odkryte rozbieżności dokumentacja ↔ zachowanie, odstępstwa od briefu, potwierdzenie, że serwer jest zatrzymany.
