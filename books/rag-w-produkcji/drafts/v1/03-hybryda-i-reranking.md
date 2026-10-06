# Rozdział 3. Wyszukiwanie hybrydowe i reranking

> **Cel rozdziału:** dołożyć do wyszukiwania gęstego drugi, leksykalny ranking i przestawić wynik cross-enkoderem – oraz zmierzyć, ile każdy z tych kroków daje, ile kosztuje i który z dziewięciu chybionych pytań rozdziału 1 naprawia.
>
> **Kod:** `ragbook/hybrid.py`, `ragbook/rerank.py`, `experiments/03_*.py`. **Pakiety poza fundamentem:** brak – `rank_bm25`, `fastembed` i `sentence-transformers` są już w venv tomu.

Baseline z rozdziału 1 ma recall@5 równy 0,72, MRR@5 0,67 i dziewięć pytań, dla których w czołowej piątce nie ma ani jednego trafnego fragmentu. Jednocześnie recall@20 wynosi 0,96. To nie jest system, który nie umie znaleźć odpowiedzi – to system, który ją znajduje i stawia na jedenastym miejscu. Dwie techniki z tego rozdziału atakują dokładnie ten rozjazd i żadna z nich nie dotyka ani chunkera, ani modelu embeddingowego.

Pierwsza to wyszukiwanie leksykalne: drugi, niezależny ranking liczony na słowach, nie na wektorach, złączony z gęstym metodą RRF. Druga to reranking: model, który zamiast liczyć dwa wektory osobno, dostaje parę (pytanie, fragment) na jednym wejściu i zwraca jedną liczbę. Obie są ortogonalne do chunkingu z rozdziału 2, więc wszystkie pomiary robię tu na baseline'owych chunkach z rozdziału 1 – stałe okno 128/32, 1550 fragmentów – żeby zmierzyć czysty wpływ hybrydy i rerankingu; złożenie jednego z drugim robi rozdział 4.

Każdy skrypt ma na górze zmienną `CHUNKER`; podmień ją na `project_chunks` z rozdziału 2 i całość zmierzy się od nowa. Uruchamiasz je z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/03_bm25.py`.

## Czego nie widzi model gęsty

Model embeddingowy uczy się reprezentacji z danych treningowych. `clear_tool_uses_20250919` w tych danych nie było, `metadata.user_id` też nie, a `query_points` jeżeli już, to jako dwa angielskie słowa bez związku z klientem Qdranta. Wektor takiego ciągu nie leży blisko niczego sensownego – model nie ma z czego wyprowadzić jego znaczenia, więc umieszcza go gdzieś pośrodku przestrzeni, razem z resztą rzeczy, których nie rozumie.

Wyszukiwanie leksykalne nie ma tego problemu, bo w ogóle nie próbuje rozumieć. BM25 liczy dla każdej pary (słowo zapytania, dokument) trzy rzeczy: częstość słowa w dokumencie (z saturacją, żeby dziesiąte wystąpienie nie ważyło tyle co pierwsze), rzadkość słowa w korpusie (IDF) i długość dokumentu względem średniej. Ciąg występujący w korpusie dokładnie raz ma maksymalne IDF i wygrywa natychmiast. Ta sama właściwość jest jego słabością: pytanie sformułowane innymi słowami niż dokument dostaje zero, bo BM25 nie zna synonimów.

Stąd pomysł hybrydy: dwa rankingi o rozłącznych trybach awarii, złożone w jeden. Zanim cokolwiek złożymy, trzeba zobaczyć, ile każdy jest wart osobno – i tu polszczyzna wystawia rachunek.

## BM25 i polska odmiana

Analizator tekstu dla BM25 składa się w tym projekcie z jednej funkcji. Tekst idzie na małe litery i jest cięty na ciągi liter oraz ciągi cyfr; wszystko inne jest separatorem.

```python
import re

_TOKEN = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def make_tokenizer(stem_to: int | None = None):
    """Obcięcie tokenu do `stem_to` znaków jako namiastka lematyzacji."""
    if stem_to is None:
        return tokenize
    return lambda text: [t[:stem_to] for t in _TOKEN.findall(text.lower())]
```

```text
tokenize('clear_tool_uses_20250919, metadata.user_id i query_points w Qdrancie')
  -> ['clear', 'tool', 'uses', '20250919', 'metadata', 'user', 'id', 'i', 'query', 'points', 'w', 'qdrancie']
  stem_to=5 -> ['clear', 'tool', 'uses', '20250', 'metad', 'user', 'id', 'i', 'query', 'point', 'w', 'qdran']
```

Klasa `[^\W\d_]` to „znak słowa, ale nie cyfra i nie podkreślnik”, czyli litera dowolnego alfabetu – polskie znaki diakrytyczne przechodzą, a `snake_case` rozpada się na człony. To decyzja, nie przypadek: identyfikator zostawiony w całości dopasuje się tylko wtedy, gdy użytkownik wklei go dokładnie, a rozbity na człony sprawia, że `user_id` w dokumencie trafi też zapytanie ze słowem „user”.

Teraz problem właściwy. Polszczyzna odmienia wszystko, a BM25 porównuje ciągi znaków: „wektorowych”, „wektorami” i „wektorowy” to dla niego trzy różne słowa. Poprawne rozwiązanie to lematyzacja (`morfeusz2`, `spacy` z `pl_core_news_sm`, stemmer Morfologika) i kosztuje kolejną zależność plus kilkadziesiąt megabajtów. Rozwiązanie tanie do obrzydliwości: obciąć każdy token do N znaków. Końcówka fleksyjna siedzi w polszczyźnie na końcu wyrazu, więc odcięcie ogona skleja formy tego samego lematu za darmo.

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|
| BM25, bez stemowania | 0,62 | 0,80 | 0,62 | 0,58 | 14 |
| BM25, obcięcie do 6 znaków | 0,71 | 0,86 | 0,65 | 0,64 | 10 |
| BM25, obcięcie do 5 znaków | 0,73 | 0,86 | 0,68 | 0,66 | 9 |
| BM25, obcięcie do 4 znaków | 0,76 | 0,90 | 0,65 | 0,65 | 8 |
| gęsty e5-small (baseline rozdz. 1) | 0,72 | 0,96 | 0,67 | 0,64 | 9 |

Skrypt: `experiments/03_bm25.py`.

Brak stemowania kosztuje 0,11 recall@5 i pięć dodatkowych pytań bez trafienia – to najdroższa pojedyncza pomyłka w całym rozdziale, a naprawia ją wycięcie plastra z tokenu. Obcięcie do pięciu znaków zmniejsza słownik korpusu z 11 705 do 5533 typów, czyli scala mniej więcej co drugą formę. Cztery znaki dają najwyższy recall, ale niższy MRR, bo sklejają już za dużo: „model” i „moderacja” to przy czterech znakach jedno „mode”, a przy pięciu dwa różne tokeny. Wybieram pięć i zaznaczam, że różnica 0,03 między czwórką a piątką to półtora pytania, czyli szum w rozumieniu reguły z rozdziału 1.

Sam BM25 z tanim stemowaniem jest na tym korpusie **lepszy od modelu gęstego na recall@5** (0,73 wobec 0,72) i zauważalnie gorszy na recall@20 (0,86 wobec 0,96). To w skrócie cała charakterystyka wyszukiwania leksykalnego: gdy trafia, trafia od razu na górę; gdy nie ma wspólnych słów, nie ma nic i pogłębianie listy tego nie naprawi. Rozbicie po typach mówi, gdzie leży granica.

| Typ | BM25 recall@5 | gęsty recall@5 |
|---|---|---|
| factual | 0,85 | 0,81 |
| procedural | 0,71 | 0,62 |
| comparative | 0,50 | 0,64 |

Skrypt: `experiments/03_bm25.py`.

Pytania faktograficzne i proceduralne wygrywa BM25, porównawcze przegrywa wyraźnie – i to ma mechanizm. Pytanie porównawcze („Qdrant czy pgvector do produkcji średniej skali?”) wymaga dwóch sekcji, a BM25 zwraca pięć fragmentów z jednej, bo to w niej oba terminy stoją obok siebie. Model gęsty rozkłada trafienia szerzej.

Najciekawsza jest lista imienna. BM25 wygrywa z gęstym na siedmiu pytaniach: q021 (`metadata.user_id`), q022 (`clear_tool_uses_20250919`), q023 (limit 25 MB dla transkrypcji), q037, q039, q040 i q044. Przegrywa na ośmiu: q004, q006, q034, q042, q047, q049, q051, q053. Cztery pytania gubią oba: q007, q029, q032 i q033.

Warto zobaczyć, dlaczego te listy wyglądają tak, a nie tak, jak zapowiadał rozdział 1. **q022 rzeczywiście naprawia się leksykalnie**, ale nie dlatego, że zapytanie zawiera `clear_tool_uses_20250919` – nie zawiera, odpowiedzią na to pytanie *jest* ten ciąg. Naprawia się, bo słowa „edycja”, „kontekstu” i „narzędzi” po obcięciu do pięciu znaków dopasowują się do sekcji, w której stoją gęsto obok siebie. **q006 działa odwrotnie, niż brzmi**: pyta o metodę klienta Qdranta, którą wykonuje się zapytanie o najbliższe wektory (`query_points`), i BM25 jest tu *gorszy* od gęstego, bo w pytaniu nie pada ani `query`, ani `points`. To jest ważna korekta intuicji z rozdziału 1: hybryda pomaga na pytania *zadane* słowami z dokumentu, a nie na pytania, których *odpowiedzią* jest identyfikator. Te drugie wymagają przekształcenia zapytania i wracają w rozdziale 4.

Na koniec liczba dla rozdziału 6. Najwyższy wynik BM25 dla pytań negatywnych mieści się w przedziale od 9,79 do 18,03, dla pozytywnych od 11,45 do 37,31 – rozkłady zachodzą na siebie tak samo jak kosinusy e5, więc BM25 też nie daje progu odcięcia.

## Wektory rzadkie w Qdrancie

Powyższe liczyłem `rank_bm25`, biblioteką trzymającą cały indeks w pamięci procesu. To w porządku przy 1550 fragmentach i nie do utrzymania przy milionie. Wersja produkcyjna wkłada oba rankingi do bazy: kolekcja z dwoma **nazwanymi wektorami**, gęstym i rzadkim, i jedno zapytanie, które liczy oba oraz zwraca gotową fuzję.

Wektor rzadki to para list: identyfikatory termów i ich wagi. Produkuje je `fastembed`, model `Qdrant/bm25` – nazwa myli, bo to nie sieć neuronowa, tylko tokenizator z listą stop-słów i stemmerem Snowball zapakowany w interfejs embeddera. Waży 10 MB, co jest jego główną zaletą wobec SPLADE (`prithivida/Splade_PP_en_v1`, 532 MB), który tę samą robotę wykonuje sensowniej, ale za cenę modelu w pamięci i tylko po angielsku (stan na wrzesień 2026).

```python
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

sparse = SparseTextEmbedding(model_name="Qdrant/bm25", language="english", disable_stemmer=True)
dense_vecs = embedder.embed_passages([c.text for c in chunks])
sparse_vecs = list(sparse.embed([c.text for c in chunks]))

client = QdrantClient(":memory:")
client.create_collection(
    collection_name="hybrid",
    vectors_config={"dense": models.VectorParams(size=384, distance=models.Distance.COSINE)},
    sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
)
client.upload_points("hybrid", points=[
    models.PointStruct(id=i, payload={"chapter": c.chapter, "section": c.section},
                       vector={"dense": dense_vecs[i].tolist(),
                               "sparse": models.SparseVector(indices=sv.indices.tolist(),
                                                             values=sv.values.tolist())})
    for i, (c, sv) in enumerate(zip(chunks, sparse_vecs))
])
```

Jedna linijka w tej konfiguracji jest nieoczywista: `modifier=models.Modifier.IDF`. Model zapisuje w wektorze tylko częstości termów w dokumencie; człon IDF zależy od całego korpusu, więc nie da się go policzyć przy zapisie pojedynczego punktu. Qdrant dolicza go przy zapytaniu, ale tylko wtedy, gdy kolekcja o to prosi tym modyfikatorem. Bez niego dostaniesz iloczyn skalarny surowych częstości, czyli ranking, w którym wygrywają dokumenty pełne słowa „i”.

Drugi haczyk jest językowy. Argument `language` wybiera listę stop-słów i stemmer Snowball, a `fastembed` obsługuje osiemnaście języków: arabski, duński, niderlandzki, angielski, fiński, francuski, niemiecki, grecki, węgierski, włoski, norweski, portugalski, rumuński, rosyjski, hiszpański, szwedzki, tamilski i turecki. Polskiego wśród nich nie ma – `language="polish"` rzuca `ValueError`. Zostaje `disable_stemmer=True`, czyli dokładnie ten wariant, który w tabeli wyżej wypadł najgorzej.

Zapytanie hybrydowe składa się z dwóch podzapytań (`prefetch`) i reguły fuzji na górze:

```python
qv = embedder.embed_queries([question])[0]
qs = next(iter(sparse.query_embed(question)))

hits = client.query_points(
    collection_name="hybrid",
    prefetch=[
        models.Prefetch(query=qv.tolist(), using="dense", limit=50),
        models.Prefetch(query=models.SparseVector(indices=qs.indices.tolist(),
                                                  values=qs.values.tolist()),
                        using="sparse", limit=50),
    ],
    query=models.RrfQuery(rrf=models.Rrf(k=60)),
    limit=5,
).points
```

`models.RrfQuery(rrf=models.Rrf(k=60))` to nowsza forma, która pozwala ustawić stałą `k` (domyślnie 2) i wagi ramion przez `Rrf(weights=[3.0, 1.0])`. Starsza `models.FusionQuery(fusion=models.Fusion.RRF)` dalej działa i używa wartości domyślnych; `models.Fusion.DBSF` to alternatywna fuzja po znormalizowanych wynikach (stan na wrzesień 2026, qdrant-client 1.19.1).

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|
| Qdrant, wektor gęsty (named vector) | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| Qdrant, wektor rzadki (`Qdrant/bm25` + IDF) | 0,60 | 0,83 | 0,53 | 0,51 | 15 |
| Qdrant, RRF po stronie serwera | 0,80 | 0,92 | 0,71 | 0,70 | 6 |
| własny `rrf_fuse` na tych samych ramionach | 0,80 | 0,92 | 0,71 | 0,70 | 6 |

Skrypt: `experiments/03_fusion.py`.

Dwie rzeczy do odczytania. Po pierwsze, **własna implementacja RRF zgadza się z serwerową**: na 56 pytaniach i dwudziestu pozycjach identyfikatory pokrywają się w 1118 przypadkach na 1120. Wartości różnią się o stałą, bo Qdrant numeruje pozycje od zera, a ja od jedynki – pierwszy wynik to u niego 0,03182, u mnie 0,03132. Kolejność jest ta sama, a to jedyne, co w fuzji rangowej ma znaczenie.

Po drugie, ramię rzadkie z `Qdrant/bm25` bez stemmera daje recall@5 równy 0,60 wobec 0,73 dla `rank_bm25` z obcięciem do pięciu znaków, i cała hybryda traci przez to 0,04. Architektura „wszystko w bazie” jest właściwa i tak wygląda produkcja, ale dla języka spoza listy osiemnastu musisz podstawić własny analizator – policzyć wektory rzadkie samodzielnie i wysłać je jako `SparseVector`. W tym rozdziale zostaję przy `rank_bm25`: korpus ma 1550 fragmentów, a 0,13 recall na ramieniu leksykalnym to za wysoka cena za wygodę.

## Fuzja: RRF czy suma ważona

Mając dwa rankingi, trzeba je złożyć. Są dwie rodziny metod i wybór między nimi nie jest kwestią gustu.

**Suma ważona wyników** normalizuje wyniki każdego rankingu do [0, 1] i sumuje je z wagami. Jest naturalna, ale wymaga, żeby wyniki dało się porównać – a kosinus e5 w przedziale 0,84–0,93 i wynik BM25 w przedziale 0–37 są nieporównywalne. Normalizacja min-max liczona na zwróconej liście dokłada drugi problem: zależy od tego, ilu kandydatów pobrałeś, więc ten sam dokument dostaje inny wynik przy puli 20 i 50.

**RRF (reciprocal rank fusion)** ignoruje wyniki i patrzy tylko na pozycje: każdy dokument zbiera sumę `1 / (k + pozycja)`. Stała `k` steruje tym, jak bardzo czołówka góruje nad resztą – przy `k` równym 1 pierwsza pozycja jest warta dwa razy tyle co druga, przy `k` równym 60 różnica to niecałe dwa procent.

```python
def rrf_fuse(rankings, k=60, weights=None):
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    fused, seen = {}, {}
    for ranking, w in zip(rankings, weights):
        for rank, chunk in enumerate(ranking, start=1):
            fused[chunk.id] = fused.get(chunk.id, 0.0) + w / (k + rank)
            seen.setdefault(chunk.id, chunk)
    return [seen[i] for i in sorted(fused, key=lambda i: -fused[i])]
```

| Fuzja | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|
| RRF, k=1 | 0,82 | 0,92 | 0,78 | 0,74 | 5 |
| RRF, k=10 | 0,86 | 0,92 | 0,79 | 0,76 | 3 |
| RRF, k=20 | 0,85 | 0,92 | 0,77 | 0,74 | 3 |
| RRF, k=60 | 0,84 | 0,93 | 0,77 | 0,74 | 3 |
| RRF, k=100 | 0,84 | 0,93 | 0,77 | 0,74 | 3 |
| RRF, k=200 | 0,84 | 0,93 | 0,77 | 0,74 | 3 |
| suma ważona, waga gęstego 0,2 | 0,78 | 0,87 | 0,70 | 0,69 | 7 |
| suma ważona, waga gęstego 0,5 | 0,86 | 0,90 | 0,78 | 0,75 | 3 |
| suma ważona, waga gęstego 0,8 | 0,78 | 0,95 | 0,73 | 0,70 | 6 |

Skrypt: `experiments/03_fusion.py`.

Najlepszy wynik obu rodzin jest ten sam: 0,86. Różni je kształt okolicy optimum. RRF od `k` równego 10 w górę jest płaski – między dziesiątką a dwiema setkami mieści się 0,02 recall i zero pytań różnicy. Suma ważona ma wyraźne maksimum przy wadze 0,5 i spada o 0,08, gdy przesuniesz wagę o 0,3 w którąkolwiek stronę. To cały argument za RRF jako wyborem domyślnym: **nie musisz go stroić, a wynik i tak wychodzi w granicach najlepszej wagi**, podczas gdy waga w sumie ważonej wymaga zestawu ewaluacyjnego, którego na starcie projektu nie masz, i zmienia się przy każdej podmianie chunkera albo modelu.

Trzeci parametr – ile kandydatów pobrać z każdego ramienia przed fuzją – okazał się prawie obojętny: przy puli 20, 50, 100 i 200 recall@5 mieści się między 0,83 a 0,84, a rośnie tylko recall@20 (z 0,92 na 0,97), bo głębsza pula wpuszcza dokumenty zgłoszone przez jedno ramię na dalekiej pozycji. Zostaję przy puli 50, bo nad fuzją stanie zaraz reranker, który i tak przestawi pierwszych dwadzieścia (`experiments/03_fusion.py` mierzy wszystkie cztery).

Zostaje najważniejsza tabela tej sekcji, czyli co się stało z pytaniami.

| Typ | gęsty recall@5 | hybryda recall@5 | gęsty MRR@5 | hybryda MRR@5 |
|---|---|---|---|---|
| factual | 0,81 | 0,92 | 0,66 | 0,75 |
| procedural | 0,62 | 0,83 | 0,60 | 0,73 |
| comparative | 0,64 | 0,64 | 0,75 | 0,86 |

Skrypt: `experiments/03_fusion.py`.

Hybryda naprawia osiem pytań (q021, q022, q023, q032, q037, q039, q040, q049) i psuje dwa (q034, q051), czyli netto sześć – zmiana, której nie da się wytłumaczyć losem. Zysk jest jednak nierówny: faktograficzne rosną o 0,11, proceduralne o 0,21, a **porównawcze o dokładnie nic**. Rośnie tylko ich MRR (z 0,75 na 0,86), czyli pierwsza z dwóch potrzebnych sekcji wchodzi wyżej, a druga dalej nie wchodzi wcale. Ten jeden wiersz tabeli jest powodem, dla którego ten rozdział ma jeszcze sekcję o dywersyfikacji.

Wśród pytań naprawionych jest q039, jedyne w całym zestawie, które w rozdziale 1 nie miało trafienia nawet w top-20. Odpowiedź – walidacja SQL-a przez `sqlglot` – siedzi w dużym bloku kodu, a blok kodu to dla BM25 zbiór bardzo rzadkich termów o maksymalnym IDF. Rozdział 5 wraca do kodu w dokumentacji szerzej; tutaj wystarczy odnotować, że hybryda jest pierwszą rzeczą, którą warto włączyć w korpusie z kodem.

## Reranking cross-enkoderem

Model embeddingowy jest bi-enkoderem: liczy wektor pytania i wektor fragmentu osobno i całą interakcję między nimi sprowadza do jednego iloczynu skalarnego. Cross-enkoder dostaje parę na jednym wejściu, przepuszcza ją przez transformer z pełną uwagą między tokenami pytania i dokumentu, i zwraca jedną liczbę. Różnica jakości jest duża, różnica kosztu też: wektory fragmentów liczysz raz przy indeksowaniu, a cross-enkoder musi wykonać tyle przebiegów przez sieć, ilu ma kandydatów, przy każdym zapytaniu. Stąd standardowy układ dwustopniowy: pierwszy stopień wyciąga dwadzieścia–pięćdziesiąt kandydatów, drugi przestawia w nich kolejność i oddaje pięć.

```python
from sentence_transformers import CrossEncoder

from ragbook.corpus import Chunk

MMARCO = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


class CrossEncoderReranker:
    def __init__(self, model_name: str = MMARCO, max_length: int = 512, batch_size: int = 16,
                 device: str | None = None):
        self.model = CrossEncoder(model_name, max_length=max_length, device=device)
        self.batch_size = batch_size

    def rerank(self, question: str, chunks: list[Chunk], top_k: int = 5) -> list[Chunk]:
        pairs = [(question, c.text) for c in chunks]
        scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        out = []
        for i in sorted(range(len(chunks)), key=lambda j: -scores[j])[:top_k]:
            c = chunks[i]
            out.append(Chunk(c.id, c.chapter, c.section, c.text,
                             {**c.meta, "stage1": c.meta.get("score"), "score": float(scores[i])}))
        return out
```

Zwróć uwagę na `meta["stage1"]`: wynik pierwszego stopnia nie jest kasowany, tylko przesuwany – przyda się w rozdziale 8 przy śledzeniu zapytań. Testowane modele to `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (dwanaście warstw, wymiar ukryty 384, destylowany z XLM-R-large, trenowany na mMARCO – maszynowym tłumaczeniu MS MARCO na czternaście języków; około 470 MB na dysku) i `BAAI/bge-reranker-v2-m3` (0,6 miliarda parametrów, zbudowany na `bge-m3`, wielojęzyczny, 2,2 GB). Oba zwracają logity, nie prawdopodobieństwa: wartości bywają ujemne i mają sens wyłącznie porównawczy w obrębie jednego zapytania (stan na wrzesień 2026).

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |
|---|---|---|---|---|---|
| gęsty, bez rerankera | 0,72 | 0,96 | 0,67 | 0,64 | 9 |
| hybryda, bez rerankera | 0,84 | 0,93 | 0,77 | 0,74 | 3 |
| gęsty → mMiniLM, 20 kandydatów | 0,85 | 0,96 | 0,81 | 0,78 | 4 |
| gęsty → mMiniLM, 50 kandydatów | 0,85 | 0,93 | 0,80 | 0,77 | 4 |
| hybryda → mMiniLM, 20 kandydatów | 0,86 | 0,93 | 0,81 | 0,78 | 3 |
| hybryda → mMiniLM, 50 kandydatów | 0,85 | 0,95 | 0,79 | 0,77 | 4 |
| hybryda → bge-reranker-v2-m3, 20 kandydatów | 0,88 | 0,93 | 0,77 | 0,77 | 3 |
| hybryda → bge-reranker-v2-m3, 50 kandydatów | 0,91 | 0,98 | 0,78 | 0,79 | 2 |

Skrypt: `experiments/03_rerank.py` (wariant bge: `experiments/03_rerank.py bge`).

Pierwszy wniosek jest o puli kandydatów. Dla mMiniLM przejście z dwudziestu na pięćdziesiąt **nie poprawia żadnej metryki** i podwaja koszt: wszystko, co ten model potrafił znaleźć, leżało już w dwudziestce. Dla bge jest odwrotnie – pięćdziesiątka podnosi recall@5 z 0,88 na 0,91 i zbija liczbę pytań bez trafienia do dwóch, czyli mocniejszy reranker naprawdę korzysta z głębszej listy. To jest reguła warta zapamiętania: szerokość pierwszego stopnia strój pod konkretny drugi stopień, a nie „na zapas”.

Drugi wniosek jest ciekawszy. Reranking na samym wyszukiwaniu gęstym daje recall@5 równy 0,85, czyli prawie tyle, co hybryda z rerankingiem (0,86), i więcej niż hybryda bez rerankera (0,84). Skoro recall@20 baseline'u wynosił 0,96, cross-enkoder miał z czego wybierać i wybrał dobrze – co potwierdza diagnozę z rozdziału 1, że problemem baseline'u było uszeregowanie, a nie wyszukiwanie. Hybryda i reranking robią więc w dużej mierze **tę samą** robotę i ich efekty się nie sumują: osobno dają +0,12 i +0,13, razem +0,14.

To argument produktowy, nie akademicki. Jeżeli masz budżet latencji na jeden model więcej, sam reranking na indeksie gęstym da prawie cały zysk bez drugiego indeksu do utrzymania; jeżeli budżetu nie masz, hybryda kosztuje kilkanaście milisekund i daje prawie to samo. Oba naraz mają sens, gdy zależy Ci na ostatnich setnych i na pytaniach, przy których model gęsty nie zgłasza niczego sensownego nawet w dwudziestce.

| Typ | recall@5 mMiniLM (20) | MRR@5 mMiniLM (20) | recall@5 bge (50) | MRR@5 bge (50) |
|---|---|---|---|---|
| factual | 0,92 | 0,79 | 0,96 | 0,81 |
| procedural | 0,88 | 0,72 | 0,88 | 0,64 |
| comparative | 0,68 | 0,95 | 0,82 | 0,84 |

Skrypt: `experiments/03_rerank.py`.

Pytania porównawcze mają przy mMiniLM MRR@5 równy 0,95 (najwyższy w całej tabeli) przy recall 0,68. Ta para liczb jest wymowna: cross-enkoder jest bardzo dobry w znajdowaniu *najlepszego* fragmentu i zupełnie obojętny na to, czy pozostałe cztery wnoszą cokolwiek nowego. Ocenia każdą parę osobno, więc nie ma jak zauważyć, że piąty kandydat jest kopią pierwszego. Większy bge radzi sobie z tym lepiej (0,82), ale nie dlatego, że dywersyfikuje – po prostu trafniej ocenia fragmenty z drugiej sekcji.

### Ile to kosztuje czasu

Jakość nie zależy od tego, na czym liczysz, latencja zależy całkowicie. Poniżej ten sam pomiar na dwudziestu pytaniach, wykonany dwa razy: raz na CPU (Intel Core i5-9300H, osiem wątków), raz na GPU (NVIDIA GTX 1650, 4 GB VRAM). Oba przebiegi mierzą `time.perf_counter` wokół samego rerankingu, z rozgrzewką przed pomiarem.

| Etap | CPU p50 / p95 [ms] | GPU p50 / p95 [ms] |
|---|---|---|
| pierwszy stopień: gęsty, top-20 | 6 / 12 | 3 / 3 |
| pierwszy stopień: BM25, top-20 | 5 / 9 | 4 / 6 |
| pierwszy stopień: hybryda, top-20 | 18 / 30 | 8 / 10 |
| mMiniLM, 20 kandydatów | 1258 / 1560 | 121 / 136 |
| mMiniLM, 50 kandydatów | 3101 / 3786 | 289 / 309 |
| bge-reranker-v2-m3, 20 kandydatów | 10 656 / 15 926 | 2560 / 2769 |
| bge-reranker-v2-m3, 50 kandydatów | 21 476 / 33 731 | 3171 / 6554 |

Skrypt: `experiments/03_latency.py cpu` oraz `experiments/03_latency.py cuda`.

Trzy rzeczy do odczytania. **Pierwszy stopień jest darmowy**: cała hybryda – wektor zapytania, przeszukanie Qdranta, BM25 na 1550 dokumentach i fuzja – mieści się w ośmiu milisekundach na GPU i osiemnastu na CPU, więc dokładanie indeksu leksykalnego nie jest decyzją o latencji, tylko o pamięci i kodzie do utrzymania. **Drugi stopień jest całym kosztem**: mMiniLM na dwudziestu kandydatach to na CPU 1,3 sekundy, sto pięćdziesiąt razy więcej niż wyszukiwanie. **GPU zmienia decyzję produktową**: te same dwadzieścia par to 121 milisekund, czyli budżet, w którym reranking mieści się w interaktywnej odpowiedzi. Na CPU mMiniLM na dwudziestce jest granicą tego, co da się zrobić synchronicznie; bge nie mieści się nigdzie.

Koszt cross-enkodera jest liniowy w liczbie par i mniej więcej stały na parę: dla mMiniLM 62–63 ms na CPU i 6 ms na GPU. Tę liczbę warto zapamiętać zamiast całych tabel, bo pozwala policzyć budżet dla dowolnego `k` – i pokazuje, po co w ogóle jest układ dwustopniowy. Gdyby cross-enkoder oceniał wszystkie 1550 fragmentów, jedno zapytanie kosztowałoby na tym GPU dziewięć sekund.

## Reranking LLM-em

Cross-enkoder ocenia każdą parę osobno i to jest jego ograniczenie. Model językowy można poprosić o coś, czego cross-enkoder z definicji nie potrafi: o uszeregowanie **całej listy naraz**, z informacją o tym, co jest w pozostałych fragmentach. To jest podejście listwise i w publikacjach o rerankingu wypada zwykle najlepiej z trzech (pointwise, pairwise, listwise) – za cenę jednego wywołania modelu na zapytanie.

Kształt jest prosty: ponumerowane fragmenty w prompcie, structured outputs na wyjściu, permutacja z powrotem.

```python
import os
from anthropic import Anthropic
from pydantic import BaseModel


class Ranking(BaseModel):
    order: list[int]


client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
response = client.messages.parse(
    model="claude-haiku-4-5",
    max_tokens=1024,
    system=LISTWISE_SYSTEM,
    messages=[{"role": "user", "content": build_listwise_prompt(question, candidates)}],
    output_format=Ranking,
)
order = [i for i in response.parsed_output.order if 0 <= i < len(candidates)]
order += [i for i in range(len(candidates)) if i not in set(order)]
ranked = [candidates[i] for i in order[:5]]
```

Dwie rzeczy są tu obowiązkowe i obie wynikają z tego, że model nie jest funkcją. **Structured outputs** (`messages.parse` z `output_format`, tom 1, rozdział 3) gwarantują listę liczb całkowitych zamiast prozy o tym, które fragmenty są ciekawe – ale nie gwarantują, że będzie to permutacja, bo model potrafi pominąć fragment albo wymienić ten sam dwa razy; kod dokleja więc brakujące indeksy na koniec. Prompt systemowy mówi wprost „nie odpowiadaj na pytanie”, bo model poproszony o uszeregowanie chętnie napisze przy okazji odpowiedź, za którą zapłacisz w tokenach wyjściowych. Wybrałem `claude-haiku-4-5`, bo reranking jest zadaniem klasyfikacyjnym, a nie rozumowaniem: przy stawkach 1 USD za milion tokenów wejściowych i 5 USD za milion wyjściowych to najtańszy rozsądny wybór (stan na wrzesień 2026).

```text
=== Cost of listwise reranking, claude-haiku-4-5, 20 candidates, 600 chars each ===
per query: 3184 input tokens (e5 tokenizer), 88 output tokens
per query: 0.00362 USD, per 1000 queries: 3.62 USD
whole golden set (49 queries): 0.1776 USD
```

Skrypt: `experiments/03_llm_rerank.py`.

Liczby tokenów pochodzą z tokenizera e5, bo tylko taki mam lokalnie; prawdziwą wartość policzysz endpointem `count_tokens` z tym samym kształtem żądania (tom 1, rozdział 2) i wyjdzie niższa, bo tokenizer Claude'a radzi sobie z polszczyzną lepiej. Rząd wielkości jest właściwy i to on decyduje: **3,6 dolara za tysiąc zapytań**, przy latencji rzędu sekundy i niezerowej szansie, że model zwróci coś, czego nie przewidziałeś. Cross-enkoder mMiniLM na tej samej liście kosztuje zero dolarów i jest deterministyczny.

Kiedy więc listwise ma sens? Gdy zapytań jest mało, a stawka za jedno wysoka – wewnętrzna wyszukiwarka dla dziesięciu analityków, research prawniczy, wsparcie techniczne, gdzie jedna zła odpowiedź kosztuje więcej niż tysiąc wywołań modelu. Gdy nie masz dobrego cross-enkodera dla swojego języka albo dziedziny (rerankery z MS MARCO są z dziedziny „pytania z wyszukiwarki”, a Twoja może wyglądać inaczej). I gdy potrzebujesz od rerankera czegoś więcej niż kolejności – uzasadnienia, etykiety „ten fragment jest o czymś innym”, sygnału do odmowy. Przy dużym i tanim ruchu nie ma sensu: płacisz przy każdym zapytaniu, a zysk nad cross-enkoderem jest niepewny.

Tego eksperymentu nie uruchomiłem – w tej książce nie ma klucza API, więc kod jest poprawny wobec dokumentacji, ale liczb z jego działania w tabeli zbiorczej nie znajdziesz. `experiments/03_llm_rerank.py` uruchomi go u Ciebie po ustawieniu `ANTHROPIC_API_KEY`, za mniej więcej osiemnaście centów.

## Próg odcięcia dla pytań bez odpowiedzi

Rozdział 1 zostawił otwartą sprawę: kosinus e5 nie pozwala odróżnić pytania, na które w korpusie jest odpowiedź, od pytania, na które jej nie ma – wszystkie siedem negatywów dostawało na pierwszym miejscu wynik wyższy niż najsłabsze prawdziwe trafienie. Powód jest strukturalny: kosinus mierzy podobieństwo dwóch wektorów, a nie „czy tu jest odpowiedź”, więc model gęsty zawsze znajdzie **najbliższy** fragment, a najbliższy zawsze jakiś jest.

Cross-enkoder trenuje się na czymś innym – na parach (zapytanie, trafny passus) kontra (zapytanie, nietrafny passus) – więc jego wyjście jest w zamierzeniu oceną trafności, a nie podobieństwa. To hipoteza, którą można sprawdzić: bierzemy najwyższy wynik cross-enkodera w dwudziestce kandydatów i patrzymy na rozkład.

| Grupa | Pytań | min | mediana | max |
|---|---|---|---|---|
| pozytywne | 49 | -1,79 | +3,47 | +9,87 |
| negatywne | 7 | -4,38 | -2,08 | +5,20 |

Skrypt: `experiments/03_negatives.py`.

Tym razem rozkłady **nie** pokrywają się całkowicie i to jest istotna różnica wobec rozdziału 1. Mediana pytań negatywnych leży pięć i pół jednostki poniżej mediany pozytywnych, a cztery z siedmiu negatywów mają wynik niższy niż najsłabszy pozytyw.

```text
threshold -2.0: catches 4/7 negatives, loses 0/49 positives
threshold  0.0: catches 5/7 negatives, loses 7/49 positives
to reject all 7 negatives the threshold must exceed +5.20,
  which also rejects 29 of 49 positives
```

Skrypt: `experiments/03_negatives.py`.

Praktyczny wniosek jest taki: **próg na poziomie -2 wyłapuje cztery z siedmiu pytań bez odpowiedzi i nie kosztuje ani jednego pytania z odpowiedzią.** To nie jest odmowa, tylko sygnał – tani, deterministyczny i policzony przy okazji rerankingu, który i tak wykonujesz. Odcięcie wszystkich siedmiu jest nieosiągalne: żeby złapać ostatnie trzy, próg musiałby przekroczyć +5,20 i zabrałby dwadzieścia dziewięć poprawnych odpowiedzi.

Które negatywy przechodzą? Najwyżej punktowane jest „Ile tokenów na sekundę generuje `claude-opus-5` przy typowym obciążeniu?” (+5,20) i zaraz po nim „Jak ustawić parametr `ef_search` w Elasticsearchu przy indeksie kNN?” (+2,78) – dokładnie te dwa, które rozdział 1 opisał jako wzorcowe pytania negatywne, bo brzmią jak pytania z dziedziny i mają w korpusie bardzo bliskich sąsiadów. Cross-enkoder nie ma jak odróżnić „ten fragment jest o `ef_search`” od „ten fragment jest o `ef` w Qdrancie”. Najniżej wypadają pytania o ceny GPU i transfer w S3 (-4,38 i -3,46), które z korpusem nie mają wspólnego nic poza tym, że dotyczą pieniędzy.

Dla rozdziału 6 zostaje więc konkretna rekomendacja: próg `score` cross-enkodera na poziomie -2 jest tanim pierwszym filtrem, który usuwa ponad połowę pytań spoza dziedziny za darmo, ale odmowa dla pozostałych musi pozostać decyzją modelu w kroku generacji.

## Dywersyfikacja: pięć fragmentów, ile sekcji

Zostały pytania porównawcze, jedyne, których ani hybryda, ani reranking nie ruszyły. Mechanizm widać było od pierwszego wyniku w rozdziale 1: wyszukiwanie po podobieństwie skupia się. Jeżeli sekcja jest trafna, jej dziesięć sąsiednich fragmentów też jest podobnych do pytania i zajmują całą piątkę; pytanie z dwiema trafnymi sekcjami przegrywa, bo druga nie ma jak się wcisnąć.

Są dwa lekarstwa. **Twarde**: limit chunków z jednej sekcji w zwracanej liście. **Miękkie**: MMR (maximal marginal relevance), które przy wyborze kolejnej pozycji odejmuje od trafności karę za podobieństwo do już wybranych, `λ · trafność − (1 − λ) · max podobieństwo do wybranych`.

```python
def cap_per_section(chunks, k, max_per_section=1):
    counts, kept, spare = {}, [], []
    for c in chunks:
        if counts.get(c.key, 0) < max_per_section:
            counts[c.key] = counts.get(c.key, 0) + 1
            kept.append(c)
            if len(kept) == k:
                return kept
        else:
            spare.append(c)
    return (kept + spare)[:k]
```

Nadmiarowe fragmenty nie wypadają, tylko trafiają na koniec listy – jeżeli po limicie zostaje mniej niż `k` pozycji, wracają. Dzięki temu limit nigdy nie zmniejsza liczby zwróconych fragmentów, a przy `k` większym niż liczba trafnych sekcji degraduje się do zwykłego rankingu.

| Wariant | recall@5 | recall@5 comparative | MRR@5 | nDCG@5 | Sekcji w top-5 |
|---|---|---|---|---|---|
| hybryda + rerank (bez dywersyfikacji) | 0,86 | 0,68 | 0,81 | 0,78 | 3,7 |
| limit 3 chunków na sekcję | 0,86 | 0,68 | 0,81 | 0,78 | 3,8 |
| limit 2 chunków na sekcję | 0,86 | 0,68 | 0,81 | 0,78 | 4,1 |
| limit 1 chunka na sekcję | 0,88 | 0,77 | 0,81 | 0,79 | 5,0 |
| MMR na kosinusie, λ=0,7 (najlepsze z czterech) | 0,76 | 0,73 | 0,68 | 0,66 | 4,1 |
| MMR na kosinusie, λ=0,5 | 0,72 | 0,64 | 0,66 | 0,63 | 4,3 |
| MMR na wyniku cross-enkodera, λ=0,7, 0,8 i 0,9 | 0,86 | 0,68 | 0,81 | 0,78 | 3,7 |

Skrypt: `experiments/03_diversify.py`.

Wygrywa wariant najbardziej prymitywny: **jeden chunk na sekcję**. Recall porównawczych rośnie z 0,68 na 0,77, ogólny z 0,86 na 0,88, MRR nie spada, a w top-5 jest pięć różnych sekcji zamiast 3,7. Na piętnastu pytaniach wielosekcyjnych obie potrzebne sekcje mieszczą się w piątce dla dziewięciu, a nie dla siedmiu. Limity 2 i 3 nie dają nic, bo przy tym rozkładzie rzadko która sekcja wchodzi do piątki więcej niż dwa razy.

MMR jest tu wynikiem negatywnym i to w dwóch odmianach. W wersji podręcznikowej, gdzie trafnością jest kosinus do zapytania, MMR **kasuje cały zysk rerankingu** – 0,76 przy najlepszym λ, o 0,10 gorzej niż sam reranking – bo przestawia listę z powrotem na podstawie tego samego sygnału, który cross-enkoder przed chwilą poprawił. W wersji poprawionej, z trafnością wziętą ze znormalizowanego wyniku cross-enkodera, MMR nie zmienia **nic**: kary za podobieństwo są prawie identyczne dla wszystkich kandydatów, bo wszystkie leżą w wąskim przedziale kosinusów rodziny E5 (rozdział 1). Model, który nie daje rozpiętości wyników, nie daje też użytecznej miary redundancji; limit na sekcję działa, bo korzysta z metadanych, a nie z geometrii.

Jest jednak koszt i trzeba go wypowiedzieć wprost: precision@5 liczona po fragmentach spada z 0,43 na 0,22. To nie pogorszenie jakości, tylko artefakt definicji – gdy z każdej sekcji bierzesz jeden fragment, pytanie z jedną trafną sekcją ma w piątce najwyżej jeden trafny fragment, więc górna granica tej metryki wynosi 0,2. Prompt dostaje mniej powtórzeń, a więcej różnych miejsc korpusu i o to właśnie chodziło. Gdyby zależało Ci na dosłownym cytacie z długiej sekcji, limit 1 byłby złym pomysłem. Rozdział 2 pokazuje trzecie wyjście: parent-child, gdzie do promptu trafia całość sekcji rodzica, a limit staje się bezprzedmiotowy.

## Co zostaje w projekcie

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | precision@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| stałe okno 128/32 + e5-small (rozdz. 1) | 0,72 | 0,96 | 0,67 | 0,64 | 0,38 | 9 |
| sam BM25 (obcięcie do 5 znaków) | 0,73 | 0,86 | 0,68 | 0,66 | 0,34 | 9 |
| hybryda RRF (k=60) | 0,84 | 0,93 | 0,77 | 0,74 | 0,43 | 3 |
| hybryda + rerank top-20 + limit 1 na sekcję | 0,88 | 0,93 | 0,81 | 0,79 | 0,22 | 3 |

Skrypt: `experiments/03_summary.py`.

| Typ | rozdz. 1 recall@5 | po rozdz. 3 recall@5 | rozdz. 1 MRR@5 | po rozdz. 3 MRR@5 |
|---|---|---|---|---|
| factual | 0,81 | 0,92 | 0,66 | 0,79 |
| procedural | 0,62 | 0,88 | 0,60 | 0,72 |
| comparative | 0,64 | 0,77 | 0,75 | 0,95 |

Skrypt: `experiments/03_summary.py`.

Recall@5 rośnie z 0,72 na 0,88, MRR@5 z 0,67 na 0,81, a liczba pytań bez trafienia spada z dziewięciu na trzy. Licząc regułą z rozdziału 1: wynik zmieniło dwanaście pytań na czterdzieści dziewięć, jedenaście na plus (q021, q022, q023, q032, q037, q039, q040, q044, q046, q049, q052) i jedno na minus. To nie jest różnica, którą da się wytłumaczyć losem.

Z dziewięciu porażek rozdziału 1 naprawionych jest sześć: **q021** (`metadata.user_id`), **q022** (`clear_tool_uses_20250919`), **q023** (limit 25 MB), **q032** (podmiana modelu embeddingowego), **q037** (bramka jakości) i **q039** (walidacja SQL-a, jedyne pytanie bez trafienia nawet w top-20). Zostają trzy i wszystkie trzy to ta sama kategoria – parafraza bez wspólnych słów. **q007** („Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?”) nie ma wspólnego ani jednego terminu z sekcją „Trening a inferencja”, a ani hybryda, ani cross-enkoder nie wymyślą słowa, którego w pytaniu nie ma. **q029** potrzebuje sekcji wstępnej rozdziału 11, gdzie stoi „lethal trifecta”. **q033** pyta o liczenie tokenów historii rozmowy, a odpowiedzią jest `count_tokens`. To dokładnie ta klasa problemów, którą rozwiązuje przekształcanie zapytania – temat rozdziału 4.

Jedna regresja: **q051** („Qdrant czy pgvector do produkcji średniej skali?”) miało w baseline'ie połowę trafnych sekcji, a teraz nie ma żadnej. Ramię leksykalne wciąga do puli fragmenty, w których „Qdrant” i „pgvector” stoją obok siebie w tabeli porównawczej, i wypycha sekcję „Wybór bazy w praktyce”, mówiącą o tym samym własnymi słowami. To cena hybrydy, zapłacona raz na czterdzieści dziewięć pytań.

Konfiguracja, która zostaje w projekcie, żyje jako `ragbook.hybrid.project_retriever` – i to jej używa tabela powyżej, nie kopia potoku napisana na potrzeby pomiaru.

```python
from ragbook.hybrid import project_retriever

retrieve = project_retriever(
    chunks,                      # z rozdziału 2; tutaj stałe okno 128/32
    mode="hybrid",               # "dense" | "bm25" | "hybrid"
    rerank=True,                 # cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
    pool=20,                     # ilu kandydatów widzi reranker
    rrf_k=60,                    # stała RRF
    stem_to=5,                   # obcięcie tokenów w analizatorze BM25
    max_per_section=1,           # dywersyfikacja zwracanej piątki
)

hits = retrieve("Jak podmienić model liczący wektory w działającym systemie?", 5)
for hit in hits:
    print(f"{hit.meta['score']:+.2f}  rozdz. {hit.chapter}  {hit.section!r}")
retrieve.close()                 # zwalnia cross-enkoder
```

Sygnatura jest ta sama, której oczekuje `ragbook.evaluate.evaluate`: `(pytanie, k) -> list[Chunk]`. Rozdział 4 podstawia więc ten obiekt pod swoje przekształcenia zapytania bez przejściówki, a rozdział 8 owija go w cache i trace.

Trzy decyzje, które warto umieć obronić. **Reranker `mmarco-mMiniLMv2`, nie `bge-reranker-v2-m3`**, mimo że bge jest lepszy o 0,03 na dwudziestce i o 0,06 na pięćdziesiątce – bo kosztuje dwadzieścia razy więcej czasu i pięć razy więcej pamięci. Masz GPU z zapasem VRAM albo płacisz za jakość więcej niż za sekundy? Wybierz odwrotnie, `03_rerank.py bge` odtworzy tamten pomiar. **Pula 20, nie 50** – pięćdziesiątka nie poprawiła ani jednej metryki mMiniLM i podwaja latencję. **Limit 1 na sekcję**, mimo że psuje precision@5 liczoną po fragmentach.

I jedna rzecz, której ten rozdział nie robi: nie dotyka chunkingu. Wszystkie liczby są na oknie 128/32 z rozdziału 1, więc pokazują czysty wpływ hybrydy i rerankingu. Techniki z rozdziału 2 działają na innym poziomie potoku i ich efekty powinny się z tymi sumować – ale „powinny” to nie pomiar, dlatego złożenie jednego z drugim robi rozdział 4.

## Podsumowanie

- Tanie stemowanie przez obcięcie tokenu do pięciu znaków podnosi recall@5 samego BM25 z 0,62 na 0,73; brak jakiejkolwiek normalizacji fleksji jest w polskim korpusie najdroższym pojedynczym błędem w tym rozdziale.
- Sam BM25 bije model gęsty na pytaniach faktograficznych (0,85 wobec 0,81) i proceduralnych (0,71 wobec 0,62), a przegrywa na porównawczych (0,50 wobec 0,64); rankingi mają rozłączne tryby awarii i dlatego opłaca się je łączyć.
- Hybryda leksykalno-gęsta złączona RRF podnosi recall@5 z 0,72 na 0,84 i zmniejsza liczbę pytań bez trafienia z dziewięciu na trzy, kosztem pięciu milisekund na zapytanie.
- RRF jest domyślnym wyborem nie dlatego, że daje najlepszy wynik (suma ważona przy wadze 0,5 daje taki sam), tylko dlatego, że jest płaski: od `k` równego 10 wzwyż wynik się nie zmienia, podczas gdy waga w sumie ważonej musi być dostrojona na zestawie, którego na starcie projektu nie masz.
- `fastembed` i wektory rzadkie w Qdrancie to właściwa architektura produkcyjna, a własna implementacja RRF zgadza się z serwerową co do kolejności (1118 identycznych identyfikatorów na 1120) – ale `Qdrant/bm25` nie zna polskiego stemmera i ramię leksykalne traci na tym 0,13 recall.
- Reranking cross-enkoderem na dwudziestu kandydatach daje +0,13 nad samym wyszukiwaniem gęstym i +0,02 nad hybrydą; hybryda i reranking naprawiają w dużej mierze te same pytania, więc ich zyski się nie sumują.
- Pięćdziesiąt kandydatów zamiast dwudziestu podwaja latencję rerankingu i nie poprawia żadnej metryki na mMiniLM; `bge-reranker-v2-m3` jest lepszy o 0,03–0,06 recall, ale dwadzieścia razy wolniejszy nawet na GPU.
- Wynik cross-enkodera, w odróżnieniu od kosinusa e5, częściowo separuje pytania bez odpowiedzi: próg -2 odrzuca cztery z siedmiu negatywów, nie tracąc ani jednego z czterdziestu dziewięciu pozytywów; odrzucenie wszystkich siedmiu kosztowałoby dwadzieścia dziewięć poprawnych.
- Limit jednego fragmentu na sekcję podnosi recall pytań porównawczych z 0,68 na 0,77, a MMR – w obu wariantach – nie daje nic albo szkodzi, bo wąski rozrzut kosinusów E5 nie niesie użytecznej miary redundancji.

## Co dalej

Rozdział 4 zajmuje się ostatnią kategorią porażek z rozdziału 1, tą, której ten rozdział nie ruszył: pytaniami sformułowanymi słowami, których w dokumencie nie ma. Zobaczysz query rewriting, multi-query, HyDE, step-back i dekompozycję pytań złożonych, filtrowanie po metadanych oraz routing – i tam też złoży się chunking z rozdziału 2 z hybrydą i rerankingiem z tego rozdziału w jeden pomiar. Zanim tam przejdziesz, uruchom u siebie `experiments/03_bm25.py` i przeczytaj listę pytań, na których BM25 wygrywa z modelem gęstym, a potem listę, na których przegrywa. Kwadrans, po którym przestaniesz traktować „hybryda jest lepsza” jako regułę, a zaczniesz jako hipotezę do sprawdzenia na swoim korpusie.

## Źródła

- https://qdrant.tech/documentation/concepts/hybrid-queries/
- https://qdrant.tech/documentation/concepts/vectors/
- https://qdrant.tech/documentation/concepts/search/
- https://qdrant.github.io/fastembed/examples/Supported_Models/
- https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
- https://huggingface.co/BAAI/bge-reranker-v2-m3
- https://sbert.net/examples/applications/retrieve_rerank/README.html
- https://dl.acm.org/doi/10.1145/1571941.1572114
- https://platform.claude.com/docs/en/api/messages
