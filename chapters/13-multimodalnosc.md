# Rozdział 13. Multimodalna AI

> **Z roadmapy:** Multimodal AI, Multimodal AI Usecases, Multimodal AI Tasks, Image Understanding, Image Generation, Video Understanding, Audio Processing, Text-to-Speech, Speech-to-Text, Implementing Multimodal AI, OpenAI Vision API, DALL-E API, NanoBanana API, Whisper API, Hugging Face Models, LangChain for Multimodal Apps, LlamaIndex for Multimodal Apps
>
> **Pakiety:** `pip install anthropic openai google-genai pydantic transformers pillow torch opencv-python faster-whisper langchain langchain-anthropic llama-index llama-index-vector-stores-qdrant llama-index-multi-modal-llms-openai`

Multimodalność brzmi jak osobna dziedzina, a w praktyce jest jednym dodatkowym typem bloku w liście `content`. W rozdziale 3 zobaczyłeś, że wiadomość to nie string, tylko lista bloków; obraz, dokument PDF i nagranie audio to po prostu inne wartości pola `type` w tej samej liście, wysyłane tym samym wywołaniem, do tego samego modelu, z tym samym `system` i tymi samymi narzędziami. Nie ma osobnego endpointu „vision", nie ma osobnego klienta, nie ma osobnego promptu. Jest blok `image` obok bloku `text` i tyle.

Konsekwencje produktowe są większe, niż sugeruje ta prostota. OCR przestaje być osobnym krokiem pipeline'u – zamiast Tesseracta, heurystyk na współrzędne i parsera na regexach wysyłasz zdjęcie faktury i klasę Pydantic, a dostajesz zwalidowany obiekt. Analiza zrzutów ekranu w zgłoszeniach supportowych przestaje wymagać człowieka. Wideo z kamery, nagranie ze spotkania, skan umowy, wykres z prezentacji – wszystko to wchodzi do modelu bez pośredniczącej warstwy ekstrakcji, którą trzeba było utrzymywać osobno dla każdego formatu.

Kosztuje to jednak inaczej niż tekst i to jest główna rzecz do zrozumienia w tym rozdziale. Obraz o rozmiarze 1000 na 1000 pikseli to dla Claude 1296 tokenów wejściowych – tyle, co dwie strony gęstego tekstu. Minuta wideo w Gemini to około 6 tysięcy tokenów przy domyślnej rozdzielczości, a minuta audio 1920 tokenów (stan na wrzesień 2026). Jeśli podejdziesz do tego bez planu, pierwszy rachunek za „wrzućmy wszystkie zrzuty ekranu do modelu" będzie nieprzyjemną niespodzianką. Cała reszta tego rozdziału to API plus arytmetyka: co ile kosztuje i gdzie da się zejść niżej bez utraty jakości.

## Zastosowania (Multimodal AI Usecases)

**Ekstrakcja danych z faktur i paragonów.** To najczęstszy pierwszy projekt multimodalny i zwykle najbardziej opłacalny, bo zastępuje kilka tysięcy linii reguł. Model czyta zdjęcie zrobione telefonem, radzi sobie z przekrzywieniem, zagięciem i cieniem, i zwraca ustrukturyzowany obiekt. Ograniczenie: kwoty trzeba walidować po stronie kodu – sprawdź, czy suma pozycji zgadza się z sumą całkowitą, bo model potrafi przepisać cyfrę i nie zasygnalizować wątpliwości. Dla dokumentów, w których pomyłka kosztuje, zostaw ścieżkę eskalacji do człowieka przy niskiej pewności.

**Moderacja obrazów.** Model potrafi ocenić, czy zdjęcie produktu wystawionego na marketplace narusza politykę serwisu, i uzasadnić decyzję po polsku, czego klasyczny klasyfikator nie robi. Ograniczenie jest dwojakie: modele odmawiają przetwarzania treści naruszających politykę dostawcy, więc twoja moderacja nie zobaczy najgorszych przypadków, tylko dostanie błąd; i nie da się użyć modelu do identyfikacji osób na zdjęciu – Claude tego odmawia z zasady. Moderacja skali (miliony obrazów dziennie) i tak wypada taniej na małym klasyfikatorze z Hugging Face, a model duży wchodzi dopiero jako druga instancja dla przypadków granicznych.

**Opisy produktów.** Zdjęcie plus kilka atrybutów ze sklepu daje opis, tytuł i tagi. Działa dobrze, bo zadanie jest tolerancyjne na błąd, a wynik i tak przechodzi przez redakcję. Warto trzymać w prompcie listę dozwolonych kategorii i kolorów, inaczej dostaniesz „głęboka morska zieleń" tam, gdzie Twój katalog zna tylko „zielony".

**Analiza wykresów.** Wysłanie wykresu z raportu PDF i pytanie o trend działa zaskakująco dobrze – model czyta osie, legendę i etykiety. Ograniczenie: odczyt konkretnych wartości z wykresu bez etykiet liczbowych jest przybliżony i nie nadaje się do raportowania finansowego. Jeśli masz dane źródłowe, podaj je jako tekst; obraz zostaw do pytań o kształt, anomalie i kompozycję.

**Transkrypcja spotkań.** Model transkrypcyjny zamienia nagranie na tekst z podziałem na mówców, a model tekstowy robi z tego notatkę z decyzjami i zadaniami. Ograniczenie to rozmiar pliku: endpoint transkrypcji OpenAI przyjmuje maksymalnie 25 MB, więc godzinne spotkanie trzeba pociąć albo skompresować do formatu stratnego. Przy cięciu zostaw kilkusekundowe zakładki, inaczej zgubisz słowa na granicy.

**Asystent głosowy.** Pętla mowa–tekst–model–mowa jest dziś trywialna do złożenia z trzech wywołań, ale opóźnienie sumuje się do kilku sekund i to widać. Do rozmowy w czasie rzeczywistym potrzebujesz API strumieniowego, które przyjmuje i zwraca audio bez pośredniej reprezentacji tekstowej (Realtime po stronie OpenAI, Live po stronie Google). Trzy osobne wywołania są za to prostsze w debugowaniu i wystarczają wszędzie tam, gdzie użytkownik nie oczekuje przerywania w pół zdania.

**Przeszukiwanie wideo.** Pytanie „w której minucie nagrania pokazują konfigurację webhooków" zadane do godzinnego materiału to zadanie, którego przed modelami wideo praktycznie się nie robiło. Gemini przyjmuje wideo natywnie i zwraca znaczniki czasu. Ograniczenie jest budżetowe: godzina wideo przy niskiej rozdzielczości mediów to około 360 tysięcy tokenów, więc indeksowanie całej biblioteki szkoleń kosztuje realne pieniądze i lepiej zrobić to raz, zapisując transkrypcję i opisy scen do bazy wektorowej z rozdziału 7.

## Rozumienie obrazu (Image Understanding)

Claude nie widzi pikseli, tylko łatki (patches). Każda łatka to blok 28 na 28 pikseli i jeden token wizualny, więc obraz kosztuje `⌈szerokość / 28⌉ × ⌈wysokość / 28⌉` tokenów. Obraz 1000 na 1000 to 36 razy 36, czyli 1296 tokenów. Każdy model ma limit rozdzielczości natywnej wyrażony jako najdłuższa krawędź i maksymalna liczba tokenów wizualnych: modele od Claude 4.7 wzwyż mają 2576 pikseli i 4784 tokeny, starsze 1568 pikseli i 1568 tokenów. Co większe, jest przeskalowywane w dół z zachowaniem proporcji, więc górna granica kosztu za obraz jest twarda (stan na wrzesień 2026).

Z tej arytmetyki wynika konkretna rada. Zdjęcie 4K wysłane do Claude Opus 5 to 4784 tokeny, czyli przy stawce 5 dolarów za milion tokenów wejściowych około 23,92 dolara za tysiąc obrazów; to samo zdjęcie przeskalowane do 1568 pikseli kosztuje najwyżej 1560 tokenów i około 7,80 dolara za tysiąc. Jeśli nie odczytujesz drobnego druku ani nie klikasz po współrzędnych, zmniejsz obraz przed wysłaniem. Odwrotnie: przy gęstym dokumencie albo zrzucie ekranu w pełnej rozdzielczości wyższa rozdzielczość jest tym, za co płacisz, i warto ją mieć.

Reszta limitów: formaty JPEG, PNG, GIF i WebP (animacje nie są obsługiwane, liczy się pierwsza klatka), maksymalnie 8000 na 8000 pikseli, 10 MB na obraz w base64, 100 obrazów na żądanie dla modeli z oknem 200 tysięcy tokenów i 600 dla pozostałych, przy czym całe żądanie nie może przekroczyć 32 MB. Powyżej 20 obrazów w jednym żądaniu obowiązuje ostrzejszy limit wymiarów każdego z nich – najprościej zejść do 2000 pikseli na dłuższej krawędzi. Obraz podajesz na trzy sposoby: jako base64 w treści żądania, jako `url` do zasobu w internecie albo jako `file_id` z Files API. Ta trzecia droga ma sens w rozmowach wieloturowych i u agentów, bo historię wysyłasz w całości przy każdej turze, a base64 obrazu leci wtedy w kółko; `file_id` to kilkanaście bajtów zamiast kilku megabajtów. Jedna drobna wskazówka z dokumentacji: układaj obraz przed tekstem, bo ta kolejność wypada mierzalnie lepiej.

```python
import base64
import os
from anthropic import Anthropic
from pydantic import BaseModel, Field

class InvoiceLine(BaseModel):
    description: str
    quantity: float
    unit_price_net: float

class Invoice(BaseModel):
    seller_name: str
    invoice_number: str
    issue_date: str = Field(description="ISO 8601 date, YYYY-MM-DD")
    currency: str
    total_gross: float
    lines: list[InvoiceLine]

with open("invoice.png", "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("ascii")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
response = client.messages.parse(
    model="claude-opus-5",
    max_tokens=2048,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png", "data": image_data}},
            {"type": "text", "text": "Extract the invoice data. Copy amounts exactly as printed."},
        ],
    }],
    output_format=Invoice,
)

invoice: Invoice = response.parsed_output
print(invoice.invoice_number, invoice.total_gross, len(invoice.lines))
print("input tokens:", response.usage.input_tokens)
```

To jest ten sam `messages.parse()` z klasą Pydantic co w rozdziale 3, tylko z blokiem `image` dodanym przed tekstem. Nie ma tu żadnego kroku OCR – model czyta obraz i wypełnia schemat w jednym wywołaniu, a `response.parsed_output` jest instancją `Invoice` z gotową walidacją typów. Zwróć uwagę na `response.usage.input_tokens`: zobaczysz tam sumę tokenów tekstowych i wizualnych, więc to najprostszy sposób, żeby zmierzyć, ile naprawdę kosztuje Twój format wejściowy, zanim wypuścisz to na produkcję. Walidacja semantyczna zostaje po Twojej stronie – suma `quantity * unit_price_net` powinna zgadzać się z `total_gross` po doliczeniu podatku i to sprawdzasz w kodzie, nie w prompcie.

Po stronie OpenAI kształt jest analogiczny, ale nazwy inne. W Responses API blok ma typ `input_image`, a obraz podajesz w polu `image_url` – albo jako adres HTTP, albo jako data URI z base64, albo zamiast tego przez `file_id` z Files API. Dochodzi parametr `detail` o wartościach `low`, `high`, `original` i `auto`, który steruje tym, jak dokładnie obraz jest wstępnie przetwarzany, a więc ile tokenów kosztuje.

```python
import base64
import os
from openai import OpenAI

with open("screenshot.png", "rb") as f:
    encoded = base64.standard_b64encode(f.read()).decode("ascii")
data_url = f"data:image/png;base64,{encoded}"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = client.responses.create(
    model="gpt-6-astra",
    input=[{
        "role": "user",
        "content": [
            {"type": "input_text",
             "text": "Which control on this screen is disabled, and what does the tooltip say?"},
            {"type": "input_image", "image_url": data_url, "detail": "high"},
        ],
    }],
)
print(response.output_text)
print("input tokens:", response.usage.input_tokens)
```

Modele OpenAI liczą obraz na łatkach 32 na 32 piksele z mnożnikiem zależnym od modelu (dla `gpt-6-astra` typowo 1,2), więc obraz 1024 na 1024 przy `detail: "high"` to około 1229 tokenów – rząd wielkości ten sam co u Claude, ale nie ta sama liczba, więc nie przenoś oszacowań między dostawcami. Limity też są inne: do 512 MB na żądanie, do 1500 obrazów i maksymalnie 30 tysięcy łatek na obraz, formaty PNG, JPEG, WebP i nieanimowany GIF (stan na wrzesień 2026). Wartość `low` przydaje się przy zadaniach typu „czy na zdjęciu jest paragon", gdzie liczy się przepustowość, a nie odczyt drobnego druku.

Osobno warto znać PDF, bo to jest najczęstsze wejście w aplikacjach biznesowych i Claude obsługuje je natywnie. Wysyłasz blok `document` zamiast `image`, ze źródłem `url`, `base64` albo `file` – tak samo jak przy obrazach. Model przetwarza każdą stronę jednocześnie jako tekst i jako obraz, dzięki czemu widzi układ, tabele i wykresy, a nie tylko wyekstrahowany strumień znaków. Cena tego jest jawna: typowa strona to 1500–3000 tokenów tekstowych plus tokeny wizualne liczone jak dla obrazu, więc dwudziestostronicowa umowa to realnie kilkadziesiąt tysięcy tokenów. Limity to 600 stron na żądanie (100, gdy okno kontekstu modelu jest mniejsze niż milion tokenów) i 32 MB na całe żądanie; dla większych plików upload przez Files API i referencja przez `file_id` jest jedyną sensowną drogą. Jeśli dokument jest czystym tekstem bez layoutu, taniej i pewniej wyciągnąć tekst lokalnie i wysłać go jako zwykły string.

## Generowanie obrazów (Image Generation)

Węzeł roadmapy nazywa się „DALL-E API" i to jest dobry przykład na to, jak szybko starzeje się ta dziedzina. DALL·E już nie ma: OpenAI ogłosiło deprecjację snapshotów DALL·E 14 listopada 2025 i usunęło je z API 12 maja 2026. Endpoint `/v1/images/generations` został – zmieniły się tylko modele. Dziś dokumentacja wymienia dwa: `gpt-image-2.5-sunburst` do zadań, w których liczy się precyzja edycji, i `gpt-image-2.5-flare` do szybkiego, codziennego generowania. Kod, który miałeś na `dall-e-3`, wymaga podmiany identyfikatora modelu i uwagi na dwie różnice: modele `gpt-image-*` zawsze zwracają obraz jako base64 (nie ma `response_format="url"`), a skala jakości to `low`, `medium`, `high`, `xhigh` i `max` zamiast `standard` i `hd` (stan na wrzesień 2026).

```python
import base64
import os
from openai import OpenAI

MODEL = "gpt-image-2.5-sunburst"  # "gpt-image-2.5-flare" is the fast everyday model

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
result = client.images.generate(
    model=MODEL,
    prompt=("A flat vector illustration of a warehouse conveyor belt carrying three "
            "labelled parcels, muted blue palette, plenty of empty space on the right, "
            "no text and no logos."),
    size="1536x1024",
    quality="high",
    output_format="png",
    n=1,
)

with open("banner.png", "wb") as f:
    f.write(base64.b64decode(result.data[0].b64_json))
print("saved banner.png")
```

Parametr `size` przyjmuje `auto`, trzy standardowe proporcje (`1024x1024`, `1536x1024`, `1024x1536`) oraz dowolne `SZEROKOŚĆxWYSOKOŚĆ` podzielne przez 16, o proporcjach między 1:3 a 3:1. `output_format` to format pliku (`png`, `jpeg`, `webp`), a nie sposób kodowania odpowiedzi – to częste źródło pomyłki, bo obraz i tak przychodzi w `data[0].b64_json`. Prompt traktuj jak brief dla grafika: opisz kompozycję, paletę i to, czego ma nie być. Instrukcja „bez tekstu" jest w praktyce jedną z najważniejszych, bo napisy generowane w obrazie bywają zniekształcone i nie da się ich potem poprawić bez ponownej generacji.

Węzeł „NanoBanana API" to potoczna nazwa modeli graficznych Gemini i akurat ta nazwa przetrwała – dokumentacja Google wprost nazywa je modelami Nano Banana. Aktualne identyfikatory to `gemini-3.1-flash-image` (podstawowy), `gemini-3-pro-image` (najwyższa jakość), `gemini-3.1-flash-lite-image` (najtańszy) i `gemini-2.5-flash-image` (starszy). Wywołujesz je tym samym `client.interactions.create()`, którym wywołujesz modele tekstowe – to jest główna różnica konceptualna wobec OpenAI, gdzie generowanie obrazów ma osobny endpoint. Dzięki temu edycja obrazu to po prostu prompt z blokiem `image` na wejściu.

```python
import base64
import os
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

created = client.interactions.create(
    model="gemini-3.1-flash-image",
    input="Product photo of a matte ceramic mug on a white studio background, soft shadow.",
)
with open("mug.png", "wb") as f:
    f.write(base64.b64decode(created.output_image.data))

with open("mug.png", "rb") as f:
    mug = base64.b64encode(f.read()).decode("utf-8")

edited = client.interactions.create(
    model="gemini-3.1-flash-image",
    input=[
        {"type": "text",
         "text": "Put the same mug on a wooden kitchen table near a window. Keep the mug identical."},
        {"type": "image", "data": mug, "mime_type": "image/png"},
    ],
)
with open("mug_kitchen.png", "wb") as f:
    f.write(base64.b64decode(edited.output_image.data))
print("saved mug.png and mug_kitchen.png")
```

Drugie wywołanie to właśnie edycja: ten sam model, ten sam endpoint, tylko na wejściu jest obraz i instrukcja, co z nim zrobić. Modele Nano Banana przyjmują wiele obrazów referencyjnych naraz (do czternastu w wariancie flash lite), co pozwala trzymać spójność postaci albo produktu przez całą serię. Rozdzielczości to 512 pikseli, 1K, 2K i 4K, a proporcje od 1:1 do 21:9.

Koszt jest przewidywalny i warto go znać przed wdrożeniem: obraz 1K to 1120 tokenów wyjściowych, czyli około 0,067 dolara dla `gemini-3.1-flash-image`, 0,0336 dolara dla wariantu flash lite i 0,134 dolara dla `gemini-3-pro-image`; obraz 4K to odpowiednio około 0,151 i 0,24 dolara (stan na wrzesień 2026). Przy generowaniu miniaturek do katalogu z dziesięcioma tysiącami produktów różnica między wariantami to setki dolarów, więc wybór modelu jest decyzją budżetową, nie estetyczną.

Zostaje kwestia praw i oznaczeń. Wszystkie obrazy generowane przez modele Gemini zawierają znak wodny SynthID – niewidoczny dla oka, wykrywalny narzędziami Google. To nie jest opcja, którą można wyłączyć, i dobrze o tym wiedzieć, zanim obiecasz klientowi „autorskie zdjęcia produktowe". Warunki licencyjne na wygenerowane obrazy różnią się między dostawcami i bywają zmieniane, a w niektórych jurysdykcjach obraz wygenerowany bez wkładu człowieka w ogóle nie podlega prawu autorskiemu, więc nie masz czego licencjonować dalej. Jeśli obrazy trafiają do produktu komercyjnego, przeczytaj aktualne warunki dostawcy i oznacz materiał wygenerowany maszynowo – w Unii Europejskiej AI Act wymaga tego wprost dla treści syntetycznych.

## Rozumienie wideo (Video Understanding)

Gemini przyjmuje wideo natywnie, bez próbkowania klatek po Twojej stronie. Krótkie pliki (poniżej 100 MB i około minuty) wysyłasz inline w treści żądania, dłuższe przez Files API, które przyjmuje do 2 GB na plik i przechowuje go przez 48 godzin; przyjmowane są też publiczne adresy YouTube. Modele z oknem miliona tokenów przetwarzają domyślnie materiał do trzech godzin przy niskiej rozdzielczości mediów albo do godziny przy wysokiej. Cena to około 100 tokenów na sekundę wideo przy rozdzielczości domyślnej i około 300 przy wysokiej, co daje wspomniane 360 tysięcy tokenów za godzinę materiału (stan na wrzesień 2026).

```python
import os
import time
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

video = client.files.upload(file="standup.mp4")
while not video.state or video.state.name != "ACTIVE":
    time.sleep(5)
    video = client.files.get(name=video.name)

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input=[
        {"type": "video", "uri": video.uri, "mime_type": video.mime_type},
        {"type": "text",
         "text": "List every decision made in this meeting as 'MM:SS - decision - owner'."},
    ],
)
print(interaction.output_text)
```

Pętla oczekiwania na stan `ACTIVE` jest obowiązkowa – upload jest asynchroniczny i plik użyty za wcześnie zwróci błąd. Model rozumie czas, więc pytania o znaczniki czasowe mają sens i to jest najcenniejsza część tej funkcji: dostajesz indeks nagrania, a nie streszczenie. Gdy nie potrzebujesz pełnej płynności, obniż koszt konfiguracją: ustawienie `fps` na 0,5 oznacza jedną klatkę na dwie sekundy, a `start_offset` i `end_offset` pozwalają wysłać tylko interesujący fragment zamiast całości. To zwykle tańsze niż przełączanie modelu.

Alternatywa działa wszędzie i nie wymaga modelu wideo: próbkujesz klatki samodzielnie i wysyłasz kilka z nich jako zwykłe obrazy. Traci się ciągłość ruchu i ścieżkę dźwiękową, ale do pytań typu „co się zmieniło na ekranie" albo „w którym momencie pojawił się komunikat błędu" to w zupełności wystarcza – i pozwala użyć modelu, którego już używasz w reszcie aplikacji.

```python
import base64
import os
import cv2
from anthropic import Anthropic

def sample_frames(path: str, every_n_seconds: float = 2.0, max_frames: int = 8) -> list[str]:
    capture = cv2.VideoCapture(path)
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(int(fps * every_n_seconds), 1)
    frames, index = [], 0
    while len(frames) < max_frames:
        ok, frame = capture.read()
        if not ok:
            break
        if index % step == 0:
            frame = cv2.resize(frame, (768, 432))
            ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                frames.append(base64.standard_b64encode(buffer).decode("ascii"))
        index += 1
    capture.release()
    return frames

content = []
for i, frame in enumerate(sample_frames("screencast.mp4")):
    content.append({"type": "text", "text": f"Frame {i} (t={i * 2}s):"})
    content.append({"type": "image", "source": {"type": "base64",
                                                "media_type": "image/jpeg", "data": frame}})
content.append({"type": "text", "text": "At which timestamp does an error dialog appear?"})

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(model="claude-opus-5", max_tokens=1024,
                                 messages=[{"role": "user", "content": content}])
print(next(b.text for b in message.content if b.type == "text"))
```

Trzy decyzje w tej funkcji są warte uwagi, bo wszystkie dotyczą kosztu. `max_frames` jest twardym limitem, żeby dziesięciominutowy screencast nie zamienił się w dwieście obrazów; przy `every_n_seconds=2` osiem klatek pokrywa szesnaście sekund i przy dłuższym materiale trzeba raczej zwiększyć odstęp niż liczbę klatek. `cv2.resize` do 768 na 432 to około 27 na 16 łatek, czyli 432 tokeny na klatkę zamiast kilku tysięcy dla klatki 4K. Wreszcie każda klatka jest poprzedzona etykietą tekstową ze znacznikiem czasu – bez tego model nie ma jak odnieść się do konkretnego momentu, a Ty nie masz jak zweryfikować odpowiedzi.

## Audio

### Speech-to-Text i Whisper API

Węzeł roadmapy mówi „Whisper API" i pod tą nazwą kryje się dziś kilka modeli o różnym przeznaczeniu. Rekomendowany do transkrypcji nagrań jest `gpt-transcribe`. `gpt-4o-transcribe-diarize` służy do rozpoznawania mówców. Stary `whisper-1` nadal jest w API i pozostaje właściwym wyborem tam, gdzie potrzebujesz znaczników czasu na poziomie słów (parametr `timestamp_granularities`), napisów albo tłumaczenia na angielski przez `/v1/audio/translations`. Modele `gpt-4o-transcribe` i `gpt-4o-mini-transcribe` są oznaczone jako starsze (stan na wrzesień 2026). Endpoint jest jeden: `client.audio.transcriptions.create()`, przyjmuje pliki do 25 MB w formatach mp3, mp4, mpeg, mpga, m4a, wav i webm.

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

with open("meeting.mp3", "rb") as audio_file:
    plain = client.audio.transcriptions.create(
        model="gpt-transcribe",
        file=audio_file,
        language="pl",
        prompt="Rozmowa o Qdrancie, embeddingach i API Acme Payments.",
    )
print(plain.text[:200])

with open("meeting.mp3", "rb") as audio_file:
    diarized = client.audio.transcriptions.create(
        model="gpt-4o-transcribe-diarize",
        file=audio_file,
        response_format="diarized_json",
    )
for segment in diarized.segments:
    print(f"[{segment.start:7.2f}] {segment.speaker}: {segment.text}")
```

Pierwsze wywołanie zwraca sam tekst. Parametr `prompt` nie jest instrukcją dla modelu w sensie rozdziału 3 – to podpowiedź słownikowa, która realnie poprawia zapis nazw własnych i żargonu. Wpisz tam nazwy produktów, skróty i nazwiska, które padają w nagraniu, bo inaczej „Qdrant" wróci jako „kwadrant". Drugie wywołanie włącza diaryzację: `response_format="diarized_json"` daje obiekt z polami `text`, `duration` i listą `segments`, w której każdy segment ma `start`, `end`, `text` i `speaker` (etykieta `A`, `B` i tak dalej albo nazwa, jeśli podasz `known_speaker_names` z próbkami głosu). Przy dłuższych nagraniach dodaj `stream=True` – dostaniesz częściowe transkrypty na bieżąco i pełny tekst w końcowym zdarzeniu `transcript.text.done`.

Lokalna alternatywa ma sens wszędzie tam, gdzie nagranie nie może opuścić infrastruktury, albo gdzie transkrybujesz tysiące godzin i chmura przestaje się opłacać. `faster-whisper` to reimplementacja Whispera na CTranslate2, kilkukrotnie szybsza od referencyjnego `openai-whisper` przy tej samej jakości; model `small` waży około 500 MB i działa na CPU w tempie zbliżonym do czasu rzeczywistego.

```python
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("meeting.mp3", language="pl", vad_filter=True)

print(f"detected language: {info.language} (p={info.language_probability:.2f})")
for segment in segments:
    print(f"[{segment.start:7.2f} -> {segment.end:7.2f}] {segment.text}")
```

`vad_filter=True` włącza detekcję aktywności głosowej, która wycina ciszę – na nagraniach ze spotkań potrafi to skrócić czas przetwarzania o połowę i ograniczyć halucynacje modelu na fragmentach bez mowy. `segments` jest generatorem, więc transkrypcja startuje dopiero przy pierwszej iteracji; to wygodne, bo możesz strumieniować wynik dalej, ale mylące, gdy mierzysz czas wywołania `transcribe()`.

### Text-to-Speech

Po stronie OpenAI synteza mowy to `client.audio.speech.create()`. Aktualne modele to `gpt-4o-mini-tts` (najnowszy i jedyny, który rozumie parametr `instructions`) oraz starsze `tts-1` i `tts-1-hd`. Głosów wbudowanych jest trzynaście: `alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `onyx`, `nova`, `sage`, `shimmer`, `verse`, `marin` i `cedar`. Wejście to maksymalnie 4096 znaków, a wyjście jeden z formatów `mp3` (domyślny), `opus`, `aac`, `flac`, `wav` i `pcm` (stan na wrzesień 2026).

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

with client.audio.speech.with_streaming_response.create(
    model="gpt-4o-mini-tts",
    voice="marin",
    input="Twoja przesyłka czeka w punkcie odbioru przez trzy dni robocze.",
    instructions="Speak calmly and clearly, at a slightly slower pace, "
                 "like an automated parcel locker announcement.",
    response_format="wav",
    speed=0.95,
) as response:
    response.stream_to_file("notice.wav")

print("saved notice.wav")
```

`with_streaming_response` zapisuje audio na dysk w trakcie pobierania, zamiast trzymać cały plik w pamięci – przy dłuższych tekstach to różnica między płynnym odtwarzaniem a czekaniem. `instructions` jest tu najciekawszym parametrem: steruje akcentem, emocjami, intonacją, tempem i szeptem, czyli rzeczami, których wcześniej nie dało się ustawić inaczej niż zmianą głosu. Do odtwarzania w czasie rzeczywistym wybierz `wav` albo `pcm`, bo nie wymagają buforowania nagłówka.

Alternatyw jest sporo. Gemini ma własne modele TTS (`gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`) z trzydziestoma głosami o nazwach takich jak Kore, Puck czy Zephyr, obsługą dialogów wielogłosowych i wyjściem PCM 24 kHz; rozlicza je po tokenach audio, po 20 dolarów za milion na wariancie 3.1 flash. ElevenLabs jest komercyjnym standardem tam, gdzie liczy się klonowanie głosu i jakość aktorska. Z open source Piper działa w czasie rzeczywistym na Raspberry Pi i nadaje się do urządzeń offline, a Kokoro daje wyraźnie lepszą jakość przy modelu rzędu 80 milionów parametrów.

### Audio jako wejście modelu (Audio Processing)

Transkrypcja to niejedyny sposób użycia dźwięku. Modele multimodalne przyjmują audio bezpośrednio, co pozwala pytać o rzeczy, których w transkrypcie nie ma: ton rozmowy, długość przerw, dźwięki w tle, liczbę mówców, nakładanie się głosów. Gemini przyjmuje audio tym samym `interactions.create()`, którym przyjmuje obrazy – blok `{"type": "audio", "uri": ..., "mime_type": ...}` albo inline `data` z base64. Formatów jest kilkanaście (WAV, MP3, AAC, OGG, FLAC, M4A, Opus i inne), limit to 9,5 godziny na prompt, koszt 32 tokeny na sekundę, czyli 1920 tokenów na minutę; sygnał jest w obie strony sprowadzany do 16 kbps i jednego kanału, więc nie licz na analizę stereo. Po stronie OpenAI odpowiednikiem jest model `gpt-audio-1.5` w Chat Completions z `modalities=["text", "audio"]` i blokiem `input_audio`, a do rozmowy dwukierunkowej – Realtime API (stan na wrzesień 2026).

Na drugim końcu skali są małe modele klasyfikujące dźwięk. Pipeline `audio-classification` z biblioteki `transformers` rozpoznaje zdarzenia akustyczne (szczekanie, alarm, tłuczone szkło) albo emocje w głosie, a `zero-shot-audio-classification` pozwala podać własne etykiety bez trenowania. Model klasyfikujący uruchomiony na strumieniu i model duży wywoływany tylko wtedy, gdy klasyfikator coś wykryje, to typowa architektura systemu monitoringu – różnica w rachunku jest rzędu wielkości.

## Modele z Hugging Face (Hugging Face Models)

Wszystko powyżej wymaga klucza API i wysyła dane na zewnątrz. Biblioteka `transformers` daje te same zadania lokalnie, w cenie pobrania modelu. Interfejsem jest `pipeline()`, a nazwy zadań multimodalnych to dziś `image-classification`, `object-detection`, `image-segmentation`, `depth-estimation`, `zero-shot-image-classification`, `zero-shot-object-detection`, `image-text-to-text` (to następca dawnego `image-to-text`), `document-question-answering`, `automatic-speech-recognition`, `audio-classification`, `zero-shot-audio-classification` oraz `text-to-speech` (alias `text-to-audio`).

Najciekawszy z nich jest `zero-shot-image-classification`, oparty na CLIP. CLIP osadza obrazy i teksty w jednej przestrzeni wektorowej – dokładnie tej samej idei, którą poznałeś w rozdziale 6 przy embeddingach tekstu – więc klasyfikacja sprowadza się do policzenia podobieństwa obrazu do opisów podanych w locie. Nie trenujesz niczego, tylko zmieniasz listę stringów.

```python
from PIL import Image, ImageDraw
from transformers import pipeline

image = Image.new("RGB", (336, 336), "white")
draw = ImageDraw.Draw(image)
draw.ellipse((40, 40, 296, 296), outline="gray", width=6)
draw.pieslice((70, 90, 270, 250), start=20, end=160, fill="gold")
draw.pieslice((70, 50, 270, 230), start=20, end=160, fill="white")

classifier = pipeline("zero-shot-image-classification", model="openai/clip-vit-base-patch32")
labels = ["a banana on a plate", "a slice of pizza", "a car", "a handwritten note"]
for row in classifier(image, candidate_labels=labels):
    print(f"{row['score']:.3f}  {row['label']}")
```

Wynik uruchomienia na CPU:

```text
0.990  a banana on a plate
0.007  a car
0.002  a handwritten note
0.000  a slice of pizza
```

Obraz jest tu narysowany proceduralnie – dwa wycinki koła układające się w żółty półksiężyc na talerzu – a CLIP i tak przypisuje mu etykietę „a banana on a plate" z pewnością 0,99. Model `clip-vit-base-patch32` waży około 600 MB i liczy tę klasyfikację w ułamku sekundy na procesorze. Zwróć uwagę, że wyniki są rozkładem prawdopodobieństwa po podanych etykietach: jeśli wyślesz obraz, który nie pasuje do żadnej, dostaniesz mimo to sumę równą jedynce. Dodaj więc etykietę-śmietnik („something else", „a blank page") i traktuj niskie maksimum jako sygnał odrzucenia, bo sam ranking nigdy Ci tego nie powie.

## Frameworki: LangChain i LlamaIndex dla aplikacji multimodalnych

LangChain ujednolica bloki treści między dostawcami. Zamiast pamiętać, że Anthropic ma `source.type`, OpenAI `image_url`, a Gemini `data` i `mime_type`, składasz listę bloków w formacie LangChaina – `{"type": "image", "url": ...}` albo `{"type": "image", "base64": ..., "mime_type": ...}` – i framework tłumaczy je na kształt wymagany przez wybrany model. Analogicznie działają bloki `audio` i `file`, a pole `file_id` pozwala odwołać się do pliku przechowywanego po stronie dostawcy.

```python
import base64
import os
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage

with open("chart.png", "rb") as f:
    encoded = base64.standard_b64encode(f.read()).decode("ascii")

model = init_chat_model("claude-opus-5", max_tokens=1024)
message = HumanMessage(content=[
    {"type": "text", "text": "Read the values of the last three bars and return them as JSON."},
    {"type": "image", "base64": encoded, "mime_type": "image/png"},
])

print(model.invoke([message]).text)
```

Zysk jest realny wtedy, gdy przełączasz dostawców albo prowadzisz ewaluację tego samego promptu na kilku modelach: zmieniasz jeden string w `init_chat_model()` i reszta kodu zostaje. Koszt to warstwa abstrakcji, która zawsze odstaje o krok od najnowszych funkcji API – jeśli potrzebujesz `detail: "original"` albo świeżego parametru z zeszłego tygodnia, i tak schodzisz do SDK.

LlamaIndex celuje w inne miejsce: multimodalny RAG. Klasa `MultiModalVectorStoreIndex` trzyma dwa osobne indeksy – tekstowy na embeddingach tekstu i obrazowy na embeddingach CLIP – i wyszukuje w obu naraz, a wynik podaje modelowi multimodalnemu jako kontekst. Dzięki temu pytanie tekstowe może zwrócić pasujący obraz, a obraz zapytania pasujące akapity.

```python
import qdrant_client
from llama_index.core import SimpleDirectoryReader, StorageContext
from llama_index.core.indices import MultiModalVectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.multi_modal_llms.openai import OpenAIMultiModal

MODEL = "gpt-6-astra"  # check docs for the current model id

db = qdrant_client.QdrantClient(path="qdrant_mm_db")
storage_context = StorageContext.from_defaults(
    vector_store=QdrantVectorStore(client=db, collection_name="text_collection"),
    image_store=QdrantVectorStore(client=db, collection_name="image_collection"),
)

documents = SimpleDirectoryReader("./catalog/").load_data()
index = MultiModalVectorStoreIndex.from_documents(documents, storage_context=storage_context)

query_engine = index.as_query_engine(
    multi_modal_llm=OpenAIMultiModal(model=MODEL, max_new_tokens=512),
)
print(query_engine.query("Which lamp in the catalog has a fabric shade?"))
```

`SimpleDirectoryReader` sam rozpoznaje obrazy w katalogu i tworzy z nich dokumenty obrazowe, a `MultiModalVectorStoreIndex` kieruje je do `image_store` z domyślnym embeddingiem CLIP. Qdrant jest tu tym samym Qdrantem co w rozdziale 7, tylko z dwiema kolekcjami zamiast jednej.

Kiedy to się opłaca? Framework bierze się do multimodalnego RAG-a, gdzie ręczne złożenie dwóch indeksów, retrievera i promptu to kilkaset linii, które ktoś już napisał i przetestował. Bierze się go też przy ewaluacji wielu dostawców, bo ujednolicony format wiadomości oszczędza realną pracę. W pozostałych przypadkach – a to znaczy w większości aplikacji, które po prostu wysyłają obraz i oczekują struktury – SDK dostawcy jest krótsze, szybsze w debugowaniu i nie wymaga czekania na aktualizację warstwy pośredniej. Reguła jest ta sama co przy RAG-u w rozdziale 8: framework wtedy, gdy potrzebujesz jego składanych części, a nie wtedy, gdy potrzebujesz jednego wywołania.

## Podsumowanie

- Multimodalność to dodatkowy typ bloku w `content`, nie osobne API: `image`, `document`, `audio` i `video` jadą tym samym wywołaniem co tekst, z tym samym system promptem i tymi samymi narzędziami.
- Claude liczy obraz w łatkach 28 na 28 pikseli, czyli `⌈w/28⌉ × ⌈h/28⌉` tokenów, z sufitem 4784 tokenów na modelach od 4.7 wzwyż i 1568 na starszych; skalowanie obrazu przed wysłaniem jest najprostszą dźwignią kosztową.
- Obraz podawaj przez base64 przy jednorazowym wywołaniu, a przez Files API i `file_id` w rozmowach wieloturowych i u agentów, gdzie historia leci w całości przy każdej turze.
- PDF Claude obsługuje natywnie blokiem `document`, przetwarzając każdą stronę jako tekst i obraz naraz; to daje zrozumienie layoutu, ale kosztuje 1500–3000 tokenów tekstowych na stronę plus tokeny wizualne.
- DALL·E zniknęło z API 12 maja 2026; generowanie obrazów po stronie OpenAI to dziś `gpt-image-2.5-sunburst` i `gpt-image-2.5-flare` na `images.generate`, a po stronie Google modele Nano Banana (`gemini-3.1-flash-image` i pokrewne) wywoływane zwykłym `interactions.create()`.
- Każdy obraz z Gemini nosi znak wodny SynthID, którego nie da się wyłączyć; prawa do treści generowanych sprawdzaj w aktualnych warunkach dostawcy, a materiał syntetyczny oznaczaj.
- Wideo wchodzi do Gemini natywnie za około 100 tokenów na sekundę przy niskiej rozdzielczości mediów; tańszą i przenośną alternatywą jest próbkowanie klatek i wysłanie kilku z nich jako zwykłych obrazów z etykietami czasu.
- Transkrypcja to dziś `gpt-transcribe` (tekst), `gpt-4o-transcribe-diarize` (mówcy) i `whisper-1` (znaczniki słów i tłumaczenia), przy limicie 25 MB na plik; lokalnie `faster-whisper` z filtrem VAD daje porównywalną jakość bez wysyłania nagrań na zewnątrz.
- Synteza mowy to `audio.speech.create()` z `gpt-4o-mini-tts` i parametrem `instructions`, który steruje tonem, tempem i emocją; do strumieniowania na dysk używaj `with_streaming_response`.
- Lokalne pipeline'y Hugging Face (`zero-shot-image-classification` na CLIP, `audio-classification`) są o rzędy wielkości tańsze od modeli chmurowych i świetnie nadają się na pierwszy filtr przed wywołaniem dużego modelu.

## Co dalej

Rozdział 14 („Narzędzia AI do kodowania") zamyka książkę po drugiej stronie stołu: nie jak budować systemy na modelach, tylko jak używać modeli do budowania czegokolwiek – asystenci w edytorze, agenci w terminalu, przegląd kodu i generowanie testów. Zanim tam przejdziesz, zrób dwie rzeczy samodzielnie. Weź dziesięć zdjęć dokumentów, które masz pod ręką, przepuść je przez snippet z `messages.parse()` i policz z `usage.input_tokens`, ile realnie kosztuje jedno wywołanie – a potem powtórz to po przeskalowaniu zdjęć do 1568 pikseli na dłuższej krawędzi i porównaj obie liczby z jakością wyniku. Drugie ćwiczenie: uruchom pipeline CLIP na własnym zbiorze obrazów z etykietami-śmietnikami i sprawdź, przy jakim progu pewności da się bezpiecznie odrzucać obrazy, zanim trafią do płatnego modelu.

## Źródła

- https://platform.claude.com/docs/en/build-with-claude/vision
- https://platform.claude.com/docs/en/build-with-claude/pdf-support
- https://platform.claude.com/docs/en/build-with-claude/files
- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/guides/speech-to-text
- https://developers.openai.com/api/docs/guides/text-to-speech
- https://developers.openai.com/api/docs/guides/audio
- https://developers.openai.com/api/docs/api-reference/images/create
- https://developers.openai.com/api/docs/api-reference/audio/createSpeech
- https://developers.openai.com/api/docs/api-reference/audio/createTranscription
- https://developers.openai.com/api/docs/deprecations
- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/gemini-api/docs/video-understanding
- https://ai.google.dev/gemini-api/docs/audio
- https://ai.google.dev/gemini-api/docs/speech-generation
- https://ai.google.dev/gemini-api/docs/files
- https://ai.google.dev/gemini-api/docs/pricing
- https://huggingface.co/docs/transformers/main_classes/pipelines
- https://docs.langchain.com/oss/python/langchain/messages
- https://developers.llamaindex.ai/python/framework/module_guides/models/multi_modal/
