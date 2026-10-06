# Rozdział 4. Przekształcanie zapytań, filtry i routing

> **Cel rozdziału:** naprawić te porażki baseline'u, które biorą się z samego sformułowania pytania, i zdecydować, kiedy w ogóle warto szukać – przekształcając zapytanie, filtrując po metadanych albo odrzucając zapytanie na wejściu.
>
> **Kod:** `ragbook/queries.py`, `ragbook/routing.py`, `experiments/04_*.py`. **Pakiety poza fundamentem:** brak.

Rozdziały 2 i 3 poprawiały to, co leży w indeksie: kształt fragmentów i sposób ich wyszukiwania. Ten rozdział nie dotyka indeksu ani razu. Zmienia tylko jedno – ciąg znaków, który trafia do wyszukiwarki – i to wystarczy, żeby na baseline'owym indeksie z rozdziału 1 podnieść recall@5 z 0,72 do 0,93 i zejść z dziewięciu pytań bez trafienia do zera. Kosztem jednego dodatkowego wywołania taniego modelu na zapytanie.

Rozdział 1 zostawił mi dwie z czterech kategorii porażek. Pierwsza to parafraza bez wspólnych słów: q007 („Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?”) ma odpowiedź w sekcji, w której nie ma ani słowa „drożej”, ani „napisze”. Druga to pytanie o dwóch odpowiedziach naraz: q032 potrzebuje sekcji z rozdziału 6 i z rozdziału 7, a wyszukiwanie po podobieństwie uparcie zwraca pięć fragmentów z jednego miejsca; dziewięć kolejnych pytań ma z tego powodu recall@5 równy dokładnie 0,5.

Jedna uwaga metodologiczna, zanim zobaczysz pierwszą tabelę. **Każde przekształcenie zapytania wymaga wywołania modelu, a ja nie mam klucza API** – więc warianty napisałem ręcznie. W `data/query_variants.jsonl` leżą dla wszystkich 49 pytań pozytywnych po dwa przeformułowania i jedna hipotetyczna odpowiedź w stylu HyDE, a dla jedenastu pytań porównawczych po dwa podpytania; pisałem je, patrząc wyłącznie na pytanie, nigdy na tekst trafnej sekcji, bo inaczej mierzyłbym własną znajomość korpusu. Retrieval, korpus i metryki są prawdziwe i policzone na tym samym zamrożonym zestawie co wszędzie indziej; **od człowieka pochodzą tylko warianty zapytań, więc czytaj te liczby jako górną granicę tego, co osiągnie model, a nie jako prognozę**. `ragbook.queries` ma wymienny adapter LLM-a właśnie po to, żebyś z własnym kluczem powtórzył cały pomiar bez zmiany linijki w eksperymencie. Skrypty uruchamiasz z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/04_queries.py`.

## Query rewriting: z potocznego na precyzyjne

Najprostsza z technik. Bierzesz pytanie użytkownika, prosisz tani model o przepisanie go na samodzielne zapytanie wyszukiwawcze – z terminologią, nazwami parametrów, bez zaimków i bez odwołań do wcześniejszej rozmowy – i szukasz tym, co wróci. Cała wartość siedzi w słowie „samodzielne”: w produkcji pytanie przychodzi w kontekście rozmowy („a ile to kosztuje?”) i jako zapytanie do wyszukiwarki nie znaczy nic.

Wynik ma ustaloną strukturę, więc to jest podręcznikowe zastosowanie structured outputs (tom 1, rozdział 3): model zwraca listę stringów, a nie prozę, którą musiałbyś parsować regexem.

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

`messages.parse` z `output_format` zwraca gotową instancję klasy w `parsed_output`; niskopoziomowy odpowiednik przez `output_config={"format": {"type": "json_schema", ...}}` opisuje tom 1, rozdział 3. Model jest tani celowo – `claude-haiku-4-5` kosztuje dolara za milion tokenów wejścia i pięć za milion wyjścia (stan na wrzesień 2026), a zadanie jest mechaniczne. W prompcie z `ragbook/queries.py` istotne są dwie rzeczy: jawny zakaz odpowiadania na pytanie (inaczej model zgaduje odpowiedź zamiast przepisywać zapytanie) i prośba o warianty „trafiające w tę samą potrzebę informacyjną innymi słowami”, bez której dostajesz dwie parafrazy różniące się szykiem.

I teraz pomiar. Kolumna z baseline'em to dokładnie te same liczby co w rozdziale 1, tylko po to, żeby było od czego odejmować.

| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| baseline (pytanie użytkownika) | 49 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| rewrite 1 | 49 | 0,85 | 0,94 | 0,79 | 0,76 | 4 |
| rewrite 2 | 49 | 0,83 | 0,97 | 0,72 | 0,71 | 5 |

Skrypt: `experiments/04_queries.py`.

Trzynaście setnych recall@5 z samego przepisania pytania. Pierwszy wariant naprawia siedem z dziewięciu porażek baseline'u (q007, q021, q022, q023, q032, q037, q039), drugi – też siedem, ale częściowo inne. Widać to w rozbiciu na typy: pierwszy podnosi pytania faktograficzne z 0,81 do 0,96, drugi zostawia je na 0,85, za to winduje proceduralne z 0,62 do 0,96. Różnica wynika ze stylu przeformułowania: zapytanie nazywające parametr trafia w zdanie z tym parametrem, a zapytanie opisujące procedurę – w akapit ją opisujący.

Jest też strata i warto ją zobaczyć. Pierwszy wariant psuje trzy pytania, które baseline miał dobrze (q041 i q042 wypadają z top-5 całkowicie), a recall@20 spada z 0,96 do 0,94. Przepisując pytanie, zawężasz je – i czasem zawęzisz w złą stronę. To jest dokładny powód, dla którego produkcyjnie prawie nikt nie używa rewritingu w wersji „jedno pytanie w, jedno w zamian”.

## Multi-query: trzy zapytania i fuzja RRF

Skoro każdy wariant zapytania naprawia inne pytania i psuje inne, nie wybieraj. Puść wszystkie trzy – oryginał plus dwa przeformułowania – i połącz listy wyników. Do łączenia służy ta sama fuzja rangowa, którą rozdział 3 stosował do hybrydy leksykalno-gęstej: reciprocal rank fusion sumuje po listach wartości $1/(k + \mathrm{rank})$, a więc patrzy wyłącznie na pozycje, nie na wyniki podobieństwa. To jest tu istotne, bo wyniki dla różnych zapytań nie są porównywalne między sobą, a rangi są.

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

To jest q007, pierwsza z porażek baseline'u. Trafna sekcja „Trening a inferencja”, której w czołowej piątce baseline'u nie było wcale, wchodzi na drugie miejsce – i to wystarcza, bo recall liczymy z całej piątki. Zwróć uwagę na wartości: trzy pierwsze pozycje mają dokładnie tyle samo, $1/61 \approx 0,0164$, bo każda z nich była pierwsza w dokładnie jednej z trzech list. RRF widzi wyłącznie rangi, więc remisy są w nim normą, a o kolejności wewnątrz remisu decyduje przypadek. Jeżeli remis przebiega dokładnie na granicy `k`, tracisz trafienie z powodu porządku iteracji po słowniku. To jeden z powodów, dla których rozdział 3 kończy potok rerankerem: cross-enkoder ma czym te trzy fragmenty rozróżnić.

| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| baseline (pytanie użytkownika) | 49 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| rewrite 1 | 49 | 0,85 | 0,94 | 0,79 | 0,76 | 4 |
| multi-query (pytanie + 2 rewrite'y, RRF) | 49 | **0,93** | 0,98 | **0,81** | **0,80** | **0** |

Skrypt: `experiments/04_queries.py`.

Zero pytań bez trafienia. Wszystkie dziewięć porażek z rozdziału 1 – q007, q021, q022, q023, q029, q032, q033, q037, q039 – ma w czołowej piątce trafną sekcję, łącznie z q039, którego baseline nie znajdował nawet w dwudziestce. Trzynaście pytań poprawiło wynik, jedno pogorszyło; po typach: faktograficzne 1,00, proceduralne 0,96, porównawcze 0,73. Mechanizm jest taki, jak zapowiadała różnica między wariantami: pytania, które jeden wariant psuje, ratuje drugi i oryginał.

Kiedy nie warto: multi-query kosztuje tyle samo wywołań LLM-a co zwykły rewriting (jedno, bo oba warianty powstają w jednej odpowiedzi), ale trzy razy więcej zapytań do bazy – przy dziesiątkach milionów wektorów i indeksie na dysku to koszt, który trzeba policzyć. Druga granica jest jakościowa: RRF premiuje dokumenty widoczne w wielu listach, więc zapytanie wyraźnie gorsze od pozostałych dokłada szumu do czołówki, co przy sześciu i więcej wariantach staje się widoczne.

## HyDE: embedujemy odpowiedź, nie pytanie

HyDE (hypothetical document embeddings, arXiv 2212.10496) wychodzi od obserwacji, że pytanie i odpowiedź to dwa różne gatunki tekstu: pytanie jest krótkie i ma słowa, których w dokumentacji nie ma („ile razy drożej”), dokument jest twierdzeniem z terminologią. Model embeddingowy mierzy podobieństwo, a nie relację „to jest odpowiedź na tamto” – więc zamiast szukać pytaniem, każ modelowi napisać zmyśloną odpowiedź i szukaj nią. Hipoteza może być merytorycznie błędna; liczy się, że jest napisana w rejestrze dokumentacji.

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

W tym kodzie jest jedna decyzja, której w oryginalnej pracy nie ma, bo dotyczy konkretnej rodziny modeli embeddingowych. E5 wymaga prefiksu: `query: ` dla zapytań, `passage: ` dla dokumentów (tom 1, rozdział 6). Hipotetyczna odpowiedź **jest** dokumentem, więc pytanie brzmi, którym prefiksem ją zakodować. Zmierzyłem oba warianty i różnica jest większa, niż się spodziewałem.

| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| baseline | 49 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| HyDE (hipoteza jako `query: `) | 49 | 0,81 | 0,98 | 0,68 | 0,68 | 6 |
| HyDE (hipoteza jako `passage: `) | 49 | 0,88 | 0,96 | 0,70 | 0,72 | 3 |
| HyDE + pytanie (RRF) | 49 | 0,91 | 0,98 | 0,74 | 0,75 | 1 |
| multi-query (dla porównania) | 49 | 0,93 | 0,98 | 0,81 | 0,80 | 0 |

Skrypt: `experiments/04_queries.py`.

Siedem setnych różnicy między dwoma prefiksami tego samego tekstu – tyle kosztuje potraktowanie hipotezy jak pytania. Jeśli używasz modelu z rodziny E5, BGE albo innego z asymetrycznymi prefiksami, koduj hipotezę jak dokument.

Sam HyDE, nawet w lepszym wariancie, przegrywa z multi-query na każdej metryce oprócz jednej: pytania porównawcze mają przy nim recall@5 równy 0,77, najwięcej ze wszystkich technik w tym rozdziale (multi-query daje 0,73). To ma sens – hipotetyczna odpowiedź na pytanie porównawcze opisuje obie strony porównania naraz, więc jej wektor leży pomiędzy dwiema trafnymi sekcjami.

Ma też wyraźną wadę, widoczną dopiero w rozbiciu per pytanie. HyDE w wariancie `query: ` naprawia wszystkie dziewięć porażek baseline'u, ale **psuje sześć pytań, które baseline miał dobrze**: q001, q004, q006, q027, q041, q043. Wszystkie sześć to pytania o konkretną liczbę albo nazwę własną – limit rozmiaru pliku, nazwa metody klienta, cena planu – a zmyślona odpowiedź podaje w tych miejscach zmyśloną liczbę i zmyśloną nazwę. Wariant `passage: ` psuje już tylko dwa pytania, a doklejenie oryginalnego pytania jako drugiej listy w RRF nie psuje ani jednego. Stąd reguła obowiązująca w całym rozdziale: **oryginalne pytanie zostaje w puli, zawsze**. Kosztuje jedno zapytanie do bazy i jest ubezpieczeniem od halucynacji przekształcenia.

## Step-back i dekompozycja pytań złożonych

Dwie techniki dla pytań, którym nie brakuje słów, tylko struktury.

Step-back prompting (arXiv 2310.06117) każe modelowi cofnąć się o krok: zamiast „ile tokenów dokłada `tool_choice`” pyta „jak liczone są tokeny przy użyciu narzędzi”, licząc na to, że sekcja wyjaśniająca mechanizm zawiera też konkretną liczbę. Tej techniki **nie zmierzyłem**: dobrego pytania cofniętego o krok nie da się napisać, nie znając struktury korpusu, a znając ją, mierzyłbym siebie. `ragbook.queries.step_back_query` implementuje ją poprawnie, a `expand_query(..., mode="step-back")` zwraca parę (pytanie, pytanie ogólniejsze) do fuzji – traktuj to jako przegląd, nie jako rekomendację popartą liczbą.

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

Przykładowy wynik dla q047 („HNSW czy IVF: czym te dwa indeksy się różnią i co się w nich kręci?”):

```text
jak działa indeks HNSW i jakimi parametrami się go stroi
jak działa indeks IVF i co robi parametr nprobe
```

Pomiar tylko na jedenastu pytaniach porównawczych, bo tylko tam dekompozycja ma sens.

| Wariant | Pytań | recall@5 | MRR@5 | nDCG@5 | Obie sekcje w top-5 |
|---|---|---|---|---|---|
| baseline | 11 | 0,64 | 0,75 | 0,58 | 3 z 11 |
| dekompozycja (2 podpytania, RRF) | 11 | 0,68 | 0,78 | 0,61 | 4 z 11 |
| dekompozycja + pytanie (RRF) | 11 | 0,68 | 0,80 | 0,65 | 4 z 11 |
| multi-query (pytanie + 2 rewrite'y) | 11 | **0,73** | **0,89** | **0,71** | **5 z 11** |

Skrypt: `experiments/04_queries.py`.

To jest wynik negatywny i tak go zapisuję: **dekompozycja, mimo że jest techniką skrojoną dokładnie pod ten typ pytań, wypada gorzej niż zwykłe multi-query**. Cztery pytania z jedenastu mają w piątce obie potrzebne sekcje, przy pięciu dla multi-query. Powód jest arytmetyczny: dwa podpytania są od siebie semantycznie odległe, więc każde ściąga własną listę, a RRF musi je przepleść w jednej piątce, oddając po dwa–trzy sloty na stronę. Gdy trafna sekcja jednej strony jest na drugim miejscu swojej listy, w scalonej piątce nie ma już dla niej miejsca. Dekompozycja zarabia więc na siebie dopiero wtedy, gdy każde podpytanie dostaje **własny budżet slotów** albo osobne wywołanie generacji – a to jest już architektura agentowa z rozdziału 7.

## Filtry po metadanych i self-query

Dotąd zmieniałem zapytanie. Teraz zawężę przestrzeń przeszukiwania. Każdy chunk w tym projekcie niesie w payloadzie numer rozdziału, nazwę sekcji i – od tego rozdziału – tag `kind` o wartości `prose`, `code` albo `table`. Qdrant przyjmuje filtr razem z zapytaniem, w `query_filter`, i stosuje go **w trakcie** przeszukiwania indeksu, a nie po nim; to jest różnica między „daj 5 najbliższych z rozdziału 10” a „daj 5 najbliższych i odrzuć te spoza rozdziału 10”, czyli między pięcioma wynikami a zerem.

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

Tag `kind` liczę heurystyką po gęstości znaków: pionowe kreski to tabela, nawiasy, znaki równości i backticki to kod. Progi kalibrowałem na tym korpusie i na baseline'owych chunkach dają 65 procent prozy, 31 procent kodu i 4 procent tabel, czyli mniej więcej tyle, ile wynosi udział kodu i tabel policzony w rozdziale 1. Uwaga praktyczna: `tokenizer.decode` gubi znaki końca linii, więc heurystyka liczona po liniach na chunkach ze stałego okna nie zadziała; rozdział 2 nadaje ten sam tag przy chunkowaniu, gdzie ma do dyspozycji nieprzycięty Markdown.

Pytanie brzmi: ile taki filtr daje i ile kosztuje, gdy jest zły. Górną granicę wyznacza filtr wyroczni, budowany z numeru rozdziału zapisanego w golden secie; dolną – filtr wskazujący deterministycznie wybrany inny rozdział.

| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| bez filtra | 49 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| filtr rozdziału trafny (wyrocznia) | 49 | 0,88 | 0,99 | 0,80 | 0,78 | 2 |
| filtr rozdziału błędny | 49 | **0,00** | 0,00 | 0,00 | 0,00 | 49 |
| filtr `kind = prose` | 49 | 0,73 | 0,95 | 0,66 | 0,65 | 8 |

Skrypt: `experiments/04_filters.py`.

Ta tabela jest w całości o ryzyku. Trafny filtr rozdziału daje szesnaście setnych recall@5 – więcej niż niejedna zmiana chunkera z rozdziału 2 – i naprawia dziewięć pytań. Błędny filtr daje dokładnie zero, bo trafnej sekcji fizycznie nie ma w przeszukiwanym podzbiorze. Z tych trzech liczb wychodzi próg opłacalności: żeby filtrowanie nie pogorszyło systemu, **ekstraktor filtru musi trafiać w co najmniej 83 procent przypadków**. Nie „zwykle działa dobrze”, tylko cztery na pięć i jeszcze trochę. Osiem pytań z czterdziestu dziewięciu ma przy tym trafne sekcje w dwóch różnych rozdziałach, więc dla nich poprawny filtr po jednym rozdziale z definicji gubi połowę odpowiedzi.

Filtr po typie treści nie zmienia nic (0,73 wobec 0,72) i to też jest wynik: na tym zestawie odpowiedzi leżą w prozie, ale odsianie kodu nie pomaga, bo fragmenty kodu i tak nie wygrywały. Pytania, w których typ treści naprawdę decyduje – o wartości z tabel i o identyfikatory w kodzie – ma rozdział 5, razem z osobnymi zestawami.

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

Kod jest prosty, a decyzja nie. Skoro błędny filtr zeruje wynik, a próg opłacalności wynosi 83 procent, self-query wpuszczam do produkcji tylko z trzema zabezpieczeniami: pole `chapter` jest typu `int | None`, a prompt każe zostawiać `None`, gdy pytanie nie wskazuje rozdziału wprost (domyślną odpowiedzią ma być „nie wiem”); zamiast filtrowania `must` puszczam dwa zapytania, z filtrem i bez, i scalam je RRF-em, co zamienia katastrofę w lekkie pogorszenie; i loguję, jak często ekstraktor coś wypełnia oraz z jakim skutkiem, bo bez tego nie wiadomo, po której stronie progu jesteś. Gdy metadane są twarde i podane przez interfejs (wybrany produkt, zakres dat, identyfikator klienta), filtr jest oczywistą wygraną. Gdy trzeba je zgadywać z języka naturalnego, jest zakładem.

## Routing: lokalne, globalne, poza domeną

Wszystko powyżej zakłada, że w ogóle chcemy szukać. Trzy rodzaje zapytań, które trafiają do produkcyjnego asystenta, wymagają trzech różnych reakcji.

**Lokalne** – „ile tokenów dokłada `tool_choice`”, „jak podmienić model embeddingowy” – mają odpowiedź w kilku sekcjach i idą normalną ścieżką RAG. Należą tu także pytania negatywne z golden setu: „jak skonfigurować replikację strumieniową PostgreSQL” brzmi dokładnie jak pytanie do tej dokumentacji, tylko odpowiedzi w niej nie ma. To wciąż pytanie w domenie, a odmowa jest zadaniem generacji (rozdział 6) – router, który zaczyna zgadywać, czego w korpusie nie ma, skasuje też pytania, na które system umie odpowiedzieć.

**Globalne** – „streść cały rozdział 9”, „ile rozdziałów mówi o kosztach”. Wyszukiwanie top-5 nie pomoże, bo odpowiedź nie leży w pięciu fragmentach, tylko w strukturze całego korpusu; reakcją jest map-reduce po sekcjach albo odpowiedź policzona z metadanych indeksu. Puszczenie takiego pytania przez RAG kończy się odpowiedzią pewną siebie i wziętą z pięciu przypadkowych fragmentów.

**Poza domeną** – „jaka jest pogoda w Krakowie”, „dzięki, to wszystko”. Tu nie szukamy wcale: nie dlatego, że retrieval by zaszkodził, tylko dlatego, że kosztuje embedding, zapytanie do bazy i pięć fragmentów w prompcie, za które płacisz, żeby model odpowiedział „cześć”.

Klasyfikator LLM-owy to jedno wywołanie ze structured outputs:

```python
from ragbook.routing import Intent, ROUTER_PROMPT

response = client.messages.parse(
    model="claude-haiku-4-5", max_tokens=256,
    messages=[{"role": "user", "content": ROUTER_PROMPT.format(
        question="Ile rozdziałów tej dokumentacji mówi o kosztach?")}],
    output_format=Intent,
)
print(response.parsed_output.route, "|", response.parsed_output.reason)
```

Przykładowy wynik:

```text
global | Pytanie wymaga przejrzenia wszystkich rozdziałów, a nie kilku fragmentów.
```

`Intent.route` jest typu `Literal["local", "global", "out_of_domain"]`, więc schemat wymusza jedną z trzech wartości i nie ma czego walidować po stronie kodu. Pole `reason` jest po to, żeby logi routingu dało się czytać, gdy zaczniesz szukać pomyłek.

Da się jednak taniej i – co ważniejsze dla tej książki – lokalnie. Klasy różnią się tu stylem, a nie treścią, więc kilka przykładów na klasę wystarcza: liczysz embedding pytania (i tak go policzysz na potrzeby retrievalu), porównujesz z centroidem każdej klasy i bierzesz najbliższy.

```python
from ragbook.embed import Embedder
from ragbook.routing import EmbeddingRouter, load_routing

prototypes = [(r.question, r.label) for r in load_routing() if r.split == "prototype"]
router = EmbeddingRouter(Embedder(), prototypes, mode="centroid")   # 4 przykłady na klasę

route, margin = router.route("Ile rozdziałów tej dokumentacji mówi o kosztach?")
print(route, round(margin, 3))        # global 0.055
```

Zmierzyłem to naprawdę, na trzydziestu etykietowanych pytaniach: dwanaście z golden setu (dziesięć pozytywnych i dwa negatywne, wszystkie jako `local`), osiem globalnych i dziesięć poza domeną napisanych na potrzeby tego rozdziału i zapisanych w `data/routing.jsonl`. Dwanaście prototypów to osobne pytania, których w zbiorze testowym nie ma.

| Prawda (wiersze) / predykcja (kolumny) | local | global | out_of_domain |
|---|---|---|---|
| **local** (12) | 12 | 0 | 0 |
| **global** (8) | 1 | 7 | 0 |
| **out_of_domain** (10) | 1 | 0 | 9 |

Skrypt: `experiments/04_routing.py`.

Dwadzieścia osiem na trzydzieści, trafność 0,93, przy dwunastu przykładach i zerowym koszcie API. Obie pomyłki idą w tę samą, bezpieczną stronę: klasyfikator woli uznać pytanie za lokalne (czyli poszukać) niż odrzucić je albo puścić kosztowną ścieżką globalną. „Ile łącznie bloków kodu w Pythonie jest w tej dokumentacji?” brzmi jak pytanie o liczbę z dokumentacji, a „Jak dojechać z Katowic do Wrocławia pociągiem?” ma kształt pytania proceduralnego, którego w klasie `local` jest pełno. Wariant kNN wypada wyraźnie gorzej, 0,83, bo przy czterech przykładach na klasę trzy głosy potrafi zdominować jeden nietypowy prototyp.

Ostatnia liczba jest praktyczna: `route` zwraca też margines, czyli różnicę podobieństw między najlepszą a drugą klasą. Przy progu 0,02 klasyfikator odpowiada na 24 z 30 pytań i **nie myli się ani razu**; pozostałe sześć to przypadki, które warto posłać do modelu albo domyślnie potraktować jako lokalne. To jest typowy układ produkcyjny: tani klasyfikator obsługuje pewną większość ruchu, a drogi dostaje resztę. Koszt lokalnego routera to 59 milisekund na CPU za embedding (ten sam wektor zużywa potem retrieval) plus trzy iloczyny skalarne.

Są jeszcze dwa przypadki, w których nie szukamy, a które do routera nie należą. Pytanie zadane wcześniej obsługuje cache – semantyczny cache odpowiedzi i cache embeddingów zapytań opisuje rozdział 8. Pytanie wymagające obliczenia albo agregacji („ile kosztowało mnie dziesięć tysięcy zapytań w zeszłym miesiącu”) należy nie do wyszukiwania, tylko do narzędzia liczącego na danych – function calling z tomu 1, rozdział 9. Router, który umie odesłać zapytanie do narzędzia, jest pierwszym krokiem w stronę agentowego RAG-u z rozdziału 7.

## Koszt przekształceń

Każde przekształcenie to dodatkowe wywołanie modelu przed właściwym wyszukiwaniem, więc dokłada latencji i tokenów. Poniższa tabela jest orientacyjna: tokeny policzyłem tokenizerem e5 na prawdziwych promptach z `ragbook/queries.py` i na wariantach z `data/query_variants.jsonl`, a rachunek zrobiłem po cenniku `claude-haiku-4-5` (1 USD za milion tokenów wejścia, 5 USD za milion wyjścia, stan na wrzesień 2026). Dokładną liczbę tokenów dla modelu generującego policzysz endpointem `count_tokens` (tom 1, rozdział 2).

| Technika | Wywołań LLM | Tokeny wejścia | Tokeny wyjścia | USD / 1000 zapytań | Retrievali |
|---|---|---|---|---|---|
| query rewriting (2 warianty) | 1 | 107 | 52 | 0,37 | 3 |
| HyDE | 1 | 109 | 87 | 0,55 | 1 |
| step-back | 1 | 71 | 28 | 0,21 | 2 |
| dekompozycja (porównawcze) | 1 | 98 | 40 | 0,30 | 2 |
| self-query (filtr z pytania) | 1 | 197 | 42 | 0,40 | 1 |
| routing intencji (LLM) | 1 | 241 | 24 | 0,36 | 1 |

Skrypt: `experiments/04_cost.py`.

Wszystkie te kwoty są małe wobec samej generacji: prompt RAG z pięcioma fragmentami po 128 tokenów to około 900 tokenów wejścia, czyli 0,90 USD na tysiąc zapytań na tym samym tanim modelu i ponad cztery razy tyle na `claude-opus-5`. Routing, multi-query i HyDE naraz to 1,28 USD na tysiąc zapytań.

Prawdziwym kosztem jest latencja, bo wywołanie jest **szeregowe**: użytkownik czeka na przekształcenie, potem na retrieval, potem na generację. Stąd trzy reguły. Multi-query jest tanie, bo jedno wywołanie daje dwa warianty, a trzy zapytania do bazy idą równolegle. HyDE jest drogie nie ceną, tylko czasem: wymaga wygenerowania dwóch–trzech zdań, a latencja rośnie z liczbą tokenów wyjścia. Routing rób lokalnym klasyfikatorem, bo dotyka **każdego** zapytania, także tych, których i tak nie obsłużymy.

## Wszystko razem

Rozdziały 2, 3 i 4 mierzyły się osobno, każdy na baseline'owym indeksie, żeby wpływ każdej zmiany był czysty. Czas złożyć je w jeden potok: chunker z rozdziału 2 (`ragbook.chunking.project_chunks`), retriever z rozdziału 3 (`ragbook.hybrid.project_retriever`: hybryda BM25 z wyszukiwaniem gęstym plus reranking cross-enkoderem) i przekształcenia zapytań stąd. Kandydatów ze wszystkich wariantów scalam RRF-em **przed** rerankingiem, żeby cross-enkoder uruchamiał się raz na pytanie, a nie raz na wariant.

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

| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| baseline z rozdziału 1 | 49 | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| rozdz. 2 + 3 (pytanie użytkownika) | 49 | **0,88** | 0,92 | 0,81 | **0,79** | 3 |
| rozdz. 2 + 3 + multi-query | 49 | 0,85 | 0,98 | **0,82** | 0,78 | 3 |
| rozdz. 2 + 3 + HyDE + pytanie | 49 | 0,86 | **0,99** | **0,82** | **0,79** | 3 |

Skrypt: `experiments/04_full_stack.py`.

I to jest najważniejszy wynik tego rozdziału, choć nie ten, na który liczyłem. **Na gotowym potoku z rozdziałów 2 i 3 przekształcanie zapytań nie daje już nic na `k` równym 5, a nawet odrobinę odbiera.** Multi-query zmienia pięć pytań z czterdziestu dziewięciu (poprawia q029, psuje q004, q034, q044 i q052), HyDE z pytaniem zmienia cztery (poprawia q029, psuje q004, q044 i q052); netto to jedno–dwa pytania na minus. Wszystko mieści się w szumie, o którym rozdział 1 mówił, że różnicę czyta się liczbą pytań, a nie trzecią cyfrą średniej – ale kierunek jest wymowny: warianty zapytania wpuszczają do puli fragmenty, które reranker czasem stawia wyżej niż właściwy.

Powód widać, gdy zestawi się listy naprawionych pytań. Dziewięć porażek baseline'u to nie dziewięć niezależnych usterek, tylko jedna usterka widziana z czterech stron: trafna sekcja była w dwudziestce, ale nie w piątce. Chunking z rozdziału 2 podnosi ją pełniejszym fragmentem z nagłówkiem, BM25 z rozdziału 3 – trafieniem w identyfikator, reranker – oceną pary pytanie-fragment, przekształcenie zapytania – dopasowaniem słów. **Każda z tych technik naprawia w dużej mierze te same pytania, więc ich efekty się nie sumują, tylko nakładają.** Kto zmierzy dwie z nich osobno na baseline i doda obie poprawy, dostanie liczbę, której nigdy nie zobaczy w produkcji.

Jedna kolumna jednak rośnie wyraźnie: recall@20 idzie z 0,92 do 0,98 przy multi-query i do 0,99 przy HyDE z pytaniem. To nie jest kosmetyka – recall@20 jest sufitem dla wszystkiego, co dzieje się dalej, bo reranker nie postawi wysoko fragmentu, którego nie dostał. Przekształcanie zapytań przestaje więc być techniką poprawiającą wynik, a staje się techniką poszerzającą pulę kandydatów, i tak trzeba je ustawić w potoku: przed rerankingiem, z fuzją RRF i z oryginalnym pytaniem w środku.

Decyzja dla projektu wygląda więc tak.

**Zostaje `ragbook.routing.route`** z klasyfikatorem centroidowym i progiem marginesu: trafność 0,93 przy dwunastu przykładach i koszcie jednego embeddingu to najlepszy stosunek zysku do pracy w całym rozdziale, a klasa, której RAG naprawdę nie obsłuży (`global`), zostaje odcięta, zanim zmarnuje pięć slotów promptu.

**Zostaje `ragbook.queries.expand_query`**, ale w domyślnej ścieżce wyłączone. Włączam je, gdy system nie ma rerankera (na samym indeksie gęstym daje od trzynastu do dwudziestu jeden setnych recall@5 i jest wtedy najtańszą dostępną poprawą), gdy zależy mi na recall@20 przed drogim rerankingiem i jako drugą próbę, gdy pierwsze wyszukanie zwróciło same słabe dopasowania. Reguła stała: **oryginalne pytanie nigdy nie wypada z puli**.

**Nie zostaje dekompozycja** – przegrywa z multi-query na własnym poletku i wraca w rozdziale 7, gdy podpytania dostaną osobne budżety kontekstu. **Nie zostaje self-query jako twardy filtr**; wchodzi wyłącznie jako druga, filtrowana lista scalana RRF-em z listą bez filtra. Filtry po metadanych podanych jawnie przez interfejs zostają bez zastrzeżeń – tam nie ma czego zgadywać.

## Podsumowanie

- Na baseline'owym indeksie z rozdziału 1 samo przepisanie pytania podnosi recall@5 z 0,72 do 0,85, a multi-query (pytanie plus dwa przeformułowania, fuzja RRF) do 0,93 przy zerze pytań bez trafienia – naprawione zostają wszystkie dziewięć porażek: q007, q021, q022, q023, q029, q032, q033, q037, q039.
- Warianty zapytań w tych pomiarach napisał człowiek, bo każda z tych technik wymaga klucza API; retrieval i metryki są prawdziwe, ale liczby czytaj jako górną granicę jakości modelu, a nie prognozę.
- Pojedyncze przepisanie pytania psuje część pytań, które działały (rewrite 1 gubi q041 i q042), więc oryginalne pytanie zostaje w puli zawsze; przy HyDE bez tego zabezpieczenia wypada z piątki sześć pytań o liczby i nazwy własne. HyDE na modelu z asymetrycznymi prefiksami koduj przy tym jak dokument (`passage: `), nie jak zapytanie – ta jedna zmiana to siedem setnych recall@5.
- Dekompozycja pytań porównawczych wypada gorzej niż zwykłe multi-query (0,68 wobec 0,73 na jedenastu pytaniach), bo dwie listy wyników muszą się zmieścić we wspólnej piątce; ma sens dopiero z osobnym budżetem slotów na podpytanie.
- Trafny filtr rozdziału daje 0,88, błędny daje 0,00 – próg opłacalności self-query to 83 procent trafności ekstraktora, więc filtr wyciągnięty z języka naturalnego stosuj jako drugą listę scalaną RRF-em, a nie jako `must`.
- Routing intencji na trzy klasy (lokalne, globalne, poza domeną) da się zrobić lokalnie: centroidy z czterech przykładów na klasę dają trafność 0,93 na trzydziestu pytaniach, a przy progu marginesu 0,02 nie mylą się ani razu na 24 z 30 pytań. Pytania negatywne z golden setu są przy tym pytaniami **w domenie** – router ma je puścić przez RAG, a odmowa należy do generacji (rozdział 6).
- Przekształcenia kosztują od 0,21 do 0,55 USD na tysiąc zapytań na `claude-haiku-4-5`, czyli ułamek kosztu samej generacji; ograniczeniem jest latencja szeregowego wywołania, a nie rachunek.
- Na pełnym potoku z rozdziałów 2 i 3 przekształcanie zapytań nie poprawia już recall@5 (0,85–0,86 wobec 0,88), bo naprawia te same pytania co lepszy chunking i reranking; podnosi natomiast recall@20 z 0,92 do 0,98–0,99, czyli sufit dla wszystkiego, co dzieje się dalej.

## Co dalej

Rozdział 5 wychodzi poza czysty Markdown: bierze ten sam korpus w formie PDF-a ze składu, z dwułamowym układem, nagłówkami stron i tabelami, i sprawdza, ile z zawartości da się z niego odzyskać oraz jak chunkować tabele i bloki kodu, żeby dało się o nie pytać. Zanim tam przejdziesz, zrób jedno ćwiczenie z własnym kluczem API: podstaw `ClaudeLLM()` w miejsce `ScriptedLLM` w `experiments/04_queries.py` i uruchom ten sam skrypt. Porównanie Twoich liczb z tabelami w tym rozdziale powie Ci dokładnie to, czego ja nie mogłem zmierzyć – o ile model przepisujący pytania jest gorszy od człowieka, który te pytania czytał.

## Źródła

- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/api/messages
- https://qdrant.tech/documentation/concepts/filtering/
- https://qdrant.tech/documentation/concepts/hybrid-queries/
- https://arxiv.org/abs/2212.10496
- https://arxiv.org/abs/2310.06117
- https://huggingface.co/intfloat/multilingual-e5-small
