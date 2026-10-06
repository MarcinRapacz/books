# Rozdział 1. Projekt, korpus, baseline i pomiar

> **Cel rozdziału:** zbudować naiwny system RAG na prawdziwym korpusie, zamrozić zestaw 56 pytań, którym wszystkie kolejne rozdziały będą mierzyć swoje techniki, i odczytać z pierwszego pomiaru listę rzeczy do naprawienia.
>
> **Kod:** `ragbook/corpus.py`, `ragbook/embed.py`, `ragbook/store.py`, `ragbook/evaluate.py`, `ragbook/generate.py`, `experiments/01_*.py`. **Pakiety poza fundamentem:** brak.

Tom 1 kończył rozdział o RAG-u zdaniem, że pięć pytań z oznaczonymi dokumentami jest nieporównywalnie lepsze niż zero. To właściwy próg wejścia, ale pięć pytań nie powie Ci, czy zmiana chunkera poprawiła system o 0,04, czy pogorszyła go o 0,02. A dokładnie takie różnice będziemy tu rozstrzygać przez osiem rozdziałów.

Weź jedno pytanie z zestawu, który za chwilę zbudujemy: „Jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi?”. Naiwny system z tego rozdziału zwraca pięć fragmentów, z czego cztery z właściwego rozdziału o kontekście – i ani jeden nie zawiera odpowiedzi, czyli nazwy `clear_tool_uses_20250919`. Wyszukiwanie trafiło temat i zgubiło ciąg znaków, który zwykłym `LIKE` znalazłbyś od razu.

Takich pytań jest dziewięć i każde pokazuje inną usterkę. Baseline zbudowany w tym rozdziale – stałe okno 128 tokenów, `multilingual-e5-small`, Qdrant, top-5 – ma recall@5 równy 0,72: dla mniej więcej trzech pytań na cztery właściwa sekcja jest wśród pięciu fragmentów wkładanych do promptu. Odpowiedź prawie zawsze jest przy tym gdzieś w dwudziestce, tylko nie na górze. To diagnoza, nie porażka, i ona wyznacza kolejność rozdziałów 2, 3 i 4.

Reszta rozdziału pokazuje, jak dojść do takiego zdania i mieć prawo je wypowiedzieć: korpus, zamrożony zestaw pytań, metryki, pomiar, analiza błędów. Snippety uruchamiasz z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/01_baseline.py`.

## Prototyp i produkcja: gdzie to pęka

Prototyp RAG powstaje w godzinę i prawie zawsze działa. Bierzesz dwadzieścia dokumentów, tniesz je po akapitach, liczysz embeddingi, wkładasz do bazy, zadajesz trzy pytania, na które znasz odpowiedź, i dostajesz trzy dobre odpowiedzi. Produkcja różni się nie skalą, tylko tym, że pytania zadaje ktoś inny niż autor systemu – a ta jedna zmiana odsłania sześć trybów awarii, których w prototypie nie da się zobaczyć.

**Pytanie sformułowane inaczej niż dokument.** Autor prototypu pyta słowami z dokumentacji, bo ją czytał. Użytkownik pyta „ile kosztuje trzymanie całej dokumentacji w prompcie”, podczas gdy w tekście stoi „koszt tokenów wejściowych rośnie liniowo z długością wejścia”. Wyszukiwanie gęste radzi sobie z tym nieźle, ale nie zawsze – i nie ma jak się dowiedzieć, kiedy nie, dopóki nie masz zestawu takich pytań. **Identyfikatory i liczby**: `max_seq_length`, `clear_tool_uses_20250919`, HTTP 429, 512 tokenów, 25 MB. Dla modelu embeddingowego to ciągi bez sąsiedztwa semantycznego, a jednocześnie dokładnie to, czego szuka się w dokumentacji technicznej; wyszukiwanie leksykalne trafia je bezbłędnie, gęste gubi.

**Odpowiedź w środku długiej sekcji.** Sekcja o ośmiu tysiącach tokenów po pocięciu na okna po 128 daje dziewięćdziesiąt fragmentów, z których jeden zawiera odpowiedź, a osiemdziesiąt dziewięć jest o tym samym temacie, tylko nie o tym; rodzeństwo wypycha się z czołówki nawzajem. **Pytania wielosekcyjne**: „Wziąć model przez API czy postawić własny?” ma odpowiedź rozrzuconą po dwóch sekcjach, a wyszukiwanie po podobieństwie ma silną skłonność do zwracania pięciu fragmentów z jednego miejsca.

**Pytania, na które odpowiedzi nie ma.** Prototyp nigdy ich nie dostaje, produkcja dostaje je codziennie. System, który na pytanie o Kubernetesa zwraca pięć fragmentów o Qdrancie z wynikiem 0,86, i model, który z nich lepi odpowiedź, to najkosztowniejsza usterka w całym potoku – bo wygląda jak poprawne działanie. I wreszcie **cicha degradacja**: ktoś dopisuje dokument, ktoś zmienia model embeddingowy, ktoś podnosi `k` z 4 do 6, a bez pomiaru każda z tych zmian jest niewidoczna do momentu, w którym ktoś się poskarży.

Lista jest nudna, ale zauważ, że każdą pozycję da się zamienić na pytanie w zestawie testowym. To jest cały pomysł na ten rozdział.

## Projekt i korpus

Projektem przewodnim tomu jest asystent odpowiadający na pytania po dokumentacji technicznej. Korpusem jest tom 1 tej serii: czternaście plików Markdown w `books/ai-engineer/chapters/`. Gdy dalej pada „sekcja «Dobre praktyki» rozdziału 11”, chodzi o rozdział tomu 1 – to on jest korpusem.

Powody są praktyczne. Masz ten tekst pod ręką, więc sprawdzisz każdą odpowiedź systemu, a oznaczanie trafności nie jest zgadywaniem. Jest po polsku, więc problemy z tokenizacją są prawdziwe, a nie hipotetyczne. I ma strukturę prawdziwej dokumentacji: nagłówki, bloki kodu, tabele, powtarzające się sekcje „Podsumowanie” i „Źródła”.

Zanim cokolwiek zaindeksujesz, policz korpus – zajmuje to pięć minut i oszczędza dwa dni. Niżej cztery rozdziały z krańców rozkładu i suma; pełną siatkę czternastu wierszy wypisuje skrypt.

| Rozdz. | Tytuł | Sekcje | Słowa | Tokeny e5 | Udział kodu |
|---|---|---|---|---|---|
| 1 | Kim jest AI Engineer | 8 | 2640 | 4649 | 0% |
| 3 | Prompt engineering | 7 | 5424 | 12500 | 31% |
| 8 | RAG | 9 | 5995 | 14672 | 31% |
| 14 | Narzędzia AI do kodowania | 7 | 2508 | 5018 | 5% |
| **razem (14 rozdz.)** | | **131** | **64 193** | **146 791** | **24,5%** |

Skrypt: `experiments/01_corpus_stats.py`.

**2,29 tokena na słowo.** Polszczyzna kosztuje w tokenizerze mniej więcej dwa razy tyle co angielski (tom 1, rozdział 2), więc każde oszacowanie długości chunku zrobione „na oko po znakach” będzie zaniżone.

**24,5 procent znaków korpusu to bloki kodu.** Co czwarty znak jest identyfikatorem, wcięciem albo nawiasem, więc chunker tnący co 128 tokenów bez patrzenia na strukturę będzie regularnie przecinał funkcje w pół.

Sekcji jest **131** i są skrajnie nierówne: mediana ma 667 tokenów, a najdłuższa, „Pipeline krok po kroku” z rozdziału 8, aż 8589. Jeżeli ktoś zapyta o coś, co stoi w jej środku, system musi wyłowić jeden fragment spośród dziewięćdziesięciu z tego samego miejsca.

Osobno warto odnotować sekcje powtarzalne: każdy rozdział tomu 1 kończy się „Podsumowaniem”, „Co dalej” i „Źródłami”. Te 40 sekcji granicznych daje dziesięć procent indeksu, a napisane są gęsto, w punktach, dokładnie tymi słowami, których użyje pytający – i dlatego wyszukiwanie je uwielbia. Do polityki trafności wrócimy za chwilę.

## Fundament kodu

Cały tom stoi na pakiecie `ragbook` i czterech modułach: `corpus.py` tnie korpus na fragmenty, `embed.py` liczy embeddingi z cache'em, `store.py` trzyma indeks, `evaluate.py` liczy metryki.

Najważniejsza decyzja siedzi w `corpus.py`. Jednostką trafności w całym tomie jest **sekcja**, czyli jeden nagłówek `##` jednego rozdziału, a nie chunk – dzięki temu zestaw ewaluacyjny nie zależy od strategii chunkowania i rozdział 2 może zmieniać chunker bez przepisywania etykiet.

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

Dwie decyzje w `load_sections` warto zobaczyć od razu. Nagłówki wewnątrz bloków kodu są ignorowane – bez tego komentarz `## Conventions` z przykładu `CLAUDE.md` w rozdziale 14 utworzyłby fałszywą sekcję. I nagłówki `###` **nie** dzielą sekcji, więc cała „Anatomia promptu” z rozdziału 3 jest jedną sekcją o 4030 tokenach – zestaw ma być gruboziarnisty i stabilny.

`embed.py` opakowuje `intfloat/multilingual-e5-small` (384 wymiary, `max_seq_length` równe 512) i sam dokleja prefiksy `query: ` albo `passage: `, których karta modelu wymaga pod rygorem spadku jakości (stan na wrzesień 2026). Cache na dysku jest tu warunkiem sensownej pracy, a nie optymalizacją: policzenie 1550 wektorów zajmuje na CPU 158 sekund, wczytanie ich z `.cache/` – pół sekundy.

`store.py` to indeks gęsty na Qdrancie w trybie `:memory:`; `DenseIndex.search(query, k, query_filter)` zwraca obiekty `Chunk` z podobieństwem w `meta["score"]`, więc reszta kodu nie musi wiedzieć, jaka baza siedzi pod spodem. Pod maską woła `client.query_points(...)`, który obsługuje też wektory rzadkie i hybrydę z rozdziału 3.

`evaluate.py` przyjmuje dowolny retriever o sygnaturze `(question, k) -> list[Chunk]` – indeks gęsty, hybrydę, potok z rerankingiem – i obok średnich zwraca listę `per_question` z recallem, pozycją pierwszego trafienia i pięcioma zwróconymi sekcjami. Ta lista to jest cała analiza błędów; nie loguj jej do pliku, tylko ją czytaj.

## Baseline end-to-end

Baseline ma być naiwny. Nie chodzi o to, żeby był dobry, tylko żeby był kompletny i żeby każdy kolejny rozdział miał od czego odjąć. Cztery kroki, pierwsze trzy lokalne.

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

Cięcie po 128 tokenach z zakładką 32 daje **1550 chunków**, średnio 11,8 na sekcję. Okno jest z premedytacją krótsze niż limit modelu – e5-small przyjmuje 512 tokenów – bo chcemy zobaczyć, ile kosztuje zły chunking, zanim rozdział 2 zacznie go naprawiać.

W wyniku widać już trzy rzeczy, o których będzie ten tom. Po pierwsze, wszystkie pięć trafień pochodzi z rozdziału 6, w tym dwa razy z tej samej sekcji: wyszukiwanie po podobieństwie skupia się, zamiast pokrywać. Po drugie, na pierwszym miejscu jest „Podsumowanie”, bo punktowana lista napisana terminami z pytania wygrywa z akapitem, który te terminy tłumaczy. Tutaj akurat niesie pełną odpowiedź, ale nie zawsze tak jest i za chwilę zamienimy to w regułę.

Po trzecie, cała piątka mieści się w przedziale dwóch setnych podobieństwa. To nie usterka: karta modelu E5 mówi wprost, że kosinusy z tej rodziny układają się mniej więcej od 0,7 do 1,0 i liczy się kolejność, nie wartość bezwzględna (stan na wrzesień 2026). Wniosek: **nie da się na tym modelu postawić progu odcięcia**.

Czwarty krok to prompt: fragmenty na górze w tagach XML, pytanie na dole, instrukcja „tylko na podstawie dokumentów” i zdefiniowana odpowiedź awaryjna – układ z tomu 1, rozdział 3. Żyje w `ragbook/generate.py`, bo jako jedyny w potoku wymaga klucza API i kosztuje pieniądze.

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

Prompt zbudowany z pięciu chunków po 128 tokenów ma 889 tokenów tokenizerem e5; dokładną liczbę dla modelu generującego policzysz endpointem `count_tokens` (tom 1, rozdział 2). To punkt odniesienia dla rozdziału 8: przy `k` równym 5 płacisz za rząd tysiąca tokenów wejścia na zapytanie, przy `k` równym 20 – cztery razy tyle. Nie masz klucza API? Trzy pierwsze kroki uruchomisz lokalnie i to na nich mierzymy wszystko aż do rozdziału 6.

## Jak zbudować golden set

To najdroższa i najważniejsza rzecz w tym rozdziale. Zestaw żyje w `code/data/golden.jsonl`, jedno pytanie na linię:

```json
{"id": "q002",
 "question": "Od jakiej długości promptu Claude Opus 5 w ogóle zapisze prefiks do cache?",
 "type": "factual",
 "relevant": [{"chapter": 3, "section": "Interakcja z modelem"}],
 "answer": "Od 512 tokenów. Krótsze prompty nie są cache'owane i nie dostajesz o tym żadnego błędu."}
```

Pole `relevant` wskazuje sekcje, nie chunki: chunk jest trafny, jeżeli należy do trafnej sekcji. Pole `answer` to wzorcowa odpowiedź w jednym–dwóch zdaniach; retrieval jej nie używa, ale rozdział 6 oceni nią wierność generacji.

### Rozkład, który ma sens

Zestaw ma 56 pytań i cztery typy. `factual` to jeden fakt w jednym miejscu (26 pytań). `procedural` to „jak coś zrobić”, czyli procedura rozłożona na kilka zdań, czasem na dwie sekcje (12). `comparative` to porównanie, prawie zawsze z trafnością w dwóch sekcjach z różnych rozdziałów (11). `negative` to pytania bez odpowiedzi w korpusie, z pustą listą `relevant` (7). Razem 64 etykiety, w tym 15 pytań wielosekcyjnych, i pokrycie wszystkich czternastu rozdziałów.

Proporcje nie są przypadkowe. Pytania faktograficzne są najłatwiejsze i dla oznaczającego, i dla systemu, więc gdyby stanowiły osiemdziesiąt procent zestawu, każdy pomiar wyglądałby optymistycznie. Porównawcze są najtrudniejsze, bo wymagają dwóch różnych sekcji w top-5. Negatywne nie wchodzą do metryk retrievalu; są po to, żeby rozdział 6 miał na czym zmierzyć odmowę.

### Pułapka numer jeden: pytania za łatwe

Jeżeli zapytasz o coś słowami, którymi to napisano, znajdziesz to zawsze. Taki zestaw daje recall@5 bliski jedności i jest bezużyteczny, bo nie ma w nim miejsca na poprawę. Sześć chwytów, które robią tu robotę:

- **Parafraza bez pokrycia leksykalnego.** „Ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślę?” zamiast „ile kosztują tokeny wyjściowe”.
- **Identyfikatory i nazwy parametrów.** Odpowiedzią na „jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi” jest `clear_tool_uses_20250919`, ciąg, który w przestrzeni semantycznej nie leży nigdzie.
- **Liczby z tabel.** „Ile kosztuje milion tokenów wejściowych i wyjściowych `gpt-6-astra`?” – odpowiedź jest komórką tabeli, a tabela po pocięciu na okna traci nagłówek.
- **Język potoczny.** „Dlaczego jedno `print()` w kodzie narzędzia potrafi zerwać połączenie z serwerem?” zamiast „jak działa ramkowanie komunikatów w transporcie stdio”.
- **Odpowiedź w środku długiej sekcji.** Próg kompaktowania stoi w połowie sekcji o 5101 tokenach, wśród pięćdziesięciu dwóch innych fragmentów o kontekście.
- **Pytania wielosekcyjne.** „Qdrant czy pgvector do produkcji średniej skali?” wymaga naraz dwóch sekcji rozdziału 7.

### Pułapka numer dwa: polityka trafności

Każdy rozdział tomu 1 kończy się „Podsumowaniem” w ośmiu punktach i często jeden z nich zawiera pełną odpowiedź na pytanie, na które właściwa sekcja odpowiada trzema akapitami. Trzeba zdecydować, czy to jest trafienie – i zdecydować raz, bo niekonsekwencja psuje metrykę bardziej niż dziesięć źle dobranych pytań.

Polityka tego tomu brzmi tak. **„Co dalej” i „Źródła” nie są trafne nigdy** – pierwsze zapowiada następny rozdział, drugie jest listą URL-i. **„Podsumowanie” jest trafne tylko wtedy, gdy zawiera pełną odpowiedź**, taką, którą dałoby się pokazać użytkownikowi bez dopisywania czegokolwiek; w całym zestawie taki przypadek jest jeden. **Sekcja wstępna** (tekst przed pierwszym `##`, w danych pusty string) jest traktowana jak każda inna i bywa trafna – „lethal trifecta” z rozdziału 11 stoi właśnie tam.

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

Sprawdzenie, że każda para (rozdział, sekcja) istnieje w `load_sections()`, jest tu najważniejszą linijką: nagłówki pisze się ręcznie, a literówka nie wywala niczego – tworzy pytanie, którego nigdy nie da się trafić, i zaniża recall na zawsze. Walidator kończy się kodem 1, więc wpina się w CI jak bramka jakości z tomu 1, rozdział 12.

### Pułapka numer trzy: pytania negatywne

Pytanie negatywne ma brzmieć jak pytanie z tej dziedziny, ale nie mieć odpowiedzi w korpusie. „Jak ustawić parametr `ef_search` w Elasticsearchu przy indeksie kNN?” jest dobre, bo `ef_search`, kNN i indeksy w korpusie są – tylko w kontekście Qdranta, FAISS-a i pgvectora. „Jak skonfigurować replikację strumieniową PostgreSQL?” jest dobre, bo PostgreSQL zajmuje w rozdziale 7 sporo miejsca, ale wyłącznie jako host dla pgvectora. Złe pytanie negatywne to takie, które nie przypomina niczego z korpusu („jaki jest przepis na żurek”): odrzuci je każdy system i nie zmierzysz nim nic.

### Ile pytań wystarczy

Pięćdziesiąt sześć, i to nie jest liczba z sufitu. Od dołu ogranicza ją szum: przy `n` pytaniach i recall na poziomie `p` błąd standardowy średniej to mniej więcej pierwiastek z `p(1-p)/n`, czyli przy 49 pytaniach i recall 0,72 około 0,06. Różnica 0,05 między wariantami mieści się więc w granicach szumu – za chwilę pokażę, dlaczego w porównaniach parami jest lepiej, niż wynika z tej liczby. Od góry ogranicza ją koszt: każde pytanie to przeczytanie sekcji i upewnienie się, że odpowiedź tam naprawdę jest, czyli jakieś pięć minut.

Z grubsza: dwadzieścia pytań pozwala zauważyć zmianę o 0,15, pięćdziesiąt – o 0,07, dwieście – o 0,035. Powyżej dwustu błąd oznaczania rośnie szybciej niż precyzja pomiaru. Rozbicie po typach wymaga co najmniej dziesięciu pytań w grupie, stąd 26/12/11/7.

I jedna zasada organizacyjna: **zestaw powstaje raz i zostaje zamrożony**. Rozdziały 2, 3 i 4 mierzą się na tym samym pliku i nie wolno im go modyfikować; rozdział, który potrzebuje pytań specjalnych, zakłada osobny plik obok (tak zrobi rozdział 5 z pytaniami o wartości w tabelach). Powód jest ten sam, co przy wersjonowaniu zbiorów ewaluacyjnych w tomie 1: zmiana zestawu zmienia znaczenie metryki.

## Metryki

Mierzymy retrieval osobno od generacji i to pierwsza decyzja metodologiczna tego tomu. Jeżeli mierzysz tylko końcową odpowiedź, to przy błędzie nie wiesz, czy model źle rozumował, czy nie dostał tego, co trzeba. Metryki retrievalu liczą się za to bez wołania modelu, w kilka milisekund na pytanie. Najważniejsze jednak jest to, że **recall retrievalu jest sufitem jakości całego systemu**: czego wyszukiwanie nie znajdzie, tego generacja nie napisze, a jeśli napisze, to znaczy, że zmyśliła.

Trafność jest u nas binarna i liczona po sekcjach. Dla pytania $q$ niech $S_q$ będzie zbiorem sekcji oznaczonych jako trafne, a $R_q^{(k)}$ – zbiorem sekcji, z których pochodzą chunki zwrócone na pierwszych $k$ pozycjach.

Pierwsza metryka pyta o jedno: jaka część potrzebnych sekcji znalazła się w zwróconej `k`-tce. Dla pytania z jedną trafną sekcją wychodzi zero albo jeden, dla porównawczego z dwiema – zero, pół albo jeden, a kolejność nie ma znaczenia.

$$\mathrm{recall@}k = \frac{1}{|Q|}\sum_{q \in Q} \frac{\left|S_q \cap R_q^{(k)}\right|}{|S_q|}$$

Standardowe `k` to 5 (tyle fragmentów idzie do promptu) i 20 (tylu kandydatów zbiera się przed rerankingiem z rozdziału 3).

Druga metryka dokłada to, czego recall nie widzi: jak głęboko trzeba sięgnąć po pierwsze trafienie. Miejsce pierwsze daje 1, drugie 0,5, piąte 0,2, a brak trafienia w `k`-tce liczymy jako 0.

$$\mathrm{MRR@}k = \frac{1}{|Q|}\sum_{q \in Q} \frac{1}{\mathrm{rank}_q}, \qquad \mathrm{rank}_q = \min\{\, i \le k : \mathrm{sec}(c_i) \in S_q \,\}$$

MRR (mean reciprocal rank) jest przez to czuły na reranking i ślepy na to, czy druga trafna sekcja też się znalazła.

Trzecia jest kompromisem: liczy się i to, ile trafnych sekcji wpadło, i jak wysoko stoją. Każde trafienie wnosi zysk $g_i$ (u nas 1 za trafienie, 0 za pudło) tym mniejszy, im niżej leży, a sumę dzielimy przez wynik idealnego uszeregowania.

$$\mathrm{DCG@}k = \sum_{i=1}^{k} \frac{g_i}{\log_2(i+1)}, \qquad \mathrm{nDCG@}k = \frac{\mathrm{DCG@}k}{\mathrm{IDCG@}k}$$

Dzięki normalizacji pytanie z jedną trafną sekcją i pytanie z dwiema są porównywalne, czego surowe DCG nie daje. nDCG (normalised discounted cumulative gain) warto raportować jako główną metrykę przy pytaniach wielosekcyjnych – i dokładnie tam rozjeżdża się z MRR.

Czwarta liczba nie jest metryką, tylko licznikiem: **ile pytań nie ma w top-`k` ani jednego trafienia** (`evaluate` zwraca go jako `misses@5`). Średnia zawsze coś ukrywa, a lista porażek prowadzi wprost do konkretnych usterek.

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

Rozbicie po typach potwierdza, że zestaw robi to, po co powstał. Faktograficzne wypadają najlepiej: w dwudziestce właściwa sekcja jest dla każdego z nich. Proceduralne są najsłabsze, bo ich odpowiedzią jest procedura na kilka akapitów, a okno 128-tokenowe łapie z niej pojedynczy krok bez kontekstu.

Porównawcze zachowują się najciekawiej: mają naraz najwyższy MRR i niski recall. System praktycznie zawsze trafia **jedną** z dwóch potrzebnych sekcji, i to wysoko, ale drugiej nie dokłada. Dziewięć pytań ma recall@5 równy dokładnie 0,5 i wszystkie dziewięć jest wielosekcyjnych.

Dwie liczby spoza tabel. **Precision@5 wynosi 0,38**: spośród 245 fragmentów wkładanych do promptów trafnych jest 94, a reszta to tokeny, za które płacisz i które model musi przeczytać, żeby je zignorować. I druga: **sekcje graniczne zajmują 8 procent slotów w top-5**, mniej więcej tyle, ile wynosi ich udział w indeksie – nie są więc przeciążone, ale skoro prawie nigdy nie niosą odpowiedzi, każdy taki slot jest zmarnowany.

Zostają pytania negatywne, których metryki retrievalu nie dotyczą, a które mówią najwięcej o tym, czego ten baseline nie potrafi.

```text
top-1 score: negatives min 0.845 max 0.875 mean 0.860
top-1 score: positives min 0.841 max 0.928 mean 0.882
7 of 7 negatives score above the weakest positive -> no usable cut-off
```

Każde z siedmiu pytań bez odpowiedzi w korpusie dostaje na pierwszym miejscu fragment z wynikiem wyższym niż najsłabsze prawdziwe trafienie; rozkłady zachodzą na siebie całkowicie. Progu odcięcia po `score` nie da się więc ustawić ani wysoko, ani nisko, ani po kalibracji. Odmowa musi być decyzją modelu w kroku generacji, a nie regułą w kodzie retrievalu: rozdział 6 zbuduje ją na zdefiniowanej odpowiedzi awaryjnej, a rozdział 4 sprawdzi, czy da się ją podeprzeć klasyfikacją intencji.

## Analiza błędów

Dziewięć pytań nie ma w top-5 ani jednego trafienia. Osiem z nich ma trafną sekcję w top-20, więc kandydat był pod ręką i przegrał ranking. Rozkładają się na cztery kategorie, a każda jest zapowiedzią któregoś z kolejnych rozdziałów.

**Kategoria 1: nazwa własna, której model gęsty nie zna.** Pytanie z początku rozdziału, o nazwę edycji kontekstu kasującej stare wyniki narzędzi (q022), dostaje cztery fragmenty z właściwego rozdziału o kontekście, ale ani jednego z „Technik zarządzania kontekstem”, gdzie ta nazwa stoi. Wyszukiwanie znalazło temat i przegapiło ciąg znaków, choć jest on w korpusie dokładnie raz. Podręcznikowy przypadek na hybrydę z BM25 (rozdział 3).

**Kategoria 2: konkret utopiony w długiej sekcji.** Pytanie o limit rozmiaru pliku w endpoincie transkrypcji (q023) zwraca sąsiadów właściwej sekcji „Audio”; limit stoi w jej środku, w jednym zdaniu, pośród opisów trzech modeli. Podobnie pytanie o pole, którym dostawca zablokuje jednego nadużywającego użytkownika zamiast całego klucza: odpowiedź siedzi w „Dobrych praktykach” rozdziału 11, sekcji o 3736 tokenach, która produkuje kilkadziesiąt konkurujących fragmentów. Na to odpowiada rozdział 2: contextual chunk headers i parent-child.

**Kategoria 3: parafraza bez wspólnych słów.** Pytanie, ile razy drożej wychodzi to, co model napisze, od tego, co mu wyślemy (q007), trafia w trzy sekcje ogólnie o kosztach; właściwa, „Trening a inferencja”, nie ma w tekście ani słowa „drożej”, ani „napisze”. Pytanie o trzy elementy, które razem czynią atak na agenta groźnym, ląduje w „Prompt injection” rozdziału 11, czyli o jedną sekcję za daleko, bo „lethal trifecta” stoi w jego wstępie. Cztery takie przypadki to zadanie dla przekształceń zapytania z rozdziału 4: query rewriting, HyDE, step-back.

**Kategoria 4: dwie sekcje, jeden temat.** Pytanie o podmianę modelu liczącego wektory w działającym systemie (q032) wymaga naraz rozdziału 7 (nowa kolekcja, przełączenie aliasu) i rozdziału 6 (nie mieszaj modeli w jednym indeksie), a baseline zwraca pięć fragmentów rozsianych po czterech rozdziałach. Dochodzi do tego dziewięć pytań, które trafiły tylko jedną z dwóch potrzebnych sekcji. Tu potrzebna jest dywersyfikacja wyników i multi-query (rozdziały 3 i 4).

Jeden przypadek wypada poza te kategorie i jako jedyny nie ma trafienia nawet w top-20: jak sprawdzić, czy wygenerowane przez model zapytanie można bezpiecznie puścić na bazę (q039). Odpowiedź – walidacja SQL-a na drzewie składniowym przez `sqlglot` – jest w „Dobrych praktykach” rozdziału 11, w kilku zdaniach prozy i w dużym bloku kodu. Fragmenty tego bloku są ciągami nazw funkcji i wyjątków, które nie leżą blisko żadnego pytania po polsku. To zapowiedź rozdziału 5: kod w dokumentacji wymaga innego traktowania niż proza.

Zauważ, czego na tej liście **nie** ma: ani jednej porażki, za którą odpowiadałby sam Qdrant. Przy 1550 wektorach indeks jest dokładny co do ostatniego bitu, a `ef`, `nprobe` i kwantyzacja z tomu 1, rozdział 7 zaczynają mieć znaczenie o dwa rzędy wielkości dalej. Cała strata siedzi w chunkingu, w reprezentacji i w sformułowaniu zapytania.

## Pętla: zmiana, pomiar, decyzja

Reszta tomu jest jedną pętlą powtarzaną kilkadziesiąt razy: zmień jedną rzecz, zmierz na zamrożonym zestawie tymi samymi metrykami i tym samym `k`, zdecyduj, czy zostaje. Trzy reguły.

**Jedna zmiana naraz.** Jeżeli podmienisz jednocześnie chunker i model embeddingowy, a wynik urośnie, nie wiesz, który z nich pomógł ani czy drugi nie zaszkodził.

**Raportuj rozbicie, nie tylko średnią.** Zmiana, która podnosi recall@5 na pytaniach faktograficznych, a obniża go na porównawczych, w średniej wygląda na wygraną. Czy nią jest, zależy od tego, jakie pytania zadają Twoi użytkownicy – to decyzja produktowa, a nie efekt uboczny uśredniania.

**Znaj szerokość swojego szumu.** Tu najłatwiej się oszukać.

```text
recall@5 = 0.724, sd per question 0.396, standard error 0.057
95% bootstrap CI: [0.612, 0.827]  (width 0.214)
```

Skrypt: `experiments/01_baseline.py`.

Przedział ufności dla recall@5 ma na czterdziestu dziewięciu pytaniach szerokość 0,21 – nie wiesz, czy prawdziwa wartość baseline'u to 0,61, czy 0,83. Byłby to wyrok na cały pomiar, gdybyśmy porównywali dwa systemy mierzone na różnych zestawach. My porównujemy **ten sam zestaw pytań przed zmianą i po zmianie**, a wtedy liczy się nie średnia, tylko rozkład różnic per pytanie – znacznie węższy, bo większość pytań zachowuje się w obu wariantach tak samo.

Stąd reguła na kolejne rozdziały: **patrz, ile pytań zmieniło wynik, a nie o ile zmieniła się średnia**. Różnica 0,04 na 49 pytaniach to mniej więcej dwa pytania, które zaczęły działać. Statystyką tego nie rozstrzygniesz – rozstrzygniesz, czytając te dwa pytania i sprawdzając, czy poprawa ma mechanizm, który potrafisz nazwać. Jeśli tak, zmiana zostaje; jeśli nie umiesz powiedzieć dlaczego, to szum, choćby średnia urosła. Zmiana rzędu ośmiu–dziesięciu pytań jest już różnicą, której nie da się wytłumaczyć losem.

I rzecz najmniej techniczna: zestaw ewaluacyjny nie jest prawdą o Twoim systemie, tylko o pięćdziesięciu sześciu pytaniach, które ktoś wybrał. Optymalizowanie pod niego bez końca daje system rozwiązujący te pięćdziesiąt sześć pytań i żadne inne. Antidotum opisał tom 1, rozdział 12: prawdziwe zapytania z produkcji wracają do zestawu. My tego luksusu nie mamy, więc zamrażamy plik i pamiętamy o jego ograniczeniu.

## Podsumowanie

- Jednostką trafności w całym tomie jest sekcja tomu 1 (numer rozdziału plus dokładny nagłówek `##`), a nie chunk – dzięki temu zestaw przetrwa każdą zmianę chunkera w rozdziałach 2–5.
- Korpus ma 131 sekcji i 146 791 tokenów e5, po 2,29 tokena na słowo, a 24,5 procent jego znaków to bloki kodu. Mediana sekcji ma 667 tokenów, najdłuższa 8589.
- Baseline (okno 128/32, `multilingual-e5-small`, Qdrant, top-5) daje 1550 chunków i recall@5 równy 0,72 przy 9 pytaniach bez trafienia w piątce; pozostałe metryki stoją w tabelach sekcji „Pierwszy pomiar”.
- Zestaw 56 pytań (26 faktograficznych, 12 proceduralnych, 11 porównawczych, 7 negatywnych) pokrywa wszystkie 14 rozdziałów i celowo zawiera parafrazy, identyfikatory i liczby z tabel, żeby baseline nie osiągnął na nim sufitu.
- Polityka trafności musi być spisana i wymuszona kodem: „Co dalej” i „Źródła” nigdy nie są trafne, „Podsumowanie” tylko gdy niesie pełną odpowiedź, a walidator pilnuje, że każda para (rozdział, sekcja) istnieje w `load_sections()`.
- Retrieval mierzymy osobno od generacji: recall jest sufitem jakości całego systemu i wskazuje winnego, gdy odpowiedź jest zła.
- Kosinusów z rodziny E5 nie da się użyć jako progu odcięcia: każde pytanie negatywne dostaje na pierwszym miejscu wynik wyższy niż najsłabsze prawdziwe trafienie, więc odmowa musi powstać w kroku generacji.
- Dziewięć porażek rozkłada się na cztery kategorie: nazwa własna zgubiona przez model gęsty, konkret utopiony w długiej sekcji, parafraza bez wspólnych słów i pytanie o dwóch odpowiedziach naraz.
- Przy 49 pytaniach przedział ufności dla recall@5 ma szerokość 0,21, więc różnicę czytaj po liczbie pytań, które zmieniły wynik, a nie po trzeciej cyfrze średniej.

## Co dalej

Rozdział 2 bierze się za pierwszy i najtańszy element z listy błędów: chunking i reprezentację. Zobaczysz, ile daje zmiana rozmiaru okna, podział po strukturze Markdown, doklejenie tytułu rozdziału i sekcji do fragmentu, small-to-big oraz zamiana `multilingual-e5-small` na model o innym wymiarze wektora – wszystko mierzone tym samym plikiem `golden.jsonl` i tym samym `k`. Zanim tam przejdziesz, uruchom `experiments/01_baseline.py` u siebie i przeczytaj listę pięciu fragmentów zwróconych dla każdej porażki. Dziewięć przypadków to dziesięć minut czytania, po których będziesz wiedział o tym korpusie więcej, niż mówi którakolwiek tabela w tym rozdziale.

## Źródła

- https://huggingface.co/intfloat/multilingual-e5-small
- https://arxiv.org/abs/2402.05672
- https://sbert.net/docs/sentence_transformer/usage/usage.html
- https://qdrant.tech/documentation/concepts/search/
- https://qdrant.tech/documentation/concepts/hybrid-queries/
- https://platform.claude.com/docs/en/api/messages
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
