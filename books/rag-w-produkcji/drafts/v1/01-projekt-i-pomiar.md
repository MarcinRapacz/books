# Rozdział 1. Projekt, korpus, baseline i pomiar

> **Cel rozdziału:** zbudować naiwny system RAG na prawdziwym korpusie, zamrozić zestaw 56 pytań, którym wszystkie kolejne rozdziały będą mierzyć swoje techniki, i odczytać z pierwszego pomiaru listę rzeczy do naprawienia.
>
> **Kod:** `ragbook/corpus.py`, `ragbook/embed.py`, `ragbook/store.py`, `ragbook/evaluate.py`, `ragbook/generate.py`, `experiments/01_*.py`. **Pakiety poza fundamentem:** brak.

Tom 1 kończył rozdział o RAG-u zdaniem, że pięć pytań z oznaczonymi dokumentami jest nieporównywalnie lepsze niż zero. To prawda i to jest właściwy próg wejścia. Ten tom zaczyna się o krok dalej: pięć pytań powie Ci, w którą stronę idziesz, ale nie powie, czy zmiana chunkera, którą właśnie wdrożyłeś, poprawiła system o 0,04, czy pogorszyła go o 0,02. A dokładnie takie różnice będziemy tu rozstrzygać przez osiem rozdziałów.

Konkret, żeby było wiadomo, o co gramy. Baseline zbudowany w tym rozdziale – stałe okno 128 tokenów, `multilingual-e5-small`, Qdrant, top-5 – ma na zamrożonym zestawie recall@5 równy 0,72 i MRR@5 równy 0,67. Dziewięć pytań na czterdzieści dziewięć nie ma w czołowej piątce ani jednego trafnego fragmentu, a wśród pięciu fragmentów wkładanych do promptu trafne są średnio niecałe dwa. Jednocześnie recall@20 wynosi 0,96, czyli odpowiedź prawie zawsze jest gdzieś w dwudziestce – po prostu nie na górze. To diagnoza, nie porażka, i to ona wyznacza kolejność rozdziałów 2, 3 i 4.

Reszta rozdziału jest o tym, jak dojść do takiego zdania i mieć prawo je wypowiedzieć. Wszystkie snippety uruchamiasz z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/01_baseline.py`.

## Prototyp i produkcja: gdzie to pęka

Prototyp RAG powstaje w godzinę i prawie zawsze działa. Bierzesz dwadzieścia dokumentów, tniesz je po akapitach, liczysz embeddingi, wkładasz do bazy, zadajesz trzy pytania, na które znasz odpowiedź, i dostajesz trzy dobre odpowiedzi. Produkcja różni się nie skalą, tylko tym, że pytania zadaje ktoś inny niż autor systemu – a ta jedna zmiana odsłania sześć trybów awarii, których w prototypie nie da się zobaczyć.

**Pytanie sformułowane inaczej niż dokument.** Autor prototypu pyta słowami z dokumentacji, bo ją czytał. Użytkownik pyta „ile kosztuje trzymanie całej dokumentacji w prompcie”, podczas gdy w tekście stoi „koszt tokenów wejściowych rośnie liniowo z długością wejścia”. Wyszukiwanie gęste radzi sobie z tym nieźle, ale nie zawsze – i nie ma jak się dowiedzieć, kiedy nie, dopóki nie masz zestawu takich pytań. **Identyfikatory i liczby**: `max_seq_length`, `clear_tool_uses_20250919`, HTTP 429, 512 tokenów, 25 MB. Dla modelu embeddingowego to ciągi bez sąsiedztwa semantycznego, a jednocześnie dokładnie to, czego szuka się w dokumentacji technicznej; wyszukiwanie leksykalne trafia je bezbłędnie, gęste gubi.

**Odpowiedź w środku długiej sekcji.** Sekcja o ośmiu tysiącach tokenów po pocięciu na okna po 128 daje dziewięćdziesiąt fragmentów, z których jeden zawiera odpowiedź, a osiemdziesiąt dziewięć jest o tym samym temacie, tylko nie o tym; rodzeństwo wypycha się z czołówki nawzajem. **Pytania wielosekcyjne**: „Wziąć model przez API czy postawić własny?” ma odpowiedź rozrzuconą po dwóch sekcjach, a wyszukiwanie po podobieństwie ma silną skłonność do zwracania pięciu fragmentów z jednego miejsca.

**Pytania, na które odpowiedzi nie ma.** Prototyp nigdy ich nie dostaje, produkcja dostaje je codziennie. System, który na pytanie o Kubernetesa zwraca pięć fragmentów o Qdrancie z wynikiem 0,86, i model, który z nich lepi odpowiedź, to najkosztowniejsza usterka w całym potoku – bo wygląda jak poprawne działanie. I wreszcie **cicha degradacja**: ktoś dopisuje dokument, ktoś zmienia model embeddingowy, ktoś podnosi `k` z 4 do 6, a bez pomiaru każda z tych zmian jest niewidoczna do momentu, w którym ktoś się poskarży.

Lista jest nudna, ale zauważ, że każdą pozycję da się zamienić na pytanie w zestawie testowym. To jest cały pomysł na ten rozdział.

## Projekt i korpus

Projektem przewodnim tomu jest asystent odpowiadający na pytania po dokumentacji technicznej. Korpusem jest tom 1 tej serii: czternaście plików Markdown w `books/ai-engineer/chapters/`. Powody są praktyczne. Masz ten tekst pod ręką i możesz sprawdzić każdą odpowiedź systemu. Jest po polsku, więc problemy z tokenizacją i modelami wielojęzycznymi są prawdziwe, a nie hipotetyczne. Ma strukturę prawdziwej dokumentacji: nagłówki, bloki kodu, tabele, powtarzające się sekcje „Podsumowanie” i „Źródła”. I – co najważniejsze dla ewaluacji – jego treść jest sprawdzalna, więc oznaczanie trafności nie jest zgadywaniem.

Zanim cokolwiek zaindeksujesz, policz korpus. Zajmuje to pięć minut i oszczędza dwa dni.

| Rozdz. | Tytuł | Sekcje | Słowa | Tokeny e5 | Linie kodu | Wiersze tabel | Udział kodu |
|---|---|---|---|---|---|---|---|
| 1 | Kim jest AI Engineer | 8 | 2640 | 4649 | 0 | 8 | 0% |
| 2 | Jak działają LLM-y | 10 | 3713 | 8047 | 162 | 8 | 19% |
| 3 | Prompt engineering | 7 | 5424 | 12500 | 405 | 0 | 31% |
| 4 | Context engineering | 11 | 5090 | 11257 | 302 | 6 | 25% |
| 5 | Modele, platformy i API | 14 | 5328 | 12137 | 211 | 22 | 16% |
| 6 | Embeddingi | 8 | 4016 | 9236 | 245 | 10 | 28% |
| 7 | Bazy wektorowe | 9 | 4318 | 10239 | 223 | 10 | 23% |
| 8 | RAG | 9 | 5995 | 14672 | 420 | 18 | 31% |
| 9 | Agenci AI | 10 | 5849 | 13193 | 339 | 8 | 31% |
| 10 | Model Context Protocol | 11 | 3828 | 9637 | 275 | 0 | 29% |
| 11 | Bezpieczeństwo i etyka | 9 | 4971 | 10998 | 307 | 0 | 29% |
| 12 | Obserwowalność i ewaluacje | 7 | 5682 | 13559 | 337 | 14 | 27% |
| 13 | Multimodalna AI | 11 | 4831 | 11649 | 289 | 0 | 24% |
| 14 | Narzędzia AI do kodowania | 7 | 2508 | 5018 | 35 | 8 | 5% |
| **razem** | | **131** | **64 193** | **146 791** | **3550** | **112** | **24,5%** |

Skrypt: `experiments/01_corpus_stats.py`.

Trzy liczby z tej tabeli są ważniejsze niż pozostałe. **2,29 tokena na słowo** – polszczyzna kosztuje w tokenizerze mniej więcej dwa razy tyle co angielski (tom 1, rozdział 2), więc każde oszacowanie długości chunku zrobione „na oko po znakach” będzie zaniżone. **24,5 procent znaków korpusu to bloki kodu**, a kolejne 2,8 procent to wiersze tabel: to nie jest korpus prozy, tylko taki, w którym co czwarty znak jest identyfikatorem, wcięciem albo nawiasem, a chunker tnący co 128 tokenów bez patrzenia na strukturę będzie regularnie przecinał funkcje w pół. I **131 sekcji przy 14 rozdziałach**, czyli średnio dziewięć na rozdział.

Druga tabela mówi, jak nierówny jest ten korpus.

| Długość sekcji (tokeny e5) | Sekcji | Udział | Słów łącznie |
|---|---|---|---|
| poniżej 200 | 5 | 4% | 505 |
| 200–500 | 43 | 33% | 6564 |
| 500–1000 | 41 | 31% | 14 044 |
| 1000–2000 | 23 | 18% | 14 229 |
| 2000–4000 | 14 | 11% | 16 981 |
| 4000 i więcej | 5 | 4% | 11 870 |

Skrypt: `experiments/01_corpus_stats.py`.

Mediana sekcji ma 667 tokenów, ale rozstęp jest ogromny: od 127 do 8589. Pięć sekcji – cztery procent zbioru – niesie osiemnaście procent tekstu. Najdłuższa to „Pipeline krok po kroku” z rozdziału 8; jeżeli ktoś zapyta o coś, co stoi w jej środku, system musi wyłowić jeden fragment spośród dziewięćdziesięciu pochodzących z tej samej sekcji.

Osobno warto odnotować sekcje powtarzalne. Każdy rozdział tomu 1 kończy się „Podsumowaniem”, „Co dalej” i „Źródłami”, a zaczyna kilkoma akapitami przed pierwszym nagłówkiem `##`. Te 40 sekcji granicznych daje po pocięciu 149 chunków (dziesięć procent indeksu), a 14 wstępów kolejne 78 (pięć procent). Sekcje graniczne są napisane gęsto, w punktach, dokładnie tymi słowami, których użyje pytający – i dlatego wyszukiwanie je uwielbia. Do polityki trafności wrócimy za chwilę.

## Fundament kodu

Cały tom stoi na pakiecie `ragbook`, instalowanym w trybie edytowalnym. Cztery moduły, które musisz znać, zanim napiszesz pierwszy eksperyment.

`ragbook/corpus.py` wczytuje korpus i tnie go na fragmenty. Jednostką trafności w całym tomie jest **sekcja**, czyli jeden nagłówek `##` jednego rozdziału, a nie chunk – dzięki temu zestaw ewaluacyjny nie zależy od strategii chunkowania i rozdział 2 może zmieniać chunker bez przepisywania etykiet.

```python
@dataclass
class Section:
    chapter: int    # numer rozdziału tomu 1
    title: str      # tytuł rozdziału
    section: str    # dokładny tekst nagłówka ##; "" dla tekstu przed pierwszym nagłówkiem
    text: str       # treść sekcji w Markdownie
    path: str

def load_sections(corpus_dir: Path = CORPUS_DIR, include_preface: bool = False) -> list[Section]: ...

def fixed_window_chunks(sections: list[Section], tokenizer, window: int = 128,
                        overlap: int = 32, prefix_with_title: bool = False) -> list[Chunk]: ...
```

Dwie decyzje w `load_sections` warto zobaczyć od razu. Nagłówki wewnątrz bloków kodu są ignorowane – bez tego komentarz `## Conventions` z przykładu `CLAUDE.md` w rozdziale 14 utworzyłby fałszywą sekcję. I nagłówki `###` **nie** dzielą sekcji, więc cała „Anatomia promptu” z rozdziału 3 jest jedną sekcją o 4030 tokenach, mimo że ma pięć podrozdziałów – chcemy, żeby zestaw był gruboziarnisty i stabilny.

`ragbook/embed.py` opakowuje model embeddingowy w cache na dysku. Domyślnym modelem tomu jest `intfloat/multilingual-e5-small`: dwanaście warstw, wektor o 384 wymiarach, `max_seq_length` równe 512, sto języków, inicjalizowany z `microsoft/Multilingual-MiniLM-L12-H384`. Karta modelu jest jednoznaczna w jednej sprawie: każdy tekst musi zaczynać się od prefiksu `query: ` albo `passage: `, inaczej jakość spada – wrapper dokleja je za Ciebie (stan na wrzesień 2026).

```python
class Embedder:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", cache: bool = True): ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...   # prefiks "passage: "
    def embed_queries(self, texts: list[str]) -> np.ndarray: ...    # prefiks "query: "
```

Cache jest tu warunkiem sensownej pracy, a nie optymalizacją: policzenie 1550 wektorów zajmuje na CPU 158 sekund, wczytanie ich z `.cache/` – pół sekundy. Klucz cache'u to hash pary (nazwa modelu, lista tekstów), więc zmiana chunkera albo modelu unieważnia wpis automatycznie.

`ragbook/store.py` to indeks gęsty na Qdrancie w trybie `:memory:`. `DenseIndex.search(query, k, query_filter)` zwraca obiekty `Chunk` z wynikiem podobieństwa w `meta["score"]`, żeby reszta kodu nie musiała wiedzieć, jaka baza siedzi pod spodem. Pod maską jest `client.query_points(...)`, uniwersalny endpoint Qdranta, który obsługuje też wektory rzadkie, hybrydę i `prefetch` – wrócimy do nich w rozdziale 3.

`ragbook/evaluate.py` liczy metryki. Najważniejsza funkcja przyjmuje dowolny retriever o sygnaturze `(question, k) -> list[Chunk]`, więc podstawisz pod nią równie dobrze indeks gęsty, hybrydę z rozdziału 3, jak i potok z rerankingiem:

```python
def evaluate(retrieve: Retriever, golden: list[Question], k: int = 5,
             ks: tuple[int, ...] = (5, 20)) -> dict: ...

def by_type(result: dict, metric: str = "recall@5") -> dict[str, float]: ...
```

`evaluate` zwraca metryki ogólne i listę `per_question`, w której dla każdego pytania siedzi jego recall, pozycja pierwszego trafienia i pięć zwróconych sekcji. Ta lista to jest cała analiza błędów – nie loguj jej do pliku, tylko ją czytaj.

## Baseline end-to-end

Baseline ma być naiwny. Nie chodzi o to, żeby był dobry, tylko żeby był kompletny i żeby każdy kolejny rozdział miał od czego odjąć. Cztery kroki, pierwsze trzy w całości lokalne.

```python
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.store import DenseIndex

embedder = Embedder()                              # intfloat/multilingual-e5-small
sections = load_sections()                         # 131 sekcji z 14 plików Markdown
chunks = fixed_window_chunks(sections, embedder.tokenizer, window=128, overlap=32)
index = DenseIndex(embedder, chunks)               # Qdrant :memory:, kosinus, 384 wymiary

for hit in index.search("Po co normalizować embeddingi?", k=5):
    print(f"{hit.meta['score']:.3f}  rozdz. {hit.chapter}  {hit.section!r}")
```

```text
0.885  rozdz. 6  'Podsumowanie'
0.879  rozdz. 6  'Modele embeddingowe'
0.868  rozdz. 6  'Czym jest embedding'
0.868  rozdz. 6  'Czym jest embedding'
0.866  rozdz. 6  'Modele embeddingowe'
```

Cięcie po 128 tokenach z zakładką 32 daje **1550 chunków**, średnio 11,8 na sekcję, o medianie 128 tokenów. Okno jest z premedytacją krótsze niż limit modelu – e5-small przyjmuje 512 tokenów – bo chcemy zobaczyć, ile kosztuje zły chunking, zanim rozdział 2 zacznie go naprawiać.

W wyniku widać już trzy rzeczy, o których będzie ten tom. Po pierwsze, wszystkie pięć trafień pochodzi z rozdziału 6, w tym dwa razy z tej samej sekcji: wyszukiwanie po podobieństwie skupia się, zamiast pokrywać. Po drugie, na pierwszym miejscu jest „Podsumowanie”, bo punktowana lista napisana terminami z pytania wygrywa z akapitem, który te terminy tłumaczy – akurat tutaj podsumowanie niesie pełną odpowiedź, więc trafienie jest poprawne, ale nie zawsze tak jest i za chwilę zamienimy to w regułę.

Po trzecie, wartości podobieństwa: 0,885 na pierwszym miejscu i 0,866 na piątym, cała piątka w przedziale dwóch setnych. To nie jest usterka – karta modelu E5 mówi wprost, że kosinusy z tej rodziny układają się mniej więcej od 0,7 do 1,0, bo model uczono funkcją kontrastywną InfoNCE z temperaturą 0,01, i liczy się kolejność, nie wartość bezwzględna (stan na wrzesień 2026). Wniosek jest twardy: **nie da się na tym modelu postawić progu odcięcia**.

Czwarty krok to prompt: fragmenty na górze w tagach XML, pytanie na dole, instrukcja „tylko na podstawie dokumentów” i zdefiniowana odpowiedź awaryjna – układ z tomu 1, rozdział 3. Ten krok żyje w `ragbook/generate.py`, bo wymaga klucza API i jako jedyny w całym potoku kosztuje pieniądze.

```python
import os
from anthropic import Anthropic
from ragbook.generate import FALLBACK, SYSTEM, build_prompt

hits = index.search("Po co normalizować embeddingi?", k=5)
prompt = build_prompt("Po co normalizować embeddingi?", hits)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-opus-5",
    max_tokens=512,
    system=SYSTEM,
    messages=[{"role": "user", "content": prompt}],
)
text = next(b.text for b in message.content if b.type == "text")
print(text)
print("odmowa:", FALLBACK in text)
```

Przykładowy wynik:

```text
Normalizacja do długości jeden sprawia, że kosinus, iloczyn skalarny i odległość
euklidesowa dają ten sam ranking, więc podobieństwo liczysz zwykłym mnożeniem
macierzy [rozdz. 6 / Czym jest embedding]. Robisz to raz, przy zapisie do indeksu,
i oszczędzasz pierwiastek oraz dzielenie przy każdym porównaniu [rozdz. 6 / Podsumowanie].
odmowa: False
```

Prompt zbudowany z pięciu chunków po 128 tokenów ma 2974 znaki, czyli 889 tokenów tokenizerem e5; dokładną liczbę dla modelu generującego policzysz endpointem `count_tokens` (tom 1, rozdział 2). To jest punkt odniesienia dla rozważań o koszcie w rozdziale 8: przy `k` równym 5 płacisz za rząd tysiąca tokenów wejścia na zapytanie, przy `k` równym 20 – za cztery razy tyle. Nie masz klucza API? Trzy pierwsze kroki potoku uruchomisz lokalnie i to na nich mierzymy wszystko aż do rozdziału 6.

## Jak zbudować golden set

To jest najdroższa i najważniejsza rzecz w tym rozdziale. Zestaw ewaluacyjny żyje w `code/data/golden.jsonl`, jedno pytanie na linię:

```json
{"id": "q002",
 "question": "Od jakiej długości promptu Claude Opus 5 w ogóle zapisze prefiks do cache?",
 "type": "factual",
 "relevant": [{"chapter": 3, "section": "Interakcja z modelem"}],
 "answer": "Od 512 tokenów. Krótsze prompty nie są cache'owane i nie dostajesz o tym żadnego błędu."}
```

Pole `relevant` wskazuje sekcje, nie chunki. Chunk jest trafny, jeżeli należy do trafnej sekcji – tak liczy `ragbook.evaluate` i dzięki temu ten sam plik obsłuży okno 128-tokenowe z tego rozdziału, podział po nagłówkach z rozdziału 2 i parent-child bez jednej zmiany. Pole `answer` to wzorcowa odpowiedź w jednym–dwóch zdaniach; retrieval jej nie używa, ale rozdział 6 oceni nią wierność generacji.

### Rozkład, który ma sens

Zestaw ma 56 pytań i cztery typy. `factual` to jeden fakt w jednym miejscu (26 pytań). `procedural` to „jak coś zrobić” – odpowiedź jest procedurą rozłożoną na kilka zdań, czasem na dwie sekcje (12). `comparative` to porównanie, prawie zawsze z trafnością w dwóch sekcjach, często z różnych rozdziałów (11). `negative` to pytania, na które w korpusie odpowiedzi nie ma, z pustą listą `relevant` (7). Razem 64 etykiety na 56 pytań, w tym 15 pytań wielosekcyjnych, i pokrycie wszystkich czternastu rozdziałów.

Proporcje nie są przypadkowe. Pytania faktograficzne są najłatwiejsze do oznaczenia i najłatwiejsze dla systemu, więc gdyby stanowiły osiemdziesiąt procent zestawu, każdy pomiar wyglądałby optymistycznie. Porównawcze są najtrudniejsze, bo wymagają, żeby w top-5 zmieściły się dwie różne sekcje – i to one najlepiej odróżniają zwykłe wyszukiwanie od potoku z rerankingiem. Negatywne nie wchodzą do metryk retrievalu w ogóle; są po to, żeby rozdział 6 miał na czym zmierzyć odmowę.

### Pułapka numer jeden: pytania za łatwe

Jeżeli zapytasz o coś słowami, którymi to napisano, znajdziesz to zawsze. Zestaw zbudowany w ten sposób daje recall@5 bliski jedności i jest bezużyteczny, bo nie ma w nim miejsca na poprawę. Sześć chwytów, które robią tu robotę:

- **Parafraza bez pokrycia leksykalnego.** „Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?” zamiast „ile kosztują tokeny wyjściowe”: ani „drożej”, ani „napisze” nie występuje w trafnym akapicie.
- **Identyfikatory i nazwy parametrów.** Odpowiedzią na „jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi” jest `clear_tool_uses_20250919`, ciąg, który w przestrzeni semantycznej nie leży nigdzie.
- **Liczby z tabel.** „Ile kosztuje milion tokenów wejściowych i wyjściowych `gpt-6-astra`?” – odpowiedź jest komórką tabeli, a tabela po pocięciu na okna traci nagłówek.
- **Język potoczny.** „Dlaczego jedno `print()` w kodzie narzędzia potrafi zerwać połączenie z serwerem?” zamiast „jak działa ramkowanie komunikatów w transporcie stdio”.
- **Odpowiedź w środku długiej sekcji.** Próg kompaktowania (150 tysięcy tokenów) stoi w połowie sekcji o 5101 tokenach, wśród pięćdziesięciu dwóch innych fragmentów o kontekście.
- **Pytania wielosekcyjne.** „Qdrant czy pgvector do produkcji średniej skali?” wymaga naraz „Przeglądu popularnych baz” i „Wyboru bazy w praktyce”.

### Pułapka numer dwa: polityka trafności

Każdy rozdział tomu 1 kończy się „Podsumowaniem”, które streszcza całość w ośmiu punktach. Bardzo często jeden z tych punktów zawiera pełną odpowiedź na pytanie, na które właściwa sekcja odpowiada trzema akapitami. Trzeba zdecydować, czy to jest trafienie – i zdecydować raz, bo niekonsekwencja psuje metrykę bardziej niż dziesięć źle dobranych pytań.

Polityka przyjęta w tym tomie brzmi tak. **„Co dalej” i „Źródła” nie są trafne nigdy** – pierwsze zapowiada następny rozdział, drugie jest listą URL-i; żadne nie odpowiada na pytanie, tylko wskazuje kierunek. **„Podsumowanie” jest trafne tylko wtedy, gdy zawiera pełną odpowiedź**, taką, którą dałoby się pokazać użytkownikowi bez dopisywania czegokolwiek. W całym zestawie taki przypadek jest jeden: pytanie „HNSW czy IVF” dostaje „Podsumowanie” rozdziału 7 obok sekcji merytorycznej, bo tamten punkt wymienia wszystkie trzy parametry HNSW i `nprobe` dla IVF. **Sekcja wstępna** (tekst przed pierwszym `##`, w danych zapisana jako pusty string) jest traktowana jak każda inna i bywa trafna – „lethal trifecta” z rozdziału 11 stoi właśnie tam.

Polityka jest wpisana w walidator, a nie tylko w rozdział:

```python
FORBIDDEN_SECTIONS = {"Co dalej", "Źródła"}

for q in load_golden():
    for chapter, section in sorted(q.relevant):
        if (chapter, section) not in known:          # known = {s.key for s in load_sections()}
            errors.append(f"{q.id}: no such section ({chapter}, {section!r})")
        elif section in FORBIDDEN_SECTIONS:
            errors.append(f"{q.id}: section {section!r} is excluded by the relevance policy")
```

```text
golden set: 56 questions, 64 relevance labels
  factual 26 (46%)  procedural 12 (21%)  comparative 11 (20%)  negative 7 (12%)
  chapters covered: 14 of 14   multi-section questions: 15

OK: every (chapter, section) exists in load_sections() and the policy holds.
```

Skrypt: `experiments/01_validate_golden.py`.

Sprawdzenie, że każda para (rozdział, sekcja) faktycznie istnieje w `load_sections()`, jest tu najważniejszą linijką. Nagłówki pisze się ręcznie, a literówka nie wywala niczego – po prostu tworzy pytanie, którego nigdy nie da się trafić, i zaniża recall o dwa punkty procentowe na zawsze. Walidator kończy się kodem 1, więc wpina się w CI tak samo jak bramka jakości z tomu 1, rozdział 12.

### Pułapka numer trzy: pytania negatywne

Pytanie negatywne ma brzmieć jak pytanie z tej dziedziny, ale nie mieć odpowiedzi w korpusie. „Jak ustawić parametr `ef_search` w Elasticsearchu przy indeksie kNN?” jest dobre, bo `ef_search`, kNN i indeksy w korpusie są – tylko w kontekście Qdranta, FAISS-a i pgvectora. „Jak skonfigurować replikację strumieniową PostgreSQL między dwoma centrami danych?” jest dobre, bo PostgreSQL zajmuje w rozdziale 7 sporo miejsca, ale wyłącznie jako host dla pgvectora. „Ile kosztuje transfer danych wychodzących z AWS S3?” jest dobre, bo korpus jest pełen cenników – tylko nie tego. Złe pytanie negatywne to takie, które nie przypomina niczego z korpusu („jaki jest przepis na żurek”): odrzuci je każdy system i nie zmierzysz nim nic.

### Ile pytań wystarczy

Pięćdziesiąt sześć, i to nie jest liczba z sufitu. Od dołu ogranicza ją szum: przy `n` pytaniach i recall na poziomie `p` błąd standardowy średniej to mniej więcej pierwiastek z `p(1-p)/n`, czyli przy 49 pytaniach i recall 0,72 około 0,06. Różnica 0,05 między dwoma wariantami mieści się więc w granicach szumu (za chwilę pokażę, dlaczego w porównaniach parami jest lepiej, niż wynika z tej liczby). Od góry ogranicza ją koszt: każde pytanie wymaga przeczytania sekcji i upewnienia się, że odpowiedź tam naprawdę jest – jakieś pięć minut na pozycję, dwie godziny na całość.

Z grubsza: dwadzieścia pytań pozwala zauważyć zmianę o 0,15, pięćdziesiąt – o 0,07, dwieście – o 0,035. Powyżej dwustu przestaje się opłacać, bo błąd oznaczania rośnie szybciej niż precyzja pomiaru. Rozbicie po typach wymaga przy tym co najmniej dziesięciu pytań w grupie, stąd 26/12/11/7, a nie 40/8/5/3.

I jedna zasada organizacyjna: **zestaw powstaje raz i zostaje zamrożony**. Rozdziały 2, 3 i 4 mierzą się na tym samym pliku i nie wolno im go modyfikować; rozdział, który potrzebuje pytań specjalnych (rozdział 5 będzie potrzebował pytań o wartości w tabelach), zakłada osobny plik obok. Powód jest ten sam, co przy wersjonowaniu zbiorów ewaluacyjnych w tomie 1: zmiana zestawu zmienia znaczenie metryki.

## Metryki

Mierzymy retrieval osobno od generacji i to jest pierwsza decyzja metodologiczna tego tomu. Powód diagnostyczny: jeżeli mierzysz tylko końcową odpowiedź, to przy błędzie nie wiesz, czy model źle rozumował, czy po prostu nie dostał tego, co trzeba. Powód budżetowy: metryki retrievalu liczą się bez wołania modelu, w kilka milisekund na pytanie. I powód najważniejszy: **recall retrievalu jest sufitem jakości całego systemu** – czego wyszukiwanie nie znajdzie, tego generacja nie napisze, a jeśli napisze, to znaczy, że zmyśliła.

Trafność jest u nas binarna i liczona po sekcjach. Dla pytania $q$ niech $S_q$ będzie zbiorem sekcji oznaczonych jako trafne, a $R_q^{(k)}$ – zbiorem sekcji, z których pochodzą chunki zwrócone na pierwszych $k$ pozycjach.

$$\mathrm{recall@}k = \frac{1}{|Q|}\sum_{q \in Q} \frac{\left|S_q \cap R_q^{(k)}\right|}{|S_q|}$$

Recall@k mówi, jaka część potrzebnych sekcji znalazła się w zwróconej `k`-tce: dla pytania z jedną trafną sekcją zero albo jeden, dla porównawczego z dwiema – zero, pół albo jeden. Kolejność nie ma znaczenia, więc trafienie na pozycji pierwszej i piątej liczą się tak samo. Standardowe `k` w tym tomie to 5 (tyle fragmentów idzie do promptu) i 20 (tyle kandydatów zbiera się przed rerankingiem z rozdziału 3).

$$\mathrm{MRR@}k = \frac{1}{|Q|}\sum_{q \in Q} \frac{1}{\mathrm{rank}_q}, \qquad \mathrm{rank}_q = \min\{\, i \le k : \mathrm{sec}(c_i) \in S_q \,\}$$

MRR (mean reciprocal rank) dokłada to, czego recall nie widzi: pozycję pierwszego trafienia. Na miejscu pierwszym daje 1, na drugim 0,5, na piątym 0,2, a brak trafienia w `k`-tce liczymy jako 0. Intuicja: „jak głęboko trzeba sięgnąć, żeby znaleźć cokolwiek trafnego”. MRR jest przez to bardzo czuły na reranking i zupełnie ślepy na to, czy druga trafna sekcja też się znalazła.

$$\mathrm{DCG@}k = \sum_{i=1}^{k} \frac{g_i}{\log_2(i+1)}, \qquad \mathrm{nDCG@}k = \frac{\mathrm{DCG@}k}{\mathrm{IDCG@}k}$$

nDCG (normalised discounted cumulative gain) jest kompromisem między tymi dwiema: sumuje zyski $g_i$ (u nas 1 za trafienie, 0 za pudło, każda sekcja liczona raz) z rabatem logarytmicznym zależnym od pozycji, a potem dzieli przez wynik idealnego uszeregowania. Dzięki tej normalizacji pytanie z jedną trafną sekcją i pytanie z dwiema są porównywalne, czego surowe DCG nie daje. To jest metryka, którą warto raportować jako główną przy pytaniach wielosekcyjnych – i dokładnie tam rozjeżdża się z MRR.

Czwarta liczba nie jest metryką, tylko licznikiem: **ile pytań nie ma w top-`k` ani jednego trafienia**. Średnia zawsze coś ukrywa, a lista dziewięciu identyfikatorów prowadzi wprost do dziewięciu konkretnych usterek. `evaluate` zwraca ją jako `misses@5`.

## Pierwszy pomiar

| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Pytań bez trafienia |
|---|---|---|---|---|---|---|
| stałe okno 128/32 + e5-small | 49 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |

Skrypt: `experiments/01_baseline.py`.

Czterdzieści dziewięć, a nie pięćdziesiąt sześć, bo siedem pytań negatywnych nie ma trafnych sekcji i metryki retrievalu je pomijają.

| Typ pytania | Pytań | recall@5 | recall@20 | MRR@5 |
|---|---|---|---|---|
| factual | 26 | 0,81 | 1,00 | 0,66 |
| procedural | 12 | 0,62 | 0,92 | 0,60 |
| comparative | 11 | 0,64 | 0,91 | 0,75 |

Skrypt: `experiments/01_baseline.py`.

Rozbicie po typach mówi więcej niż średnia i potwierdza, że zestaw robi to, po co powstał. Pytania faktograficzne wypadają najlepiej i mają recall@20 równy jedności. Proceduralne są najsłabsze, bo ich odpowiedzią jest procedura rozłożona na kilka akapitów, a okno 128-tokenowe łapie z niej pojedynczy krok bez kontekstu. Porównawcze mają najwyższy MRR (0,75) i niski recall (0,64) naraz, i ta para liczb jest wymowna: system praktycznie zawsze trafia **jedną** z dwóch potrzebnych sekcji, i to wysoko, ale drugiej nie dokłada. Dziewięć pytań w całym zestawie ma recall@5 równy dokładnie 0,5 i wszystkie dziewięć to pytania wielosekcyjne.

Dwie liczby spoza tabeli. **Precision@5 wynosi 0,38** – spośród 245 fragmentów wkładanych do promptów trafnych jest 94; pozostałe 151 to tokeny, za które płacisz i które model musi przeczytać, żeby je zignorować. I drugie: **sekcje graniczne zajmują 8 procent slotów w top-5** – dwadzieścia z 245, w tym piętnaście razy „Podsumowanie” i pięć razy „Co dalej”, a sekcje wstępne kolejne siedem procent. To mniej więcej tyle, ile wynosi ich udział w indeksie, więc nie są przeciążone – ale skoro prawie nigdy nie niosą odpowiedzi, każdy taki slot jest wprost zmarnowany.

Zostają pytania negatywne, których metryki retrievalu nie dotyczą, a które mówią najwięcej o tym, czego ten baseline nie potrafi.

```text
top-1 score: negatives min 0.845 max 0.875 mean 0.860
top-1 score: positives min 0.841 max 0.928 mean 0.882
7 of 7 negatives score above the weakest positive -> no usable cut-off
```

Każde z siedmiu pytań, na które w korpusie nie ma odpowiedzi, dostaje na pierwszym miejscu fragment z wynikiem wyższym niż najsłabsze prawdziwe trafienie; rozkłady zachodzą na siebie całkowicie. Progu odcięcia po `score` nie da się więc ustawić ani wysoko, ani nisko, ani po kalibracji, a odmowa musi być decyzją modelu w kroku generacji, a nie regułą w kodzie retrievalu. Rozdział 6 zbuduje ją na zdefiniowanej odpowiedzi awaryjnej; rozdział 4 sprawdzi, czy da się ją podeprzeć klasyfikacją intencji.

## Analiza błędów

Dziewięć pytań bez trafienia w top-5. Osiem z nich ma trafną sekcję w top-20. Poniżej cztery kategorie, na które się rozkładają – i to są cztery zapowiedzi kolejnych rozdziałów.

**Kategoria 1: nazwa własna, której model gęsty nie zna (q022).** „Jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi?” dostaje pięć fragmentów, z których cztery pochodzą z właściwego rozdziału 4 – „Tryby awarii kontekstu” dwa razy, wstęp, „Skąd bierze się kontekst” – ale ani jeden z „Technik zarządzania kontekstem”, gdzie stoi `clear_tool_uses_20250919`. Wyszukiwanie znalazło właściwy temat i przegapiło właściwy ciąg znaków, choć ten ciąg jest w korpusie dokładnie raz i dopasowałby się bezbłędnie zwykłym `LIKE`. Podręcznikowy przypadek na hybrydę z BM25 (rozdział 3).

**Kategoria 2: konkret utopiony w długiej sekcji (q023, q021).** „Jak duży plik przyjmie endpoint transkrypcji OpenAI?” zwraca „Zastosowania” i „Rozumienie obrazu” z rozdziału 13, czyli sąsiadów właściwej sekcji „Audio”; limit 25 MB stoi w jej środku, w jednym zdaniu, pośród opisów trzech modeli transkrypcyjnych. Podobnie q021: cztery z pięciu trafień to fragmenty rozdziału 12 o logowaniu, podczas gdy `metadata.user_id` siedzi w sekcji „Dobre praktyki” rozdziału 11, która ma 3736 tokenów i produkuje kilkadziesiąt konkurujących ze sobą fragmentów. Na to odpowiada rozdział 2: contextual chunk headers i parent-child.

**Kategoria 3: parafraza bez wspólnych słów (q007, q029, q033, q037).** „Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?” trafia w „Czym zajmuje się AI Engineer”, „Zamknięte czy otwarte” i „Czym jest RAG i kiedy go użyć” – wszystkie ogólnie o kosztach, żadna o mnożniku pięć. Sekcja „Trening a inferencja” nie ma w tekście ani słowa „drożej”, ani „napisze”. W q029 dwa z pięciu fragmentów pochodzą z sekcji „Prompt injection” rozdziału 11, czyli o jedną sekcję za daleko, bo „lethal trifecta” stoi w jego wstępie. To zadanie dla przekształceń zapytania z rozdziału 4: query rewriting, HyDE, step-back.

**Kategoria 4: dwie sekcje, jeden temat (q032 oraz dziewięć pytań z połówkowym recall).** „Jak podmienić model liczący wektory w działającym systemie?” wymaga rozdziału 7 („Indeksowanie embeddingów”: nowa kolekcja, przełączenie aliasu) i rozdziału 6 („Praktyczne pułapki”: nie mieszaj modeli w jednym indeksie). Baseline zwraca pięć fragmentów o tematyce ogólnie właściwej, ale rozsianych po czterech rozdziałach. Dochodzi do tego dziewięć pytań, które trafiły tylko jedną z dwóch potrzebnych sekcji – wszystkie wielosekcyjne. Tu potrzebna jest dywersyfikacja wyników i multi-query (rozdziały 3 i 4).

Jeden przypadek wypada poza te kategorie. Pytanie q039 („Jak sprawdzić, czy zapytanie wygenerowane przez model można bezpiecznie puścić na bazę?”) jako jedyne nie ma trafienia nawet w top-20. Odpowiedź – walidacja SQL-a na drzewie składniowym przez `sqlglot` – jest w „Dobrych praktykach” rozdziału 11, w kilku zdaniach prozy i w dużym bloku kodu. Po pocięciu na okna fragmenty z tego bloku są ciągami nazw funkcji i wyjątków, które nie leżą blisko żadnego pytania po polsku, a zdania prozy giną wśród trzydziestu kilku sąsiadów. To zapowiedź rozdziału 5: kod w dokumentacji wymaga innego traktowania niż proza.

Zauważ, czego na tej liście **nie** ma: ani jednej porażki, za którą odpowiadałby sam Qdrant. Przy 1550 wektorach indeks jest dokładny co do ostatniego bitu, a `ef`, `nprobe` i kwantyzacja z tomu 1, rozdział 7 zaczynają mieć znaczenie o dwa rzędy wielkości dalej. Cała strata siedzi w chunkingu, w reprezentacji i w sformułowaniu zapytania.

## Pętla: zmiana, pomiar, decyzja

Reszta tego tomu jest jedną pętlą powtarzaną kilkadziesiąt razy: zmień jedną rzecz, zmierz na zamrożonym zestawie tymi samymi metrykami i tym samym `k`, zdecyduj, czy zostaje. Trzy reguły.

**Jedna zmiana naraz.** Jeżeli podmienisz jednocześnie chunker i model embeddingowy, a wynik urośnie o 0,06, nie wiesz, który z nich pomógł ani czy drugi przypadkiem nie zaszkodził.

**Raportuj rozbicie, nie tylko średnią.** Zmiana, która podnosi recall@5 o 0,04 na pytaniach faktograficznych i obniża go o 0,03 na porównawczych, w średniej wygląda na wygraną. Czy nią jest, zależy od tego, jakie pytania zadają Twoi użytkownicy – i to jest decyzja produktowa, a nie efekt uboczny uśredniania.

**Znaj szerokość swojego szumu.** Tu najłatwiej się oszukać.

```text
recall@5 = 0.724, sd per question 0.396, standard error 0.057
95% bootstrap CI: [0.612, 0.827]  (width 0.214)
```

Skrypt: `experiments/01_baseline.py`.

Przedział ufności dla recall@5 na czterdziestu dziewięciu pytaniach ma szerokość 0,21 – nie wiesz, czy prawdziwa wartość tego baseline'u to 0,61, czy 0,83. To brzmi jak wyrok na cały pomiar i byłoby nim, gdybyśmy porównywali dwa systemy mierzone na dwóch różnych zestawach. My porównujemy **ten sam zestaw pytań przed zmianą i po zmianie**, a wtedy interesująca statystyka to nie średnia, tylko rozkład różnic per pytanie – znacznie węższy, bo większość pytań zachowuje się tak samo w obu wariantach i wnosi do różnicy zero.

Stąd praktyczna reguła stosowana w kolejnych rozdziałach: **patrz, ile pytań zmieniło wynik, a nie o ile zmieniła się średnia**. Różnica 0,04 na 49 pytaniach to mniej więcej dwa pytania, które zaczęły działać. Statystyką tego nie rozstrzygniesz, ale rozstrzygniesz, czytając te dwa pytania i sprawdzając, czy poprawa ma mechanizm, który potrafisz nazwać. Jeśli tak, zmiana zostaje; jeśli poprawiło się jedno pytanie i nie umiesz powiedzieć dlaczego, to jest szum, choćby średnia urosła. Zmiana o osiem–dziesięć pytań (0,15–0,20) jest już różnicą, której nie da się wytłumaczyć losem.

I rzecz najmniej techniczna: zestaw ewaluacyjny nie jest prawdą o Twoim systemie, tylko o pięćdziesięciu sześciu pytaniach, które ktoś wybrał. Optymalizowanie pod niego bez końca daje system rozwiązujący te pięćdziesiąt sześć pytań i żadne inne. Antidotum opisał tom 1, rozdział 12: prawdziwe zapytania z produkcji wracają do zestawu, a zestaw rośnie w kierunku wyznaczonym przez użytkowników, nie przez autora. My tego luksusu w książce nie mamy, więc zamrażamy plik i pamiętamy o jego ograniczeniu.

## Podsumowanie

- Jednostką trafności w całym tomie jest sekcja tomu 1 (numer rozdziału plus dokładny nagłówek `##`), a nie chunk – dzięki temu zestaw przetrwa każdą zmianę chunkera w rozdziałach 2–5.
- Korpus ma 131 sekcji, 64 193 słowa i 146 791 tokenów e5 (2,29 tokena na słowo), z czego 24,5 procent znaków to bloki kodu; mediana sekcji ma 667 tokenów, najdłuższa 8589 i po pocięciu daje 90 konkurujących ze sobą fragmentów.
- Baseline (okno 128/32, `multilingual-e5-small`, Qdrant, top-5) daje 1550 chunków i osiąga recall@5 0,72, recall@20 0,96, MRR@5 0,67, nDCG@5 0,64 oraz precision@5 0,38 przy 9 pytaniach bez trafienia.
- Zestaw 56 pytań (26 faktograficznych, 12 proceduralnych, 11 porównawczych, 7 negatywnych, 15 wielosekcyjnych) pokrywa wszystkie 14 rozdziałów i celowo zawiera parafrazy, identyfikatory i liczby z tabel, żeby naiwny baseline nie osiągnął na nim sufitu.
- Polityka trafności musi być spisana i wymuszona kodem: „Co dalej” i „Źródła” nigdy nie są trafne, „Podsumowanie” tylko gdy niesie pełną odpowiedź, a walidator sprawdza, że każda para (rozdział, sekcja) istnieje w `load_sections()`.
- Retrieval mierzymy osobno od generacji, bo recall jest sufitem jakości całego systemu, liczy się bez klucza API w kilka milisekund na pytanie i wskazuje winnego, gdy odpowiedź jest zła.
- Kosinusów z rodziny E5 nie da się użyć jako progu odcięcia: wszystkie pytania negatywne dostają na pierwszym miejscu wynik wyższy niż najsłabsze prawdziwe trafienie, więc odmowa musi powstać w kroku generacji.
- Dziewięć porażek rozkłada się na cztery kategorie – nazwa własna zgubiona przez model gęsty, konkret utopiony w długiej sekcji, parafraza bez wspólnych słów i pytanie o dwóch odpowiedziach naraz – i to one wyznaczają zakres rozdziałów 2, 3 i 4.
- Przy 49 pytaniach przedział ufności dla recall@5 ma szerokość 0,21, więc różnicę czytaj po liczbie pytań, które zmieniły wynik, a nie po trzeciej cyfrze średniej.

## Co dalej

Rozdział 2 bierze się za pierwszy i najtańszy element z listy błędów: chunking i reprezentację. Zobaczysz, ile daje zmiana rozmiaru okna, podział po strukturze Markdown zamiast po tokenach, doklejenie tytułu rozdziału i sekcji do fragmentu, small-to-big z rodzicem wkładanym do promptu oraz zamiana `multilingual-e5-small` na model o innym wymiarze wektora – wszystko mierzone tym samym plikiem `golden.jsonl` i tym samym `k`. Zanim tam przejdziesz, uruchom `experiments/01_baseline.py` u siebie i przeczytaj analizę błędów w całości, łącznie z listą pięciu fragmentów zwróconych dla każdej porażki. Dziewięć przypadków to dziesięć minut czytania, po których będziesz wiedział o tym korpusie więcej, niż mówi którakolwiek tabela w tym rozdziale.

## Źródła

- https://huggingface.co/intfloat/multilingual-e5-small
- https://arxiv.org/abs/2402.05672
- https://sbert.net/docs/sentence_transformer/usage/usage.html
- https://qdrant.tech/documentation/concepts/search/
- https://qdrant.tech/documentation/concepts/hybrid-queries/
- https://platform.claude.com/docs/en/api/messages
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
