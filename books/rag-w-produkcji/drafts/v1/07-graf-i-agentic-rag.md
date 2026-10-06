# Rozdział 7. GraphRAG i agentic RAG

> **Cel rozdziału:** sprawdzić na liczbach, czy wyjście poza podobieństwo wektorowe – graf relacji między fragmentami i pętla, w której model sam decyduje o kolejnym wyszukiwaniu – opłaca się na korpusie dokumentacji.
>
> **Kod:** `ragbook/graph.py`, `ragbook/agentic.py`, `experiments/07_graph.py`, `experiments/07_graphrag_cost.py`, `experiments/07_corrective.py`, `experiments/07_agentic.py`. **Pakiety poza fundamentem:** `pip install networkx tiktoken anthropic`.

Sześć poprzednich rozdziałów opierało się na jednym założeniu: że odpowiedź leży w jednym miejscu i wystarczy je znaleźć. Najsłabsza grupa w golden secie mówi, że to założenie bywa fałszywe. Pytania porównawcze – jedenaście pozycji, każda z trafnością w dwóch sekcjach – mają na baseline'ie z rozdziału 1 recall@5 równy 0,64 przy MRR@5 równym 0,75. Ta para liczb znaczy dokładnie jedno: system prawie zawsze trafia jedną z dwóch potrzebnych sekcji, i to wysoko, a drugiej nie dokłada nigdy. Podobieństwo kosinusowe nie ma pojęcia, że pytanie ma dwie odpowiedzi.

Ten rozdział sprawdza dwa pomysły uchodzące w literaturze za lekarstwo na tę klasę porażek. Pierwszy to graf: fragmenty połączone odwołaniami, wspólnymi terminami i sąsiedztwem, po których wyszukiwanie może przejść skok dalej. Drugi to pętla: model ocenia, czy dostał dość, i pyta jeszcze raz. Oba mają wersję tanią, mierzalną lokalnie, i wersję z LLM-em, która kosztuje pieniądze i czas.

Uprzedzam wynik, bo w tym tomie nie ma napięcia dramatycznego, tylko pomiar: **graf zbudowany bez LLM-a nie poprawił na tym korpusie ani jednej metryki**, a ta porażka ma mechanizm, który da się nazwać i który powie Ci, kiedy u siebie oczekiwać czegoś innego. Skrypty uruchamiasz z katalogu `code/`, na przykład `../.venv/bin/python experiments/07_graph.py`; wszystko poza wywołaniami modelu jest prawdziwe i odtwarzalne bez klucza.

## Kiedy podobieństwo nie wystarcza

Trzy kształty pytań wymykają się wyszukiwaniu po podobieństwie, każdy z innego powodu. **Relacyjne** („jak X wiąże się z Y”) potrzebują dwóch bytów naraz, a wektor zapytania leży pomiędzy nimi – bliżej tego, który ma w korpusie więcej tekstu. **Wieloskokowe** wymagają złożenia dwóch fragmentów, z których drugi nie jest podobny do pytania, tylko do pierwszego fragmentu. **Globalne** („które rozdziały poruszają koszty”) pytają o cały korpus, a top-5 zwraca pięć miejsc, nie przekrój.

Zobaczmy to na pytaniach porównawczych z golden setu, puszczonych przez gęsty retriever z rozdziału 1.

```text
q044: Wiedza firmowa w modelu: dostroić go czy dołożyć wyszukiwanie?
  oczekiwane: r5/Fine-tuning w skrócie, r8/RAG a fine-tuning
   1. 0.861  r5/Zamknięte czy otwarte
   2. 0.861  r1/Czym zajmuje się AI Engineer
   3. 0.860  r6/Modele embeddingowe
   4. 0.860  r9/wstep
  *5. 0.859  r8/RAG a fine-tuning

q053: Czym różnią się dwa rodzaje wstrzykiwania instrukcji i dlaczego bronimy się przed nimi inaczej?
  oczekiwane: r4/Bezpieczeństwo kontekstu, r11/Prompt injection
  *1. 0.860  r11/Prompt injection
  *2. 0.856  r11/Prompt injection
   3. 0.849  r9/Systemy wieloagentowe
   4. 0.848  r11/Podsumowanie
   5. 0.847  r3/wstep
```

Skrypt: `experiments/07_graph.py`.

Oba przypadki są typowe. W q044 sekcja o RAG-u kontra fine-tuning wylądowała na piątym miejscu, a „Fine-tuning w skrócie” z rozdziału 5 nie ma nigdzie – sloty zajęły fragmenty „z tej okolicy tematycznej”. W q053 obie górne pozycje to ta sama sekcja „Prompt injection”, zwrócona dwa razy, a sekcja opisująca drugi rodzaj wstrzyknięcia przepadła. To nie jest problem progu ani modelu embeddingowego, tylko tego, że ranking po podobieństwie nagradza koncentrację, a pytanie porównawcze wymaga pokrycia.

Graf obiecuje dokładnie to, czego tu brakuje. Jeżeli „Prompt injection” i „Bezpieczeństwo kontekstu” są połączone krawędzią, wystarczy z pierwszego przejść jeden skok, żeby dostać drugie. Cała reszta tej połowy rozdziału sprawdza, czy ta obietnica jest prawdziwa.

## Graf sekcji, którego da się zmierzyć

Zanim wydasz pieniądze na ekstrakcję encji LLM-em, zbuduj graf z tego, co masz w tekście za darmo. Węzłami są sekcje tomu 1 – ta sama jednostka, w której golden set liczy trafność – a krawędzie pochodzą z trzech warstw liczonych wyrażeniem regularnym.

```python
CHAPTER_REF = re.compile(r"rozdzia[lłuey]\w*\s+(\d+)", re.IGNORECASE)   # "rozdziale 12"
CODE_SPAN = re.compile(r"`([^`\n]{1,60})`")                              # `max_tokens`
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-/]{2,}$")

def build_section_graph(sections, max_df=20, w_ref=1.0, w_term=1.0, w_adj=1.0) -> nx.Graph:
    # (a) jawne odwołania: sekcja wskazująca rozdział n dotyka każdej jego sekcji,
    #     z wagą rozcieńczoną przez wielkość tego rozdziału
    # (b) wspólne identyfikatory: waga to suma idf terminów występujących w obu sekcjach
    # (c) sąsiedztwo: kolejne sekcje tego samego rozdziału
    ...
```

Warstwa (a) jest specyficzna dla dokumentacji i dlatego tak cenna: autor tomu 1 sto piętnaście razy napisał w prozie „rozdział 4” albo „rozdziale 12”, a każde takie zdanie to ręcznie postawiona krawędź, której żaden model nie musi zgadywać. Odwołanie wskazuje jednak rozdział, nie sekcję, więc łączymy źródło ze wszystkimi sekcjami celu, dzieląc wagę przez ich liczbę. Warstwa (b) bierze identyfikatory ze spanów `` `...` `` w prozie (bloki kodu wycinamy wcześniej) i waży je odwrotną częstością dokumentową; `max_df` odrzuca terminy z więcej niż dwudziestu sekcji, bo `user` i `text` połączyłyby wszystko ze wszystkim.

```text
nodes 131  edges 1270  density 0.149  components 1  isolated 0
degree: mean 19.4 median 17 max 81
  ref   edges   882  components   1  isolated   0  mean degree 13.5
  term  edges   371  components  57  isolated  54  mean degree 5.7
  adj   edges   117  components  14  isolated   0  mean degree 1.8
cross-chapter references in prose: 115
inline identifiers: 629 distinct, 900 occurrences, 148 in two or more sections
```

Skrypt: `experiments/07_graph.py`.

Zwróć uwagę na gęstość: przy 131 węzłach i 1270 krawędziach przeciętna sekcja ma dziewiętnastu sąsiadów, a rekordzistka osiemdziesięciu jeden, więc „o jeden skok” znaczy tu „gdzieś w piętnastu procentach korpusu”. I na to, że warstwy są różnej natury – odwołania dają jeden spójny komponent, a wspólne identyfikatory zostawiają 54 sekcje w izolacji, bo połowa tekstu tomu 1 to proza bez inline'owego kodu.

### Co graf mówi sam z siebie

Nawet gdyby nie posłużył do wyszukiwania, taki graf jest niezłym narzędziem redakcyjnym.

| Sekcja | Stopień ważony | PageRank | Betweenness |
|---|---|---|---|
| r1/Słownik pojęć, do których będziemy wracać | 26,7 | 0,0335 | 0,192 |
| r8/Pipeline krok po kroku | 21,8 | 0,0247 | 0,076 |
| r3/Interakcja z modelem | 16,0 | 0,0173 | 0,022 |
| r12/Obserwowalność | 15,3 | 0,0170 | 0,000 |
| r3/Anatomia promptu | 14,7 | 0,0164 | 0,024 |
| r4/Techniki zarządzania kontekstem | 13,3 | 0,0156 | 0,036 |

Skrypt: `experiments/07_graph.py`.

Najbardziej centralny jest słownik pojęć z rozdziału 1 – jedyne miejsce wskazujące na dziewięć rozdziałów naraz. Jego wysokie betweenness mówi więcej niż stopień: to ta jedna sekcja spina książkę i bez niej graf rozpadłby się na słabo połączone części. Druga pozycja, „Pipeline krok po kroku”, to najdłuższa sekcja korpusu (8589 tokenów) i węzeł przelotowy między rozdziałami o embeddingach, bazach i RAG-u.

Podział na społeczności robi `louvain_communities` z networkx – to heurystyka maksymalizująca modularność, opisana w dokumentacji jako dwufazowa: najpierw przenosi pojedyncze węzły tam, gdzie zysk modularności jest największy, potem zwija znalezione grupy w nowe węzły i powtarza. Na naszym grafie przy `resolution` równym 1,0 wychodzi pięć społeczności o modularności 0,416.

| # | Sekcji | Rozdziały (liczba sekcji) | Najcięższa sekcja |
|---|---|---|---|
| 1 | 33 | 11(9) 10(9) 14(7) 12(4) 9(2) | r11/Dobre praktyki |
| 2 | 31 | 7(9) 13(8) 6(8) 8(4) 5(2) | r8/Pipeline krok po kroku |
| 3 | 25 | 5(12) 4(6) 8(5) 1(2) | r1/Słownik pojęć |
| 4 | 25 | 9(8) 3(7) 4(5) 12(2) 10(2) | r3/Interakcja z modelem |
| 5 | 17 | 2(10) 1(6) 12(1) | r2/Rodzaje modeli w skrócie |

Skrypt: `experiments/07_graph.py`.

Podział jest czytelny: druga społeczność to „dane i wyszukiwanie”, czwarta „prompt i pętla”, pierwsza „produkcja i bezpieczeństwo”. Ważniejsze, że społeczności **nie** pokrywają się z rozdziałami – rozdział 4 rozkłada się na trzy z nich, rozdział 12 na cztery. To jest informacja, której płaski indeks nie ma, i to na niej stoi pomysł na odpowiedzi na pytania globalne.

### Wyszukiwanie z rozszerzeniem po grafie

Schemat ma jeden parametr. Wyszukujemy gęsto, bierzemy pięć najlepszych sekcji jako zalążki, z każdego rozlewamy premię na jego najcięższych sąsiadów i porządkujemy wszystko jeszcze raz.

```python
def search(self, query, k=5):
    cos = self.matrix @ self.embedder.embed_queries([query])[0]
    boost = defaultdict(float)
    for section, score in self.seed_sections(cos).items():          # 5 najlepszych sekcji
        for neighbour, weight in self.neighbours[section]:           # per_seed najcięższych
            boost[neighbour] += score * weight
    final = cos + self.beta * np.array([boost.get(key, 0.0) for key in self.keys])
    return [self._wrap(int(i), float(final[int(i)]), cos, boost) for i in np.argsort(-final)[:k]]
```

Pierwsze uruchomienie tego kodu było pouczające z powodu, którego nie przewidziałem. Przy `beta` równym 0,05 – wartości, która w normalnym rankingu byłaby drobną korektą – recall@5 spadł z 0,72 do 0,38. Powód siedzi w rozdziale 1: kosinusy z rodziny E5 układają się między 0,84 a 0,93, a cała czołowa piątka mieści się w przedziale dwóch setnych. Premia rzędu 0,05 nie jest korektą, tylko zaorywa ranking. Na modelu o takiej skali podobieństwa **każdy addytywny bonus trzeba skalować do rozstępu wyników, a nie do ich wartości**.

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | comparative recall@5 | bez trafienia |
|---|---|---|---|---|---|---|
| gęsty baseline (rozdział 1) | 0,72 | 0,96 | 0,67 | 0,64 | 0,64 | 9 |
| boost, beta = 0,001 | 0,72 | 0,93 | 0,68 | 0,65 | 0,64 | 9 |
| boost, beta = 0,005 | 0,72 | 0,92 | 0,63 | 0,62 | 0,64 | 10 |
| boost, beta = 0,01 | 0,70 | 0,86 | 0,61 | 0,60 | 0,68 | 11 |
| boost, beta = 0,02 | 0,59 | 0,76 | 0,54 | 0,52 | 0,59 | 17 |
| fuzja rang RRF, k = 10 | 0,64 | 0,84 | 0,32 | 0,38 | 0,55 | 13 |
| rezerwacja piątego slotu dla sąsiada | 0,71 | 0,93 | 0,66 | 0,64 | 0,59 | 10 |
| dedup po sekcjach (kontrola, bez grafu) | 0,72 | 0,97 | 0,67 | 0,65 | 0,64 | 9 |

Skrypt: `experiments/07_graph.py`.

Wynik jest jednoznaczny i negatywny. Przy `beta` dostatecznie małym, żeby nie zepsuć rankingu, graf nie zmienia recall@5 wcale – rosną o setną MRR i nDCG, czyli premia lekko porządkuje to, co i tak było w piątce, kosztem trzech setnych recall@20. Wariant z twardo zarezerwowanym piątym slotem dla sąsiada, czyli najbardziej dosłowne „dołóż sąsiadów 1-hop”, psuje pytania porównawcze (0,64 → 0,59) i niczego nie naprawia. Fuzja rang, która w rozdziale 3 działa świetnie dla BM25, tutaj jest katastrofą, bo ranking po premii grafowej nie jest rankingiem trafności, tylko rankingiem centralności. A kontrolna kolumna na dole jest najbardziej bolesna: zwykłe wymuszenie „jedna sekcja, jeden fragment”, bez żadnego grafu, daje tyle samo albo o setną więcej.

Skrypt mierzy też każdą warstwę osobno i liczbę sąsiadów na zalążek od jednego do dziesięciu. Żadna kombinacja nie przekroczyła baseline'u; najlepsza zrównała się z nim.

### Dlaczego nie zadziałało

Wynik negatywny bez mechanizmu jest bezużyteczny, bo nie wiadomo, czy przenosi się na inny korpus. Mechanizm da się tu zmierzyć w czterech liniach: dla każdej trafnej sekcji, której zabrakło w top-5, sprawdzamy, czy leży o jeden skok od czegoś, co system znalazł, i na którym miejscu listy sąsiadów.

```text
brakujących sekcji trafnych w top-5: 19; sąsiadów 1-hop: 17 (89%); wśród 3 najcięższych sąsiadów: 5
pozycja brakującej sekcji na liście sąsiadów: mediana 7, średnia 11,5
```

Skrypt: `experiments/07_graph.py`.

Osiemdziesiąt dziewięć procent brakujących sekcji naprawdę leży o jeden skok – graf „wie”, gdzie one są. Tylko że mediana ich pozycji na liście sąsiadów wynosi siedem, przy średnim stopniu dziewiętnaście. Żeby dosięgnąć właściwej sekcji, trzeba wpuścić do rankingu siedmiu sąsiadów na każdy z pięciu zalążków, czyli trzydzieści pięć kandydatów, z których trzydzieści cztery są nietrafne. **Graf ma zasięg, ale nie ma precyzji** – i to jest cała diagnoza. Przy 1550 fragmentach zwykły gęsty retriever i tak sięga po całą okolicę tematyczną, więc sąsiedztwo nie dokłada informacji, której model embeddingowy już nie miał.

Kiedy będzie inaczej? Wtedy, gdy krawędź niesie fakt, którego w tekście fragmentu nie ma. Umowa, która wskazuje aneks numerem; zgłoszenie serwisowe przypięte do maszyny, która stoi w hali; osoba, która jest sygnatariuszem trzech dokumentów. W takich korpusach krawędź zastępuje brakujące zdanie i jeden skok trafia w jedno miejsce, a nie w piętnaście procent zbioru. Nasz korpus jest dokumentacją liniową: każda sekcja opisuje siebie w całości i sąsiedztwo jest w niej redundantne.

## GraphRAG z LLM-em: ile to kosztuje, zanim zadziała

Wersja z pracy „From Local to Global: A Graph RAG Approach to Query-Focused Summarization” (arXiv 2404.16130) buduje graf inaczej i po to, żeby odpowiadać na inne pytania. Indeksowanie ma dwa etapy: LLM wyciąga z każdego fragmentu encje i relacje, a potem – po wykryciu społeczności w powstałym grafie – pisze podsumowanie każdej z nich. Odpowiedź na pytanie globalne powstaje z odpowiedzi cząstkowych generowanych z każdego podsumowania. Praca celuje w pytania „sensemaking” nad korpusami rzędu miliona tokenów, czyli dokładnie w to, czego top-5 nie umie.

Ekstrakcja jest podręcznikowym zastosowaniem structured outputs z rozdziału 6: schemat Pydantic, `messages.parse`, sparsowany obiekt z powrotem.

```python
class Entity(BaseModel):
    name: str = Field(description="Canonical name of the entity, as written in the text")
    type: str = Field(description='One of: concept, model, library, parameter, metric, format, role')
    description: str = Field(description="One sentence about what this entity is, in Polish")

class Relation(BaseModel):
    source: str = Field(description="Name of the source entity, exactly as in entities")
    target: str = Field(description="Name of the target entity, exactly as in entities")
    description: str = Field(description="One sentence on how the two are related, in Polish")
    strength: int = Field(description="1-10, how strongly the fragment ties the two together")

class GraphChunk(BaseModel):
    entities: list[Entity]
    relations: list[Relation]

def extract_graph(client, text, model="claude-haiku-4-5") -> GraphChunk:
    response = client.messages.parse(
        model=model, max_tokens=4096,
        system=[{"type": "text", "text": EXTRACT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"<fragment>\n{text}\n</fragment>"}],
        output_format=GraphChunk,
    )
    return response.parsed_output
```

Przykładowy wynik dla fragmentu sekcji „Pipeline krok po kroku” z rozdziału 8:

```text
entities:  RAG (concept), chunking (concept), multilingual-e5-small (model),
           max_seq_length (parameter), Qdrant (library), recall@5 (metric)
relations: chunking -> multilingual-e5-small  "rozmiar chunku musi mieścić się w limicie
             wejścia modelu embeddingowego" (strength 8)
           multilingual-e5-small -> max_seq_length  "limit modelu to 512 tokenów" (strength 9)
           RAG -> Qdrant  "baza wektorowa przechowuje embeddingi fragmentów" (strength 6)
```

Dwa punkty promptu są tu nieoczywiste. „Tylko to, co mówi fragment” jest konieczne, bo model chętnie dokłada relacje znane z treningu, a wtedy graf przestaje być indeksem korpusu i staje się indeksem wiedzy modelu. Wymóg, żeby `source` i `target` były nazwami zwróconych encji, chroni przed krawędziami do nieistniejących węzłów – `entity_graph` i tak je odrzuca przy scalaniu, ale lepiej ich nie generować.

Teraz rachunek, bo on decyduje. Wejście jest znane co do tokena: 146 814 tokenów `o200k_base` w 131 sekcjach. Wyjście trzeba oszacować i robię to jawnie – osiem encji i sześć relacji na tysiąc tokenów, trzydzieści pięć tokenów na encję, czterdzieści pięć na relację. Zmienisz te cztery liczby na górze skryptu i cała tabela się przesunie.

| Wariant indeksowania | Wywołań | Tokeny wejścia | Tokeny wyjścia | Koszt |
|---|---|---|---|---|
| ekstrakcja, `claude-haiku-4-5`, 1 przebieg | 131 | 173 014 | 80 747 | 0,577 USD |
| ekstrakcja, `claude-haiku-4-5`, 2 przebiegi | 262 | 346 028 | 161 495 | 1,154 USD |
| ekstrakcja, `claude-opus-5`, 1 przebieg | 131 | 173 014 | 80 747 | 2,884 USD |
| 60 podsumowań społeczności, `claude-haiku-4-5` | 60 | 92 747 | 24 000 | 0,213 USD |
| razem: haiku, 1 przebieg + 60 podsumowań | 191 | – | – | 0,789 USD |
| razem: opus, 2 przebiegi + 60 podsumowań | 322 | – | – | 6,831 USD |

Skrypt: `experiments/07_graphrag_cost.py`. Ceny z oficjalnego cennika (stan na wrzesień 2026): `claude-haiku-4-5` 1 i 5 dolarów za milion tokenów wejścia i wyjścia, `claude-opus-5` 5 i 25.

Osiemdziesiąt centów za zaindeksowanie książki to nie jest kwota, przy której ktoś się zawaha – i dlatego warto ją zobaczyć w skali. Przy zapytaniu kosztującym 0,011 dolara (rozdział 8) to równowartość pięćdziesięciu zapytań: tani eksperyment i drogi indeks. Koszt rośnie liniowo z korpusem i płaci się go **od nowa przy każdej zmianie dokumentu**, bo przepisany fragment wymaga nowej ekstrakcji, a jego encje trzeba pogodzić z istniejącymi. Przy korpusie sto razy większym to osiemdziesiąt dolarów i dwadzieścia tysięcy wywołań na przebieg, a przy korpusie zmieniającym się codziennie – tyle samo co miesiąc. Przyrostowa aktualizacja z rozdziału 8 obsługuje indeks gęsty jednym hashem; w grafie encji ta sama operacja wymaga scalania nazw i przeliczenia społeczności.

Druga faza jest w GraphRAG-u sednem: podsumowania społeczności są **pregenerowane**, płacisz za nie raz i odpowiadasz z nich na pytania globalne bez dotykania korpusu. Na naszym grafie sekcji ten krok jest lokalny i darmowy – pięć społeczności przy `resolution` 1,0, czternaście przy 2,0 – ale na grafie encji to sześćdziesiąt wywołań i podsumowania tak dobre, jak ekstrakcja pod spodem.

Kiedy więc warto? Wtedy, gdy w korpusie jest gęsta sieć relacji między bytami, których nazwy powtarzają się w wielu dokumentach: umowy i ich strony, systemy i ich zależności, ludzie i sprawy, zgłoszenia i komponenty. Wtedy graf niesie fakty, których nie ma w żadnym pojedynczym fragmencie, a pytania globalne („które umowy wiążą nas z tym dostawcą”) są w ogóle nieodpowiadalne przez top-k. Kiedy nie warto: przy dokumentacji liniowej takiej jak nasza, gdzie encje to terminy techniczne, relacje między nimi są wyłożone w tekście, a użytkownik pyta o jedno miejsce naraz. Nasz pomiar z poprzedniej sekcji jest zresztą argumentem wstępnym – skoro graf zbudowany z jawnych odwołań autora nie pomógł, graf zgadnięty przez model ma trudniejszy punkt startu, a nie łatwiejszy.

## Agentic RAG: wyszukiwać więcej niż raz

Drugi pomysł nie dotyka indeksu: zamiast budować lepszą strukturę, uruchamiamy zwykły retriever kilka razy, a decyzję, czy i z czym szukać ponownie, podejmuje model albo mały sędzia.

### Iteracyjne wyszukiwanie

Pętla jest tą samą pętlą, co w tomie 1, rozdziale 9: wywołanie, `stop_reason` równy `"tool_use"`, wykonanie narzędzi, wyniki z powrotem w jednej wiadomości `user`. Nowe jest tylko narzędzie i reguła zatrzymania.

```python
while run.steps <= max_steps:
    message = client.messages.create(
        model="claude-opus-5", max_tokens=2048,
        system=[{"type": "text", "text": AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        tools=[SEARCH_TOOL],
        messages=messages,
    )
    messages.append({"role": "assistant", "content": message.content})
    if message.stop_reason != "tool_use":
        run.answer = "".join(b.text for b in message.content if b.type == "text")
        return run
    results = []
    for block in (b for b in message.content if b.type == "tool_use"):
        hits = retrieve(block.input["query"], min(int(block.input.get("k", 5)), 20))
        results.append({"type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps([{"chapter": c.chapter, "section": c.section,
                                                "text": c.text} for c in hits], ensure_ascii=False)})
    messages.append({"role": "user", "content": results})
    run.steps += 1
```

Cała wartość tej pętli jest w opisie narzędzia, nie w kodzie. Opis `corpus_search` mówi wprost, kiedy szukać **ponownie** („gdy pytanie porównuje dwie rzeczy, a znalazłeś tylko jedną”), w jakich słowach formułować zapytanie i że pusta lista jest odpowiedzią, a nie błędem. Limit kroków stoi w kodzie, nie w prompcie, a po jego wyczerpaniu robimy jedno wywołanie bez narzędzi, żeby przebieg skończył się odpowiedzią, a nie wyjątkiem.

Przykładowy wynik dla pytania q044:

```text
  zapytanie 1: fine-tuning a RAG kiedy dostroić model
  zapytanie 2: fine-tuning w skrócie LoRA koszt dostrajania modelu
  kroków: 2  stop_reason: end_turn  unikalnych fragmentów: 9
  sekcje: [(5, 'Fine-tuning w skrócie'), (5, 'Zamknięte czy otwarte'), (8, 'RAG a fine-tuning'), ...]
```

To jest właśnie ten mechanizm, którego grafowi zabrakło: drugie zapytanie zostało napisane pod brakującą część odpowiedzi, a nie wyprowadzone z sąsiedztwa pierwszej. Cena jest jednak wprost proporcjonalna do liczby kroków, bo każde wywołanie niesie całą dotychczasową historię.

| Kroków wyszukiwania | Wywołań API | Tokeny wejścia | Tokeny wyjścia | Koszt zapytania |
|---|---|---|---|---|
| 1 | 2 | 2246 | 370 | 0,02048 USD |
| 2 | 3 | 4509 | 490 | 0,03479 USD |
| 3 | 4 | 7532 | 610 | 0,05291 USD |
| 4 | 5 | 11 315 | 730 | 0,07483 USD |

Skrypt: `experiments/07_agentic.py`; `claude-opus-5`, `k` = 5, mediana chunku 128 tokenów `o200k_base`, narzut systemowy tool use 286 tokenów przy `tool_choice` `auto` (stan na wrzesień 2026).

Cztery kroki kosztują 3,7 raza tyle co jeden i wymagają pięciu wywołań API zamiast dwóch – czyli w budżecie latencji z rozdziału 8 zamieniają sekundy na kilkanaście sekund. To jest prawdziwa cena „niech model sam zdecyduje”: nie trzy razy więcej tokenów, tylko trzy razy więcej tokenów **i** kilkukrotnie dłuższe oczekiwanie, którego nie da się zrównoleglić, bo krok drugi zależy od wyniku pierwszego.

### Corrective RAG bez LLM-a

CRAG (arXiv 2401.15884) wkłada między wyszukiwanie a generację lekki ewaluator: ocenia jakość zwróconych dokumentów, a w zależności od jego pewności albo je akceptuje, albo sięga po wyszukiwarkę internetową, albo robi obie rzeczy. Self-RAG (arXiv 2310.11511) idzie dalej i uczy sam model wypluwać tokeny refleksji, którymi decyduje, czy w ogóle wyszukiwać i czy własna odpowiedź jest pokryta dowodami. Obie prace opisują tę samą pętlę: oceń to, co masz, i napraw, jeśli jest złe.

Tę pętlę da się zbudować bez ani jednego wywołania LLM-a, i wtedy da się ją zmierzyć. Rolę ewaluatora gra cross-encoder `mmarco-mMiniLMv2-L12-H384-v1` – ten sam, którym rozdział 3 robi reranking – a rolę „wyszukiwania w internecie” ponowne zapytanie napisane słowami najlepiej ocenionych fragmentów (pseudo-relevance feedback).

```python
class Vocabulary:
    def feedback_terms(self, texts, top_n=5, min_len=4, min_docs=2, min_df=3):
        """Częste w ocenionych fragmentach, rzadkie w korpusie - i to dokładamy do zapytania."""
        per_doc = [{t for t in normalize(text) if len(t) >= min_len and t not in self.STOP}
                   for text in texts]
        docs = Counter(t for tokens in per_doc for t in tokens)
        tf = Counter(t for text in texts for t in normalize(text))
        scored = [(n * tf[t] * self.idf(t), t) for t, n in docs.items()
                  if n >= min_docs and self.df.get(t, 0) >= min_df]
        return [t for _, t in sorted(scored, key=lambda kv: -kv[0])[:top_n]]

def correct(question, first, scores, threshold, min_kept):
    kept = [c for c, s in zip(first, scores) if s >= threshold]
    return kept, len(kept) < min_kept        # drugi element: czy szukać jeszcze raz
```

Zanim ustawisz próg, zobacz rozkład ocen – tak samo jak przy progu odcięcia w rozdziale 6, bo tam identyczny odruch skończył się niczym.

| Grupa fragmentów | Fragmentów | min | mediana | średnia | maks |
|---|---|---|---|---|---|
| z sekcji trafnej | 200 | -7,70 | -1,44 | -0,72 | 9,87 |
| z sekcji nietrafnej | 780 | -10,03 | -3,90 | -3,69 | 9,31 |
| z pytań negatywnych | 140 | -10,14 | -5,60 | -4,88 | 5,20 |

Skrypt: `experiments/07_corrective.py`; oceny to surowe logity, nie prawdopodobieństwa.

W przeciwieństwie do kosinusa e5 z rozdziału 6 te rozkłady **rozdzielają się**: mediana fragmentu z trafnej sekcji to -1,44, z nietrafnej -3,90, a z pytania negatywnego -5,60. Dwa i pół punktu różnicy między medianami to jest sygnał, na którym da się postawić próg – i to jest pierwsza dobra wiadomość tego rozdziału. Próg wyznacza jednak nie tylko jakość filtra, ale i to, jak często odpala się druga tura: przy -4,0 mediana zachowanych fragmentów wynosi 12 i naprawę uruchamia 7 pytań, przy 0,0 zostają dwa fragmenty i naprawia się 35 z 56 pytań.

| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | comparative recall@5 | bez trafienia |
|---|---|---|---|---|---|---|
| gęsty baseline (rozdział 1) | 0,72 | 0,96 | 0,67 | 0,64 | 0,64 | 9 |
| sama ocena: reranking 20 → 5 (rozdział 3) | 0,85 | 0,96 | 0,81 | 0,78 | 0,73 | 4 |
| corrective, próg -4,0 (7 pytań z drugą turą) | 0,85 | 0,96 | 0,81 | 0,78 | 0,73 | 4 |
| corrective, próg -2,0 (21 pytań z drugą turą) | 0,85 | 0,95 | 0,81 | 0,78 | 0,73 | 4 |
| corrective, próg 0,0 (35 pytań z drugą turą) | 0,85 | 0,95 | 0,81 | 0,78 | 0,73 | 4 |

Skrypt: `experiments/07_corrective.py`.

Cały zysk siedzi w ocenie i żaden w naprawie. Przesortowanie dwudziestki cross-encoderem podnosi recall@5 z 0,72 do 0,85, MRR z 0,67 do 0,81, a liczbę pytań bez trafienia z dziewięciu do czterech – to jednak jest reranking z rozdziału 3, nie corrective RAG. Druga tura wyszukiwania nie zmieniła **ani jednego pytania** przy żadnym progu, za to obniżyła recall@20, bo dołożone fragmenty wypychają z dwudziestki te, które już tam były.

Część winy ponosi przepisywanie zapytań. Wersja naiwna, biorąca najwyższe tf-idf z jednego fragmentu, wybiera hapaksy – po polsku wychodzi z tego „workflow przesada wyciagniecie łatwiejszy”. Wariant powyżej, wymagający terminu w dwóch fragmentach zwrotnych i w trzech fragmentach korpusu, daje słowa sensowniejsze („argumentow konektor zdalny serwer”), a wynik i tak stoi w miejscu. Głębsza przyczyna jest ta sama, co przy grafie: przy recall@20 równym 0,96 drugie wyszukiwanie nie ma czego dołożyć, bo odpowiedź była w dwudziestce od początku. CRAG projektowano dla sytuacji, w której retrieval bywa całkowicie chybiony i trzeba wyjść poza korpus; u nas zdarza się to raz na 49 pytań.

### RAG jako jedno z narzędzi agenta

Trzeci wariant agentowy nie dotyczy tego, ile razy szukać, tylko czy w ogóle. Gdy asystent ma obok wyszukiwania inne narzędzia, decyzja „to jest pytanie do korpusu” staje się decyzją modelu, a nie routera w kodzie: dokładasz kolejne definicje narzędzi i pozwalasz wybrać `tool_choice` `auto`. Mierzy się to inaczej – nie recallem, tylko odsetkiem pytań, przy których model sięgnął po właściwe narzędzie.

Zestaw to z routingiem z rozdziału 4. Klasyfikacja intencji małym modelem kosztuje jedno tanie wywołanie i kilkaset tokenów; decyzja agenta kosztuje pełne wywołanie flagowca z definicjami wszystkich narzędzi w prefiksie – u nas 286 tokenów narzutu plus 417 tokenów na system prompt i jedno narzędzie. Przy kilkunastu narzędziach sam prefiks jest wielkości promptu z pięcioma fragmentami. Reguła: zbiór intencji zamknięty i znany – routing w kodzie jest tańszy, szybszy i testowalny; zbiór otwarty, a narzędzia trzeba składać w nieprzewidziane sekwencje – płacisz za agenta.

## Koszt kontra zysk

Pięć pozycji w jednej tabeli, z rozdziałem na to, co zmierzone lokalnie, i to, co wymaga klucza.

| Technika | Wywołania LLM | Dodatkowy koszt | Zmierzony zysk | Decyzja |
|---|---|---|---|---|
| graf sekcji bez LLM-a | 0 | 0,1 s na budowę grafu, ~1 ms na zapytanie | recall@5 0,72 → 0,72, comparative 0,64 → 0,64 | odrzucony |
| GraphRAG (ekstrakcja + społeczności) | 191 przy indeksowaniu, 0 przy zapytaniu | 0,79 USD za przebieg, powtarzany przy każdej zmianie dokumentu | niezmierzony – wymaga klucza | nie wchodzi |
| iteracyjne wyszukiwanie | 2–5 na zapytanie | ×3,7 kosztu i 5 wywołań przy czterech krokach | niezmierzony – wymaga klucza | opcja dla pytań porównawczych |
| cross-encoder jako sędzia (CRAG, część oceniająca) | 0 | 2,7 s CPU na pytanie | recall@5 0,72 → 0,85, comparative 0,64 → 0,73 | zostaje (jako reranking z rozdziału 3) |
| ponowne zapytanie z PRF (CRAG, część naprawcza) | 0 | druga tura wyszukiwania i oceny | 0,85 → 0,85, recall@20 spada | odrzucony |

Decyzja jest krótka: w potoku zostaje reranking cross-encoderem z rozdziału 3, a z nowych technik nie zostaje nic. Graf sekcji zostaje w repozytorium jako narzędzie diagnostyczne, bo mówi o korpusie rzeczy, których nie widać w indeksie, ale nie dotyka rankingu. Pętla agentowa jest opcją warunkową: dla pytań, które router z rozdziału 4 sklasyfikuje jako porównawcze, z twardym limitem dwóch kroków.

Morał jest ogólniejszy niż te cztery liczby. Obie odrzucone techniki są opisane rzetelnie i obie działają – tylko na innych korpusach. GraphRAG mierzono na pytaniach sensemaking nad milionem tokenów, CRAG na zbiorach, w których retrieval bywa całkowicie chybiony. Nasze pytania są lokalne, a odpowiedź niemal zawsze siedzi w dwudziestce (recall@20 0,96 od rozdziału 1). Nie ma więc czego naprawiać drugą turą ani doklejać z sąsiedztwa – trzeba tylko lepiej uszeregować to, co już jest, i dlatego wygrywa reranker.

## Podsumowanie

- Pytania porównawcze, relacyjne i globalne psują się na wyszukiwaniu po podobieństwie z jednego powodu: ranking nagradza koncentrację, a te pytania wymagają pokrycia dwóch różnych miejsc.
- Graf sekcji da się zbudować bez modelu z trzech warstw – jawnych odwołań w prozie (115 w tomie 1), wspólnych identyfikatorów w spanach `` `...` `` (629 terminów) i sąsiedztwa – w stu liniach kodu i dziesiątej części sekundy, ale nie poprawił on żadnej metryki: przy każdej wartości `beta`, przy fuzji rang i przy rezerwacji slotu recall@5 stoi na 0,72 albo spada, a kontrolna deduplikacja po sekcjach daje tyle samo bez grafu.
- Mechanizm porażki jest mierzalny: 89 procent brakujących sekcji leży o jeden skok, ale na medianowej pozycji siódmej wśród dziewiętnastu sąsiadów, więc graf ma zasięg bez precyzji.
- Na modelu z rodziny E5 każda addytywna premia musi być skalowana do rozstępu wyników (dwie setne), a nie do ich wartości (0,84–0,93); `beta` równe 0,05 obniżyło recall@5 z 0,72 do 0,38.
- Pełna ekstrakcja encji i relacji z tego korpusu to 131 wywołań i 0,79 dolara na `claude-haiku-4-5` razem z podsumowaniami społeczności – tanio jednorazowo, drogo przy każdej zmianie dokumentu, bo aktualizacja wymaga scalania nazw encji, a nie jednego hasha.
- GraphRAG opłaca się przy korpusach o gęstej sieci relacji między nazwanymi bytami (umowy, systemy, osoby) i przy pytaniach o cały zbiór; przy dokumentacji liniowej, gdzie relacje są wypisane w tekście, nie ma czego wydobywać.
- Iteracyjne wyszukiwanie kosztuje 3,7 raza tyle co jedno zapytanie i pięć wywołań API zamiast dwóch, a jego wartość siedzi w opisie narzędzia – w zdaniu mówiącym modelowi, kiedy szukać **ponownie**.
- Z corrective RAG przeżywa tylko część oceniająca: cross-encoder podnosi recall@5 z 0,72 do 0,85, a dokładana do niego druga tura z pseudo-relevance feedback nie zmienia ani jednego pytania.

## Co dalej

Rozdział 8 zamyka tom i zajmuje się tym, co dzieje się z systemem po wdrożeniu: przyrostową aktualizacją indeksu, cache'owaniem, budżetem kosztu i latencji, wstrzyknięciami przez dokumenty i śladem, z którego da się odtworzyć nieudane zapytanie. Z tego rozdziału zabierasz tam dwie rzeczy: liczbę wywołań modelu jako pierwszą pozycję rachunku i nawyk, żeby przed wdrożeniem techniki sprawdzić, czy jej mechanizm w ogóle ma zaczepienie w Twoich danych. Zanim tam przejdziesz, uruchom `experiments/07_graph.py` na własnym korpusie i przeczytaj sekcję o zasięgu: jeżeli brakujące dokumenty leżą u Ciebie na trzeciej pozycji listy sąsiadów, a nie na siódmej, cały ten rozdział skończy się u Ciebie inaczej.

## Źródła

- https://arxiv.org/abs/2404.16130
- https://arxiv.org/abs/2310.11511
- https://arxiv.org/abs/2401.15884
- https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- https://platform.claude.com/docs/en/about-claude/pricing
