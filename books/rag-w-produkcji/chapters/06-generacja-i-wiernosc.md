# Rozdział 6. Generacja, cytowania i wierność odpowiedzi

> **Cel rozdziału:** zamienić wynik wyszukiwania w odpowiedź, o której da się w kodzie orzec, czy pochodzi z korpusu, czy z wyobraźni modelu.
>
> **Kod:** `ragbook/answer.py`, `ragbook/judge.py`, `experiments/06_prompt_tokens.py`, `experiments/06_threshold.py`, `experiments/06_citations.py`, `experiments/06_generate.py`. **Pakiety poza fundamentem:** `pip install anthropic tiktoken`.

Przez pięć rozdziałów mierzyliśmy jedno: czy właściwy fragment trafia do promptu. To sufit jakości całego systemu, ale sufit to nie podłoga. Nad tym, co model z tymi fragmentami zrobi, metryki wyszukiwania nie mają żadnej władzy.

Weź pytanie „Ile tokenów dokłada się do promptu, gdy wymuszę użycie narzędzia parametrem `tool_choice`?”. Wyszukiwanie spisuje się wzorowo: właściwa sekcja rozdziału 9 tomu 1 jest w piątce, a we fragmencie stoją obie liczby – 286 tokenów przy `auto` i `none`, 406 przy `any` i `tool`. Model odpowiada poprawnie i dokłada trzecie zdanie, o zachowaniu tego narzutu przy cache'owaniu promptu. Tego zdania nie ma w żadnym z pięciu fragmentów; model wziął je z treningu i postawił obok dwóch prawdziwie zacytowanych, gdzie wygląda dokładnie tak samo jak one.

Drugi układ jest groźniejszy. Pytanie „Jak skonfigurować HorizontalPodAutoscaler dla wdrożenia z modelem w Kubernetesie?” nie ma w korpusie odpowiedzi, ale wyszukiwanie nie zna pojęcia „nic nie znalazłem” – zawsze zwróci `k` fragmentów:

```text
question: Jak skonfigurować HorizontalPodAutoscaler dla wdrożenia z modelem w Kubernetesie?
  [1] score=0.861  r6 / Zastosowania
  [2] score=0.860  r8 / Sposoby implementacji
  [3] score=0.858  r8 / Sposoby implementacji
  [4] score=0.857  r2 / Rodzaje modeli w skrócie
  [5] score=0.853  r12 / Obserwowalność
```

Pięć fragmentów o wdrażaniu modeli, zero zdań o Kubernetesie – a wyniki wyglądają jak każde inne trafienie. Model dostaje polecenie „odpowiadaj z kontekstu” i materiał ocierający się o temat, więc odpowiada wiedzą ogólną o autoskalowaniu i cytuje fragment [2], bo pada w nim słowo „wdrożenie”. Formalnie spełnia regułę o cytowaniu, merytorycznie kłamie o zawartości korpusu – i wygląda przy tym jak poprawne działanie.

Stąd cztery kroki: prompt, który daje modelowi sposób wskazania źródła; cytowania w dwóch wariantach, między którymi trzeba wybrać; weryfikacja cytatu w kodzie; wreszcie odmowa i pomiar wierności sędzią modelowym. Kod trafia do `ragbook/answer.py`, następcy `ragbook/generate.py` z rozdziału 1 – to samo miejsce w potoku, tylko zwraca obiekt zamiast stringa.

Ten rozdział jako jedyny w tomie wymaga klucza API. Wyniki lokalne – rozmiary promptów, rozkłady score'ów, pokrycie n-gramów, arytmetyka zgodności sędziego – policzysz bez niego, a odpowiedzi modelu są oznaczone jako „Przykładowy wynik:”. Resztę odtworzysz, ustawiając `ANTHROPIC_API_KEY` i uruchamiając z katalogu `code/` polecenie `../.venv/bin/python experiments/06_generate.py`: sześć pytań to około 5,6 tysiąca tokenów wejścia na `claude-opus-5`, poniżej trzech centów, plus tyle samo na sędziego `claude-haiku-4-5` za mniej niż cent.

## Prompt z kontekstem i jego granice

Prompt do generacji ma trzy zadania: dostarczyć fragmenty, dać modelowi sposób na wskazanie, którego użył, i nie pozwolić mu wyjść poza nie. Pierwsze dwa załatwia numeracja.

Fragmenty numerujemy od jedynki i numer jest jedynym kluczem cytowania – nie identyfikator chunku (`c00889` nic nie mówi modelowi i łatwo go przekręcić) ani nazwa sekcji (powtarza się, bo jedna sekcja daje kilka chunków). Do numeru dokładamy rozdział i nagłówek sekcji: dzięki nim model widzi, że fragmenty [1] i [5] są z tego samego miejsca, i nie bierze ich za dwa niezależne potwierdzenia faktu.

```python
from ragbook.corpus import Chunk


def format_context(chunks: list[Chunk], with_meta: bool = True) -> str:
    """Render retrieved chunks as numbered fragments. Numbering is 1-based and is the citation key."""
    parts = []
    for i, c in enumerate(chunks, start=1):
        if with_meta:
            title = c.meta.get("title", "")
            section = c.section or "wstęp"
            head = f"[{i}] rozdział {c.chapter} „{title}” / sekcja „{section}”"
        else:
            head = f"[{i}]"
        parts.append(f"{head}\n{c.text.strip()}")
    return "\n\n".join(parts)


def build_prompt(question: str, chunks: list[Chunk], with_meta: bool = True) -> str:
    """Context first, question last - the order the long-context guidance asks for."""
    return (f"<context>\n{format_context(chunks, with_meta)}\n</context>\n\n"
            f"<question>{question}</question>")
```

Kolejność jest z dokumentacji, nie z przeczucia: dane na górze, pytanie na samym dole, granice oznaczone tagami XML. Im dłuższe wejście, tym gorzej model przywołuje fakt ze środka (tom 1, rozdział 4). Przy naszym tysiącu tokenów efekt jest niewielki, ale kosztuje zero.

Ile fragmentów? Tu decyduje arytmetyka, którą policzysz lokalnie. `experiments/06_prompt_tokens.py` buduje prawdziwe prompty dla wszystkich 49 pytań pozytywnych i mierzy je dwoma tokenizatorami – `tiktoken` w kodowaniu `o200k_base` i tokenizatorem e5. Oba są przybliżeniem, bo Claude ma własny, a różnica między nimi mówi, jak grubym.

| k | tokeny promptu (o200k) | tokeny e5 | koszt wejścia (Opus 5) |
|---|---|---|---|
| 1 | 333 | 185 | 0,00166 USD |
| 5 | 987 | 775 | 0,00494 USD |
| 10 | 1788 | 1506 | 0,00894 USD |
| 20 | 3395 | 2979 | 0,01698 USD |

Skrypt: `experiments/06_prompt_tokens.py` – wypisuje też wartości pośrednie i rozrzut między pytaniami.

Większe `k` w tym korpusie się nie opłaca. Przejście z piątki na dziesiątkę to **plus 81 procent tokenów wejścia**, a pokrycie rośnie z 40 do 44 pytań na 49 – przy milionie zapytań tysiące dolarów miesięcznie za osiem punktów procentowych. Ten sam skrypt pokazuje dlaczego: pierwszy trafny fragment ląduje na pierwszej pozycji w 28 pytaniach, na drugiej w 6, a poza piątką dochodzą już tylko cztery. Poprawa należy więc do kolejności, nie do objętości – czyli do rerankingu z rozdziału 3, a `k` zostaje równe 5.

Zostaje trzecie zadanie promptu: nie pozwolić modelowi wyjść poza fragmenty. Sama instrukcja „odpowiadaj tylko z kontekstu” tego nie robi, bo nie mówi nic o tym, czy kontekst dotyczy pytania. Potrzebny jest schemat, który pozwala odmówić, i mechanizm, który tę odmowę wymusza.

## Cytowania

Cytowanie da się zrobić na dwa sposoby i to wybór architektoniczny, nie szczegół implementacyjny. Albo pozwalasz API znaczyć cytaty za siebie: wkładasz fragmenty jako bloki `document`, a model dostaje do nich zakreślacz i w odpowiedzi wracają dosłowne wycinki tekstu z numerem dokumentu. Albo numerujesz fragmenty sam i każesz modelowi wypełnić formularz: schemat z polami „czy da się odpowiedzieć”, „odpowiedź” i „numery użytych fragmentów”.

Obu naraz mieć nie można – cytowania włączone razem z parametrem `output_config.format` zwracają 400, bo bloki cytowań przeplatają się z tekstem, a sztywny schemat JSON tego nie przewiduje. Pierwsza droga daje cytat, który na pewno istnieje, ale odpowiedź wraca jako ciąg bloków tekstu; druga daje obiekt dla kodu, ale numery pisze model, więc mogą być zmyślone. Pytanie rozstrzygające: cytat ma trafić do oczu użytkownika czy do instrukcji warunkowej?

### Droga pierwsza: Citations API

Włączasz je, ustawiając `citations: {"enabled": true}` na bloku treści typu `document`; dokumenty idą do wiadomości użytkownika przed tekstem pytania. Tom 1, rozdział 8 pokazał wariant z blokami `search_result` – tutaj używamy `document`, bo chcemy kontrolować granulację cytatu.

```python
from ragbook.corpus import Chunk


def document_blocks(chunks: list[Chunk], cache_last: bool = False) -> list[dict]:
    """One `document` content block per chunk, citations on. Citation indices then point at our chunks."""
    blocks = []
    for c in chunks:
        blocks.append({
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": c.text.strip()},
            "title": f"r{c.chapter}: {c.section}"[:200],
            "context": f'{{"chapter": {c.chapter}, "section": "{c.section}", "chunk_id": "{c.id}"}}',
            "citations": {"enabled": True},
        })
    if cache_last and blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks
```

Dwa szczegóły z dokumentacji decydują o kształcie tego kodu (stan na wrzesień 2026). `title` i `context` widzi model, ale **nie są treścią cytowalną** – cytowany może być wyłącznie tekst z `source`, więc metadane chunku idą do `context` i nie wrócą jako fakt z korpusu. A jeden blok `document` na chunk daje mapowanie jeden do jednego: `document_index` w odpowiedzi to numer naszego fragmentu, liczony od zera.

Odpowiedź rozpada się na ciąg bloków tekstowych. Blok cytujący niesie listę `citations`, a w niej trzy potrzebne rzeczy: `cited_text` (dosłowny wycinek), `document_index` i granice w źródle – `start_char_index` z `end_char_index` dla tekstu, numery stron dla PDF-a. Bloki bez cytowania mają tę listę pustą i to one są ciekawe: ich udział w odpowiedzi jest gotową metryką „ile model dopowiedział od siebie”.

Przykładowy wynik:

```text
  [1] Deklaracja narzędzi dokłada systemowy prefiks: 286 tokenów przy `auto` i `none`
       cited_text: dla Claude Opus 5 przy `tool_choice` `auto` lub `none` to 286 tokenów, a przy `any`
  [1] oraz 406 tokenów przy `any` i `tool`
       cited_text: a przy `any` lub `tool` – 406 tokenów
  [-] Przy włączonym prompt cachingu ten narzut płacisz tylko przy pierwszym wywołaniu.
```

Trzecia linia to przypadek z otwarcia rozdziału: zdanie, którego model nie podparł niczym, stojące obok dwóch podpartych.

Dokument tekstowy (`source.type: "text"`) API dzieli na zdania samo, więc cytatem jest zdanie chunku; jeśli chunk ma być cytowany w całości, wstaw go jako dokument z własną treścią. I drobiazg z rachunku: `cited_text` nie liczy się do tokenów wyjściowych ani wejściowych, więc cytowanie przez API jest tańsze niż proszenie modelu o dosłowne cytaty w prompcie.

### Droga druga: własne numery i schemat

Structured outputs opisuje tom 1, rozdział 3; tutaj liczy się tylko to, co wkładamy do modelu Pydantic.

```python
import os
from anthropic import Anthropic
from pydantic import BaseModel, Field

from ragbook.answer import SYSTEM, build_prompt


class Answer(BaseModel):
    """Schema the model must fill. `citations` are 1-based fragment numbers from the prompt."""
    answerable: bool = Field(description="True only if the fragments contain the answer")
    text: str = Field(description="The answer in Polish, or one sentence saying what is missing")
    citations: list[int] = Field(description="1-based numbers of the fragments used; empty if not answerable")


client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generate_answer(question: str, chunks) -> Answer:
    response = client.messages.parse(
        model="claude-opus-5",
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_prompt(question, chunks)}],
        output_format=Answer,
    )
    return response.parsed_output
```

Kolejność pól nie jest przypadkowa. `answerable` stoi pierwsze, bo model wypełnia schemat po kolei i decyzja „czy da się odpowiedzieć” ma zapaść przed odpowiedzią. Gdyby `text` był pierwszy, model musiałby zaprzeczyć czemuś, co przed chwilą napisał – a tego modele nie lubią i dopisują `answerable: true` do wszystkiego. Kształt schematu steruje rozumowaniem; to ta sama sztuczka co pole `unsupported_claims` u sędziego z tomu 1, rozdziału 12.

Instrukcja systemowa domyka trzy rzeczy i nic więcej:

```text
1. Use only the numbered fragments in <context>. Your own knowledge about LLMs, APIs and
   libraries is not evidence and must not appear in the answer.
2. Every sentence that states a fact must end with the numbers of the fragments it comes from,
   in square brackets: [2] or [2][5].
3. If the fragments do not contain the answer, set answerable to false, leave citations empty
   and write one sentence saying what is missing. Do not guess, do not approximate.
```

Zdanie drugie w regule 1 jest ważniejsze, niż wygląda, i wraca wprost do przykładu z otwarcia rozdziału. „Odpowiadaj tylko z kontekstu” model rozumie jako „nie zmyślaj”, a nie jako „nie używaj tego, co i tak wiesz” – a nasz korpus to podręcznik o API, o których model wie z treningu sporo. Bez jawnego wykluczenia wiedzy własnej dostaniesz odpowiedzi poprawne merytorycznie i niecytowalne.

W tym projekcie zostaje droga druga, bo odpowiedź jest u nas wejściem dla kodu: `answerable` to bool, a nie zdanie do sparsowania. Citations API zostaje opcją dla trybu „pokaż źródła”, gdzie `cited_text` podświetlisz użytkownikowi.

### Weryfikacja cytatów w kodzie

Skoro numery pisze model, może je przekręcić – i to jedyna słabość drugiej drogi. Wykryjesz ją lokalnie, bez drugiego wywołania modelu, prostym pytaniem: czy zdanie odpowiedzi ma **wspólne trzy słowa pod rząd** z fragmentem, który przy nim stoi? Zdanie sprowadzamy do małych liter bez polskich znaków, tniemy na trójki kolejnych słów i liczymy, jaka ich część stoi we wskazanym fragmencie. To pokrycie trigramów.

```python
from ragbook.answer import check_citations

for chk in check_citations(answer.text, chunks, answer.citations):
    print(f"[{','.join(map(str, chk.cited)) or '-'}] cov={chk.coverage_cited:.2f} "
          f"best={chk.coverage_best:.2f}@[{chk.best_chunk}] {chk.status}")
```

Funkcja liczy pokrycie dwa razy: we wskazanym fragmencie i w najlepszym fragmencie z całej piątki. Z zestawienia tych dwóch liczb bierze się jeden z czterech statusów: `ok`, `wrong-chunk` (zdanie jest w kontekście, ale pod innym numerem), `low-overlap` (nie ma go nigdzie) i `no-citation`.

Czy to w ogóle rozróżnia? `experiments/06_citations.py` liczy pokrycie wzorcowej odpowiedzi z golden setu w chunku z trafnej sekcji, w pozostałych chunkach z piątki i w chunku losowym. Dla kontroli robi to samo ze zdaniem wyjętym wprost z fragmentu, czyli z odpowiedzią czysto ekstrakcyjną.

| twierdzenie vs fragment | przypadków | średnia | mediana | p90 |
|---|---|---|---|---|
| odpowiedź wzorcowa vs trafna sekcja | 94 | 0,109 | 0,000 | 0,333 |
| odpowiedź wzorcowa vs inny z top-5 | 151 | 0,007 | 0,000 | 0,000 |
| odpowiedź wzorcowa vs losowy chunk | 49 | 0,000 | 0,000 | 0,000 |
| zdanie z fragmentu vs ten fragment | 40 | 1,000 | 1,000 | 1,000 |

Skrypt: `experiments/06_citations.py`.

Test jest bardzo precyzyjny i mało czuły. Fragment nietrafny praktycznie nigdy nie przepuszcza twierdzenia – 0,007 to szum – więc pokrycie **powyżej** progu jest mocnym sygnałem, że cytat jest prawdziwy. W drugą stronę jest gorzej: wzorcowa odpowiedź to ludzka parafraza, a nie cytat, i przy progu 0,05 przechodzi jej tylko 33 procent. Ostatni wiersz wyznacza drugi koniec skali: gdy model cytuje dosłownie, pokrycie wynosi 1,0.

Stąd wniosek: pokrycie n-gramów nadaje się na **alarm, nie na bramkę**. Zdanie, którego słownictwa nie ma w żadnym z pięciu fragmentów, trafia do kolejki przeglądu; zdanie z pokryciem zero we wskazanym fragmencie, ale wysokim w innym, ma przekręcony numer i poprawisz je automatycznie. Odrzucanie odpowiedzi za to, że model ładnie sparafrazował, kosztowałoby więcej niż problem, który rozwiązuje. Cztery statusy na czterech ręcznych przypadkach wyglądają tak:

```text
cytat z fragmentu        cited=[1] cov_cited=1.000 cov_best=1.000@[1] -> ok
ten sam cytat, zły numer cited=[2] cov_cited=0.000 cov_best=1.000@[1] -> wrong-chunk
parafraza wzorcowa       cited=[1] cov_cited=0.167 cov_best=0.167@[1] -> ok
twierdzenie zmyślone     cited=[1] cov_cited=0.000 cov_best=0.000@[None] -> low-overlap
```

## Odmowa, gdy nie ma podstaw

Pole `answerable` daje modelowi wyjście awaryjne, ale ktoś musi je wymusić. Naturalny pomysł brzmi: skoro wyszukiwanie zwraca score, to przy zbyt niskim w ogóle nie pytajmy modelu – zaoszczędzimy wywołanie i zamkniemy drogę do konfabulacji.

Na kosinusie to nie działa. `experiments/06_threshold.py` bierze najlepszy wynik kosinusowy dla 49 pytań pozytywnych i 7 negatywnych; rozkłady nakładają się na całej długości, bo kosinus mierzy podobieństwo do najbliższego wektora, a najbliższy zawsze jakiś jest. Próg odcinający wszystkie siedem pytań negatywnych odrzuca przy okazji **19 z 49 pytań, na które system umie odpowiedzieć**. Progu odmowy nie stawia się więc na surowym kosinusie e5.

Sygnał musi być inny, a w tym potoku już jest. Cross-enkoder z rozdziału 3 jest trenowany wprost na pytaniu „czy ten dokument odpowiada na to pytanie”, więc rozdziela oba przypadki ostrzej: próg −2 odcina cztery z siedmiu pytań negatywnych, nie tracąc ani jednego pozytywnego, i liczy się przy okazji rerankingu. Pozostałe trzy musi zatrzymać model, więc ostateczną bramką zostaje `answerable`, a próg w `ragbook.answer` jest parametrem domyślnie wyłączonym.

## Wierność odpowiedzi

Zanim cokolwiek policzymy, jedna tabelka – najszybsze narzędzie diagnostyczne, jakie ma zespół RAG-owy. Wyszukiwanie i generacja psują się niezależnie, więc ustaw je na dwóch osiach.

| | odpowiedź wierna | odpowiedź niewierna |
|---|---|---|
| **retrieval trafny** | działa – nic nie rób | usterka generacji: popraw prompt, schemat, model; dołóż weryfikację cytatów |
| **retrieval nietrafny** | poprawna odmowa – dobrze; policz, ile ich jest, bo to koszt recall | najgorsza ćwiartka: system kłamie wiarygodnie, napraw retrieval, nie prompt |

Klucz jest w dolnym wierszu. Po lewej stoi system, który nie kłamie, tylko nie odpowiada – jeśli mierzysz wyłącznie wierność, wygląda doskonale. Po prawej stoi przykład z Kubernetesem, a naprawia się go w rozdziałach 2–4: poprawianie promptu, gdy zawodzi wyszukiwanie, jest najczęstszym marnotrawstwem w projektach RAG.

Samą wierność (faithfulness, groundedness) definiuje się przez rozbicie: dzielisz odpowiedź na atomowe twierdzenia i dla każdego sprawdzasz, czy wynika z kontekstu; wynik to udział twierdzeń wspartych. Na poziomie twierdzenia jest zerojedynkowa, więc nie wymaga od sędziego skali, na której zawsze się rozjeżdża, a niewsparte twierdzenie jest cytowalne w raporcie. Nie miesza się też z trafnością: odpowiedź może być w stu procentach wierna i zupełnie nie na temat.

Sędzia dostaje ten sam kontekst co generator i schemat wyjścia, który wymusza rozbicie przed werdyktem.

```python
from pydantic import BaseModel, Field

from ragbook.answer import format_context
from ragbook.judge import JUDGE_SYSTEM


class ClaimVerdict(BaseModel):
    claim: str = Field(description="One atomic claim from the answer, in its original language")
    verdict: str = Field(description='"supported", "contradicted" or "missing"')
    evidence: str = Field(description="Verbatim fragment text supporting the verdict, empty if missing")


class FaithfulnessReport(BaseModel):
    claims: list[ClaimVerdict]


def judge_faithfulness(client, question: str, answer: str, chunks) -> FaithfulnessReport:
    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=[{"type": "text", "text": JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   f"<context>\n{format_context(chunks)}\n</context>\n"
                   f"<question>{question}</question>\n<answer>{answer}</answer>"}],
        output_format=FaithfulnessReport,
    )
    return response.parsed_output
```

Trzy decyzje w tej rubryce są nieoczywiste (tom 1, rozdział 12). Sędzią jest `claude-haiku-4-5`, a nie model, który generował – modele faworyzują własne odpowiedzi, a przy zadaniu tak prostym tańszy wystarcza. Werdykt ma trzy wartości: `missing` (kontekst milczy) to co innego niż `contradicted` (kontekst mówi coś przeciwnego), a mieszanie ich zaciera różnicę między wierszami macierzy. I rubryka mówi wprost, że twierdzenie prawdziwe w ogólności, ale nieobecne we fragmentach, jest `missing` – bez tego zdania sędzia ocenia własną wiedzę, nie ugruntowanie.

```python
from ragbook.judge import FaithfulnessReport


def faithfulness_score(report: FaithfulnessReport) -> float:
    """Supported claims / all claims - the same definition RAGAS uses. An empty answer scores 1.0."""
    if not report.claims:
        return 1.0
    return sum(1 for c in report.claims if c.verdict == "supported") / len(report.claims)
```

Przykładowy wynik dla pytania negatywnego, na które model odpowiedział z wiedzy własnej:

```text
faithfulness=0.33 (3 claims)
  supported     HorizontalPodAutoscaler skaluje liczbę replik.
  missing       Metryką skalującą bywa wykorzystanie GPU.
  missing       Dla modeli LLM zaleca się skalowanie po długości kolejki.
```

### Kalibracja sędziego

Sędzia jest modelem, więc sam się myli, i dopóki nie wiesz jak bardzo, jego liczby są dekoracją. Sprawdzenie zajmuje godzinę: bierzesz trzydzieści odpowiedzi z prawdziwego ruchu i oznaczasz je ręcznie jedną binarną etykietą – „czy jest tu twierdzenie bez pokrycia w kontekście”. Trzydzieści, bo tyle człowiek przeczyta na jedno posiedzenie, a do decyzji „ufać czy nie” wystarczy próbka, na której gruby rozjazd widać gołym okiem.

Potem puszczasz sędziego na tych samych trzydziestu i liczysz dwie liczby. Zgodność surowa mówi, w jakiej części przypadków macie tę samą etykietę, i pochlebia, bo sędzia mówiący zawsze „ok” zgarnia za darmo wszystkie odpowiedzi czyste – a tych jest zwykle większość. Kappa Cohena odejmuje tę zgodność, którą dostalibyście przez przypadek, i dlatego to ją się raportuje.

```python
from ragbook.judge import agreement, cohen_kappa, confusion

# Illustrative labels: 30 answers, 22 clean by the human, 8 with an unsupported claim.
human = ["ok"] * 22 + ["hallucination"] * 8
judge = ["ok"] * 19 + ["hallucination"] * 3 + ["ok"] * 3 + ["hallucination"] * 5

print(f"zgodnosc = {agreement(human, judge):.2f}")
print(f"kappa    = {cohen_kappa(human, judge):.2f}")
for k, v in sorted(confusion(human, judge).items()):
    print(f"  czlowiek={k[0]:14s} sedzia={k[1]:14s} {v}")
```

```text
zgodnosc = 0.80
kappa    = 0.49
  czlowiek=hallucination  sedzia=hallucination  5
  czlowiek=hallucination  sedzia=ok             3
  czlowiek=ok             sedzia=hallucination  3
  czlowiek=ok             sedzia=ok             19
```

Etykiety są tu przykładowe, ale arytmetyka prawdziwa i pokazuje właśnie tę pułapkę. Osiemdziesiąt procent zgodności brzmi świetnie, a kappa 0,49 mówi, że po odjęciu przypadku zostaje niecała połowa. Taki sędzia nadaje się do porównywania wersji („po zmianie promptu wierność wzrosła z 0,71 do 0,82”), ale nie do raportowania wartości bezwzględnej. Progi do zapamiętania: poniżej 0,4 sędzia jest szumem, 0,4–0,6 nadaje się do porównań, powyżej 0,6 możesz cytować samą liczbę. Macierz pomyłek czyta się osobno: trzy fałszywe alarmy i trzy przeoczenia to sędzia zrównoważony, a osiem alarmów i zero przeoczeń to sygnał, żeby poluzować rubrykę.

### RAGAS i DeepEval

Własnego sędziego pisze się tylko wtedy, gdy potrzebujesz czegoś, czego gotowa metryka nie daje; jak wpiąć obie biblioteki w testy regresyjne, pokazuje tom 1, rozdział 12. Tutaj liczy się mapa: która metryka mierzy który etap i czego wymaga na wejściu (stan na wrzesień 2026).

| Co mierzy | RAGAS | DeepEval | Wejście |
|---|---|---|---|
| wierność odpowiedzi wobec kontekstu | `Faithfulness` (nowe: `ragas.metrics.collections.Faithfulness`), wariant `FaithfulnesswithHHEM` bez LLM-a | `FaithfulnessMetric` | odpowiedź + kontekst |
| trafność odpowiedzi wobec pytania | `ResponseRelevancy` (nowe: `AnswerRelevancy`), wymaga modelu embeddingów | `AnswerRelevancyMetric` | pytanie + odpowiedź |
| precyzja kontekstu (ranking) | `LLMContextPrecisionWithoutReference`, `LLMContextPrecisionWithReference`, `NonLLMContextPrecisionWithReference`, `IDBasedContextPrecision` | `ContextualPrecisionMetric` | pytanie + konteksty (+ wzorzec) |
| pokrycie kontekstu | `LLMContextRecall`, `NonLLMContextRecall`, `IDBasedContextRecall` | `ContextualRecallMetric` | wzorzec + konteksty |
| wrażliwość na szum w kontekście | `NoiseSensitivity` | `ContextualRelevancyMetric` | pytanie + konteksty + odpowiedź |
| kryterium własne | – | `GEval` (kryterium jednym zdaniem, próg 0–1) | wybrane pola przypadku |

Dwie różnice praktyczne. Biblioteki inaczej nazywają pola przypadku (`user_input`, `retrieved_contexts`, `response` i `reference` wobec `input`, `retrieval_context`, `actual_output` i `expected_output`), a DeepEval wymaga wzorca tam, gdzie RAGAS pozwala liczyć precyzję bez niego. I `Faithfulness` w RAGAS liczy dokładnie to, co nasz sędzia – jeśli chcesz porównywalności z literaturą, użyj gotowej implementacji.

## Strumień i cache

Cytowania działają w trybie strumieniowym: przychodzą jako delta typu `citations_delta` wewnątrz zdarzenia `content_block_delta`, zawsze po tekście, który wspierają. Interfejs może więc renderować zdanie od razu i dokleić znacznik, gdy cytowanie dotrze.

```python
from ragbook.answer import SYSTEM, document_blocks


def stream_with_citations(client, question: str, chunks, model: str = "claude-opus-5"):
    """Yield ("text", str) and ("citation", citation) pairs as they arrive."""
    with client.messages.stream(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM}],
        messages=[{"role": "user", "content": document_blocks(chunks)
                   + [{"type": "text", "text": question}]}],
    ) as stream:
        for event in stream:
            if event.type != "content_block_delta":
                continue
            if event.delta.type == "text_delta":
                yield "text", event.delta.text
            elif event.delta.type == "citations_delta":
                yield "citation", event.delta.citation
```

Prompt caching wygląda tu na oczywistą oszczędność i w naszym projekcie nią nie jest – warto wiedzieć dlaczego, zanim dołożysz `cache_control` odruchowo. Mechanikę opisuje tom 1, rozdział 3, a istotna jest jedna liczba: Claude Opus 5 zapisze prefiks do cache dopiero od 512 tokenów (stan na wrzesień 2026), a nasz system prompt ma ich 138. Jest o rząd wielkości za krótki, więc `cache_control` na nim nie robi nic i nie zwraca przy tym błędu – `cache_read_input_tokens` zostaje zerem. Sensowny jest dopiero prefiks rozbudowany o przykłady few-shot ponad próg albo `cache_control` na blokach `document`, gdy te same chunki wracają w większości zapytań; do tego wrócimy w rozdziale 8. Breakpoint stawia się wtedy na ostatnim bloku wspólnego prefiksu, a zmiana schematu `output_config.format` unieważnia cache całego wątku.

## Co zostaje w projekcie

| Decyzja | Wybór | Dlaczego |
|---|---|---|
| liczba fragmentów w prompcie | `k` = 5 | +81% tokenów wejścia za +8 pkt proc. pokrycia przy `k` = 10 to zły interes; poprawa należy do rerankingu |
| format kontekstu | numerowane fragmenty z rozdziałem i sekcją | numer jest kluczem cytowania; metadane odbudowują kontekst ucięty przez chunker |
| schemat odpowiedzi | `Answer(answerable, text, citations)` przez `messages.parse` | `answerable` jako bool przed `text`; odpowiedź jest wejściem dla kodu, nie tekstem do parsowania |
| cytowania | własne numery domyślnie, Citations API dla trybu „pokaż źródła” | structured outputs i cytowania wykluczają się (400); w kodzie potrzebujemy schematu |
| weryfikacja cytatów | pokrycie trigramów jako alarm, nie bramka | precyzja wysoka (0,007 na fragmentach nietrafnych), czułość niska (33% przy progu 0,05) |
| próg pewności z retrievalu | wyłączony (parametr, domyślnie 0,0) | na kosinusie próg odcinający wszystkie negatywne kosztuje 19 z 49 pytań; tanim filtrem jest dopiero score cross-enkodera z rozdziału 3 |
| sędzia wierności | `claude-haiku-4-5`, trzy werdykty, w CI na całym golden secie | inny model niż generator; `missing` osobno od `contradicted` rozdziela winę retrievalu i generacji |
| kalibracja sędziego | 30 ręcznych etykiet, raportowana kappa | poniżej 0,4 sędzia jest szumem; bez tej liczby jego wyniki nie znaczą nic |

## Podsumowanie

- Fragmenty w prompcie numerujemy od jedynki i doklejamy rozdział oraz sekcję; numer jest jedynym kluczem cytowania, który da się sprawdzić w kodzie.
- `k` = 5 zamiast 10 to 81 procent mniej tokenów wejścia za osiem punktów procentowych pokrycia; lekarstwem na braki jest ranking, nie objętość.
- Instrukcja „tylko z kontekstu” nie chroni przed kontekstem nietrafnym, bo wyszukiwanie zawsze zwróci `k` fragmentów; odmowa musi być osobnym mechanizmem.
- Cytowanie ma dwie drogi i trzeba wybrać jedną: Citations API daje cytat, który na pewno istnieje, własne numery ze structured outputs dają obiekt dla kodu, a razem zwracają 400.
- Pokrycie n-gramów weryfikuje cytat lokalnie i za darmo, ale jest precyzyjne i mało czułe – nadaje się na alarm i na wykrywanie przekręconego numeru, nie na bramkę.
- Próg na surowym kosinusie e5 nie rozdziela pytań pozytywnych od negatywnych: odcięcie wszystkich siedmiu negatywnych kosztuje 19 z 49 pozytywnych, a użytecznym sygnałem jest dopiero wynik cross-enkodera z rozdziału 3.
- Retrieval i generacja psują się niezależnie, więc czytaj je jako macierz dwa na dwa: wierna odpowiedź przy nietrafnych fragmentach to odmowa, niewierna przy trafnych to usterka promptu.
- Wierność to udział twierdzeń wspartych kontekstem; sędzia ma być innym, tańszym modelem z trzecim werdyktem `missing`, a bez trzydziestu ręcznych etykiet i kappy Cohena jego liczby są dekoracją.

## Co dalej

Rozdział 7 wychodzi poza podobieństwo wektorowe: pokazuje GraphRAG dla pytań typu „jak X wiąże się z Y” i agentic RAG, w którym model sam decyduje, czy wyszukać jeszcze raz – buduje więc na `answerable` i na sędzim z tego rozdziału, bo to one dają sygnał „to, co znalazłem, nie wystarcza”. Zanim tam przejdziesz, uruchom `experiments/06_generate.py` z własnym kluczem i przejrzyj ręcznie wyniki `check_citations`: kolejka przypadków `wrong-chunk` i `low-overlap` powie Ci o Twoim prompcie więcej niż jakakolwiek średnia.

## Źródła

- https://platform.claude.com/docs/en/build-with-claude/citations
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/build-with-claude/streaming
- https://platform.claude.com/docs/en/build-with-claude/search-results
- https://platform.claude.com/docs/en/build-with-claude/token-counting
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
- https://deepeval.com/docs/metrics-introduction
- https://deepeval.com/docs/metrics-contextual-precision
- https://deepeval.com/docs/metrics-contextual-recall
