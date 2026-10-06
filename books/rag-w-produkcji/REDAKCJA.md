# Brief redakcyjny – drugi przebieg tomu 2 („RAG w produkcji”)

Cel przebiegu: ta sama wiedza i te same liczby, ale opowiedziane tak, żeby czytelnik, który uczy się RAG-u, chciał czytać dalej po piątej stronie. Pierwsza wersja (kopie w `drafts/v1/`) jest poprawna merytorycznie, ale czyta się jak raport z laboratorium: rozdziały zaczynają się od dwunastowierszowych tabel, co kilka zdań pada identyfikator pytania albo trzy metryki naraz, a intuicja przychodzi po liczbach zamiast przed nimi. Autor tomu powiedział wprost: „wolę prostsze podejście, które tłumaczy, niż suche laboratorium, które odrzuci po pięciu stronach”.

Wzorzec tonu: `books/ai-engineer/chapters/03-prompt-engineering.md` (tom 1) oraz sekcja „Prototyp i produkcja: gdzie to pęka” z `chapters/01-projekt-i-pomiar.md` tego tomu. Tak ma brzmieć cała książka.

## Czego NIE zmieniać

- **Żadnej liczby.** Wszystkie wyniki pomiarów zostają dokładnie takie, jakie są (zaokrąglenia też). Jeśli podejrzewasz błąd, napisz o tym w raporcie, nie poprawiaj.
- **Żadnego nowego pomiaru** ani uruchamiania skryptów. Kod w `code/` jest zamknięty; nie edytuj go. Możesz go czytać, żeby lepiej wytłumaczyć.
- **Decyzji projektowych** („co zostaje w projekcie”) i wyników negatywnych – zostają, tylko opowiedziane prościej.
- **Snippetów kodu** – zostają, chyba że snippet nic nie tłumaczy (wtedy skróć albo usuń, ale nie zmieniaj składni istniejących wywołań). Bloki „Przykładowy wynik:” zostają z tym oznaczeniem.
- **Struktury końcowej**: `## Podsumowanie`, `## Co dalej`, `## Źródła` zostają. Zdania „Skrypt: `experiments/…`” zostają przy każdej tabeli, która przetrwa.
- Nazwy plików rozdziałów, blok „Cel rozdziału / Kod” na początku.
- Zasady języka z `books/ai-engineer/BRIEF.md` (polska typografia, półpauza, druga osoba, angielski w kodzie).

## Co zmienić

1. **Każdy rozdział zaczyna się od problemu opowiedzianego po ludzku**, nie od tabeli. Dwa–trzy akapity: co się dzieje, gdy tego nie zrobisz; jeden konkretny przykład pytania z golden setu zacytowany słownie („Jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi?”) i to, co system odpowiedział źle. Dopiero potem plan rozdziału w dwóch zdaniach.

2. **Każda technika w stałym rytmie**: (a) po co – jaki błąd naprawia, na przykładzie; (b) jak działa – w dwóch–czterech zdaniach, bez żargonu, jeśli da się bez, z porównaniem do czegoś znanego, jeśli pomaga; (c) kod – minimalny; (d) wynik – **krótka tabela (3–6 wierszy)** z jednym akapitem interpretacji zaczynającym się od wniosku, nie od liczby; (e) kiedy warto, kiedy nie – jedno–dwa zdania.

3. **Tabele odchudzić.** Zostaw wiersze, które niosą wniosek (baseline, najlepszy wariant, najgorszy, ewentualnie ten, który zaskakuje). Resztę zastąp zdaniem „pełną siatkę dwunastu wariantów wypisuje `experiments/02_chunking.py`”. Kolumny też: recall@5 i „pytań bez trafienia” wystarczą w większości tabel; MRR/nDCG tylko tam, gdzie o nich mowa. Tabela zbiorcza na końcu rozdziału może być pełniejsza (do 8 wierszy).

4. **Liczby w prozie ograniczyć.** Reguła: jeden akapit, jedna liczba, którą czytelnik ma zapamiętać. Trzy metryki w jednym zdaniu to za dużo. Zamiast „recall@5 0,81 → 0,72 → 0,81, MRR 0,67, nDCG 0,63–0,67” napisz „zakładka nie ma czytelnego wpływu: wyniki skaczą w obie strony bez wzoru”, a liczby zostaw w tabeli.

5. **Identyfikatory pytań (q022, q039…) usunąć z prozy.** Zamiast nich krótki opis pytania („pytanie o limit pliku w transkrypcji”). Identyfikator może zostać raz, w nawiasie, tam gdzie czytelnik ma odszukać pytanie w pliku, i w tabelach.

6. **Przypominać znaczenie metryk**, gdy wracają po dłuższej przerwie, półzdaniem: „recall@5, czyli czy właściwa sekcja jest wśród pięciu fragmentów wkładanych do promptu”. Nie zakładaj, że czytelnik pamięta definicję z rozdziału 1.

7. **Odwołania do tomu 1** zostają w formie „tom 1, rozdział N”. Gdy mowa o sekcji korpusu („Dobre praktyki” rozdziału 11), dopisz raz w rozdziale, że chodzi o rozdział tomu 1, bo to on jest korpusem.

8. **Skrócić o 20–30 procent.** Cięcia idą najpierw w tabele, potem w powtórzenia i w akapity, które tylko komentują liczby. Nie tnij przykładów, intuicji ani wyników negatywnych.

9. **Akapity 3–6 zdań, jedna myśl.** Zdania krótsze niż w wersji pierwszej. Bez zdań z trzema nawiasami.

## Przykład przebudowy (z rozdziału 2, sekcja o rozmiarze okna)

Przed: nagłówek, zdanie wprowadzające, tabela 12 wierszy × 9 kolumn, trzy akapity z kilkunastoma liczbami.

Po: nagłówek; akapit o tym, że rozmiar okna każdy tutorial każe ustawić „na oko”, i o tym, co się stanie, gdy ustawisz za duży (jeden wektor uśrednia trzy akapity o różnych rzeczach i nie leży blisko żadnego z nich); akapit o tym, jak to zmierzono (cztery rozmiary, trzy zakładki, ten sam golden set); tabela 4 wierszy (64, 128, 256, 512 bez zakładki: liczba chunków, tokeny w prompcie, recall@5, pytań bez trafienia); akapit z wnioskiem: „okno 512 jest wyraźnie złe, 128 i 64 są równie dobre, a zakładka nie ma czytelnego wpływu – pełną siatkę wypisuje skrypt”; akapit „co robić bez zestawu ewaluacyjnego: okno cztery razy krótsze niż limit modelu, liczone tokenizerem, nie w znakach”.

## Raport końcowy

Liczba słów prozy przed i po, liczba wierszy tabel przed i po, lista tabel usuniętych lub skróconych, lista miejsc, w których wątpisz w liczbę lub w spójność z innym rozdziałem (bez poprawiania), lista wszystkich zmian w kodzie snippetów (powinna być pusta lub prawie pusta).
