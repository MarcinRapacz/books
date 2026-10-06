# Rozdział 6. Generacja, cytowania i wierność odpowiedzi

> **Cel rozdziału:** zamienić wynik wyszukiwania w odpowiedź, o której da się w kodzie orzec, czy pochodzi z korpusu, czy z wyobraźni modelu.
>
> **Kod:** `ragbook/answer.py`, `ragbook/judge.py`, `experiments/06_prompt_tokens.py`, `experiments/06_threshold.py`, `experiments/06_citations.py`, `experiments/06_generate.py`. **Pakiety poza fundamentem:** `pip install anthropic tiktoken`.

Do tej pory mierzyliśmy wyszukiwanie i tylko wyszukiwanie. Recall@5 mówi, czy właściwa sekcja w ogóle trafiła do promptu, i jest sufitem jakości całego systemu – ale sufit to nie podłoga. Na bazowym potoku z rozdziału 1 (stałe okno 128 tokenów z zakładką 32, e5-small, Qdrant) co najmniej jedna trafna sekcja jest w piątce dla 40 z 49 pytań pozytywnych golden setu. Pozostaje pytanie, co się dzieje z tymi czterdziestoma: czy model odpowiada z podanych fragmentów, czy dokłada z pamięci, czy wskazuje właściwe źródło i czy potrafi powiedzieć „nie wiem" przy siedmiu pytaniach negatywnych, dla których odpowiedzi w korpusie nie ma.

To są cztery różne pytania i każde ma inną odpowiedź inżynierską. Pierwsze rozwiązuje prompt, drugie schemat wyjścia i cytowania, trzecie weryfikacja po stronie kodu, czwarte próg i sędzia modelowy. Rozdział idzie w tej kolejności i kończy się listą tego, co z tych czterech mechanizmów zostaje w projekcie na stałe. Cały kod trafia do `ragbook/answer.py` – następcy jednowywołaniowego `ragbook/generate.py` z rozdziału 1, zajmującego to samo miejsce w potoku, ale zwracającego obiekt zamiast stringa.

Jedna uczciwa uwaga na starcie, która obowiązuje przez cały rozdział. Wszystko, co dotyczy generacji, wymaga wywołania modelu, a ja piszę ten rozdział bez klucza API – więc każda odpowiedź modelu jest tu oznaczona jako „Przykładowy wynik:" i pochodzi z lektury dokumentacji, a nie z uruchomienia. Wyniki lokalne – rozmiary promptów, rozkłady score'ów z Qdranta, pokrycie n-gramów, arytmetyka zgodności sędziego – są prawdziwe i odtwarzalne bez klucza. Żeby odtworzyć część modelową, ustaw `ANTHROPIC_API_KEY` i uruchom `../.venv/bin/python experiments/06_generate.py`: sześć pytań to około 5,6 tysiąca tokenów wejścia na `claude-opus-5` (poniżej trzech centów) plus tyle samo na sędziego `claude-haiku-4-5` (poniżej jednego centa). Skrypty uruchamiasz z katalogu `code/`.

## Prompt z kontekstem i jego granice

Prompt do generacji ma trzy zadania: dostarczyć fragmenty, dać modelowi sposób na wskazanie, którego użył, i nie pozwolić mu wyjść poza nie. Każde z nich przekłada się na konkretny element struktury.

Fragmenty numerujemy od jedynki i numer jest jedynym kluczem cytowania. Nie identyfikator chunku (`c00889` nic nie mówi modelowi i łatwo go przekręcić), nie nazwa sekcji (powtarza się, bo jedna sekcja daje kilka chunków), tylko liczba porządkowa w tym konkretnym prompcie. Do numeru dokładamy metadane, których model sam nie odtworzy z tekstu uciętego w pół zdania: numer i tytuł rozdziału oraz nagłówek sekcji. To nie jest ozdoba – dzięki temu model widzi, że fragmenty [1] i [5] pochodzą z tej samej sekcji, i nie traktuje ich jako dwóch niezależnych potwierdzeń tego samego faktu.

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

Kolejność jest z dokumentacji, nie z przeczucia: dane na górze, pytanie na samym dole, granice oznaczone tagami XML. Powód opisuje tom 1, rozdział 4 – im dłuższe wejście, tym gorzej model przywołuje fakt ze środka, bo budżet uwagi jest ograniczony. Przy naszych promptach efekt jest niewielki, bo wejście ma rząd tysiąca tokenów, ale kosztuje zero i nie ma sensu z niego rezygnować. Ta sama zasada ma drugą stronę praktyczną: jeśli kiedykolwiek będziesz wstawiać do kontekstu fragmenty w kolejności innej niż rankingowa, wstaw najlepszy na początek i drugi na koniec, a nie oba w środku.

Ile fragmentów? Tu decyduje arytmetyka, którą da się policzyć lokalnie. Skrypt `experiments/06_prompt_tokens.py` buduje prawdziwe prompty dla wszystkich 49 pytań pozytywnych i liczy ich długość dwoma tokenizatorami: `tiktoken` w kodowaniu `o200k_base` i tokenizatorem e5, którego i tak używamy do chunkowania. Oba są przybliżeniem – Claude ma własny tokenizator, a dokładną liczbę da tylko `client.messages.count_tokens`, które wymaga klucza. Rozbieżność między nimi (około 20 procent na polskim tekście) jest dobrą miarą tego, jak bardzo to przybliżenie.

| k | tokeny promptu (o200k) | tokeny e5 | zakres min–max | koszt wejścia (Opus 5) |
|---|---|---|---|---|
| 1 | 333 | 185 | 249–367 | 0,00166 USD |
| 3 | 656 | 476 | 484–727 | 0,00328 USD |
| 5 | 987 | 775 | 819–1101 | 0,00494 USD |
| 8 | 1469 | 1214 | 1239–1663 | 0,00734 USD |
| 10 | 1788 | 1506 | 1452–2049 | 0,00894 USD |
| 20 | 3395 | 2979 | 2955–3758 | 0,01698 USD |

Skrypt: `experiments/06_prompt_tokens.py`. Przejście z `k` równego 5 na 10 to plus 81 procent tokenów wejścia, a z 5 na 20 – plus 244 procent. Co za to dostajesz? Ten sam skrypt wypisuje, na której pozycji ląduje pierwszy trafny chunk: w 28 pytaniach na pierwszej, w 6 na drugiej, a poza piątką trafienie pojawia się jeszcze tylko dla czterech pytań. W liczbach zbiorczych: 40 z 49 pytań ma trafienie w top-5 i 44 z 49 w top-10. Osiem punktów procentowych pokrycia za 81 procent kosztu wejścia to kiepski interes przy jednym zapytaniu, a przy milionie zapytań to różnica rzędu tysięcy dolarów miesięcznie. Stąd standardowe `k` równe 5 w tym tomie – i stąd wniosek, że właściwym miejscem na poprawę nie jest większe `k`, tylko lepszy ranking, czyli reranking z rozdziału 3.

Teraz granica, o której mówi się rzadziej niż o halucynacjach. Instrukcja „odpowiadaj tylko z kontekstu" nie chroni przed sytuacją, w której kontekst jest po prostu nietrafny. Wyszukiwanie zawsze zwróci `k` fragmentów – nie ma w nim pojęcia „nic nie znalazłem". Dla pytania negatywnego z golden setu wygląda to tak:

```text
question: Jak skonfigurować HorizontalPodAutoscaler dla wdrożenia z modelem w Kubernetesie?
  [1] score=0.861  r6 / Zastosowania
  [2] score=0.860  r8 / Sposoby implementacji
  [3] score=0.858  r8 / Sposoby implementacji
  [4] score=0.857  r2 / Rodzaje modeli w skrócie
  [5] score=0.853  r12 / Obserwowalność
```

Pięć fragmentów o wdrażaniu modeli, zero zdań o Kubernetesie. Model dostaje polecenie „odpowiadaj z kontekstu" i materiał, który tematycznie ociera się o pytanie. To jest najbardziej niebezpieczny układ w całym RAG-u, bo odpowiedź brzmi wiarygodnie, cytuje istniejące fragmenty i jest fałszywa. Sama instrukcja tego nie załatwi; potrzebny jest schemat, który pozwala modelowi odmówić, i mechanizm, który tę odmowę wymusza.

## Cytowania

### Citations API

Anthropic parsuje cytowania po swojej stronie i to jest jego przewaga nad wszystkim, co zrobisz promptem. Włączasz je, ustawiając `citations: {"enabled": true}` na bloku treści typu `document`; dokumenty wstawiasz do wiadomości użytkownika przed tekstem pytania. Tom 1, rozdział 8 pokazał wariant z blokami `search_result`; tutaj używamy bloków `document`, bo mamy własne chunki i chcemy mieć pełną kontrolę nad granulacją cytatu.

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

Trzy szczegóły z dokumentacji, które decydują o kształcie tego kodu (stan na wrzesień 2026). Po pierwsze, `title` i `context` są przekazywane modelowi, ale **nie są treścią cytowalną** – cytowany może być wyłącznie tekst z `source`. Dlatego metadane chunku idą do `context` jako sklejony JSON: model je widzi, a nie może ich zacytować jako faktu z korpusu. Po drugie, cytowania są ustawieniem „wszystko albo nic" w obrębie żądania – nie da się włączyć ich dla trzech dokumentów i wyłączyć dla dwóch. Po trzecie, jeden blok `document` na chunk daje nam mapowanie jeden do jednego: `document_index` w odpowiedzi to numer naszego fragmentu (liczony od zera, indeksowany po wszystkich blokach `document` w całym żądaniu).

Granulacja cytatu zależy od typu dokumentu. Dokument tekstowy (`source.type: "text"`) jest automatycznie dzielony na zdania i cytowania wracają jako `char_location` z polami `cited_text`, `document_index`, `document_title`, `start_char_index` i `end_char_index` (indeksy od zera, koniec wyłączny). PDF daje `page_location` ze `start_page_number` i `end_page_number` (strony od jedynki, koniec wyłączny). Jest też trzeci typ, `custom content`, w którym sam podajesz listę bloków i nie następuje żadne dalsze dzielenie – cytowania wracają wtedy jako `content_block_location` z indeksami bloków. Wybór jest prosty: jeśli chcesz, żeby model cytował pojedyncze zdania ze swojego chunku, wstaw chunk jako dokument tekstowy; jeśli chunk ma być cytowany w całości albo ma własną strukturę (punkty listy, wiersze tabeli), użyj dokumentu z własną treścią.

Odpowiedź rozpada się na ciąg bloków tekstowych, z których cytujące niosą listę `citations`, a pozostałe mają ją pustą.

```python
def flatten_citations(message) -> list[dict]:  # ragbook.answer
    """Collapse a citations-enabled Message into (claim, cited_text, document_index) rows."""
    rows = []
    for block in message.content:
        if block.type != "text":
            continue
        for cit in (getattr(block, "citations", None) or []):
            rows.append({"claim": block.text.strip(), "cited_text": cit.cited_text,
                         "document_index": cit.document_index, "type": cit.type})
        if not getattr(block, "citations", None) and block.text.strip():
            rows.append({"claim": block.text.strip(), "cited_text": None,
                         "document_index": None, "type": None})
    return rows
```

Przykładowy wynik:

```text
  [1] Deklaracja narzędzi dokłada systemowy prefiks: 286 tokenów przy `auto` i `none`
       cited_text: dla Claude Opus 5 przy `tool_choice` `auto` lub `none` to 286 tokenów, a przy `any`
  [1] oraz 406 tokenów przy `any` i `tool`
       cited_text: a przy `any` lub `tool` – 406 tokenów, plus tokeny samych definicji
  [-] Do tego dochodzą tokeny samych definicji narzędzi.
```

Udział bloków bez cytowania w całej odpowiedzi jest gotową metryką „ile model dopowiedział od siebie" i nie kosztuje nic poza jedną pętlą. Warto też wiedzieć, że `cited_text` nie liczy się do tokenów wyjściowych ani – przy odsyłaniu historii w kolejnej turze – do tokenów wejściowych; cytowanie przez API jest więc tańsze niż proszenie modelu w prompcie o dosłowne cytaty.

### Własne cytowania i structured outputs

Citations API ma jedno twarde ograniczenie: **nie da się go połączyć ze structured outputs**. Włączenie cytowań na jakimkolwiek bloku `document` albo `search_result` razem z parametrem `output_config.format` zwraca 400, bo bloki cytowań przeplatają się z tekstem, a sztywny schemat JSON tego nie przewiduje. To nie jest usterka do obejścia, tylko rozwidlenie architektury, i trzeba wybrać.

Druga droga to własne cytowania po numerach fragmentów plus schemat wyjścia. Structured outputs opisuje tom 1, rozdział 3; tutaj liczy się tylko to, co wkładamy do modelu Pydantic.

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

Kolejność pól w schemacie nie jest przypadkowa. `answerable` stoi pierwsze, bo model wypełnia schemat po kolei i decyzja „czy w ogóle da się odpowiedzieć" ma zapaść przed napisaniem odpowiedzi, a nie po. Gdyby `text` był pierwszy, model najpierw napisałby odpowiedź, a potem musiałby sam siebie zaprzeczyć – a modele tego nie lubią i w praktyce dopisują `answerable: true` do czegokolwiek, co już wygenerowały. To ta sama sztuczka co wymuszanie pola `unsupported_claims` u sędziego z tomu 1, rozdziału 12: kształt schematu steruje rozumowaniem.

Instrukcja systemowa musi domknąć trzy rzeczy i nic więcej:

```text
1. Use only the numbered fragments in <context>. Your own knowledge about LLMs, APIs and
   libraries is not evidence and must not appear in the answer.
2. Every sentence that states a fact must end with the numbers of the fragments it comes from,
   in square brackets: [2] or [2][5].
3. If the fragments do not contain the answer, set answerable to false, leave citations empty
   and write one sentence saying what is missing. Do not guess, do not approximate.
```

Zdanie drugie w regule 1 jest ważniejsze, niż wygląda. „Odpowiadaj tylko z kontekstu" model rozumie jako „nie zmyślaj", a nie jako „nie używaj tego, co i tak wiesz" – a nasz korpus to podręcznik o API, o których model wie sporo z treningu. Bez jawnego wykluczenia wiedzy własnej dostaniesz odpowiedzi poprawne merytorycznie i niecytowalne, czyli dokładnie to, czego w systemie weryfikowalnym nie chcesz.

Kiedy który wariant? Citations API wygrywa wszędzie tam, gdzie cytat ma być pokazany użytkownikowi: wskaźniki są parsowane przez API, więc nie mogą wskazywać na nieistniejący fragment, a `cited_text` jest dosłownym wycinkiem, który podświetlisz w interfejsie. Własne cytowania ze schematem wygrywają tam, gdzie odpowiedź jest wejściem dla kodu – bo `answerable` to bool, a nie zdanie do sparsowania, i bo możesz do schematu dołożyć własne pola (pewność, typ pytania, sugerowane pytanie doprecyzowujące). W tym projekcie zostaje wariant drugi, a citations API jest opcją włączaną dla trybu „pokaż źródła" w interfejsie.

### Weryfikacja cytatów w kodzie

Model, który sam numeruje cytaty, może się pomylić – i to jest jedyny scenariusz, którego Citations API nie ma. Da się go wykryć lokalnie, bez drugiego wywołania modelu: sprawdzamy, czy słownictwo zdania faktycznie występuje we wskazanym fragmencie. Miarą jest pokrycie n-gramów słownych po normalizacji (małe litery, bez polskich znaków diakrytycznych, same znaki wyrazowe).

```python
from ragbook.answer import check_citations

for chk in check_citations(answer.text, chunks, answer.citations):
    print(f"[{','.join(map(str, chk.cited)) or '-'}] cov={chk.coverage_cited:.2f} "
          f"best={chk.coverage_best:.2f}@[{chk.best_chunk}] {chk.status}")
```

Funkcja tnie odpowiedź na zdania, wyciąga z każdego znaczniki `[k]`, liczy pokrycie trigramów zdania we wskazanym fragmencie oraz – osobno – w najlepszym fragmencie z całej piątki, i na tej podstawie przypisuje jeden z czterech statusów: `ok`, `wrong-chunk` (zdanie jest w kontekście, ale pod innym numerem), `low-overlap` (nie ma go nigdzie) i `no-citation`. Pytanie brzmi, czy to w ogóle rozróżnia. Skrypt `experiments/06_citations.py` mierzy to na prawdziwych danych: dla każdego pytania pozytywnego bierze wzorcową odpowiedź z golden setu i liczy jej pokrycie w chunku z trafnej sekcji, w pozostałych chunkach z piątki i w chunku losowym z korpusu. Dla kontroli robi to samo ze zdaniem wyjętym wprost z fragmentu, czyli z odpowiedzią czysto ekstrakcyjną.

| twierdzenie vs fragment | przypadków | średnia | mediana | p90 |
|---|---|---|---|---|
| odpowiedź wzorcowa vs trafna sekcja | 94 | 0,109 | 0,000 | 0,333 |
| odpowiedź wzorcowa vs inny z top-5 | 151 | 0,007 | 0,000 | 0,000 |
| odpowiedź wzorcowa vs losowy chunk | 49 | 0,000 | 0,000 | 0,000 |
| zdanie z fragmentu vs ten fragment | 40 | 1,000 | 1,000 | 1,000 |
| zdanie z fragmentu vs inny z top-5 | 39 | 0,014 | 0,000 | 0,043 |

Skrypt: `experiments/06_citations.py`, pokrycie trigramów. Czyta się to tak: test jest bardzo precyzyjny i mało czuły. Fragment nietrafny praktycznie nigdy nie przepuszcza twierdzenia – średnie 0,007 i 0,000 to szum – więc pokrycie **powyżej** progu jest mocnym sygnałem, że cytat jest prawdziwy. W drugą stronę jest gorzej: wzorcowa odpowiedź to ludzka parafraza, a nie cytat, i przy progu 0,05 przechodzi tylko 33 procent par „odpowiedź – trafna sekcja" (przy 3 procentach fałszywych trafień na fragmentach nietrafnych). Wiersz z odpowiedzią ekstrakcyjną wyznacza drugi koniec skali: gdy model cytuje dosłownie, pokrycie wynosi dokładnie 1,0 i test jest bezbłędny.

Wniosek jest praktyczny i trzeba go przyjąć bez udawania: pokrycie n-gramów nadaje się na **alarm, nie na bramkę**. Zdanie, którego słownictwa nie ma w żadnym z pięciu fragmentów, trafia do kolejki przeglądu; zdanie z pokryciem zero we wskazanym fragmencie, ale wysokim w innym, prawie na pewno ma przekręcony numer i to da się naprawić automatycznie. Odrzucanie odpowiedzi tylko dlatego, że model ładnie sparafrazował, byłoby kosztowniejsze niż problem, który rozwiązuje. Cztery statusy na czterech ręcznie przygotowanych przypadkach wyglądają tak:

```text
cytat z fragmentu        cited=[1] cov_cited=1.000 cov_best=1.000@[1] -> ok
ten sam cytat, zły numer cited=[2] cov_cited=0.000 cov_best=1.000@[1] -> wrong-chunk
parafraza wzorcowa       cited=[1] cov_cited=0.167 cov_best=0.167@[1] -> ok
twierdzenie zmyślone     cited=[1] cov_cited=0.000 cov_best=0.000@[None] -> low-overlap
```

## Odmowa, gdy nie ma podstaw

Pole `answerable` daje modelowi wyjście awaryjne, ale ktoś musi je wymusić. Naturalny pomysł brzmi: skoro wyszukiwanie zwraca score, to przy zbyt niskim score'ze w ogóle nie pytajmy modelu – zaoszczędzimy wywołanie i zamkniemy drogę do konfabulacji. To hipoteza mierzalna lokalnie, więc ją zmierzyłem: `experiments/06_threshold.py` liczy rozkład najlepszego score'u kosinusowego dla 49 pytań pozytywnych i 7 negatywnych.

```text
pozytywne  n= 49  min=0.841  p25=0.864  median=0.881  p75=0.895  max=0.928
negatywne  n=  7  min=0.845  p25=0.847  median=0.861  p75=0.874  max=0.875
```

Rozkłady nakładają się na całej długości: najgorsze pytanie pozytywne ma 0,841, a najlepsze negatywne 0,875. Żaden pojedynczy próg ich nie rozdzieli, co widać w tabeli przeglądu progów.

| próg top-1 | odrzuconych negatywnych | odrzuconych pozytywnych (błąd) |
|---|---|---|
| 0,848 | 2/7 | 1/49 |
| 0,862 | 4/7 | 10/49 |
| 0,870 | 5/7 | 17/49 |
| 0,877 | 7/7 | 19/49 |

Skrypt: `experiments/06_threshold.py`. Żeby odciąć wszystkie siedem pytań negatywnych, trzeba odrzucić 19 z 49 pytań, na które system umie odpowiedzieć. To jest wynik negatywny i jest wart tyle, co pozytywny: **próg na surowym score kosinusowym e5 nie jest w tym projekcie użytecznym mechanizmem odmowy**. Przyczyna jest strukturalna, nie przypadkowa. Kosinus między znormalizowanymi wektorami e5 na jednorodnym korpusie mieści się w wąskim pasmie – tutaj całe 56 pytań zajmuje przedział od 0,841 do 0,928 – a wewnątrz tego pasma o pozycji decyduje bardziej styl tekstu niż trafność. Ten sam eksperyment na drugiej mierze, marginesie top-1 nad średnią z piątki, wypada równie źle: mediana 0,008 dla pytań pozytywnych i 0,004 dla negatywnych.

Nie znaczy to, że bramka jest złym pomysłem – znaczy, że sygnał musi być inny. Score cross-enkodera z rozdziału 3 jest logitem trenowanym wprost na zadaniu „czy ten dokument odpowiada na to pytanie" i rozdziela te dwa przypadki dużo ostrzej niż kosinus; jeśli w Twoim potoku jest reranker, to jego wynik, a nie kosinus, jest właściwym miejscem na próg. Do tego czasu bramką jest samo `answerable`, a kosztem jest jedno wywołanie modelu na pytanie, na które i tak odpowiemy „nie wiem". W `ragbook.answer` próg jest więc parametrem, a nie stałą:

```python
def should_ask_model(chunks, min_score: float) -> bool:  # ragbook.answer
    """Retrieval confidence gate: below the threshold, refuse without paying for a generation."""
    if not chunks:
        return False
    return max(c.meta.get("score", 0.0) for c in chunks) >= min_score
```

Typowy błąd przy pytaniach negatywnych wygląda tak: model dostaje pięć fragmentów o wdrażaniu modeli, pytanie o HorizontalPodAutoscaler i odpowiada poprawną wiedzą ogólną o Kubernetesie, cytując fragment [2], bo tam pada słowo „wdrożenie". Formalnie spełnia regułę o cytowaniu, merytorycznie kłamie o zawartości korpusu. Wykryje to dopiero weryfikacja cytatu (pokrycie n-gramów spadnie do zera) albo sędzia modelowy – i po to jest następna sekcja.

## Wierność odpowiedzi

Wierność (faithfulness, groundedness) definiuje się przez rozbicie: dzielisz odpowiedź na atomowe twierdzenia i dla każdego sprawdzasz, czy wynika z kontekstu. Wynik to udział twierdzeń wspartych w liczbie wszystkich. Ta definicja ma trzy zalety. Jest zerojedynkowa na poziomie twierdzenia, więc nie wymaga od sędziego skali, na której zawsze się rozjeżdża. Daje diagnostykę, bo niewsparte twierdzenie jest cytowalne w raporcie. I jest niezależna od trafności odpowiedzi: odpowiedź może być w stu procentach wierna i zupełnie nie na temat.

Sędzia dostaje ten sam kontekst co generator i schemat wyjścia, który wymusza dwa kroki.

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

Trzy decyzje w tej rubryce są nieoczywiste i wszystkie wynikają z praktyki opisanej w tomie 1, rozdziale 12. Sędzią jest `claude-haiku-4-5`, a nie ten sam model, który generował – modele mają mierzalną skłonność do faworyzowania własnych odpowiedzi, a przy zadaniu tak prostym jak „czy to zdanie jest w tym akapicie" tańszy model wystarcza. Werdykt ma trzy wartości, nie dwie: `missing` (kontekst milczy) jest czym innym niż `contradicted` (kontekst mówi coś przeciwnego), a mieszanie ich zaciera różnicę między „retrieval nie dowiózł" a „model kłamie". Wreszcie rubryka mówi wprost, że twierdzenie prawdziwe w ogólności, ale nieobecne we fragmentach, jest `missing`, a nie `supported` – bez tego zdania sędzia ocenia własną wiedzę, a nie ugruntowanie.

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

Sędzia jest modelem, więc sam jest źródłem błędu, i dopóki nie wiesz jakiego, jego liczby są dekoracją. Kalibracja jest tania: weź trzydzieści odpowiedzi z prawdziwego ruchu, oznacz je ręcznie jedną binarną etykietą („czy jest tu twierdzenie bez pokrycia w kontekście"), puść sędziego na tych samych trzydziestu i policz dwie liczby. Zgodność surowa mówi, w jakiej części przypadków się zgadzacie. Kappa Cohena mówi to samo po odjęciu zgodności, którą dostalibyście przez przypadek – i to ona jest liczbą, którą raportujesz.

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

Etykiety w tym przykładzie są zmyślone – nie miałem klucza, żeby uruchomić sędziego na prawdziwych odpowiedziach – ale arytmetyka jest prawdziwa i pokazuje dokładnie tę pułapkę, dla której warto ją znać. Osiemdziesiąt procent zgodności brzmi świetnie, a kappa 0,49 mówi, że po odjęciu przypadku zostaje niecała połowa. Taki sędzia nadaje się do porównywania wersji („po zmianie promptu wierność wzrosła z 0,71 do 0,82"), ale nie do raportowania wartości bezwzględnej i na pewno nie do automatycznego blokowania odpowiedzi użytkownikowi. Próg do zapamiętania: poniżej 0,4 sędzia jest szumem, 0,4–0,6 nadaje się do porównań, powyżej 0,6 możesz cytować samą liczbę. Macierz pomyłek czyta się osobno – trzy fałszywe alarmy i trzy przeoczenia to sędzia zrównoważony; osiem alarmów i zero przeoczeń to sędzia przesadnie surowy i trzeba poluzować rubrykę, a nie próg.

### RAGAS i DeepEval

Obu bibliotek nie trzeba pisać od nowa – tom 1, rozdział 12 pokazuje, jak je wpiąć w testy regresyjne. Tutaj liczy się mapa: która metryka mierzy który etap i czego wymaga na wejściu (stan na wrzesień 2026).

| Co mierzy | RAGAS | DeepEval | Wejście |
|---|---|---|---|
| wierność odpowiedzi wobec kontekstu | `Faithfulness` (nowe: `ragas.metrics.collections.Faithfulness`), wariant `FaithfulnesswithHHEM` bez LLM-a | `FaithfulnessMetric` | odpowiedź + kontekst |
| trafność odpowiedzi wobec pytania | `ResponseRelevancy` (nowe: `AnswerRelevancy`), wymaga modelu embeddingów | `AnswerRelevancyMetric` | pytanie + odpowiedź |
| precyzja kontekstu (ranking) | `LLMContextPrecisionWithoutReference`, `LLMContextPrecisionWithReference`, `NonLLMContextPrecisionWithReference`, `IDBasedContextPrecision` | `ContextualPrecisionMetric` | pytanie + konteksty (+ wzorzec) |
| pokrycie kontekstu | `LLMContextRecall`, `NonLLMContextRecall`, `IDBasedContextRecall` | `ContextualRecallMetric` | wzorzec + konteksty |
| wrażliwość na szum w kontekście | `NoiseSensitivity` | `ContextualRelevancyMetric` | pytanie + konteksty + odpowiedź |
| kryterium własne | – | `GEval` (kryterium jednym zdaniem, próg 0–1) | wybrane pola przypadku |

Dwie różnice praktyczne. RAGAS nazywa pola przypadku `user_input`, `retrieved_contexts`, `response` i `reference`; DeepEval – `input`, `retrieval_context`, `actual_output` i `expected_output`, i wymaga `expected_output` tam, gdzie RAGAS pozwala liczyć precyzję bez wzorca. Druga: w RAGAS `Faithfulness` liczy dokładnie to, co nasz sędzia – wsparte twierdzenia przez wszystkie twierdzenia – więc jeśli chcesz porównywalności z literaturą, użyj gotowej implementacji, a własną zostaw tam, gdzie potrzebujesz trzeciej wartości werdyktu albo cytowania dowodu.

### Dlaczego wierność mierzy się osobno od trafności retrievalu

Bo to dwie niezależne osi awarii i każda ćwiartka wymaga innej naprawy. Ta macierz jest w praktyce najszybszym narzędziem diagnostycznym, jakie ma zespół RAG-owy.

| | odpowiedź wierna | odpowiedź niewierna |
|---|---|---|
| **retrieval trafny** | działa – nic nie rób | usterka generacji: popraw prompt, schemat, model; dołóż weryfikację cytatów |
| **retrieval nietrafny** | poprawna odmowa – dobrze; policz, ile ich jest, bo to koszt recall | najgorsza ćwiartka: system kłamie wiarygodnie, napraw retrieval, nie prompt |

Klucz jest w dwóch skrajnych polach. Wysoka wierność przy niskim recall to system, który nie kłamie, tylko nie odpowiada – i jeśli mierzysz wyłącznie faithfulness, wygląda doskonale. Niska wierność przy wysokim recall to problem promptu i wraca po jednym dniu pracy. Odwrotny błąd, poprawianie promptu, gdy zawodzi wyszukiwanie, jest najczęstszym marnotrawstwem w projektach RAG i dlatego rozdział 1 zaczyna od metryk retrievalu, a ten dokłada drugą oś, zamiast zastępować pierwszą.

## Strumień i cache

Cytowania działają w trybie strumieniowym: przychodzą jako delta typu `citations_delta` wewnątrz zdarzenia `content_block_delta`, a każda delta niesie jedno cytowanie do dopisania do listy `citations` bieżącego bloku tekstowego. Kolejność jest wygodna – cytowanie zawsze przychodzi po tekście, który wspiera – więc interfejs może renderować zdanie od razu i doklejać do niego znacznik, gdy cytowanie dotrze.

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

Prompt caching wygląda w tym miejscu na oczywistą oszczędność i w naszym projekcie nią nie jest – warto wiedzieć dlaczego, zanim dołożysz `cache_control` odruchowo. Mechanika jest w tomie 1, rozdziale 3; istotna jest jedna liczba: minimalna długość prefiksu, od której Claude Opus 5 w ogóle zapisze wpis do cache, to 512 tokenów (dla Opus 4.8 i Sonnet 5 jest to 1024, dla Opus 4.7 – 2048, dla Opus 4.6 i Haiku 4.5 – 4096; stan na wrzesień 2026). Nasz system prompt ma 138 tokenów według `o200k_base`. Jest o rząd wielkości za krótki, więc `cache_control` na nim nie robi nic i nie zwraca przy tym żadnego błędu – po prostu `cache_read_input_tokens` zostaje zerem. Sensowne są dopiero dwa inne układy: prefiks rozbudowany o przykłady few-shot ponad 512 tokenów albo `cache_control` na blokach `document`, gdy część korpusu jest gorąca i te same chunki wracają w większości zapytań. Ten drugi przypadek wraca w rozdziale 8 razem z cache'em semantycznym; tutaj wystarczy zapamiętać, że breakpoint stawia się na ostatnim bloku, którego prefiks jest identyczny między żądaniami, a zmiana schematu `output_config.format` unieważnia cache całego wątku.

## Co zostaje w projekcie

| Decyzja | Wybór | Dlaczego |
|---|---|---|
| liczba fragmentów w prompcie | `k` = 5 | +81% tokenów wejścia za +8 pkt proc. pokrycia przy `k` = 10 to zły interes; poprawa należy do rerankingu |
| format kontekstu | numerowane fragmenty z rozdziałem i sekcją | numer jest kluczem cytowania; metadane odbudowują kontekst ucięty przez chunker |
| schemat odpowiedzi | `Answer(answerable, text, citations)` przez `messages.parse` | `answerable` jako bool przed `text`; odpowiedź jest wejściem dla kodu, nie tekstem do parsowania |
| cytowania | własne numery domyślnie, Citations API dla trybu „pokaż źródła" | structured outputs i cytowania wykluczają się (400); w kodzie potrzebujemy schematu |
| weryfikacja cytatów | pokrycie trigramów jako alarm, nie bramka | precyzja wysoka (0,007 na fragmentach nietrafnych), czułość niska (33% przy progu 0,05) |
| próg pewności z retrievalu | wyłączony (parametr, domyślnie 0,0) | rozkłady score'u dla pytań pozytywnych i negatywnych nakładają się; próg odcinający wszystkie negatywne kosztuje 19 z 49 pytań |
| sędzia wierności | `claude-haiku-4-5`, trzy werdykty, w CI na całym golden secie | inny model niż generator; `missing` osobno od `contradicted` rozdziela winę retrievalu i generacji |
| kalibracja sędziego | 30 ręcznych etykiet, raportowana kappa | poniżej 0,4 sędzia jest szumem; bez tej liczby jego wyniki nie znaczą nic |

## Podsumowanie

- Kontekst do promptu numerujemy od jedynki i doklejamy rozdział oraz sekcję; numer fragmentu jest jedynym kluczem cytowania, po którym da się coś sprawdzić w kodzie.
- `k` = 5 zamiast 10 to 81 procent mniej tokenów wejścia za osiem punktów procentowych pokrycia; przy naszym korpusie właściwym lekarstwem na braki jest ranking, nie objętość.
- Instrukcja „tylko z kontekstu" nie chroni przed kontekstem nietrafnym – wyszukiwanie zawsze zwróci `k` fragmentów, więc odmowa musi być osobnym mechanizmem, a nie zdaniem w prompcie.
- Citations API daje wskaźniki parsowane po stronie API (`cited_text`, `char_location`, `page_location`, `content_block_location`) i nie da się go połączyć ze structured outputs; wybór między nim a własnym numerowaniem jest rozwidleniem architektury.
- Pokrycie n-gramów weryfikuje cytat lokalnie i za darmo, ale jest testem precyzyjnym i mało czułym – nadaje się na alarm i na wykrywanie przekręconego numeru, nie na bramkę.
- Próg na surowym score kosinusowym e5 nie rozdziela pytań pozytywnych od negatywnych: rozkłady nakładają się w całości, a odcięcie wszystkich siedmiu negatywnych kosztuje 19 z 49 pytań pozytywnych.
- Wierność mierzy się przez rozbicie odpowiedzi na twierdzenia i ocenę każdego osobno; sędzia ma być innym, tańszym modelem i ma mieć trzeci werdykt `missing`, żeby oddzielić winę retrievalu od winy generacji.
- Sędzia bez kalibracji jest dekoracją: trzydzieści ręcznych etykiet i kappa Cohena mówią, czy jego liczby wolno porównywać, czy tylko oglądać.

## Co dalej

Rozdział 7 wychodzi poza podobieństwo wektorowe: pokazuje GraphRAG dla pytań typu „jak X wiąże się z Y" i agentic RAG, w którym model sam decyduje, czy wyszukać jeszcze raz – a więc buduje na `answerable` i na sędzim z tego rozdziału, bo to one dają sygnał „to, co znalazłem, nie wystarcza". Zanim tam przejdziesz, uruchom `experiments/06_generate.py` z własnym kluczem na dziesięciu pytaniach i przejrzyj ręcznie wyniki `check_citations`: pierwsza kolejka przypadków ze statusem `wrong-chunk` i `low-overlap` powie Ci o Twoim prompcie więcej niż jakakolwiek średnia.

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
