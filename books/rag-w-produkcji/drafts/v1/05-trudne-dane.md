# Rozdział 5. Trudne dane: PDF-y z układem, tabele i kod

> **Cel rozdziału:** odzyskać z PDF-a, tabeli i bloku kodu tę strukturę, bez której chunk jest nieczytelny i niecytowalny – i zmierzyć, ile to daje.
>
> **Kod:** `ragbook/pdf.py`, `ragbook/tables.py`, `ragbook/code_chunks.py`, `ragbook/value_check.py`, `experiments/05_pdf.py`, `05_tables.py`, `05_code.py`. **Pakiety poza fundamentem:** `pip install pymupdf`.

Dotąd korpus był wygodny: czternaście plików Markdown, w których nagłówek jest nagłówkiem, tabela ma pionowe kreski, a blok kodu trzy grawisy. W prawdziwym projekcie dostajesz to samo w formie, która tę strukturę ukrywa – PDF wygenerowany z tego samego źródła, eksport z Confluence, skan umowy. Tekst jest ten sam; znika informacja o tym, czym ten tekst jest.

To nie jest problem kosmetyczny. Chunk, który zaczyna się od „AI Engineer 73 bo fakt wpisany w wagi nie ma źródła", jest bezużyteczny w prompcie, bo model nie wie, o czym mówi ani z czego pochodzi. Chunk z wierszem tabeli bez nagłówka kolumny jest gorszy niż brak chunku, bo wygląda na odpowiedź. A metadane, których nie wydobyłeś przy indeksowaniu – numer rozdziału, tytuł sekcji, typ treści – to dokładnie te, na których w rozdziale 4 opierały się filtry i routing, a w rozdziale 6 będą się opierać cytowania.

Mamy tu komfort, którego rzadko się ma w praktyce: `build/ai-engineer.pdf` to 143 strony złożone z tych samych plików Markdown, które są naszym korpusem. Znamy więc prawdę o każdej stronie i możemy zmierzyć nie „czy ekstrakcja wygląda dobrze", tylko „ile recall traci system, który czyta PDF zamiast źródła". Snippety uruchamiasz z katalogu `code/`, jak w poprzednich rozdziałach. Pomiary idą na trzech własnych, małych zestawach (`data/golden_pdf.jsonl`, `golden_tables.jsonl`, `golden_code.jsonl`), bo baseline z rozdziału 1 mierzy co innego – jakość wyszukiwania na czystym Markdownie, nie jakość ekstrakcji.

## PDF, w którym układ niesie znaczenie

PDF nie jest formatem dokumentu, tylko formatem opisu strony: listą poleceń „narysuj ten ciąg glifów tą czcionką w tym miejscu". Nie ma w nim pojęcia akapitu, nagłówka ani komórki tabeli – są prostokąty z tekstem, które człowiek składa w strukturę, bo widzi rozmiar liter i odstępy. Cała robota ekstrakcji polega na odtworzeniu tego, co widzi człowiek, z tego, co zapisał generator. Zacznijmy od tego, co dostajesz za darmo; PyMuPDF instaluje się jako `pymupdf` i od wersji 1.24.3 tak też się go importuje (stare `import fitz` działa, ale od 1.27.1 ostrzega).

```python
import pymupdf

doc = pymupdf.open("../../../build/ai-engineer.pdf")
print("stron:", doc.page_count)
page = doc[72]                      # gdzieś w środku rozdziału 8
print(page.get_text()[:330])
```

```text
stron: 143
AI Engineer
73
bo fakt wpisany w wagi nie ma źródła, nie da się go zacytować, nie da się go usunąć na żądanie i dezaktualizuje się przy
następnej zmianie w danych.
Kryterium
RAG
Fine-tuning
Co zmienia
zawartość promptu
wagi modelu
Nadaje się do
faktów, dokumentów, danych zmiennych
stylu, formatu, zachowania, domenowego słownictw
```

Trzynaście linijek, cztery osobne problemy. Pierwsze dwie linie to żywa pagina i numer strony – wkleją się w środek zdania, bo dla PDF-a są zwykłym tekstem na stronie. Trzecia zaczyna się od małej litery: zdanie zaczęło się na poprzedniej stronie i `get_text()` nie ma jak tego wiedzieć. Dalej rozsypuje się tabela „RAG a fine-tuning" – każda komórka w osobnej linii, bez informacji, co jest nagłówkiem kolumny, a co wartością. I wreszcie każda linia layoutu kończy się znakiem nowej linii, więc dzielenie po `\n\n` nie da akapitów.

### Odzyskiwanie struktury z rozmiaru fontu

Informacja, której brakuje w `get_text("text")`, jest w `get_text("dict")`: blok ma `type` (0 to tekst, 1 obraz), linia ma `bbox` i listę `spans`, a każdy span niesie `text`, `font`, `size`, `flags`, `color` i własny `bbox`. To wystarczy, żeby odtworzyć role, które nadał generator.

```python
import collections
import pymupdf

doc = pymupdf.open("../../../build/ai-engineer.pdf")
sizes = collections.Counter()
for page in doc:
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:                      # 0 = text, 1 = image
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"].strip():
                    sizes[(round(span["size"], 2), span["font"])] += len(span["text"])

for (size, font), chars in sizes.most_common(8):
    print(f"{size:6.2f}  {font:22s} {chars:7d}")
```

```text
  8.05  NotoSerif-Regular       317211
  6.44  DejaVuSansMono          101915
  6.84  DejaVuSansMono           17991
  6.51  NotoSerif-Regular        12619
  6.90  NotoSans-Regular          9759
  6.44  DejaVuSansMono-Bold       7934
  7.28  NotoSerif-Regular         3848
  6.44  DejaVuSansMono-Oblique    3578
```

Ten histogram jest mapą dokumentu. Najliczniejsza para to proza. Wszystko w foncie monotypowym to kod, przy czym 6,44 to blok, a 6,84 to `kod w linii` – dwie różne role, rozróżnialne o czwarte miejsce po przecinku. Sans mniejszy od prozy (6,90) to komórki tabel, bo skład używa dla nich innej rodziny fontu. Wyżej w ogonie, którego tu nie widać, siedzą nagłówki: 12,26 NotoSans-Bold to `##`, 9,58 to `###`, 19,92 to tytuł rozdziału. Zasada praktyczna: nie wpisuj tych liczb na sztywno, tylko wyznacz rozmiar prozy jako dominantę i klasyfikuj względem niej.

```python
def classify(line, body_size):
    if line.size >= 1.9 * body_size:
        return "h1"
    if 1.35 * body_size <= line.size < 1.9 * body_size:
        return "h2"
    if 1.10 * body_size <= line.size < 1.35 * body_size:
        return "h3"
    if "Mono" in line.font and line.size < body_size:
        return "code"
    if "Sans" in line.font and line.size < body_size:
        return "table"
    return "body"
```

Klasyfikujemy linię, nie span, biorąc font i rozmiar spanu, który wnosi najwięcej znaków. Dzięki temu zdanie prozy z wtrąconym `identyfikatorem` zostaje prozą, a linia, w której wszystkie spany są monotypowe, zostaje kodem. To jeden z tych momentów, w których prosta heurystyka wygrywa z modelem: rozpoznanie roli linii jest w stu procentach deterministyczne, bo generator PDF-a sam ją zakodował w wyborze czcionki.

### Żywa pagina, stopka i akapit przecięty stroną

Nagłówek i stopkę można wyciąć geometrycznie – `get_text()` przyjmuje `clip`, więc jeden `pymupdf.Rect` z marginesem załatwia sprawę. Wadą jest sztywność: przy pierwszym dokumencie z innym marginesem odetniesz zdanie. Odporniejsze jest podejście statystyczne – tekst powtarzający się w górnym albo dolnym pasie na większości stron jest paginą z definicji. Numery stron są za każdym razem inne, więc przed zliczaniem zamieniamy cyfry na `#`.

```python
def running_lines(lines, page_count, band=0.08, page_height=841.92):
    counter = collections.Counter()
    for ln in lines:                       # ln.y0 = top of the line on its page
        if band * page_height < ln.y0 < (1 - band) * page_height:
            continue
        counter[re.sub(r"\d+", "#", ln.text.strip())] += 1
    return {pattern for pattern, n in counter.items() if n > page_count / 2}
```

Na naszym PDF-ie ta funkcja usuwa 437 z 8133 linii, czyli dokładnie dwie na stronę: „AI Engineer" i numer strony. Zostaje sklejanie akapitów. Skład jest justowany, więc każda linia akapitu poza ostatnią sięga prawego marginesu – i to jedyny sygnał, który przeżywa przejście na następną stronę. Reguła: akapit trwa, dopóki jego linie dochodzą do prawego marginesu, a linia krótsza go kończy. Przy okazji trzeba cofnąć dzielenie wyrazów, bo CSS składu ma `hyphens: auto`.

```python
from ragbook import pdf

lines = pdf.load_lines()                    # klasyfikacja + usunięcie paginy
els = pdf.elements(lines)                   # akapity, bloki kodu, tabele, nagłówki
para = next(e for e in els
            if e.kind == "para" and len(e.pages) > 1 and "wiedza idzie do RAG" in e.text)
print("strony:", para.pages)
print(para.text[300:520])
```

```text
strony: (71, 72)
 schematu nazw. Nie jest natomiast sensownym nośnikiem faktów, bo fakt wpisany w wagi nie ma
źródła, nie da się go zacytować, nie da się go usunąć na żądanie i dezaktualizuje się przy
następnej zmianie w danych.
```

Zdanie, które w surowej ekstrakcji było przecięte żywą paginą i numerem strony, wróciło w całości. W całym dokumencie takich akapitów jest siedemnaście – niedużo, ale każdy z nich to jeden chunk, który w surowej wersji zaczynałby się w połowie zdania. Po złożeniu elementów w sekcje (`pdf.clean_sections()`) dostajemy 131 sekcji, czyli dokładnie tyle, ile ma korpus Markdown, i wszystkie 131 kluczy `(rozdział, sekcja)` zgadzają się co do znaku.

### Ile to jest warte w liczbach

Zestaw `data/golden_pdf.jsonl` ma dwadzieścia pytań o fakty z całego tomu 1; pięć z nich celuje w zdania leżące dokładnie na granicy stron. Trafność liczymy jak zawsze po sekcjach. Cztery warianty dzielą chunker (stałe okno 128/32), model `intfloat/multilingual-e5-small` i Qdranta, a różnią się wyłącznie tym, skąd pochodzi tekst i skąd pochodzą nazwy sekcji.

| Wariant | Sekcje trafne/wszystkie | Chunki | recall@5 | recall@20 | mrr@5 | Pytania bez trafienia |
|---|---|---|---|---|---|---|
| Markdown (ground truth) | 131/131 | 1550 | 0,90 | 1,00 | 0,88 | 2 |
| PDF surowy, nagłówki zgadywane | 121/542 | 1864 | 0,35 | 0,35 | 0,29 | 13 |
| PDF surowy, nagłówki podpowiedziane | 131/132 | 1634 | 0,95 | 1,00 | 0,84 | 1 |
| PDF oczyszczony | 131/131 | 1498 | 0,95 | 1,00 | 0,80 | 1 |

Skrypt: `experiments/05_pdf.py`.

Wynik zaprzecza intuicji. Porównaj wiersz pierwszy z trzecim: surowy tekst z PDF-a, z paginami wklejonymi w zdania i akapitami pociętymi na granicach stron, wyszukuje się **tak samo dobrze** jak czysty Markdown. Wyszukiwanie gęste na oknie 128 tokenów jest odporne na kilka wtrąconych śmieci, bo wektor liczy się z całości fragmentu; różnica 0,05 przy dwudziestu pytaniach to jedno pytanie i mieści się w szumie. Tak samo czytaj niższy MRR w wierszu czwartym – sklejanie akapitów przesuwa granice okien, więc trafny fragment czasem ląduje o pozycję niżej.

Cała gra toczy się o wiersz drugi, bo to jedyny uczciwy wariant surowy: bez informacji o foncie nie wiesz, która linia jest nagłówkiem, więc piszesz heurystykę „krótka linia, która nie jest zdaniem". Ta heurystyka znajduje 542 „sekcje" tam, gdzie jest ich 131, kroi korpus na fragmenty o medianie 23 słów i etykietuje chunki napisami `}`, `<source> i` albo – najlepsza – `AI Engineer`, bo żywa pagina też jest krótką linią, która nie jest zdaniem. Recall@5 spada z 0,90 do 0,35, a trzynaście z dwudziestu pytań nie ma ani jednego trafienia. Wiersz trzeci różni się od drugiego wyłącznie tym, że podpowiedzieliśmy listę prawdziwych nagłówków – czego w prawdziwym projekcie nikt Ci nie poda.

Wniosek jest odwrotny do oczekiwanego. Z PDF-a nie odzyskujesz przede wszystkim **tekstu**, bo ten wychodzi zaskakująco dobrze sam. Odzyskujesz **metadane**: numer rozdziału, tytuł sekcji, typ fragmentu. Bez nich nie masz czym filtrować, nie masz co pokazać w cytowaniu i nie masz nawet jak zbudować zestawu ewaluacyjnego, bo nie da się wskazać trafnej sekcji.

Jedna rzecz nie naprawia się sama. Te same dwadzieścia pytań, zadane o wartości z tabel (zestaw `golden_tables.jsonl`), wygląda tak:

| Wariant | recall@5 | mrr@5 | Pytania bez trafienia |
|---|---|---|---|
| Markdown (ground truth) | 0,92 | 0,78 | 1 |
| PDF surowy, nagłówki zgadywane | 0,23 | 0,12 | 10 |
| PDF surowy, nagłówki podpowiedziane | 0,85 | 0,69 | 2 |
| PDF oczyszczony | 0,85 | 0,65 | 2 |

Skrypt: `experiments/05_pdf.py`.

Oczyszczanie oparte na foncie rozpoznaje, że linia jest komórką tabeli, ale nie odtwarza wierszy i kolumn – dostajesz pionowy ciąg komórek. Do tego służy osobne narzędzie: `Page.find_tables()`, dodane w PyMuPDF 1.23.0, zwraca `TableFinder` z listą `tables`, a każda tabela ma `extract()`, `to_pandas()` i `to_markdown()`. Działa geometrycznie (strategie po liniach i po tekście, jak w pdfplumberze, z którego to API jest wzorowane), więc na tabeli z widocznymi kreskami jest niezawodne, a bez obramowania bywa kapryśne. Układ praktyczny: najpierw `find_tables(clip=...)`, potem wytnij znalezione prostokąty z przetwarzania tekstowego, żeby nie zaindeksować tej samej tabeli dwa razy.

### Kolejność czytania i dwie szpalty

Nasz PDF jest jednołamowy, więc kolejność czytania jest tu problemem teoretycznym – w pracach naukowych i w starszym składzie to problem numer jeden. `get_text()` zwraca tekst w kolejności, w jakiej polecenia rysowania trafiły do pliku, co przy dwóch szpaltach potrafi znaczyć „najpierw cała lewa, potem cała prawa", ale równie dobrze „na przemian, linia po linii". Dokumentacja mówi wprost: „The output may not equal an accustomed natural reading order".

Argument `sort=True` porządkuje wynik od lewego górnego rogu do prawego dolnego. Naprawia to dokumenty z pomieszaną kolejnością rysowania, ale **nie naprawia dwułamowości** – przeciwnie, sortowanie po współrzędnej pionowej przeplata szpalty linia po linii i miesza zdania z obu. Poprawne rozwiązanie wymaga najpierw wykrycia kolumn, potem czytania każdej z osobna. Projekt PyMuPDF udostępnia do tego skrypt `multi_column.py` w repozytorium PyMuPDF-Utilities; jego `column_boxes(page)` zwraca prostokąty kolumn ułożone już w kolejności czytania, więc wystarczy pętla po nich z `clip=`. Alternatywą jest `pymupdf4llm`, osobny pakiet tego samego projektu, który deklaruje obsługę układów wielokolumnowych i od razu oddaje Markdown. Zanim napiszesz jakikolwiek chunker, wypisz surowy tekst trzech losowych stron i przeczytaj go: jeśli zdania się nie kleją, żadna strategia cięcia tego nie uratuje.

## Tabele: najmniejszy sensowny chunk to wiersz

W korpusie jest czternaście tabel Markdown o łącznie 84 wierszach – porównanie RAG i fine-tuningu w rozdziale 8, przegląd baz wektorowych w 7, modele w 5 i 6, narzędzia obserwowalności w 12. To niewiele tekstu, ale gęstość faktów na token jest w nich najwyższa w całej książce. Zacznijmy od tego, co robi z tabelą stałe okno: sekcja „RAG a fine-tuning" ma 290 słów prozy i tabelę o dziewięciu wierszach, a okno 128/32 kroi ją na sześć chunków:

```text
'To pytanie pada przy każdym projekcie i ma prostą odpowiedź, którą warto zapamiętać przed tabelą: **wiedza idz'
'fakt wpisany w wagi nie ma źródła, nie da się go zacytować, nie da się go usunąć na żądanie i dezaktualizuje s'
'| stylu, formatu, zachowania, domenowego słownictwa | | Świeżość danych | natychmiastowa (reindeksacja dokumen'
'ka za token modelu własnego | | Cytowalność | naturalna, fragment ma źródło | brak, model nie wie, skąd wie | '
'wersji | godziny | dni do tygodni | Kombinacja obu jest sensowna i wcale nie rzadka. Typowy układ: RAG dostarc'
'engineering, potem RAG, a fine-tuning na końcu i tylko wtedy, gdy masz już ewaluację, która pokaże, że coś na '
```

Widać dwie wady. Wiersz „Koszt bieżący" został przecięty w połowie – początek w trzecim chunku, koniec w czwartym. Ważniejsze, że żaden chunk poza pierwszym nie ma wiersza nagłówkowego, więc w indeksie leży komórka „natychmiastowa (reindeksacja dokumentu)", przy której nie stoi ani „Świeżość danych", ani „RAG". Model, który dostanie taki fragment, ma pełne prawo przypisać tę wartość do fine-tuningu.

Lekarstwo: wyjąć tabelę z prozy i zaindeksować osobno, w postaci, która sama się tłumaczy. `ragbook/tables.py` parsuje tabele Markdown i serializuje je na trzy sposoby.

```python
from ragbook.corpus import load_sections
from ragbook.tables import find_tables, table_as_chunk, table_rows, table_sentences

tables = find_tables(load_sections())
print(f"tabel: {len(tables)}, wierszy: {sum(len(t.rows) for t in tables)}")

t = next(t for t in tables if t.section == "RAG a fine-tuning")
print(table_rows(t)[2])
print(table_sentences(t)[2])
```

```text
tabel: 14, wierszy: 84
RAG: generowanie wspomagane wyszukiwaniem / RAG a fine-tuning
Kryterium: Świeżość danych; RAG: natychmiastowa (reindeksacja dokumentu); Fine-tuning: wymaga ponownego treningu
RAG: generowanie wspomagane wyszukiwaniem / RAG a fine-tuning
Dla pozycji „Świeżość danych” (Kryterium): RAG to natychmiastowa (reindeksacja dokumentu), a Fine-tuning to wymaga ponownego treningu.
```

Każdy wariant zaczyna się od nagłówka kontekstowego „tytuł rozdziału / sekcja", bo chunk wyjęty z tabeli traci otoczenie jeszcze bardziej niż chunk prozy; `table_as_chunk` dokleja dodatkowo akapit poprzedzający tabelę, który prawie zawsze jest jej podpisem w przebraniu. Wariant wierszowy powtarza nazwy kolumn przy każdej wartości – redundancja jest tu celem, nie wadą.

Pomiar idzie na trzynastu pytaniach o konkretne wartości (`data/golden_tables.jsonl`), z jednym dodatkiem. Trafność po sekcjach jest dla tabel zbyt łagodna: chunk może należeć do właściwej sekcji i nie zawierać wiersza, o który pytamy. Dlatego każde pytanie ma pole `value` z wartością, która musi dosłownie wystąpić w którymś z pięciu zwróconych chunków (`ragbook/value_check.py`).

| Wariant | Chunki | recall@5 | mrr@5 | Wartość w top-5 | Pytania bez trafienia |
|---|---|---|---|---|---|
| stałe okno (baseline) | 1550 | 0,92 | 0,78 | 0,69 | 1 |
| tabela jako jeden chunk | 1509 | 0,92 | 0,64 | 0,62 | 1 |
| wiersz po wierszu | 1579 | 1,00 | 0,85 | 0,85 | 0 |
| wiersz jako zdanie | 1579 | 1,00 | 0,80 | 0,85 | 0 |

Skrypt: `experiments/05_tables.py`.

Tabela w całości jako jeden chunk wypada **gorzej** niż baseline i warto zrozumieć dlaczego. Przegląd baz wektorowych z rozdziału 7 to siedem kolumn i osiem wierszy o zupełnie różnych tematach; jeden wektor na taki tekst jest średnią ze wszystkiego, czyli punktem, który nie leży blisko żadnego konkretnego pytania. To ta sama pułapka, którą rozdział 2 opisywał przy zbyt dużych chunkach, tylko w skrajnej postaci. Dochodzi do tego obcięcie: trzy z czternastu tabel przekraczają w tej postaci limit 512 tokenów modelu e5 (przegląd narzędzi z rozdziału 14 ma ich 1173), więc lądują w indeksie w połowie, bez żadnego ostrzeżenia.

Wiersz po wierszu wygrywa wyraźnie: wszystkie trzynaście pytań ma trafienie, a wartość wraca w top-5 dla jedenastu zamiast dla dziewięciu. Wariant zdaniowy ma tę samą trafność, ale gorszy MRR – parafraza nic nie dodaje, a rozcieńcza dopasowanie leksykalne. **Decyzja: tabele wyjmujemy z prozy i indeksujemy wiersz po wierszu, z powtórzonym nagłówkiem kolumn i kontekstem sekcji.** Koszt to 84 dodatkowe chunki, poniżej dwóch procent indeksu.

Dwa pytania nie trafiają w wartość w żadnym wariancie: pytanie o cenę `claude-opus-5` konkuruje z kilkunastoma innymi fragmentami o cenach, a pytanie o metryki agentów – z bardzo długą sekcją „Ewaluacje". To nie problem serializacji, tylko rankingu; wraca w rozdziale 3.

## Kod w dokumentacji: blok jest jednostką, nie oknem

Korpus zawiera 156 bloków kodu o medianie 238 tokenów i maksimum 668; 123 z nich są dłuższe niż okno 128 tokenów, czyli w baseline większość snippetów jest pocięta. Wygląda to tak:

```text
blok z Obserwowalność (456 tokenów) -> 5 chunków w stałym oknie
'```python from opentelemetry import trace from opentelemetry.sdk.trace import TracerProvid'
'_provider(provider) tracer = trace.get_tracer("acme.support-bot") def fake_model_call(prom'
'tokens": 37} with tracer.start_as_current_span("chat claude-opus-5") as span: span.set_att'
'") span.set_attribute("gen_ai.conversation.id", "conv-8123") result = fake_model_call("Wha'
']) span.set_attribute("gen_ai.usage.output_tokens", result["output_tokens"]) span.set_attr'
```

Pięć chunków, z których żaden nie jest kompletnym programem, a drugi zaczyna się od `_provider(provider)`, czyli od końca identyfikatora przeciętego w środku. Do promptu taki fragment nadaje się wyłącznie jako materiał na halucynację. Naprawa nie wymaga niczego poza parsowaniem grawisów: blok kodu trzymamy w całości jako jeden chunk, a prozę tniemy jak dotąd.

```python
from ragbook.code_chunks import code_aware_chunks, code_stats
from ragbook.corpus import load_sections
from ragbook.embed import Embedder

sections = load_sections()
tok = Embedder().tokenizer
print(code_stats(sections, tok))

chunks = code_aware_chunks(sections, tok, window=128, overlap=32, attach_lead=True)
code = [c for c in chunks if c.meta.get("kind") == "code"]
print("chunków razem:", len(chunks), "w tym kodu:", len(code))
print(code[0].text[:110])
```

```text
{'blocks': 156, 'median_tokens': 238, 'max_tokens': 668, 'over_128': 123}
chunków razem: 1299 w tym kodu: 161
I tu zaczyna się problem języka polskiego. Korpusy treningowe, na których uczono tokenizery, są zdominowane
```

Wypisany początek pierwszego chunku kodu nie jest kodem, tylko akapitem, który go zapowiada – i o to chodzi w parametrze `attach_lead`. Sam blok kodu jest kiepskim materiałem na embedding: składa się z nazw funkcji, nawiasów i stringów, a pytanie użytkownika jest zdaniem po polsku. Dlatego doklejamy do niego akapit, w którym autor napisał ludzkimi słowami, co ten kod robi. Bloki dłuższe niż 512 tokenów (limit e5) dzielimy po pustych liniach, powtarzając ten akapit na początku każdej części.

Pomiar idzie na dziesięciu pytaniach o identyfikatory występujące w korpusie **wyłącznie wewnątrz bloków kodu** – `create_payload_index`, `start_as_current_span`, `output_dimensionality` i podobne. Obok trafności po sekcjach sprawdzamy, czy identyfikator dosłownie pojawił się w top-5, oraz – jako kontrola – czy zmiana nie zepsuła pytań o prozę.

| Wariant | Chunki | recall@5 | mrr@5 | Identyfikator w top-5 | Pytania bez trafienia | recall@5 na pytaniach o prozę |
|---|---|---|---|---|---|---|
| stałe okno (baseline) | 1550 | 0,90 | 0,63 | 0,40 | 1 | 0,90 |
| blok kodu w całości | 1299 | 1,00 | 0,67 | 0,30 | 0 | 0,90 |
| blok kodu + poprzedzający akapit | 1299 | 1,00 | 0,68 | 0,70 | 0 | 0,90 |

Skrypt: `experiments/05_code.py`.

Środkowy wiersz to najciekawsza część tego pomiaru. Trzymanie bloku w całości podnosi trafność po sekcjach do jedności, ale jednocześnie **obniża** udział identyfikatorów w top-5 z 0,40 do 0,30. Powód jest ten sam co przy tabeli jako jednym chunku: 250-tokenowy blok kodu embeduje się w rozmytą średnią, więc trafia do sekcji, ale przegrywa z prozą o tej samej tematyce. Dopiero doklejenie akapitu wprowadzającego daje 0,70 – bo teraz chunk ma i zdanie po polsku, po którym da się go znaleźć, i kod, który jest odpowiedzią. Liczba chunków spada przy tym z 1550 do 1299, czyli indeks jest o szesnaście procent mniejszy.

Zwróć jednak uwagę, gdzie ta droga się kończy. Nawet w najlepszym wariancie trzy pytania na dziesięć nie dostają szukanego identyfikatora w pięciu zwróconych fragmentach, a MRR wynosi 0,68 przy 0,88 na pytaniach o prozę. To nie wina chunkera: `query_points`, `max_seq_length` czy `output_config` to ciągi, które model embeddingowy widzi jako kilka mało znaczących podsłów, a wielojęzyczny e5 o 384 wymiarach nie ma czym odróżnić nazwy metody od innej nazwy metody. Takie zapytania wygrywa wyszukiwanie leksykalne i zbuduje je rozdział 3. Zapamiętaj tylko, że chunker trzymający blok kodu w całości jest warunkiem wstępnym – hybryda nie pomoże, jeśli identyfikator jest przecięty na pół.

## Obrazy i diagramy w PDF-ie

Nasz PDF nie ma ani jednego obrazu rastrowego (`page.get_images()` zwraca puste listy na wszystkich 143 stronach), bo diagramy w tomie 1 są rysowane znakami w blokach kodu. W prawdziwej dokumentacji jest inaczej i obowiązuje zasada: obraz, którego nie opiszesz tekstem, nie istnieje dla wyszukiwania. Potok wygląda tak – wykryj obrazy (`page.get_images(full=True)`) albo wyrenderuj obszar strony do PNG (`page.get_pixmap(dpi=150, clip=rect).tobytes("png")`), poproś model multimodalny o opis, a opis zaindeksuj jako zwykły chunk z metadanymi wskazującymi stronę. Kształt wywołania jest ten z tomu 1, rozdział 13: blok `image` ze źródłem `base64`, `media_type` i `data`, ułożony **przed** blokiem tekstowym, bo dokumentacja Anthropic zaleca kolejność obraz-potem-tekst (stan na wrzesień 2026).

```python
import base64, os, anthropic, pymupdf

page = pymupdf.open("../../../build/ai-engineer.pdf")[72]
png = page.get_pixmap(dpi=150, clip=pymupdf.Rect(57, 62, 540, 300)).tobytes("png")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
message = client.messages.create(
    model="claude-opus-5",
    max_tokens=512,
    system="Opisz diagram jako tekst do wyszukiwania. Wymień wszystkie etykiety dosłownie.",
    messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.standard_b64encode(png).decode("ascii")}},
        {"type": "text", "text": "Strona 73, rozdział 8. Opisz w 3-4 zdaniach po polsku."},
    ]}],
)
print(next(b.text for b in message.content if b.type == "text"))
```

Przykładowy wynik:

```text
Tabela porównawcza „RAG a fine-tuning" o trzech kolumnach: Kryterium, RAG,
Fine-tuning. Wiersze: Co zmienia, Nadaje się do, Świeżość danych, Koszt
wejścia, Cytowalność, Usunięcie danych. Świeżość danych to dla RAG-u
reindeksacja dokumentu, a dla fine-tuningu ponowny trening.
```

Dwie uwagi do wdrożenia. W prompcie żądaj dosłownego wymienienia etykiet – opis „diagram architektury systemu" jest w wyszukiwaniu bezużyteczny, lista nazw komponentów już nie. I pamiętaj, że opis obrazu jest treścią wygenerowaną przez model: oznacz go w metadanych jako pochodny, żeby przy cytowaniu nie udawał tekstu z dokumentu.

## Gotowe parsery: kiedy nie pisać własnego

Sto linijek z `ragbook/pdf.py` wystarczyło, bo nasz PDF jest born-digital, jednołamowy i wygenerowany przez znany nam skład. Przy tysiącu PDF-ów z pięciu źródeł ta droga kończy się szybko. Poniżej narzędzia, które warto znać, zweryfikowane w ich oficjalnej dokumentacji (stan na wrzesień 2026).

| Narzędzie | Licencja | Tryb | Wyjście | Tabele | OCR | Ciężar |
|---|---|---|---|---|---|---|
| pdfplumber | MIT | lokalnie | obiekty Pythona, tekst | `extract_tables()`, geometria linii i tekstu | brak | znikomy |
| PyMuPDF | AGPL v3 lub komercyjna | lokalnie | tekst, dict, HTML, XML | `find_tables()`, geometria | brak (w rdzeniu) | mały |
| Docling | MIT | lokalnie | Markdown, HTML, JSON | model TableFormer (`FAST`/`ACCURATE`) | tak (EasyOCR, Tesseract, RapidOCR) | modele lokalne |
| unstructured | Apache 2.0 (OSS) + SaaS | lokalnie i chmura | lista elementów, JSON | `infer_table_structure=True`, HTML w `text_as_html` | tak (Tesseract) | duży w `hi_res` |
| marker | kod Apache 2.0, wagi OpenRAIL-M | lokalnie | Markdown, JSON, HTML | modelowo (Surya), `--use_llm` | tak (Surya) | GPU zalecane |
| LlamaParse | usługa komercyjna | chmura | Markdown, tekst, JSON | modele generatywne, tiery jakości | tak, layout-aware | brak (SaaS) |

**pdfplumber** to najlżejszy wybór i najlepszy do tabel z widocznymi liniami. Jest nadbudową nad `pdfminer.six`, daje dostęp do znaków z fontem i pozycją, a `extract_tables()` ma kilkanaście ustawień strategii (`lines`, `lines_strict`, `text`, `explicit`) i żadnego modelu w środku. Nie obsługuje skanów – README mówi to wprost.

**PyMuPDF** jest szybszy i bogatszy (HTML, XML, obrazy, `find_tables()` wzorowane na pdfplumberze), ale ma haczyk licencyjny: AGPL v3 albo licencja komercyjna od Artifexu – decyzja do podjęcia świadomie, a nie przy `pip install`. Dodatek `pymupdf4llm` daje Markdown jednym wywołaniem i deklaruje obsługę układów wielokolumnowych.

**Docling** to dziś domyślny wybór, gdy potrzebujesz jakości bez wysyłania dokumentów na zewnątrz. Jest na MIT, działa lokalnie (README podkreśla środowiska odcięte od sieci), przyjmuje PDF, DOCX, PPTX, XLSX, HTML i obrazy, a strukturę tabel rozpoznaje modelem TableFormer w dwóch trybach dokładności. Cena: ściąga modele layoutu, więc pierwsze uruchomienie waży setki megabajtów.

**unstructured** wygrywa liczbą formatów (ponad sześćdziesiąt) i modelem elementów – `Title`, `NarrativeText`, `Table` – który wprost odpowiada temu, co odtwarzaliśmy tu z rozmiarów fontu. Warto jednak przeczytać, co dokumentacja OSS pisze o sobie sama: biblioteka open source jest przeznaczona do prototypowania, nie do produkcji, i nie wspiera GPU. Produkcyjna jest płatna platforma.

**marker** daje najlepszą jakość spośród lokalnych, ale wymaga GPU do trybu zrównoważonego i ma niestandardową licencję na wagi – OpenRAIL-M, darmową dla badań i firm poniżej pięciu milionów dolarów przychodu. **LlamaParse** to usługa chmurowa rozliczana w kredytach za stronę (od jednego kredytu w trybie Fast do 45 w Agentic Plus, przy 1,25 USD za tysiąc kredytów); ma sens tam, gdzie dokumenty są zróżnicowane i trudne, a wysyłka na zewnątrz dopuszczalna.

Reguła wyboru jest krótka. Jeden znany szablon dokumentu – własny kod na PyMuPDF albo pdfplumberze. Wiele źródeł, dużo tabel, dane zostają u Ciebie – Docling. Dużo formatów innych niż PDF – unstructured. Skany i dokumenty, których nie umiesz opanować – usługa, i zmierz, czy jest warta rachunku.

## Podsumowanie

- PDF zapisuje wygląd, nie strukturę – ale generator zostawia ją w rozmiarze i rodzinie fontu, a `get_text("dict")` oddaje je w polach `size`, `font` i `bbox`. Klasyfikuj linie względem dominującego rozmiaru prozy, nie po stałych progach.
- Sam tekst z PDF-a wyszukuje się prawie tak dobrze jak źródło (recall@5 0,95 wobec 0,90). Traci się **metadane**: heurystyczne zgadywanie nagłówków zbija recall@5 do 0,35 i zostawia 13 z 20 pytań bez trafienia.
- Żywą paginę wykrywaj statystycznie (powtarzalny tekst w pasie 8 procent wysokości strony), a nie sztywnym `clip`. Akapit przez granicę stron sklejaj po tym, że jego linie sięgają prawego marginesu.
- `sort=True` porządkuje dokumenty z pomieszaną kolejnością rysowania, ale nie rozwiązuje dwułamowości – do tego trzeba najpierw wykryć kolumny (`multi_column.py` albo `pymupdf4llm`).
- Tabelę indeksuj wiersz po wierszu, z powtórzonym nagłówkiem kolumn i nazwą sekcji: recall@5 rośnie z 0,92 do 1,00, a udział poprawnej wartości w top-5 z 0,69 do 0,85. Tabela jako jeden chunk wypada gorzej niż stałe okno.
- Blok kodu trzymaj w całości i doklejaj do niego poprzedzający akapit prozy. Sam blok bez akapitu obniża trafność identyfikatorów (0,40 → 0,30); z akapitem podnosi ją do 0,70.
- Wyszukiwanie gęste zostaje słabe na identyfikatorach nawet przy dobrym chunkingu. To zadanie dla hybrydy z rozdziału 3, nie dla kolejnej strategii cięcia.

## Co dalej

Wiemy już, jak zamienić trudny dokument w chunki, które da się przeczytać i zacytować. Rozdział 6 bierze te chunki i pyta, co model z nimi robi: jak zbudować prompt, który nie pozwala wyjść poza kontekst, jak wymusić cytowanie z dokładnością do fragmentu, jak wykryć odpowiedź bez podstawy i jak zmierzyć wierność sędzią LLM. Zanim tam przejdziesz, podmień ścieżkę w `ragbook/pdf.py` na własny PDF i wypisz sto losowych linii z ich klasyfikacją. Jeśli progi 1,10 i 1,35 razy rozmiar prozy nie trafiają w Twoje nagłówki, masz histogram z drugiego snippetu i pięć minut roboty.

## Źródła

- PyMuPDF: https://pymupdf.readthedocs.io/en/latest/ – strony `page`, `textpage`, `app1`, `recipes-text`, `changes`, `pymupdf4llm`
- https://github.com/pymupdf/PyMuPDF-Utilities/blob/master/text-extraction/multi_column.py
- https://github.com/jsvine/pdfplumber, https://github.com/datalab-to/marker
- https://docling-project.github.io/docling/ oraz .../usage/advanced_options/
- https://docs.unstructured.io/open-source/introduction/overview oraz .../core-functionality/partitioning
- https://developers.llamaindex.ai/llamaparse/parse/ oraz .../general/pricing/
- https://platform.claude.com/docs/en/build-with-claude/vision
- https://huggingface.co/intfloat/multilingual-e5-small
