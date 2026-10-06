# Rozdział 4. Przekształcanie zapytań, filtry i routing

> **Cel rozdziału:** naprawić te porażki baseline'u, które biorą się z samego sformułowania pytania, i zdecydować, kiedy w ogóle warto szukać – przekształcając zapytanie, filtrując po metadanych albo odrzucając zapytanie na wejściu.
>
> **Kod:** `ragbook/queries.py`, `ragbook/routing.py`, `experiments/04_*.py`. **Pakiety poza fundamentem:** brak.

„Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?” To pytanie z zamrożonego zestawu (q007) i jedno z trzech, których nie naprawił ani lepszy chunking z rozdziału 2, ani hybryda z rerankerem z rozdziału 3. Odpowiedź stoi w sekcji „Trening a inferencja” rozdziału 2 tomu 1 – to tom 1 jest korpusem tej książki – a baseline zwrócił zamiast niej trzy sekcje ogólnie o kosztach.

Powodu nie da się naprawić po stronie indeksu. W trafnej sekcji nie ma ani słowa „drożej”, ani „napisze”. Pytający myśli o rachunku, dokumentacja pisze o tokenach wejściowych i wyjściowych, a wyszukiwanie gęste mierzy podobieństwo dwóch tekstów – i te dwa podobne nie są. Leksykalne jest jeszcze bardziej bezradne: BM25 nie wymyśli słowa, którego w pytaniu nie ma.

Zostaje trzecia rzecz do zmiany: sam ciąg znaków, który trafia do wyszukiwarki. Ten rozdział nie dotyka indeksu ani razu. Najpierw pięć sposobów na przepisanie pytania, potem filtry po metadanych, na koniec decyzja, czy w ogóle warto szukać. Samo przepisywanie podnosi na baseline'owym indeksie recall@5 – szansę, że właściwa sekcja jest wśród pięciu fragmentów wkładanych do promptu – z 0,72 do 0,93 i zbija dziewięć pytań bez trafienia do zera.

Jedna uczciwa uwaga, zanim zobaczysz pierwszą liczbę. Każde przekształcenie wymaga wywołania modelu, a ja nie mam klucza API – więc warianty zapytań napisałem ręcznie i leżą w `data/query_variants.jsonl`. Patrzyłem przy tym wyłącznie na pytanie, nigdy na tekst trafnej sekcji, ale i tak jestem człowiekiem, który ten korpus zna. Retrieval i metryki są prawdziwe, od człowieka pochodzą tylko warianty – czytaj więc te liczby jako **górną granicę** tego, co osiągnie model. Skrypty uruchamiasz z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/04_queries.py`.

## Query rewriting: z potocznego na precyzyjne

Technika naprawia pytanie, które człowiek rozumie bez trudu, a wyszukiwarka nie ma z czym zestawić – „ile razy drożej” u nas, a w produkcji najczęściej pytanie zadane w rozmowie („a ile to kosztuje?”), które jako zapytanie do bazy nie znaczy nic. Prosisz tani model o przepisanie go na samodzielne zapytanie wyszukiwawcze: z terminologią, z nazwami parametrów, bez zaimków i bez odwołań do wcześniejszych tur. Cała wartość siedzi w słowie „samodzielne”. Wynik ma ustaloną strukturę, więc to podręcznikowe zastosowanie structured outputs (tom 1, rozdział 3).

```python
import os
from anthropic import Anthropic
from pydantic import BaseModel, Field
from ragbook.queries import REWRITE_PROMPT

class Rewrites(BaseModel):
    queries: list[str] = Field(description="self-contained search queries, no pronouns")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
question = "Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?"
response = client.messages.parse(
    model="claude-haiku-4-5",                       # przekształcenia są krótkie i częste
    max_tokens=512,
    messages=[{"role": "user", "content": REWRITE_PROMPT.format(n=2, question=question)}],
    output_format=Rewrites,
)
for query in response.parsed_output.queries:
    print(query)
```

Przykładowy wynik:

```text
stosunek ceny tokenów wyjściowych do wejściowych w cenniku modeli Claude
mnożnik kosztu tokenów wygenerowanych względem tokenów wysłanych w API
```

Model jest tani celowo: zadanie jest mechaniczne, a `claude-haiku-4-5` kosztuje dolara za milion tokenów wejścia (stan na wrzesień 2026). W prompcie istotny jest jawny zakaz odpowiadania na pytanie – bez niego model zgaduje odpowiedź, zamiast przepisywać zapytanie.

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| baseline (pytanie użytkownika) | 0,72 | 0,96 | 9 |
| rewrite 1 | 0,85 | 0,94 | 4 |
| rewrite 2 | 0,83 | 0,97 | 5 |

Skrypt: `experiments/04_queries.py`. Wszystkie pomiary w tym rozdziale idą na czterdziestu dziewięciu pytaniach pozytywnych; siedem negatywnych nie ma trafnych sekcji i metryki retrievalu je pomijają.

Samo przepisanie pytania jest najtańszą poprawą w tym rozdziale: trzynaście setnych recall@5 za jedno wywołanie taniego modelu, bez żadnej magii – to tylko zamiana słów użytkownika na słowa dokumentacji.

Jest za to kaprys. Oba warianty naprawiają po siedem z dziewięciu porażek baseline'u, ale nie te same siedem. Pierwszy podnosi pytania faktograficzne z 0,81 do 0,96, drugi zostawia je na 0,85, za to winduje proceduralne z 0,62 do 0,96: zapytanie nazywające parametr trafia w zdanie z tym parametrem, a opisujące procedurę – w akapit, który ją opisuje.

Jest też strata: pierwszy wariant psuje trzy pytania, które baseline miał dobrze, a recall@20 spada z 0,96 do 0,94. Przepisując pytanie, zawężasz je, i czasem zawęzisz w złą stronę – dlatego rewritingu w wersji „jedno pytanie w, jedno w zamian” prawie nikt produkcyjnie nie używa.

## Multi-query: trzy zapytania i fuzja RRF

Skoro każdy wariant naprawia inne pytania i psuje inne, nie wybieraj. Puść wszystkie trzy – oryginał plus dwa przeformułowania – i połącz listy tą samą fuzją rangową, którą rozdział 3 stosował do hybrydy: reciprocal rank fusion sumuje po listach wartości $1/(k + \mathrm{rank})$, czyli patrzy na pozycje, nie na wyniki podobieństwa. To istotne, bo wyniki dla różnych zapytań nie są porównywalne, a rangi są.

```python
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.queries import ScriptedLLM, expand_query, load_variants, multi_retrieve
from ragbook.store import DenseIndex

embedder = Embedder()
index = DenseIndex(embedder, fixed_window_chunks(load_sections(), embedder.tokenizer))

llm = ScriptedLLM(load_variants()).for_question("q007")   # w produkcji: ClaudeLLM()
queries = expand_query(question, llm, mode="multi")       # pytanie + 2 przeformułowania
hits = multi_retrieve(index.search, queries, k=5)         # 3 x retrieval, fuzja RRF
for hit in hits:
    print(f"{hit.meta['score']:.4f}  rozdz. {hit.chapter}  {hit.section!r}")
```

```text
0.0164  rozdz. 1  'Czym zajmuje się AI Engineer'
0.0164  rozdz. 2  'Trening a inferencja'
0.0164  rozdz. 6  'Modele embeddingowe'
0.0161  rozdz. 5  'Zamknięte czy otwarte'
0.0161  rozdz. 2  'Od tekstu do tokenów'
```

To jest pytanie o mnożnik kosztu, od którego zaczął się ten rozdział. Trafna sekcja „Trening a inferencja”, której w piątce baseline'u nie było wcale, wchodzi na drugie miejsce. Zwróć przy okazji uwagę na wartości: trzy pierwsze pozycje mają dokładnie tyle samo, $1/61 \approx 0,0164$, bo każda była pierwsza w jednej z trzech list. Remisy są w RRF normą i rozstrzyga je przypadek – gdy remis przebiega na granicy `k`, tracisz trafienie przez porządek iteracji po słowniku. To jeden z powodów, dla których rozdział 3 kończy potok rerankerem.

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| baseline (pytanie użytkownika) | 0,72 | 0,96 | 9 |
| rewrite 1 | 0,85 | 0,94 | 4 |
| multi-query (pytanie + 2 rewrite'y, RRF) | **0,93** | 0,98 | **0** |

Skrypt: `experiments/04_queries.py`.

Na baseline'owym indeksie nie ma już ani jednego pytania bez trafienia – wszystkie dziewięć porażek z rozdziału 1 ma w piątce trafną sekcję, łącznie z tym o walidacji SQL-a, którego baseline nie znajdował nawet w dwudziestce. Czego jeden wariant nie znajdzie, tego szuka drugi, a oryginał pilnuje, żeby nie zgubić tego, co i tak działało.

Kiedy nie warto. Multi-query kosztuje tyle samo wywołań LLM-a co zwykły rewriting, ale trzy razy więcej zapytań do bazy – przy dziesiątkach milionów wektorów to koszt, który trzeba policzyć. I nie mnóż wariantów w nieskończoność: RRF premiuje dokumenty widoczne w wielu listach, więc zapytanie wyraźnie gorsze od pozostałych dokłada szumu do czołówki.

## HyDE: embedujemy odpowiedź, nie pytanie

HyDE (hypothetical document embeddings, arXiv 2212.10496) wychodzi od obserwacji, że pytanie i odpowiedź to dwa różne gatunki tekstu. Pytanie jest krótkie i pełne słów, których w dokumentacji nie ma; dokument jest twierdzeniem z terminologią. Model embeddingowy mierzy podobieństwo, a nie relację „to jest odpowiedź na tamto” – więc każ modelowi napisać zmyśloną odpowiedź i szukaj nią. Hipoteza może być błędna; liczy się, że jest napisana w rejestrze dokumentacji.

```python
from ragbook.queries import HYDE_PROMPT, Hypothetical

response = client.messages.parse(
    model="claude-haiku-4-5",
    max_tokens=512,
    messages=[{"role": "user", "content": HYDE_PROMPT.format(question=question)}],
    output_format=Hypothetical,
)
hypothesis = response.parsed_output.answer
vector = embedder.embed_passages([hypothesis])[0]      # prefiks "passage: ", nie "query: "
points = index.client.query_points(collection_name="chunks",
                                   query=vector.tolist(), limit=5).points
```

Przykładowy wynik:

```text
Tokeny wyjściowe są w cennikach droższe od wejściowych, zwykle kilkukrotnie, bo generowanie
kosztuje więcej obliczeń niż przetworzenie wejścia. W rodzinie modeli Claude stosunek ten jest
taki sam na każdym modelu bieżącej generacji.
```

W tym kodzie jest decyzja, której w oryginalnej pracy nie ma. E5 wymaga prefiksu: `query: ` dla zapytań, `passage: ` dla dokumentów (tom 1, rozdział 6). Hipotetyczna odpowiedź **jest** dokumentem – ale czy na pewno tak ją zakodować? Zmierzyłem oba warianty.

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| baseline | 0,72 | 0,96 | 9 |
| HyDE (hipoteza jako `query: `) | 0,81 | 0,98 | 6 |
| HyDE (hipoteza jako `passage: `) | 0,88 | 0,96 | 3 |
| HyDE + pytanie (RRF) | 0,91 | 0,98 | 1 |
| multi-query (dla porównania) | 0,93 | 0,98 | 0 |

Skrypt: `experiments/04_queries.py`.

Prefiks nie jest formalnością: ten sam tekst zakodowany jak dokument, a nie jak pytanie, jest wart siedem setnych recall@5. Na modelach z rodziny E5, BGE i innych z asymetrycznymi prefiksami koduj hipotezę jak dokument.

Poza tym HyDE przegrywa z multi-query na każdej metryce z jednym wyjątkiem: pytania porównawcze mają przy nim recall@5 równy 0,77, najwięcej ze wszystkich technik w rozdziale. Hipotetyczna odpowiedź opisuje obie strony porównania naraz, więc jej wektor leży pomiędzy dwiema trafnymi sekcjami.

Wadę widać dopiero w rozbiciu per pytanie. Wariant `query: ` naprawia wszystkie dziewięć porażek baseline'u, ale psuje sześć pytań o konkretną liczbę albo nazwę własną, które baseline miał dobrze: zmyślona odpowiedź wstawia w takim miejscu zmyśloną liczbę, a wyszukiwanie posłusznie za nią idzie. Wariant `passage: ` psuje tylko dwa, a doklejenie oryginału jako drugiej listy w RRF nie psuje ani jednego. Stąd reguła obowiązująca w całym rozdziale: **oryginalne pytanie zostaje w puli, zawsze**. Kosztuje jedno zapytanie do bazy i jest ubezpieczeniem od halucynacji przekształcenia.

## Step-back i dekompozycja pytań złożonych

Dwie techniki dla pytań, którym nie brakuje słów, tylko struktury.

Step-back prompting (arXiv 2310.06117) każe modelowi cofnąć się o krok: zamiast „ile tokenów dokłada `tool_choice`” pytać „jak liczone są tokeny przy użyciu narzędzi”, licząc na to, że sekcja wyjaśniająca mechanizm zawiera też konkretną liczbę. Tej techniki **nie zmierzyłem**: dobrego pytania cofniętego o krok nie da się napisać, nie znając struktury korpusu, a znając ją, mierzyłbym siebie. `expand_query(..., mode="step-back")` zwraca parę (pytanie, pytanie ogólniejsze) do fuzji – to przegląd, nie rekomendacja poparta liczbą.

Dekompozycja jest mierzalna. Pytanie porównawcze rozkładasz na dwa podpytania, każde o jedną stronę porównania, wyszukujesz osobno i scalasz wyniki.

```python
from ragbook.queries import DECOMPOSE_PROMPT, Decomposition, multi_retrieve

response = client.messages.parse(
    model="claude-haiku-4-5", max_tokens=512,
    messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(question=question)}],
    output_format=Decomposition,
)
hits = multi_retrieve(index.search, response.parsed_output.subquestions, k=5)
```

Przykładowy wynik dla pytania „HNSW czy IVF: czym te dwa indeksy się różnią i co się w nich kręci?”:

```text
jak działa indeks HNSW i jakimi parametrami się go stroi
jak działa indeks IVF i co robi parametr nprobe
```

| Wariant (11 pytań porównawczych) | recall@5 | MRR@5 | Obie sekcje w top-5 |
|---|---|---|---|
| baseline | 0,64 | 0,75 | 3 z 11 |
| dekompozycja (2 podpytania, RRF) | 0,68 | 0,78 | 4 z 11 |
| dekompozycja + pytanie (RRF) | 0,68 | 0,80 | 4 z 11 |
| multi-query (pytanie + 2 rewrite'y) | **0,73** | **0,89** | **5 z 11** |

Skrypt: `experiments/04_queries.py`.

To jest wynik negatywny i tak go zapisuję: dekompozycja, choć skrojona dokładnie pod ten typ pytań, wypada gorzej niż zwykłe multi-query. Powód jest arytmetyczny. Dwa podpytania są semantycznie odległe, więc każde ściąga własną listę, a RRF musi je przepleść w jednej piątce, oddając po dwa–trzy sloty na stronę. Gdy trafna sekcja jednej strony jest na drugim miejscu swojej listy, w scalonej piątce nie ma już dla niej miejsca. Dekompozycja zarabia na siebie dopiero wtedy, gdy każde podpytanie dostaje **własny budżet slotów** – a to jest już architektura agentowa z rozdziału 7.

## Filtry po metadanych i self-query

Dotąd zmieniałem zapytanie; teraz zawężę przestrzeń przeszukiwania. Każdy chunk niesie w payloadzie numer rozdziału, nazwę sekcji i – od tego rozdziału – tag `kind` o wartości `prose`, `code` albo `table`. Qdrant przyjmuje filtr w `query_filter` i stosuje go **w trakcie** przeszukiwania indeksu, a nie po nim. To różnica między „daj 5 najbliższych z rozdziału 10” a „daj 5 najbliższych i odrzuć te spoza rozdziału 10”, czyli między pięcioma wynikami a zerem.

```python
from qdrant_client import models
from ragbook.queries import tag_chunks, chapter_filter

chunks = tag_chunks(chunks)            # dokłada meta["kind"]: prose / code / table
index = DenseIndex(embedder, chunks)   # payload: chapter, section, kind, ...

hits = index.search("Jak podpiąć lokalny serwer narzędzi?", k=5,
                    query_filter=chapter_filter(10, kind="code"))
# chapter_filter buduje models.Filter(must=[FieldCondition(key="chapter", ...),
#                                           FieldCondition(key="kind", ...)])
```

Tag `kind` liczę heurystyką po gęstości znaków i na baseline'owych chunkach daje 65 procent prozy, 31 procent kodu i 4 procent tabel – mniej więcej tyle, ile wynosi udział kodu i tabel policzony w rozdziale 1.

Ile taki filtr daje i ile kosztuje, gdy jest zły? Górną granicę wyznacza filtr wyroczni, budowany z numeru rozdziału z golden setu; dolną – filtr wskazujący inny rozdział.

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| bez filtra | 0,72 | 0,96 | 9 |
| filtr rozdziału trafny (wyrocznia) | 0,88 | 0,99 | 2 |
| filtr rozdziału błędny | **0,00** | 0,00 | 49 |
| filtr `kind = prose` | 0,73 | 0,95 | 8 |

Skrypt: `experiments/04_filters.py`.

Ta tabela jest w całości o ryzyku: trafny filtr rozdziału podnosi wynik mocniej niż niejedna zmiana chunkera z rozdziału 2, a błędny zeruje go do końca, bo trafnej sekcji fizycznie nie ma w przeszukiwanym podzbiorze. Z obu granic wychodzi próg opłacalności – żeby filtrowanie nie pogorszyło systemu, ekstraktor filtru musi trafiać w co najmniej **83 procent** przypadków. Nie „zwykle działa dobrze”, tylko cztery na pięć i jeszcze trochę.

Filtr po typie treści nie zmienia nic i to też jest wynik: odsianie kodu nie pomaga, bo fragmenty kodu i tak nie wygrywały. Pytania, w których typ treści naprawdę decyduje, ma rozdział 5, razem z osobnymi zestawami.

Self-query to pomysł, żeby filtr wyciągał z pytania model: „w rozdziale o MCP, jak podpiąć lokalny serwer” ma dać `chapter = 10` i zapytanie bez tego fragmentu.

```python
from ragbook.queries import SELF_QUERY_PROMPT, ExtractedFilter

response = client.messages.parse(
    model="claude-haiku-4-5", max_tokens=512,
    messages=[{"role": "user", "content": SELF_QUERY_PROMPT.format(
        question="W rozdziale o MCP: jak podpiąć lokalny serwer narzędzi?")}],
    output_format=ExtractedFilter,
)
extracted = response.parsed_output
print(extracted.chapter, extracted.kind, extracted.query)
```

Przykładowy wynik:

```text
10 None jak podpiąć lokalny serwer narzędzi
```

Kod jest prosty, decyzja nie. Self-query wpuszczam do produkcji tylko z trzema zabezpieczeniami: pole `chapter` jest typu `int | None`, a prompt każe zostawiać `None`, gdy pytanie nie wskazuje rozdziału wprost; zamiast `must` puszczam dwa zapytania, z filtrem i bez, i scalam je RRF-em; loguję, jak często ekstraktor coś wypełnia i z jakim skutkiem. Do tego osiem pytań z czterdziestu dziewięciu ma trafne sekcje w dwóch rozdziałach, więc dla nich nawet poprawny filtr po jednym rozdziale z definicji gubi połowę odpowiedzi.

Reguła na koniec: gdy metadane są twarde i podane przez interfejs – wybrany produkt, zakres dat, identyfikator klienta – filtr jest oczywistą wygraną. Gdy trzeba je zgadywać z języka naturalnego, jest zakładem.

## Routing: lokalne, globalne, poza domeną

Wszystko powyżej zakłada, że w ogóle chcemy szukać. Do produkcyjnego asystenta trafiają trzy rodzaje zapytań, a rozróżnia je jedno pytanie: gdzie leży odpowiedź.

**Lokalne** – w kilku sekcjach korpusu, jak przy „Jak podmienić model embeddingowy w działającym systemie?”. Idą normalną ścieżką RAG. Należą tu także pytania negatywne z golden setu: „Jak skonfigurować replikację strumieniową PostgreSQL?” brzmi dokładnie jak pytanie do tej dokumentacji, tylko odpowiedzi w niej nie ma. To wciąż pytanie w domenie, a odmowa jest zadaniem generacji (rozdział 6) – router, który zaczyna zgadywać, czego w korpusie nie ma, skasuje też pytania, na które system umie odpowiedzieć.

**Globalne** – nie w żadnej sekcji, tylko w strukturze całego korpusu. „Ile rozdziałów tej dokumentacji mówi o kosztach?” nie ma odpowiedzi w pięciu fragmentach i nie będzie jej miało przy żadnym `k`; potrzebny jest map-reduce po sekcjach albo rachunek na metadanych indeksu. Puszczone przez RAG kończy się odpowiedzią pewną siebie i zlepioną z pięciu przypadkowych fragmentów.

**Poza domeną** – nigdzie, bo odpowiedzi nie szukamy wcale. „Jaka jest pogoda w Krakowie?” i „Dzięki, to wszystko” nie potrzebują retrievalu nie dlatego, że by zaszkodził, tylko dlatego, że kosztuje embedding, zapytanie do bazy i pięć fragmentów w prompcie, za które płacisz, żeby model odpowiedział „cześć”.

Klasyfikator LLM-owy to jedno wywołanie ze structured outputs: `ragbook.routing.Intent` ma pole `route` typu `Literal["local", "global", "out_of_domain"]`, więc schemat wymusza jedną z trzech wartości. Da się jednak taniej i lokalnie. Te trzy klasy różnią się stylem, a nie treścią, więc kilka przykładów na klasę wystarcza: liczysz embedding pytania (i tak go policzysz na potrzeby retrievalu), porównujesz z centroidem każdej klasy i bierzesz najbliższy.

```python
from ragbook.embed import Embedder
from ragbook.routing import EmbeddingRouter, load_routing

prototypes = [(r.question, r.label) for r in load_routing() if r.split == "prototype"]
router = EmbeddingRouter(Embedder(), prototypes, mode="centroid")   # 4 przykłady na klasę

route, margin = router.route("Ile rozdziałów tej dokumentacji mówi o kosztach?")
print(route, round(margin, 3))        # global 0.055
```

Zmierzyłem to na trzydziestu etykietowanych pytaniach z `data/routing.jsonl`: dwanaście z golden setu (wszystkie jako `local`), osiem globalnych i dziesięć spoza domeny. Dwanaście prototypów to osobne pytania, których w zbiorze testowym nie ma.

| Prawda (wiersze) / predykcja (kolumny) | local | global | out_of_domain |
|---|---|---|---|
| **local** (12) | 12 | 0 | 0 |
| **global** (8) | 1 | 7 | 0 |
| **out_of_domain** (10) | 1 | 0 | 9 |

Skrypt: `experiments/04_routing.py`.

Dwanaście przykładów i zero kosztu API dają trafność 0,93 – najlepszy stosunek zysku do pracy w tym rozdziale. Ważniejszy od liczby jest kształt obu pomyłek: idą w bezpieczną stronę, bo klasyfikator woli uznać pytanie za lokalne, czyli poszukać, niż je odrzucić albo puścić kosztowną ścieżką globalną. „Jak dojechać z Katowic do Wrocławia pociągiem?” ma kształt pytania proceduralnego, których w klasie `local` jest pełno. Wariant kNN wypada wyraźnie gorzej, 0,83, bo przy czterech przykładach na klasę trzy głosy potrafi zdominować jeden nietypowy prototyp.

`route` zwraca też margines, czyli różnicę podobieństw między najlepszą a drugą klasą. Przy progu 0,02 klasyfikator odpowiada na 24 z 30 pytań i **nie myli się ani razu**; pozostałe sześć posyłasz do modelu albo domyślnie traktujesz jako lokalne. To typowy układ produkcyjny: tani klasyfikator obsługuje pewną większość ruchu, drogi dostaje resztę – tutaj za 59 milisekund na CPU, bo ten sam wektor zużywa potem retrieval.

Dwa przypadki, w których też nie szukamy, do routera nie należą: pytanie zadane wcześniej obsługuje cache (rozdział 8), a pytanie wymagające obliczenia – narzędzie liczące na danych (tom 1, rozdział 9).

## Koszt przekształceń

Każde przekształcenie to jedno dodatkowe wywołanie modelu przed właściwym wyszukiwaniem. Tokeny policzyłem tokenizerem e5 na prawdziwych promptach z `ragbook/queries.py`, a rachunek zrobiłem po cenniku `claude-haiku-4-5` (stan na wrzesień 2026).

| Technika | Tokeny wejścia | Tokeny wyjścia | USD / 1000 zapytań | Retrievali |
|---|---|---|---|---|
| query rewriting (2 warianty) | 107 | 52 | 0,37 | 3 |
| HyDE | 109 | 87 | 0,55 | 1 |
| step-back | 71 | 28 | 0,21 | 2 |
| dekompozycja (porównawcze) | 98 | 40 | 0,30 | 2 |
| self-query (filtr z pytania) | 197 | 42 | 0,40 | 1 |
| routing intencji (LLM) | 241 | 24 | 0,36 | 1 |

Skrypt: `experiments/04_cost.py`.

Rachunek za przekształcenia ginie przy rachunku za generację: prompt RAG z pięcioma fragmentami po 128 tokenów to około 900 tokenów wejścia, czyli 0,90 USD na tysiąc zapytań na tym samym tanim modelu i ponad cztery razy tyle na `claude-opus-5`. Routing, multi-query i HyDE naraz kosztują 1,28 USD.

Prawdziwym kosztem jest latencja, bo wywołania są **szeregowe**: użytkownik czeka na przekształcenie, potem na retrieval, potem na generację. Multi-query jest pod tym względem tanie, bo jedno wywołanie daje dwa warianty, a trzy zapytania do bazy idą równolegle. HyDE jest drogie nie ceną, tylko czasem. Routing rób lokalnym klasyfikatorem, bo dotyka **każdego** zapytania, także tych, których i tak nie obsłużymy.

## Wszystko razem

Rozdziały 2, 3 i 4 mierzyły się osobno, każdy na baseline'owym indeksie, żeby wpływ każdej zmiany był czysty. Czas złożyć je w jeden potok: chunker z rozdziału 2, hybryda z rerankerem z rozdziału 3 i przekształcenia zapytań stąd. Kandydatów ze wszystkich wariantów scalam RRF-em **przed** rerankingiem, żeby cross-enkoder uruchamiał się raz na pytanie, a nie raz na wariant.

```python
from ragbook.chunking import project_chunks
from ragbook.corpus import load_sections
from ragbook.embed import Embedder
from ragbook.hybrid import project_retriever
from ragbook.queries import ClaudeLLM, expand_query, rrf

embedder, llm = Embedder(), ClaudeLLM()                        # ClaudeLLM chce klucza API
chunks = project_chunks(load_sections(), embedder.tokenizer)
retriever = project_retriever(chunks, embedder=embedder)       # hybryda + reranking

def retrieve(question: str, k: int = 5):
    queries = expand_query(question, llm, mode="multi")         # pytanie + 2 przeformułowania
    pool = rrf([retriever.candidates(q, 30) for q in queries], limit=30)
    return retriever.reranker.rerank(question, pool, top_k=k)
```

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| baseline z rozdziału 1 | 0,72 | 0,96 | 9 |
| rozdz. 2 + 3 (pytanie użytkownika) | **0,88** | 0,92 | 3 |
| rozdz. 2 + 3 + multi-query | 0,85 | 0,98 | 3 |
| rozdz. 2 + 3 + HyDE + pytanie | 0,86 | **0,99** | 3 |

Skrypt: `experiments/04_full_stack.py`.

I to jest najważniejszy wynik tego rozdziału, choć nie ten, na który liczyłem. **Na gotowym potoku z rozdziałów 2 i 3 przekształcanie zapytań nie daje już nic na `k` równym 5, a nawet odrobinę odbiera.** Multi-query zmienia wynik pięciu pytań z czterdziestu dziewięciu: jedno poprawia, cztery psuje. Wszystko mieści się w szumie, o którym rozdział 1 mówił, że różnicę czyta się liczbą pytań, a nie trzecią cyfrą średniej – ale kierunek jest wymowny.

Powód widać, gdy zestawi się listy naprawionych pytań. Dziewięć porażek baseline'u to nie dziewięć niezależnych usterek, tylko jedna usterka widziana z czterech stron: trafna sekcja była w dwudziestce, ale nie w piątce. Chunking z rozdziału 2 podnosi ją pełniejszym fragmentem z nagłówkiem, BM25 z rozdziału 3 – trafieniem w identyfikator, reranker – oceną pary pytanie-fragment, przekształcenie zapytania – dopasowaniem słów. To są cztery klucze do tych samych drzwi, a drugi klucz nie otwiera ich bardziej. **Każda z tych technik naprawia w dużej mierze te same pytania, więc ich efekty się nie sumują, tylko nakładają.** Kto zmierzy dwie z nich osobno na baseline i doda obie poprawy, dostanie liczbę, której nigdy nie zobaczy w produkcji. Rozdział 3 zauważył to samo o hybrydzie i rerankingu; tutaj widać, że reguła obejmuje cały potok.

Jedna kolumna jednak rośnie wyraźnie: recall@20 idzie z 0,92 do 0,98 przy multi-query i do 0,99 przy HyDE z pytaniem. To nie jest kosmetyka, bo recall@20 jest sufitem dla wszystkiego, co dzieje się dalej – reranker nie postawi wysoko fragmentu, którego w ogóle nie dostał. Przekształcanie zapytań przestaje więc być techniką poprawiającą wynik, a staje się techniką poszerzającą pulę kandydatów. Tak trzeba je ustawić w potoku: przed rerankingiem, z fuzją RRF i z oryginalnym pytaniem w środku.

Stąd decyzja dla projektu. **Zostaje `ragbook.routing.route`** z klasyfikatorem centroidowym i progiem marginesu: kosztuje jeden embedding, a klasa, której RAG naprawdę nie obsłuży (`global`), zostaje odcięta, zanim zmarnuje pięć slotów promptu. **Zostaje `ragbook.queries.expand_query`**, ale w domyślnej ścieżce wyłączone – włączam je, gdy system nie ma rerankera (na samym indeksie gęstym daje od trzynastu do dwudziestu jeden setnych recall@5), gdy zależy mi na recall@20 przed drogim rerankingiem i jako drugą próbę po słabym pierwszym wyszukaniu.

**Nie zostaje dekompozycja** – przegrywa z multi-query na własnym poletku i wraca w rozdziale 7. **Nie zostaje self-query jako twardy filtr**; wchodzi wyłącznie jako druga, filtrowana lista scalana RRF-em z listą bez filtra. Filtry po metadanych podanych jawnie przez interfejs zostają bez zastrzeżeń – tam nie ma czego zgadywać.

## Podsumowanie

- Na baseline'owym indeksie z rozdziału 1 samo przepisanie pytania podnosi recall@5 z 0,72 do 0,85, a multi-query (pytanie plus dwa przeformułowania, fuzja RRF) do 0,93 i zeruje liczbę pytań bez trafienia.
- Pojedyncze przepisanie psuje część pytań, które działały, więc oryginalne pytanie zostaje w puli zawsze; przy HyDE bez tego zabezpieczenia wypada z piątki sześć pytań o liczby i nazwy własne.
- HyDE na modelu z asymetrycznymi prefiksami koduj jak dokument (`passage: `), nie jak zapytanie – ta jedna zmiana to siedem setnych recall@5.
- Dekompozycja pytań porównawczych wypada gorzej niż zwykłe multi-query (0,68 wobec 0,73), bo dwie listy wyników muszą się zmieścić we wspólnej piątce; ma sens dopiero z osobnym budżetem slotów na podpytanie.
- Trafny filtr rozdziału daje 0,88, błędny daje 0,00 – próg opłacalności self-query to 83 procent trafności ekstraktora, więc filtr wyciągnięty z języka naturalnego stosuj jako drugą listę scalaną RRF-em, a nie jako `must`.
- Routing na trzy klasy da się zrobić lokalnie: centroidy z czterech przykładów na klasę dają trafność 0,93, a przy progu marginesu 0,02 nie mylą się ani razu na 24 z 30 pytań. Pytania negatywne z golden setu są przy tym **w domenie** – router ma je puścić przez RAG, a odmowa należy do generacji (rozdział 6).
- Przekształcenia kosztują od 0,21 do 0,55 USD na tysiąc zapytań, czyli ułamek kosztu generacji; ograniczeniem jest latencja szeregowego wywołania, a nie rachunek.
- Na pełnym potoku z rozdziałów 2 i 3 przekształcanie zapytań nie poprawia już recall@5 (0,85–0,86 wobec 0,88), bo naprawia te same pytania co lepszy chunking i reranking; podnosi natomiast recall@20 z 0,92 do 0,98–0,99, czyli sufit dla wszystkiego, co dzieje się dalej.

## Co dalej

Rozdział 5 wychodzi poza czysty Markdown: bierze ten sam korpus w formie PDF-a ze składu, z dwułamowym układem i tabelami, i sprawdza, ile z zawartości da się odzyskać oraz jak chunkować tabele i bloki kodu, żeby dało się o nie pytać. Zanim tam przejdziesz, zrób jedno ćwiczenie z własnym kluczem API: podstaw `ClaudeLLM()` w miejsce `ScriptedLLM` w `experiments/04_queries.py` i uruchom ten sam skrypt. Porównanie Twoich liczb z tabelami powie Ci to, czego ja zmierzyć nie mogłem.

## Źródła

- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/api/messages
- https://qdrant.tech/documentation/concepts/filtering/
- https://qdrant.tech/documentation/concepts/hybrid-queries/
- https://arxiv.org/abs/2212.10496
- https://arxiv.org/abs/2310.06117
- https://huggingface.co/intfloat/multilingual-e5-small
