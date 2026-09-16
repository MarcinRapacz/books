# Rozdział 5. Modele, platformy i API

> **Z roadmapy:** Type of Models, Pre-trained Models, Closed vs Open Source Models, Self-Hosted Models, Choosing the Right Model, Anthropic Claude, Google Gemini, OpenAI (GPT, o-series), Cohere, Mistral, Meta Llama, DeepSeek, Qwen, Gemma, Hugging Face, Hugging Face Tasks, Hugging Face Hub, Transformers.js, Ollama, LM Studio, OpenRouter, OpenAI Response API, Claude Messages API, Google Gemini APi, Hugging Face Inference SDK, OpenAI-compatible APIs, Fine-tuning
>
> **Pakiety:** `pip install anthropic openai google-genai transformers torch huggingface_hub ollama`

Wybór modelu wygląda na decyzję o jakości, a jest decyzją o czterech rzeczach naraz: koszcie za tysiąc wywołań, opóźnieniu do pierwszego tokenu, jakości na Twoim zadaniu i ryzyku, że dostawca zmieni Ci grunt pod nogami. Te cztery osie prawie nigdy nie wskazują tego samego modelu. Model, który najlepiej pisze kod, jest najdroższy i najwolniejszy; model, który klasyfikuje zgłoszenia za ułamek centa, nie poradzi sobie z analizą umowy. Dlatego dojrzała aplikacja na LLM-ach prawie nigdy nie używa jednego modelu – używa kilku i świadomie rozdziela między nie ruch.

Ryzyko dostawcy jest osią, którą najłatwiej przeoczyć, a najtrudniej naprawić po fakcie. Model zamknięty żyje na cudzym serwerze: może zostać wycofany z terminem trzech miesięcy, może zmienić zachowanie po cichej aktualizacji, może przestać być dostępny w Twoim regionie, może podrożeć. Model otwarty, którego wagi masz na dysku, nie zmieni się nigdy – ale wtedy to Ty odpowiadasz za GPU, aktualizacje, przepustowość i za to, że w nocy nikt nie odbierze telefonu. To nie jest wybór między „lepszym" a „gorszym", tylko między dwoma różnymi rozkładami ryzyka.

## Rodzaje modeli

Zacznij od rozróżnienia, które porządkuje resztę: model bazowy (pre-trained, base) kontra model instrukcyjny (instruction-tuned, instruct). Model bazowy powstaje z jednego zadania – przewidywania następnego tokenu na ogromnym korpusie tekstu. Nic więcej nie umie i nic więcej nie „chce". Jeśli dasz mu prompt „Napisz funkcję sortującą", może kontynuować go jako „…w Pythonie. Napisz funkcję odwracającą listę. Napisz funkcję…", bo statystycznie tak wyglądają listy zadań w korpusie. Model bazowy nie odpowiada na pytania, tylko kontynuuje tekst.

Model instrukcyjny to ten sam model bazowy po dodatkowym treningu na parach instrukcja–odpowiedź i po dostrojeniu do preferencji ludzi. Dopiero on zachowuje się jak asystent: ma format rozmowy z rolami, kończy odpowiedź zamiast ciągnąć w nieskończoność, odmawia rzeczy, których odmawiać ma. Wszystko, co robisz przez API dostawców, to modele instrukcyjne. Na Hugging Face różnicę widać wprost w nazwie repozytorium – wariant z przyrostkiem `-Instruct` albo `-it` to wersja dostrojona, a ta bez przyrostka to baza. Jeśli pobierzesz bazę i zdziwisz się, że „nie słucha", to nie jest awaria, tylko wybór złego wariantu.

„Pre-trained model" w praktyce znaczy coś prostszego, niż sugeruje nazwa: bierzesz wagi, których ktoś inny nie wytrenował za Ciebie za kilkadziesiąt milionów dolarów, i używasz ich jako gotowego komponentu. Cała inżynieria na LLM-ach stoi na tym założeniu. Nie trenujesz modelu – wybierasz go, promptujesz, obudowujesz danymi i narzędziami, ewentualnie dostrajasz na małym zbiorze. Trening od zera nie jest opcją dla zespołu produktowego i nie będzie nią w przewidywalnej przyszłości.

Trzeci typ to modele rozumujące (reasoning models). Generują przed odpowiedzią wewnętrzny ciąg rozumowania i dopiero potem właściwą treść, a długość tego ciągu jest sterowalna – w Claude przez `output_config={"effort": ...}`, w modelach OpenAI przez `reasoning.effort`, w Gemini przez `generation_config={"thinking_level": ...}`. Płacisz za tokeny rozumowania jak za wyjściowe, więc pokrętło jest wprost pokrętłem kosztu i opóźnienia. Opłaca się tam, gdzie zadanie ma wiele kroków i pomyłka w kroku trzecim psuje wszystko dalej: planowanie, analiza kodu, matematyka, debugowanie. Na klasyfikacji krótkiego tekstu tylko przepala budżet.

Czwarta kategoria to małe modele – od kilkuset milionów do kilkunastu miliardów parametrów. Ich sens nie jest taki, że są „prawie tak dobre", bo nie są. Sens jest taki, że mieszczą się na jednym GPU albo na laptopie, odpowiadają w kilkadziesiąt milisekund i kosztują tyle, co nic, a wiele realnych zadań – klasyfikacja intencji, ekstrakcja pól z faktury, routing zgłoszenia – nie wymaga modelu flagowego. Są też jedyną opcją tam, gdzie dane nie mogą opuścić maszyny.

Piąta kategoria to modele wyspecjalizowane, których nie używa się do rozmowy. Modele embeddingowe zamieniają tekst na wektor i są podstawą wyszukiwania semantycznego (rozdział 6). Rerankery przyjmują parę zapytanie–dokument i zwracają jedną liczbę: jak dobrze pasują; w RAG-u poprawiają trafność bardziej niż wymiana modelu generującego (rozdział 8). Osobno są modele multimodalne (rozdział 13) oraz moderacyjne (rozdział 11). Dobierając stos, dobierasz zwykle trzy modele naraz: generujący, embeddingowy i reranker – i każdy ocenia się osobno.

## Zamknięte czy otwarte

Pierwsza rzecz do uporządkowania to słownictwo, bo „open source" w świecie modeli jest używane niedbale. Prawie wszystko, co pobierasz z Hugging Face, to open weights: dostajesz plik z wagami i licencję na ich używanie, ale nie dostajesz danych treningowych ani kodu, którym je wytrenowano. Open source w klasycznym rozumieniu wymagałoby jednego i drugiego, a do tego licencji bez ograniczeń co do pola zastosowania. Różnica nie jest akademicka: bez danych treningowych nie odtworzysz modelu, nie zbadasz, skąd bierze się jego zachowanie, i nie usuniesz z niego czegoś, czego nie chcesz. Możesz go tylko uruchomić i dostroić.

Druga rzecz to licencja, którą trzeba przeczytać, a nie założyć. Część modeli otwartych wychodzi na Apache 2.0 albo MIT i wtedy naprawdę możesz z nimi robić, co chcesz. Część wychodzi na licencjach własnych dostawcy, które dopuszczają użycie komercyjne, ale nakładają warunki: obowiązek oznaczania produktu, zakaz trenowania konkurencyjnych modeli na wyjściach, próg liczby użytkowników, powyżej którego trzeba osobnej zgody, albo politykę dopuszczalnego użycia wpisaną do licencji. Dla działu prawnego to różnica między „bierzemy" a „nie bierzemy", więc sprawdź plik `LICENSE` w repozytorium modelu, zanim zbudujesz na nim produkt.

Trzecia rzecz to model kosztowy, bo obie opcje liczą pieniądze inaczej. Za API płacisz za token i koszt rośnie liniowo z ruchem; przy zerowym ruchu płacisz zero. Za self-hosting płacisz za godzinę GPU niezależnie od tego, czy ktoś z aplikacji korzysta. Stąd prosty próg opłacalności: self-hosting ma sens przy dużym, stałym i przewidywalnym ruchu, a przy ruchu nierównym albo małym prawie zawsze przegrywa. Do rachunku doliczasz przy tym redundancję (jedna karta to jeden punkt awarii), inżyniera utrzymującego serwer inferencyjny i czas potrzebny na dogonienie wydajności, którą dostawcy mają z pudełka.

Czwarta rzecz to prywatność i kontrola wersji, i tu self-hosting wygrywa bezdyskusyjnie. Wagi na Twoim sprzęcie oznaczają, że dane nie opuszczają Twojej sieci – co bywa nie preferencją, tylko wymogiem umownym albo regulacyjnym. Oznaczają też, że model, który dziś przechodzi Twoje testy, będzie przechodził je za rok, bo plik z wagami się nie zmienia. Modele zamknięte mają cykl życia: pojawiają się, dostają następców, dostają datę wycofania. Aplikacja zbudowana na API musi mieć w planie migrację między wersjami modelu i zestaw ewaluacji, który powie, czy nowa wersja niczego nie zepsuła (rozdział 12).

W praktyce większość zespołów miesza oba światy. Model zamknięty obsługuje zadania trudne i rzadkie, mały model otwarty – częste i proste, a ten drugi bywa jednocześnie planem awaryjnym na wypadek awarii albo podwyżki u dostawcy. Warunkiem sensowności tego podejścia jest warstwa abstrakcji nad wywołaniem modelu i zestaw ewaluacji – bez nich „przełączenie na inny model" jest życzeniem, a nie operacją.

## Modele zamknięte

Pięciu dostawców, których spotkasz najczęściej, wypełnia różne nisze. Poniższa tabela zestawia flagowce – model, po który sięgasz, gdy nie wiesz jeszcze, czego potrzebujesz. Ceny są za milion tokenów, dla zwykłego, niewsadowego ruchu, bez rabatów za cache (stan na wrzesień 2026).

| Dostawca | Flagowy model | Okno kontekstu / max wyjście | Cena wejście / wyjście (USD za 1M) | Mocne strony wg dokumentacji |
|---|---|---|---|---|
| Anthropic | `claude-opus-5` | 1 000 000 / 128 000 | 5 / 25 | złożone kodowanie agentowe i zastosowania firmowe |
| OpenAI | `gpt-6-astra` | 1 050 000 / 128 000 | 10 / 50 | złożone rozumowanie, kodowanie, computer use, praca z dokumentami |
| Google | `gemini-3.1-pro-preview` | 1 048 576 / 65 536 | 2–4 / 12–18 | multimodalne wejście: tekst, obraz, wideo, audio, PDF |
| Cohere | `command-a-plus-05-2026` | 128 000 / 64 000 | brak publicznego cennika per token | RAG, tool use, 48 języków, wagi na Apache 2.0 |
| Mistral | `mistral-medium-3-5` | 256 000 / brak danych | 1,5 / 7,5 | otwarte wagi, zastosowania agentowe i kodowanie |

Anthropic prowadzi cztery modele naraz i dokumentacja sama podpowiada, od którego zacząć: `claude-opus-5` do większości zadań, `claude-fable-5-1` (10 i 50 dolarów) do wymagającego rozumowania i długich zadań agentowych, `claude-sonnet-5` jako kompromis (2 i 10), a `claude-haiku-4-5` jako najszybszy i najtańszy (1 i 5, 200 tysięcy tokenów kontekstu). Dwie rzeczy z cennika zmieniają rachunki: Batch API obcina cenę o połowę, a odczyt z cache kosztuje jedną dziesiątą stawki wejściowej. Trzecia jest pułapką przy migracji – modele od wersji 4.7 wzwyż używają nowego tokenizera, który z tego samego tekstu robi około 30 procent więcej tokenów.

OpenAI ma najszerszy rozstrzał cenowy w obrębie jednej generacji. Flagowy `gpt-6-astra` kosztuje 10 i 50 dolarów, a `gpt-5.6-luna` z tym samym oknem kontekstu – 0,20 i 1,20 dolara, czyli pięćdziesiąt razy mniej na wejściu. Między nimi są `gpt-5.6-terra` (2 i 12) oraz `gpt-5.6-sol` (4 i 20), a cache daje 90 procent zniżki na wejściu. Taki rozstrzał to zaproszenie do routingu: różnica jakości w obrębie jednej rodziny jest zwykle mniejsza niż różnica ceny. Roadmapa wymienia jeszcze „o-series" (o1, o3): to była osobna linia modeli rozumujących z lat 2024–2025, którą OpenAI wchłonęło do głównej linii GPT, gdy rozumowanie stało się standardową cechą flagowców; w aktualnej dokumentacji i cenniku nie występuje już jako oddzielna rodzina.

Google Gemini wyróżnia się wejściem multimodalnym i cenami zależnymi od długości promptu. `gemini-3.1-pro-preview` kosztuje 2 dolary za milion tokenów wejściowych przy promptach do 200 tysięcy tokenów i 4 dolary powyżej tego progu; wyjście odpowiednio 12 i 18 dolarów. Model przyjmuje tekst, obrazy, wideo, audio i PDF-y w jednym wywołaniu, co robi z niego domyślny wybór, gdy dane wejściowe nie są tekstem. W linii Flash `gemini-3.8-flash` jest opisany jako najinteligentniejszy model Flash, przeznaczony do długotrwałych zadań inżynierskich (0,75–1,50 i 3,75–7,50), a `gemini-3.5-flash-lite` to wariant najtańszy (0,30 i 2,50).

Cohere traktuje wyszukiwanie jako produkt pierwszej klasy. Poza rodziną Command ma własne embeddingi (`embed-v4.0`, kontekst 128 tysięcy tokenów, wymiary do wyboru: 256, 512, 1024 albo 1536) oraz rerankery (`rerank-v4.0-pro` i `rerank-v4.0-fast`, kontekst 32 tysięcy tokenów). Flagowy `command-a-plus-05-2026` to Mixture of Experts o 218 miliardach parametrów, z 25 miliardami aktywnymi na token, obsługujący 48 języków – i jednocześnie wydany na Hugging Face na licencji Apache 2.0, co jest rzadkim przypadkiem modelu z górnej półki dostępnego i przez API, i do pobrania. Cennik per token dla bieżących modeli nie jest publikowany; na stronie cen są wyłącznie modele wycofywane i instancje dedykowane rozliczane godzinowo.

Mistral jest dostawcą europejskim i wypuszcza dużą część oferty na otwartych licencjach. `mistral-large-2512` (Mixture of Experts, 675 miliardów parametrów, 41 miliardów aktywnych) jest na Apache 2.0 i kosztuje 0,50 oraz 1,50 dolara za milion tokenów; `mistral-small-2603` na tej samej licencji – 0,15 i 0,60; flagowy `mistral-medium-3-5` na zmodyfikowanej licencji MIT – 1,50 i 7,50. Wszystkie trzy mają 256 tysięcy tokenów kontekstu. Zamknięte pozostają modele wyspecjalizowane: Codestral do kodu, Mistral Embed, OCR, Voxtral do mowy. Jeśli szukasz dostawcy, u którego ta sama rodzina jest dostępna i przez API, i do postawienia u siebie, to najbardziej spójna oferta na rynku.

## Modele otwarte

Cztery rodziny dominują w świecie otwartych wag. Poniższa tabela pokazuje aktualne generacje; wszystkie pozycje pobierzesz z Hugging Face, a różnice licencyjne między nimi są większe niż różnice techniczne (stan na wrzesień 2026).

| Rodzina | Aktualna generacja | Rozmiary | Licencja | Kontekst | Repozytorium |
|---|---|---|---|---|---|
| Meta Llama | Llama 4 | Scout 109B (17B aktywnych), Maverick 400B (17B aktywnych) | Llama 4 Community License Agreement | 10M (Scout), 1M (Maverick) | `huggingface.co/meta-llama` |
| DeepSeek | DeepSeek V4.1 / V4 Pro | V4.1-Flash 552B (8–16B aktywnych), V4-Pro 1,7T | MIT | 1M | `huggingface.co/deepseek-ai` |
| Qwen | Qwen3.8 | 27B (dense), Flash-Next 125B (6B aktywnych) | Apache 2.0 (27B), Qwen Community License 1.0 (Flash-Next) | 262 144, rozszerzalny do 1M | `huggingface.co/Qwen` |
| Gemma | Gemma 4 | E2B, E4B, 12B, 26B A4B (3,8B aktywnych), 31B | Apache 2.0 | 128K (E2B, E4B), 256K (pozostałe) | `huggingface.co/google` |

Llama 4 to modele Mixture of Experts z natywną multimodalnością. Scout ma 109 miliardów parametrów łącznie przy 17 miliardach aktywnych na token i okno kontekstu 10 milionów tokenów – największe w tym zestawieniu. Maverick ma 400 miliardów łącznie, te same 17 miliardów aktywnych i milion tokenów kontekstu. Haczyk jest licencyjny: Llama 4 Community License Agreement to własna licencja Meta, nie zatwierdzona przez OSI, z warunkami dotyczącymi oznaczania produktu i progu skali. Jeśli budujesz produkt komercyjny, ten plik musi przeczytać prawnik, a nie inżynier.

DeepSeek jest w tym zestawieniu najbardziej liberalny prawnie: wagi wychodzą na licencji MIT, bez warunków poza zachowaniem noty o prawach autorskich. `DeepSeek-V4.1-Flash` ma 552 miliardy parametrów w szkielecie, ale aktywuje tylko 8 miliardów przy przetwarzaniu promptu i 16 przy generowaniu, ma milion tokenów kontekstu i sterowalny wysiłek rozumowania w skali od 1 do 100. DeepSeek prowadzi też własne API z cenami zależnymi od pory dnia – poza godzinami szczytu stawki są o połowę niższe.

Qwen jest rodziną najwygodniejszą do self-hostingu, bo ma warianty mieszczące się na pojedynczej karcie. `Qwen3.8-27B` to model gęsty z enkoderem wizyjnym, 262 tysiące tokenów kontekstu natywnie i rozszerzalny do miliona, na licencji Apache 2.0. `Qwen3.8-Flash-Next` to MoE ze 125 miliardami parametrów i zaledwie 6 miliardami aktywnych, ale wychodzi na Qwen Community License 1.0 – w obrębie jednej rodziny licencje się różnią, więc sprawdzaj je per repozytorium, nie per marka.

Gemma 4 to otwarta rodzina Google i jedyna w tym zestawieniu, gdzie wszystkie warianty są na Apache 2.0 – wcześniejsze generacje wychodziły na własnym dokumencie „Gemma Terms of Use", więc jeśli pamiętasz Gemmę jako licencyjnie kłopotliwą, ta ocena jest już nieaktualna. Rodzina jest zaprojektowana pod urządzenia: E2B ma 2,3 miliarda parametrów efektywnych, E4B – 4,5 miliarda, oba z oknem 128 tysięcy tokenów; wyżej są 12B, 26B A4B (3,8 miliarda aktywnych) i gęsty 31B z oknem 256 tysięcy. Do tego warianty wyspecjalizowane: MedGemma, ShieldGemma 2 do moderacji, T5Gemma.

## Jak wybrać model

Wybór modelu bez zestawu testowego jest wróżeniem. Rankingi publiczne mówią, jak modele radzą sobie na zadaniach, których nie masz; Twoje zadanie jest inne, Twoje dane są inne i Twoje kryterium poprawności jest inne. Procedura, która działa, ma cztery kroki: zbierz dwadzieścia do pięćdziesięciu realnych przypadków z produkcji, zapisz dla każdego oczekiwany wynik, uruchom na nich dwa–trzy modele i porównaj liczby, nie wrażenia. Jak zbudować taki zestaw i czym mierzyć jakość, opisuje rozdział 12; tutaj wystarczy zasada, że decyzja o modelu jest decyzją opartą na pomiarze.

Taktyka, która oszczędza najwięcej czasu, brzmi: zacznij od najlepszego, potem tnij. Najpierw zbuduj działającą wersję na modelu flagowym i nie optymalizuj niczego. Dopiero gdy aplikacja robi to, co ma, spróbuj zejść niżej – ten sam zestaw testowy, model o rzędnie niższej cenie, porównanie wyników. Odwrotna kolejność, czyli zaczynanie od modelu taniego, kończy się tygodniami debugowania promptu, po których okazuje się, że zadanie po prostu przerasta model. Nie wiesz wtedy, czy problem jest w prompcie, w danych, czy w modelu, bo zmieniałeś wszystkie trzy rzeczy naraz.

Kryteria porządkuj w tej kolejności. Najpierw twarde ograniczenia: czy dane mogą opuścić Twoją infrastrukturę, czy potrzebujesz wejścia innego niż tekst, ile tokenów ma największy realny prompt, jakie masz wymogi co do regionu przetwarzania – to zawęża listę, zanim w ogóle spojrzysz na jakość. Potem jakość na Twoim zestawie. Potem koszt na tysiąc wywołań przy Twoim rozkładzie długości promptu, a nie cena katalogowa. Na końcu opóźnienie, o ile produkt jest interaktywny.

Routing to konsekwencja tego, że jedno zadanie to nie wszystkie zadania. Prosty router patrzy na typ zadania i długość wejścia i wybiera model, zanim cokolwiek wyśle. Bardziej rozbudowany dokłada eskalację: tani model odpowiada, a walidator (schemat, reguła biznesowa, próg pewności) decyduje, czy odpowiedź przyjąć, czy powtórzyć zapytanie na modelu mocniejszym. Ważne, żeby ta logika miała jedno miejsce w kodzie – funkcję, która przyjmuje opis zadania i zwraca identyfikator modelu wraz z parametrami.

```python
from dataclasses import dataclass

CHEAP = "claude-haiku-4-5"
FLAGSHIP = "claude-opus-5"
LONG_CONTEXT_LIMIT = 180_000


@dataclass(frozen=True)
class Route:
    model: str
    effort: str
    reason: str


def estimate_tokens(text: str) -> int:
    """Rough upper bound; use a real tokenizer when the number drives billing."""
    return len(text) // 3

def route(task: str, payload: str) -> Route:
    tokens = estimate_tokens(payload)
    if tokens > LONG_CONTEXT_LIMIT:
        return Route(FLAGSHIP, "medium", f"{tokens} tokens: needs the large window")
    if task in {"classify", "extract", "moderate"} and tokens < 4_000:
        return Route(CHEAP, "low", "short closed-set task, schema validates the answer")
    if task == "summarize":
        return Route(CHEAP, "medium", "single pass over known text")
    if task in {"plan", "review_code", "debug"}:
        return Route(FLAGSHIP, "high", "open-ended reasoning, errors are expensive")
    return Route(FLAGSHIP, "medium", "unknown task type, fall back to the strong model")

if __name__ == "__main__":
    cases = [
        ("classify", "Invoice attached, please refund order 12931."),
        ("summarize", "Meeting transcript. " * 500),
        ("review_code", "def charge(amount): return gateway.post(amount)"),
        ("extract", "Contract text. " * 40_000),
    ]
    for task, payload in cases:
        r = route(task, payload)
        print(f"{task:12} -> {r.model:18} effort={r.effort:6} ({r.reason})")
```

```text
classify     -> claude-haiku-4-5   effort=low    (short closed-set task, schema validates the answer)
summarize    -> claude-haiku-4-5   effort=medium (single pass over known text)
review_code  -> claude-opus-5      effort=high   (open-ended reasoning, errors are expensive)
extract      -> claude-opus-5      effort=medium (200000 tokens: needs the large window)
```

Router zwraca nie tylko model, ale i wysiłek oraz powód wyboru – powód trafia do logów i pozwala odpowiedzieć na pytanie „dlaczego to wywołanie kosztowało tyle". Zwróć uwagę na kolejność warunków: twarde ograniczenie długości sprawdzane jest pierwsze, bo żadna oszczędność nie ma znaczenia, jeśli prompt się nie zmieści. Funkcja jest czysta i bez zależności, więc obejmiesz ją testami jednostkowymi, a próg `LONG_CONTEXT_LIMIT` poniżej faktycznego okna daje margines na odpowiedź i na narastającą historię.

## Ekosystem Hugging Face

Hugging Face pełni w uczeniu maszynowym rolę, którą w Pythonie pełni PyPI, a w kontenerach – rejestr obrazów. Strona główna Huba podaje ponad dwa miliony modeli, ponad pięćset tysięcy zbiorów danych i ponad milion aplikacji (Spaces), utrzymywanych przez pięćdziesiąt tysięcy organizacji (stan na wrzesień 2026). Każdy model otwarty z poprzedniej sekcji ma tu repozytorium z kartą modelu, licencją i wagami, a pobranie go jest jedną linijką kodu.

Wejściem do katalogu są Tasks: taksonomia zadań podzielona na sześć grup modalności – multimodalne, przetwarzanie języka naturalnego, wizja komputerowa, audio, dane tabelaryczne i uczenie ze wzmocnieniem – w sumie kilkadziesiąt zadań. To użyteczny słownik, bo przekłada problem biznesowy na kategorię techniczną: „wyciągnij pola z faktury" to `document-question-answering` albo `token-classification`, „znajdź podobne zgłoszenia" to `sentence-similarity`, „ułóż wyniki wyszukiwania" to `text-ranking`. Znając nazwę zadania, filtrujesz Hub i porównujesz tylko sensowne kandydatury. Uwaga: etykiety na stronie Tasks nie są identyczne z identyfikatorami, które przyjmuje `pipeline()`.

Biblioteka `transformers` to warstwa wykonawcza. Funkcja `pipeline()` ukrywa całą mechanikę – pobranie wag, tokenizację, przepuszczenie przez model, zamianę logitów na etykiety – za jednym wywołaniem. Poniższy przykład uruchamia klasyfikator sentymentu lokalnie, bez żadnego klucza API.

```python
from transformers import pipeline

MODEL = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"

classifier = pipeline(task="text-classification", model=MODEL, device="cpu")

reviews = [
    "The checkout flow is fast and the docs are actually correct.",
    "Support took four days to answer and the answer was wrong.",
]
for review, result in zip(reviews, classifier(reviews)):
    print(f"{result['label']:8} {result['score']:.3f}  {review}")
```

```text
POSITIVE 1.000  The checkout flow is fast and the docs are actually correct.
NEGATIVE 0.999  Support took four days to answer and the answer was wrong.
```

Przy pierwszym uruchomieniu wagi ściągają się do lokalnego cache'u i kolejne wywołania startują w sekundę. Trzy szczegóły. Kanoniczna nazwa zadania to `text-classification`, a popularne `sentiment-analysis` jest jej aliasem. Parametr `device="cpu"` jest jawny, bo bez niego pipeline sam położy model na pierwszym dostępnym akceleratorze. Parametr sterujący precyzją nazywa się w `transformers` w wersji 5 po prostu `dtype` (domyślnie `"auto"`), a nie `torch_dtype` jak wcześniej.

Ten sam mechanizm działa w przeglądarce. Transformers.js to port biblioteki na JavaScript, publikowany w npm jako `@huggingface/transformers`, wykonujący modele przez ONNX Runtime na WebGPU albo na CPU. Dane nie opuszczają urządzenia użytkownika, więc nadaje się do klasyfikacji, wyszukiwania semantycznego i transkrypcji tam, gdzie wysyłka na serwer jest niemożliwa albo zbyt droga.

```javascript
import { pipeline } from '@huggingface/transformers';

const pipe = await pipeline(
  'sentiment-analysis',
  'Xenova/distilbert-base-uncased-finetuned-sst-2-english',
  { device: 'webgpu' },
);
const out = await pipe('I love transformers!');
console.log(out);
// [{ label: 'POSITIVE', score: 0.999817686 }]
```

API jest celowo bliźniacze wobec pythonowego: ta sama funkcja `pipeline`, ta sama nazwa zadania, ta sama struktura wyniku. Różnice są dwie – wszystko jest asynchroniczne, a model wskazujesz jawnie, bo domyślny wariant bywa zbyt duży jak na pobranie do przeglądarki. Kwantyzację ustawia opcja `dtype` (na przykład `'q4'`).

Trzecia droga to inferencja zdalna bez utrzymywania czegokolwiek. `InferenceClient` z pakietu `huggingface_hub` woła model z Huba u jednego z podpiętych dostawców mocy – Together, Groq, Fireworks, Cerebras, Replicate i kilkunastu innych – a Ty podajesz identyfikator modelu z Huba, nie identyfikator u dostawcy.

```python
import os
from huggingface_hub import InferenceClient

client = InferenceClient(
    model="meta-llama/Llama-3.3-70B-Instruct",
    provider="auto",
    api_key=os.environ["HF_TOKEN"],
)

output = client.chat_completion(
    messages=[{"role": "user", "content": "What is a reranker? Answer in two sentences."}],
    max_tokens=200,
)
print(output.choices[0].message.content)
print("model:", output.model, "tokens:", output.usage.total_tokens)
```

`provider="auto"` to wartość domyślna: klient wybiera pierwszego dostępnego dostawcę dla tego modelu, według kolejności z Twojego profilu. Odpowiedź jest dataclassem zgodnym kształtem ze specyfikacją OpenAI – nieprzypadkowo, bo `client.chat.completions.create` jest tu aliasem na `chat_completion`. Ten sam klient obsłuży serwer lokalny: `InferenceClient(model="http://localhost:8080")` zadziała z llama.cpp, vLLM, TGI albo Ollamą.

## Uruchamianie lokalne

Ollama to najkrótsza droga od „chcę sprawdzić ten model" do działającej odpowiedzi. Instalujesz jeden plik wykonywalny, wydajesz `ollama pull qwen3:8b`, a potem `ollama run qwen3:8b` daje czat w terminalu. Pod spodem działa serwer HTTP na porcie 11434 z endpointami `/api/generate` i `/api/chat`, a nazwy modeli mają postać `rodzina:rozmiar` – `llama3.3:70b`, `gemma4:12b`, `deepseek-r1:8b`. Odpowiedzi są domyślnie strumieniowane, a ostatni obiekt w strumieniu niesie metryki: liczbę tokenów i czasy w nanosekundach.

```python
from ollama import Client

MODEL = "qwen3:8b"  # pull it first: ollama pull qwen3:8b

client = Client(host="http://localhost:11434")
response = client.chat(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a concise backend engineering tutor."},
        {"role": "user", "content": "Explain a database index in two sentences."},
    ],
)

print(response.message.content)
print("generated tokens:", response.eval_count)
print("tokens per second:", response.eval_count / response.eval_duration * 1e9)
```

Biblioteka `ollama` (`pip install ollama`) opakowuje to API i pozwala czytać odpowiedź i jak słownik (`response["message"]["content"]`), i obiektowo. Poza `chat` masz `generate`, `embed`, `pull` oraz `AsyncClient`. Metryki z ostatniej linijki są przy self-hostingu najważniejszą liczbą: mówią, ile tokenów na sekundę wyciska Twój sprzęt na konkretnym modelu i konkretnej kwantyzacji – a od tego zależy, ilu użytkowników obsłużysz.

LM Studio rozwiązuje ten sam problem od strony interfejsu graficznego: aplikacja desktopowa z przeglądarką modeli, czatem i suwakami parametrów, a dla programisty – lokalny serwer zgodny z API OpenAI, uruchamiany z GUI albo poleceniem `lms server start`. Stoi na porcie 1234 i wystawia `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`, `/v1/models` oraz `/v1/responses`. Ollama ma analogiczną warstwę pod `http://localhost:11434/v1/`, a dodatkowo tryb zgodny z Messages API Anthropic pod `/v1/messages`.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",  # any non-empty string; the SDK refuses to start without one
)

completion = client.chat.completions.create(
    model="qwen/qwen3-4b-2507",  # the identifier shown in LM Studio
    messages=[{"role": "user", "content": "Explain a database index in two sentences."}],
)
print(completion.choices[0].message.content)
```

To wzorzec, który zobaczysz jeszcze kilka razy: bierzesz oficjalne SDK OpenAI, podmieniasz `base_url` i rozmawiasz z czymś zupełnie innym – a aplikację przełączasz między modelem lokalnym a chmurowym zmianą jednej zmiennej środowiskowej. LM Studio ma też własne SDK (`pip install lmstudio`) z kontrolą nad ładowaniem i zwalnianiem modeli z pamięci.

## OpenRouter i API zgodne z OpenAI

OpenRouter dociąga ten wzorzec do końca: jeden klucz, jeden `base_url` i katalog kilkuset modeli od wszystkich liczących się dostawców pod wspólnym interfejsem. Identyfikatory mają postać `autor/model` (`anthropic/claude-opus-5`, `openai/gpt-6-astra`, `google/gemini-3.8-flash`), a aliasy z tyldą – `~anthropic/claude-opus-latest` – zawsze wskazują najnowszy model w rodzinie, więc możesz wypuścić kod na stabilnym aliasie i dostawać nowe wersje bez wdrożenia. Za inferencję OpenRouter nie bierze marży; zarabia na prowizji od doładowania kredytów.

Najmocniejszą funkcją jest automatyczne przełączanie. Parametr `models` przyjmuje listę modeli w kolejności priorytetu i wchodzi w grę, gdy podstawowy dostawca jest niedostępny, limituje ruch albo odmawia odpowiedzi; płacisz według modelu, który faktycznie odpowiedział, a jego nazwę dostajesz w polu `model`. To najtańszy sposób na odporność na awarię jednego dostawcy.

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

completion = client.chat.completions.create(
    model="anthropic/claude-sonnet-5",
    extra_headers={
        "HTTP-Referer": "https://example.com/ticket-triage",
        "X-OpenRouter-Title": "Ticket triage",
    },
    extra_body={"models": ["openai/gpt-6-astra", "google/gemini-3.8-flash"]},
    messages=[{"role": "user", "content": "Summarize in one sentence: webhooks arrive twice."}],
)

print("answered by:", completion.model)
print(completion.choices[0].message.content)
```

Wszystko, czego SDK OpenAI nie zna, przemycasz przez `extra_body` – tam idzie lista modeli zapasowych, a także obiekt `provider`, którym wymuszasz konkretnego dostawcę mocy, sortowanie po cenie albo przepustowości, górny limit ceny za milion tokenów czy zakaz zbierania danych.

Cena tej wygody to utrata funkcji specyficznych dla dostawcy, bo interfejs jest najmniejszym wspólnym mianownikiem. Część rzeczy przetłumaczono: prompt caching Anthropic działa przez pole `cache_control` – jawnie na wybranych blokach treści (maksymalnie cztery punkty podziału) albo automatycznie, gdy ustawisz `cache_control` na najwyższym poziomie żądania, a OpenRouter sam przesuwa punkt podziału w miarę wydłużania rozmowy; oszczędność raportuje pole `cache_discount`. Warstwy zgodności wystawiają też sami dostawcy: Claude API pod `https://api.anthropic.com/v1/`, Gemini pod `https://generativelanguage.googleapis.com/v1beta/openai/`. Dokumentacja Anthropic wymienia przy tym wprost, czego się tam nie da: prompt caching nie działa, `response_format`, `reasoning_effort` i flaga `strict` przy narzędziach są ignorowane, a wiadomości systemowe są sklejane w jedną na początku rozmowy. Warstwa zgodności jest dobra do porównania modeli; produkcję pisz na natywnym API.

## Trzy API, jeden wzorzec

Trzy główne API robią to samo trzema słownikami. Wszystkie przyjmują instrukcję globalną, listę wiadomości i konfigurację, wszystkie zwracają tekst plus licznik tokenów, i wszystkie obsługują narzędzia, streaming i wyjście według schematu. Różnią się nazwami i kształtem odpowiedzi – i to jest dokładnie ta warstwa, którą warto schować za własnym interfejsem, żeby zmiana dostawcy nie oznaczała przepisywania aplikacji.

```python
import os
from anthropic import Anthropic
from openai import OpenAI
from google import genai

QUESTION = "Name the three main costs of running an LLM in production."
SYSTEM = "You answer in one short sentence."

claude = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = claude.messages.create(
    model="claude-opus-5",
    max_tokens=256,
    system=SYSTEM,
    messages=[{"role": "user", "content": QUESTION}],
)
print("claude:", next(b.text for b in message.content if b.type == "text"))

gpt = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = gpt.responses.create(
    model="gpt-6-astra",
    instructions=SYSTEM,
    input=QUESTION,
)
print("gpt:", response.output_text)

gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
interaction = gemini.interactions.create(
    model="gemini-3.8-flash",
    system_instruction=SYSTEM,
    input=QUESTION,
)
print("gemini:", interaction.output_text)
```

Trzy wywołania, trzy różne nazwy tego samego. Poniższa tabela zbiera różnice, o które najczęściej się potykasz przy przenoszeniu kodu między dostawcami (stan na wrzesień 2026).

| | Claude Messages API | OpenAI Responses API | Gemini Interactions API |
|---|---|---|---|
| Instrukcja globalna | `system=` | `instructions=` albo rola `developer` | `system_instruction=` |
| Wejście | `messages=[{role, content}]` | `input=` (tekst albo lista) | `input=` |
| Historia rozmowy | po stronie klienta | po stronie klienta albo `previous_response_id` | `previous_interaction_id`, stan po stronie serwera |
| Tekst odpowiedzi | lista bloków, filtr `type == "text"` | `response.output_text` | `interaction.output_text` |
| Sterowanie wysiłkiem | `output_config={"effort": ...}` | `reasoning={"effort": ...}` | `generation_config={"thinking_level": ...}` |
| Streaming | `client.messages.stream()` | `stream=True`, zdarzenia `response.output_text.delta` | `stream=True`, zdarzenia `step.delta` |
| Wyjście wg schematu | `messages.parse(output_format=...)` | `responses.parse(text_format=...)` | `generation_config` |

Najważniejsza różnica architektoniczna jest w wierszu o historii. Claude jest bezstanowe: całą rozmowę wysyłasz przy każdym żądaniu i to Ty decydujesz, co w niej zostaje. OpenAI i Gemini dają dodatkowo tryb serwerowy, w którym podajesz identyfikator poprzedniej tury, a resztę dokleja dostawca; u Gemini przechowywanie jest domyślnie włączone. Tryb serwerowy oszczędza kod i pasmo, ale odbiera Ci kontrolę nad tym, co dokładnie ląduje w oknie kontekstu – a to jest temat rozdziału 4 i jeden z głównych sposobów panowania nad kosztem.

## Fine-tuning w skrócie

Fine-tuning to douczenie gotowego modelu na Twoich przykładach. Ma sens w trzech sytuacjach: gdy potrzebujesz stałego formatu albo stylu, którego prompt nie utrzymuje; gdy chcesz przenieść zachowanie modelu dużego na model mały i tani; gdy zadanie jest wąskie, powtarzalne i masz setki przykładów poprawnych wyników. Nie ma sensu jako sposób na wtłoczenie do modelu wiedzy faktograficznej – od tego jest RAG, a porównanie obu podejść z kryteriami wyboru znajdziesz w rozdziale 8.

Krajobraz u dostawców zamkniętych zrobił się ubogi i warto to wiedzieć, zanim zaplanujesz architekturę wokół dostrajania. Claude API nie oferuje fine-tuningu – modele Claude dostraja się przez Amazon Bedrock. Gemini API nie ma obecnie modelu wspierającego dostrajanie i dokumentacja mówi wprost, że nie ma na to planów. Cohere wycofał fine-tuning we wrześniu 2025, Mistral oznaczył swoją dokumentację dostrajania jako wycofaną. Realnie zostaje OpenAI z trzema metodami: supervised fine-tuning (SFT) na parach wejście–wyjście, direct preference optimization (DPO) na parach odpowiedź lepsza–gorsza i reinforcement fine-tuning (RFT) dla modeli rozumujących, gdzie odpowiedzi ocenia grader.

Proces u dostawcy ma zawsze ten sam kształt: przygotuj plik JSONL, w którym każda linia jest jednym przykładem w formacie rozmowy, wgraj go jako plik o przeznaczeniu `fine-tune`, utwórz zadanie dostrajania, poczekaj, a potem używaj zwróconego identyfikatora modelu tak samo jak nazwy modelu bazowego.

```python
import json
import os
from openai import OpenAI

BASE_MODEL = "gpt-4.1-2025-04-14"  # check docs for the current fine-tunable model id

examples = [
    {"messages": [
        {"role": "system", "content": "You classify support tickets for Acme Payments."},
        {"role": "user", "content": "POST /v1/charges returns 500 since this morning."},
        {"role": "assistant", "content": '{"category": "outage", "severity": 1}'},
    ]},
]

with open("train.jsonl", "w", encoding="utf-8") as f:
    for example in examples:
        f.write(json.dumps(example, ensure_ascii=False) + "\n")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
uploaded = client.files.create(file=open("train.jsonl", "rb"), purpose="fine-tune")
job = client.fine_tuning.jobs.create(
    model=BASE_MODEL,
    training_file=uploaded.id,
    method={"type": "supervised", "supervised": {"hyperparameters": {"n_epochs": "auto"}}},
)
print(job.id, job.status)
```

Jeden przykład w liście jest ilustracją formatu – realny zbiór ma ich od kilkuset wzwyż plus osobny zbiór walidacyjny. Zwróć uwagę, że przykłady mają dokładnie taki kształt, jakiego użyjesz w produkcji, razem z system promptem; zmiana system promptu po dostrojeniu potrafi zepsuć wynik. Zadanie jest asynchroniczne – `job.status` odpytujesz później, a po zakończeniu dostajesz identyfikator modelu, który podajesz w `model=` przy zwykłych wywołaniach.

Dla modeli otwartych droga jest tańsza, niż się wydaje. Standardem jest biblioteka TRL od Hugging Face z gotowymi klasami treningowymi – `SFTTrainer`, `DPOTrainer`, `GRPOTrainer` – zintegrowana z PEFT, czyli z adapterami typu LoRA. Adapter oznacza, że nie dotykasz oryginalnych wag, tylko uczysz małą macierz korekcyjną: trening mieści się na jednej karcie, wynik waży kilkadziesiąt megabajtów zamiast kilkudziesięciu gigabajtów, a jeden model bazowy obsłuży wiele adapterów.

Kiedy fine-tuning nie pomoże: gdy model myli fakty (dołóż dane do kontekstu), gdy odpowiedzi są niespójne, bo prompt jest niejednoznaczny (popraw prompt), gdy masz mniej niż kilkadziesiąt przykładów (użyj few-shot), i gdy nie masz zestawu ewaluacyjnego – bo wtedy nie będziesz wiedział, czy dostrojony model jest lepszy, czy tylko inny.

## Podsumowanie

- Wybór modelu jest kompromisem między kosztem, opóźnieniem, jakością i ryzykiem dostawcy; te cztery osie prawie nigdy nie wskazują tego samego modelu.
- Model bazowy kontynuuje tekst, model instrukcyjny odpowiada – na Hugging Face rozróżnisz je po przyrostku `-Instruct` albo `-it` w nazwie repozytorium.
- „Open weights" to nie „open source": licencje otwartych rodzin bywają różne nawet w obrębie jednej marki, więc czytaj plik `LICENSE`, zanim zbudujesz na modelu produkt.
- Self-hosting opłaca się przy dużym, stałym ruchu albo wtedy, gdy dane nie mogą opuścić Twojej sieci; przy ruchu nierównym API prawie zawsze wygrywa.
- Zacznij od modelu flagowego, doprowadź aplikację do działania, a dopiero potem schodź na tańszy wariant – z tym samym zestawem testowym.
- Routing i eskalacja to normalna architektura: jedna funkcja wybiera model i wysiłek, a walidator decyduje, czy powtórzyć zapytanie na mocniejszym modelu.
- Hugging Face jest rejestrem całego ekosystemu, a Ollama i LM Studio dają lokalny serwer zgodny z API OpenAI – przełączenie aplikacji na model lokalny to zmiana `base_url`.
- Warstwy zgodne z OpenAI upraszczają kod kosztem funkcji specyficznych dla dostawcy: prompt cachingu, structured outputs z gwarancją schematu, bloków myślenia.

## Co dalej

Masz mapę modeli i sposobów ich uruchamiania. Rozdział 6 („Embeddingi") schodzi piętro niżej – do modeli, które nie generują tekstu, tylko zamieniają go na wektory, i od których zaczyna się każde wyszukiwanie semantyczne. Zanim tam przejdziesz, zrób dwie rzeczy. Po pierwsze, uruchom snippet z `pipeline()` u siebie i podmień model na taki, który rozumie polski – zobaczysz, ile kosztuje wejście w świat modeli otwartych (kilka minut i kilkaset megabajtów). Po drugie, weź jedno miejsce w swoim kodzie, w którym nazwa modelu jest zapisana na sztywno, i schowaj je za funkcją w rodzaju `route()` ze snippetu o wyborze modelu. Bez tej jednej funkcji żadna optymalizacja kosztu z tego rozdziału nie będzie wykonalna.

## Źródła

- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk
- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/guides/fine-tuning
- https://developers.openai.com/api/docs/guides/conversation-state
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/quickstart
- https://ai.google.dev/gemini-api/docs/text-generation
- https://ai.google.dev/gemini-api/docs/interactions
- https://ai.google.dev/gemini-api/docs/openai
- https://ai.google.dev/gemini-api/docs/model-tuning
- https://docs.cohere.com/docs/models
- https://docs.cohere.com/docs/fine-tuning
- https://docs.mistral.ai/getting-started/models/
- https://mistral.ai/pricing/api
- https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct
- https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash
- https://huggingface.co/Qwen/Qwen3.8-27B
- https://ai.google.dev/gemma/docs/core/model_card_4
- https://huggingface.co/tasks
- https://huggingface.co/docs/transformers/pipeline_tutorial
- https://huggingface.co/docs/transformers/main_classes/pipelines
- https://huggingface.co/docs/huggingface_hub/guides/inference
- https://huggingface.co/docs/transformers.js/index
- https://huggingface.co/docs/trl/index
- https://github.com/ollama/ollama/blob/main/docs/api.md
- https://github.com/ollama/ollama-python
- https://lmstudio.ai/docs/developer/openai-compat
- https://openrouter.ai/docs/quickstart
- https://openrouter.ai/docs/guides/routing/model-fallbacks
- https://openrouter.ai/docs/guides/best-practices/prompt-caching
- https://opensource.org/ai/open-source-ai-definition
