# Rozdział 2. Chunking i model embeddingowy z pomiarem

> **Cel rozdziału:** zmierzyć na zamrożonym zestawie wszystkie popularne strategie cięcia dokumentu i trzy modele embeddingowe, odróżnić rzeczywisty zysk od losu, i zdecydować, co zostaje w projekcie.
>
> **Kod:** `ragbook/chunking.py`, `experiments/02_chunking.py`, `02_alignment.py`, `02_structure.py`, `02_context.py`, `02_embedders.py`, `02_summary.py`. **Pakiety poza fundamentem:** brak.

Rozdział 1 skończył się listą dziewięciu pytań, na które naiwny baseline nie znajduje niczego trafnego w czołowej piątce. Jedno jest gorsze od pozostałych: „Jak sprawdzić, czy zapytanie wygenerowane przez model można bezpiecznie puścić na bazę?” nie ma trafienia nawet w dwudziestce kandydatów. A odpowiedź w korpusie jest – walidacja SQL-a na drzewie składniowym przez `sqlglot`, w sekcji „Dobre praktyki” rozdziału 11 tomu 1, bo to tom 1 tej serii jest korpusem naszego projektu.

Zniknęła z powodu, który nie ma nic wspólnego ani z modelem, ani z bazą. Chunker tnie tekst co 128 tokenów i nie patrzy, co tnie. Blok kodu rozpada się na kawałki będące ciągami nazw funkcji urwanymi w połowie wiersza; żaden nie leży blisko pytania po polsku, bo w żadnym nie ma polskiego zdania. A zdania prozy, które ten blok wprowadzają, konkurują z kilkudziesięcioma sąsiadami z tej samej, bardzo długiej sekcji. Fakt jest w indeksie i jest nieosiągalny.

Chunking to najtańsza rzecz do zmiany w całym potoku RAG: nie wymaga nowego modelu, nowej bazy ani jednego wywołania API. Dlatego zaczynamy od niego. Uprzedzę zakończenie, bo to uczciwsze niż budowanie napięcia przez dwanaście stron: żadna ze strategii cięcia zmierzonych w tym rozdziale nie poprawia wyniku w sposób, który przetrwa kontrolę. Poprawia go natomiast zamiana modelu embeddingowego na dwa razy większy.

Snippety uruchamiasz z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/02_chunking.py`. Zestaw pytań jest ten sam co w rozdziale 1. Metryka główna też: recall@5, czyli czy właściwa sekcja jest wśród pięciu fragmentów wkładanych do promptu.

## Rozmiar okna i zakładka

Rozmiar okna to parametr, który w każdym tutorialu ustawia się „na oko”, a w każdą stronę boli inaczej. Za duże okno robi z jednego wektora średnią trzech akapitów o różnych rzeczach, a taka średnia nie leży blisko żadnego z nich. Za małe daje fragmenty, których nie da się przeczytać bez sąsiadów: pół zdania, sam wiersz tabeli, sama sygnatura funkcji. Zakładka (overlap) ma być lekarstwem na to drugie: kolejne okno zaczyna się kilkanaście tokenów przed końcem poprzedniego, więc zdanie przecięte na granicy zachowuje się w całości w jednym z nich. Sprawdziłem cztery rozmiary okna po trzy zakładki, na tym samym zestawie pytań i tym samym `k`.

| Okno (bez zakładki) | Chunków | Tokeny w prompcie @5 | recall@5 | Bez trafienia |
|---|---|---|---|---|
| 64 | 2364 | 314 | 0,72 | 9 |
| 128 | 1213 | 612 | 0,81 | 5 |
| 256 | 636 | 1207 | 0,76 | 7 |
| 512 | 347 | 2066 | 0,62 | 15 |

Skrypt: `experiments/02_chunking.py`; pełną siatkę dwunastu wariantów z zakładkami wypisuje ten sam skrypt.

Wniosek jest jeden i jest twardy: okno 512 tokenów jest wyraźnie złe. Recall spada do 0,61–0,65 niezależnie od zakładki, a pytań bez trafienia robi się kilkanaście zamiast dziewięciu. Mechanizm widać gołym okiem: takich chunków jest w całym korpusie 347, więc czołowa piątka to trzynaście procent indeksu – to już nie wyszukiwanie, tylko grube przybliżenie. Rozmiary 64, 128 i 256 tworzą płaskowyż, na którym różnice są znacznie mniejsze niż odległość do 512. Zakładka nie ma czytelnego wpływu: wyniki skaczą w obie strony bez wzoru, a gdyby stał za nią mechanizm ratowania przeciętych zdań, powinna pomagać podobnie przy każdym rozmiarze okna.

Druga kolumna to koszt, i to jedyna liczba, która w tej tabeli zachowuje się przewidywalnie. „Tokeny w prompcie @5” to prawdziwa średnia długość pięciu zwracanych fragmentów, a nie iloczyn `k` razy rozmiar okna: podwojenie okna podwaja rachunek za wejście do modelu generującego, a w rozmowie wielotorowej także za wszystkie kolejne tury (tom 1, rozdział 4). Indeks zachowuje się odwrotnie, ale w naszej skali to pół megabajta przeciwko sześciu i pół, czyli nic.

Jeżeli musisz wybrać rozmiar okna dziś, bez zestawu ewaluacyjnego: weź okno mniej więcej cztery razy krótsze niż limit wejścia modelu i policz je tokenizerem tego modelu, a nie w znakach. Przy e5 z limitem 512 wychodzi 128. Przy modelu z limitem 8192 wyszłoby 2000, ale wtedy ogranicza Cię już nie model, tylko prompt: pięć razy 2000 tokenów to dziesięć tysięcy tokenów wejścia na jedno pytanie. Górną granicę wyznacza budżet promptu, dolną to, żeby fragment dało się przeczytać bez sąsiadów.

Zanim jednak ogłosisz, że okno 128 bez zakładki wygrywa z baseline'em o 0,09, zrób eksperyment z następnej sekcji.

## Ile kosztuje samo miejsce cięcia

Wyobraź sobie, że tniesz gazetę na paski równej szerokości. Przesuń linijkę o dwa centymetry i potniesz tę samą stronę w tych samych odstępach, tylko w innych miejscach – a zdanie, które przedtem mieściło się w środku paska, teraz leży w poprzek dwóch i nie ma go w całości nigdzie. Dokładnie to robi chunker, gdy przesuniesz początek cięcia.

Wziąłem więc baseline z rozdziału 1 – okno 128, zakładka 32 – i nie zmieniłem w nim nic poza jednym: pierwsze cięcie w każdej sekcji zaczyna się o kilkanaście tokenów dalej. Ta sama strategia, ten sam rozmiar, ta sama zakładka, ten sam model, niemal ta sama liczba chunków. Zmienia się wyłącznie to, w którym miejscu tekstu wypadają granice – czyli rzecz, której w żadnym artykule o chunkingu się nie opisuje, bo nie jest decyzją.

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

| Przesunięcie | Chunków | recall@5 | MRR@5 | Bez trafienia |
|---|---|---|---|---|
| 0 | 1550 | 0,72 | 0,67 | 9 |
| 16 | 1656 | 0,71 | 0,67 | 10 |
| 32 | 1637 | 0,80 | 0,66 | 5 |
| 48 | 1616 | 0,76 | 0,66 | 7 |
| 80 | 1570 | 0,85 | 0,64 | 4 |
| 96 | 1550 | 0,72 | 0,67 | 9 |

Skrypt: `experiments/02_alignment.py` (liczy siedem przesunięć, w tabeli jest sześć).

Rozstęp recall@5 wynosi 0,133 i nie stoi za nim żadna decyzja projektowa. Ostatni wiersz jest tu kontrolą poprawności: przesunięcie o 96 tokenów daje dokładnie te same liczby co brak przesunięcia, bo krok okna wynosi 96 i cięcia wracają na swoje miejsca. Wszystko pomiędzy jest losowaniem. Dla porównania: najlepszy wariant z dwunastoelementowej siatki z poprzedniej sekcji wygrywał z baseline'em o 0,082, czyli o dwie trzecie tego, co potrafi wylosować samo przesunięcie granicy.

Skąd bierze się taki rozstęp przy metryce liczonej z czterdziestu dziewięciu pytań? Stąd, że recall@5 jest metryką progową. Fragment z właściwej sekcji stoi na szóstym miejscu i pytanie ma zero; przesuwasz granicę, fragment zyskuje pół zdania kontekstu, przeskakuje na piąte – i pytanie ma jeden, całym skokiem. Kilka takich przeskoków na czterdziestu dziewięciu pytaniach robi 0,1 recall. MRR@5, czyli miara tego, jak wysoko stoi pierwsze trafienie, przy tych samych siedmiu wariantach mieści się w rozstępie 0,029, pięć razy węższym – bo przeskok z szóstego miejsca na piąte zmienia ją o trzy setne, a nie o jedynkę. Stąd reguła na resztę tomu: raportuj obie metryki, a gdy się rozjeżdżają, wierz tej stabilniejszej.

To jest kontekst dla całej reszty rozdziału i dla każdego porównania chunkerów, jakie przeczytasz gdziekolwiek indziej. Jeżeli ktoś pokazuje, że jego strategia cięcia daje o 0,05 lepszy recall, a nie pokazuje, ile daje przesunięcie granic o dwadzieścia tokenów w jego własnej strategii, to nie wiesz, czy patrzysz na technikę, czy na szczęśliwy los. Reguła z rozdziału 1 – patrz, ile pytań zmieniło wynik, i sprawdź, czy umiesz nazwać mechanizm – przestaje tu być radą metodologiczną i staje się jedynym narzędziem, jakie masz.

## Podział po strukturze Markdown

Skoro miejsce cięcia losowane w ciemno kosztuje tyle, warto przestać je losować. Dokumentacja ma granice, których nie trzeba zgadywać: nagłówki, akapity, bloki kodu, tabele. `split_blocks` rozbija sekcję właśnie po nich – blok otoczony ogrodzeniem z trzech znaków wstecznego apostrofu zostaje w całości, a reszta rozdziela się po pustych liniach, co samo z siebie utrzymuje tabelę i listę w jednym kawałku.

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

Dziewięćset cztery bloki na 131 sekcji, w tym 156 bloków kodu – to cała mapa korpusu i punkt wyjścia dla czterech wariantów: sekcja jako chunk, blok jako chunk, bloki sklejane do budżetu tokenów i podział rekurencyjny.

| Wariant | Chunków | recall@5 | MRR@5 | Bez trafienia |
|---|---|---|---|---|
| stałe okno 128/32 (baseline) | 1550 | 0,72 | 0,67 | 9 |
| sekcja = chunk (ucięta do 512) | 131 | 0,47 | 0,38 | 22 |
| bloki łączone do 256 | 691 | 0,72 | 0,62 | 9 |
| rekurencyjny 256 | 780 | 0,78 | 0,60 | 7 |

Skrypt: `experiments/02_structure.py`; wypisuje też warianty pośrednie – blok jako chunk oraz bloki łączone do 128 i 384 tokenów.

Drugi wiersz to jedyna katastrofa w tym rozdziale i najczęstszy cichy błąd początkującego. „Sekcja jako chunk” brzmi rozsądnie: sekcja jest jednostką trafności, niech będzie jednostką indeksu. Tyle że sekcje w tym korpusie mają medianę 667 tokenów, a `multilingual-e5-small` czyta 512. Osiemdziesiąt ze 131 sekcji jest dłuższych niż limit modelu, więc do indeksu trafia 59 070 ze 146 791 tokenów korpusu, a reszta znika bez ostrzeżenia. Recall@20 spada z 0,96 do 0,72: dla jednego pytania na cztery odpowiedzi nie ma nawet w dwudziestce, bo fizycznie nie ma jej w indeksie.

Reszta tabeli to płaskowyż z jednym odchyleniem w górę. Podział rekurencyjny – najgrubsza dostępna granica, schodzenie niżej tylko wtedy, gdy kawałek nadal jest za długi – ma naraz najwyższy recall i najniższy MRR, czyli wpuszcza trafną sekcję do piątki częściej, ale niżej. Rozbicie po typach mówi dlaczego: pytania proceduralne skaczą z 0,62 na 0,79, bo chunk o dwustu tokenach mieści całą procedurę, gdy okno 128-tokenowe łapie jeden krok bez kontekstu. W drugą stronę spadają porównawcze, bo większe chunki to mniej różnych sekcji w piątce. To pierwszy wynik z nazwanym mechanizmem – i za słaby, żeby przejść test z poprzedniej sekcji, bo 0,051 średniej to mniej niż rozstęp samego losowania granic.

Struktura daje jeszcze jedną korzyść, której ten zestaw pytań nie umie zmierzyć, a która zadecyduje o wyborze na końcu rozdziału: chunk pokrywający się z blokiem Markdown da się pokazać użytkownikowi. Zaczyna się od początku akapitu, kończy kropką, a jeśli jest kodem, to kompilowalnym. Metryka liczona po sekcjach jest na to ślepa z definicji.

Jedyna istotna różnica między naszym podziałem rekurencyjnym a tym, który znasz z `RecursiveCharacterTextSplitter` w LangChainie, siedzi w pierwszej linii funkcji: długość liczymy tokenizerem modelu embeddingowego, a nie w znakach.

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

Przy polszczyźnie wychodzi 2,3 tokena na słowo (rozdział 1), więc limit liczony w znakach przepuści do indeksu chunki dłuższe niż limit modelu – patrz katastrofa powyżej.

Wynik negatywny na koniec tej sekcji: podział semantyczny. Nie pyta dokumentu o granice, tylko sam je wyznacza – embeduje kolejne zdania, liczy kosinus między sąsiadami i tnie tam, gdzie podobieństwo spada najmocniej (próg bierzemy z rozkładu, bo kosinusy z rodziny E5 układają się ciasno między 0,7 a 1,0).

```python
from ragbook.chunking import semantic_chunks

chunks = semantic_chunks(sections, embedder, max_tokens=256, percentile=80.0)
print(len(chunks), "chunków, próg odległości", round(chunks[0].meta["threshold"], 3))
```

Nie zadziałał, a kosztuje podwójnie: korpus rozpada się na 3348 zdań o łącznej długości równej całemu korpusowi, więc chunker embeduje wszystko raz dodatkowo, zanim powstanie pierwszy chunk, i płacisz to przy każdej reindeksacji. W zamian daje 0,73 przy progu p80 i 0,68 przy p90, czyli tyle samo co baseline albo mniej. Powód jest banalny i wart zapamiętania: dokumentacja jest już podzielona przez autora na akapity, a akapit jest lepszą granicą tematyczną niż próg na kosinusie. Semantyczny chunking ma sens tam, gdzie granic nie ma – w transkrypcjach rozmów, w skanach bez struktury, w długich mailach.

## Contextual chunk headers

Fragment wycięty ze środka sekcji nie wie, gdzie jest. Zdanie „ponawiamy pięć razy z wykładniczym backoffem” nie mówi, czego dotyczy, a jego wektor leży blisko wszystkiego, co mówi o ponawianiu. Najtańsza naprawa to doklejenie tytułu rozdziału i nagłówka sekcji przed treść chunku, zanim policzysz wektor. Robi to `with_context_headers`, zachowując oryginalną treść w `meta["body"]`, żeby do promptu trafił czysty tekst bez nagłówka.

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

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| stałe okno 128/32 | 0,72 | 0,96 | 9 |
| 128/32 + nagłówek | 0,76 | 0,91 | 7 |
| stałe okno 128/0 | 0,81 | 0,94 | 5 |
| 128/0 + nagłówek | 0,76 | 0,91 | 8 |
| 128/0 + nagłówek + 1. zdanie sekcji | 0,60 | 0,80 | 15 |

Skrypt: `experiments/02_context.py`; mierzy nagłówki także na blokach łączonych i na chunkerze rekurencyjnym.

Contextual chunk headers są techniką polecaną w internecie najczęściej ze wszystkich opisanych w tym rozdziale i na naszym korpusie nie działają. Podnoszą wynik jednej konfiguracji z czterech zmierzonych i obniżają trzy pozostałe; porównanie parami wobec baseline'u daje pięć pytań w górę i pięć w dół, czyli definicję szumu, a recall@20 spada za każdym razem. Mechanizm porażki dotyczy każdego korpusu jednorodnego tematycznie: nagłówek dokleja kilkanaście tokenów identycznych dla wszystkich chunków tej samej sekcji i bardzo podobnych w obrębie rozdziału, więc wektory zbliżają się do siebie, zamiast się różnicować, a sekcje o podobnych tytułach konkurują ze sobą tytułem, a nie treścią. Zysk pojawia się tylko tam, gdzie pytanie jest sformułowane terminami z nagłówka: faktograficzne rosną z 0,81 na 0,88, proceduralne spadają. Na korpusie zbudowanym z dokumentów wielu klientów nagłówek „Acme / Limity zapytań” niósłby informację różnicującą i wynik byłby inny; u nas wszystkie dokumenty są o jednym.

Ostatni wiersz to tanie przybliżenie contextual retrieval: zamiast prosić model o opis fragmentu, doklejamy pierwsze zdanie sekcji, czyli to, co autor sam napisał jako wprowadzenie. Kosztuje zero i jest gorsze za każdym razem, przy oknie bez zakładki aż o 0,21 – bo te same trzydzieści tokenów przy kilkudziesięciu chunkach sekcji sprawia, że przestają się one różnić właśnie w tym, co w nich najważniejsze. Prawdziwą technikę przybliża to tylko w jednym wymiarze: kosztu.

## Contextual retrieval z LLM-em

Prawdziwa technika opisana przez Anthropic robi jedną rzecz inaczej i ta jedna rzecz jest kluczowa. Tani model dostaje cały dokument i jeden chunk, po czym pisze jedno–dwa zdania umieszczające ten fragment w całości; opis dokleja się przed treścią przed embedowaniem. Jest więc różny dla każdego chunku, czyli rozsuwa wektory zamiast je spłaszczać – dokładna odwrotność tego, co zepsuło nasze tanie przybliżenie. Anthropic raportuje spadek odsetka nieudanych wyszukiwań w top-20 o 35 procent dla samych embeddingów kontekstowych i o 49 procent w połączeniu z kontekstowym BM25.

Ekonomia stoi tu w całości na prompt cachingu: bez niego wysyłasz cały rozdział raz na każdy chunk, czyli u nas dziewięćdziesiąt razy.

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

Dwie liczby sprawdź w dokumentacji, zanim policzysz budżet (stan na wrzesień 2026). Minimalna długość prefiksu, który w ogóle wejdzie do cache'u, dla Claude Haiku 4.5 wynosi 4096 tokenów; krótszy dokument nie zostanie zapisany i nie dostaniesz o tym błędu, a jedynym sygnałem jest `cache_creation_input_tokens` równe zeru. Nasz najkrótszy rozdział leży tuż nad tym progiem, więc trzeba przeczytać `usage`, a nie zakładać. Druga liczba przesądza o opłacalności całej techniki: odczyt z cache'u kosztuje 0,1 stawki wejściowej, a zapis 1,25 raza tej stawki przy domyślnym czasie życia wpisu (pięć minut) i 2 razy przy godzinnym, który ustawia snippet.

Nie mam klucza API, więc tej techniki nie zmierzyłem i nie wstawiam jej do tabeli zbiorczej. Spodziewam się, że zadziałałaby lepiej niż tanie przybliżenie, ale słabiej niż u Anthropic: ich korpusy testowe to bazy kodu i dokumenty wielu podmiotów, gdzie zdanie „to fragment raportu ACME za drugi kwartał” niesie ogromną informację różnicującą, a u nas każdy chunk pochodzi z tej samej książki. Jeżeli masz klucz, uruchom `ragbook.chunking.contextualize` na 1283 chunkach projektu i zmierz wynik tym samym `experiments/02_summary.py`.

## Parent-child: mały chunk do wyszukiwania, duży do promptu

Small-to-big rozdziela dwie rzeczy, które stałe okno skleja: czym wyszukujesz i co czytasz. Indeksujesz małe, precyzyjne fragmenty, bo one dają ostre dopasowanie wektorowe, ale do promptu wkładasz rodzica – akapit albo całą sekcję, z której dziecko pochodzi. To jedno pole w metadanych i cienka nakładka na retriever.

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

Metryki retrievalu nie mogą się przy tym zmienić i nie zmieniają się, bo trafność liczymy po sekcji dziecka, a podmiana tekstu wkładanego do promptu jej nie dotyka. Zmienia się wyłącznie rachunek.

| Co trafia do promptu | Tokeny w prompcie @5 | recall@5 | Bez trafienia |
|---|---|---|---|
| samo dziecko (128 tokenów) | 490 | 0,66 | 12 |
| rodzic-akapit | 1002 | 0,66 | 12 |
| rodzic-sekcja | 2462 | 0,76 | 8 |
| rodzic-sekcja, z deduplikacją | 1804 | 0,76 | 8 |

Skrypt: `experiments/02_context.py`.

Cała decyzja sprowadza się do pierwszej kolumny: rodzic-akapit kosztuje dwa razy więcej tokenów niż samo dziecko, rodzic-sekcja pięć razy. Deduplikacja, czyli wstawienie rodzica tylko raz, gdy dwoje dzieci z tej samej sekcji trafi do piątki, ścina rachunek za rodzica-sekcję o 27 procent; przy rodzicu-akapicie nie daje prawie nic, bo dwoje dzieci rzadko pochodzi z jednego akapitu. Wariantem tej samej idei jest okno zdaniowe – indeksujesz zdanie, a do promptu wkładasz je z dwoma zdaniami przed i dwoma po – i przy akapitach dłuższych niż nasze to dobry pierwszy wybór.

Kiedy to się opłaca: gdy pytania są proceduralne, a dziecko pokazuje tylko jeden krok procedury, albo gdy generacja ma cytować i potrzebuje zdania przed i po. Kiedy nie: gdy sekcje są długie i niejednorodne, bo wkładasz wtedy do promptu trzy akapity o czymś innym, żeby dowieźć jeden właściwy, i płacisz podwójnie – tokenami i rozproszoną uwagą modelu (tom 1, rozdział 4). Na naszym korpusie, z medianą sekcji 667 tokenów, rodzic-sekcja jest za drogi, a rodzic-akapit byłby rozsądnym kompromisem, gdyby dziecko wygrywało cokolwiek w metrykach. Nie wygrywa.

## Model embeddingowy, prefiksy i czas

Do tej pory zmienialiśmy wszystko oprócz modelu. Zmieńmy model, zostawiając chunker w spokoju: te same okna 128-tokenowe bez zakładki, ten sam zestaw pytań, ten sam `k`.

| Model i okno | Limit wejścia | recall@5 | MRR@5 | Bez trafienia |
|---|---|---|---|---|
| `multilingual-e5-small`, 128 | 512 | 0,81 | 0,67 | 5 |
| `multilingual-e5-small`, 256 | 512 | 0,76 | 0,64 | 7 |
| `MiniLM-L12-v2`, 128 | 128 | 0,68 | 0,56 | 10 |
| `MiniLM-L12-v2`, 256 | 128 | 0,58 | 0,47 | 16 |
| `multilingual-e5-base`, 128 | 512 | **0,88** | **0,79** | **2** |

Skrypt: `experiments/02_embedders.py`.

To jest najważniejsza tabela w rozdziale. `multilingual-e5-base` – dwanaście warstw, 768 wymiarów, ten sam limit wejścia co e5-small – zostawia tylko dwa pytania bez trafienia zamiast pięciu, a w przeciwieństwie do wszystkiego wcześniej rośnie przy tym również ta stabilniejsza metryka. Płacisz 1,1 gigabajta wag zamiast 0,47 i dwa razy większym indeksem (3,55 zamiast 1,78 megabajta, bo rozmiar indeksu to wymiar wektora razy liczba chunków razy cztery bajty).

Żeby sprawdzić, czy to nie kolejna wygrana na loterii, powtórzyłem eksperyment z przesuwaniem granic na e5-base. Rozstęp recall@5 spada z 0,133 do 0,082, a cały przedział przesuwa się w górę: najgorsze losowanie na e5-base (0,765) jest lepsze niż mediana losowań na e5-small (0,755). Lepszy model nie tylko podnosi wynik, ale też uodparnia go na to, gdzie wypadnie cięcie – bo model, który lepiej rozumie kontekst, mniej potrzebuje, żeby fakt leżał akurat w środku chunku.

Trzeci model przegrywa pouczająco. `paraphrase-multilingual-MiniLM-L12-v2` ma ten sam wymiar wektora co e5-small, a przy oknie 128 wypada o 0,13 gorzej. Przy oknie 256 spada do 0,58, bo jego `max_seq_length` wynosi 128 tokenów i połowa każdego chunku jest po cichu ucinana – ta sama pułapka co „sekcja jako chunk”, tylko z drugiej strony. Porównaj wiersz drugi z czwartym: identyczne chunki, identyczny wymiar, cała różnica to limit wejścia i jakość treningu. Limit długości wejścia jest twardym parametrem architektury indeksu, a nie szczegółem z karty modelu (tom 1, rozdział 6).

Osobno mierzę prefiksy `query:` i `passage:`, które rodzina E5 wymaga na każdym tekście. Bez nich recall@5 spada z 0,81 do 0,74, a pytań bez trafienia robi się osiem zamiast pięciu (skrypt: `experiments/02_embedders.py`). Sześć setnych za dwa opuszczone łańcuchy znaków, o których karta modelu mówi wprost – i mimo to jeden z najczęstszych cichych błędów w projektach RAG, bo wszystko działa, tylko gorzej. Sprawdź w `ragbook/embed.py`, że słownik `_PREFIXES` obejmuje model, którego używasz: dla modeli spoza rodziny E5 wrapper zwraca puste prefiksy, co dla MiniLM-a jest poprawne, a dla `bge-m3` już niekoniecznie.

Na koniec czas, bo on decyduje o tym, ile wariantów zdążysz sprawdzić w ciągu dnia. Pomiar bez cache'u, ten sam korpus 1213 chunków:

| Model i urządzenie | Czas [s] | Tokenów/s |
|---|---|---|
| `multilingual-e5-small`, GPU (GTX 1650) | 6,0 | 24 331 |
| `multilingual-e5-small`, CPU | 30,3 | 4845 |
| `multilingual-e5-base`, GPU (GTX 1650) | 27,0 | 5433 |
| `multilingual-e5-base`, CPU | 160,5 | 915 |

Skrypt: `experiments/02_embedders.py`; mierzy także MiniLM-a, który wypada niemal identycznie jak e5-small.

E5-base jest pięć razy wolniejszy od e5-small po obu stronach, a przejście na kartę – nawet tak skromną jak GTX 1650 – daje pięciokrotne przyspieszenie. Przy naszym korpusie to pół minuty przeciwko trzem i nie ma znaczenia; przy milionie chunków to różnica między czterema godzinami a dobą, i wtedy koszt reindeksacji staje się argumentem przy wyborze modelu (tom 1, rozdział 6).

## Co zostaje w projekcie

Czas wybrać. Porównuję każdego kandydata z baseline'em pytanie po pytaniu, tak jak obiecywał rozdział 1: bootstrap na różnicach per pytanie jest znacznie węższy niż na średniej, bo większość pytań zachowuje się w obu wariantach tak samo i wnosi do różnicy zero.

| Wariant | recall@5 | Bez trafienia | Średnia różnica | 95% CI (parami) | W górę / w dół |
|---|---|---|---|---|---|
| stałe okno 128/32 (rozdz. 1) | 0,72 | 9 | – | – | – |
| stałe okno 128/0 | 0,81 | 5 | +0,082 | [+0,010; +0,163] | 6 / 1 |
| stałe okno 128/64 | 0,81 | 6 | +0,082 | [+0,020; +0,153] | 6 / 0 |
| stałe okno 128/32 + nagłówek | 0,76 | 7 | +0,031 | [−0,061; +0,133] | 5 / 5 |
| bloki łączone do 256 | 0,72 | 9 | +0,000 | [−0,102; +0,102] | 5 / 5 |
| rekurencyjny 256 | 0,78 | 7 | +0,051 | [−0,051; +0,163] | 7 / 4 |
| kod i tabele w całości 128/32 | 0,71 | 10 | −0,010 | [−0,082; +0,061] | 2 / 2 |

Skrypt: `experiments/02_summary.py`.

Dwa warianty mają przedział ufności nieobejmujący zera: okno 128 bez zakładki i z zakładką pięćdziesięcioprocentową. Pokusa jest oczywista – wziąć któryś i ogłosić plus 0,08. Nie zrobię tego z dwóch powodów. Po pierwsze, to dwa wybrane wyniki z dwunastu, a kto sprawdza dwanaście hipotez i raportuje przedział ufności najlepszej, ten nie liczy prawdopodobieństwa pomyłki, tylko je ukrywa. Po drugie, ich zysk jest mniejszy niż rozstęp samego przesunięcia granic, a mechanizmu, dla którego zakładka zerowa i pięćdziesięcioprocentowa wygrywa, a dwudziestopięcioprocentowa przegrywa, nie umiem nazwać, bo go nie ma.

Dlatego decyzja projektowa nie jest podjęta na podstawie recall@5, i to jest w tym rozdziale najważniejsze zdanie.

```python
PROJECT_EMBEDDER = "intfloat/multilingual-e5-small"
BETTER_EMBEDDER = "intfloat/multilingual-e5-base"   # +0,07 recall@5, 768 dims, 1,1 GB


def project_chunks(sections: list[Section], tokenizer) -> list[Chunk]:
    """The chapter 1 window over prose, whole fenced code blocks and whole Markdown tables."""
    return code_aware_window_chunks(sections, tokenizer, window=128, overlap=32)
```

`project_chunks` zostawia okno 128/32 z rozdziału 1 tam, gdzie jest proza, i zmienia dokładnie jedną rzecz: blok kodu i tabela Markdown trafiają do indeksu w całości, z doklejonym akapitem, który je wprowadza, a blok dłuższy niż 512 tokenów jest cięty po pustych liniach, a nie ucinany po cichu przez model. Daje 1283 chunki i w średniej nie poprawia niczego – ostatni wiersz tabeli powyżej to minus 0,010.

Wybieram to mimo tej liczby, z trzech powodów, z których żaden nie jest średnią. Po pierwsze, pytanie z początku rozdziału – to o bezpieczne puszczenie wygenerowanego SQL-a na bazę, jedyne bez trafienia nawet w dwudziestce (w `golden.jsonl` to `q039`) – jest teraz na trzecim miejscu, bo blok kodu z walidacją przestał być ciągiem urwanych nazw funkcji, a stał się jednym fragmentem poprzedzonym akapitem po polsku. To mechanizm, który umiem nazwać, i naprawia klasę błędów, a nie jedno pytanie. Po drugie, chunk z całą funkcją i całą tabelą jest tym, czego potrzebują następne rozdziały: BM25 z rozdziału 3 dopasowuje identyfikatory rozdarte przez granicę okna, a rozdział 5 zajmie się tabelami. Po trzecie, recall@20 zostaje na 0,96, czyli najwyżej wśród zmierzonych chunkerów – a to sufit dla rerankingu z rozdziału 3.

Płacę za to uczciwie: pytanie o bramkę jakości blokującą wdrożenie wypada z dwudziestki, a pytanie o cenę z tabeli w rozdziale 14 spada z piątki, bo cała tabela w jednym chunku rozmywa wiersz, o który pytam. Oba są zadaniem dla rozdziałów 3 i 5, a nie dla chunkera.

| Wariant | Tokeny w prompcie @5 | recall@5 | recall@20 | precision@5 | Bez trafienia |
|---|---|---|---|---|---|
| rozdz. 1: stałe okno 128/32 | 620 | 0,72 | 0,96 | 0,38 | 9 |
| rozdz. 2: `project_chunks` | 668 | 0,71 | 0,96 | 0,33 | 10 |
| `project_chunks` + e5-base (poza projektem) | 699 | 0,79 | 0,94 | 0,38 | 5 |

Skrypt: `experiments/02_summary.py`.

Trzeci wiersz pokazuje, ile daje sam model przy chunkerze, który zostaje w projekcie: pięć pytań bez trafienia zamiast dziesięciu. To mniej niż 0,88, które e5-base osiągnął przy oknie bez zakładki, bo kupon loterii jest losowany osobno dla każdej pary chunker-model. Ta sama loteria rozdaje na e5-small wyniki od 0,71 do 0,85, a na e5-base od 0,77 do 0,85 – przesuwa się cały rozkład, a nie pojedynczy pomiar, i tylko takiemu przesunięciu warto wierzyć.

Skoro tak, dlaczego lepszy model nie wchodzi do projektu? Bo cała książka mierzy się na `multilingual-e5-small`, a jego zmiana unieważniłaby liczby z rozdziału 1 i z rozdziałów 5–8, które już powstały. To decyzja redakcyjna, nie inżynierska, i chcę, żeby była widoczna jako taka. W Twoim projekcie zrób odwrotnie niż ja: zanim spędzisz tydzień na strojeniu chunkera, wydaj godzinę na porównanie trzech modeli embeddingowych. Stała `BETTER_EMBEDDER` w `ragbook/chunking.py` czeka gotowa – zmiana jednej linii i reindeksacja.

Jest jeszcze jedna rzecz, której chunkerowi nie wolno zepsuć: metadane. Każdy `Chunk` niesie `chapter` i `section`, a na tym stoi ewaluacja całego tomu, filtrowanie z rozdziału 4 i cytowanie z rozdziału 6. Dlatego wszystkie chunkery w tym rozdziale mają ten sam kontrakt: mogą dowolnie zmieniać to, jak tekst jest pocięty, ale nigdy tego, do której sekcji fragment należy. Napisz do tego kontraktu test, zanim napiszesz własny chunker – inaczej błąd w propagacji metadanych zobaczysz dopiero jako niewytłumaczalny spadek recall.

Z dziewięciu porażek rozdziału 1 ten rozdział naprawia jedną – tę od walidacji SQL-a. Osiem zostaje i mają już właścicieli. Dwie dotyczą identyfikatorów, których model gęsty nie zna: nazwy edycji kontekstu kasującej stare wyniki narzędzi i pola z identyfikatorem użytkownika w logach – zadanie dla hybrydy z BM25 z rozdziału 3. Trzy to parafrazy bez wspólnych słów z tekstem, czyli rozdział 4. Dwie to konkret utopiony wśród sąsiadów, który powinien wypłynąć po rerankingu. Ostatnia wymaga dwóch sekcji z dwóch różnych rozdziałów naraz. Żadna nie jest już problemem chunkingu i to też jest wynik tego rozdziału.

## Podsumowanie

- Rozmiar okna ma znaczenie tylko na krańcach: 512 tokenów jest wyraźnie złe (recall@5 0,61–0,65), a 64, 128 i 256 tworzą płaskowyż, na którym różnice są mniejsze niż szum. Zakładka nie ma czytelnego wpływu przy żadnym rozmiarze okna.
- Samo przesunięcie granic cięcia o kilkanaście tokenów – ta sama strategia, ten sam model – daje rozstęp recall@5 równy 0,133, czyli więcej, niż wygrywa którakolwiek technika w tym rozdziale. MRR@5 zmienia się przy tym o 0,029, więc gdy obie metryki się rozjeżdżają, wierz MRR.
- „Sekcja jako chunk” traci sześćdziesiąt procent korpusu, bo 80 ze 131 sekcji jest dłuższych niż limit modelu, a ten ucina je bez ostrzeżenia; recall@20 spada z 0,96 do 0,72, czyli odpowiedzi fizycznie nie ma w indeksie.
- Podział rekurencyjny podnosi pytania proceduralne z 0,62 na 0,79, bo mieści całą procedurę w jednym chunku, ale obniża MRR i pytania porównawcze. Podział semantyczny kosztuje dodatkowe zaembedowanie 3348 zdań i nie daje nic ponad baseline, bo akapit napisany przez autora jest lepszą granicą niż próg na kosinusie.
- Contextual chunk headers na korpusie jednorodnym tematycznie nie działają: pięć pytań w górę, pięć w dół, recall@20 spada z 0,96 do 0,91. Ten sam nagłówek doklejony do wszystkich chunków sekcji zbliża ich wektory do siebie, zamiast je rozróżniać. Tanie przybliżenie contextual retrieval jest jeszcze gorsze: 0,60–0,65.
- Parent-child nie zmienia metryk retrievalu z definicji, zmienia rachunek: rodzic-akapit kosztuje dwa razy więcej tokenów w prompcie niż dziecko, rodzic-sekcja pięć razy, a deduplikacja rodziców ścina ten ostatni koszt o 27 procent.
- Zamiana modelu z `multilingual-e5-small` na `multilingual-e5-base` daje recall@5 0,88 zamiast 0,81 i dwie porażki zamiast pięciu, a do tego zawęża rozstęp loterii cięcia z 0,133 do 0,082. Prefiksy `query:`/`passage:` są warte 0,06 recall; MiniLM z limitem 128 tokenów przy oknie 256 spada do 0,58.
- W projekcie zostaje `project_chunks`: okno 128/32 na prozie plus bloki kodu i tabele w całości. Wybrane nie za średnią (−0,010), tylko za mechanizm – naprawia jedyne pytanie bez trafienia w top-20 – i za to, że utrzymuje recall@20 na 0,96, czyli sufit dla rerankingu z rozdziału 3.

## Co dalej

Rozdział 3 zajmie się tym, czego chunking zrobić nie mógł. Osiem z dziewięciu porażek rozdziału 1 wciąż tam jest, a recall@20 równy 0,96 mówi, że odpowiedź niemal zawsze jest w dwudziestce kandydatów – tylko nie na górze. To sytuacja, w której opłaca się dołożyć drugi sygnał i drugi etap: BM25, które trafia nazwę `clear_tool_uses_20250919` bezbłędnie tam, gdzie model gęsty nie ma pojęcia, fuzję RRF łączącą obie listy i reranking cross-encoderem, który z dwudziestu kandydatów wybiera pięć, patrząc na pytanie i fragment naraz. Zanim tam przejdziesz, uruchom u siebie `experiments/02_alignment.py` i popatrz, jak siedem liczb rozjeżdża się o 0,13 bez żadnego powodu – to jedyna znana mi szczepionka przeciw wierze w trzecią cyfrę po przecinku.

## Źródła

- https://huggingface.co/intfloat/multilingual-e5-small
- https://huggingface.co/intfloat/multilingual-e5-base
- https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- https://www.anthropic.com/news/contextual-retrieval
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/api/messages
- https://sbert.net/docs/sentence_transformer/usage/usage.html
