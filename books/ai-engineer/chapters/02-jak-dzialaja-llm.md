# Rozdział 2. Jak działają LLM-y

> **Z roadmapy:** How LLMs Work, Core LLM Elements: Tokens, Context, Sampling Parameters, Temperature, Top-K, Top-P, Repetition Penalties, Type of Models, Training, Inference
>
> **Pakiety:** `pip install anthropic openai tiktoken numpy`

Możesz zbudować działającą integrację z LLM-em, nie wiedząc, co dzieje się pod spodem. Problem pojawia się później: gdy rachunek za API rośnie trzy razy szybciej niż ruch, gdy ten sam prompt raz zwraca poprawny JSON, a raz akapit wstępu, gdy aplikacja nagle dostaje HTTP 400 po dwudziestej wiadomości w rozmowie. Każda z tych sytuacji ma swoje wyjaśnienie w mechanice modelu i żadnej z nich nie da się naprawić metodą prób i błędów na poziomie tekstu promptu.

Ten rozdział jest o trzech rzeczach, które kontrolujesz jako programista: co wchodzi do modelu (tokeny i okno kontekstu), co model robi z tym wejściem (inferencja) i jak wybiera każde kolejne słowo (sampling). Wszystkie trzy mają bezpośrednie przełożenie na koszt, opóźnienie i powtarzalność wyników. Im wcześniej zrozumiesz, gdzie jest granica między „to da się ustawić parametrem" a „to trzeba rozwiązać architekturą", tym mniej czasu stracisz na debugowanie zachowań, które są z definicji losowe.

Jest też powód, żeby przeczytać ten rozdział teraz, a nie polegać na tym, co pamiętasz z artykułów sprzed dwóch lat. Część klasycznej wiedzy o sterowaniu modelem – w szczególności `temperature` – przestała obowiązywać na czołowych modelach obu głównych dostawców. Pokażę dokładnie, co się zmieniło i co weszło na to miejsce.

## Od tekstu do tokenów

Model nie widzi znaków ani słów. Widzi ciąg liczb całkowitych – identyfikatorów w słowniku o ustalonym rozmiarze. Token (token) to jednostka tego słownika: czasem całe słowo, czasem fragment słowa, czasem pojedynczy znak interpunkcyjny razem ze spacją, która go poprzedza. Tokenizacja jest deterministyczna i odwracalna – ten sam tekst zawsze da ten sam ciąg identyfikatorów, a z identyfikatorów zawsze odtworzysz oryginalny tekst co do bajtu.

Standardem jest dziś BPE (byte pair encoding). Algorytm startuje od pojedynczych bajtów i w pętli scala najczęściej występującą parę sąsiadujących jednostek w nową jednostkę, powtarzając to aż słownik osiągnie zadany rozmiar. Efekt jest taki, że częste sekwencje – angielskie słowa, popularne końcówki, typowe wcięcia w kodzie – dostają własne tokeny, a rzadkie rozpadają się na kawałki. Ponieważ scalanie odbywa się na bajtach, każdy tekst da się zakodować, nawet taki, którego tokenizer nigdy nie widział.

I tu zaczyna się problem języka polskiego. Korpusy treningowe, na których uczono tokenizery, są zdominowane przez angielski, więc to angielskie sekwencje wygrały konkurs o miejsce w słowniku. Polska fleksja, znaki diakrytyczne i długie wyrazy złożone rozpadają się na wiele fragmentów. Zmierzmy to zamiast szacować.

```python
import tiktoken

# o200k_base is the encoding used by current GPT models.
enc = tiktoken.get_encoding("o200k_base")

PL = "Wczoraj zaimplementowaliśmy nieprzewidywalne zachowanie modelu językowego."
EN = "Yesterday we implemented the unpredictable behaviour of the language model."

for label, text in (("PL", PL), ("EN", EN)):
    ids = enc.encode(text)
    pieces = [enc.decode([i]) for i in ids]
    print(f"{label}: chars={len(text)} tokens={len(ids)}")
    print(f"    {pieces}")

print(f"ratio PL/EN = {len(enc.encode(PL)) / len(enc.encode(EN)):.2f}")
```

```text
PL: chars=74 tokens=21
    ['W', 'cz', 'oraj', ' za', 'implement', 'ow', 'aliśmy', ' nie', 'pr', 'zew', 'idy', 'wal', 'ne', ' zach', 'owanie', ' model', 'u', ' ję', 'zyk', 'owego', '.']
EN: chars=75 tokens=11
    ['Yesterday', ' we', ' implemented', ' the', ' unpredictable', ' behaviour', ' of', ' the', ' language', ' model', '.']
ratio PL/EN = 1.91
```

Dwa zdania o praktycznie identycznej długości w znakach – 74 i 75 – kosztują 21 i 11 tokenów. Zwróć uwagę na podział: „Yesterday" to jeden token, a „Wczoraj" rozpada się na trzy. Angielskie „implemented" to jeden token, polskie „zaimplementowaliśmy" – cztery. Konsekwencja jest bezpośrednio finansowa: ten sam dokument po polsku zajmie w oknie kontekstu około dwa razy więcej miejsca i będzie kosztował około dwa razy więcej niż jego angielski odpowiednik. Jeżeli budujesz system RAG na polskich dokumentach, wlicz ten mnożnik w budżet od pierwszego dnia.

Jedna pułapka, która kosztuje ludzi realne pieniądze: `tiktoken` jest tokenizerem OpenAI i nie służy do liczenia tokenów dla Claude. Dla typowego tekstu zaniża wynik o kilkanaście do dwudziestu procent, a dla kodu i tekstów nieangielskich znacznie bardziej. Anthropic udostępnia do tego osobny endpoint, który liczy dokładnie tak, jak policzy go model przy właściwym wywołaniu.

```python
import os
import anthropic

MODEL = "claude-opus-5"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PL = "Wczoraj zaimplementowaliśmy nieprzewidywalne zachowanie modelu językowego."
EN = "Yesterday we implemented the unpredictable behaviour of the language model."


def count(text: str) -> int:
    response = client.messages.count_tokens(
        model=MODEL,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens


pl_tokens, en_tokens = count(PL), count(EN)
print(f"PL={pl_tokens} EN={en_tokens} ratio={pl_tokens / en_tokens:.2f}")
```

Endpoint `count_tokens` przyjmuje dokładnie ten sam kształt żądania co `messages.create` – łącznie z system promptem, definicjami narzędzi, obrazami i dokumentami PDF – i zwraca `input_tokens`. Jest bezpłatny i ma własny limit zapytań na minutę, niezależny od limitu na generowanie wiadomości, więc możesz wołać go przed każdym realnym żądaniem. Licz zawsze na tym samym identyfikatorze modelu, którego użyjesz do inferencji: modele Claude od wersji 4.7 wzwyż mają nowszy tokenizer, który dla tego samego tekstu daje około 30 procent więcej tokenów niż modele wcześniejsze (stan na wrzesień 2026). Przeniesienie aplikacji na nowszy model bez przeliczenia promptów to najprostszy sposób na niespodziankę w rachunku.

## Trening a inferencja

Model powstaje w trzech etapach i każdy z nich zostawia ślad w tym, jak zachowuje się w twojej aplikacji. Pretraining (pre-training) to uczenie na ogromnym korpusie tekstu w jednym zadaniu: przewidzieć następny token. Model nie dostaje etykiet ani instrukcji – uczy się statystyki języka, faktów o świecie i struktury kodu wyłącznie z tego, co najczęściej następuje po czym. To najdroższy etap, liczony w miesiącach pracy klastrów GPU, i to on ustala datę odcięcia wiedzy modelu.

Instruction tuning to znacznie krótszy etap douczania na parach „polecenie – dobra odpowiedź". Model bazowy zapytany „Jaka jest stolica Polski?" równie chętnie wygeneruje kolejne pytania z tego samego testu, bo tak wygląda statystycznie tekst, w którym takie zdanie występuje. Model po instruction tuningu odpowiada na pytanie, bo nauczył się, że po instrukcji następuje jej wykonanie. Trzeci etap, RLHF (reinforcement learning from human feedback) i jego warianty, dostraja model względem ludzkich preferencji: ludzie porównują pary odpowiedzi, na tych porównaniach uczy się model nagrody, a nim optymalizuje się model główny. Stąd bierze się ton odpowiedzi, skłonność do odmowy przy szkodliwych prośbach i – ubocznie – rozwlekłość, z którą walczysz potem w promptach.

Inferencja, czyli to, co dzieje się przy twoim wywołaniu API, ma dwie wyraźnie różne fazy i warto je rozróżniać, bo inaczej się skalują. **Prefill** to przetworzenie całego wejścia: system promptu, historii rozmowy, definicji narzędzi. Wszystkie tokeny wejściowe idą przez model równolegle, w jednym przebiegu, więc faza jest ograniczona mocą obliczeniową i skaluje się dobrze. **Decode** to generowanie odpowiedzi token po tokenie. Każdy token wymaga osobnego przebiegu przez cały model i nie da się tego zrównoleglić, bo token numer 50 zależy od tokena numer 49. Ta faza jest ograniczona przepustowością pamięci i to ona odpowiada za czas oczekiwania na długą odpowiedź.

Ta asymetria tłumaczy cennik. Tokeny wyjściowe kosztują u Anthropic dokładnie pięć razy więcej niż wejściowe na każdym modelu z bieżącej rodziny: Claude Opus 5 to 5 USD za milion tokenów wejściowych i 25 USD za milion wyjściowych, Claude Sonnet 5 to 2 i 10 USD, Claude Haiku 4.5 to 1 i 5 USD (stan na wrzesień 2026). Wnioski projektowe są konkretne. Po pierwsze, skracanie odpowiedzi opłaca się pięciokrotnie bardziej niż skracanie promptu – instrukcja „odpowiedz jednym zdaniem" bywa skuteczniejszą optymalizacją kosztu niż przycinanie kontekstu. Po drugie, ponieważ prefill jest powtarzalny, można go cache'ować: odczyt z cache'u promptu kosztuje 10 procent ceny bazowej tokenów wejściowych. Po trzecie, opóźnienie do pierwszego tokena zależy głównie od długości wejścia, a całkowity czas odpowiedzi głównie od długości wyjścia – jeżeli użytkownik narzeka na powolność, zmierz, która z tych dwóch liczb rośnie.

## Okno kontekstu

Okno kontekstu (context window) to maksymalna liczba tokenów, którą model może naraz objąć – i wbrew nazwie nie jest to tylko miejsce na twoje pytanie. Mieści się w nim wszystko: system prompt, każda wiadomość w historii rozmowy, definicje wszystkich narzędzi, które udostępniasz, treści zwrócone przez te narzędzia, załączone obrazy i dokumenty, a także odpowiedź, którą model dopiero wygeneruje, razem z jego wewnętrznym rozumowaniem. Model jest bezstanowy: przy każdym wywołaniu wysyłasz całą historię od nowa, więc rozmowa nie tyle „trwa", co rośnie liniowo z każdą turą.

| Model | Okno kontekstu | Maks. tokenów wyjścia |
| --- | --- | --- |
| `claude-opus-5` | 1 000 000 | 128 000 |
| `claude-sonnet-5` | 1 000 000 | 128 000 |
| `claude-haiku-4-5` | 200 000 | 64 000 |
| `claude-fable-5-1` | 1 000 000 | 128 000 |
| `gpt-6-astra` | 1 050 000 | 128 000 |
| `gpt-5.6-sol` | 1 050 000 | 128 000 |

Wartości sprawdzone w dokumentacji Anthropic i OpenAI (stan na wrzesień 2026).

Po przekroczeniu limitu zachowanie jest ściśle określone i warto je znać, bo to dwa różne przypadki. Jeżeli samo wejście nie mieści się w oknie, dostajesz HTTP 400 `invalid_request_error` z komunikatem „prompt is too long" i żadna odpowiedź nie powstaje. Jeżeli natomiast wejście się mieści, ale wejście plus `max_tokens` przekracza okno, modele Claude od generacji 4.5 wzwyż przyjmują żądanie i generują odpowiedź, a gdy dobiją do limitu, zatrzymują się ze `stop_reason` równym `model_context_window_exceeded`. To znaczy, że musisz sprawdzać `stop_reason`, a nie zakładać, że brak wyjątku oznacza kompletną odpowiedź.

```python
import os
import anthropic

MODEL = "claude-opus-5"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
limits = client.models.retrieve(MODEL)
print(f"context window: {limits.max_input_tokens}, max output: {limits.max_tokens}")

history = [
    {"role": "user", "content": "Wyjaśnij, czym jest prefill w inferencji LLM."},
    {"role": "assistant", "content": "Prefill to równoległe przetworzenie tokenów wejściowych."},
    {"role": "user", "content": "A czym różni się od fazy decode?"},
]

budget = client.messages.count_tokens(model=MODEL, messages=history).input_tokens
print(f"history costs {budget} input tokens")

try:
    response = client.messages.create(
        model=MODEL, max_tokens=1024, messages=history,
    )
    print(f"stop_reason={response.stop_reason}")
    if response.stop_reason == "model_context_window_exceeded":
        print("Odpowiedź ucięta na granicy okna – skróć historię.")
except anthropic.BadRequestError as exc:
    print(f"Żądanie odrzucone przed generowaniem: {exc}")
```

Snippet pokazuje trzy rzeczy, które powinny być odruchem. `client.models.retrieve` zwraca limity modelu programowo w polach `max_input_tokens` i `max_tokens`, więc nie musisz ich zapisywać na sztywno w kodzie i nie zdezaktualizują się po zmianie modelu. `count_tokens` pozwala zmierzyć historię, zanim ją wyślesz, i zdecydować, czy przyciąć starsze tury. Wreszcie obsłużone są oba tryby awarii: `BadRequestError` dla wejścia za długiego i sprawdzenie `stop_reason` dla odpowiedzi uciętej w trakcie.

Warto dodać, że duże okno nie jest darmowe jakościowo. Wraz ze wzrostem liczby tokenów pogarsza się zdolność modelu do precyzyjnego odwoływania się do szczegółów w środku kontekstu – zjawisko nazywane „context rot". Milion tokenów to nie jest zaproszenie do wrzucenia całej bazy dokumentów do promptu. To margines bezpieczeństwa dla agentów, które wykonują wiele kroków z narzędziami. Do wyszukiwania w dużych zbiorach służy RAG, do którego wrócimy w dalszych rozdziałach.

## Jak model wybiera następny token

Wejście przechodzi przez sieć i na wyjściu ostatniej warstwy dostajesz wektor o długości równej rozmiarowi słownika – po jednej liczbie na każdy możliwy token. Te liczby to logity (logits). Nie są prawdopodobieństwami: mogą być ujemne, nie sumują się do jedynki, mają sens tylko względny. Logit 4,2 oznacza tylko tyle, że ten token jest bardziej prawdopodobny niż token z logitem 2,1.

Zamiana logitów na rozkład prawdopodobieństwa to funkcja softmax, jedyny wzór w tym rozdziale:

$$P(t_i) = \frac{e^{z_i / T}}{\sum_j e^{z_j / T}}$$

gdzie $z_i$ to logit tokena $i$, a $T$ to temperatura. Eksponenta gwarantuje wartości dodatnie, dzielenie przez sumę – że wszystko zsumuje się do jedynki. Cała rola temperatury sprowadza się do dzielenia logitów przed eksponentą. Przy $T$ mniejszym od 1 różnice między logitami się powiększają i rozkład robi się ostry; przy $T$ większym od 1 różnice maleją i rozkład się spłaszcza. Zobacz to na liczbach.

```python
import numpy as np

VOCAB = ["kawa", "herbata", "sok", "beton"]
LOGITS = np.array([4.2, 3.8, 2.1, -1.5])


def softmax(logits: np.ndarray, temperature: float) -> np.ndarray:
    scaled = logits / temperature
    exp = np.exp(scaled - scaled.max())  # subtract max for numerical stability
    return exp / exp.sum()


for t in (0.2, 0.7, 1.0, 2.0):
    probs = softmax(LOGITS, t)
    row = "  ".join(f"{w}={p:.3f}" for w, p in zip(VOCAB, probs))
    print(f"T={t:<4} {row}")
```

```text
T=0.2  kawa=0.881  herbata=0.119  sok=0.000  beton=0.000
T=0.7  kawa=0.619  herbata=0.350  sok=0.031  beton=0.000
T=1.0  kawa=0.557  herbata=0.373  sok=0.068  beton=0.002
T=2.0  kawa=0.449  herbata=0.368  sok=0.157  beton=0.026
```

Przy $T$ równym 0,2 model wybierze „kawa" w 88 procentach przypadków, a „beton" praktycznie nigdy. Przy $T$ równym 2,0 przewaga „kawy" spada do 45 procent, a bezsensowny „beton" dostaje 2,6 procent szansy – i przy dostatecznie wielu wywołaniach kiedyś wypadnie. To jest cała tajemnica „kreatywności" modelu i zarazem cała tajemnica halucynacji przy wysokiej temperaturze. Zwróć też uwagę, że nawet przy $T$ równym 1,0 najlepszy token nie jest pewny – model nigdy nie jest deterministyczny „z natury", jest nim tylko wtedy, gdy zmusisz go do wybierania maksimum.

Ostatni krok to sampling: losowanie tokena zgodnie z tym rozkładem. Wylosowany token dopisuje się do sekwencji, ta wraca na wejście i cykl powtarza się dla kolejnej pozycji. Parametry samplowania nie zmieniają tego, co model „wie" – zmieniają wyłącznie sposób, w jaki losujesz z gotowego rozkładu.

## Parametry samplowania

Zanim przejdziemy do poszczególnych parametrów, jedna rzecz, która zaskakuje osoby wracające do tematu po przerwie. Na czołowych modelach obu głównych dostawców klasyczne parametry samplowania zostały wycofane. W API Anthropic `temperature` jest oznaczone jako deprecated z jednoznaczną notatką: modele wydane po Claude Opus 4.6 nie wspierają ustawiania temperatury, wartość 1.0 jest przyjmowana dla zgodności wstecznej, a każda inna zwraca błąd 400. To samo dotyczy `top_p` i `top_k` na modelach Claude Opus 5, Sonnet 5 i Fable 5.1. Po stronie OpenAI dokumentacja migracji na bieżące modele mówi wprost: „Remove `temperature`, `top_p`, and `top_logprobs`" (stan na wrzesień 2026).

Powód jest ten sam u obu dostawców: bieżące modele czołowe są modelami rozumującymi i ich jakość zależy od przebiegu wewnętrznego rozumowania, a nie od ręcznego spłaszczania rozkładu. Ich miejsce zajął parametr wysiłku – `effort` u Anthropic, `reasoning.effort` u OpenAI. Parametry poniżej nadal są w pełni aktualne na modelach spoza tej ścisłej czołówki (u Anthropic `claude-haiku-4-5` i modele generacji 4.6) oraz w całym świecie open source, gdzie samodzielnie sterujesz pętlą generowania. Musisz je rozumieć, bo pojęcia wracają w każdej bibliotece lokalnej inferencji.

### Temperature

Temperatura dzieli logity przed softmaksem, jak w poprzedniej sekcji. Wartość 0 oznacza greedy decoding – zawsze bierzemy token o najwyższym prawdopodobieństwie – i jest najbliższa determinizmowi, jaką da się uzyskać. Zakres to 0–1 u Anthropic i 0–2 u OpenAI, z domyślną wartością 1,0 w obu przypadkach. Do zadań, w których istnieje jedna poprawna odpowiedź – klasyfikacja, ekstrakcja danych, generowanie JSON-a, wybór narzędzia – ustawiaj wartości bliskie 0. Do generowania wariantów tekstu, burzy mózgów czy dialogów sięgaj po 0,7–1,0.

```python
import os
import anthropic

# Claude Haiku 4.5 still accepts sampling parameters; models released after
# Claude Opus 4.6 reject any temperature other than 1.0 with HTTP 400.
MODEL = "claude-haiku-4-5"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
PROMPT = "Podaj jedną nazwę dla biblioteki do cache'owania w Pythonie. Sama nazwa."

for temperature in (0.0, 1.0):
    answers = []
    for _ in range(3):
        response = client.messages.create(
            model=MODEL,
            max_tokens=32,
            temperature=temperature,
            messages=[{"role": "user", "content": PROMPT}],
        )
        answers.append(response.content[0].text.strip())
    print(f"temperature={temperature}: {answers}")
```

Uruchom to kilka razy. Przy `temperature=0.0` trzy odpowiedzi będą niemal zawsze identyczne, przy `temperature=1.0` zobaczysz trzy różne nazwy. Podkreślam „niemal": zero nie gwarantuje pełnego determinizmu, bo na wynik wpływa jeszcze kolejność operacji zmiennoprzecinkowych przy zrównoleglonym wykonaniu na GPU i skład partii żądań na serwerze. Jeżeli twoje testy wymagają powtarzalności co do znaku, nie opieraj ich na równości stringów – sprawdzaj strukturę odpowiedzi albo użyj modelu atrapy.

### Top-K

Top-K obcina rozkład do $K$ najbardziej prawdopodobnych tokenów, zeruje resztę i normalizuje pozostałe prawdopodobieństwa, dopiero z tego losując. Przy `top_k=1` dostajesz greedy decoding, przy `top_k=50` odcinasz ogon rozkładu, zachowując sensowną różnorodność. Wadą jest sztywność: $K$ jest stałe niezależnie od tego, czy rozkład jest ostry, czy płaski. W sytuacji, gdy jeden token ma prawdopodobieństwo 0,95, top-K i tak dopuszcza 49 alternatyw; gdy rozkład jest płaski, odcina sensowne kandydatury. `top_k` istnieje w API Anthropic (na modelach, które wspierają sampling) i w bibliotekach open source. **W API OpenAI nie ma parametru `top_k`** – nie szukaj go tam.

### Top-P

Top-P, zwane też nucleus sampling, rozwiązuje problem sztywności top-K. Zamiast stałej liczby tokenów bierze najmniejszy zbiór, którego łączne prawdopodobieństwo przekracza próg $P$. Przy `top_p=0.9` z ostrego rozkładu zostaną dwa–trzy tokeny, a z płaskiego kilkadziesiąt – próg dostosowuje się do sytuacji. To dlatego top-P jest dziś domyślnym wyborem tam, gdzie sampling w ogóle jest dostępny. Typowe wartości to 0,9–0,95; schodzenie poniżej 0,5 zwykle niepotrzebnie zubaża wypowiedź.

Obaj dostawcy zgodnie odradzają łączenie top-P z temperaturą. Dokumentacja OpenAI mówi: „We generally recommend altering this or `top_p` but not both". Rekomendacja Anthropic jest taka sama. Powód jest praktyczny: oba parametry sterują tym samym – szerokością rozkładu, z którego losujesz – tyle że w różny sposób, a ich złożenie daje efekt trudny do przewidzenia i jeszcze trudniejszy do dostrojenia. Wybierz jeden i zostaw drugi na wartości domyślnej.

### Repetition Penalties

Poprzednie trzy parametry działają na rozkładzie jednej pozycji, niezależnie od tego, co model już napisał. Kary za powtórzenia działają inaczej: modyfikują logity tokenów **na podstawie historii bieżącej generacji**. To one zapobiegają pętlom, w które model potrafi wpaść przy dłuższych wypowiedziach.

OpenAI udostępnia dwa niezależne parametry, oba w zakresie od -2,0 do 2,0 z domyślnym 0. `frequency_penalty` karze token proporcjonalnie do tego, ile razy już wystąpił – im częściej, tym mocniejsza kara, co zwalcza dosłowne powtarzanie fraz. `presence_penalty` karze token jednorazowo za sam fakt, że już się pojawił, niezależnie od liczby wystąpień – to raczej popychanie modelu w stronę nowych tematów niż walka z zapętleniem.

```python
import os
from openai import OpenAI

MODEL = "gpt-5.6-luna"  # check docs for the current model id

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
PROMPT = "Opisz w pięciu zdaniach zalety cache'owania promptów."

for freq, pres in ((0.0, 0.0), (1.2, 0.6)):
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        frequency_penalty=freq,
        presence_penalty=pres,
        max_completion_tokens=300,
    )
    print(f"--- frequency={freq} presence={pres} ---")
    print(completion.choices[0].message.content)
```

Przy zerowych karach zobaczysz, że model chętnie powtarza sformułowanie „cache'owanie promptów" w każdym zdaniu. Przy wartościach dodatnich zacznie sięgać po synonimy i zaimki. Nie przesadzaj z siłą: wartości powyżej około 1,5 potrafią wypchnąć model z poprawnej terminologii, bo kara nie rozróżnia powtórzenia stylistycznego od terminu technicznego, który po prostu musi się powtarzać.

W świecie open source ten sam mechanizm nazywa się inaczej i działa multiplikatywnie, a nie addytywnie. W bibliotece `transformers` argument `repetition_penalty` przyjmuje wartość 1,0 jako brak kary, a typowo 1,1–1,2 jako kara umiarkowana – logity już użytych tokenów są dzielone przez tę wartość. To samo pojęcie i ta sama nazwa parametru występują w `llama.cpp` i w większości lokalnych serwerów inferencji. Zwróć uwagę na różnicę skali: 1,2 w `transformers` jest wartością łagodną, podczas gdy 1,2 w `frequency_penalty` OpenAI jest już wyraźnie agresywne. Te liczby nie są przenośne między API.

## Rodzaje modeli w skrócie

Model bazowy (base / pre-trained model) to wynik samego pretreningu. Kontynuuje tekst, który dostał, i nic więcej – nie odpowiada na pytania, tylko przedłuża je w statystycznie prawdopodobny sposób. Dostawcy komercyjni rzadko wystawiają takie modele przez API; spotkasz je głównie na Hugging Face, w nazwach bez sufiksu `-instruct`. Są punktem wyjścia do własnego fine-tuningu.

Model instrukcyjny (instruction-tuned) to model bazowy po instruction tuningu i RLHF. Rozumie role w rozmowie, wykonuje polecenia, potrafi korzystać z narzędzi. To z nim pracujesz w dziewięciu na dziesięć przypadków i to jego wariant kryje się za większością identyfikatorów w API.

Model rozumujący (reasoning model) idzie krok dalej: zanim wygeneruje odpowiedź, produkuje wewnętrzny łańcuch rozumowania, który zwykle nie trafia w całości do użytkownika, ale jest liczony i płatny jak tokeny wyjściowe. U Anthropic sterujesz tym przez `thinking` i `output_config.effort`, u OpenAI przez `reasoning.effort`; obaj dostawcy przyjmują poziomy od `low` do `max`. I tu domyka się wątek z poprzedniej sekcji: właśnie na tych modelach parametry samplowania są niedostępne. Wysiłek zastąpił temperaturę jako główne pokrętło jakości i kosztu.

```python
import os
import anthropic

MODEL = "claude-opus-5"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

for effort in ("low", "high"):
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        messages=[{"role": "user", "content": "Ile jest liczb pierwszych mniejszych od 100?"}],
    )
    usage = response.usage
    print(f"effort={effort}: in={usage.input_tokens} out={usage.output_tokens}")
```

Zwróć uwagę na trzy szczegóły. `effort` jest zagnieżdżony w `output_config`, a nie podany na najwyższym poziomie – to częsty błąd. `thinking={"type": "adaptive"}` oznacza, że model sam decyduje, ile myśleć, w granicach wyznaczonych przez `effort`; starszy tryb ze stałym budżetem `budget_tokens` został na bieżących modelach usunięty i zwraca 400. Wreszcie `response.usage.output_tokens` obejmuje tokeny rozumowania, więc różnica między `low` a `high` będzie widoczna właśnie tam – i właśnie tam zobaczysz ją na rachunku. Szczegółowe porównanie rodzin modeli i kryteria wyboru znajdziesz w rozdziale 5.

## Podsumowanie

- Model widzi tokeny, nie znaki. Tekst polski kosztuje w praktyce około dwa razy więcej tokenów niż angielski o tej samej długości – wlicz ten mnożnik w budżet i w planowanie okna kontekstu.
- Do liczenia tokenów dla Claude używaj endpointu `messages.count_tokens`, nigdy `tiktoken`. Licz zawsze na tym samym identyfikatorze modelu, którego użyjesz do inferencji.
- Inferencja ma dwie fazy: prefill jest równoległy i zależy od długości wejścia, decode jest sekwencyjny i odpowiada za czas oczekiwania. Tokeny wyjściowe kosztują pięciokrotnie więcej niż wejściowe, więc skracanie odpowiedzi jest najtańszą optymalizacją.
- W oknie kontekstu mieści się wszystko: system prompt, cała historia, definicje narzędzi, wyniki narzędzi i generowana odpowiedź razem z rozumowaniem. Za długie wejście to HTTP 400, ucięta generacja to `stop_reason` równy `model_context_window_exceeded` – obsłuż oba przypadki.
- Model zamienia logity na prawdopodobieństwa przez softmax, a potem losuje. Temperatura skaluje logity przed softmaksem: niska wyostrza rozkład, wysoka go spłaszcza i wpuszcza tokeny bezsensowne.
- Top-K bierze stałą liczbę kandydatów, top-P bierze zmienną liczbę do progu prawdopodobieństwa. Nie łącz top-P z temperaturą – oba sterują tym samym. `top_k` nie istnieje w API OpenAI.
- Kary za powtórzenia działają na historii generacji: `frequency_penalty` rośnie z liczbą wystąpień, `presence_penalty` jest jednorazowa. Ich skale nie są przenośne między OpenAI a `repetition_penalty` w bibliotekach open source.
- Na bieżących modelach czołowych obu dostawców `temperature`, `top_p` i `top_k` zostały wycofane i zwracają błąd 400. Ich rolę przejął parametr wysiłku: `effort` u Anthropic, `reasoning.effort` u OpenAI.

## Co dalej

Skoro wiesz już, co model dostaje na wejściu i jak buduje odpowiedź, następnym krokiem jest nauczenie się, jak formułować to wejście, żeby dostawać wyniki, których oczekujesz. Rozdział 3 („Prompt engineering") pokazuje, jak system prompt różni się od wiadomości użytkownika, jak działa few-shot, jak wymuszać ustrukturyzowane wyjście i jak testować prompty, zamiast zgadywać. Zanim tam przejdziesz, zrób dwa ćwiczenia na własnych danych: przepuść przez `count_tokens` typowy dokument ze swojego projektu w wersji polskiej i angielskiej i porównaj wyniki, a potem uruchom to samo zapytanie na `claude-haiku-4-5` z `temperature` równą 0 i 1, po pięć razy, i zmierz, ile różnych odpowiedzi dostaniesz. Te dwie liczby powiedzą ci więcej o twoim przyszłym rachunku i o powtarzalności twojego systemu niż dowolna tabela w dokumentacji.

## Źródła

- https://platform.claude.com/docs/en/build-with-claude/token-counting
- https://platform.claude.com/docs/en/api/messages
- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/build-with-claude/context-windows
- https://platform.claude.com/docs/en/build-with-claude/thinking
- https://platform.claude.com/docs/en/build-with-claude/effort
- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/api-reference/chat/create
- https://developers.openai.com/api/docs/guides/reasoning
- https://developers.openai.com/api/docs/guides/latest-model
- https://github.com/openai/tiktoken
