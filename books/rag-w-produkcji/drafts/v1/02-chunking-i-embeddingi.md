# Rozdział 2. Chunking i model embeddingowy z pomiarem

> **Cel rozdziału:** zmierzyć na zamrożonym zestawie wszystkie popularne strategie cięcia dokumentu i trzy modele embeddingowe, odróżnić rzeczywisty zysk od losu, i zdecydować, co zostaje w projekcie.
>
> **Kod:** `ragbook/chunking.py`, `experiments/02_chunking.py`, `02_alignment.py`, `02_structure.py`, `02_context.py`, `02_embedders.py`, `02_summary.py`. **Pakiety poza fundamentem:** brak.

Rozdział 1 zostawił Cię z liczbą 0,72 i listą dziewięciu pytań, na które naiwny baseline nie znajduje niczego w czołowej piątce. Druga z czterech kategorii błędów – konkret utopiony w długiej sekcji – i osobny przypadek q039, w którym okno tokenowe tnie blok kodu w pół, wyglądają na problemy chunkingu, a chunking jest w całym potoku RAG najtańszą rzeczą do zmiany: nie wymaga nowego modelu, nowej bazy ani jednego wywołania API. Dlatego zaczynamy od niego.

Uprzedzę zakończenie, bo to uczciwsze niż budowanie napięcia przez dwanaście stron. Żadna ze strategii cięcia zmierzonych w tym rozdziale nie poprawia recall@5 na tym korpusie w sposób, który przetrwa kontrolę. Poprawia go natomiast zamiana modelu embeddingowego na dwa razy większy: o 0,07–0,08 na każdym chunkerze, na którym go zmierzyłem, przy liczbie pytań bez trafienia spadającej o połowę. Po drodze zobaczysz eksperyment, który tłumaczy, dlaczego pierwsze zdanie tego akapitu brzmi tak, jak brzmi – i który powinien zmienić sposób, w jaki czytasz każdą tabelę z porównaniem chunkerów, łącznie z moimi.

Wszystkie snippety uruchamiasz z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/02_chunking.py`. Zestaw pytań jest ten sam co w rozdziale 1 i nie zmienia się ani o jedną linię; metryki liczy `ragbook.evaluate` po sekcjach, więc każdy chunker mogę porównać z każdym.

## Stałe okno: siatka rozmiarów i zakładek

Zacznijmy od parametru, który w każdym tutorialu jest ustawiany „na oko”: rozmiaru okna i wielkości zakładki. Cztery rozmiary razy trzy zakładki to dwanaście indeksów; każdy trzeba policzyć raz, a potem siedzi w cache'u.

| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|---|
| 64/0 (0%) | 2364 | 64 | 314 | 0,72 | 0,93 | 0,66 | 0,63 | 9 |
| 64/16 (25%) | 3078 | 64 | 314 | 0,73 | 0,88 | 0,66 | 0,64 | 8 |
| 64/32 (50%) | 4524 | 64 | 318 | 0,79 | 0,89 | 0,67 | 0,65 | 6 |
| 128/0 (0%) | 1213 | 128 | 612 | 0,81 | 0,94 | 0,67 | 0,67 | 5 |
| 128/32 (25%) | 1550 | 128 | 620 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| 128/64 (50%) | 2233 | 128 | 631 | 0,81 | 0,90 | 0,67 | 0,67 | 6 |
| 256/0 (0%) | 636 | 256 | 1207 | 0,76 | 0,95 | 0,64 | 0,63 | 7 |
| 256/64 (25%) | 787 | 256 | 1228 | 0,72 | 0,92 | 0,68 | 0,65 | 10 |
| 256/128 (50%) | 1083 | 256 | 1235 | 0,71 | 0,88 | 0,63 | 0,61 | 9 |
| 512/0 (0%) | 347 | 512 | 2066 | 0,62 | 0,93 | 0,52 | 0,51 | 15 |
| 512/128 (25%) | 405 | 512 | 2130 | 0,65 | 0,88 | 0,57 | 0,56 | 12 |
| 512/256 (50%) | 519 | 512 | 2250 | 0,61 | 0,89 | 0,55 | 0,52 | 14 |

Skrypt: `experiments/02_chunking.py`.

Jeden wniosek z tej tabeli jest twardy i powtarzalny: **okno 512 tokenów jest wyraźnie złe**. Recall spada do 0,61–0,65, MRR do 0,52–0,57, a liczba pytań bez trafienia rośnie z dziewięciu do dwunastu–piętnastu. Mechanizm jest prosty i nie ma w nim nic z losu: chunk o 512 tokenach to u nas kawałek sekcji obejmujący trzy–cztery akapity o różnych rzeczach, a jeden wektor uśrednia je do punktu, który nie leży blisko żadnego z nich. Do tego takich chunków jest tylko 347, więc czołowa piątka to trzynaście procent całego korpusu – wyszukiwanie przestaje być wyszukiwaniem, a staje się grubym przybliżeniem. Rozmiary 64, 128 i 256 tworzą płaskowyż, na którym różnice są znacznie mniejsze niż różnica między płaskowyżem a 512.

Drugi wniosek dotyczy kosztu. Kolumna „Tokeny w prompcie @5” to **prawdziwa** średnia liczba tokenów e5 w pięciu zwracanych fragmentach, a nie iloczyn `k` razy rozmiar okna: 314 przy oknie 64, 620 przy 128, 1228 przy 256 i 2130 przy 512. Podwojenie okna podwaja rachunek za wejście do modelu generującego, a w rozmowie wielotorowej – także za wszystkie kolejne tury (tom 1, rozdział 4). Indeks działa odwrotnie: 512-tokenowe chunki dają 347 wektorów zamiast 4524. W naszej skali to różnica między 0,5 a 6,6 megabajta i nie obchodzi nikogo; przy dziesięciu milionach dokumentów to różnica między jedną a trzynastoma maszynami.

Jeżeli musisz wybrać rozmiar okna dziś, bez zestawu ewaluacyjnego: **weź okno mniej więcej cztery razy krótsze niż limit wejścia modelu i policz je tokenizerem tego modelu, nie w znakach**. Przy e5 z limitem 512 wychodzi 128. Przy modelu z limitem 8192 wyszłoby 2000, ale wtedy ogranicza Cię już nie model, tylko prompt: pięć razy 2000 tokenów to dziesięć tysięcy tokenów wejścia na pytanie. Górną granicę wyznacza budżet promptu, dolną – to, żeby fragment dało się przeczytać bez sąsiadów; sztuką jest trzymać się z dala od obu krańców, a nie stroić trzecią cyfrę.

Zakładka nie ma w tej tabeli żadnego czytelnego wpływu. Dla okna 64 recall rośnie z zakładką (0,72 → 0,73 → 0,79), dla 128 zachowuje się niemonotonicznie (0,81 → 0,72 → 0,81), dla 256 maleje (0,76 → 0,72 → 0,71), a dla 512 skacze w obie strony. Gdyby zakładka miała mechanizm – „ratuje zdania przecięte na granicy” – powinien on działać podobnie przy każdym rozmiarze okna. Nie działa. Zanim jednak uznasz, że 128 bez zakładki to zwycięzca (0,81 przeciwko 0,72 baseline'u, dziewięć porażek spada do pięciu), zrób eksperyment z następnej sekcji.

## Ile kosztuje samo miejsce cięcia

Weź baseline z rozdziału 1 – okno 128, zakładka 32 – i nie zmieniaj w nim niczego poza jednym: niech pierwsze cięcie w każdej sekcji zaczyna się o kilkanaście tokenów dalej. Strategia ta sama, rozmiar ten sam, zakładka ta sama, model ten sam, liczba chunków niemal ta sama. Zmienia się wyłącznie to, w którym miejscu tekstu wypadają granice.

```python
from ragbook.chunking import evaluate_chunks, shifted_window_chunks
from ragbook.corpus import load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden

sections, golden = load_sections(), load_golden()
embedder = Embedder()

for offset in (0, 16, 32, 48, 64, 80, 96):
    chunks = shifted_window_chunks(sections, embedder.tokenizer, 128, 32, offset)
    r = evaluate_chunks(f"offset {offset}", chunks, embedder, golden)
    print(f"offset {offset:3d}  {r['chunks']:5d} chunks  "
          f"recall@5 {r['recall@5']:.3f}  MRR@5 {r['mrr@5']:.3f}  misses {r['misses@5']}")
```

| Przesunięcie | Chunków | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| 0 | 1550 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| 16 | 1656 | 0,71 | 0,85 | 0,67 | 0,64 | 10 |
| 32 | 1637 | 0,80 | 0,94 | 0,66 | 0,67 | 5 |
| 48 | 1616 | 0,76 | 0,88 | 0,66 | 0,64 | 7 |
| 64 | 1597 | 0,77 | 0,92 | 0,67 | 0,65 | 7 |
| 80 | 1570 | 0,85 | 0,94 | 0,64 | 0,66 | 4 |
| 96 | 1550 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |

Skrypt: `experiments/02_alignment.py`.

Rozstęp recall@5 wynosi **0,133** – od 0,714 do 0,847 – i nie stoi za nim żadna decyzja projektowa. Przesunięcie o 96 tokenów daje te same liczby co brak przesunięcia, bo krok okna wynosi 96 i cięcia wracają na swoje miejsca; to przy okazji dowód, że implementacja robi to, co obiecuje. Wszystko pomiędzy jest losowaniem. Dla porównania: najlepszy wariant z dwunastoelementowej siatki wygrywał z baseline'em o 0,082, czyli o dwie trzecie tego, co potrafi wylosować samo przesunięcie granicy.

Zwróć uwagę na kolumnę MRR@5: od 0,644 do 0,673, rozstęp 0,029, pięć razy węższy. To nie przypadek. Recall@5 liczony po sekcjach jest metryką progową – wystarczy, że chunk z właściwej sekcji przeskoczy z szóstego miejsca na piąte, a pytanie zmienia wynik z 0 na 1 całym skokiem, podczas gdy MRR zmienia się o 0,03. Kilka takich przeskoków na 49 pytaniach robi 0,1 recall i prawie nic w MRR. **Raportuj obie metryki, a gdy się rozjeżdżają, wierz tej stabilniejszej.**

To jest kontekst dla reszty tego rozdziału i dla każdego porównania chunkerów, jakie przeczytasz gdziekolwiek indziej. Jeżeli ktoś pokazuje, że jego strategia cięcia daje o 0,05 lepszy recall, a nie pokazuje, ile daje przesunięcie granic o dwadzieścia tokenów w jego własnej strategii, to nie wiesz, czy widzisz technikę, czy szczęśliwy los. Reguła z rozdziału 1 – patrz, ile pytań zmieniło wynik i czy umiesz nazwać mechanizm – przestaje tu być radą metodologiczną, a staje się jedynym narzędziem, jakie masz.

## Podział po strukturze Markdown

Dokumentacja ma granice, których nie trzeba zgadywać: nagłówki, akapity, bloki kodu, tabele. Chunker, który z nich korzysta, produkuje fragmenty, które da się przeczytać, i nie przecina funkcji w połowie definicji. `ragbook/chunking.py` rozbija sekcję na bloki funkcją `split_blocks`: blok otoczony ogrodzeniem z trzech znaków wstecznego apostrofu zostaje w całości niezależnie od pustych linii w środku, a reszta rozdziela się po pustych liniach, co samo z siebie utrzymuje tabelę Markdown i listę punktowaną w jednym kawałku.

```python
from collections import Counter

from ragbook.chunking import evaluate_chunks, merged_block_chunks, split_blocks
from ragbook.corpus import load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden

sections, golden = load_sections(), load_golden()
embedder = Embedder()

kinds = Counter(kind for s in sections for kind, _ in split_blocks(s.text))
print(kinds.most_common())

chunks = merged_block_chunks(sections, embedder.tokenizer, max_tokens=256)
r = evaluate_chunks("bloki łączone do 256", chunks, embedder, golden)
print(r["chunks"], "chunków, recall@5", round(r["recall@5"], 3), "misses", r["misses@5"])
```

```text
[('prose', 614), ('code', 156), ('heading', 76), ('list', 28), ('quote', 14), ('table', 14), ('math', 2)]
691 chunków, recall@5 0.724 misses 9
```

Dziewięćset cztery bloki na 131 sekcji, w tym 156 bloków kodu i 14 tabel. To jest cała mapa korpusu i punkt wyjścia dla czterech wariantów: sekcja jako jeden chunk, blok jako chunk, bloki sklejane do budżetu i podział rekurencyjny.

| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|---|
| stałe okno 128/32 (baseline) | 1550 | 128 | 620 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| sekcja = chunk (ucięta do 512) | 131 | 512 | 2257 | 0,47 | 0,72 | 0,38 | 0,37 | 22 |
| blok Markdown = chunk | 904 | 142 | 903 | 0,70 | 0,92 | 0,61 | 0,59 | 10 |
| bloki łączone do 128 | 861 | 128 | 585 | 0,69 | 0,92 | 0,58 | 0,57 | 10 |
| bloki łączone do 256 | 691 | 188 | 986 | 0,72 | 0,91 | 0,62 | 0,61 | 9 |
| bloki łączone do 384 | 499 | 293 | 1352 | 0,65 | 0,87 | 0,57 | 0,56 | 12 |
| rekurencyjny 256 | 780 | 194 | 1018 | 0,78 | 0,92 | 0,60 | 0,60 | 7 |
| rekurencyjny 128 | 1450 | 108 | 506 | 0,71 | 0,95 | 0,63 | 0,61 | 9 |
| semantyczny 256 (p90) | 726 | 201 | 1020 | 0,68 | 0,92 | 0,61 | 0,59 | 10 |
| semantyczny 256 (p80) | 830 | 151 | 976 | 0,73 | 0,95 | 0,64 | 0,63 | 9 |

Skrypt: `experiments/02_structure.py`.

Pierwszy wiersz po baseline'ie to jedyna katastrofa w tym rozdziale. „Sekcja jako chunk” brzmi rozsądnie – sekcja jest jednostką trafności, więc niech będzie jednostką indeksu – ale sekcje w tym korpusie mają medianę 667 tokenów i maksimum 8589, a `multilingual-e5-small` czyta 512. **Osiemdziesiąt ze 131 sekcji, czyli 61 procent, jest dłuższych niż limit modelu.** Po ucięciu w indeksie ląduje 59 070 ze 146 791 tokenów korpusu: **czterdzieści procent tekstu, reszta znika bez jednego ostrzeżenia**. Recall@5 spada do 0,47, recall@20 do 0,72, czyli dla jednego pytania na cztery odpowiedzi nie ma nawet w dwudziestce – bo fizycznie nie ma jej w indeksie. To ta sama pułapka, którą tom 1 opisywał przy MiniLM-ie i limicie 128 tokenów, widziana od strony metryki.

Reszta tabeli to płaskowyż z jednym odchyleniem w górę. Bloki sklejane do 256 tokenów dają tyle samo co baseline (0,72 przy dziewięciu porażkach), bloki do 128 i 384 nieco mniej, a rekurencyjny 256 najwięcej (0,78, siedem porażek) – ale z najniższym MRR w tabeli (0,60 przeciwko 0,67). Ta para liczb mówi, że rekurencyjny wpuszcza trafną sekcję do piątki częściej, ale niżej. Rozbicie po typach pokazuje dlaczego: pytania proceduralne skaczą z 0,62 na **0,79**, bo odpowiedzią na „jak coś zrobić” jest procedura rozłożona na kilka zdań, a chunk o 194 tokenach mieści ją w całości, gdy okno 128-tokenowe łapie jeden krok bez kontekstu. W drugą stronę spadają porównawcze (0,64 → 0,59): większe chunki to mniej chunków i mniej różnych sekcji w piątce, a pytanie porównawcze potrzebuje dwóch.

To jest pierwszy wynik w tym rozdziale, który ma nazwany mechanizm i widać go w rozbiciu, a nie tylko w średniej. Jest jednocześnie za słaby, żeby przetrwać test z poprzedniej sekcji: +0,051 średniej to mniej niż rozstęp losowania granic.

Jest jednak druga korzyść ze struktury, której ten zestaw pytań nie umie zmierzyć, a która zadecyduje o wyborze na końcu rozdziału. Chunk pokrywający się z blokiem Markdown **da się pokazać użytkownikowi**: zaczyna się od początku akapitu, kończy kropką, a jeśli jest kodem, to kompilowalnym, a nie jego drugą połową. Ma to znaczenie przy cytowaniach z rozdziału 6, przy BM25 z rozdziału 3 – który potrzebuje całego identyfikatora, a nie `clear_tool_uses_2025` uciętego na granicy okna – i przy tabelach z rozdziału 5. Metryka po sekcjach jest na to ślepa z definicji: pyta, z której sekcji pochodzi fragment, a nie czy da się go przeczytać.

## Rekurencyjny i semantyczny

Podział rekurencyjny to ta sama idea, którą w LangChainie realizuje `RecursiveCharacterTextSplitter`: próbuj najgrubszej granicy, jaką dokument oferuje, schodź niżej tylko wtedy, gdy kawałek nadal jest za długi, a na końcu posklej sąsiadów z powrotem do budżetu. U nas granice to nagłówki `###`, puste linie, końce zdań i wreszcie pojedyncze tokeny – i to jest cała implementacja, dwadzieścia linii bez zależności.

```python
import re


def recursive_split(text: str, tokenizer, max_tokens: int, separators: list[str]) -> list[str]:
    if len(tokenizer(text, add_special_tokens=False)["input_ids"]) <= max_tokens:
        return [text]
    for i, sep in enumerate(separators):
        parts = [p for p in re.split(sep, text) if p.strip()]
        if len(parts) > 1:
            out = []
            for part in parts:
                out.extend(recursive_split(part, tokenizer, max_tokens, separators[i + 1:]))
            return out
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    return [tokenizer.decode(ids[j:j + max_tokens]) for j in range(0, len(ids), max_tokens)]


SEPARATORS = [r"\n(?=### )", r"\n\s*\n", r"(?<=[.!?])\s+", r"\s+"]
```

Jedyna istotna różnica wobec wersji z frameworka siedzi w pierwszej linii: długość liczymy **tokenizerem modelu embeddingowego**, a nie w znakach. Przy polszczyźnie i tokenizerze XLM-R to 2,3 tokena na słowo (rozdział 1), więc limit ustawiony na znakach albo przepuści chunki powyżej limitu modelu, albo potnie je bez potrzeby. Po podziale `recursive_chunks` skleja sąsiadujące kawałki, żeby nie zostawić w indeksie czterotokenowych ogonków.

Podział semantyczny działa inaczej: nie pyta dokumentu o granice, tylko sam je wyznacza. Embeduje kolejne zdania, liczy kosinus między sąsiadami i tnie tam, gdzie podobieństwo spada poniżej progu. Ponieważ kosinusy z rodziny E5 układają się ciasno między 0,7 a 1,0 (rozdział 1), próg bezwzględny jest bezużyteczny i trzeba go wziąć z rozkładu: p90 oznacza „tnij na dziesięciu procentach największych skoków”.

```python
from ragbook.chunking import semantic_chunks

chunks = semantic_chunks(sections, embedder, max_tokens=256, percentile=80.0)
print(len(chunks), "chunków, próg odległości", round(chunks[0].meta["threshold"], 3))
```

Koszt trzeba policzyć przed, a nie po. Korpus rozpada się na **3348 zdań o łącznej długości 146 791 tokenów**, czyli tyle, ile ma cały korpus – semantyczny chunker embeduje więc całość raz dodatkowo, zanim powstanie pierwszy chunk, a potem drugi raz już jako chunki. Podwaja to rachunek za indeksowanie i za każdą reindeksację. W zamian daje 0,73 przy progu p80 i 0,68 przy p90: tyle samo co baseline i mniej niż rekurencyjny. **Na tym korpusie się nie opłaca**, i nie jest to zaskoczenie – dokumentacja jest już podzielona przez autora na akapity, a akapit jest lepszą granicą tematyczną niż próg na kosinusie. Semantyczny chunking ma sens tam, gdzie granic nie ma: w transkrypcjach rozmów, w skanach bez struktury, w długich mailach.

## Contextual chunk headers i tanie contextual retrieval

Fragment wycięty ze środka sekcji nie wie, gdzie jest. Zdanie „ponawiamy pięć razy z wykładniczym backoffem” nie mówi, czego dotyczy, a wektor policzony z takiego zdania leży blisko wszystkiego, co mówi o ponawianiu. Najtańsza naprawa to doklejenie tytułu rozdziału i nagłówka sekcji przed treść chunku **przed embedowaniem** – w `ragbook.corpus.fixed_window_chunks` służy do tego flaga `prefix_with_title`, a `with_context_headers` robi to samo dla dowolnego chunkera, zachowując oryginalną treść w `meta["body"]`, żeby do promptu trafił czysty tekst bez nagłówka.

```python
from ragbook.chunking import evaluate_chunks, section_leads, with_context_headers
from ragbook.corpus import fixed_window_chunks

plain = fixed_window_chunks(sections, embedder.tokenizer, 128, 32)
leads = section_leads(sections)          # first sentence of every section

for name, chunks in [
    ("bez kontekstu", plain),
    ("nagłówek", with_context_headers(plain, "title")),
    ("nagłówek + 1. zdanie sekcji", with_context_headers(plain, "lead", leads)),
]:
    r = evaluate_chunks(name, chunks, embedder, golden, count_tokens_on="body")
    print(f"{name:>28}  recall@5 {r['recall@5']:.3f}  misses {r['misses@5']}")
```

Drugi wariant jest tanim przybliżeniem contextual retrieval: zamiast prosić model o opis chunku, doklejamy nagłówek i pierwsze zdanie sekcji, czyli to, co autor sam napisał jako wprowadzenie. Kosztuje zero i da się policzyć w sekundę.

| Wariant | Chunków | Tokeny w prompcie @5 | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|
| stałe okno 128/32 | 1550 | 620 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| 128/32 + nagłówek | 1550 | 628 | 0,76 | 0,91 | 0,68 | 0,66 | 7 |
| 128/32 + nagłówek + 1. zdanie | 1550 | 622 | 0,65 | 0,80 | 0,65 | 0,60 | 12 |
| stałe okno 128/0 | 1213 | 612 | 0,81 | 0,94 | 0,67 | 0,67 | 5 |
| 128/0 + nagłówek | 1213 | 615 | 0,76 | 0,91 | 0,63 | 0,63 | 8 |
| 128/0 + nagłówek + 1. zdanie | 1213 | 622 | 0,60 | 0,80 | 0,55 | 0,53 | 15 |
| bloki łączone do 256 | 691 | 986 | 0,72 | 0,91 | 0,62 | 0,61 | 9 |
| bloki do 256 + nagłówek | 691 | 1004 | 0,71 | 0,95 | 0,62 | 0,61 | 11 |
| rekurencyjny 256 | 780 | 1018 | 0,78 | 0,92 | 0,60 | 0,60 | 7 |
| rekurencyjny 256 + nagłówek | 780 | 1015 | 0,70 | 0,93 | 0,55 | 0,56 | 10 |

Skrypt: `experiments/02_context.py`.

Contextual chunk headers są techniką, którą poleca się w internecie najczęściej ze wszystkich opisanych w tym rozdziale, i na naszym korpusie **nie działają**. Podnoszą wynik jednej konfiguracji o 0,03 (0,72 → 0,76, dziewięć porażek na siedem), obniżają trzy pozostałe – o 0,05 przy oknie bez zakładki, o 0,01 przy blokach i o 0,08 przy rekurencyjnym. Porównanie parami wobec baseline'u daje pięć pytań w górę i pięć w dół; to jest definicja szumu. Recall@20 spada we wszystkich czterech przypadkach, najmocniej z 0,96 do 0,91.

Mechanizm porażki daje się nazwać i dotyczy każdego korpusu jednorodnego tematycznie. Nagłówek dokleja do 128-tokenowego chunku kilkanaście tokenów **identycznych dla wszystkich chunków tej samej sekcji** i bardzo podobnych w obrębie rozdziału. Wektory chunków jednej sekcji zbliżają się więc do siebie, a sekcje o podobnych tytułach do siebie nawzajem – i „Obserwowalność” z rozdziału 12 konkuruje z „Dobrymi praktykami” z rozdziału 11 tytułem, a nie treścią. Zysk pojawia się tylko tam, gdzie pytanie jest sformułowane terminami z nagłówka, i widać to w rozbiciu: faktograficzne rosną z 0,81 na 0,88, proceduralne spadają z 0,62 na 0,58. Gdyby korpus był zbiorem niepowiązanych dokumentów wielu klientów, nagłówek „Acme / Limity zapytań” niósłby informację różnicującą i wynik byłby inny. U nas wszystkie dokumenty są o jednym.

Wariant z pierwszym zdaniem sekcji jest gorszy za każdym razem i to o dużo: 0,65 i 0,60 przeciwko 0,76, przy dwunastu i piętnastu porażkach. Doklejenie tych samych trzydziestu tokenów do kilkudziesięciu chunków sekcji sprawia, że chunki przestają się różnić właśnie w tym, co w nich najważniejsze. Dwadzieścia osiem sekcji – wszystkie „Podsumowania” i „Źródła”, zaczynające się listą, a nie akapitem – nie ma zdania wprowadzającego i dostaje sam nagłówek. To uczciwe przybliżenie contextual retrieval tylko w jednym wymiarze: kosztu. **Czego nie mierzy**, opisuje następna sekcja.

## Contextual retrieval z LLM-em

Technika opisana przez Anthropic polega na tym, że dla każdego chunku tani model dostaje **cały dokument** i ten chunk, po czym pisze jedno–dwa zdania umieszczające fragment w całości; opis dokleja się przed treścią chunku przed embedowaniem. Różnica wobec naszego przybliżenia jest zasadnicza: opis jest **różny dla każdego chunku** i mówi o tym konkretnym fragmencie, zamiast powtarzać jedno zdanie przy wszystkich fragmentach sekcji. Anthropic raportuje spadek odsetka nieudanych wyszukiwań w top-20 o 35 procent dla samych embeddingów kontekstowych i o 49 procent w połączeniu z kontekstowym BM25.

Ekonomia tego rozwiązania stoi w całości na prompt cachingu. Bez niego wysyłasz cały rozdział raz na każdy chunk, czyli u nas dziewięćdziesiąt razy na rozdział. Z nim płacisz za rozdział raz, a każde kolejne wywołanie czyta go z cache'u.

```python
import os

from anthropic import Anthropic

from ragbook.chunking import project_chunks
from ragbook.corpus import load_sections
from ragbook.embed import Embedder

sections = load_sections()
chunks = project_chunks(sections, Embedder().tokenizer)
document = "\n\n".join(s.text for s in sections if s.chapter == 7)
chunk = next(c for c in chunks if c.chapter == 7 and c.section == "Indeksowanie embeddingów")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
CHUNK_PROMPT = """Here is the chunk we want to situate within the whole document:
<chunk>
{chunk}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the
purposes of improving search retrieval of the chunk. Answer only with the succinct context and
nothing else. Answer in Polish."""

message = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=150,
    messages=[{"role": "user", "content": [
        {"type": "text", "text": f"<document>\n{document}\n</document>",
         "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": CHUNK_PROMPT.format(chunk=chunk.text)},
    ]}],
)
context = next(b.text for b in message.content if b.type == "text").strip()
print(message.usage.cache_creation_input_tokens, message.usage.cache_read_input_tokens)
print(context)
```

Przykładowy wynik drugiego i każdego kolejnego wywołania dla tego samego rozdziału – pierwsze miałoby te dwie liczby zamienione miejscami:

```text
0 9871
Fragment pochodzi z rozdziału o bazach wektorowych, z sekcji o indeksowaniu embeddingów;
opisuje procedurę podmiany modelu embeddingowego przez zbudowanie nowej kolekcji obok starej
i przełączenie aliasu, omawianą tuż po opisie parametrów HNSW.
```

Trzy rzeczy z tego snippetu trzeba sprawdzić w dokumentacji, zanim policzysz budżet (stan na wrzesień 2026). Po pierwsze, **minimalna długość prefiksu, który w ogóle wejdzie do cache'u, zależy od modelu i dla Claude Haiku 4.5 wynosi 4096 tokenów**; krótszy dokument nie zostanie zapisany i nie dostaniesz o tym błędu – jedyny sygnał to `cache_creation_input_tokens` równe zeru w odpowiedzi. Nasz najkrótszy rozdział ma 4649 tokenów e5, czyli jest tuż nad progiem, i to jest dokładnie ten przypadek, w którym trzeba sprawdzić `usage`, a nie zakładać. Po drugie, domyślny czas życia wpisu to pięć minut; przy dziewięćdziesięciu wywołaniach na rozdział zmieścisz się, ale jeśli przetwarzasz dokumenty przeplatane albo z limitem szybkości, weź `"ttl": "1h"`. Po trzecie, zapis do cache'u kosztuje 1,25 raza stawkę wejściową przy pięciu minutach i 2 razy przy godzinie, a odczyt 0,1 stawki – i to ten ostatni mnożnik decyduje o opłacalności całej techniki. Anthropic podaje koszt rzędu jednego dolara na milion tokenów dokumentów.

Nie mam klucza API, więc tej techniki **nie zmierzyłem** i nie wstawiam jej do tabeli zbiorczej. Czego nie wiem: czy na tym korpusie opis generowany per chunk zachowałby się inaczej niż tanie przybliżenie. Argument za tym, że tak, jest mocny – opis różni się między chunkami, więc ich wektory rozsuwa, zamiast je spłaszczać, czyli robi odwrotność tego, co zepsuło wariant z pierwszym zdaniem sekcji. Argument za tym, że efekt będzie mniejszy niż u Anthropic, też jest mocny: ich korpusy testowe to bazy kodu i dokumenty finansowe wielu podmiotów, gdzie zdanie „to fragment raportu ACME za Q2 2023” niesie ogromną informację różnicującą, a u nas każdy chunk pochodzi z tej samej książki. Jeżeli masz klucz, uruchom `ragbook.chunking.contextualize` na 1283 chunkach projektu i zmierz wynik tym samym `experiments/02_summary.py`.

## Parent-child: mały chunk do wyszukiwania, duży do promptu

Small-to-big rozdziela dwie rzeczy, które stałe okno skleja: **czym wyszukujesz** i **co czytasz**. Indeksujesz małe, precyzyjne fragmenty, bo one dają ostre dopasowanie wektorowe, ale do promptu wkładasz rodzica – akapit albo całą sekcję, z której dziecko pochodzi. Implementacja sprowadza się do jednego pola w metadanych i cienkiej nakładki na retriever.

```python
from ragbook.chunking import ParentRetriever, evaluate_chunks, parent_child_chunks
from ragbook.store import DenseIndex

children, parents = parent_child_chunks(sections, embedder.tokenizer,
                                        child_tokens=128, parent="section")
index = DenseIndex(embedder, children)
retriever = ParentRetriever(index, parents, dedup=True)

for hit in retriever.search("Po co normalizować embeddingi?", k=3):
    print(hit.chapter, repr(hit.section), len(hit.meta["child_text"]), "->", len(hit.text), "znaków")
```

Metryki retrievalu nie mogą się przy tym zmienić i nie zmieniają się, bo trafność liczymy po sekcji dziecka, a podmiana tekstu jej nie dotyka. Zmienia się wyłącznie rachunek za prompt.

| Wariant | Chunków | Tokeny w prompcie @5 | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|
| dziecko 128, do promptu dziecko | 1641 | 490 | 0,66 | 0,92 | 0,58 | 0,56 | 12 |
| dziecko 128 → rodzic (blok) | 1641 | 1002 | 0,66 | 0,92 | 0,58 | 0,56 | 12 |
| dziecko 128 → rodzic (blok), dedup | 1641 | 986 | 0,66 | 0,92 | 0,58 | 0,56 | 12 |
| dziecko 128 → rodzic (sekcja) | 1213 | 2462 | 0,76 | 0,91 | 0,63 | 0,63 | 8 |
| dziecko 128 → rodzic (sekcja), dedup | 1213 | 1804 | 0,76 | 0,91 | 0,63 | 0,63 | 8 |

Skrypt: `experiments/02_context.py`.

Rodzic-akapit kosztuje dwa razy więcej tokenów niż samo dziecko (1002 przeciwko 490), rodzic-sekcja pięć razy więcej (2462) – i to jest cała decyzja. Deduplikacja, czyli wstawienie rodzica tylko raz, gdy dwoje dzieci z tej samej sekcji trafi do piątki, ścina rachunek za rodzica-sekcję o 27 procent, do 1804 tokenów; przy rodzicu-akapicie nie daje prawie nic, bo dwoje dzieci rzadko pochodzi z jednego akapitu. W skrajnym przypadku wszystkie pięć slotów promptu pokrywa wtedy jedną sekcję – i płacisz za powtórzenia.

Wariantem tej samej idei jest okno zdaniowe: indeksujesz pojedyncze zdanie, a do promptu wkładasz je z dwoma zdaniami przed i dwoma po. Rodzicem nie jest wtedy żadna z góry ustalona jednostka dokumentu, tylko okno wycięte wokół trafienia, więc nie dowozisz pół sekcji po to, żeby dostarczyć jedno zdanie. W `ragbook.chunking` nie ma na to osobnej funkcji, bo `parent_child_chunks` z rodzicem-blokiem realizuje to samo w przybliżeniu – ale przy akapitach dłuższych niż nasze to dobry pierwszy wybór.

**Kiedy to się opłaca:** gdy pytania są proceduralne, a dziecko pokazuje tylko jeden krok procedury; gdy generacja ma cytować i potrzebuje zdania przed i po; gdy płacisz głównie za wyjście, a wejście masz tanie. **Kiedy nie:** gdy sekcje są długie i niejednorodne, bo wkładasz wtedy do promptu trzy akapity o czymś innym, żeby dowieźć jeden właściwy, i płacisz podwójnie – tokenami i rozproszoną uwagą modelu (tom 1, rozdział 4). Na naszym korpusie, z medianą sekcji 667 tokenów, rodzic-sekcja jest za drogi; rodzic-akapit byłby rozsądnym kompromisem, gdyby dziecko wygrywało cokolwiek w metrykach, a nie wygrywa.

## Model embeddingowy, prefiksy i rozmiar indeksu

Do tej pory zmienialiśmy wszystko oprócz modelu. Zmieńmy model, zostawiając chunker w spokoju: te same okna 128-tokenowe bez zakładki, ten sam zestaw, ten sam `k`. Ładujemy po jednym modelu naraz i zwalniamy pamięć po pomiarze, bo karta ma cztery gigabajty.

| Model | Wymiar | Limit wejścia | Chunków | Indeks [MB] | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|---|---|
| `multilingual-e5-small`, okno 128 | 384 | 512 | 1213 | 1,78 | 0,81 | 0,94 | 0,67 | 0,67 | 5 |
| `MiniLM-L12-v2`, okno 128 | 384 | 128 | 1213 | 1,78 | 0,68 | 0,84 | 0,56 | 0,56 | 10 |
| `MiniLM-L12-v2`, okno 256 | 384 | 128 | 636 | 0,93 | 0,58 | 0,87 | 0,47 | 0,48 | 16 |
| `multilingual-e5-small`, okno 256 | 384 | 512 | 636 | 0,93 | 0,76 | 0,95 | 0,64 | 0,63 | 7 |
| `multilingual-e5-base`, okno 128 | 768 | 512 | 1213 | 3,55 | **0,88** | 0,96 | **0,79** | **0,78** | **2** |

Skrypt: `experiments/02_embedders.py`.

To jest najważniejsza tabela w rozdziale. `multilingual-e5-base` – dwanaście warstw, 768 wymiarów, 512 tokenów wejścia, inicjalizowany z `xlm-roberta-base` – daje recall@5 równy 0,88 i **dwa** pytania bez trafienia zamiast pięciu, a MRR@5 skacze z 0,67 na 0,79. Różnica wobec e5-small to 0,072 recall i 0,12 MRR, i w przeciwieństwie do wszystkiego wcześniej rośnie tu również ta stabilna metryka. Kosztuje 1,1 gigabajta wag zamiast 0,47 i dwa razy większy indeks (3,55 zamiast 1,78 megabajta przy 1213 chunkach; rozmiar indeksu to wymiar razy liczba chunków razy cztery bajty).

Żeby sprawdzić, czy to nie kolejna wygrana na loterii, powtórzyłem eksperyment z przesuwaniem granic na e5-base. Rozstęp recall@5 spada z 0,133 do **0,082**, a cały przedział przesuwa się w górę: najgorsze losowanie na e5-base (0,765) jest lepsze niż mediana losowań na e5-small (0,755). Lepszy model nie tylko podnosi wynik, ale też **uodparnia go na to, gdzie wypadnie cięcie** – co jest logiczne, bo model, który lepiej rozumie kontekst, mniej potrzebuje, żeby fakt leżał akurat w środku chunku.

`paraphrase-multilingual-MiniLM-L12-v2` przegrywa wyraźnie. Przy oknie 128 daje 0,68, czyli o 0,13 gorzej niż e5-small, choć ma ten sam wymiar wektora. Przy oknie 256 spada do 0,58 przy szesnastu porażkach, bo jego `max_seq_length` wynosi 128 tokenów i **połowa każdego chunku jest po cichu ucinana**. Porównaj to z e5-small przy tym samym oknie (0,76): identyczne chunki, identyczny wymiar, cała różnica to limit wejścia i jakość treningu. Limit długości wejścia jest twardym parametrem architektury indeksu, a nie szczegółem z karty modelu (tom 1, rozdział 6).

Prefiksy `query:` i `passage:` mierzę osobno, z wyłączonym cache'em – inaczej wariant bez prefiksów trafiłby na wpis policzony z prefiksami, bo klucz cache'u jest hashem pary (model, teksty), a prefiks dokleja się w środku `Embedder`.

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|
| e5-small z prefiksami | 0,81 | 0,94 | 0,67 | 0,67 | 5 |
| e5-small bez prefiksów | 0,74 | 0,96 | 0,65 | 0,65 | 8 |

Skrypt: `experiments/02_embedders.py`.

Sześć setnych recall i trzy dodatkowe porażki za dwa opuszczone łańcuchy znaków. Karta modelu mówi o tym wprost, a i tak jest to jeden z najczęstszych cichych błędów w projektach RAG, bo wszystko działa – tylko gorzej. Sprawdź w `ragbook/embed.py`, że słownik `_PREFIXES` obejmuje model, którego używasz: są tam trzy modele z rodziny E5, a dla każdego innego wrapper zwraca puste prefiksy – co dla MiniLM-a jest poprawne, a dla `bge-m3` czy modelu Jiny już niekoniecznie.

Na koniec czas, bo on decyduje o tym, ile wariantów zdążysz sprawdzić w ciągu dnia pracy. Pomiar bez cache'u, ten sam korpus 1213 chunków i 146 928 tokenów:

| Model | Urządzenie | Czas [s] | Tokenów/s |
|---|---|---|---|
| `multilingual-e5-small` | GPU (GTX 1650) | 6,0 | 24 331 |
| `multilingual-e5-small` | CPU | 30,3 | 4845 |
| `MiniLM-L12-v2` | GPU (GTX 1650) | 5,5 | 26 897 |
| `MiniLM-L12-v2` | CPU | 30,4 | 4838 |
| `multilingual-e5-base` | GPU (GTX 1650) | 27,0 | 5433 |
| `multilingual-e5-base` | CPU | 160,5 | 915 |

Skrypt: `experiments/02_embedders.py`.

E5-base jest pięć razy wolniejszy od e5-small po obu stronach, a przejście na kartę – nawet tak skromną jak GTX 1650 z czterema gigabajtami – daje pięciokrotne przyspieszenie. Przy naszym korpusie to pół minuty przeciwko trzem minutom i nie ma znaczenia; przy milionie chunków to różnica między czterema godzinami a dobą, i wtedy koszt reindeksacji staje się argumentem przy wyborze modelu (tom 1, rozdział 6). Cache w `ragbook.embed` sprawia, że płacisz ten czas raz na wariant: drugie uruchomienie tego samego eksperymentu wczytuje wektory z dysku w ułamku sekundy.

## Co zostaje w projekcie

Zbierzmy kandydatów i porównajmy każdego z baseline'em **pytanie po pytaniu**, tak jak obiecywał rozdział 1: bootstrap na różnicach per pytanie jest znacznie węższy niż bootstrap na średniej, bo większość pytań zachowuje się tak samo w obu wariantach i wnosi do różnicy zero.

| Wariant | Chunków | Tokeny w prompcie @5 | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|
| stałe okno 128/32 (rozdz. 1) | 1550 | 620 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| stałe okno 128/0 | 1213 | 612 | 0,81 | 0,94 | 0,67 | 0,67 | 5 |
| stałe okno 128/64 | 2233 | 631 | 0,81 | 0,90 | 0,67 | 0,67 | 6 |
| stałe okno 128/32 + nagłówek | 1550 | 628 | 0,76 | 0,91 | 0,68 | 0,66 | 7 |
| bloki łączone do 256 | 691 | 986 | 0,72 | 0,91 | 0,62 | 0,61 | 9 |
| rekurencyjny 256 | 780 | 1018 | 0,78 | 0,92 | 0,60 | 0,60 | 7 |
| kod i tabele w całości 128/32 | 1283 | 668 | 0,71 | 0,96 | 0,66 | 0,64 | 10 |

| Wariant | Średnia różnica | 95% CI (bootstrap parami) | Pytań w górę | Pytań w dół |
|---|---|---|---|---|
| stałe okno 128/0 | +0,082 | [+0,010; +0,163] | 6 | 1 |
| stałe okno 128/64 | +0,082 | [+0,020; +0,153] | 6 | 0 |
| stałe okno 128/32 + nagłówek | +0,031 | [−0,061; +0,133] | 5 | 5 |
| bloki łączone do 256 | +0,000 | [−0,102; +0,102] | 5 | 5 |
| rekurencyjny 256 | +0,051 | [−0,051; +0,163] | 7 | 4 |
| kod i tabele w całości 128/32 | −0,010 | [−0,082; +0,061] | 2 | 2 |

Skrypt: `experiments/02_summary.py`.

Dwa warianty mają przedział ufności nieobejmujący zera: okno 128 bez zakładki i z zakładką 50 procent. Pokusa jest oczywista – wziąć któryś i ogłosić plus 0,08. Nie zrobię tego z dwóch powodów. Po pierwsze, to **dwa wybrane wyniki z dwunastu przetestowanych**; kto sprawdza dwanaście hipotez i raportuje przedział ufności najlepszej, ten nie liczy już prawdopodobieństwa pomyłki, tylko je ukrywa. Po drugie, ich zysk (0,082) jest mniejszy niż rozstęp, który produkuje samo przesunięcie granic (0,133), a mechanizmu, dla którego zakładka 0 i 50 procent wygrywa, a 25 procent przegrywa, nie umiem nazwać – bo go nie ma. To kupony tej samej loterii.

Dlatego decyzja projektowa nie jest podjęta na podstawie recall@5, i to jest w tym rozdziale najważniejsze zdanie.

```python
PROJECT_EMBEDDER = "intfloat/multilingual-e5-small"
BETTER_EMBEDDER = "intfloat/multilingual-e5-base"   # +0,07 recall@5, 768 dims, 1,1 GB


def project_chunks(sections: list[Section], tokenizer) -> list[Chunk]:
    """The chapter 1 window over prose, whole fenced code blocks and whole Markdown tables."""
    return code_aware_window_chunks(sections, tokenizer, window=128, overlap=32)
```

`project_chunks` zostawia okno 128/32 z rozdziału 1 tam, gdzie jest proza, i zmienia dokładnie jedną rzecz: **blok kodu i tabela Markdown trafiają do indeksu w całości**, z doklejonym akapitem, który je wprowadza, a blok dłuższy niż 512 tokenów jest cięty po pustych liniach, a nie ucinany po cichu przez model. Daje 1283 chunki (1092 prozy, 174 kodu, 17 tabel), recall@5 0,71 i recall@20 0,96 – czyli w średniej **nie poprawia niczego**, minus 0,010 przy przedziale [−0,082; +0,061].

Wybieram to mimo tej liczby, z trzech powodów, z których żaden nie jest średnią. Po pierwsze, jedyne pytanie, które w rozdziale 1 nie miało trafienia nawet w top-20 – q039, „jak sprawdzić, czy zapytanie wygenerowane przez model można bezpiecznie puścić na bazę” – jest teraz na **trzecim miejscu**, bo blok kodu z walidacją SQL-a przez `sqlglot` przestał być ciągiem urwanych nazw funkcji, a stał się jednym fragmentem poprzedzonym akapitem po polsku. To mechanizm, który umiem nazwać, i naprawia klasę błędów, a nie jedno pytanie. Po drugie, chunk z całą funkcją i całą tabelą jest tym, czego potrzebują następne rozdziały: BM25 z rozdziału 3 dopasowuje identyfikatory rozdarte przez granicę okna, a rozdział 5 zajmie się tabelami, których wiersze bez nagłówka nie znaczą nic. Po trzecie, recall@20 zostaje na 0,96, najwyższym wyniku wśród zmierzonych chunkerów – a to sufit dla rerankingu z rozdziału 3 i metryka, którą teraz najbardziej warto chronić.

Płacę za to uczciwie: q037 („jak zbudować bramkę, która nie przepuści wdrożenia po spadku jakości”) wypada z dwudziestki, a q027, pytanie o cenę z tabeli w rozdziale 14, spada z piątki, bo cała tabela w jednym chunku rozmywa wiersz, o który pytam. Oba przypadki są zadaniem dla rozdziałów 3 i 5, a nie dla chunkera.

| Wariant | Chunków | Tokeny w prompcie @5 | recall@5 | recall@20 | MRR@5 | nDCG@5 | precision@5 | Bez trafienia |
|---|---|---|---|---|---|---|---|---|
| rozdz. 1: stałe okno 128/32 | 1550 | 620 | 0,72 | 0,96 | 0,67 | 0,64 | 0,38 | 9 |
| rozdz. 2: `project_chunks` | 1283 | 668 | 0,71 | 0,96 | 0,66 | 0,64 | 0,33 | 10 |
| `project_chunks` + e5-base (poza projektem) | 1283 | 699 | 0,79 | 0,94 | 0,67 | 0,65 | 0,38 | 5 |

Skrypt: `experiments/02_summary.py`.

Trzeci wiersz pokazuje, ile daje sam model przy chunkerze, który zostaje w projekcie: recall@5 0,79 zamiast 0,71 i pięć porażek zamiast dziesięciu. Zwróć uwagę, że to mniej niż 0,88, które e5-base osiągnął przy oknie 128 bez zakładki – bo kupon loterii jest losowany osobno dla każdej pary chunker-model. Rzetelne podsumowanie brzmi więc tak: ta sama loteria cięcia rozdaje na e5-small wyniki od 0,71 do 0,85, a na e5-base od 0,77 do 0,85, przy czym e5-base sięga 0,88 tam, gdzie e5-small kończy na 0,81. Przesuwa się cały rozkład, a nie pojedynczy pomiar, i tylko takiemu przesunięciu warto wierzyć.

Model `multilingual-e5-base` wygrywa w tym rozdziale wszystko, ale **nie wchodzi do projektu**, bo cała książka mierzy się na `multilingual-e5-small` i zmiana modelu unieważniłaby liczby z rozdziałów 1 oraz 5–8, które już powstały. To jest decyzja redakcyjna, nie inżynierska, i chcę, żeby była widoczna jako taka. W Twoim projekcie zrób odwrotnie: zanim spędzisz tydzień na strojeniu chunkera, wydaj godzinę na porównanie trzech modeli embeddingowych, bo to tam leżą punkty procentowe. Stała `BETTER_EMBEDDER` w `ragbook/chunking.py` jest gotowa – zmiana jednej linii i reindeksacja.

Jest jeszcze jedna rzecz, której chunkerowi nie wolno zepsuć: **metadane**. Każdy `Chunk` w `ragbook` niesie `chapter` i `section`, i na tym stoi ewaluacja całego tomu, filtrowanie z rozdziału 4, cytowanie z rozdziału 6 i przyrostowa reindeksacja z rozdziału 8. Dlatego wszystkie chunkery w tym rozdziale mają identyczny kontrakt: biorą `list[Section]`, zwracają `list[Chunk]` i mogą dowolnie zmieniać to, jak tekst jest pocięty, poprzedzony i ucięty, ale nigdy tego, do której sekcji fragment należy. Pisząc własny chunker, ustaw ten kontrakt jako pierwszy i napisz do niego test – inaczej błąd w propagacji metadanych zobaczysz dopiero jako niewytłumaczalny spadek recall.

Z dziewięciu porażek rozdziału 1 ten rozdział naprawia **jedną: q039**. Osiem zostaje i mają już przypisanych właścicieli. **q022** (nazwa `clear_tool_uses_20250919`) i **q021** (pole `metadata.user_id`) to identyfikatory, których model gęsty nie zna – rozdział 3, hybryda z BM25. **q007**, **q029** i **q033** to parafrazy bez wspólnych słów z tekstem – rozdział 4, przekształcenia zapytania. **q023** (limit 25 MB w środku sekcji „Audio”) i **q037** to konkret utopiony wśród sąsiadów, który powinien wypłynąć po rerankingu – rozdział 3. **q032** wymaga dwóch sekcji z dwóch różnych rozdziałów naraz – rozdziały 3 i 4, dywersyfikacja i multi-query. Żadna z nich nie jest już problemem chunkingu i to też jest wynik tego rozdziału.

## Podsumowanie

- Rozmiar okna ma znaczenie tylko na krańcach: 512 tokenów jest wyraźnie złe (recall@5 0,61–0,65, piętnaście porażek), a 64, 128 i 256 tworzą płaskowyż, na którym różnice są mniejsze niż szum. Zakładka nie ma czytelnego wpływu przy żadnym rozmiarze okna.
- Samo przesunięcie granic cięcia o kilkanaście tokenów – ta sama strategia, ten sam model, ta sama liczba chunków – daje rozstęp recall@5 równy 0,133, czyli więcej, niż wygrywa którakolwiek technika w tym rozdziale. MRR@5 zmienia się przy tym o 0,029, więc gdy obie metryki się rozjeżdżają, wierz MRR.
- „Sekcja jako chunk” traci 60 procent korpusu, bo 80 ze 131 sekcji jest dłuższych niż 512 tokenów i model ucina je bez ostrzeżenia; recall@20 spada z 0,96 do 0,72, czyli odpowiedzi fizycznie nie ma w indeksie.
- Podział rekurencyjny podnosi pytania proceduralne z 0,62 na 0,79, bo mieści całą procedurę w jednym chunku, ale obniża MRR i pytania porównawcze; podział semantyczny kosztuje dodatkowe zaembedowanie 3348 zdań (drugie tyle tokenów co korpus) i nie daje nic ponad baseline.
- Contextual chunk headers na jednorodnym tematycznie korpusie **nie działają**: pięć pytań w górę, pięć w dół, recall@20 spada z 0,96 do 0,91. Doklejenie tego samego nagłówka do wszystkich chunków sekcji zbliża ich wektory do siebie zamiast je rozróżniać. Tanie przybliżenie contextual retrieval (nagłówek plus pierwsze zdanie sekcji) jest jeszcze gorsze: 0,60–0,65.
- Parent-child nie zmienia metryk retrievalu z definicji, zmienia rachunek: rodzic-akapit kosztuje dwa razy więcej tokenów w prompcie niż dziecko, rodzic-sekcja pięć razy, a deduplikacja rodziców ścina ten ostatni koszt o 27 procent.
- Zamiana modelu z `multilingual-e5-small` na `multilingual-e5-base` daje recall@5 0,88 zamiast 0,81, MRR 0,79 zamiast 0,67 i dwie porażki zamiast pięciu, a do tego zawęża rozstęp loterii cięcia z 0,133 do 0,082. Prefiksy `query:`/`passage:` są warte 0,06 recall i trzy porażki; MiniLM z limitem 128 tokenów przy oknie 256 spada do 0,58.
- W projekcie zostaje `project_chunks`: okno 128/32 na prozie plus bloki kodu i tabele w całości. Wybrane nie za średnią (−0,010), tylko za mechanizm – naprawia q039, jedyne pytanie bez trafienia w top-20 – i za to, że utrzymuje recall@20 na 0,96, który jest sufitem dla rerankingu z rozdziału 3.

## Co dalej

Rozdział 3 zajmie się tym, czego chunking zrobić nie mógł. Osiem z dziewięciu porażek rozdziału 1 wciąż tam jest, a recall@20 równy 0,96 mówi, że odpowiedź niemal zawsze **jest** w dwudziestce kandydatów – tylko nie na górze. To dokładnie sytuacja, w której opłaca się dołożyć drugi sygnał i drugi etap: BM25, które trafia `clear_tool_uses_20250919` bezbłędnie tam, gdzie model gęsty nie ma pojęcia, fuzję RRF łączącą obie listy i reranking cross-encoderem, który z dwudziestu kandydatów wybiera pięć, patrząc na pytanie i fragment naraz, a nie na dwa wektory osobno. Zanim tam przejdziesz, uruchom u siebie `experiments/02_alignment.py` i popatrz, jak siedem liczb rozjeżdża się o 0,13 bez żadnego powodu – to jedyna znana mi szczepionka przeciw wierze w trzecią cyfrę po przecinku.

## Źródła

- https://huggingface.co/intfloat/multilingual-e5-small
- https://huggingface.co/intfloat/multilingual-e5-base
- https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- https://www.anthropic.com/news/contextual-retrieval
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/api/messages
- https://sbert.net/docs/sentence_transformer/usage/usage.html
