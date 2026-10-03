# Rozdział 3. Prompt engineering

> **Z roadmapy:** Prompt Engineering, Prompt Anatomy, Input Format, System Prompting, Role & Behavior, Context, Constraints, Structured Output, Prompting Techniques, Zero-Shot, Few-Shot, CoT, ReAct, Model Interaction, Function Calling, Prompt Caching, Streaming Responses
>
> **Pakiety:** `pip install anthropic openai pydantic`

Prompt to nie zaklęcie, tylko argument wywołania funkcji. Model jest funkcją, która przyjmuje listę wiadomości i zestaw parametrów, a zwraca listę bloków treści plus licznik zużytych tokenów. Wszystko, co robisz w tym rozdziale, sprowadza się do świadomego składania tego argumentu: co wstawiasz, w jakiej kolejności, jak oznaczasz granice między instrukcją a danymi i w jakim formacie oczekujesz odpowiedzi. Kiedy zaczniesz myśleć o prompcie jak o wejściu funkcji, przestaniesz dopisywać „bardzo proszę, to ważne" i zaczniesz zmieniać rzeczy, które mają mierzalny wpływ.

W praktyce boli to w trzech miejscach. Po pierwsze, prompt żyje w kodzie jako wielolinijkowy f-string, który rośnie przez kilka miesięcy i nikt nie wie, która linijka za co odpowiada – aż ktoś usunie jedno zdanie i połowa odpowiedzi przestaje być poprawnym JSON-em. Po drugie, prompt nie ma testów, więc zmiana modelu albo przeredagowanie instrukcji to skok w ciemno. Po trzecie, prompt kosztuje: każdy token systemowy płacisz przy każdym żądaniu, a przy dziesięciu tysiącach wywołań dziennie różnica między dobrze a źle ułożonym prefiksem to konkretne pieniądze.

Dlatego traktujemy prompty jak kod. Trzymasz je w plikach, a nie w konkatenacjach; wersjonujesz je razem z aplikacją; zmieniasz je pod kontrolą zestawu testowego, a nie na podstawie jednego udanego wywołania w konsoli. Testowanie i ewaluacja promptów to temat na osobny rozdział – wrócimy do niego w rozdziale 12. Tutaj chodzi o warstwę niżej: z czego prompt się składa, jakie techniki układania go działają i jakie mechanizmy API (narzędzia, cache, streaming) zmieniają sposób, w jaki go piszesz.

## Anatomia promptu

### Format wejścia (Input Format)

To, co potocznie nazywasz „promptem", w API jest kilkoma osobnymi polami. Jest lista wiadomości (`messages`), w której każda wiadomość ma rolę (`role`) i treść (`content`). Treść to albo zwykły string, albo lista bloków – bloku tekstowego, obrazu, wywołania narzędzia, wyniku narzędzia. Role naprzemiennie opisują, kto mówi: `user` to Ty (albo Twój użytkownik), `assistant` to model. Historia rozmowy to po prostu rosnąca lista tych wiadomości, którą wysyłasz w całości przy każdym żądaniu – API nie pamięta poprzedniego wywołania.

Instrukcja globalna, czyli system prompt, trafia gdzie indziej i tu oba SDK się różnią. W API Anthropic system prompt to osobny parametr `system` obok `messages`; nie jest wiadomością i nie ma roli. W API OpenAI (Responses API) instrukcja globalna to albo parametr `instructions`, albo wiadomość w `input` z rolą `developer`; dokumentacja opisuje te dwa sposoby jako w przybliżeniu równoważne, a rola `developer` ma pierwszeństwo przed rolą `user`. Starsza rola `system` z Chat Completions została w Responses API zastąpiona przez `developer`.

```python
import os
from anthropic import Anthropic
from openai import OpenAI

QUESTION = "Explain what a database index is, in two sentences."

anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = anthropic_client.messages.create(
    model="claude-opus-5",
    max_tokens=512,
    system="You are a concise backend engineering tutor.",
    messages=[{"role": "user", "content": QUESTION}],
)
print("claude:", next(b.text for b in message.content if b.type == "text"))

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = openai_client.responses.create(
    model="gpt-6-astra",
    input=[
        {"role": "developer", "content": "You are a concise backend engineering tutor."},
        {"role": "user", "content": QUESTION},
    ],
)
print("gpt:", response.output_text)
```

Zwróć uwagę na trzy rzeczy. Po stronie Anthropic odpowiedź to lista bloków, więc tekst wyciągasz filtrem po `block.type == "text"` – przy włączonym myśleniu i przy narzędziach w tej liście będą też bloki innego typu, a ślepe `content[0].text` się wywali. Parametr `max_tokens` jest po stronie Anthropic obowiązkowy i jest twardym limitem długości odpowiedzi, nie sugestią. Po stronie OpenAI `response.output_text` to wygodny skrót, który skleja wszystkie bloki tekstowe – pod spodem `response.output` jest analogiczną listą elementów.

Warto od razu zapamiętać dwie konsekwencje tego kształtu. Pierwsza: skoro `content` bywa listą bloków, to prompt nie musi być tekstem – obraz, dokument PDF, wynik narzędzia to po prostu inne typy bloków w tej samej liście, obsługiwane tym samym wywołaniem. Druga: skoro historia jest wysyłana w całości przy każdym żądaniu, to koszt rozmowy rośnie kwadratowo względem liczby tur, a nie liniowo. Dziesiąta wiadomość w rozmowie płaci za dziewięć poprzednich. To jest główny powód, dla którego dalsze części tego rozdziału tyle uwagi poświęcają cache'owaniu, a cały rozdział 4 – zarządzaniu kontekstem.

### System prompt i rola (System Prompting, Role & Behavior)

System prompt to miejsce na rzeczy stałe: kim jest asystent, w jakim produkcie działa, jakiego rejestru języka używa, czego nie wolno mu obiecywać, jak ma się zachować, gdy nie zna odpowiedzi. Kryterium jest proste: jeśli coś jest prawdą dla każdego zapytania, idzie do system promptu; jeśli zmienia się z zapytania na zapytanie, idzie do wiadomości `user`. To nie jest tylko higiena – od tego zależy, czy zadziała cache (o tym w dalszej części rozdziału).

Nadanie roli działa, i to mocniej, niż się wydaje. Dokumentacja Anthropic zaleca ustawianie roli właśnie w system prompcie i zauważa, że różnicę robi już jedno zdanie. Rola nie jest jednak kostiumem, tylko zawężeniem przestrzeni odpowiedzi: „jesteś inżynierem wsparcia dla API płatności" to informacja o dziedzinie, słownictwie i typowych intencjach użytkownika. „Jesteś genialnym, światowej klasy ekspertem" nie niesie żadnej informacji i tylko zajmuje tokeny.

Czego do system promptu nie wkładać? Danych. Treść dokumentu, wyniki wyszukiwania, historia zgłoszeń klienta – to wszystko jest zmienne i należy do wiadomości użytkownika. Nie wkładaj też sekretów: system prompt bywa wyciekany przez model, a użytkownik i tak nie powinien mieć możliwości wyciągnięcia klucza API przez rozmowę. Nie wkładaj wreszcie instrukcji, których nie umiesz sprawdzić – każde zdanie w system prompcie powinno dać się przełożyć na test.

```python
import os
from anthropic import Anthropic

SYSTEM_PROMPT = """You are a technical support assistant for Acme Payments API.

Scope:
- You answer questions about our REST API, webhooks, and sandbox environment.
- For billing disputes or account access, hand the user off to billing@acme.example.

Behavior:
- Answer in the language the user writes in.
- When the answer depends on the API version, ask which version the user is on.
- If the documentation excerpt provided does not contain the answer, say so and
  suggest the closest documented endpoint instead of guessing parameter names.
- End every answer that contains a code sample with the exact endpoint path used.
"""

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": "Webhooki przychodzą u mnie podwójnie. Co robić?"}],
)
print(next(b.text for b in message.content if b.type == "text"))
```

Ten system prompt ma strukturę, którą łatwo utrzymywać: zakres, potem zachowanie, potem reguły wyjścia. Każda reguła jest sprawdzalna – „odpowiada w języku użytkownika" i „kończy odpowiedź z kodem ścieżką endpointu" to rzeczy, które zweryfikujesz automatycznie. Zauważ też, że instrukcja dotycząca braku odpowiedzi jest sformułowana pozytywnie: mówi, co model ma zrobić zamiast zgadywania, a nie tylko zakazuje zgadywania.

### Kontekst w prompcie (Context)

Kontekst to dane, które wstrzykujesz do promptu w czasie działania programu: fragment dokumentacji, wiersze z bazy, transkrypcja rozmowy. Dwa pytania decydują o jakości: jak oznaczysz granicę między danymi a instrukcją i w jakiej kolejności je ułożysz.

Granicę oznaczasz delimiterem. Dla modeli Claude dokumentacja zaleca tagi XML – `<document>`, `<instructions>`, `<example>` – bo model jest trenowany na takim oznaczaniu i potrafi się do tagów odwoływać („zacytuj fragmenty z `<records>`"). Przy wielu dokumentach zagnieżdżasz: `<documents>`, w środku `<document index="1">` z podtagami `<source>` i `<document_content>`. Markdown (nagłówki, potrójne backticki) też działa, ale gorzej znosi dane, które same zawierają markdown. Kluczowe jest, żeby delimiter nie mógł wystąpić w danych – jeśli wklejasz cudzy HTML, tagi XML przestają być bezpieczne i lepiej użyć nietypowego ogranicznika.

Kolejność jest mniej oczywista. Dokumentacja Anthropic dla długiego kontekstu (od około 20 tysięcy tokenów) mówi wprost: długie dane umieszczaj na górze promptu, nad pytaniem, instrukcjami i przykładami, a pytanie zadawaj na końcu. W testach zapytanie na końcu poprawiało jakość odpowiedzi nawet o 30 procent, szczególnie przy wielu dokumentach (stan na wrzesień 2026). To samo ułożenie pomaga później przy cache'owaniu, bo stałe dane lądują w prefiksie.

```python
import os
from anthropic import Anthropic

DOC = """Rate limits are enforced per API key. The sandbox key allows 10 requests
per second; production keys start at 100 requests per second. Exceeding the limit
returns HTTP 429 with a Retry-After header expressed in seconds."""

PROMPT = f"""<documents>
  <document index="1">
    <source>acme-api-guide.md</source>
    <document_content>
{DOC}
    </document_content>
  </document>
</documents>

Answer the question using only the documents above. If the answer is not there,
reply exactly: NOT IN DOCS.

Question: What should a client do after receiving HTTP 429?"""

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-opus-5",
    max_tokens=512,
    messages=[{"role": "user", "content": PROMPT}],
)
print(next(b.text for b in message.content if b.type == "text"))
```

Dane są na górze, instrukcja i pytanie na dole, a granica jest jawna. Instrukcja „użyj wyłącznie dokumentów powyżej" plus zdefiniowana odpowiedź awaryjna (`NOT IN DOCS`) daje Ci sygnał, który da się sprawdzić w kodzie – zamiast zgadywać z prozy, czy model coś zmyślił. To najprostsza wersja mechanizmu, który w rozdziale o RAG rozbudujesz o wyszukiwanie fragmentów.

### Ograniczenia (Constraints)

Ograniczenia to czwarty element anatomii: długość, język, format, ton, zakres. Część z nich egzekwujesz parametrami API, a nie prozą. Długość odpowiedzi ograniczasz przez `max_tokens` – to twardy limit, po przekroczeniu którego odpowiedź jest ucinana w połowie zdania, a `stop_reason` przyjmuje wartość `max_tokens`. Format wyjścia najpewniej wymusisz przez structured outputs, o czym za chwilę. Prozą zostają rzeczy, których API nie zna: rejestr, poziom szczegółowości, zakres tematyczny.

Najważniejsza zasada brzmi: pisz, co model ma robić, a nie czego ma nie robić. Dokumentacja Anthropic podaje ten przykład wprost – zamiast „nie używaj markdownu" napisz „odpowiedź ma być ciągiem płynnych akapitów prozy". Powód jest prozaiczny: zakaz opisuje nieskończony zbiór zachowań niepożądanych i nie wskazuje żadnego pożądanego, więc model musi sam wymyślić, co zrobić zamiast. Instrukcja pozytywna od razu podaje cel.

Drugi wariant tej samej zasady: dodaj uzasadnienie. Dokumentacja porównuje „NIGDY nie używaj wielokropka" z „odpowiedź będzie czytana przez syntezator mowy, więc nigdy nie używaj wielokropka, bo syntezator nie wie, jak go wymówić". Wersja z uzasadnieniem działa lepiej, bo model potrafi z niej uogólnić na przypadki, których nie wymieniłeś – na przykład na inne znaki, których syntezator nie przeczyta.

```text
Źle:
- Nie pisz długich odpowiedzi.
- Nie używaj list.
- Nie wspominaj o konkurencji.

Lepiej:
- Odpowiadaj w maksymalnie trzech akapitach; odpowiedź trafia do okna czatu
  o wysokości 400 pikseli i dłuższa wymaga przewijania.
- Pisz ciągłą prozą; listy rozbijają odpowiedź na fragmenty, których nasz
  syntezator mowy nie czyta w naturalnym rytmie.
- Gdy użytkownik pyta o produkt innej firmy, opisz odpowiadającą mu funkcję
  Acme Payments i zaznacz, że porównań nie prowadzimy.
```

Trzy zakazy zamieniły się w trzy instrukcje z uzasadnieniem i wskazanym zachowaniem zastępczym. Zauważ, że ostatnia reguła nie jest już ograniczeniem, tylko procedurą – i dopiero w tej formie da się ją przetestować.

### Ustrukturyzowane wyjście (Structured Output)

Proszenie w prozie o JSON i parsowanie tego, co przyjdzie, jest najczęstszym źródłem awarii w aplikacjach na LLM-ach. Oba API mają dziś natywne rozwiązanie: podajesz schemat JSON Schema, a serwer gwarantuje, że odpowiedź do niego pasuje.

Po stronie Anthropic mechanizm nazywa się structured outputs i jest dostępny bez nagłówka beta; parametr to `output_config` z zagnieżdżonym kluczem `format` (starszy `output_format` na `messages.create()` jest wycofany i w Pythonowym SDK w wersji 1.0 i nowszych podniesie `TypeError`). SDK daje wygodniejszą drogę: metoda `client.messages.parse()` przyjmuje klasę Pydantic w argumencie `output_format`, sama tłumaczy ją na schemat i zwraca zwalidowany obiekt w `response.parsed_output` (stan na wrzesień 2026).

```python
import os
from anthropic import Anthropic
from pydantic import BaseModel

class Ticket(BaseModel):
    category: str
    severity: int
    affected_endpoint: str
    needs_human: bool

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
response = client.messages.parse(
    model="claude-opus-5",
    max_tokens=1024,
    system="You triage incoming support tickets for Acme Payments API.",
    messages=[{
        "role": "user",
        "content": "Since this morning POST /v1/charges returns 500 for every "
                   "request from our production key. Nothing changed on our side.",
    }],
    output_format=Ticket,
)

ticket: Ticket = response.parsed_output
print(ticket.category, ticket.severity, ticket.affected_endpoint, ticket.needs_human)
print(type(ticket))
```

`response.parsed_output` jest instancją Twojej klasy, a nie słownikiem – dostajesz podpowiedzi typów w edytorze i walidację Pydantica za darmo. Schemat wysyłany do modelu jest generowany z klasy, więc opisy pól (`Field(description=...)`) trafiają do promptu i realnie sterują ekstrakcją; to najtańszy sposób na doprecyzowanie, co znaczy „severity". Jeśli potrzebujesz surowego schematu, na przykład dlatego że budujesz go dynamicznie, użyj `output_config={"format": {"type": "json_schema", "schema": {...}}}` na `messages.create()`; schemat musi mieć `additionalProperties: false` i listę `required`.

Po stronie OpenAI odpowiednikiem jest `client.responses.parse()` z argumentem `text_format` i wynikiem w `response.output_parsed`. Wersja niskopoziomowa to `text={"format": {"type": "json_schema", "name": ..., "strict": True, "schema": {...}}}` na `responses.create()`, a odpowiedź czytasz z `response.output_text`.

```python
import os
from openai import OpenAI
from pydantic import BaseModel, Field

class Ticket(BaseModel):
    category: str = Field(description="One of: outage, bug, question, billing")
    severity: int = Field(description="1 = cosmetic, 5 = production outage")
    affected_endpoint: str
    needs_human: bool

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = client.responses.parse(
    model="gpt-6-astra",
    input=[
        {"role": "developer", "content": "You triage incoming support tickets."},
        {"role": "user", "content": "Since this morning POST /v1/charges returns 500 "
                                    "for every request from our production key."},
    ],
    text_format=Ticket,
)

ticket = response.output_parsed
print(ticket.model_dump())
```

Oba SDK realizują ten sam wzorzec: klasa Pydantic jest jednocześnie kontraktem z modelem i typem w Twoim kodzie. Trzymaj ją w jednym miejscu i nie duplikuj schematu w prozie promptu – jeśli napiszesz w instrukcji „zwróć pola category i severity", a potem zmienisz klasę, masz dwa źródła prawdy. Instrukcja tekstowa powinna opisywać zadanie („zaklasyfikuj zgłoszenie"), a nie kształt wyjścia.

## Techniki promptowania

Anatomia mówi, gdzie co wstawić. Techniki mówią, ile wstawić i w jakiej formie. Cztery, które trzeba znać, układają się w rosnącą skalę kosztu i mocy: zero-shot nie kosztuje nic ponad instrukcję, few-shot dokłada przykłady, chain-of-thought dokłada rozumowanie, a ReAct dokłada pętlę ze światem zewnętrznym. Reguła wyboru jest jedna i nudna: bierz najtańszą technikę, która przechodzi Twoje testy. Każdy krok w górę tej skali zwiększa liczbę tokenów, opóźnienie i liczbę miejsc, w których coś może pójść nie tak.

### Zero-shot

Zero-shot to wywołanie bez przykładów: opisujesz zadanie i oczekujesz wyniku. Dla zadań, które model zna z treningu – klasyfikacja sentymentu, tłumaczenie, streszczenie, ekstrakcja oczywistych pól – to zwykle wystarczy i jest najtańsze. Zacznij zawsze od zero-shot, zmierz jakość, i dopiero gdy jest za niska, dokładaj przykłady. Odwrotna kolejność kończy się promptem, który ma dwa tysiące tokenów przykładów i nikt nie wie, czy są potrzebne.

```python
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-opus-5",
    max_tokens=16,
    system="Classify the sentiment of a product review. "
           "Reply with exactly one word: positive, negative, or mixed.",
    messages=[{
        "role": "user",
        "content": "Szybka dostawa, ale obudowa przyszła porysowana.",
    }],
)
print(next(b.text for b in message.content if b.type == "text"))
```

Dwie rzeczy robią tu robotę i obie są tanie. Instrukcja podaje zamknięty zbiór dopuszczalnych odpowiedzi, więc wynik da się porównać ze stringiem zamiast parsować prozę. `max_tokens=16` jest bezpiecznikiem: jeśli model mimo instrukcji zacznie tłumaczyć swoją decyzję, zapłacisz za szesnaście tokenów, a nie za akapit.

### Few-shot

Few-shot to dołożenie przykładów wejścia i oczekiwanego wyjścia. Działa najlepiej tam, gdzie zadanie jest specyficzne dla Twojej domeny albo gdzie format wyjścia jest nietypowy – przykład pokazuje konwencję szybciej, niż opisze ją akapit instrukcji. Dokumentacja Anthropic zaleca od trzech do pięciu przykładów i podkreśla, że mają być trafne (podobne do realnych danych), zróżnicowane (żeby model nie wyłapał przypadkowego wzorca) i wyraźnie oznaczone.

Przykłady możesz umieścić na dwa sposoby: jako oznaczone tagami `<example>` bloki wewnątrz jednej wiadomości albo jako naprzemienne wiadomości `user` i `assistant`. Druga forma jest czytelniejsza i mocniejsza, bo dosłownie pokazuje modelowi, jak wygląda jego własna tura.

```python
import os
from anthropic import Anthropic

EXAMPLES = [
    ("Nie mogę się zalogować do panelu, hasło nie działa.", "account|2"),
    ("Webhook /v1/events dubluje zdarzenia od wtorku.", "bug|3"),
    ("Czy sandbox wspiera płatności cykliczne?", "question|1"),
    ("Wszystkie transakcje produkcyjne zwracają 500 od 20 minut.", "outage|5"),
]

messages = []
for text, label in EXAMPLES:
    messages.append({"role": "user", "content": text})
    messages.append({"role": "assistant", "content": label})
messages.append({"role": "user", "content": "Retry-After przychodzi jako data, nie liczba sekund."})

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-opus-5",
    max_tokens=16,
    system="Label each support ticket as category|severity. Reply with the label only.",
    messages=messages,
)
print(next(b.text for b in message.content if b.type == "text"))
```

Przykłady w rolach `user` i `assistant` są dla modelu historią rozmowy, w której on sam już cztery razy odpowiedział w wymaganym formacie – piąta odpowiedź w tym samym formacie jest najbardziej prawdopodobną kontynuacją. Zwróć uwagę, że przykłady pokrywają cztery różne kategorie i cały zakres severity; gdyby wszystkie były błędami o severity 3, model nauczyłby się zwracać „bug|3". Koszt też jest realny: te przykłady lecą przy każdym żądaniu, więc to pierwszy kandydat do cache'owania.

### Chain-of-Thought (CoT)

Chain-of-thought to poproszenie modelu, żeby rozpisał rozumowanie, zanim poda odpowiedź. Klasyczna forma to dopisek „think step by step", forma lepsza to wskazanie kroków i miejsca na nie – na przykład prośba o rozumowanie w tagach `<reasoning>`, a odpowiedź w `<answer>`. Ma to sens przy zadaniach wieloetapowych: arytmetyce, wnioskowaniu na regułach, analizie przyczyn.

Na współczesnych modelach rozumujących ta technika jest dużo mniej potrzebna, bo rozumowanie jest wbudowane w API. Modele Claude od generacji 4.6 wzwyż używają myślenia adaptacyjnego (`thinking: {"type": "adaptive"}`), w którym model sam decyduje, kiedy i ile myśleć; na Claude Opus 5 myślenie jest domyślnie włączone, a głębokość sterujesz parametrem `output_config.effort` o wartościach od `low` do `max` (domyślnie `high`). Starszy tryb z `budget_tokens` jest wycofany i na modelach od 4.7 wzwyż zwraca błąd 400. Po stronie OpenAI odpowiednikiem jest `reasoning={"effort": ...}`. Dokumentacja Anthropic podaje, że w wewnętrznych ewaluacjach myślenie adaptacyjne wypada lepiej niż ręcznie sterowane (stan na wrzesień 2026).

```python
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PUZZLE = ("A webhook is retried 3 times with exponential backoff starting at 2s "
          "and doubling. The consumer times out after 15s total. How many "
          "retries actually reach the consumer?")

explicit_cot = client.messages.create(
    model="claude-opus-5",
    max_tokens=2048,
    system="Work through the problem inside <reasoning> tags, "
           "then give the final number inside <answer> tags.",
    messages=[{"role": "user", "content": PUZZLE}],
)
print(next(b.text for b in explicit_cot.content if b.type == "text"))
```

To jest jawny CoT: prosisz o rozumowanie w oznaczonym miejscu, dzięki czemu możesz je pokazać, zalogować albo wyciąć regexem przed pokazaniem użytkownikowi. Wadą jest to, że rozumowanie jest zwykłym tekstem – płacisz za nie jak za wyjście i musisz je sam wycinać. Wersja natywna przenosi ten sam mechanizm do osobnych bloków treści.

```python
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

message = client.messages.create(
    model="claude-opus-5",
    max_tokens=4096,
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={"effort": "high"},
    messages=[{
        "role": "user",
        "content": "A webhook is retried 3 times with exponential backoff starting "
                   "at 2s and doubling. The consumer times out after 15s total. "
                   "How many retries actually reach the consumer?",
    }],
)

for block in message.content:
    if block.type == "thinking":
        print("[thinking]", block.thinking[:200])
    elif block.type == "text":
        print("[answer]", block.text)
```

Rozumowanie przychodzi teraz jako osobne bloki `thinking`, a odpowiedź jako bloki `text` – nie musisz niczego parsować. Jedna pułapka: na Claude Opus 5 domyślną wartością `display` jest `omitted`, czyli bloki `thinking` przychodzą z pustym tekstem. Ustaw `display: "summarized"`, jeśli chcesz zobaczyć streszczenie rozumowania; surowy łańcuch myśli nie jest udostępniany w żadnym trybie, a myślenie jest rozliczane tak samo niezależnie od ustawienia. Praktyczny wniosek: dopisek „think step by step" w system prompcie modelu rozumującego jest dziś zwykle zbędny, a bywa szkodliwy – zachęca do dublowania rozumowania w widocznym tekście.

### ReAct

ReAct to wzorzec, w którym model przeplata rozumowanie z działaniem: myśl (Thought), akcja (Action), obserwacja (Observation), i tak w pętli, aż dojdzie do odpowiedzi. Historycznie realizowano go czysto tekstowo – model pisze `Action: search(...)`, Ty przerywasz generowanie, wykonujesz akcję i dopisujesz `Observation: ...`. Dziś tę samą pętlę realizuje się zwykle przez function calling (następna sekcja), ale warto raz zobaczyć wersję surową, bo pokazuje, skąd wzięła się cała koncepcja agenta.

Jedna uwaga techniczna: klasyczna implementacja ReAct wymuszała format przez prefill, czyli wstawienie niedokończonej wiadomości `assistant` na końcu listy. Na aktualnych modelach Claude prefill ostatniej tury asystenta zwraca błąd 400, więc format wymuszamy instrukcją, a generowanie przerywamy przez `stop_sequences` (stan na wrzesień 2026).

```python
import os
from anthropic import Anthropic

FACTS = {"acme charges": "POST /v1/charges creates a charge; rate limit 100 rps."}

def search(query: str) -> str:
    return FACTS.get(query.lower().strip(), "no results")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
system = ("Solve the task in a loop. Each turn write exactly one line "
          "'Thought: ...' followed by one line 'Action: search[query]' or "
          "one line 'Final: <answer>'. Never write anything else.")
messages = [{"role": "user", "content": "What is the rate limit of the charges endpoint?"}]

for step in range(4):
    reply = client.messages.create(
        model="claude-opus-5", max_tokens=512, system=system,
        messages=messages, stop_sequences=["Observation:"],
    )
    text = next(b.text for b in reply.content if b.type == "text").strip()
    print(f"--- step {step}\n{text}")
    if "Final:" in text:
        break
    query = text.split("Action: search[", 1)[1].split("]", 1)[0]
    messages += [{"role": "assistant", "content": text},
                 {"role": "user", "content": f"Observation: {search(query)}"}]
```

Pętla jest cała po Twojej stronie: model produkuje tekst, Ty wykrywasz w nim akcję, wykonujesz ją i dopisujesz obserwację jako kolejną wiadomość `user`. `stop_sequences` sprawia, że model nie halucynuje obserwacji za Ciebie – generowanie urywa się dokładnie tam, gdzie powinno wejść środowisko. Zauważ też limit iteracji: bez niego źle sformułowane zadanie kręci się w kółko i pali budżet. Pełny agent, z wieloma narzędziami, obsługą błędów i zarządzaniem kontekstem, to temat rozdziału 9.

## Interakcja z modelem

Do tej pory prompt był tekstem, który wysyłasz, i tekstem, który wraca. Trzy mechanizmy API zmieniają ten obraz na tyle, że wpływają na sposób pisania promptów. Function calling sprawia, że część promptu to schematy narzędzi, a odpowiedź bywa żądaniem wywołania kodu. Prompt caching sprawia, że kolejność sekcji w prompcie ma cenę wyrażoną w dolarach. Streaming sprawia, że odpowiedź jest strumieniem zdarzeń, a nie obiektem – co zmienia sposób, w jaki odczytujesz wyniki i liczniki zużycia.

### Function calling

Function calling (tool use) to ustandaryzowana wersja pętli z poprzedniej sekcji. Zamiast parsować tekst, deklarujesz narzędzia ze schematem JSON, a model zwraca ustrukturyzowane żądanie wywołania. Pętla ma cztery kroki: wysyłasz wiadomość z listą `tools`, model odpowiada blokiem `tool_use` i ustawia `stop_reason` na `"tool_use"`, Ty wykonujesz funkcję i odsyłasz wynik jako blok `tool_result` w wiadomości `user`, model formułuje odpowiedź końcową.

Definicja narzędzia po stronie Anthropic ma trzy pola: `name`, `description` i `input_schema` (JSON Schema). Opis jest najważniejszym elementem – model decyduje na jego podstawie, kiedy sięgnąć po narzędzie. Same narzędzia kosztują tokeny: dokumentacja podaje, że dla Claude Opus 5 przy `tool_choice` `auto` dodatkowy systemowy prompt obsługi narzędzi to 286 tokenów, plus tokeny samych definicji (stan na wrzesień 2026).

```python
import os, json
from anthropic import Anthropic

TOOLS = [{
    "name": "get_order_status",
    "description": "Look up the current status of a customer order by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {"order_id": {"type": "string", "description": "Order ID, e.g. ORD-42"}},
        "required": ["order_id"],
    },
}]

def get_order_status(order_id: str) -> str:
    return json.dumps({"order_id": order_id, "status": "shipped", "eta_days": 2})

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
messages = [{"role": "user", "content": "Where is order ORD-42?"}]

while True:
    reply = client.messages.create(
        model="claude-opus-5", max_tokens=1024, tools=TOOLS, messages=messages,
    )
    messages.append({"role": "assistant", "content": reply.content})
    if reply.stop_reason != "tool_use":
        print(next(b.text for b in reply.content if b.type == "text"))
        break
    results = []
    for block in reply.content:
        if block.type == "tool_use":
            print("calling", block.name, block.input)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": get_order_status(**block.input)})
    messages.append({"role": "user", "content": results})
```

Trzy szczegóły decydują o poprawności tej pętli. Do historii dopisujesz `reply.content` w całości, a nie sam tekst – bloki `tool_use` muszą wrócić do modelu, inaczej `tool_result` nie będzie miał się do czego odnieść. Wszystkie wyniki z jednej tury pakujesz do jednej wiadomości `user`; rozbicie ich na kilka wiadomości działa, ale uczy model, żeby nie wywoływać narzędzi równolegle. Wreszcie warunkiem pętli jest `stop_reason`, a nie obecność bloku `tool_use` – to ta sama informacja, ale `stop_reason` jest jawnym kontraktem API i obsłuży Ci również przypadek `max_tokens`.

Po stronie OpenAI kształt jest analogiczny, ale nazwy inne. Narzędzie ma `type: "function"`, a wywołanie przychodzi jako element listy `response.output` o typie `function_call`, z polami `call_id` i `arguments` (argumenty są stringiem z JSON-em, nie słownikiem). Wynik dopisujesz do wejścia jako element `function_call_output`.

```python
import os, json
from openai import OpenAI

TOOLS = [{
    "type": "function",
    "name": "get_order_status",
    "description": "Look up the current status of a customer order by its ID.",
    "parameters": {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
    },
}]

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
input_list = [{"role": "user", "content": "Where is order ORD-42?"}]

response = client.responses.create(model="gpt-6-astra", input=input_list, tools=TOOLS)
input_list += response.output
for item in response.output:
    if item.type == "function_call":
        args = json.loads(item.arguments)
        result = json.dumps({"order_id": args["order_id"], "status": "shipped"})
        input_list.append({"type": "function_call_output",
                           "call_id": item.call_id, "output": result})

final = client.responses.create(model="gpt-6-astra", input=input_list, tools=TOOLS)
print(final.output_text)
```

Zwróć uwagę na `json.loads(item.arguments)` – argumenty przychodzą jako tekst i musisz je sparsować. Ta sama reguła obowiązuje po stronie Anthropic, gdzie `block.input` jest już słownikiem, ale przy streamingu składasz go z fragmentów `partial_json`; nigdy nie dopasowuj argumentów przez porównywanie stringów, bo escapowanie znaków potrafi się różnić między modelami.

### Prompt caching

Prompt caching to mechanizm, który pozwala nie płacić pełnej stawki za powtarzający się początek promptu. Działa na zasadzie prefiksu: system sprawdza, czy początek żądania – aż do wskazanego punktu, zwanego cache breakpoint – jest już w cache z niedawnego żądania. Jeśli tak, używa wersji zapisanej, jeśli nie, przetwarza całość i zapisuje prefiks. Kluczowa konsekwencja: zmiana jednego bajtu gdziekolwiek w prefiksie unieważnia wszystko, co jest za nim.

Liczby po stronie Anthropic (stan na wrzesień 2026). Minimalna długość prefiksu zależy od modelu: 512 tokenów dla Claude Opus 5 i modeli Fable 5/5.1, 1024 dla Claude Opus 4.8, Sonnet 5 i Sonnet 4.6, 2048 dla Opus 4.7, 4096 dla Opus 4.6 i Haiku 4.5. Krótsze prompty po prostu się nie cache'ują i nie dostajesz o tym żadnego błędu. Domyślny czas życia wpisu to 5 minut, opcjonalnie 1 godzina (`"ttl": "1h"`), liczony od początku żądania, które wpis zapisuje lub czyta. Zapis do cache kosztuje 1,25 raza stawkę wejściową przy 5 minutach i 2 razy przy godzinie; odczyt kosztuje 0,1 stawki wejściowej. Dla Claude Opus 5 przy stawce 5 dolarów za milion tokenów wejściowych daje to 6,25 dolara za zapis 5-minutowy, 10 dolarów za zapis godzinny i 0,50 dolara za odczyt. Breakpointów możesz ustawić maksymalnie cztery.

Kolejność prefiksów jest stała: najpierw `tools`, potem `system`, potem `messages`. Z tego wynika reguła układania promptu: stałe na początku, zmienne na końcu. Definicje narzędzi i system prompt są niezmienne, więc idą pierwsze i to na nich stawiasz breakpoint; bieżące pytanie użytkownika, znacznik czasu i identyfikator żądania idą za nim.

```python
import os
from anthropic import Anthropic

POLICY = ("Acme Payments API support policy. " + "Every answer must cite the endpoint path. " * 200)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def ask(question: str):
    return client.messages.create(
        model="claude-opus-5",
        max_tokens=256,
        system=[{"type": "text", "text": POLICY, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": question}],
    )

first = ask("What does a 429 mean?")
print("write:", first.usage.cache_creation_input_tokens,
      "read:", first.usage.cache_read_input_tokens,
      "fresh:", first.usage.input_tokens)

second = ask("And what about a 500?")
print("write:", second.usage.cache_creation_input_tokens,
      "read:", second.usage.cache_read_input_tokens,
      "fresh:", second.usage.input_tokens)
```

Przykładowy wynik (konkretne liczby zależą od długości `POLICY` i tokenizera modelu):

```text
write: 1612 read: 0 fresh: 15
write: 0 read: 1612 fresh: 16
```

Pierwsze wywołanie zapisuje prefiks (`cache_creation_input_tokens`), drugie go odczytuje (`cache_read_input_tokens`), a `input_tokens` liczy wyłącznie to, co jest za ostatnim breakpointem – czyli samo pytanie. Dokładne liczby zależą od długości `POLICY`, ale wzorzec jest zawsze taki: zapis w pierwszym wywołaniu, odczyt w każdym kolejnym w oknie TTL. Suma tych trzech pól to całkowita liczba tokenów wejściowych. Zwróć uwagę, że `system` jest tu listą bloków, a nie stringiem – `cache_control` ustawia się na bloku, więc string trzeba najpierw „opakować". To jest też Twój podstawowy test diagnostyczny: jeśli `cache_read_input_tokens` uparcie wynosi zero przy powtarzanych żądaniach, gdzieś w prefiksie siedzi coś zmiennego, najczęściej `datetime.now()` w system prompcie albo słownik serializowany bez sortowania kluczy.

Z tego wynika konkretny sposób projektowania warstwy promptów. Trzymaj w prefiksie wszystko, co jest wspólne dla ruchu: definicje narzędzi w ustalonej kolejności, system prompt, przykłady few-shot, stałe fragmenty dokumentacji. Wszystko, co jest per żądanie – identyfikator korelacji, znacznik czasu, nazwa użytkownika – umieszczaj za ostatnim breakpointem albo, jeśli musi być w system prompcie, zaakceptuj, że płacisz pełną stawkę za cały prefiks. Cztery breakpointy wystarczają na typowy podział na warstwy zmieniające się z różną częstotliwością: narzędzia (zmiana raz na wdrożenie), polityka (raz na tydzień), dokumentacja klienta (raz na dzień), historia rozmowy (co turę). Cache jest przy tym związany z modelem, więc kaskada „tanim modelem, a trudne do drogiego" traci możliwość współdzielenia prefiksu i bywa droższa, niż wygląda na cenniku.

OpenAI robi to samo automatycznie. Cache jest domyślnie włączony dla wspieranych modeli, minimalna długość to 1024 widoczne tokeny wejściowe (GPT-5.6 i nowsze), a tokeny odczytane z cache kosztują 0,1 stawki podstawowej. Czas życia to 30 minut dla GPT-5.6 i nowszych. W odpowiedzi znajdziesz to w polu `usage.input_tokens_details.cached_tokens`. Opcjonalny parametr `prompt_cache_key` rozdziela rozliczenie cache między klientów lub użytkowników. Zasada układania promptu jest identyczna, bo mechanizm jest ten sam: stałe na początku, zmienne na końcu (stan na wrzesień 2026).

### Streaming

Streaming to przesyłanie odpowiedzi kawałkami, w miarę jak model ją generuje, zamiast czekania na całość. Powód jest głównie produktowy: time-to-first-token spada z kilku sekund do kilkuset milisekund, a użytkownik widzi, że coś się dzieje. Jest też powód techniczny – przy dużym `max_tokens` żądanie nieustawione na streaming potrafi przekroczyć limit czasu połączenia HTTP, dlatego SDK Anthropic wymaga streamingu przy naprawdę długich odpowiedziach.

Pod spodem jest strumień zdarzeń SSE: `message_start` (z obiektem wiadomości i początkowym `usage`), potem serie `content_block_start`, `content_block_delta`, `content_block_stop` dla każdego bloku treści, następnie `message_delta` z `stop_reason` i skumulowanym `usage`, i na końcu `message_stop`. Pythonowe SDK opakowuje to w context manager, który sam składa całość.

```python
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

with client.messages.stream(
    model="claude-opus-5",
    max_tokens=1024,
    system="You are a concise backend engineering tutor.",
    messages=[{"role": "user", "content": "Explain idempotency keys in three sentences."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    message = stream.get_final_message()

print()
print("stop_reason:", message.stop_reason)
print("usage:", message.usage.input_tokens, message.usage.output_tokens)
```

`stream.text_stream` daje wyłącznie przyrosty tekstu, więc nadaje się wprost do wypisania na wyjście albo wysłania po WebSockecie. `get_final_message()` zwraca kompletny obiekt `Message` – identyczny z tym, który dostałbyś z `messages.create()` – więc `usage` i `stop_reason` masz bez dodatkowego żądania. Wywołaj go po wyczerpaniu strumienia; wcześniej i tak musiałby poczekać na jego koniec.

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

stream = client.responses.create(
    model="gpt-6-astra",
    input=[{"role": "user", "content": "Explain idempotency keys in three sentences."}],
    stream=True,
)

chunks = []
for event in stream:
    if event.type == "response.output_text.delta":
        chunks.append(event.delta)
        print(event.delta, end="", flush=True)
    elif event.type == "response.completed":
        usage = event.response.usage

print()
print("full length:", len("".join(chunks)))
print("usage:", usage.input_tokens, usage.output_tokens)
```

Po stronie OpenAI iterujesz po zdarzeniach i sam wybierasz te, które Cię interesują: `response.output_text.delta` niesie przyrost tekstu w polu `delta`, a `response.completed` niesie kompletny obiekt odpowiedzi wraz z `usage`. Pełną odpowiedź składasz z fragmentów albo bierzesz gotową z `event.response`.

Ostatnia uwaga: streaming z narzędziami wymaga uwagi. Argumenty wywołania narzędzia nie przychodzą w całości, tylko jako seria delt typu `input_json_delta` z polem `partial_json`, które trzeba skleić i dopiero wtedy sparsować. Dopóki blok się nie zakończy, masz w ręku niekompletny JSON, więc nie próbuj go parsować po każdej delcie. Jeśli używasz `client.messages.stream()`, SDK złoży to za Ciebie i w `get_final_message()` dostaniesz gotowe bloki `tool_use` z `input` jako słownikiem.

## Podsumowanie

- Prompt to wejście funkcji, a nie zaklęcie: ma strukturę (`system`, `messages`, bloki treści) i parametry, które egzekwują ograniczenia lepiej niż proza.
- System prompt trzymaj na rzeczy stałe (rola, zakres, reguły zachowania), a dane zmienne wkładaj do wiadomości użytkownika – to jednocześnie warunek działania cache.
- Długie dane umieszczaj na górze promptu, pytanie na dole, a granice oznaczaj delimiterami, najlepiej tagami XML.
- Ograniczenia formułuj pozytywnie i z uzasadnieniem: „pisz ciągłą prozą, bo syntezator mowy nie czyta list" działa lepiej niż „nie używaj list".
- Ustrukturyzowane wyjście bierz z natywnego mechanizmu (`messages.parse()` z Pydantikiem po stronie Anthropic, `responses.parse()` po stronie OpenAI), a nie z proszenia o JSON w prozie.
- Zaczynaj od zero-shot, mierz, i dopiero potem dokładaj trzy do pięciu zróżnicowanych przykładów few-shot; przykłady są pierwszym kandydatem do cache'owania.
- Na modelach rozumujących jawny chain-of-thought zastępuje natywne myślenie adaptacyjne sterowane parametrem `effort`; dopisek „think step by step" jest tam zwykle zbędny.
- Function calling to pętla: `tool_use` w odpowiedzi, `tool_result` w wiadomości `user`, warunek pętli na `stop_reason`, cała historia dopisywana bez skracania.
- Prompt caching opłaca się wszędzie tam, gdzie prefiks jest stały i długi; odczyt kosztuje 0,1 stawki wejściowej, a `cache_read_input_tokens` równe zeru to sygnał, że coś w prefiksie się zmienia.
- Streaming poprawia odczuwalną szybkość i chroni przed timeoutami przy długich odpowiedziach; pełny `usage` dostajesz na końcu strumienia.

## Co dalej

Ten rozdział pokazał, jak zbudować pojedynczy prompt i jedno wywołanie. Rozdział 4 („Context engineering") zajmuje się tym, co robić, gdy danych jest więcej, niż mieści okno kontekstu, i jak zarządzać historią rozmowy, która rośnie z każdą turą – od wyboru, co do kontekstu w ogóle trafia, przez kompaktowanie i czyszczenie wyników narzędzi, po budżetowanie tokenów. Zanim tam przejdziesz, zrób dwie rzeczy samodzielnie: wyciągnij prompty z jednego ze swoich skryptów do osobnego modułu i dopisz do każdego jedno zdanie o tym, co ma sprawdzać; a potem uruchom snippet z cache'owaniem na własnym system prompcie i sprawdź, czy `cache_read_input_tokens` rośnie przy drugim wywołaniu. Jeśli nie rośnie, masz w prefiksie coś zmiennego – i to jest najlepsze możliwe wprowadzenie do następnego rozdziału.

## Źródła

- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/build-with-claude/streaming
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python
- https://github.com/anthropics/anthropic-sdk-python
- https://developers.openai.com/api/docs/guides/text
- https://developers.openai.com/api/docs/guides/function-calling
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://developers.openai.com/api/docs/guides/streaming-responses
- https://developers.openai.com/api/docs/models
