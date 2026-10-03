# Rozdział 12. Obserwowalność, ewaluacje i testy regresyjne

> **Z roadmapy:** LLM Observability, Tracing & logging, Cost/latency monitoring, Production monitoring, Observability Tools, LangSmith, Langfuse, Helicone, Arize AI, LLM Evaluations, Evaluation Types, Deterministic Evals, Model-Based Evals, Human Evals, Evaluation Metrics, Evaluation Tools, DeepEval, RAGAS, Regression Testing
>
> **Pakiety:** `pip install anthropic pydantic pytest opentelemetry-sdk opentelemetry-api langfuse deepeval ragas`

Zmiana jednego zdania w system prompcie może poprawić jedną odpowiedź i zepsuć trzydzieści innych, których nie widziałeś. Bez zbioru ewaluacyjnego nie masz jak tego zauważyć – masz tylko poczucie, że „teraz brzmi lepiej". To nie jest inżynieria, to zgadywanie z kroplą potwierdzenia. Ten sam problem w drugą stronę dotyczy produkcji: aplikacja bez logowania wywołań modelu jest czarną skrzynką, w której użytkownik zgłasza „bot odpowiada bez sensu", a Ty nie umiesz odtworzyć ani promptu, ani odpowiedzi, ani wersji promptu, która wtedy obowiązywała.

W rozdziale 1 padło stwierdzenie, że ewaluacja jest w projektach z LLM-ami częścią definicji „done". Teraz zamienimy je na konkret. Definicja „done" dla funkcji opartej na modelu obejmuje trzy rzeczy, których nie ma w klasycznym backendzie: zbiór przypadków testowych z metryką i progiem, logowanie każdego wywołania modelu z usage i identyfikatorem wersji promptu oraz bramkę w CI, która nie przepuszcza spadku jakości. Wszystkie trzy da się zbudować w jeden dzień i wszystkie trzy zwracają się przy pierwszej zmianie modelu.

Kolejność w tym rozdziale jest odwrotna niż kolejność wdrażania. Najpierw obserwowalność, bo to z produkcji biorą się najlepsze przypadki testowe: prawdziwe zapytania użytkowników są lepszym zbiorem ewaluacyjnym niż cokolwiek, co wymyślisz przy biurku. Potem ewaluacje, czyli sposób mierzenia jakości na tych przypadkach. Na końcu testy regresyjne, czyli ewaluacje podłączone do CI, które zmieniają jednorazowy pomiar w mechanizm ochronny.

## Obserwowalność

Obserwowalność aplikacji LLM różni się od zwykłego APM w jednym istotnym punkcie: interesujący sygnał nie jest w kodzie statusu. Wywołanie modelu, które zwróciło 200 i zajęło 1,2 sekundy, może być kompletnie bezużyteczną odpowiedzią, a wywołanie, które trwało 40 sekund i pochłonęło 50 tysięcy tokenów, może być poprawne. Dlatego logujesz nie tylko czas i status, ale treść, zużycie i kontekst decyzyjny.

### Tracing i logowanie

Trace to zapis jednej operacji biznesowej od początku do końca – na przykład „użytkownik zadał pytanie i dostał odpowiedź". Span to pojedynczy krok wewnątrz trace'u, z czasem rozpoczęcia, czasem trwania i atrybutami. W aplikacji LLM typowy trace ma kilka spanów: retrieval (zapytanie do bazy wektorowej), wywołanie modelu, wywołanie narzędzia, drugie wywołanie modelu z wynikiem narzędzia. Spany zagnieżdżają się, więc od razu widać, że z ośmiu sekund odpowiedzi sześć zjadł retrieval, a nie model.

Co logować przy wywołaniu modelu: prompt (system i wiadomości), odpowiedź, `usage` w komplecie (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`), identyfikator modelu, wersję promptu, identyfikator użytkownika i sesji, latencję oraz `stop_reason`. Ostatnie dwa pola są niedoceniane. `stop_reason` równe `max_tokens` oznacza uciętą odpowiedź, a nie błąd – bez tego pola zobaczysz w statystykach same dwusetki i będziesz się zastanawiał, dlaczego użytkownicy narzekają na ucięte zdania. Wersja promptu jest z kolei jedyną rzeczą, która pozwala powiedzieć „jakość spadła po wdrożeniu z wtorku".

Czego nie logować: danych osobowych i sekretów. Prompt użytkownika to często najbardziej wrażliwa rzecz w całym systemie – zawiera treść maila, numer sprawy, dane medyczne. Jeśli logujesz treść, rób to świadomie: z maskowaniem wzorców (PESEL, numer karty, adres e-mail), z krótką retencją i z osobnym uprawnieniem do odczytu. Identyfikator użytkownika trzymaj jako nieodwracalny hash albo wewnętrzny identyfikator, nie jako adres e-mail. Szczegóły – klasyfikacja danych, minimalizacja, zgody – są w rozdziale 11; tutaj wystarczy reguła, że log z wywołań modelu jest zbiorem danych osobowych i podlega tym samym zasadom co baza.

Najprostsza użyteczna wersja to jeden plik JSONL i wrapper wokół wywołania.

```python
import json
import os
import time
import uuid
from datetime import datetime, timezone
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
PROMPT_VERSION = "support-v7"
SYSTEM_PROMPT = "You are a support assistant for the Acme Payments API."

def call_and_log(user_id: str, question: str, log_path: str = "llm_calls.jsonl"):
    started = time.perf_counter()
    message = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
        metadata={"user_id": user_id},
    )
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": str(uuid.uuid4()),
        "user_id": user_id,
        "prompt_version": PROMPT_VERSION,
        "model": message.model,
        "stop_reason": message.stop_reason,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": message.usage.model_dump(),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return message

call_and_log("u-1042", "Webhooki przychodzą u mnie podwójnie. Co robić?")
```

Ten rekord nie zawiera treści promptu ani odpowiedzi – i to jest domyślna, bezpieczna wersja. Treść dokładasz osobnym polem, gdy wiesz, że masz do tego podstawę i mechanizm maskowania. `message.usage.model_dump()` daje cały słownik zużycia, razem z polami cache, więc nie musisz pamiętać, które pola istnieją w danej wersji SDK. Parametr `metadata={"user_id": ...}` jest przekazywany do API Anthropic i pomaga dostawcy w wykrywaniu nadużyć; ma tam trafiać identyfikator nieodwracalny, a nie e-mail. Plik JSONL wystarcza do pierwszych tygodni – łatwo go zgrepować, wczytać pandasem i policzyć dowolny agregat.

Gdy trace ma więcej niż jeden krok, własny format przestaje wystarczać i warto sięgnąć po standard. OpenTelemetry (OTel) jest w tej roli neutralnym wyborem: eksportujesz spany do dowolnego backendu, który mówi OTLP, i nie wiążesz się z jednym dostawcą. Dla aplikacji LLM istnieją osobne konwencje semantyczne GenAI, definiujące nazwy atrybutów (`gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.conversation.id`, `gen_ai.tool.name`) oraz spany dla agentów i MCP. Konwencje są nadal rozwojowe i zostały przeniesione z głównego repozytorium specyfikacji do osobnego repozytorium `semantic-conventions-genai`, więc nazwy mogą się jeszcze zmieniać (stan na wrzesień 2026). Mimo to warto ich używać zamiast wymyślać własne, bo narzędzia potrafią je rozpoznać.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("acme.support-bot")

def fake_model_call(prompt: str) -> dict:
    """Stand-in for client.messages.create(), so the demo runs offline."""
    return {"text": "429 means rate limited.", "input_tokens": 812, "output_tokens": 37}

with tracer.start_as_current_span("chat claude-opus-5") as span:
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.provider.name", "anthropic")
    span.set_attribute("gen_ai.request.model", "claude-opus-5")
    span.set_attribute("gen_ai.conversation.id", "conv-8123")
    result = fake_model_call("What does HTTP 429 mean?")
    span.set_attribute("gen_ai.response.model", "claude-opus-5")
    span.set_attribute("gen_ai.usage.input_tokens", result["input_tokens"])
    span.set_attribute("gen_ai.usage.output_tokens", result["output_tokens"])
    span.set_attribute("gen_ai.response.finish_reasons", ["end_turn"])

provider.shutdown()
```

Wynik (fragment, `ConsoleSpanExporter` wypisuje pełny obiekt JSON):

```text
{
    "name": "chat claude-opus-5",
    "context": {"trace_id": "0xdeaa135be8...", "span_id": "0x8fe5ac3bf7...", ...},
    "start_time": "2026-09-16T17:47:26.651049Z",
    "end_time": "2026-09-16T17:47:26.651094Z",
    "attributes": {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "claude-opus-5",
        "gen_ai.conversation.id": "conv-8123",
        "gen_ai.usage.input_tokens": 812,
        "gen_ai.usage.output_tokens": 37,
        "gen_ai.response.finish_reasons": ["end_turn"]
    }
}
```

Podmiana `ConsoleSpanExporter` na `OTLPSpanExporter` wysyła dokładnie te same spany do Jaegera, Grafany, Langfuse albo Phoenixa – kod aplikacji się nie zmienia. Zwróć uwagę na nazwę spanu: konwencja mówi, żeby składała się z nazwy operacji i modelu, bo dzięki temu backend potrafi grupować. Atrybuty ustawiasz w dwóch miejscach – część przed wywołaniem (to, co wiesz z żądania), część po (to, co przyszło w odpowiedzi) – i to samo rozbicie zobaczysz w każdej bibliotece instrumentującej.

### Monitorowanie kosztów i latencji

Koszt liczysz z `usage` i cennika, i to jest jedyny wiarygodny sposób – liczenie tokenów po stronie klienta rozjedzie się z rozliczeniem, bo nie uwzględni narzutu narzędzi ani myślenia. Komplikacją jest cache: tokeny zapisu i odczytu mają inne stawki niż zwykłe wejście, a rozdział 3 opisał mnożniki – zapis pięciominutowy kosztuje 1,25 stawki wejściowej, zapis godzinny 2 razy stawkę, odczyt 0,1 stawki. Dla Claude Opus 5 stawka wejściowa to 5 dolarów za milion tokenów, a wyjściowa 25 dolarów; dla Claude Haiku 4.5 odpowiednio 1 i 5 dolarów (stan na wrzesień 2026).

```python
from dataclasses import dataclass

# USD per 1M tokens, Anthropic list prices, checked September 2026.
PRICES = {
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}
CACHE_WRITE_5M = 1.25   # multiplier on the input rate
CACHE_WRITE_1H = 2.00
CACHE_READ = 0.10

@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

def cost_usd(model: str, usage: Usage, cache_ttl: str = "5m") -> float:
    rate = PRICES[model]
    write_mult = CACHE_WRITE_1H if cache_ttl == "1h" else CACHE_WRITE_5M
    tokens = (
        usage.input_tokens * 1.0
        + usage.cache_creation_input_tokens * write_mult
        + usage.cache_read_input_tokens * CACHE_READ
    )
    return (tokens * rate["input"] + usage.output_tokens * rate["output"]) / 1_000_000

cold = Usage(input_tokens=40, output_tokens=300, cache_creation_input_tokens=12_000)
warm = Usage(input_tokens=40, output_tokens=300, cache_read_input_tokens=12_000)
no_cache = Usage(input_tokens=12_040, output_tokens=300)

for label, usage in [("cold", cold), ("warm", warm), ("no cache", no_cache)]:
    print(f"{label:9} {cost_usd('claude-opus-5', usage):.6f} USD")
print(f"1000 warm calls: {1000 * cost_usd('claude-opus-5', warm):.2f} USD")
```

```text
cold      0.082700 USD
warm      0.013700 USD
no cache  0.067700 USD
1000 warm calls: 13.70 USD
```

Liczby pokazują dokładnie to, o czym mówił rozdział 3, i warto się przy nich zatrzymać. Pierwsze wywołanie z cache jest droższe niż wywołanie bez cache, bo płacisz premię za zapis – cache opłaca się dopiero od drugiego trafienia. Za to trafienie kosztuje pięć razy mniej niż wywołanie bez cache. Jeśli w Twoich logach `cache_read_input_tokens` jest stale zerowe, to nie jest kwestia optymalizacji, tylko realny mnożnik rachunku. Ta funkcja powinna działać na produkcji przy każdym wywołaniu, a wynik lądować w logu obok `usage` – inaczej dowiesz się o problemie z faktury.

Latencja ma w aplikacjach LLM dwie różne miary i mylenie ich prowadzi do złych decyzji. TTFT (time to first token) to czas do pierwszego fragmentu odpowiedzi i to on decyduje o odczuwalnej szybkości interfejsu czatu. Czas całkowity to czas do ostatniego tokenu i to on jest istotny przy wywołaniach wsadowych oraz w pętli agenta, gdzie i tak nikt nie czyta strumienia. Model z krótkim TTFT i wolnym generowaniem będzie się wydawał szybki w czacie i będzie wolny w pipelinie.

Obie miary raportuj percentylami, nie średnią. Średnia latencja w systemie z LLM-em jest bezużyteczna, bo rozkład jest silnie prawoskośny: mediana 1,5 sekundy przy p95 równym 25 sekund to normalny obraz, gdy część zapytań uruchamia narzędzia albo dłuższe myślenie. Alerty stawiaj na p95 i p99 oraz na odsetku żądań przekraczających limit czasu. Do tego dochodzą budżety: dzienny limit kosztu per użytkownik i per tenant, twardo egzekwowany w kodzie, plus alert przy odchyleniu dziennego kosztu od średniej z tygodnia. Pojedynczy zapętlony agent potrafi w godzinę wygenerować miesięczny rachunek i to nie jest przypadek hipotetyczny.

### Monitorowanie produkcyjne

Jakość na produkcji dryfuje, nawet gdy nic nie zmieniasz w kodzie. Zmieniają się użytkownicy i ich zapytania, zmieniają się dokumenty w bazie wiedzy, dostawca aktualizuje model pod tym samym aliasem. Dlatego oprócz kosztu i latencji potrzebujesz wskaźników, które są tanim proxy jakości i dają się liczyć z logów bez udziału człowieka.

Cztery działają prawie zawsze. Odsetek odmów, czyli odpowiedzi, w których model odmawia wykonania zadania – nagły skok zwykle oznacza, że ktoś zmienił system prompt albo że do systemu weszła nowa klasa zapytań. Odsetek odpowiedzi „nie wiem" albo z Twoją zdefiniowaną frazą awaryjną (w rozdziale 3 był to `NOT IN DOCS`) – rosnący udział oznacza, że retrieval przestał znajdować dokumenty. Odsetek błędów narzędzi, liczony po `is_error` w blokach `tool_result`, oraz średnia liczba kroków agenta na zadanie. I wreszcie odsetek odpowiedzi uciętych, czyli ze `stop_reason` równym `max_tokens`.

Do tego dochodzi feedback użytkownika. Kciuki w górę i w dół są prymitywne, ale mają dwie zalety: kosztują jedno kliknięcie i dają sygnał skorelowany z rzeczywistym zadowoleniem. Kluczowe jest, żeby zapisywać je z `request_id` z logu, bo wtedy kciuk w dół natychmiast prowadzi do konkretnego promptu, kontekstu i odpowiedzi. Sygnał domyślny jest przy tym mocno stronniczy – ludzie klikają głównie przy złych odpowiedziach – więc traktuj go jako źródło przypadków do naprawy, a nie jako miarę odsetka sukcesu.

Rozróżnienie, które porządkuje resztę, to ewaluacja offline kontra online. Offline uruchamiasz na stałym zbiorze przed wdrożeniem: masz oczekiwane wyniki, powtarzalność i możesz porównywać wersje. Online liczysz na ruchu produkcyjnym, gdzie nie ma oczekiwanych wyników, więc sięgasz po wskaźniki pośrednie, sędziego modelowego na próbce i feedback. Praktyczny wzorzec to próbkowanie: losowy jeden procent ruchu trafia do kolejki przeglądu, w której sędzia modelowy ocenia wszystko, a człowiek przegląda odpowiedzi ocenione nisko oraz te z kciukiem w dół. Przypadki z tej kolejki wracają potem do zbioru offline – i to jest główny mechanizm, dzięki któremu zbiór ewaluacyjny rośnie w sensownym kierunku zamiast starzeć się razem z Twoimi wyobrażeniami o użytkownikach.

### Narzędzia

Budowanie własnego backendu obserwowalności przestaje się opłacać mniej więcej wtedy, gdy chcesz oglądać zagnieżdżone trace'y w przeglądarce. Cztery narzędzia wymienione w roadmapie pokrywają cały zakres podejść – od czystego proxy po platformę z ewaluacjami.

| Narzędzie | Hosting | Open source | Integracja | Ewaluacje wbudowane | Cena wejściowa |
|---|---|---|---|---|---|
| LangSmith | chmura (self-host i hybryda w Enterprise) | nie | SDK (`LANGSMITH_TRACING`, `@traceable`), auto dla LangChain | tak (datasety, `evaluate()`, sędziowie LLM) | Developer 0 USD/miejsce, do 5 tys. trace'ów/mies.; Plus 39 USD/miejsce |
| Langfuse | chmura (EU/US) i self-host | tak | SDK na OpenTelemetry (`@observe`, `get_client()`), OTLP | tak (datasety, eksperymenty, ewaluatory) | Hobby 0 USD, 50 tys. jednostek/mies.; Core 29 USD/mies. |
| Helicone | chmura i on-prem (Enterprise) | tak | proxy (`base_url`), bez zmian w kodzie SDK | ograniczone (głównie analityka i alerty) | Hobby 0 USD, 10 tys. żądań/mies.; Pro 79 USD/mies. |
| Arize Phoenix / AX | Phoenix lokalnie i self-host, AX w chmurze | Phoenix tak, AX nie | OpenTelemetry + OpenInference | tak (`phoenix.evals`, ewaluatory LLM i kodowe) | Phoenix 0 USD; AX Free 25 tys. spanów/mies., AX Pro 50 USD/mies. |

Dane z oficjalnych cenników i dokumentacji sprawdzonych we wrześniu 2026.

LangSmith jest najbardziej zintegrowany z ekosystemem LangChain: jeśli używasz LangChaina lub LangGraph, wystarczy ustawić `LANGSMITH_TRACING=true` i `LANGSMITH_API_KEY`, a trace'y pojawiają się bez żadnej zmiany w kodzie. Poza LangChainem instrumentujesz dekoratorem. To narzędzie zamknięte, rozliczane od liczby trace'ów i miejsc, z self-hostem dostępnym dopiero w planie Enterprise.

Langfuse jest w tej stawce najbardziej neutralny: SDK Pythona w wersji 4 jest zbudowane na OpenTelemetry, więc te same spany wysyłasz do Langfuse albo gdziekolwiek indziej, a self-host na Docker Compose jest darmowy i pełnoprawny. Poza tracingiem dostajesz zarządzanie wersjami promptów, datasety i ewaluacje w tym samym miejscu, co ma znaczenie dla dalszej części tego rozdziału – ten sam przypadek produkcyjny jednym kliknięciem ląduje w zbiorze ewaluacyjnym.

```python
import os
from anthropic import Anthropic
from langfuse import get_client, observe, propagate_attributes

# LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL come from the env.
langfuse = get_client()
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

@observe(name="answer-support-question")
def answer(question: str, user_id: str) -> str:
    with propagate_attributes(user_id=user_id, tags=["support", "support-v7"]):
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="claude-call",
            model="claude-opus-5",
            input=question,
        ) as generation:
            message = client.messages.create(
                model="claude-opus-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": question}],
            )
            text = next(b.text for b in message.content if b.type == "text")
            generation.update(
                output=text,
                usage_details={
                    "input": message.usage.input_tokens,
                    "output": message.usage.output_tokens,
                    "cache_read_input_tokens": message.usage.cache_read_input_tokens,
                },
            )
    return text

print(answer("What does HTTP 429 mean?", "u-1042"))
langfuse.flush()
```

Dekorator `@observe` tworzy span dla całej funkcji, a `start_as_current_observation(as_type="generation", ...)` zagnieżdża w nim span typu „generacja", który w interfejsie Langfuse pokazuje prompt, odpowiedź, model i koszt. `propagate_attributes` przypina identyfikator użytkownika i tagi do całego trace'u, nie tylko do jednego spanu – dzięki temu możesz potem filtrować „pokaż mi wszystkie odpowiedzi na wersji promptu support-v7". `usage_details` to miejsce, w którym przekazujesz liczniki tokenów; Langfuse liczy z nich koszt, o ile zna model. `flush()` wymuś przed zakończeniem krótko żyjącego procesu, bo wysyłka jest asynchroniczna i inaczej stracisz ostatnie spany.

Helicone reprezentuje zupełnie inny wzorzec integracji: proxy. Zamiast instrumentować kod, podmieniasz `base_url` klienta – `Anthropic(base_url="https://anthropic.helicone.ai", default_headers={"Helicone-Auth": f"Bearer {os.environ['HELICONE_API_KEY']}"})` – i wszystkie żądania idą przez bramę, która loguje je po drodze. Zaleta jest oczywista: zero zmian w logice, działa z każdym językiem i każdą biblioteką. Wada też: dokładasz sobie skok sieciowy i punkt awarii na ścieżce krytycznej, nie widzisz kroków, które nie są wywołaniami HTTP do modelu (retrieval, logika), i powierzasz treść promptów pośrednikowi. Proxy jest dobrym wyborem, gdy chcesz mieć koszty i podstawową analitykę w godzinę; instrumentacja SDK jest lepsza, gdy chcesz widzieć cały trace.

Arize Phoenix to open source'owa część oferty Arize AI, zbudowana na OpenTelemetry i instrumentacji OpenInference. Uruchamiasz ją lokalnie jednym poleceniem (`uvx arize-phoenix serve`, interfejs na porcie 6006), więc świetnie nadaje się do pracy na własnej maszynie i do CI. Phoenix ma wbudowane ewaluacje – ewaluatory LLM-owe, kodowe i etykiety ludzkie – i potrafi przyjmować wyniki z RAGAS czy DeepEval. Arize AX to komercyjna, zarządzana wersja tej samej architektury, z monitoringiem produkcyjnym i alertami.

## Ewaluacje

Ewaluacja to pomiar jakości systemu na zbiorze przypadków, powtarzalny na tyle, żeby dało się porównać dwie wersje. Składa się z czterech elementów: zbioru (dataset), przypadków testowych, uruchomienia i metryki. Przypadek testowy ma wejście, oczekiwanie i metadane – przy czym „oczekiwanie" nie zawsze jest oczekiwaną odpowiedzią. Bywa nim etykieta (`category = "outage"`), lista faktów, które muszą się pojawić, kryterium jakościowe („nie wolno podać ścieżki endpointu, której nie ma w kontekście") albo po prostu informacja, że odpowiedź ma być odmową. Metadane – kategoria, trudność, źródło, wersja – decydują potem o tym, czy raport da się czytać: średnia po wszystkim mówi mniej niż rozbicie na kategorie, w którym widać, że spadek dotyczy wyłącznie pytań o webhooki.

Skąd brać przypadki. Najlepsze pochodzą z produkcji: prawdziwe zapytania mają prawdziwy rozkład, w tym te dziwne trzydzieści procent, których byś nie wymyślił. Drugie źródło to przypadki syntetyczne – generujesz je modelem z opisu dziedziny, żeby pokryć klasy, których jeszcze nie widziałeś w ruchu. Trzecie to red team, czyli przypadki celowo wrogie: prompt injection, próby wyciągnięcia system promptu, pytania poza zakresem, wejścia bardzo długie i wejścia puste. Dokumentacja Anthropic formułuje przy tym regułę, która ratuje wiele projektów przed paraliżem: lepsza jest większa liczba przypadków z automatycznym ocenianiem o nieco słabszym sygnale niż garstka ocenianych ręcznie. Sto przypadków z regexem bije dwadzieścia z ludzką oceną, bo sto da się uruchomić przy każdym commicie.

### Ewaluacje deterministyczne

Ewaluacje deterministyczne to takie, w których ocena jest funkcją kodu – ten sam wynik modelu zawsze dostaje tę samą ocenę. Są najtańsze, najszybsze i najbardziej wiarygodne, więc zaczynasz od nich i sięgasz po inne dopiero dla tego, czego nie da się tak zmierzyć.

Cztery rodzaje pokrywają większość potrzeb. Dokładne dopasowanie po normalizacji – dla klasyfikacji, ekstrakcji pól, routingu. Wyrażenia regularne i sprawdzanie obecności lub nieobecności fraz – dla reguł formatu i dla sygnałów awaryjnych w rodzaju `NOT IN DOCS`. Walidacja JSON i schematu – sprawdzasz, czy odpowiedź parsuje się i przechodzi walidację Pydantica; przy structured outputs (rozdział 3) to powinno być stuprocentowe, a każdy spadek jest alarmem. Wreszcie testy wykonania kodu: jeśli model generuje SQL albo Pythona, uruchamiasz wynik w sandboxie i sprawdzasz, czy działa i czy zwraca to, co ma zwrócić – to najsilniejsza możliwa metryka, bo nie ma w niej miejsca na interpretację.

Osobno stoją metryki tekstowe: BLEU i ROUGE porównują wygenerowany tekst z referencyjnym przez pokrycie n-gramów albo najdłuższy wspólny podciąg. Rzadko wystarczają, bo karzą poprawne odpowiedzi sformułowane inaczej niż referencja i nagradzają odpowiedzi podobne powierzchownie, a merytorycznie błędne. Traktuj je jako sygnał pomocniczy przy streszczeniach, nie jako kryterium akceptacji.

Runner nie musi być niczym wymyślnym. Pytest z parametryzacją po przypadkach daje raport, integrację z CI i selekcję pojedynczego przypadku za darmo.

```python
import json
import pytest

CASES = [
    {"id": "outage-1", "input": "All production charges return 500.",
     "expect": {"category": "outage", "min_severity": 4}},
    {"id": "question-1", "input": "Does the sandbox support recurring payments?",
     "expect": {"category": "question", "min_severity": 1}},
    {"id": "bug-1", "input": "Webhook /v1/events fires twice since Tuesday.",
     "expect": {"category": "bug", "min_severity": 2}},
]

def triage(text: str) -> str:
    """Stand-in for the model call; returns raw JSON like the app does."""
    if "500" in text:
        return json.dumps({"category": "outage", "severity": 5})
    if text.strip().endswith("?"):
        return json.dumps({"category": "question", "severity": 1})
    return json.dumps({"category": "bug", "severity": 3})

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_triage(case):
    raw = triage(case["input"])
    parsed = json.loads(raw)                                  # schema check
    assert set(parsed) == {"category", "severity"}
    assert parsed["category"] == case["expect"]["category"]    # exact match
    assert parsed["severity"] >= case["expect"]["min_severity"]
```

```text
ch12/test_triage_eval.py::test_triage[outage-1] PASSED                   [ 33%]
ch12/test_triage_eval.py::test_triage[question-1] PASSED                 [ 66%]
ch12/test_triage_eval.py::test_triage[bug-1] PASSED                      [100%]
============================== 3 passed in 0.01s ===============================
```

Funkcja `triage` jest tu atrapą, żeby przykład dało się uruchomić bez klucza – w prawdziwym projekcie w tym miejscu jest wywołanie `client.messages.parse()`. Parametr `ids` sprawia, że w raporcie widzisz identyfikator przypadku, a nie `case0`, więc regresję zgłaszasz jako „outage-1 padł", a nie „trzeci test padł". Asercje są ułożone od najogólniejszej do najbardziej szczegółowej: najpierw kształt, potem etykieta, potem próg – dzięki temu komunikat błędu od razu mówi, czy zepsuł się format, czy merytoryka. Ten sam plik uruchomisz na jednym przypadku (`pytest -k outage-1`), na całym zbiorze i w CI.

### Ewaluacje modelowe

Ewaluacje modelowe (LLM-as-judge) rozwiązują problem, którego kod nie ruszy: „czy ta odpowiedź jest uprzejma", „czy trzyma się dostarczonego kontekstu", „czy jest lepsza od poprzedniej". Sędzią jest model, któremu dajesz rubrykę i prosisz o ocenę. Dokumentacja Anthropic wyróżnia dwa główne kształty: skalę Likerta (ocena 1–5 dla cech takich jak ton czy trafność) oraz klasyfikację binarną (czy odpowiedź zawiera dane wrażliwe, tak/nie). Binarna jest zauważalnie stabilniejsza, więc gdy pytanie da się postawić jako tak/nie, rób to.

Rubryka musi być zakotwiczona. „Oceń jakość od 1 do 5" da Ci szum; opis, co konkretnie znaczy każdy stopień, da powtarzalność. Drugą regułą jest oddzielenie ról: sędzia powinien być innym modelem niż ten oceniany, bo modele mają mierzalną skłonność do faworyzowania własnych odpowiedzi. Do tego dochodzą znane obciążenia. Bias pozycyjny w porównaniach parami – model częściej wybiera pierwszą albo drugą odpowiedź niezależnie od treści; lekarstwem jest ocenianie każdej pary w obu kolejnościach i uśrednianie. Bias długości – dłuższe odpowiedzi dostają wyższe noty; lekarstwem jest jawne zdanie w rubryce, że długość nie jest zaletą. Wreszcie kalibracja: zanim zaufasz sędziemu, oceń ręcznie pięćdziesiąt przypadków i policz zgodność z nim. Jeśli sędzia zgadza się z Tobą w siedemdziesięciu procentach, jego wyniki nadają się do porównywania wersji, ale nie do raportowania „mamy 4,2 jakości".

```python
import os
from anthropic import Anthropic
from pydantic import BaseModel, Field

RUBRIC = """You grade answers from a support assistant. Judge only groundedness:
whether every factual claim in the answer is supported by <context>.

5 - every claim is supported; missing information is explicitly flagged.
4 - every claim is supported, but the answer adds unsupported hedging.
3 - one minor claim is not supported by the context.
2 - a central claim is not supported by the context.
1 - the answer invents endpoints, parameters or numbers.

Length is not a quality signal. Grade a short correct answer as 5."""

class Judgement(BaseModel):
    score: int = Field(description="Groundedness score from 1 to 5")
    reason: str = Field(description="One sentence, quoting the unsupported claim if any")
    unsupported_claims: list[str]

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def judge(context: str, question: str, answer: str) -> Judgement:
    response = client.messages.parse(
        model="claude-opus-5",
        max_tokens=1024,
        system=RUBRIC,
        messages=[{"role": "user", "content":
                   f"<context>{context}</context>\n"
                   f"<question>{question}</question>\n"
                   f"<answer>{answer}</answer>"}],
        output_format=Judgement,
    )
    return response.parsed_output

verdict = judge(
    context="Production keys start at 100 requests per second.",
    question="What is the rate limit of the charges endpoint?",
    answer="Production keys allow 500 requests per second on /v1/charges.",
)
print(verdict.score, verdict.reason, verdict.unsupported_claims)
```

Structured output robi tu dwie rzeczy naraz. Po pierwsze, `score` jest liczbą całkowitą, a nie tekstem do sparsowania – nie musisz się martwić o „Ocena: 2/5" ani o wiodące spacje. Po drugie, wymuszenie pola `unsupported_claims` zmienia zachowanie sędziego: model musi wskazać konkretne zdanie, więc trudniej mu przyznać niską ocenę „z wyczucia". Uzasadnienie zapisuj razem z wynikiem; przy przeglądzie regresji to ono najszybciej mówi, czy sędzia miał rację. Zwróć też uwagę, że rubryka mówi wprost o długości – to tania szczepionka na najczęstsze obciążenie.

### Ewaluacje ludzkie

Ocena ludzka jest niezbędna w trzech sytuacjach: gdy kalibrujesz sędziego modelowego, gdy stawka błędu jest wysoka (medycyna, prawo, finanse) i gdy oceniane kryterium jest z natury subiektywne – ton marki, jakość tłumaczenia literackiego, użyteczność odpowiedzi. We wszystkich pozostałych przypadkach jest zbyt wolna i zbyt droga, żeby być pętlą rozwojową.

Projekt oceny jest tu ważniejszy niż liczba oceniających. Potrzebujesz rubryki z zakotwiczonymi stopniami i przykładami granicznymi, jednego kryterium na raz (ocenianie „jakości" jako jednej liczby daje rozrzut nie do użycia), losowej kolejności prezentacji i ślepej oceny – oceniający nie może wiedzieć, która odpowiedź pochodzi z nowej wersji. Zgodność między oceniającymi mierz jawnie: część przypadków daj dwóm osobom i policz, jak często się zgadzają. Niska zgodność nie oznacza, że oceniający są słabi, tylko że rubryka jest nieostra – i to ją trzeba poprawić, zanim uznasz wyniki za dane.

Koszt liczy się w minutach: przy trzech minutach na przypadek stuelementowy zbiór to pięć godzin pracy, a więc coś, co robisz raz na kwartał, a nie przy każdym PR-ze. Narzędzia do etykietowania – Label Studio, Argilla, kolejki przeglądu w LangSmith, Langfuse i Phoenix – skracają to o tyle, o ile dają prezentację kontekstu obok odpowiedzi i skróty klawiszowe. Praktyczny wzorzec jest taki: człowiek ocenia próbkę, ocena człowieka kalibruje sędziego, sędzia ocenia całą resztę, a człowiek wraca tylko do przypadków spornych.

### Metryki

Metryka bierze się z zadania, nie z listy popularnych wskaźników. Poniższa tabela porządkuje te, które realnie się liczą, według typu systemu.

| Zadanie | Metryki | Uwaga |
|---|---|---|
| Klasyfikacja, routing, ekstrakcja | accuracy, precision, recall, F1, macierz pomyłek | przy niezrównoważonych klasach accuracy kłamie; patrz na F1 per klasa |
| Retrieval (rozdziały 7 i 8) | recall@k, precision@k, MRR, nDCG | recall@k jest sufitem jakości całego RAG-u |
| RAG (odpowiedź) | faithfulness, answer relevancy, context precision, context recall | rozdzielają winę: retrieval czy generacja |
| Agenci (rozdział 9) | task success rate, liczba kroków, liczba wywołań narzędzi, odsetek błędów narzędzi, koszt na zadanie | koszt na ukończone zadanie, nie na żądanie |
| Bezpieczeństwo (rozdział 11) | attack success rate, odsetek fałszywych odmów | mierz oba naraz, inaczej „bezpieczny" znaczy „bezużyteczny" |
| Operacje | TTFT p50/p95, czas całkowity p95, koszt na żądanie, odsetek `max_tokens` | percentyle, nigdy średnia |

Dwie uwagi praktyczne. Metryki RAG-owe są cenne głównie dlatego, że rozdzielają odpowiedzialność: niska context recall oznacza, że retrieval nie dostarczył potrzebnego fragmentu, a niska faithfulness przy dobrym kontekście – że generacja zmyśla mimo poprawnych danych. To dwie zupełnie różne naprawy. I drugie: dla agentów jedyną uczciwą miarą kosztu jest koszt na ukończone zadanie. Tańszy model, który potrzebuje trzech prób, nie jest tańszy.

### Narzędzia: DeepEval i RAGAS

DeepEval jest frameworkiem ewaluacyjnym zbudowanym wokół pytesta. Przypadek opisuje klasa `LLMTestCase`, metryki liczą sędziowie modelowi, a `assert_test` zamienia ocenę w asercję. Najciekawszą metryką jest `GEval` – definiujesz kryterium w jednym zdaniu, a framework sam rozpisuje je na kroki oceny i zwraca wynik 0–1 z progiem.

```python
import os
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

judge_model = AnthropicModel(model="claude-opus-5", api_key=os.environ["ANTHROPIC_API_KEY"])

groundedness = GEval(
    name="Groundedness",
    criteria=("The actual output must only state facts present in the retrieval "
              "context, and must say it does not know when the context is silent."),
    evaluation_params=[SingleTurnParams.INPUT,
                       SingleTurnParams.ACTUAL_OUTPUT,
                       SingleTurnParams.RETRIEVAL_CONTEXT],
    model=judge_model,
    threshold=0.7,
)

def test_rate_limit_answer():
    case = LLMTestCase(
        input="What is the rate limit of the charges endpoint?",
        actual_output="Production keys allow 500 requests per second on /v1/charges.",
        retrieval_context=["Production keys start at 100 requests per second."],
    )
    assert_test(case, [groundedness])
```

Plik uruchamiasz poleceniem `deepeval test run test_support.py`, które pod spodem jest pytestem z dodatkowym raportem. Zwróć uwagę na `evaluation_params`: wskazujesz, które pola przypadku sędzia w ogóle widzi, i to jest istotne – gdybyś nie podał `RETRIEVAL_CONTEXT`, metryka oceniałaby wiarygodność odpowiedzi na podstawie wiedzy własnej modelu, a nie dostarczonych dokumentów. `AnthropicModel` pozwala ustawić sędziego na Claude; domyślnie DeepEval sięga po OpenAI i klucz z `OPENAI_API_KEY`. Wersja 4.2 używa wyliczenia `SingleTurnParams` – w starszych wydaniach to samo nazywało się `LLMTestCaseParams` (stan na wrzesień 2026).

RAGAS jest węższy i celuje wprost w RAG. Dostarcza gotowe implementacje metryk, o których była mowa w tabeli, a Ty dajesz zbiór z czterema polami: `user_input`, `retrieved_contexts`, `response` i opcjonalnie `reference`.

```python
import os
from anthropic import Anthropic
from ragas import EvaluationDataset, evaluate
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference

evaluator_llm = llm_factory(
    "claude-opus-5",
    provider="anthropic",
    client=Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
)

dataset = EvaluationDataset.from_list([
    {
        "user_input": "What is the rate limit of the charges endpoint?",
        "retrieved_contexts": ["Production keys start at 100 requests per second.",
                               "Sandbox keys allow 10 requests per second."],
        "response": "Production keys start at 100 requests per second.",
        "reference": "100 requests per second for production keys.",
    },
])

result = evaluate(
    dataset=dataset,
    metrics=[Faithfulness(llm=evaluator_llm),
             LLMContextPrecisionWithReference(llm=evaluator_llm)],
)
print(result)
print(result.to_pandas())
```

`llm_factory` z argumentem `provider="anthropic"` i gotowym klientem to aktualny sposób podpięcia sędziego; starszy `LangchainLLMWrapper` jest wycofywany. Metryki wybieraj świadomie: `Faithfulness` i `LLMContextPrecisionWithReference` potrzebują tylko modelu, natomiast `ResponseRelevancy` wymaga dodatkowo modelu embeddingów, bo porównuje pytanie z pytaniami odtworzonymi z odpowiedzi. `result.to_pandas()` daje ramkę z wynikiem per przypadek – i to jej używaj, a nie średniej, bo dopiero widok pojedynczych wierszy pokazuje, że jeden przypadek z pustym kontekstem ciągnie całą metrykę w dół. W wersji 0.4 trwa migracja metryk do `ragas.metrics.collections`; te nowe klasy ocenia się per przypadek metodą `ascore()` i nie działają jeszcze z `evaluate()`.

Kiedy własny runner, a kiedy framework? Własny pytest wystarcza, gdy Twoje oceny są deterministyczne albo masz jednego prostego sędziego – wtedy framework dokłada zależności i warstwę abstrakcji, nie dokładając niczego, czego nie masz. Framework wygrywa, gdy potrzebujesz kilkunastu gotowych metryk (RAG, agenci), gdy chcesz raportów i śledzenia wyników między uruchomieniami albo gdy zespół ma korzystać z ewaluacji bez pisania kodu. Osobną kategorią jest promptfoo – narzędzie CLI, w którym przypadki i asercje opisujesz w pliku `promptfooconfig.yaml`, uruchamiasz komendą `promptfoo eval` i wpinasz w GitHub Actions. Jest bezstanowe i językowo neutralne, więc dobrze pasuje do porównywania wariantów promptu i modeli, a osobny tryb red teamingu generuje ataki na podstawie opisu aplikacji.

## Testy regresyjne

Ewaluacja uruchomiona raz jest ciekawostką. Ewaluacja uruchamiana przy każdej zmianie promptu, modelu, parametru `effort` albo pipeline'u retrievalu jest testem regresyjnym – i dopiero wtedy zaczyna chronić. Mechanika jest prosta: zapisujesz wynik wzorcowy (baseline), a każde uruchomienie porównujesz z nim i przerywasz build, gdy spadek przekracza tolerancję.

Największą różnicą wobec zwykłych testów jest niedeterminizm. Ten sam przypadek potrafi raz przejść, raz nie, i nie dlatego, że coś zepsułeś. Trzy rzeczy tłumią ten szum. Po pierwsze, powtórzenia: uruchamiaj każdy przypadek trzy albo pięć razy i bierz medianę lub odsetek sukcesów, a nie pojedynczy wynik. Po drugie, stałe ustawienia: `effort` ustawiony jawnie, ten sam identyfikator modelu (nie alias, który dostawca może przestawić), to samo `max_tokens`, ten sam zbiór dokumentów w retrievalu. Po trzecie, tolerancja zamiast twardej równości – bramka „accuracy nie spadło o więcej niż 0,02" jest sensowna, bramka „accuracy jest dokładnie takie samo" będzie migać bez końca.

Drugą różnicą jest koszt. Pełny zbiór z sędzią modelowym to realne pieniądze i realne minuty przy każdym PR-ze, więc rozdziel uruchomienia. W PR-ze puszczasz podzbiór: wszystkie ewaluacje deterministyczne (są darmowe) plus sędziego na kilkudziesięciu przypadkach dobranych tak, by pokryć każdą kategorię. Pełny zbiór, wszystkie powtórzenia i wszystkie metryki uruchamiasz nocą i przed wydaniem. Wyniki nocne trzymaj w historii, bo wykres metryki w czasie wykrywa powolny dryf, którego porównanie z jednym baseline'em nie złapie.

Wersjonowanie dotyczy trzech rzeczy naraz. Prompty trzymasz w repo z identyfikatorem wersji, który ląduje w logu (to ten `prompt_version` z pierwszego snippetu). Zbiory ewaluacyjne też są w repo albo w narzędziu z wersjonowaniem – zmiana zbioru zmienia znaczenie metryki, więc porównywanie wyników z różnych wersji zbioru jest bezsensowne i trzeba to jawnie blokować. Baseline zawiera obie informacje: wersję promptu i liczbę przypadków. Każdy naprawiony błąd produkcyjny dopisujesz jako nowy przypadek – incydent, który nie zostawił po sobie testu, wróci. Ta sama zasada dotyczy red teamu: udany atak z rozdziału 11 staje się przypadkiem regresyjnym, a jego metryką jest attack success rate.

```python
import json
import sys

# metric -> (direction, max tolerated regression)
GATES = {
    "accuracy": ("higher_is_better", 0.02),
    "json_valid": ("higher_is_better", 0.00),
    "refusal_rate": ("lower_is_better", 0.02),
}

baseline = json.load(open(sys.argv[1]))["metrics"]
current = json.load(open(sys.argv[2]))["metrics"]

failures = []
for name, (direction, tolerance) in GATES.items():
    before, after = baseline[name], current[name]
    delta = after - before if direction == "higher_is_better" else before - after
    status = "ok" if delta >= -tolerance else "REGRESSION"
    print(f"{name:14} {before:6.3f} -> {after:6.3f}  ({delta:+.3f})  {status}")
    if status == "REGRESSION":
        failures.append(f"{name}: {before:.3f} -> {after:.3f}, tolerance {tolerance}")

if failures:
    print("\nquality gate failed:", *failures, sep="\n  ")
    sys.exit(1)
print("\nquality gate passed")
```

Przy `baseline.json` z `accuracy` 0,91 i `refusal_rate` 0,02 oraz wyniku bieżącym 0,88 i 0,05 skrypt wypisuje:

```text
accuracy        0.910 ->  0.880  (-0.030)  REGRESSION
json_valid      1.000 ->  1.000  (+0.000)  ok
refusal_rate    0.020 ->  0.050  (-0.030)  REGRESSION

quality gate failed:
  accuracy: 0.910 -> 0.880, tolerance 0.02
  refusal_rate: 0.020 -> 0.050, tolerance 0.02

exit code: 1
```

Trzy szczegóły decydują o użyteczności tej bramki. Kierunek metryki jest zadeklarowany jawnie, bo dla `refusal_rate` spadkiem jakości jest wzrost wartości – pomylenie tego jest najczęstszym błędem w takich skryptach. Tolerancje są różne dla różnych metryk: dla `json_valid` wynosi zero, bo przy structured outputs każdy nieprawidłowy JSON to defekt, a nie szum. I wreszcie skrypt wypisuje wszystkie metryki, także te, które przeszły, zanim zakończy się kodem 1 – dzięki temu z loga CI odczytujesz pełny obraz zmiany, a nie tylko pierwszą rzecz, która się zepsuła. Podniesienie baseline'u jest świadomą decyzją: gdy zmiana faktycznie poprawia jakość, zapisujesz nowy `baseline.json` w tym samym commicie co zmianę promptu i masz w historii gita dokładny zapis, co i o ile poprawiło.

## Podsumowanie

- Obserwowalność i ewaluacja są częścią definicji „done" dla funkcji opartej na modelu: log z `usage` i wersją promptu, zbiór ewaluacyjny z progiem, bramka w CI.
- Trace to operacja biznesowa, span to krok; w aplikacji LLM interesujące spany to retrieval, wywołanie modelu i wywołanie narzędzia, a najcenniejsze atrybuty to `usage`, wersja promptu i `stop_reason`.
- Loguj treść promptów tylko świadomie, z maskowaniem i krótką retencją; log z wywołań modelu jest zbiorem danych osobowych (rozdział 11).
- OpenTelemetry z konwencjami GenAI (`gen_ai.*`) pozwala wysyłać te same spany do dowolnego backendu; konwencje są jeszcze rozwojowe, ale lepsze niż własne nazwy.
- Koszt licz z `usage` i mnożników cache; pierwsze wywołanie z cache jest droższe niż bez cache, a zerowe `cache_read_input_tokens` to realny mnożnik rachunku.
- Latencję raportuj jako TTFT i czas całkowity, zawsze w percentylach; średnia w systemie z LLM-em nie niesie informacji.
- Na produkcji monitoruj dryf tanimi wskaźnikami: odsetek odmów, „nie wiem", błędów narzędzi i odpowiedzi uciętych, plus feedback użytkownika powiązany z `request_id`.
- Zaczynaj od ewaluacji deterministycznych (dopasowanie, regex, schemat, wykonanie kodu), bo są darmowe i powtarzalne; sędziego modelowego dokładaj tylko tam, gdzie kod nie sięga.
- Sędzia LLM potrzebuje zakotwiczonej rubryki, innego modelu niż oceniany, ochrony przed biasem pozycji i długości oraz kalibracji na próbce ocenionej przez człowieka.
- Ewaluacje jako testy regresyjne: powtórzenia i mediana przeciw niedeterminizmowi, próbka w PR-ze i pełny zbiór nocą, tolerancja zamiast równości, baseline wersjonowany razem z promptem.

## Co dalej

Rozdział 13 („Multimodalność") wychodzi poza tekst: obrazy, dokumenty i dźwięk jako bloki treści w tym samym wywołaniu API, które znasz z poprzednich rozdziałów. Zanim tam przejdziesz, zrób dwie rzeczy samodzielnie. Po pierwsze, dopisz do jednego ze swoich skryptów wrapper z pierwszego snippetu i po dniu działania policz z pliku JSONL trzy liczby: koszt dzienny, medianę i p95 latencji oraz odsetek odpowiedzi ze `stop_reason` równym `max_tokens`. Po drugie, wybierz dwadzieścia prawdziwych zapytań z tego logu, dopisz do każdego oczekiwanie i zamknij je w pliku pytesta z ostatniego snippetu. To dwadzieścia przypadków będzie pierwszym baseline'em – i pierwszym momentem, w którym zmiana promptu przestanie być zgadywaniem.

## Źródła

- https://platform.claude.com/docs/en/test-and-evaluate/define-success
- https://platform.claude.com/docs/en/test-and-evaluate/develop-tests
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/about-claude/pricing
- https://opentelemetry.io/docs/specs/semconv/gen-ai/
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- https://github.com/open-telemetry/semantic-conventions-genai
- https://langfuse.com/docs/observability/sdk/python/overview
- https://langfuse.com/docs/observability/sdk/python/instrumentation
- https://langfuse.com/pricing
- https://docs.langchain.com/langsmith
- https://www.langchain.com/pricing-langsmith
- https://docs.helicone.ai/getting-started/quick-start
- https://docs.helicone.ai/integrations/anthropic/python
- https://www.helicone.ai/pricing
- https://arize.com/docs/phoenix
- https://arize.com/pricing/
- https://deepeval.com/docs/getting-started
- https://docs.ragas.io/en/stable/getstarted/rag_eval/
- https://www.promptfoo.dev/docs/intro/
