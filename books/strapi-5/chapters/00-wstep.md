# Wstęp

Strapi da się nauczyć z panelu. Klikasz typ treści w Content-Type Builderze, zaznaczasz uprawnienia roli Public, frontend dostaje JSON i aplikacja działa. Tak powstaje większość projektów i tak powstały też te, z których wyrosła ta książka. Problem zaczyna się w dniu, w którym trzeba dopisać logikę: autor ma edytować tylko swoje artykuły, komentarz ma czekać na moderację, frontend ma odświeżyć cache po publikacji. Wtedy okazuje się, że Strapi ma pod spodem kilka warstw (trasy, polityki, middleware, kontrolery, serwisy, Document Service, lifecycle hooks), a każda z nich przyjmie twój kod, tylko nie każda jest dobrym miejscem.

Ta książka jest mapą tych warstw. Dokumentacja Strapi 5 ma około siedmiuset stron i opisuje każdą opcję z osobna. Tutaj wybieramy to, czego naprawdę używa się przy budowie aplikacji, układamy w kolejności, w jakiej przechodzi żądanie, i przy każdym mechanizmie odpowiadamy na pytanie, które dokumentacja zostawia czytelnikowi: kiedy tego użyć, a kiedy czegoś innego.

## Dla kogo

Dla programisty, który ma już działające aplikacje na Strapi 5, zna panel i REST, a chce wiedzieć, co dzieje się pod spodem. Zakładamy TypeScript, Node.js, podstawy Koa albo Expressa i self-hosting na Dockerze. Nie zakładamy, że wiesz, czym polityka różni się od middleware – od tego pytania ta książka się zaczęła.

Płatnych funkcji (Strapi Cloud, plany Growth i Enterprise: Releases, Review Workflows, Content History, SSO, Audit Logs) nie opisujemy. Wszystko, co jest w książce, działa w darmowej wersji self-hosted.

## Jak ułożona jest książka

Rozdział 1 to mapa: struktura projektu, droga żądania od pierwszego middleware do bazy i tabela „gdzie umieścić logikę”. Rozdziały 2 i 3 dotyczą danych z zewnątrz: jak modelować treść i jak klient o nią pyta przez REST i GraphQL. Rozdziały 4–6 to rdzeń książki – trasy, polityki i middleware, potem kontrolery i serwisy, potem Document Service i reagowanie na zmiany. Jeśli masz czas tylko na trzy rozdziały, przeczytaj te.

Rozdziały 7 i 8 opisują to, co Strapi daje gotowe: użytkowników i tokeny, draft & publish, i18n, media, e-mail, webhooki i cron. Rozdziały 9 i 10 to rozszerzanie samego Strapi: własny plugin i panel admina. Rozdział 11 łączy backend z frontendem w Next.js, rozdział 12 dokłada typy, testy i narzędzia AI, a rozdział 13 prowadzi przez produkcję na Dockerze z Postgresem.

## Projekt przewodni i kod

Wszystkie rozdziały pracują na jednym projekcie: „Redakcja”, magazyn technologiczny pisany przez wielu autorów. Ma artykuły z draft & publish i dynamic zone, kategorie, komentarze z moderacją i ustawienia strony. Fundament leży w katalogu `code/` (Strapi 5.56, TypeScript, SQLite), a `npm run seed` wypełnia go danymi: trzema kategoriami, czterema artykułami i dwoma autorami, `anna` i `piotr`.

Fundament jest celowo niezabezpieczony – każdy zalogowany autor może edytować cudze artykuły, a komentarz można dodać od razu zatwierdzony. Kolejne rozdziały zamykają te luki i pokazują przy tym, jak wyglądają one w curl-u, zanim zostaną zamknięte. Kod każdego rozdziału jest w `examples/NN-nazwa/` z krótkim README: co skopiować do fundamentu i jak to sprawdzić.

Każdy wynik w książce pochodzi z uruchomionego projektu: odpowiedzi curl, logi, wyniki testów. Tam, gdzie lokalnie nie dało się czegoś uruchomić (prawdziwy S3, pełny OAuth z GitHubem, wysyłka przez zewnętrzny SMTP), blok jest oznaczony jako „Przykładowy wynik”. Ramki „Pułapka” zbierają miejsca, w których zachowanie Strapi 5.56 różni się od tego, co sugeruje dokumentacja, albo od tego, czego intuicyjnie się spodziewasz. Jest ich sporo i są najcenniejszą częścią tej książki.

## Wersja

Książka opisuje Strapi 5.56.0 (październik 2026). Strapi wydaje wersje minor co tydzień, więc szczegóły będą się zmieniać – wartości domyślne, nazwy eksportów, drobne zachowania. Architektura (droga żądania, rola Document Service, podział na Content API i Admin API) jest stabilna od 5.0. Gdy coś nie zgadza się z książką, sprawdź najpierw wersję, a potem stronę dokumentacji w wersji Markdown: każdy adres `docs.strapi.io` z dopisanym `.md` zwraca czysty tekst, a `https://docs.strapi.io/llms.txt` to indeks całości – rozdział 12 pokazuje, jak podłączyć to do asystenta AI.
