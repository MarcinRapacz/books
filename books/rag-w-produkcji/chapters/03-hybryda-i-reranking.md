# Rozdział 3. Wyszukiwanie hybrydowe i reranking

> **Cel rozdziału:** dołożyć do wyszukiwania gęstego drugi, leksykalny ranking i przestawić wynik cross-enkoderem – oraz zmierzyć, ile każdy z tych kroków daje, ile kosztuje i który z dziewięciu chybionych pytań rozdziału 1 naprawia.
>
> **Kod:** `ragbook/hybrid.py`, `ragbook/rerank.py`, `experiments/03_*.py`. **Pakiety poza fundamentem:** brak – `rank_bm25`, `fastembed` i `sentence-transformers` są już w venv tomu.

„Jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi?” – tak brzmi jedno z pytań zamrożonego zestawu z rozdziału 1 (q022). Baseline zwraca na nie pięć fragmentów i cztery pochodzą z właściwego rozdziału tomu 1: „Tryby awarii kontekstu” dwa razy, wstęp i „Skąd bierze się kontekst”. Nie ma wśród nich jedynego potrzebnego – z sekcji „Techniki zarządzania kontekstem”, gdzie stoi odpowiedź: `clear_tool_uses_20250919`. Wyszukiwanie trafiło w temat i przegapiło ciąg znaków, który w korpusie występuje dokładnie raz i który znalazłby bezbłędnie zwykły `LIKE`.

Model embeddingowy uczy się reprezentacji z danych treningowych, a tego ciągu w nich nie było. `metadata.user_id` też nie, a `query_points` jeżeli już, to jako dwa angielskie słowa bez związku z klientem Qdranta. Wektor takiej nazwy nie leży blisko niczego sensownego – model nie ma z czego wyprowadzić jej znaczenia, więc umieszcza ją pośrodku przestrzeni, razem z resztą rzeczy, których nie rozumie. A dokumentacja techniczna składa się z takich ciągów w dużej mierze i to właśnie ich szuka się w niej najczęściej.

Baseline ma przy tym własność, która mówi, co robić dalej: recall@5 równy 0,72 i dziewięć pytań bez trafienia w piątce, ale recall@20 równy 0,96. To nie jest system, który nie umie znaleźć odpowiedzi – to system, który ją znajduje i stawia na jedenastym miejscu. Pierwsza technika z tego rozdziału atakuje ten rozjazd drugim rankingiem, liczonym na słowach zamiast na wektorach. Druga to reranking: model oceniający parę (pytanie, fragment) na jednym wejściu.

Żadna nie dotyka chunkera ani modelu embeddingowego, więc wszystkie pomiary robię na chunkach z rozdziału 1: stałe okno 128/32, 1550 fragmentów. Skrypty mają na górze zmienną `CHUNKER` i po podmianie na `project_chunks` z rozdziału 2 zmierzą wszystko od nowa. Uruchamiasz je z katalogu `code/`.

## BM25, czyli liczenie słów zamiast znaczeń

BM25 nie próbuje niczego rozumieć i to jest cała jego siła. Dla każdego słowa z pytania sprawdza trzy rzeczy: ile razy pada w dokumencie, jak rzadkie jest w całym korpusie i czy dokument nie jest podejrzanie długi. Częstość liczy z saturacją, żeby dziesiąte wystąpienie nie ważyło tyle co pierwsze, a o wyniku decyduje głównie rzadkość: ciąg występujący w korpusie raz ma maksymalną wagę i wygrywa natychmiast. Ta sama właściwość jest słabością – pytanie zadane innymi słowami niż dokument dostaje zero, bo BM25 nie zna synonimów. Stąd pomysł hybrydy: dwa rankingi o rozłącznych trybach awarii, złożone w jeden.

Zanim cokolwiek złożymy, trzeba zobaczyć, ile każdy ranking jest wart osobno – i tu polszczyzna wystawia rachunek. Analizator BM25 jest w tym projekcie jedną funkcją: tekst na małe litery, cięcie na ciągi liter i ciągi cyfr, reszta to separatory.

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

Klasa `[^\W\d_]` to „litera dowolnego alfabetu”: polskie znaki diakrytyczne przechodzą, a `snake_case` rozpada się na człony. To decyzja, nie przypadek – dzięki niej `user_id` w dokumencie trafi też zapytanie ze słowem „user”.

Teraz problem właściwy. BM25 porównuje ciągi znaków, a polszczyzna odmienia wszystko: „wektorowych”, „wektorami” i „wektorowy” to dla niego trzy różne słowa, więc pytanie i dokument mogą mówić o tym samym bez jednego wspólnego tokenu. Poprawne rozwiązanie to lematyzacja (`morfeusz2`, `spacy` z `pl_core_news_sm`) – kolejna zależność i kilkadziesiąt megabajtów. Rozwiązanie tanie do obrzydliwości: obciąć każdy token do N znaków. Końcówka fleksyjna siedzi w polszczyźnie na końcu wyrazu, więc odcięcie ogona skleja formy tego samego lematu za darmo.

| Wariant | recall@5 | recall@20 | MRR@5 | Bez trafienia |
|---|---|---|---|---|
| BM25, bez stemowania | 0,62 | 0,80 | 0,62 | 14 |
| BM25, obcięcie do 5 znaków | 0,73 | 0,86 | 0,68 | 9 |
| BM25, obcięcie do 4 znaków | 0,76 | 0,90 | 0,65 | 8 |
| gęsty e5-small (baseline rozdz. 1) | 0,72 | 0,96 | 0,67 | 9 |

Skrypt: `experiments/03_bm25.py` (mierzy też wariant sześcioznakowy).

Brak jakiejkolwiek normalizacji fleksji to najdroższa pojedyncza pomyłka w tym rozdziale, a naprawia ją wycięcie plastra z tokenu: obcięcie do pięciu znaków podnosi recall@5 o 0,11 i zabiera pięć pytań z listy nietrafionych. Słownik korpusu zmniejsza się z 11 705 do 5533 typów, czyli scala mniej więcej co drugą formę. Cztery znaki dają wyższy recall, ale niższy MRR, bo sklejają za dużo: „model” i „moderacja” to przy czterech znakach jedno „mode”. Wybieram pięć.

Sam BM25 z tanim stemowaniem jest na tym korpusie **lepszy od modelu gęstego na recall@5** i zauważalnie gorszy na recall@20 (0,86 wobec 0,96). To cała jego charakterystyka: gdy trafia, trafia od razu na górę; gdy nie ma wspólnych słów, nie ma nic i głębsza lista tego nie naprawi.

| Typ | BM25 recall@5 | gęsty recall@5 |
|---|---|---|
| factual | 0,85 | 0,81 |
| procedural | 0,71 | 0,62 |
| comparative | 0,50 | 0,64 |

Skrypt: `experiments/03_bm25.py`.

Pytania faktograficzne i proceduralne wygrywa BM25, porównawcze przegrywa wyraźnie – i to ma mechanizm. Pytanie porównawcze („Qdrant czy pgvector do produkcji średniej skali?”) wymaga dwóch sekcji, a BM25 zwraca pięć fragmentów z jednej, bo to w niej oba terminy stoją obok siebie. Sumarycznie wygrywa z gęstym na siedmiu pytaniach, przegrywa na ośmiu, a cztery gubią oba.

Przy okazji warto poprawić intuicję z rozdziału 1. Pytanie o edycję kontekstu z otwarcia rozdziału naprawia się leksykalnie, ale nie dlatego, że zawiera `clear_tool_uses_20250919` – ono go nie zawiera, ten ciąg *jest* odpowiedzią. Naprawia się, bo słowa „edycja”, „kontekstu” i „narzędzi” po obcięciu do pięciu znaków trafiają w sekcję, w której stoją gęsto obok siebie. Hybryda pomaga na pytania *zadane* słowami z dokumentu, a nie na te, których *odpowiedzią* jest identyfikator; te drugie wracają w rozdziale 4. I jedna obserwacja dla rozdziału 6: wyniki BM25 dla pytań negatywnych i pozytywnych zachodzą na siebie tak samo jak kosinusy e5, więc progu odcięcia z niego nie zrobisz.

## Wektory rzadkie w Qdrancie

Powyższe liczyłem `rank_bm25`, biblioteką trzymającą indeks w pamięci procesu. To w porządku przy 1550 fragmentach i nie do utrzymania przy milionie. Produkcja wkłada oba rankingi do bazy: jedna kolekcja z dwoma **nazwanymi wektorami**, gęstym i rzadkim, i jedno zapytanie, które liczy oba ramiona i zwraca gotową fuzję. Wektor rzadki to para list – identyfikatory termów i ich wagi – a produkuje je `fastembed`, model `Qdrant/bm25`: nie sieć neuronowa, tylko tokenizator ze stop-słowami i stemmerem Snowball zapakowany w interfejs embeddera, ważący 10 MB (stan na wrzesień 2026).

Zapytanie hybrydowe to dwa podzapytania (`prefetch`) i reguła fuzji na górze:

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

Po stronie kolekcji liczy się jedna linijka: wektor rzadki zakładasz w `sparse_vectors_config` z `modifier=models.Modifier.IDF`. Model zapisuje tylko częstości termów w dokumencie, a rzadkość zależy od całego korpusu, więc Qdrant dolicza ją przy zapytaniu – ale tylko wtedy, gdy kolekcja o to prosi tym modyfikatorem. Bez niego wygrywają dokumenty pełne słowa „i”.

Drugi haczyk jest językowy. Argument `language` wybiera stop-słowa i stemmer Snowball, a `fastembed` zna osiemnaście języków, od arabskiego po turecki. Polskiego wśród nich nie ma, więc zostaje `disable_stemmer=True` – wariant, który w tabeli wyżej wypadł najgorzej.

| Wariant | recall@5 | recall@20 | Bez trafienia |
|---|---|---|---|
| Qdrant, wektor gęsty (named vector) | 0,72 | 0,96 | 9 |
| Qdrant, wektor rzadki (`Qdrant/bm25` + IDF) | 0,60 | 0,83 | 15 |
| Qdrant, RRF po stronie serwera | 0,80 | 0,92 | 6 |

Skrypt: `experiments/03_fusion.py`.

Architektura „wszystko w bazie” jest właściwa i tak wygląda produkcja, ale dla języka spoza listy osiemnastu kosztuje: ramię rzadkie bez stemmera traci 0,13 recall@5 wobec `rank_bm25` z obcięciem do pięciu znaków, a cała hybryda traci przez to 0,04. Jeżeli zostajesz przy bazie, podstaw własny analizator: policz wektory rzadkie samodzielnie i wyślij je jako `SparseVector`. Ja zostaję przy `rank_bm25` i liczę fuzję sam – wypada identycznie, bo na 56 pytaniach i dwudziestu pozycjach moja kolejność zgadza się z serwerową w 1118 przypadkach na 1120.

## Fuzja: RRF czy suma ważona

Masz dwie listy kandydatów – jedną z wyszukiwania gęstego, drugą z BM25 – i musisz zrobić z nich jedną. Przepis RRF (reciprocal rank fusion) mieści się w zdaniu: każdy dokument dostaje za swoje miejsce na liście `1 / (k + pozycja)`, a punkty z obu list się sumują. Kosinusy i punkty BM25 w ogóle nie wchodzą do rachunku, liczą się wyłącznie pozycje, więc dokument drugi na jednej liście i trzeci na drugiej wyprzedza taki, który był pierwszy w jednym rankingu, a w drugim nie ma go wcale. Stała `k` steruje tym, jak mocno czołówka góruje nad resztą: przy `k` równym 1 pierwsza pozycja jest warta dwa razy tyle co druga, przy 60 różnica to niecałe dwa procent.

Druga rodzina metod, **suma ważona wyników**, normalizuje wyniki każdego rankingu do przedziału [0, 1] i sumuje je z wagami. Jest naturalniejsza, ale wymaga wyników porównywalnych – a kosinus e5 w przedziale 0,84–0,93 i wynik BM25 w przedziale 0–37 takie nie są. Normalizacja min-max dokłada drugi problem: zależy od wielkości pobranej puli.

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

| Fuzja | recall@5 | MRR@5 | Bez trafienia |
|---|---|---|---|
| RRF, k=1 | 0,82 | 0,78 | 5 |
| RRF, k=10 | 0,86 | 0,79 | 3 |
| RRF, k=60 | 0,84 | 0,77 | 3 |
| suma ważona, waga gęstego 0,5 | 0,86 | 0,78 | 3 |

Skrypt: `experiments/03_fusion.py` (pełną siatkę – sześć wartości `k` i trzy wagi – wypisuje skrypt).

RRF wygrywa nie wynikiem – najlepszy rezultat obu rodzin jest ten sam – tylko kształtem okolicy optimum. Od `k` równego 10 w górę jest płaski: między dziesiątką a dwiema setkami mieści się 0,02 recall i zero pytań różnicy. Suma ważona ma ostre maksimum przy wadze 0,5 i spada o 0,08, gdy przesuniesz wagę o 0,3 w którąkolwiek stronę. Stąd wybór domyślny: **RRF nie wymaga strojenia, a wynik i tak wychodzi w granicach najlepszej wagi**, podczas gdy wagę trzeba dostroić na zestawie, którego na starcie projektu nie masz, i powtórzyć to po każdej podmianie chunkera. Trzeci parametr, czyli wielkość puli przed fuzją, okazał się prawie obojętny – między 20 a 200 recall@5 nie drgnął – więc zostaję przy 50.

| Typ | gęsty recall@5 | hybryda recall@5 | gęsty MRR@5 | hybryda MRR@5 |
|---|---|---|---|---|
| factual | 0,81 | 0,92 | 0,66 | 0,75 |
| procedural | 0,62 | 0,83 | 0,60 | 0,73 |
| comparative | 0,64 | 0,64 | 0,75 | 0,86 |

Skrypt: `experiments/03_fusion.py`.

Hybryda naprawia osiem pytań i psuje dwa, czyli netto sześć – zmiana, której nie da się wytłumaczyć losem. Zysk jest jednak nierówny: faktograficzne rosną o 0,11, proceduralne o 0,21, a **porównawcze o dokładnie nic**. Rośnie tylko ich MRR: pierwsza z dwóch potrzebnych sekcji wchodzi wyżej, a druga dalej nie wchodzi wcale. Ten jeden wiersz jest powodem, dla którego rozdział ma jeszcze sekcję o dywersyfikacji.

Wśród naprawionych jest pytanie o walidację zapytania SQL wygenerowanego przez model – jedyne w zestawie, które w rozdziale 1 nie miało trafienia nawet w top-20. Odpowiedź siedzi w dużym bloku kodu, a blok kodu to dla BM25 zbiór bardzo rzadkich termów o maksymalnej wadze. W korpusie z kodem hybryda jest więc pierwszą rzeczą do włączenia.

## Reranking cross-enkoderem

Model embeddingowy jest bi-enkoderem: patrzy na pytanie i na fragment **osobno**, zamienia każde w wektor i całą interakcję między nimi sprowadza do jednego iloczynu skalarnego. Cross-enkoder dostaje je **razem**, jako jedno wejście, w którym każdy token pytania widzi każdy token fragmentu, i zwraca jedną liczbę. Stąd bierze się i lepsza jakość, i wyższy koszt: wektory fragmentów liczysz raz, przy indeksowaniu, a cross-enkoder musi przy każdym zapytaniu przepuścić przez sieć każdego kandydata osobno. Dlatego pracuje w układzie dwustopniowym – pierwszy stopień wyciąga dwadzieścia–pięćdziesiąt kandydatów, drugi przestawia w nich kolejność i oddaje pięć.

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

Zwróć uwagę na `meta["stage1"]`: wynik pierwszego stopnia nie jest kasowany, tylko przesuwany – przyda się w rozdziale 8 przy śledzeniu zapytań. Testuję model mały, `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (około 470 MB, wielojęzyczny), i duży, `BAAI/bge-reranker-v2-m3` (2,2 GB). Oba zwracają logity, nie prawdopodobieństwa – wartości bywają ujemne i mają sens tylko w obrębie jednego zapytania (stan na wrzesień 2026).

| Wariant | recall@5 | MRR@5 | Bez trafienia |
|---|---|---|---|
| hybryda, bez rerankera | 0,84 | 0,77 | 3 |
| gęsty → mMiniLM, 20 kandydatów | 0,85 | 0,81 | 4 |
| hybryda → mMiniLM, 20 kandydatów | 0,86 | 0,81 | 3 |
| hybryda → bge-reranker-v2-m3, 50 kandydatów | 0,91 | 0,78 | 2 |

Skrypt: `experiments/03_rerank.py` (wariant bge: `experiments/03_rerank.py bge`; skrypt mierzy też pule pięćdziesięcioelementowe dla mMiniLM).

Szerokość pierwszego stopnia strój pod konkretny drugi stopień, a nie „na zapas”. Dla mMiniLM przejście z dwudziestu kandydatów na pięćdziesiąt **nie poprawia żadnej metryki** i podwaja koszt: wszystko, co ten model potrafił znaleźć, leżało już w dwudziestce. Mocniejszy bge korzysta z głębszej listy naprawdę, bo pięćdziesiątka podnosi jego recall@5 o 0,03.

Drugi wniosek jest ciekawszy: hybryda i reranking robią w dużej mierze **tę samą** robotę. Sam reranking na wyszukiwaniu gęstym daje 0,85, czyli więcej niż sama hybryda i prawie tyle, co jedno z drugim – przy recall@20 równym 0,96 cross-enkoder miał z czego wybierać. Zyski się nie sumują: osobno +0,12 i +0,13, razem +0,14. Jeżeli masz budżet latencji na jeden model więcej, sam reranking na indeksie gęstym da prawie cały zysk bez drugiego indeksu do utrzymania; jeżeli nie masz, hybryda daje prawie to samo za kilkanaście milisekund.

Jednego cross-enkoder nie zrobi. Pytania porównawcze mają przy mMiniLM najwyższy MRR w tabeli, 0,95, przy recall równym 0,68. Ta para liczb jest wymowna: model znakomicie wskazuje *najlepszy* fragment i jest obojętny na to, czy pozostałe cztery wnoszą cokolwiek nowego. Ocenia każdą parę osobno, więc nie ma jak zauważyć, że piąty kandydat jest kopią pierwszego.

### Ile to kosztuje czasu

Jakość nie zależy od tego, na czym liczysz, latencja zależy całkowicie. Poniżej ten sam pomiar na dwudziestu pytaniach, wykonany dwa razy: raz na CPU (Intel Core i5-9300H, osiem wątków), raz na GPU (NVIDIA GTX 1650, 4 GB VRAM), z rozgrzewką przed pomiarem.

| Etap | CPU p50 / p95 [ms] | GPU p50 / p95 [ms] |
|---|---|---|
| pierwszy stopień: hybryda, top-20 | 18 / 30 | 8 / 10 |
| mMiniLM, 20 kandydatów | 1258 / 1560 | 121 / 136 |
| bge-reranker-v2-m3, 20 kandydatów | 10 656 / 15 926 | 2560 / 2769 |

Skrypt: `experiments/03_latency.py cpu` oraz `experiments/03_latency.py cuda` (osobno ramiona pierwszego stopnia i pule pięćdziesięcioelementowe).

**Pierwszy stopień jest darmowy, cały koszt siedzi w drugim.** Wektor zapytania, przeszukanie Qdranta, BM25 na 1550 dokumentach i fuzja mieszczą się w ośmiu milisekundach na GPU, więc dokładanie indeksu leksykalnego nie jest decyzją o latencji, tylko o pamięci i kodzie do utrzymania. Reranking mMiniLM na dwudziestu kandydatach to na CPU 1,3 sekundy, mniej więcej sto pięćdziesiąt razy więcej; na GPU 121 milisekund, czyli budżet interaktywnej odpowiedzi. Na CPU dwudziestka jest granicą synchronicznego przetwarzania, a bge nie mieści się nigdzie.

Zapamiętaj zamiast tabel jedną liczbę: koszt cross-enkodera jest liniowy w liczbie par i dla mMiniLM wynosi 6 ms na parę na GPU (62–63 ms na CPU). Policzysz z niej budżet dla dowolnego `k` i zobaczysz, po co jest układ dwustopniowy – gdyby cross-enkoder oceniał wszystkie 1550 fragmentów, jedno zapytanie kosztowałoby na tym GPU dziewięć sekund.

## Reranking LLM-em

Cross-enkoder ocenia każdą parę osobno i to jest jego ograniczenie. Model językowy można poprosić o uszeregowanie **całej listy naraz**, z wiedzą o tym, co jest w pozostałych fragmentach – to podejście listwise, za cenę jednego wywołania modelu na zapytanie. Kształt jest prosty: ponumerowane fragmenty w prompcie, structured outputs na wyjściu, permutacja z powrotem.

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

Dwie rzeczy są obowiązkowe i obie wynikają z tego, że model nie jest funkcją. Structured outputs (`messages.parse` z `output_format`, tom 1, rozdział 3) gwarantują listę liczb całkowitych, ale nie permutację – model potrafi pominąć fragment albo wymienić ten sam dwa razy, więc kod dokleja brakujące indeksy na koniec. Prompt systemowy mówi zaś wprost „nie odpowiadaj na pytanie”, bo model poproszony o uszeregowanie chętnie dopisze odpowiedź, za którą zapłacisz w tokenach wyjściowych.

```text
=== Cost of listwise reranking, claude-haiku-4-5, 20 candidates, 600 chars each ===
per query: 3184 input tokens (e5 tokenizer), 88 output tokens
per query: 0.00362 USD, per 1000 queries: 3.62 USD
whole golden set (49 queries): 0.1776 USD
```

Skrypt: `experiments/03_llm_rerank.py`.

Liczby tokenów pochodzą z tokenizera e5, bo tylko taki mam lokalnie; prawdziwą wartość policzysz endpointem `count_tokens` (tom 1, rozdział 2) i wyjdzie niższa. Rząd wielkości jest jednak właściwy i to on decyduje: **3,6 dolara za tysiąc zapytań**, przy latencji rzędu sekundy i niezerowej szansie, że model zwróci coś, czego nie przewidziałeś. Cross-enkoder kosztuje na tej samej liście zero dolarów i jest deterministyczny.

Listwise ma więc sens tam, gdzie zapytań jest mało, a stawka za jedno wysoka: research prawniczy, wsparcie techniczne, wyszukiwarka dla dziesięciu analityków. Albo gdy nie masz dobrego cross-enkodera dla swojego języka, albo gdy potrzebujesz od rerankera czegoś więcej niż kolejności – uzasadnienia, sygnału do odmowy. Przy dużym i tanim ruchu nie ma sensu. Tego eksperymentu nie uruchomiłem, bo w książce nie ma klucza API; `experiments/03_llm_rerank.py` uruchomi go u Ciebie za osiemnaście centów.

## Próg odcięcia dla pytań bez odpowiedzi

Rozdział 1 zostawił otwartą sprawę: kosinus e5 nie pozwala odróżnić pytania, na które w korpusie jest odpowiedź, od pytania, na które jej nie ma. Wszystkie siedem pytań negatywnych dostawało na pierwszym miejscu wynik wyższy niż najsłabsze prawdziwe trafienie, bo kosinus mierzy podobieństwo dwóch wektorów, a nie to, czy w tekście stoi odpowiedź – model gęsty zawsze znajdzie **najbliższy** fragment, a najbliższy zawsze jakiś jest. Cross-enkoder uczy się czegoś innego, par (zapytanie, trafny passus) kontra (zapytanie, nietrafny passus), więc jego wyjście jest w zamierzeniu oceną trafności. Sprawdźmy: bierzemy jego najwyższy wynik w dwudziestce kandydatów i patrzymy na rozkład.

| Grupa | Pytań | min | mediana | max |
|---|---|---|---|---|
| pozytywne | 49 | -1,79 | +3,47 | +9,87 |
| negatywne | 7 | -4,38 | -2,08 | +5,20 |

Skrypt: `experiments/03_negatives.py`.

```text
threshold -2.0: catches 4/7 negatives, loses 0/49 positives
threshold  0.0: catches 5/7 negatives, loses 7/49 positives
to reject all 7 negatives the threshold must exceed +5.20,
  which also rejects 29 of 49 positives
```

Skrypt: `experiments/03_negatives.py`.

Rozkłady **nie** pokrywają się całkowicie i to jest istotna różnica wobec rozdziału 1. Liczba do zapamiętania jest jedna: **próg −2 odcina cztery z siedmiu pytań bez odpowiedzi i nie kosztuje ani jednego pytania z odpowiedzią**. To nie jest odmowa, tylko sygnał – tani, deterministyczny i policzony przy okazji rerankingu, który i tak wykonujesz. Odcięcie wszystkich siedmiu jest nieosiągalne: żeby złapać ostatnie trzy, próg musiałby przekroczyć +5,20, a wtedy zabrałby dwadzieścia dziewięć poprawnych odpowiedzi.

Które negatywy przechodzą? Pytanie o przepustowość modelu w tokenach na sekundę i pytanie o parametr `ef_search` w Elasticsearchu – te, które rozdział 1 opisał jako wzorcowe, bo brzmią jak pytania z dziedziny i mają w korpusie bliskich sąsiadów. Cross-enkoder nie ma jak odróżnić „ten fragment jest o `ef_search`” od „ten fragment jest o `ef` w Qdrancie”. Dla rozdziału 6 zostaje więc rekomendacja: próg jest tanim pierwszym filtrem, ale odmowa dla pozostałych pytań musi pozostać decyzją modelu w kroku generacji.

## Dywersyfikacja: pięć fragmentów, ile sekcji

Zostały pytania porównawcze, jedyne, których ani hybryda, ani reranking nie ruszyły. Mechanizm widać było od pierwszego pomiaru w rozdziale 1: wyszukiwanie po podobieństwie skupia się. Jeżeli sekcja jest trafna, jej sąsiednie fragmenty też są podobne do pytania i zajmują całą piątkę, więc druga potrzebna sekcja nie ma się jak wcisnąć.

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

Nadmiarowe fragmenty nie wypadają, tylko trafiają na koniec listy, więc limit nigdy nie zmniejsza liczby zwróconych fragmentów.

| Wariant | recall@5 | recall@5 comparative | Sekcji w top-5 |
|---|---|---|---|
| hybryda + rerank (bez dywersyfikacji) | 0,86 | 0,68 | 3,7 |
| limit 1 chunka na sekcję | 0,88 | 0,77 | 5,0 |
| MMR na kosinusie, λ=0,7 (najlepsze z czterech) | 0,76 | 0,73 | 4,1 |
| MMR na wyniku cross-enkodera, λ=0,7, 0,8 i 0,9 | 0,86 | 0,68 | 3,7 |

Skrypt: `experiments/03_diversify.py` (mierzy też limity 2 i 3 chunków oraz MMR przy λ=0,5).

Wygrywa wariant najbardziej prymitywny: **jeden chunk na sekcję**. Recall pytań porównawczych rośnie o 0,09, MRR nie spada, a w top-5 jest pięć różnych sekcji zamiast 3,7; na piętnastu pytaniach wielosekcyjnych obie potrzebne sekcje mieszczą się w piątce dla dziewięciu, a nie dla siedmiu. Limity 2 i 3 nie dają nic.

MMR jest tu wynikiem negatywnym i to w dwóch odmianach. W wersji podręcznikowej, gdzie trafnością jest kosinus do zapytania, **kasuje cały zysk rerankingu**, bo przestawia listę na podstawie tego samego sygnału, który cross-enkoder przed chwilą poprawił. W wersji z trafnością z wyniku cross-enkodera nie zmienia **nic**: kary za podobieństwo są prawie identyczne dla wszystkich kandydatów, bo wszyscy leżą w wąskim przedziale kosinusów rodziny E5. Model bez rozpiętości wyników nie daje użytecznej miary redundancji – a limit na sekcję działa, bo korzysta z metadanych, nie z geometrii.

Jest jednak koszt: precision@5 liczona po fragmentach spada z 0,43 na 0,22. To nie pogorszenie jakości, tylko artefakt definicji – gdy z każdej sekcji bierzesz jeden fragment, pytanie z jedną trafną sekcją ma w piątce najwyżej jedno trafienie, więc górna granica metryki wynosi 0,2. Prompt dostaje mniej powtórzeń, a więcej różnych miejsc korpusu i o to chodziło. Gdyby zależało Ci na dosłownym cytacie z długiej sekcji, lepszy jest parent-child z rozdziału 2.

## Co zostaje w projekcie

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | precision@5 | Bez trafienia |
|---|---|---|---|---|---|---|
| stałe okno 128/32 + e5-small (rozdz. 1) | 0,72 | 0,96 | 0,67 | 0,64 | 0,38 | 9 |
| sam BM25 (obcięcie do 5 znaków) | 0,73 | 0,86 | 0,68 | 0,66 | 0,34 | 9 |
| hybryda RRF (k=60) | 0,84 | 0,93 | 0,77 | 0,74 | 0,43 | 3 |
| hybryda + rerank top-20 + limit 1 na sekcję | 0,88 | 0,93 | 0,81 | 0,79 | 0,22 | 3 |

Skrypt: `experiments/03_summary.py`.

Recall@5 – czyli czy właściwa sekcja jest wśród pięciu fragmentów wkładanych do promptu – rośnie z 0,72 na 0,88, a liczba pytań bez trafienia spada z dziewięciu na trzy. Licząc regułą z rozdziału 1: wynik zmieniło dwanaście pytań na czterdzieści dziewięć, jedenaście na plus i jedno na minus, więc nie jest to różnica do wytłumaczenia losem. Pytania porównawcze, te, które w połowie rozdziału nie drgnęły, kończą z recall 0,77.

Z dziewięciu porażek rozdziału 1 naprawionych jest sześć: pytanie o pole blokujące pojedynczego użytkownika (`metadata.user_id`), o edycję kontekstu z otwarcia tego rozdziału, o limit rozmiaru pliku w transkrypcji, o podmianę modelu embeddingowego, o bramkę jakości i o walidację SQL-a. Zostają trzy i wszystkie są parafrazą bez wspólnych słów. „Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?” nie ma ani jednego wspólnego terminu z sekcją „Trening a inferencja” rozdziału 2 tomu 1, a ani hybryda, ani cross-enkoder nie wymyślą słowa, którego w pytaniu nie ma. Tym zajmuje się przekształcanie zapytania z rozdziału 4.

Jest też jedna regresja. Pytanie „Qdrant czy pgvector do produkcji średniej skali?” miało w baseline'ie połowę trafnych sekcji, a teraz nie ma żadnej: ramię leksykalne wciąga fragmenty, w których obie nazwy stoją obok siebie w tabeli porównawczej, i wypycha sekcję mówiącą o tym samym własnymi słowami. To cena hybrydy, płacona raz na czterdzieści dziewięć pytań.

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

Sygnatura jest ta sama, której oczekuje `ragbook.evaluate.evaluate`: `(pytanie, k) -> list[Chunk]`. Rozdział 4 podstawia ten obiekt pod swoje przekształcenia zapytania bez przejściówki, a rozdział 8 owija go w cache i trace.

Trzy decyzje warto umieć obronić. **Reranker `mmarco-mMiniLMv2`, nie `bge-reranker-v2-m3`**, mimo że bge jest lepszy – bo kosztuje dwadzieścia razy więcej czasu i pięć razy więcej pamięci; jeżeli masz GPU z zapasem VRAM, wybierz odwrotnie. **Pula 20, nie 50**, bo pięćdziesiątka nie poprawiła ani jednej metryki mMiniLM. **Limit 1 na sekcję**, mimo że psuje precision@5 liczoną po fragmentach. I jedna rzecz, której ten rozdział nie robi: nie dotyka chunkingu. Efekty technik z rozdziału 2 powinny się z tymi sumować – ale „powinny” to nie pomiar, dlatego złożenie jednego z drugim robi rozdział 4.

## Podsumowanie

- Tanie stemowanie przez obcięcie tokenu do pięciu znaków podnosi recall@5 samego BM25 z 0,62 na 0,73; brak normalizacji fleksji jest w polskim korpusie najdroższym pojedynczym błędem w tym rozdziale.
- Sam BM25 bije model gęsty na pytaniach faktograficznych i proceduralnych, a przegrywa na porównawczych: rankingi mają rozłączne tryby awarii i dlatego opłaca się je łączyć.
- Hybryda leksykalno-gęsta złączona RRF podnosi recall@5 z 0,72 na 0,84 i zmniejsza liczbę pytań bez trafienia z dziewięciu na trzy, kosztem pięciu milisekund na zapytanie.
- RRF jest domyślnym wyborem nie dlatego, że daje najlepszy wynik (suma ważona przy wadze 0,5 daje taki sam), tylko dlatego, że jest płaski: od `k` równego 10 wzwyż wynik się nie zmienia, a waga wymaga strojenia na zestawie, którego na starcie nie masz.
- `fastembed` i wektory rzadkie w Qdrancie to właściwa architektura produkcyjna, ale `Qdrant/bm25` nie zna polskiego stemmera i ramię leksykalne traci na tym 0,13 recall.
- Reranking cross-enkoderem na dwudziestu kandydatach daje +0,13 nad samym wyszukiwaniem gęstym i +0,02 nad hybrydą; obie techniki naprawiają w dużej mierze te same pytania, więc ich zyski się nie sumują.
- Pięćdziesiąt kandydatów zamiast dwudziestu podwaja latencję i nie poprawia żadnej metryki na mMiniLM; `bge-reranker-v2-m3` jest lepszy o 0,03–0,06 recall, ale dwadzieścia razy wolniejszy nawet na GPU.
- Wynik cross-enkodera, w odróżnieniu od kosinusa e5, częściowo separuje pytania bez odpowiedzi: próg −2 odrzuca cztery z siedmiu negatywów, nie tracąc ani jednego pozytywu.
- Limit jednego fragmentu na sekcję podnosi recall pytań porównawczych z 0,68 na 0,77, a MMR w obu wariantach nie daje nic albo szkodzi, bo wąski rozrzut kosinusów E5 nie niesie użytecznej miary redundancji.

## Co dalej

Rozdział 4 zajmuje się ostatnią kategorią porażek z rozdziału 1, tą, której ten rozdział nie ruszył: pytaniami sformułowanymi słowami, których w dokumencie nie ma. Zobaczysz query rewriting, multi-query, HyDE, step-back i dekompozycję pytań złożonych, filtrowanie po metadanych oraz routing – i tam też złoży się chunking z rozdziału 2 z hybrydą i rerankingiem w jeden pomiar. Zanim tam przejdziesz, uruchom `experiments/03_bm25.py` i przeczytaj listę pytań, na których BM25 wygrywa z modelem gęstym, a potem tę, na których przegrywa. Kwadrans, po którym przestaniesz traktować „hybryda jest lepsza” jako regułę, a zaczniesz jako hipotezę do sprawdzenia na swoim korpusie.

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
