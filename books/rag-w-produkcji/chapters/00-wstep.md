# Wstęp

Tom 1 tej serii, „AI Engineer”, był mapą: czternaście rozdziałów, po jednym na każdy węzeł roadmapy, każdy doprowadzony do punktu „rozumiem i umiem uruchomić”. Rozdział o RAG-u kończył się tam działającym potokiem na pięciu pytaniach testowych i zdaniem, że to nieporównywalnie lepiej niż zero. Ten tom zaczyna się o krok dalej i przez osiem rozdziałów zajmuje się jedną rzeczą: jak z potoku, który działa na pięciu pytaniach, zrobić system, o którym potrafisz powiedzieć, jak dobrze działa, ile kosztuje i co się w nim zepsuje.

Różnica względem tomu 1 jest metodyczna, nie tylko tematyczna. Tam każdy rozdział opisywał technikę; tu każdy rozdział ją **mierzy**. Jeden korpus, jeden zamrożony zestaw pytań, te same metryki i to samo `k` od pierwszej do ostatniej strony. Każda tabela z liczbami ma obok nazwę skryptu, który ją odtwarza. Wyniki negatywne zostają w tekście, bo technika, która na tym korpusie nie pomogła, jest równie pouczająca jak ta, która pomogła – a w kilku miejscach bardziej.

## Dla kogo

Dla czytelnika tomu 1 albo kogoś o równoważnej wiedzy: wiesz, czym jest embedding, baza wektorowa, chunk i prompt z kontekstem, i uruchomiłeś przynajmniej raz prosty RAG. Tych pojęć nie tłumaczymy od nowa; w miejscach, gdzie są potrzebne, odsyłamy do konkretnego rozdziału tomu 1 („tom 1, rozdział 6”). Zakładamy też, że umiesz czytać wyniki pomiarów krytycznie, bo dużo miejsca poświęcamy temu, kiedy różnica w tabeli coś znaczy, a kiedy jest szumem.

## Projekt przewodni i korpus

Budujemy asystenta odpowiadającego na pytania po dokumentacji technicznej. Korpusem jest sam tom 1: czternaście plików Markdown, 131 sekcji, 64 tysiące słów po polsku, z blokami kodu, tabelami i powtarzającymi się sekcjami „Podsumowanie” na końcu każdego rozdziału. Wybraliśmy go z trzech powodów. Masz go pod ręką, więc każdą odpowiedź systemu możesz sprawdzić. Jest po polsku, więc problemy z tokenizacją, fleksją i modelami wielojęzycznymi są prawdziwe. I ma pułapki prawdziwej dokumentacji: co czwarty znak to kod, a najdłuższa sekcja ma 8,5 tysiąca tokenów.

Z tego wynika jedna konwencja, którą warto znać od początku. Kiedy w tekście pada „rozdział 3”, chodzi o rozdział tego tomu. Kiedy analizujemy wyniki wyszukiwania i mówimy, że trafienie pochodzi z sekcji „Dobre praktyki” rozdziału 11, chodzi o rozdział tomu 1, bo to on jest korpusem – ten tom ma tylko osiem rozdziałów, więc numer większy od ośmiu zawsze wskazuje na korpus. Odwołania do treści tomu 1 zapisujemy jawnie jako „tom 1, rozdział N”.

Zestaw ewaluacyjny to 56 pytań zbudowanych w rozdziale 1 i potem zamrożonych: 26 faktograficznych, 12 proceduralnych, 11 porównawczych z odpowiedzią w dwóch sekcjach i 7 takich, na które w korpusie odpowiedzi nie ma. Trafność oznaczona jest na poziomie sekcji, nie chunka, dzięki czemu ten sam plik obsługuje każdą strategię chunkowania z rozdziału 2 i każdy retriever z rozdziałów 3 i 4.

## Jak ułożona jest książka

Rozdział 1 buduje naiwny baseline, zestaw pytań i metryki, a jego analiza błędów wyznacza plan reszty. Rozdziały 2, 3 i 4 poprawiają kolejno trzy elementy wyszukiwania – reprezentację (chunking, model embeddingowy), ranking (hybryda z BM25, reranking) i zapytanie (przeformułowania, filtry, routing) – i każdy kończy się tabelą przed/po oraz decyzją, co zostaje w projekcie. Rozdział 5 zajmuje się danymi, które nie są czystym Markdownem: PDF-ami z układem, tabelami i kodem. Rozdział 6 przechodzi do generacji: cytowania, odmowa, wierność odpowiedzi i jej pomiar. Rozdział 7 wychodzi poza podobieństwo wektorowe do grafów i pętli agentowych i uczciwie liczy, co z tego wynika. Rozdział 8 zamienia potok w usługę: aktualizacje indeksu, cache, koszt, latencja, bezpieczeństwo i obserwowalność.

Kolejność ma znaczenie w pierwszych czterech rozdziałach, bo każdy mierzy się względem poprzedniego. Rozdziały 5–8 stoją na fundamencie z rozdziału 1 i można je czytać w dowolnym porządku.

## Kod

Cały kod żyje w jednym katalogu, `books/rag-w-produkcji/code/`, jako pakiet `ragbook` plus skrypty w `experiments/`. Snippety w rozdziałach pokazują istotę; pełne, uruchamialne wersje są w pakiecie, a każdą tabelę z liczbami odtwarza jeden skrypt, którego nazwa stoi pod tabelą. Uruchamiasz je z katalogu `code/`, w środowisku wirtualnym książki.

Wszystko, co lokalne – chunking, embeddingi, BM25, indeks Qdrant w pamięci, rerankery, metryki, cache, pomiary czasu – zostało uruchomione naprawdę i liczby w tabelach pochodzą z tych uruchomień. Wywołania modeli językowych (generacja odpowiedzi, przeformułowania zapytań, sędzia wierności, ekstrakcja encji) wymagają klucza API, którego autorzy podczas pisania nie używali: kod tych wywołań jest zgodny z dokumentacją sprawdzoną we wrześniu 2026, a ich wyniki są oznaczone jako „Przykładowy wynik”. W każdym takim miejscu tekst mówi wprost, jak odtworzyć eksperyment z własnym kluczem i ile to orientacyjnie kosztuje.

Pomiary czasu były wykonywane na laptopie z ośmiordzeniowym procesorem i kartą GeForce GTX 1650 z 4 GB pamięci; przy każdej liczbie stoi, na czym była mierzona. Domyślny model embeddingowy tomu to `intfloat/multilingual-e5-small`, dobrany tak, żeby cały korpus liczył się w kilkadziesiąt sekund także bez karty graficznej. Rozdział 2 pokazuje, ile daje model większy, i dlaczego mimo tego zostaliśmy przy mniejszym.

## Jak powstała ta książka

Tekst został napisany z pomocą modeli Claude pod redakcją autora, tą samą metodą co tom 1: każdy rozdział pisał osobny agent na podstawie aktualnej dokumentacji i własnych uruchomień kodu, a redaktor scalał wyniki, sprawdzał spójność liczb między rozdziałami i składał całość. Golden set również powstał w tym procesie i ma ograniczenie, o którym rozdział 1 mówi wprost: 56 pytań wybranych przez autora to nie to samo, co pytania Twoich użytkowników. Kiedy zbudujesz własny system, pierwszą rzeczą, którą warto z tej książki powtórzyć, jest nie żadna technika, tylko ten zestaw.
