# Rozdział 7. GraphRAG i agentic RAG

> **Cel rozdziału:** sprawdzić na liczbach, czy wyjście poza podobieństwo wektorowe – graf relacji między fragmentami i pętla, w której model sam decyduje o kolejnym wyszukiwaniu – opłaca się na korpusie dokumentacji.
>
> **Kod:** `ragbook/graph.py`, `ragbook/agentic.py`, `experiments/07_graph.py`, `experiments/07_graphrag_cost.py`, `experiments/07_corrective.py`, `experiments/07_agentic.py`. **Pakiety poza fundamentem:** `pip install networkx tiktoken anthropic`.

Weź z golden setu pytanie, które wygląda niewinnie: „Jak podmienić model liczący wektory w działającym systemie, nie psując wyszukiwania?”. Odpowiedź jest krótka – przelicz korpus nowym modelem do nowej kolekcji, przełącz alias, dopiero potem skasuj starą – ale nie stoi w żadnym pojedynczym miejscu. Procedura z aliasem jest w „Indeksowaniu embeddingów” rozdziału 7 tomu 1, a ostrzeżenie, żeby nie mieszać dwóch modeli w jednym indeksie, w „Praktycznych pułapkach” rozdziału 6. Baseline z rozdziału 1 zwraca pięć fragmentów rozsianych po czterech rozdziałach i nie łapie żadnej z tych sekcji. Nie ma tu fragmentu, który byłby odpowiedzią, więc nie ma i takiego, blisko którego leżałby wektor pytania.

Cała najsłabsza grupa zestawu zachowuje się tak samo. Pytania porównawcze – jedenaście pozycji, każda z trafnością w dwóch sekcjach – mają na baseline'ie recall@5 równy 0,64 przy MRR@5 równym 0,75: system prawie zawsze trafia jedną z dwóch potrzebnych sekcji, i to wysoko, a drugiej nie dokłada nigdy.

Stąd pomysł na graf. Indeks jest płaską listą fragmentów i zna jedną relację: podobieństwo fragmentu do zapytania. Graf dokłada drugą, między samymi fragmentami – „ta sekcja odsyła do rozdziału 6”, „w tych dwóch pada `max_seq_length`”. Lista odpowiada na pytanie „co jest podobne do zapytania”, graf na „co stoi obok tego, co już znalazłem”.

Ten rozdział sprawdza tę obietnicę i drugą, pokrewną: pętlę, w której model ocenia, czy dostał dość, i pyta ponownie. Uprzedzam wynik, bo nie ma tu napięcia dramatycznego, tylko pomiar: **graf zbudowany bez LLM-a nie poprawił na tym korpusie ani jednej metryki**, a ta porażka ma mechanizm, który powie Ci, kiedy u siebie oczekiwać czegoś innego.

## Kiedy podobieństwo nie wystarcza

Trzy kształty pytań wymykają się podobieństwu. **Relacyjne** („jak X wiąże się z Y”) potrzebują dwóch bytów naraz, a wektor zapytania leży pomiędzy nimi. **Wieloskokowe** wymagają złożenia dwóch fragmentów, z których drugi jest podobny nie do pytania, tylko do pierwszego. **Globalne** pytają o cały korpus, a top-5 zwraca pięć miejsc, nie przekrój.

Tak to wygląda na dwóch pytaniach porównawczych puszczonych przez gęsty retriever z rozdziału 1.

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

Oba przypadki są typowe. W pytaniu o fine-tuning sekcja „RAG a fine-tuning” ledwo zmieściła się na piątym miejscu, a „Fine-tuning w skrócie” nie ma nigdzie. W pytaniu o wstrzykiwanie instrukcji obie górne pozycje to ta sama sekcja, zwrócona dwa razy. Ranking po podobieństwie nagradza koncentrację, a pytanie porównawcze wymaga pokrycia.

## Graf sekcji, którego da się zmierzyć

Zanim wydasz pieniądze na ekstrakcję encji LLM-em, zbuduj graf z tego, co w tekście już jest. Węzłami są sekcje tomu 1 – ta sama jednostka, w której golden set liczy trafność – a krawędzie pochodzą z trzech warstw.

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

**Jawne odwołania** są specyficzne dla dokumentacji i dlatego najcenniejsze. Gdy w rozdziale 3 stoi „wrócimy do niego w rozdziale 12”, autor własną ręką postawił krawędź; takich zdań jest w tomie 1 sto piętnaście. Odwołanie wskazuje jednak rozdział, a nie sekcję, więc łączymy źródło ze wszystkimi sekcjami celu i dzielimy wagę.

**Wspólne identyfikatory** łapią pokrewieństwo, którego autor nie nazwał: dwie sekcje, w których pada w prozie `max_seq_length`, mówią o tym samym, choćby innymi słowami. Terminy ważymy odwrotną częstością dokumentową, a `max_df` odrzuca te z więcej niż dwudziestu sekcji, bo `user` połączyłby wszystko ze wszystkim.

**Sąsiedztwo** to najtańsza krawędź: kolejne sekcje tego samego rozdziału. „Anatomia promptu” dotyka „Technik promptowania”, bo autor ustawił je obok siebie – i to cała informacja, jaką ta warstwa niesie.

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

Ten graf jest gęsty i to powinno Cię zaniepokoić: przeciętna sekcja ma dziewiętnastu sąsiadów, a rekordzistka osiemdziesięciu jeden, więc „o jeden skok” znaczy tu „gdzieś w piętnastu procentach korpusu”. Warstwy są różnej natury: odwołania spinają tom w jeden komponent, identyfikatory zostawiają 54 sekcje w izolacji.

Nawet gdyby nie posłużył do wyszukiwania, taki graf jest niezłym narzędziem redakcyjnym. Najbardziej centralną sekcją tomu 1 okazuje się słownik pojęć z rozdziału 1 – jedyne miejsce wskazujące na dziewięć rozdziałów naraz. Jego betweenness mówi więcej niż stopień: to ta jedna sekcja spina książkę.

Społeczności wykrywa `louvain_communities` z networkx. Przy `resolution` równym 1,0 wychodzi pięć czytelnych grup – „dane i wyszukiwanie”, „prompt i pętla”, „produkcja i bezpieczeństwo” – o modularności 0,416, i **nie** pokrywają się one z rozdziałami. Tej informacji płaski indeks nie ma i na niej stoi pomysł na pytania globalne.

### Wyszukiwanie z rozszerzeniem po grafie

Schemat ma jeden parametr. Wyszukujemy gęsto, bierzemy pięć najlepszych sekcji jako zalążki, z każdego rozlewamy premię na najcięższych sąsiadów i porządkujemy wszystko jeszcze raz.

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

Pierwsze uruchomienie było pouczające. Przy `beta` równym 0,05 – wartości, która w normalnym rankingu byłaby drobną korektą – recall@5 spadł z 0,72 do 0,38. Powód siedzi w rozdziale 1: kosinusy z rodziny E5 układają się między 0,84 a 0,93, a czołowa piątka mieści się w dwóch setnych. **Bonus trzeba skalować do rozstępu wyników, nie do ich wartości.**

| Wariant | recall@5 | comparative recall@5 | Pytań bez trafienia |
|---|---|---|---|
| gęsty baseline (rozdział 1) | 0,72 | 0,64 | 9 |
| boost, beta = 0,001 (najlepszy wariant grafowy) | 0,72 | 0,64 | 9 |
| rezerwacja piątego slotu dla sąsiada | 0,71 | 0,59 | 10 |
| dedup po sekcjach (kontrola, bez grafu) | 0,72 | 0,64 | 9 |

Skrypt: `experiments/07_graph.py`.

Wynik jest jednoznaczny i negatywny: graf nie poprawił niczego. Przy `beta` dostatecznie małym, żeby nie zepsuć rankingu, recall@5 stoi tam, gdzie stał, a pytania porównawcze – te, dla których cały pomysł powstał – nie drgnęły. Najbardziej dosłowna wersja, rezerwacja piątego slotu dla sąsiada, właśnie je psuje. A dedup po sekcjach daje tyle samo bez grafu.

Skrypt mierzy jeszcze fuzję rang RRF, każdą warstwę osobno i liczbę sąsiadów na zalążek. Fuzja wypada najgorzej ze wszystkiego: ranking po premii grafowej nie jest rankingiem trafności, tylko centralności. Żadna kombinacja nie przekroczyła baseline'u.

### Dlaczego nie zadziałało

Wynik negatywny bez mechanizmu jest bezużyteczny, bo nie wiadomo, czy przenosi się na inny korpus. Ten da się zmierzyć w czterech liniach: dla każdej trafnej sekcji, której zabrakło w top-5, sprawdzamy, czy leży o jeden skok od czegoś, co system znalazł, i na którym miejscu listy sąsiadów.

```text
brakujących sekcji trafnych w top-5: 19; sąsiadów 1-hop: 17 (89%); wśród 3 najcięższych sąsiadów: 5
pozycja brakującej sekcji na liście sąsiadów: mediana 7, średnia 11,5
```

Skrypt: `experiments/07_graph.py`.

Cała diagnoza mieści się w dwóch zdaniach. Brakujące sekcje naprawdę leżą o jeden skok – 89 procent z nich – więc graf „wie”, gdzie one są, tylko że mediana ich pozycji na liście sąsiadów wynosi siedem. **Graf ma zasięg, ale nie ma precyzji**: żeby dosięgnąć właściwej sekcji, trzeba wpuścić trzydziestu pięciu kandydatów, w tym trzydziestu czterech nietrafnych.

Inaczej będzie tam, gdzie krawędź niesie fakt, którego w tekście fragmentu nie ma: umowa wskazująca aneks numerem, zgłoszenie przypięte do maszyny, osoba będąca sygnatariuszem trzech dokumentów. Tam jeden skok trafia w jedno miejsce. Nasz korpus jest dokumentacją liniową: każda sekcja opisuje siebie w całości, a gęsty retriever i tak bierze całą okolicę.

## GraphRAG z LLM-em: ile to kosztuje, zanim zadziała

Wersja z pracy „From Local to Global: A Graph RAG Approach to Query-Focused Summarization” (arXiv 2404.16130) buduje graf inaczej. Węzłem nie jest fragment tekstu, tylko byt w nim wymieniony: LLM czyta każdy fragment i wypisuje encje – model, parametr, biblioteka, metryka – oraz relacje między nimi. „Qdrant” jest w takim grafie **jednym** węzłem, choćby padał w dziesięciu rozdziałach.

Drugi etap indeksowania wykrywa w grafie społeczności, czyli skupiska gęsto powiązanych bytów, i każe modelowi napisać podsumowanie każdej z nich. Płacisz za nie raz, przy indeksowaniu.

Odpowiedź na pytanie globalne – „co ten zbiór mówi o kosztach” – powstaje potem z odpowiedzi cząstkowych generowanych osobno z każdego podsumowania. Praca celuje w pytania typu sensemaking nad korpusami rzędu miliona tokenów, czyli w to, czego top-5 nie umie z definicji.

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

Jeden punkt tego promptu jest nieoczywisty: instrukcja „tylko to, co mówi fragment”. Bez niej model dokłada relacje znane z treningu i graf przestaje być indeksem korpusu, a staje się indeksem wiedzy modelu.

Teraz rachunek, bo on decyduje. Wejście znamy co do tokena – 146 814 tokenów `o200k_base` w 131 sekcjach – a wyjście skrypt szacuje jawnie. Jedna liczba do zapamiętania: **jeden przebieg ekstrakcji przez ten korpus to 0,577 dolara na `claude-haiku-4-5`, czyli równowartość mniej więcej pięćdziesięciu zapytań do gotowego RAG-a** (0,011 dolara za zapytanie, rozdział 8).

Ta proporcja jest ważniejsza od kwoty, bo nie zależy od cennika i skaluje się liniowo z korpusem. Podsumowania społeczności dokładają 0,213 dolara, a opus albo drugi przebieg mnożą rachunek kilkukrotnie; siatkę wariantów wypisuje `experiments/07_graphrag_cost.py`. Ceny z oficjalnego cennika (stan na wrzesień 2026): `claude-haiku-4-5` 1 i 5 dolarów za milion tokenów, `claude-opus-5` 5 i 25.

Gorsze od kwoty jest to, że płacisz ją **od nowa przy każdej zmianie dokumentu**: przepisany fragment wymaga nowej ekstrakcji, a jego encje trzeba pogodzić z istniejącymi. Przyrostowa aktualizacja z rozdziału 8 obsługuje indeks gęsty jednym hashem; tu jest to scalanie nazw i przeliczanie społeczności.

Kiedy więc warto? Wtedy, gdy korpus ma gęstą sieć relacji między bytami, których nazwy powtarzają się w wielu dokumentach: umowy i ich strony, systemy i ich zależności, ludzie i sprawy. Graf niesie tam fakty, których nie ma w żadnym pojedynczym fragmencie, a pytania globalne („które umowy wiążą nas z tym dostawcą”) są dla top-k nieodpowiadalne. Nie warto przy dokumentacji liniowej: skoro graf z jawnych odwołań autora nie pomógł, ten zgadnięty przez model ma start trudniejszy.

## Agentic RAG: wyszukiwać więcej niż raz

Drugi pomysł nie dotyka indeksu: uruchamiamy zwykły retriever kilka razy, a decyzję, czy szukać ponownie, podejmuje model albo mały sędzia.

### Iteracyjne wyszukiwanie

Pomysł mieści się w trzech słowach: szukaj, oceń, szukaj inaczej. Model dostaje narzędzie `corpus_search`, wywołuje je, czyta wyniki i sam rozstrzyga, czy ma komplet; jeżeli nie, pisze drugie zapytanie, sformułowane pod brakującą część odpowiedzi. Technicznie jest to pętla z tomu 1, rozdziału 9: wywołanie, `stop_reason` równy `"tool_use"`, wykonanie narzędzi, wyniki z powrotem.

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

Cała wartość tej pętli siedzi w opisie narzędzia, nie w kodzie. Opis `corpus_search` mówi wprost, kiedy szukać **ponownie** („gdy pytanie porównuje dwie rzeczy, a znalazłeś tylko jedną”). Limit kroków stoi w kodzie, a po jego wyczerpaniu robimy jedno wywołanie bez narzędzi, żeby przebieg skończył się odpowiedzią.

Przykładowy wynik dla pytania o fine-tuning kontra RAG:

```text
  zapytanie 1: fine-tuning a RAG kiedy dostroić model
  zapytanie 2: fine-tuning w skrócie LoRA koszt dostrajania modelu
  kroków: 2  stop_reason: end_turn  unikalnych fragmentów: 9
  sekcje: [(5, 'Fine-tuning w skrócie'), (5, 'Zamknięte czy otwarte'), (8, 'RAG a fine-tuning'), ...]
```

To jest dokładnie ten mechanizm, którego grafowi zabrakło: drugie zapytanie celuje w to, czego brakuje, zamiast rozlewać premię na okolicę. Cena rośnie jednak z liczbą kroków szybciej niż liniowo, bo każde wywołanie niesie całą historię.

| Kroków wyszukiwania | Wywołań API | Tokeny wejścia | Tokeny wyjścia | Koszt zapytania |
|---|---|---|---|---|
| 1 | 2 | 2246 | 370 | 0,02048 USD |
| 2 | 3 | 4509 | 490 | 0,03479 USD |
| 3 | 4 | 7532 | 610 | 0,05291 USD |
| 4 | 5 | 11 315 | 730 | 0,07483 USD |

Skrypt: `experiments/07_agentic.py`; `claude-opus-5`, `k` = 5, mediana chunku 128 tokenów `o200k_base`, narzut systemowy tool use 286 tokenów przy `tool_choice` `auto` (stan na wrzesień 2026).

Cztery kroki kosztują 3,7 raza tyle co jeden i wymagają pięciu wywołań API zamiast dwóch. To jest prawdziwa cena „niech model sam zdecyduje”: nie tylko tokeny, ale i oczekiwanie, którego nie da się zrównoleglić, bo krok drugi zależy od pierwszego.

### Corrective RAG bez LLM-a

Ta sama pętla, tylko bez modelu w roli decydenta. CRAG (arXiv 2401.15884) wkłada między wyszukiwanie a generację lekkiego sędziego: ocenia on zwrócone dokumenty i zależnie od pewności albo je akceptuje, albo sięga po wyszukiwarkę internetową. Self-RAG (arXiv 2310.11511) przenosi tę decyzję do samego modelu, który wypluwa tokeny refleksji.

Tę pętlę da się zbudować bez ani jednego wywołania LLM-a, a wtedy da się ją zmierzyć. Sędzią jest cross-encoder `mmarco-mMiniLMv2-L12-H384-v1` – ten sam, którym rozdział 3 robi reranking – a „wyszukiwaniem w internecie” ponowne zapytanie ze słów najlepiej ocenionych fragmentów (pseudo-relevance feedback).

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

Zanim ustawisz próg, zobacz rozkład ocen – tak jak w rozdziale 6, gdzie identyczny odruch skończył się niczym.

| Grupa fragmentów | Fragmentów | min | mediana | maks |
|---|---|---|---|---|
| z sekcji trafnej | 200 | -7,70 | -1,44 | 9,87 |
| z sekcji nietrafnej | 780 | -10,03 | -3,90 | 9,31 |
| z pytań negatywnych | 140 | -10,14 | -5,60 | 5,20 |

Skrypt: `experiments/07_corrective.py`; oceny to surowe logity, nie prawdopodobieństwa.

W przeciwieństwie do kosinusa e5 z rozdziału 6 te rozkłady **rozdzielają się**, i to jest pierwsza dobra wiadomość tego rozdziału. Między medianą fragmentu z trafnej sekcji a medianą fragmentu z nietrafnej leży dwa i pół punktu, a pytania negatywne siedzą jeszcze niżej. Na takim sygnale da się postawić próg.

Próg decyduje przy tym, jak często odpala się druga tura: przy -4,0 naprawiane jest 7 pytań, przy 0,0 aż 35 z 56. Dwa pozostałe progi dają w tych samych kolumnach identyczne liczby.

| Wariant | recall@5 | comparative recall@5 | Pytań bez trafienia |
|---|---|---|---|
| gęsty baseline (rozdział 1) | 0,72 | 0,64 | 9 |
| sama ocena: reranking 20 → 5 (rozdział 3) | 0,85 | 0,73 | 4 |
| corrective, próg -4,0 (7 pytań z drugą turą) | 0,85 | 0,73 | 4 |

Skrypt: `experiments/07_corrective.py`.

Cały zysk daje ocena, żaden naprawa. Przesortowanie dwudziestki cross-encoderem podnosi recall@5 z 0,72 do 0,85 i zbija liczbę pytań bez trafienia z dziewięciu do czterech – tyle że to jest reranking z rozdziału 3, a nie corrective RAG. Druga tura nie zmieniła **ani jednego pytania** przy żadnym progu, za to obniżyła recall@20.

Część winy ponosi przepisywanie zapytań: wersja naiwna wybiera hapaksy („workflow przesada wyciagniecie łatwiejszy”), a wariant z kodu powyżej daje słowa sensowniejsze i wynik stoi w miejscu tak samo. Głębsza przyczyna jest ta sama, co przy grafie: przy recall@20 równym 0,96 drugie wyszukiwanie nie ma czego dołożyć. CRAG projektowano dla retrievalu bywającego całkowicie chybionym; u nas zdarza się to raz na 49 pytań.

### RAG jako jedno z narzędzi agenta

Trzeci wariant agentowy nie dotyczy tego, ile razy szukać, tylko czy w ogóle. Gdy asystent ma obok wyszukiwania inne narzędzia, decyzja „to jest pytanie do korpusu” należy do modelu, a nie do routera w kodzie, i mierzy się ją odsetkiem pytań, przy których model sięgnął po właściwe narzędzie. Zestaw to z routingiem z rozdziału 4: przy zbiorze intencji zamkniętym i znanym routing w kodzie jest tańszy i testowalny, przy otwartym płacisz za wywołanie flagowca z definicjami wszystkich narzędzi w prefiksie.

## Koszt kontra zysk

Cztery pozycje: dwie zmierzone lokalnie i dwie, na które trzeba klucza API.

| Technika | Wywołania LLM | Dodatkowy koszt | Zmierzony zysk | Decyzja |
|---|---|---|---|---|
| graf sekcji bez LLM-a | 0 | 0,1 s na budowę grafu, ~1 ms na zapytanie | recall@5 0,72 → 0,72, comparative 0,64 → 0,64 | odrzucony |
| GraphRAG (ekstrakcja + społeczności) | 191 przy indeksowaniu, 0 przy zapytaniu | 0,79 USD za przebieg, powtarzany przy każdej zmianie dokumentu | niezmierzony – wymaga klucza | nie wchodzi |
| iteracyjne wyszukiwanie | 2–5 na zapytanie | ×3,7 kosztu i 5 wywołań przy czterech krokach | niezmierzony – wymaga klucza | opcja dla pytań porównawczych |
| corrective RAG: ocena cross-encoderem plus druga tura z PRF | 0 | 2,7 s CPU na pytanie | z samej oceny recall@5 0,72 → 0,85, comparative 0,64 → 0,73; z naprawy 0,85 → 0,85 | ocena zostaje (jako reranking z rozdziału 3), naprawa odrzucona |

Decyzja jest krótka: w potoku zostaje reranking cross-encoderem z rozdziału 3, a z nowych technik nie zostaje nic. Graf sekcji zostaje w repozytorium jako narzędzie diagnostyczne, ale nie dotyka rankingu. Pętla agentowa jest opcją warunkową: dla pytań porównawczych, z limitem dwóch kroków.

Morał jest ogólniejszy niż te liczby. Obie odrzucone techniki działają, tylko na innych korpusach: GraphRAG mierzono na pytaniach sensemaking nad milionem tokenów, CRAG tam, gdzie retrieval bywa całkowicie chybiony. Nasze pytania są lokalne, a odpowiedź niemal zawsze siedzi w dwudziestce – trzeba ją lepiej uszeregować, nie dokładać nowej.

## Podsumowanie

- Pytania porównawcze, relacyjne i globalne psują się na podobieństwie z jednego powodu: ranking nagradza koncentrację, a one wymagają pokrycia dwóch miejsc.
- Graf sekcji zbudujesz bez modelu z trzech warstw – jawnych odwołań w prozie, wspólnych identyfikatorów i sąsiedztwa – w stu liniach kodu, ale nie poprawił on tu żadnej metryki: recall@5 stoi na 0,72 albo spada, a kontrolna deduplikacja po sekcjach daje tyle samo bez grafu.
- Mechanizm porażki jest mierzalny: 89 procent brakujących sekcji leży o jeden skok, ale na medianowej pozycji siódmej listy sąsiadów, więc graf ma zasięg bez precyzji.
- Na modelu z rodziny E5 każda addytywna premia musi być skalowana do rozstępu wyników, a nie do ich wartości; `beta` równe 0,05 obniżyło recall@5 z 0,72 do 0,38.
- Jeden przebieg ekstrakcji encji z tego korpusu to 0,577 dolara na `claude-haiku-4-5`, czyli równowartość pięćdziesięciu zapytań – i płacisz go od nowa przy każdej zmianie dokumentu, bo aktualizacja wymaga scalania nazw encji, a nie jednego hasha.
- GraphRAG opłaca się przy gęstej sieci relacji między nazwanymi bytami (umowy, systemy, osoby) i przy pytaniach o cały zbiór; przy dokumentacji liniowej nie ma czego wydobywać.
- Iteracyjne wyszukiwanie kosztuje przy czterech krokach 3,7 raza tyle co jedno zapytanie, a jego wartość siedzi w opisie narzędzia – w zdaniu mówiącym, kiedy szukać **ponownie**.
- Z corrective RAG przeżywa tylko część oceniająca: cross-encoder podnosi recall@5 z 0,72 do 0,85, a druga tura z pseudo-relevance feedback nie zmienia ani jednego pytania.

## Co dalej

Rozdział 8 zamyka tom i zajmuje się tym, co dzieje się z systemem po wdrożeniu: przyrostową aktualizacją indeksu, cache'owaniem, budżetem kosztu i latencji oraz śladem, z którego odtworzysz nieudane zapytanie. Zabierasz tam nawyk, żeby przed wdrożeniem techniki sprawdzić, czy jej mechanizm ma zaczepienie w Twoich danych. Uruchom najpierw `experiments/07_graph.py` na własnym korpusie: jeżeli brakujące dokumenty leżą u Ciebie na trzeciej pozycji listy sąsiadów, ten rozdział skończy się inaczej.

## Źródła

- https://arxiv.org/abs/2404.16130
- https://arxiv.org/abs/2310.11511
- https://arxiv.org/abs/2401.15884
- https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- https://platform.claude.com/docs/en/about-claude/pricing
