# Rozdział 7. Bazy wektorowe

> **Z roadmapy:** Vector Databases, Vector DBs, Purpose and Functionality, Popular Vector DBs (pick one): Chroma, Pinecone, Weaviate, FAISS, LanceDB, Qdrant, Supabase, MongoDB Atlas, Implementing Vector Search, Indexing Embeddings, Performing Similarity Search
>
> **Pakiety:** `pip install qdrant-client faiss-cpu chromadb sentence-transformers numpy`

Embedding jest wektorem liczb, a podobieństwo dwóch wektorów to iloczyn skalarny. Skoro tak, to całe wyszukiwanie semantyczne mieści się w jednej linijce numpy: `scores = matrix @ query`, potem `argsort` i masz ranking. Dla tysiąca akapitów dokumentacji to działa, jest dokładne co do ostatniego bitu i nie wymaga żadnej infrastruktury. Zanim sięgniesz po bazę wektorową, warto umieć nazwać moment, w którym ta linijka przestaje wystarczać – bo ten moment przychodzi później, niż sugerują materiały marketingowe dostawców.

Przestaje wystarczać z czterech powodów naraz. Skala: przy milionie wektorów po 384 wymiary macierz zajmuje półtora gigabajta, a każde zapytanie to pełny przemiał tej macierzy. Filtrowanie: prawie nigdy nie szukasz w całym zbiorze, tylko w dokumentach jednego klienta, jednego języka albo z ostatniego kwartału, więc obok wektora musi mieszkać metadana i musi dać się po niej filtrować bez ładowania wszystkiego do pamięci. Trwałość: indeks ma przeżyć restart procesu bez liczenia embeddingów od nowa. Aktualizacje: dokumenty się zmieniają, znikają i dochodzą, a przebudowywanie całej macierzy przy każdej edycji nie jest planem.

Baza wektorowa odpowiada na te cztery rzeczy naraz: struktura danych znajdująca najbliższych sąsiadów bez przeglądania wszystkiego, plus magazyn metadanych, plus trwałość, plus API do wstawiania i usuwania pojedynczych rekordów. Cena jest jedna i trzeba ją znać od początku: wynik przestaje być dokładny. W tym rozdziale zobaczysz, skąd bierze się ta niedokładność, jak się ją mierzy i jak wybrać narzędzie, które nie okaże się za trzy miesiące klockiem u nogi.

## Po co baza wektorowa i jak działa

### Wyszukiwanie dokładne kontra przybliżone

Wyszukiwanie dokładne (exact search, k-NN) porównuje zapytanie z każdym wektorem w zbiorze. Złożoność jest liniowa względem liczby wektorów i względem wymiaru, a wynik jest z definicji poprawny. W FAISS odpowiadają za to indeksy z rodziny `IndexFlat`, w Qdrancie jest to tryb, do którego baza sama schodzi przy małych kolekcjach. Nie lekceważ go: nowoczesny procesor przemiela kilkaset tysięcy wektorów po 384 wymiary w pojedynczych milisekundach, a implementacja w numpy nie ma żadnych parametrów do zepsucia.

Wyszukiwanie przybliżone (approximate nearest neighbor, ANN) rezygnuje z gwarancji poprawności w zamian za czas. Zamiast przejrzeć wszystko, przegląda starannie wybraną garstkę kandydatów – i w tej garstce zwykle, ale nie zawsze, siedzą prawdziwi najbliżsi sąsiedzi. „Zwykle" jest tu terminem technicznym i ma miarę, o której za chwilę. Każdy indeks ANN ma więc pokrętło: przekręcasz je w stronę jakości i płacisz czasem, przekręcasz w stronę czasu i płacisz trafnościami.

### HNSW i IVF

HNSW (Hierarchical Navigable Small World) to dziś domyślny indeks w większości baz wektorowych – używają go Qdrant, Weaviate, pgvector, Chroma w wersji jednowęzłowej i Atlas Vector Search. Intuicja jest grafowa. Każdy wektor jest wierzchołkiem, a krawędzie łączą go z kilkunastoma bliskimi sąsiadami; zapytanie zaczyna w losowym punkcie i wielokrotnie przeskakuje do sąsiada bliższego celu, aż nie da się poprawić. Taki graf łatwo utknąłby w lokalnym minimum, więc HNSW układa kilka warstw: górne są rzadkie i mają długie krawędzie, dolne gęste i krótkie. Wyszukiwanie zjeżdża piętrami – najpierw przelatuje pół przestrzeni kilkoma skokami po górze, potem dopracowuje wynik na dole. To ta sama idea, co lista z przeskokami (skip list), przeniesiona do przestrzeni metrycznej.

HNSW ma trzy parametry, które nazywają się tak samo we wszystkich implementacjach. `m` to maksymalna liczba krawędzi wychodzących z wierzchołka na warstwie – domyślnie 16 w Qdrancie i 16 w Chromie, gdzie nazywa się `max_neighbors`; większe `m` to gęstszy graf, lepsza jakość i więcej pamięci. `ef_construct` (w FAISS `efConstruction`) to szerokość przeszukiwania przy budowie grafu, domyślnie 100 w Qdrancie i w Chromie; rośnie z nim czas indeksowania i jakość krawędzi. `ef` (w FAISS `efSearch`) to szerokość przeszukiwania przy zapytaniu – i to jest owo pokrętło, jedyny z trzech parametrów, który zmienisz bez przebudowy indeksu.

IVF (inverted file) idzie inną drogą: dzieli przestrzeń na komórki algorytmem k-średnich i zapamiętuje, który wektor wpadł do której. Zapytanie liczy odległość tylko do centroidów, wybiera `nprobe` najbliższych komórek i przegląda wyłącznie ich zawartość, czyli z grubsza `nprobe/nlist` zbioru; dokumentacja FAISS zaleca dobierać `nlist` w okolicach pierwiastka z liczby wektorów. W odróżnieniu od HNSW indeks IVF wymaga treningu (`index.train(...)`), bo centroidy trzeba policzyć na reprezentatywnej próbce. W zamian daje przewidywalne zużycie pamięci i dobrze łączy się z kompresją.

### Kwantyzacja

Krawędzie grafu nie są największym kosztem – są nim wektory. Milion embeddingów po 1536 wymiarów we `float32` to sześć gigabajtów, zanim dołożysz cokolwiek innego. Kwantyzacja (quantization) zmniejsza ten rachunek, przechowując wektory w gorszej precyzji i akceptując błąd w wyliczanej odległości.

Trzy warianty warto znać. Kwantyzacja skalarna zamienia każdą składową z `float32` na `uint8`, czyli kompresuje czterokrotnie; dokumentacja Qdranta podaje, że w ich eksperymentach błąd wynosi poniżej jednego procenta. Kwantyzacja produktowa (product quantization, PQ) dzieli wektor na podwektory i każdy zastępuje indeksem najbliższego elementu z małego słownika – kompresja sięga tu 64 razy, kosztem wyraźnie większego błędu. Kwantyzacja binarna sprowadza każdą składową do jednego bitu, kompresuje 32 razy i daje, według dokumentacji Qdranta, nawet czterdziestokrotne przyspieszenie, ale wymaga wektorów o dużej liczbie wymiarów i wyśrodkowanego rozkładu (stan na wrzesień 2026).

Wspólnym ratunkiem na błąd kwantyzacji jest przeliczanie (rescoring) z nadpróbkowaniem (oversampling): indeks skwantyzowany wybiera więcej kandydatów, niż potrzebujesz, a ostateczny ranking liczysz na oryginalnych wektorach. Przy `oversampling` równym 2,4 i limicie 100 baza wstępnie wybierze 240 wektorów i dopiero je przeliczy. Zapamiętaj regułę: kwantyzacja binarna praktycznie zawsze wymaga przeliczania, skalarna zwykle nie.

### Metryki, payload i filtrowanie

Metryka decyduje, co znaczy „blisko". W praktyce używasz trzech: kosinusowej (`cosine`), iloczynu skalarnego (`dot`, `ip`) i euklidesowej (`l2`). Dla wektorów znormalizowanych do długości jeden wszystkie trzy uszeregują wyniki tak samo. Różnica zaczyna się przy wektorach nieznormalizowanych: iloczyn skalarny premiuje wtedy wektory długie, co bywa pożądane, a częściej jest błędem. Najbezpieczniejsza domyślna decyzja to normalizować embeddingi przy zapisie i wybierać `cosine` – pamiętając, że Chroma domyślnie liczy `l2`.

Payload (w innych bazach: metadata, properties, atrybuty) to dane nieliczbowe przypięte do wektora: identyfikator dokumentu, język, właściciel, data, kategoria, sam tekst chunku. Filtrowanie po payloadzie najmocniej odróżnia bazę wektorową od macierzy w numpy i jest trudniejsze, niż wygląda. Naiwne „znajdź sto najbliższych, potem odfiltruj" (post-filtering) rozsypuje się, gdy filtr przepuszcza jeden dokument na tysiąc – dostajesz zero wyników mimo tego, że pasujące dokumenty istnieją. Podejście odwrotne, „odfiltruj, potem szukaj" (pre-filtering), wymaga przeglądania wszystkiego, co przeszło filtr. Bazy rozwiązują to na poziomie indeksu: Qdrant buduje filtrowalny HNSW, dokładając do grafu krawędzie oparte na indeksowanych wartościach payloadu, i wymaga, żeby indeks payloadu istniał przed wstawieniem danych. Pola, po których będziesz filtrować, zadeklaruj więc przy tworzeniu kolekcji, a nie po zaindeksowaniu miliona punktów.

### Hybrydowe wyszukiwanie i recall@k

Wyszukiwanie gęste (dense) świetnie radzi sobie z parafrazą i z językiem, ale gubi rzeczy, które są dosłowne: numer katalogowy, nazwę własną, identyfikator błędu. Odwrotnie zachowuje się klasyczne wyszukiwanie leksykalne BM25, które nie ma pojęcia o synonimach, ale numer katalogowy trafia bezbłędnie. Hybryda łączy oba rankingi. Qdrant robi to w jednym zapytaniu przez `prefetch` i `FusionQuery` z metodą RRF (reciprocal rank fusion, wynik to suma `1/(k + rank)`) albo DBSF. Weaviate ma parametr `alpha` przesuwający wagę między częścią wektorową (`alpha=1`) a BM25F (`alpha=0`) i domyślnie łączy wyniki metodą `relativeScoreFusion` (od wersji 1.24). MongoDB Atlas składa oba rankingi etapem `$rankFusion`. W rozdziale 8 hybryda wróci jako standardowy element potoku RAG – tutaj wystarczy wiedzieć, że jest funkcją bazy, a nie czymś, co dopisujesz sam.

Zostaje pytanie, jak zmierzyć, ile tracisz na przybliżeniu. Miarą jest recall@k: dla zestawu zapytań liczysz wynik pełnym przeglądem, potem wynik z indeksu ANN, i sprawdzasz, jaka część prawdziwej dziesiątki znalazła się w zwróconej dziesiątce. Recall@10 równy 0,94 znaczy, że średnio 9,4 z 10 prawdziwych sąsiadów wróciło z zapytania. To jedyna liczba pozwalająca świadomie ustawić `ef` albo `nprobe` i jedyna, która wykrywa, że indeks zaczął po cichu gubić wyniki.

## Przegląd popularnych baz

Roadmapa wymienia osiem pozycji i sugeruje wybrać jedną. Różnią się przede wszystkim tym, ile infrastruktury dokładają do Twojego systemu – od biblioteki w procesie po zarządzaną usługę z rozliczeniem za operacje.

| Nazwa | Typ | Hosting | Filtry po metadanych | Hybryda | Licencja / wejście | Kiedy wybrać |
|---|---|---|---|---|---|---|
| FAISS | biblioteka | w procesie | brak | brak | MIT | eksperymenty, benchmarki, pełna kontrola nad indeksem |
| Chroma | biblioteka / serwer | w procesie, Docker, Chroma Cloud | tak (`where`) | tak | Apache 2.0 | prototyp, gdy chcesz API na dokumentach, nie na wektorach |
| LanceDB | biblioteka / format | w procesie, dysk lub S3, LanceDB Cloud | tak (SQL) | tak | Apache 2.0 | dane multimodalne i wersjonowany zbiór na obiektowym storage |
| Qdrant | serwer | Docker, self-hosted, Qdrant Cloud (free tier) | tak (filtrowalny HNSW) | tak (RRF/DBSF) | Apache 2.0 | produkcja, gdy filtrowanie i kwantyzacja mają znaczenie |
| Weaviate | serwer | Docker, Kubernetes, Weaviate Cloud | tak | tak (`alpha`) | BSD-3-Clause | gdy chcesz wektoryzację i moduły po stronie bazy |
| pgvector (Supabase) | rozszerzenie bazy relacyjnej | dowolny Postgres, Supabase | tak (zwykły `WHERE`) | tak (z `tsvector`) | PostgreSQL License | gdy już masz Postgresa i transakcyjne dane obok wektorów |
| Pinecone | managed | wyłącznie SaaS | tak (40 KB/rekord) | tak (dense + sparse) | zamknięta; Starter darmowy | gdy nie chcesz utrzymywać niczego |
| MongoDB Atlas | managed | Atlas (i self-managed) | tak (MQL) | tak (`$rankFusion`) | zamknięta; darmowy klaster | gdy dokumenty już są w Mongo |

FAISS to biblioteka Meta AI napisana w C++ z wrapperem dla Pythona i numpy. Nie jest bazą: nie ma serwera, trwałości poza `write_index`, metadanych ani filtrowania – dostajesz strukturę danych i pełną kontrolę nad nią. Za to żadne inne narzędzie nie da Ci tylu wariantów indeksu do porównania w jednym procesie, więc FAISS jest naturalnym miejscem, żeby zrozumieć, co robi HNSW i ile kosztuje kwantyzacja.

Chroma celuje w wygodę. Przyjmuje teksty, sama liczy embeddingi wybraną funkcją i sama je indeksuje; wołasz `add(documents=...)` i `query(query_texts=...)`, a wektorów nie widzisz na oczy. Wersja jednowęzłowa stoi na HNSW, rozproszona i Chroma Cloud na indeksie SPANN. To najkrótsza droga od pomysłu do działającego wyszukiwania, a jej wadą jest ta sama wygoda: warstwa embeddingów jest ukryta, więc trudniej nad nią panować.

LanceDB jest biblioteką osadzoną zbudowaną wokół kolumnowego formatu Lance, który leży na zwykłym dysku albo na storage obiektowym. Dzięki temu ten sam zbiór jest jednocześnie tabelą do analityki, źródłem do treningu i indeksem wektorowym, a wersjonowanie danych jest wbudowane; do tego dochodzi wyszukiwanie pełnotekstowe, hybrydowe, reranking i filtrowanie SQL-em. Wybierzesz ją przy danych multimodalnych albo gdy nie chcesz kopiować zbioru między hurtownią a bazą wektorową.

Qdrant to serwer napisany w Ruście, z licencją Apache 2.0, obrazem Dockera i zarządzaną chmurą z darmowym poziomem. Jego wyróżnikiem jest praca z filtrami: filtrowalny HNSW, bogaty język warunków (`Filter`, `FieldCondition`, zakresy, geo, pełny tekst) i indeksy payloadu z konfigurowalnym poziomem trzymania w pamięci. Ma też najbardziej rozbudowany zestaw kwantyzacji spośród rozwiązań open source, a klient Pythona działa w trybie lokalnym (`QdrantClient(":memory:")`), więc te same wywołania uruchomisz w teście jednostkowym bez serwera.

Weaviate jest serwerem na licencji BSD-3-Clause, uruchamianym przez Dockera, Kubernetes, w trybie osadzonym albo w Weaviate Cloud. Odróżnia go filozofia modułów: baza może sama wołać model embeddingowy, rerankować i generować odpowiedź, więc część potoku RAG przenosi się z Twojego kodu do konfiguracji bazy. Hybrydę ma dopracowaną – jedno pokrętło `alpha` i dwie metody łączenia rankingów.

pgvector to rozszerzenie PostgreSQL, a Supabase to najwygodniejszy sposób, żeby dostać Postgresa z tym rozszerzeniem gotowym do włączenia. Kolumna typu `vector(n)` żyje w zwykłej tabeli, obok kluczy obcych i kolumn tekstowych, więc filtrowanie jest zwykłym `WHERE`, a spójność transakcyjna wynika z bazy. Jedno ograniczenie warto znać: typ `vector` przyjmuje do 16 000 wymiarów, ale indeks tylko do 2000 (typ `halfvec` – do 4000).

Pinecone jest usługą zarządzaną i nie da się go uruchomić u siebie. W zamian dostajesz brak operacji: nie ma wersji, kopii zapasowych ani skalowania do przemyślenia. Rozliczenie idzie za operacje – jednostki odczytu (RU) i zapisu (WU) plus magazyn – z darmowym planem Starter i płatnymi od 20 dolarów miesięcznie (Builder) oraz od 50 dolarów minimum (Standard) (stan na wrzesień 2026). Indeksy dokumentowe łączą dziś wektory gęste, rzadkie i BM25 w jednej strukturze.

MongoDB Atlas Vector Search dokłada wyszukiwanie wektorowe do bazy dokumentowej, którą być może już masz. Zapytanie to etap `$vectorSearch` na początku potoku agregacji, z polami `index`, `path`, `queryVector`, `numCandidates` i `filter`; obsługuje HNSW i tryb dokładny, wektory do 8192 wymiarów, kwantyzację oraz hybrydę przez `$rankFusion`. Argument jest ten sam co przy pgvectorze: wektory blisko danych, jedna baza do utrzymania.

## Indeksowanie embeddingów

Indeksowanie to trzy decyzje: jakie parametry ma wektor, jaki payload mu towarzyszy i jakie identyfikatory nadajesz punktom. Zacznijmy od Qdranta w trybie lokalnym, bo `QdrantClient(":memory:")` daje pełne API bez stawiania czegokolwiek.

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DOCS = [
    ("Indeks HNSW przyspiesza wyszukiwanie przybliżone.", "pl", "search"),
    ("Product quantization reduces index memory footprint.", "en", "search"),
    ("Kopia zapasowa kolekcji wykonywana jest snapshotem.", "pl", "ops"),
    ("Rolling updates require a replication factor above one.", "en", "ops"),
    ("Embeddingi zdaniowe liczymy modelem wielojęzycznym.", "pl", "embeddings"),
    ("Cosine similarity needs L2-normalized vectors.", "en", "embeddings"),
]

encoder = SentenceTransformer(MODEL)
vectors = encoder.encode([text for text, _, _ in DOCS], normalize_embeddings=True)
dim = vectors.shape[1]

client = QdrantClient(":memory:")
client.create_collection(
    collection_name="notes",
    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
)
client.upsert(
    collection_name="notes",
    points=[
        PointStruct(
            id=i,
            vector=vector.tolist(),
            payload={"text": text, "lang": lang, "topic": topic},
        )
        for i, (vector, (text, lang, topic)) in enumerate(zip(vectors, DOCS))
    ],
)

info = client.get_collection("notes")
print("dim:", dim, "points:", info.points_count, "distance:", info.config.params.vectors.distance)
```

```text
dim: 384 points: 6 distance: Cosine
```

Trzy rzeczy są tu warte uwagi. `VectorParams` to kontrakt kolekcji: rozmiar i metryka są ustalane raz i nie da się ich zmienić – wstawienie wektora o innej długości skończy się błędem, a zmiana modelu embeddingów oznacza nową kolekcję. `normalize_embeddings=True` w `encode()` załatwia normalizację po stronie modelu, więc `Distance.COSINE` i `Distance.DOT` dadzą tu ten sam ranking. Wreszcie payload zawiera pełny tekst chunku: to nie marnotrawstwo, tylko warunek tego, żeby po wyszukiwaniu nie biec do drugiej bazy po treść.

Identyfikatory zasługują na osobne zdanie. Qdrant przyjmuje liczbę całkowitą albo UUID, więc naturalnym wyborem jest deterministyczny UUID wyliczony z pary „identyfikator dokumentu, numer chunku" (`uuid.uuid5`). Wtedy `upsert` tego samego chunku nadpisuje punkt zamiast tworzyć duplikat, a ponowne przetworzenie dokumentu jest idempotentne. Wstawiaj paczkami, po kilkaset punktów na wywołanie – koszt siedzi w liczbie żądań, nie w liczbie wektorów.

Teraz ta sama operacja w FAISS, gdzie widać dokładnie, ile kosztuje struktura indeksu.

```python
import os
import faiss
import numpy as np

D, N = 384, 50_000
rng = np.random.default_rng(7)
data = rng.normal(size=(N, D)).astype("float32")
faiss.normalize_L2(data)  # cosine == inner product on normalized vectors

flat = faiss.IndexFlatIP(D)
flat.add(data)

hnsw = faiss.IndexHNSWFlat(D, 32, faiss.METRIC_INNER_PRODUCT)
hnsw.hnsw.efConstruction = 80
hnsw.add(data)

print("flat  trained:", flat.is_trained, "ntotal:", flat.ntotal)
print("hnsw  trained:", hnsw.is_trained, "ntotal:", hnsw.ntotal)

faiss.write_index(flat, "flat.faiss")
faiss.write_index(hnsw, "hnsw.faiss")
print("flat.faiss  MB:", round(os.path.getsize("flat.faiss") / 2**20, 1))
print("hnsw.faiss  MB:", round(os.path.getsize("hnsw.faiss") / 2**20, 1))
print("reloaded ntotal:", faiss.read_index("hnsw.faiss").ntotal)
```

```text
flat  trained: True ntotal: 50000
hnsw  trained: True ntotal: 50000
flat.faiss  MB: 73.2
hnsw.faiss  MB: 86.2
reloaded ntotal: 50000
```

`IndexFlatIP` przechowuje wektory i nic poza tym: 50 000 razy 384 razy 4 bajty to dokładnie 73,2 MB, które widzisz na dysku. `IndexHNSWFlat(D, 32, ...)` dokłada graf o `m` równym 32 i kosztuje 13 MB więcej – to cena wyszukiwania przybliżonego wyrażona w megabajtach. Oba indeksy mają `is_trained` równe `True`, bo ani `Flat`, ani `HNSW` nie wymagają treningu; przy `IndexIVFFlat` albo `IndexIVFPQ` trzeba najpierw zawołać `index.train(sample)`, inaczej `add()` rzuci wyjątkiem. `faiss.write_index` i `faiss.read_index` to cała trwałość, jaką FAISS oferuje – identyfikatory, metadane i mapowanie na dokumenty przechowujesz sam, zwykle w bazie relacyjnej obok.

Zostają dwie sprawy operacyjne. Wersjonowanie: indeks jest funkcją modelu embeddingów, więc zapisz nazwę i wersję modelu razem z indeksem (w Qdrancie w metadanych kolekcji, w FAISS w pliku obok) i sprawdzaj ją przy starcie aplikacji. Reindeksacja: zmiana modelu unieważnia wszystko, bo wektory ze starego i nowego modelu leżą w różnych przestrzeniach. Bezpieczny schemat to budowa nowej kolekcji obok starej, przełączenie aliasu i usunięcie starej po weryfikacji – nigdy „w miejscu".

## Wyszukiwanie podobieństwa

Zapytanie w Qdrancie to `query_points`: podajesz wektor, limit i opcjonalnie filtr po payloadzie. Zobaczmy najpierw, co robi filtr.

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, VectorParams, PointStruct,
                                  Filter, FieldCondition, MatchValue)
from sentence_transformers import SentenceTransformer

DOCS = [
    ("Indeks HNSW przyspiesza wyszukiwanie przybliżone.", "pl", "search"),
    ("Product quantization reduces index memory footprint.", "en", "search"),
    ("Kopia zapasowa kolekcji wykonywana jest snapshotem.", "pl", "ops"),
    ("Rolling updates require a replication factor above one.", "en", "ops"),
    ("Embeddingi zdaniowe liczymy modelem wielojęzycznym.", "pl", "embeddings"),
    ("Cosine similarity needs L2-normalized vectors.", "en", "embeddings"),
]

encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
vectors = encoder.encode([t for t, _, _ in DOCS], normalize_embeddings=True)

client = QdrantClient(":memory:")
client.create_collection("notes", VectorParams(size=vectors.shape[1], distance=Distance.COSINE))
client.upsert("notes", points=[
    PointStruct(id=i, vector=v.tolist(), payload={"text": t, "lang": lang, "topic": topic})
    for i, (v, (t, lang, topic)) in enumerate(zip(vectors, DOCS))
])

query = encoder.encode("jak zmniejszyć zużycie pamięci przez indeks", normalize_embeddings=True)

print("-- no filter")
for p in client.query_points("notes", query=query.tolist(), limit=3, with_payload=True).points:
    print(f"{p.score:.4f} [{p.payload['lang']}] {p.payload['text']}")

print("-- lang == pl")
hits = client.query_points(
    "notes", query=query.tolist(), limit=3, with_payload=True,
    query_filter=Filter(must=[FieldCondition(key="lang", match=MatchValue(value="pl"))]),
).points
for p in hits:
    print(f"{p.score:.4f} [{p.payload['lang']}] {p.payload['text']}")
```

```text
-- no filter
0.7448 [en] Product quantization reduces index memory footprint.
0.3282 [pl] Indeks HNSW przyspiesza wyszukiwanie przybliżone.
0.2117 [en] Rolling updates require a replication factor above one.
-- lang == pl
0.3282 [pl] Indeks HNSW przyspiesza wyszukiwanie przybliżone.
0.0832 [pl] Embeddingi zdaniowe liczymy modelem wielojęzycznym.
0.0577 [pl] Kopia zapasowa kolekcji wykonywana jest snapshotem.
```

Pierwszy wynik wart jest zatrzymania: polskie pytanie o zużycie pamięci przez indeks wyciągnęło angielskie zdanie o kwantyzacji produktowej z wynikiem 0,7448, podczas gdy najlepsze polskie zdanie dostało 0,3282. Model wielojęzyczny umieszcza zdania o tym samym znaczeniu blisko siebie niezależnie od języka – i właśnie dlatego filtr po języku jest osobnym mechanizmem, a nie efektem ubocznym embeddingów. `query_points` zwraca obiekt z polem `.points`, na liście są `ScoredPoint` z `id`, `score` i `payload`; `with_payload=True` jest konieczne, bo domyślnie payload nie wraca. Zauważ też, że trafienia po filtrze mają niskie wyniki podobieństwa – filtr zawęża zbiór, ale nie zmienia progu trafności, więc odcięcie musisz nałożyć sam.

Zostaje pytanie, ile na przybliżeniu tracimy. Poniższy snippet buduje zbiór 50 000 wektorów skupionych wokół 200 centroidów (czyli z grubsza tak, jak układają się prawdziwe embeddingi), liczy prawdę indeksem dokładnym i porównuje z HNSW dla kilku wartości `efSearch`.

```python
import time
import faiss
import numpy as np

faiss.omp_set_num_threads(1)  # stable, comparable timings

D, N, K = 384, 50_000, 10
rng = np.random.default_rng(7)
centroids = rng.normal(size=(200, D)).astype("float32")
data = (centroids[rng.integers(0, 200, N)] + 0.35 * rng.normal(size=(N, D))).astype("float32")
faiss.normalize_L2(data)
queries = (data[rng.choice(N, 500, replace=False)]
           + 0.05 * rng.normal(size=(500, D))).astype("float32")
faiss.normalize_L2(queries)

flat = faiss.IndexFlatIP(D)
flat.add(data)
hnsw = faiss.IndexHNSWFlat(D, 32, faiss.METRIC_INNER_PRODUCT)
hnsw.hnsw.efConstruction = 80
hnsw.add(data)

t0 = time.perf_counter()
_, truth = flat.search(queries, K)
flat_ms = (time.perf_counter() - t0) * 1000 / len(queries)
print(f"IndexFlatIP        recall@{K}=1.000  {flat_ms:.3f} ms/query")

for ef in (16, 32, 64, 128):
    hnsw.hnsw.efSearch = ef
    t0 = time.perf_counter()
    _, found = hnsw.search(queries, K)
    ms = (time.perf_counter() - t0) * 1000 / len(queries)
    recall = np.mean([len(set(a) & set(b)) / K for a, b in zip(truth, found)])
    print(f"IndexHNSWFlat ef={ef:<4} recall@{K}={recall:.3f}  {ms:.3f} ms/query")
```

```text
IndexFlatIP        recall@10=1.000  0.411 ms/query
IndexHNSWFlat ef=16   recall@10=0.742  0.046 ms/query
IndexHNSWFlat ef=32   recall@10=0.874  0.064 ms/query
IndexHNSWFlat ef=64   recall@10=0.941  0.089 ms/query
IndexHNSWFlat ef=128  recall@10=0.978  0.139 ms/query
```

To jest cały kompromis ANN na jednym ekranie. Indeks dokładny bierze 0,411 ms na zapytanie i z definicji ma recall równy jedności. HNSW przy `efSearch=16` jest dziewięć razy szybszy, ale gubi co czwartego sąsiada; przy `efSearch=128` odzyskuje 97,8 procent wyników i wciąż jest trzykrotnie szybszy. Przy 50 000 wektorów ta przewaga jest skromna – prawdziwa różnica pojawia się o dwa rzędy wielkości dalej, bo czas indeksu dokładnego rośnie liniowo, a HNSW z grubsza logarytmicznie. `efSearch` dobierasz więc eksperymentem: ustal próg recall wymagany przez produkt (dla RAG zwykle 0,95 wystarcza z zapasem) i wybierz najmniejsze `ef`, które go osiąga.

Dla porównania to samo zadanie w Chromie. Różnica w API jest ciekawsza niż w wynikach: operujesz dokumentami, nie wektorami.

```python
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

client = chromadb.EphemeralClient()  # PersistentClient(path="./chroma") to keep data
collection = client.get_or_create_collection(
    name="notes",
    embedding_function=SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    ),
)

collection.add(
    ids=["1", "2", "3", "4"],
    documents=[
        "Indeks HNSW przyspiesza wyszukiwanie przybliżone.",
        "Product quantization reduces index memory footprint.",
        "Kopia zapasowa kolekcji wykonywana jest snapshotem.",
        "Rolling updates require a replication factor above one.",
    ],
    metadatas=[{"lang": "pl"}, {"lang": "en"}, {"lang": "pl"}, {"lang": "en"}],
)

result = collection.query(
    query_texts=["jak zmniejszyć zużycie pamięci przez indeks"],
    n_results=2,
    where={"lang": "en"},
)
for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
    print(f"{dist:.4f} [{meta['lang']}] {doc}")
```

```text
0.2552 [en] Product quantization reduces index memory footprint.
0.7883 [en] Rolling updates require a replication factor above one.
```

Nigdzie nie pojawia się wektor. Podajesz teksty, Chroma je koduje, `query_texts` koduje zapytanie tą samą funkcją, a filtr metadanych to słownik w argumencie `where`. Zwróć uwagę na liczby: to odległości, a nie podobieństwa, więc mniej znaczy lepiej – i są to odległości `l2`, bo taka jest domyślna metryka Chromy; kosinusa ustawiasz jawnie w konfiguracji kolekcji. Wynik wraca jako słownik list list, bo `query()` przyjmuje wiele zapytań naraz.

Na koniec wariant relacyjny. Poniższy SQL działa na każdym Postgresie z rozszerzeniem pgvector, a w Supabase włączasz je jednym kliknięciem w zakładce Extensions.

```sql
create extension if not exists vector;

create table documents (
  id          bigserial primary key,
  tenant_id   uuid not null,
  lang        text not null,
  body        text not null,
  embedding   vector(384)
);

create index on documents using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 100);
create index on documents (tenant_id, lang);

-- :q is the query embedding, passed as a parameter, e.g. '[0.12, -0.03, ...]'
select id, body, 1 - (embedding <=> :q) as similarity
from documents
where tenant_id = :tenant and lang = 'pl'
order by embedding <=> :q
limit 10;
```

Operator `<=>` to odległość kosinusowa, więc podobieństwo dostajesz jako `1 - (...)`; dla iloczynu skalarnego jest `<#>` (zwraca wartość ujemną), dla euklidesowej `<->`. Kluczowe jest, żeby w `order by` stał ten sam operator co w klasie operatorów indeksu (`vector_cosine_ops`) – inaczej Postgres indeksu nie użyje i po cichu zrobi sekwencyjny skan. Zwykły `where` na `tenant_id` załatwia wielodostępność bez dodatkowego mechanizmu i to największa zaleta tego wariantu. Ograniczenie: indeks HNSW w pgvectorze obsługuje wektory do 2000 wymiarów (`halfvec` do 4000), więc embeddingi o 3072 wymiarach trzeba skrócić albo przechować w połówkowej precyzji (stan na wrzesień 2026).

## Wybór bazy w praktyce

Drzewo decyzyjne jest krótsze, niż sugeruje liczba opcji. Na etapie prototypu, gdy zbiór mieści się w pamięci i mierzysz, czy wyszukiwanie w ogóle działa, bierz FAISS, Chromę albo Qdranta w trybie `:memory:` – wszystkie trzy uruchamiasz jednym `pip install`, a przejście z Qdranta lokalnego na serwerowego to zmiana jednego argumentu konstruktora.

Na produkcji małej i średniej skali, do kilkunastu milionów wektorów, wybór sprowadza się do pytania, czy masz już Postgresa. Jeśli tak, pgvector jest zwykle tańszy niż nowy komponent w architekturze: jedna baza do monitorowania, jeden backup, jedne uprawnienia, transakcje obejmujące wektory i dane biznesowe naraz. Jeśli nie masz Postgresa albo filtry i kwantyzacja są krytyczne, postaw Qdranta – jeden kontener, konfiguracja w YAML-u i wyraźnie lepsze zachowanie przy selektywnych filtrach.

Wariant zarządzany (Pinecone, MongoDB Atlas, Weaviate Cloud, Qdrant Cloud) wybierasz, gdy koszt utrzymania przewyższa koszt abonamentu – co zależy głównie od tego, czy masz zespół dbający o infrastrukturę. Uważaj na model rozliczeń: w Pinecone płacisz za jednostki odczytu proporcjonalne do rozmiaru przestrzeni nazw, więc aplikacja generująca dużo zapytań na dużym indeksie bywa droższa, niż wynika z pierwszego szacunku.

Trzy aspekty operacyjne rozstrzygają częściej niż benchmarki. Kopie zapasowe: Qdrant robi snapshoty kolekcji, pgvector obejmuje zwykły `pg_dump`, przy FAISS backup piszesz sam – i pamiętaj, że odtworzenie indeksu z surowych tekstów wymaga ponownego policzenia embeddingów. Wielodostępność (multi-tenancy): w pgvectorze to kolumna i `WHERE`, w Qdrancie indeksowane pole payloadu (dokumentacja odradza kolekcję na klienta), w Pinecone przestrzenie nazw – wybierz jeden z tych mechanizmów od pierwszego dnia, bo przerabianie izolacji na działającym systemie jest bolesne. Koszty: przy milionie wektorów po 1536 wymiarów sama pamięć na wektory to 6 GB, więc albo płacisz za RAM, albo włączasz kwantyzację skalarną i schodzisz do 1,5 GB przy błędzie poniżej procenta.

## Podsumowanie

- Baza wektorowa daje cztery rzeczy, których nie daje macierz w numpy: wyszukiwanie przybliżone, filtrowanie po metadanych, trwałość i punktowe aktualizacje. Poniżej kilkuset tysięcy wektorów bez filtrów numpy nadal wygrywa prostotą.
- HNSW ma trzy parametry: `m` i `ef_construct` ustalasz przy budowie, a `ef` (`efSearch`) jest jedynym pokrętłem dostępnym przy zapytaniu. IVF dzieli przestrzeń na komórki, wymaga treningu i steruje się parametrem `nprobe`.
- Kwantyzacja kupuje pamięć za dokładność: skalarna 4 razy przy błędzie poniżej procenta, binarna 32 razy, produktowa do 64 razy. Warianty agresywne wymagają przeliczania wyników na oryginalnych wektorach.
- Normalizuj embeddingi i używaj metryki kosinusowej, o ile nie masz konkretnego powodu, żeby zrobić inaczej; sprawdzaj domyślne ustawienia, bo Chroma liczy domyślnie `l2`.
- Pola, po których filtrujesz, deklaruj jako indeksy payloadu przed wstawieniem danych – filtrowanie dopisane po fakcie albo przestaje działać, albo zamienia wyszukiwanie w pełny skan.
- Recall@k to jedyna liczba pozwalająca świadomie ustawić `ef`. Przy 50 000 wektorów `efSearch=128` daje 0,978 i jest trzy razy szybszy od indeksu dokładnego.
- Zmiana modelu embeddingów unieważnia indeks w całości: buduj nową kolekcję obok, przełącz alias, usuń starą.
- Wybieraj po infrastrukturze, nie po benchmarkach: masz Postgresa – pgvector; nie masz i chcesz open source – Qdrant; nie chcesz utrzymywać niczego – rozwiązanie zarządzane; prototypujesz – FAISS, Chroma albo Qdrant `:memory:`.

## Co dalej

Umiesz już zaindeksować embeddingi i znaleźć podobne. To środkowe ogniwo potoku, którego początek – dzielenie dokumentów i liczenie embeddingów – poznałeś w rozdziale 6, a koniec opisuje rozdział 8 („RAG"): wstrzyknięcie znalezionych fragmentów do promptu, ocena trafności odpowiedzi i radzenie sobie z tym, że wyszukiwanie czasem zwraca śmieci. Zanim tam przejdziesz, zrób dwie rzeczy na własnych danych. Po pierwsze, policz recall@10, porównując Qdranta albo HNSW z pełnym przeglądem w numpy; jeśli wyjdzie poniżej 0,9, masz pierwszego kandydata do poprawy jakości odpowiedzi i nie jest nim prompt. Po drugie, dodaj do payloadu wszystkie pola, po których kiedykolwiek będziesz chciał filtrować, i zaindeksuj je – to decyzja, którą najtrudniej odwrócić.

## Źródła

- https://qdrant.tech/documentation/quickstart/
- https://qdrant.tech/documentation/concepts/indexing/
- https://qdrant.tech/documentation/concepts/hybrid-queries/
- https://qdrant.tech/documentation/guides/quantization/
- https://github.com/qdrant/qdrant
- https://github.com/facebookresearch/faiss/wiki/Getting-started
- https://github.com/facebookresearch/faiss/wiki/Faiss-indexes
- https://github.com/facebookresearch/faiss
- https://docs.trychroma.com/docs/overview/getting-started
- https://docs.trychroma.com/docs/collections/configure
- https://docs.pinecone.io/guides/index-data/indexing-overview
- https://docs.pinecone.io/guides/manage-cost/understanding-cost
- https://docs.weaviate.io/weaviate/introduction
- https://docs.weaviate.io/weaviate/search/hybrid
- https://lancedb.github.io/lancedb/
- https://github.com/lancedb/lancedb
- https://supabase.com/docs/guides/ai/vector-columns
- https://github.com/pgvector/pgvector
- https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/
