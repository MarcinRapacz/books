# Rozdział 5. Trudne dane: PDF-y z układem, tabele i kod

> **Cel rozdziału:** odzyskać z PDF-a, tabeli i bloku kodu tę strukturę, bez której chunk jest nieczytelny i niecytowalny – i zmierzyć, ile to daje.
>
> **Kod:** `ragbook/pdf.py`, `ragbook/tables.py`, `ragbook/code_chunks.py`, `ragbook/value_check.py`, `experiments/05_pdf.py`, `05_tables.py`, `05_code.py`. **Pakiety poza fundamentem:** `pip install pymupdf`.

Dotąd korpus był wygodny: czternaście plików Markdown, w których nagłówek jest nagłówkiem, tabela ma pionowe kreski, a blok kodu trzy grawisy. W prawdziwym projekcie dostajesz to samo w formie, która tę strukturę ukrywa – PDF wygenerowany z tego samego źródła, eksport z Confluence, skan umowy. Tekst jest ten sam. Znika informacja o tym, czym ten tekst jest.

Zobacz, jak to wygląda z bliska. Otwierasz PDF-a złożonego z naszego korpusu i wypisujesz tekst jednej strony ze środka rozdziału o RAG-u. PyMuPDF instaluje się jako `pymupdf` i od wersji 1.24.3 tak też się go importuje (stare `import fitz` działa, ale od 1.27.1 ostrzega).

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

Cztery usterki w kilkunastu linijkach. Pierwsze dwie linie to żywa pagina i numer strony – wkleją się w środek zdania, bo dla PDF-a są zwykłym tekstem na stronie. Trzecia zaczyna się od małej litery, bo zdanie zaczęło się na poprzedniej stronie i `get_text()` nie ma jak tego wiedzieć. Dalej rozsypuje się tabela „RAG a fine-tuning”: każda komórka w osobnej linii, bez informacji, co jest nagłówkiem kolumny, a co wartością. I każda linia layoutu kończy się znakiem nowej linii, więc dzielenie po `\n\n` nie da akapitów.

To nie jest problem kosmetyczny. Chunk zaczynający się od „AI Engineer 73 bo fakt wpisany w wagi nie ma źródła” jest w prompcie bezużyteczny, bo model nie wie, o czym mówi ani skąd to ma. Chunk z wierszem tabeli bez nagłówka kolumny jest gorszy niż brak chunku, bo wygląda na odpowiedź. A metadanych, których przy indeksowaniu nie wydobyłeś – numer rozdziału, tytuł sekcji, typ treści – potrzebują filtry z rozdziału 4 i cytowania z rozdziału 6.

Mamy tu komfort, którego rzadko się ma w praktyce: `build/ai-engineer.pdf` to 143 strony złożone z tych samych plików Markdown, które są naszym korpusem. Znamy prawdę o każdej stronie, więc zmierzymy nie „czy ekstrakcja wygląda dobrze”, tylko „ile recall traci system, który czyta PDF zamiast źródła”. Trzy sekcje, trzy trudne formaty: PDF, tabela, blok kodu. Snippety uruchamiasz z katalogu `code/`, a pomiary idą na trzech małych, własnych zestawach (`data/golden_pdf.jsonl`, `golden_tables.jsonl`, `golden_code.jsonl`), bo baseline z rozdziału 1 mierzy jakość wyszukiwania, nie jakość ekstrakcji.

## PDF, w którym układ niesie znaczenie

PDF nie jest formatem dokumentu, tylko formatem opisu strony: listą poleceń „narysuj ten ciąg glifów tą czcionką w tym miejscu”. Nie ma w nim pojęcia akapitu, nagłówka ani komórki tabeli. Są prostokąty z tekstem, które człowiek składa w strukturę, bo widzi rozmiar liter i odstępy. I to jest dobra wiadomość: skoro generator zapisał strukturę w wyglądzie, da się ją z wyglądu odczytać z powrotem.

Informacja, której brakuje w `get_text("text")`, siedzi w `get_text("dict")`: linia ma `bbox` i listę spanów, a każdy span niesie `text`, `font`, `size` i własny `bbox`. Policz, ile znaków przypada na każdą parę (rozmiar, font), a dostaniesz mapę dokumentu. W naszym PDF-ie prozy jest najwięcej i ma 8,05 punktu w NotoSerif-Regular; wszystko w foncie monotypowym to kod, przy czym blok i `kod w linii` różnią się rozmiarem o czwarte miejsce po przecinku. Font bezszeryfowy mniejszy od prozy to komórki tabel, a nagłówki siedzą w ogonie rozkładu, powyżej rozmiaru prozy.

Progów nie wpisuj na sztywno – wyznacz rozmiar prozy jako dominantę i klasyfikuj wszystko względem niej.

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

Klasyfikujemy linię, nie span, biorąc font i rozmiar tego spanu, który wnosi najwięcej znaków – dzięki temu zdanie prozy z wtrąconym `identyfikatorem` zostaje prozą. To jeden z tych momentów, w których prosta heurystyka wygrywa z modelem: rola linii jest rozpoznawalna deterministycznie, bo generator PDF-a sam ją zakodował w wyborze czcionki.

Zostają dwie usterki z pierwszego zrzutu. Żywą paginę najbezpieczniej wykrywać statystycznie: tekst, który na większości stron powtarza się w pasie u góry albo u dołu, jest paginą z definicji – wystarczy przed zliczaniem zamienić cyfry na `#`, bo numery stron są za każdym razem inne. Wycięcie stałym `clip` też działa, ale przy pierwszym dokumencie o innym marginesie odetnie zdanie. U nas reguła statystyczna usuwa dokładnie dwie linie na stronę: „AI Engineer” i numer strony.

Akapit przecięty granicą stron skleja się po justowaniu. Każda linia akapitu poza ostatnią sięga prawego marginesu i to jedyny sygnał, który przeżywa przejście na następną stronę: akapit trwa, dopóki linie dochodzą do marginesu, a linia krótsza go kończy. Przy okazji trzeba cofnąć dzielenie wyrazów. Takich rozdzielonych akapitów jest w dokumencie siedemnaście, a każdy z nich to jeden chunk, który w surowej wersji zaczynałby się w połowie zdania – jak ten o fakcie wpisanym w wagi.

Obie reguły razem z klasyfikacją linii mieszczą się w `ragbook/pdf.py`; tam zajrzyj po progi i szerokości pasów. Efekt: `pdf.clean_sections()` zwraca 131 sekcji, dokładnie tyle, ile ma korpus Markdown, a wszystkie 131 kluczy `(rozdział, sekcja)` zgadza się co do znaku.

### Ile to jest warte w liczbach

Zestaw `data/golden_pdf.jsonl` ma dwadzieścia pytań o fakty z całego tomu 1, w tym pięć o zdania leżące dokładnie na granicy stron. Warianty dzielą chunker (stałe okno 128/32), model `intfloat/multilingual-e5-small` i Qdranta, a różnią się wyłącznie tym, skąd pochodzi tekst i skąd pochodzą nazwy sekcji. Trafność liczymy po sekcjach, a recall@5 mówi, czy właściwa sekcja jest wśród pięciu fragmentów wkładanych do promptu.

| Wariant | Sekcje trafne/wszystkie | recall@5 | Pytań bez trafienia |
|---|---|---|---|
| Markdown (ground truth) | 131/131 | 0,90 | 2 |
| PDF surowy, nagłówki zgadywane | 121/542 | 0,35 | 13 |
| PDF oczyszczony | 131/131 | 0,95 | 1 |

Skrypt: `experiments/05_pdf.py`.

Z PDF-a nie odzyskujesz przede wszystkim **tekstu** – ten wychodzi zaskakująco dobrze sam. Był jeszcze czwarty wariant, kontrolny: surowy tekst z PDF-a, z paginami wklejonymi w zdania i akapitami pociętymi stroną, ale z podpowiedzianą listą prawdziwych nagłówków. Wypada tak samo jak oczyszczony, bo wyszukiwanie gęste znosi kilka wtrąconych śmieci – wektor liczy się z całego okna 128 tokenów. Takiej listy nikt Ci jednak w prawdziwym projekcie nie poda.

Cała strata siedzi więc w nagłówkach, czyli w **metadanych**. Bez informacji o foncie nie wiesz, która linia jest nagłówkiem, więc piszesz heurystykę „krótka linia, która nie jest zdaniem”. Ta heurystyka znajduje 542 „sekcje” tam, gdzie jest ich 131, i etykietuje chunki napisami `}`, `<source> i` albo – najlepsza – `AI Engineer`, bo żywa pagina też jest krótką linią, która nie jest zdaniem. Trzynaście pytań na dwadzieścia nie ma wtedy w piątce ani jednego trafienia. Skutki sięgają dalej niż tabela: bez nagłówków nie masz czym filtrować (rozdział 4), nie masz co pokazać w cytowaniu (rozdział 6) i nie zbudujesz nawet zestawu ewaluacyjnego, bo nie da się wskazać trafnej sekcji.

Jedna rzecz nie naprawia się sama. Osobny zestaw pytań o wartości z tabel (`golden_tables.jsonl`), puszczony przez te same warianty, daje na oczyszczonym PDF-ie recall@5 równy 0,85 wobec 0,92 na Markdownie. Klasyfikacja po foncie rozpoznaje, że linia jest komórką tabeli, ale nie odtwarza wierszy ani kolumn: dostajesz pionowy ciąg komórek. Do tego służy osobne narzędzie – `Page.find_tables()` zwraca tabele z metodami `extract()`, `to_pandas()` i `to_markdown()`, działa geometrycznie, więc przy widocznych kreskach jest niezawodne, a bez obramowania bywa kapryśne. Znalezione prostokąty wytnij potem z przetwarzania tekstowego, żeby nie zaindeksować tej samej tabeli dwa razy.

Została pułapka, która u nas jest teoretyczna, bo nasz PDF jest jednołamowy, a w pracach naukowych bywa problemem numer jeden. `get_text()` zwraca tekst w kolejności, w jakiej polecenia rysowania trafiły do pliku; dokumentacja mówi wprost: „The output may not equal an accustomed natural reading order”. Argument `sort=True` porządkuje wynik od lewego górnego rogu do prawego dolnego, ale **dwułamowości nie naprawia** – przeciwnie, przeplata szpalty linia po linii. Trzeba najpierw wykryć kolumny: `column_boxes(page)` ze skryptu `multi_column.py` w repozytorium PyMuPDF-Utilities zwraca prostokąty kolumn już w kolejności czytania, a alternatywą jest pakiet `pymupdf4llm`, który od razu oddaje Markdown. Zanim napiszesz jakikolwiek chunker, wypisz surowy tekst trzech losowych stron i przeczytaj go: jeśli zdania się nie kleją, żadna strategia cięcia tego nie uratuje.

## Tabele: najmniejszy sensowny chunk to wiersz

W korpusie jest czternaście tabel Markdown o łącznie 84 wierszach. To niewiele tekstu, ale gęstość faktów na token jest w nich najwyższa w całej książce – i o te właśnie fakty pytają użytkownicy. Zobacz, co robi z taką tabelą stałe okno: sekcja „RAG a fine-tuning” ma 290 słów prozy i tabelę o dziewięciu wierszach, a okno 128/32 kroi ją na sześć chunków. Oto dwa z nich:

```text
'| stylu, formatu, zachowania, domenowego słownictwa | | Świeżość danych | natychmiastowa (reindeksacja dokumen'
'ka za token modelu własnego | | Cytowalność | naturalna, fragment ma źródło | brak, model nie wie, skąd wie | '
```

Wiersz „Koszt bieżący” jest przecięty w pół: początek został w jednym chunku, koniec w drugim. Ważniejsze jest jednak to, czego brakuje w obu – wiersza nagłówkowego. W indeksie leży komórka „natychmiastowa (reindeksacja dokumentu)”, przy której nie stoi ani „Świeżość danych”, ani „RAG”. Taki fragment wygląda jak odpowiedź, ale nią nie jest, a model, który go dostanie, ma pełne prawo przypisać tę wartość do fine-tuningu.

Lekarstwo: wyjąć tabelę z prozy i zaindeksować osobno, w postaci, która sama się tłumaczy. `ragbook/tables.py` parsuje tabele Markdown i serializuje je na trzy sposoby – całą tabelę jako jeden chunk, wiersz po wierszu i wiersz przepisany na zdanie.

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

Każdy wariant zaczyna się od nagłówka kontekstowego „tytuł rozdziału / sekcja”, bo chunk wyjęty z tabeli traci otoczenie jeszcze bardziej niż chunk prozy. Wariant wierszowy powtarza przy tym nazwy kolumn przy każdej wartości – redundancja jest tu celem, nie wadą.

Pomiar idzie na trzynastu pytaniach o konkretne wartości (`data/golden_tables.jsonl`), z jednym dodatkiem. Trafność po sekcjach jest dla tabel zbyt łagodna: chunk może należeć do właściwej sekcji i nie zawierać wiersza, o który pytamy. Dlatego każde pytanie ma pole `value` z wartością, która musi dosłownie wystąpić w którymś z pięciu zwróconych chunków (`ragbook/value_check.py`).

| Wariant | recall@5 | Wartość w top-5 | Pytań bez trafienia |
|---|---|---|---|
| stałe okno (baseline) | 0,92 | 0,69 | 1 |
| tabela jako jeden chunk | 0,92 | 0,62 | 1 |
| wiersz po wierszu | 1,00 | 0,85 | 0 |

Skrypt: `experiments/05_tables.py`.

Wiersz po wierszu wygrywa wyraźnie: wszystkie trzynaście pytań ma trafienie, a wartość wraca w piątce dla jedenastu z nich zamiast dla dziewięciu. Czwarty wariant, wiersz przepisany na zdanie, ma tę samą trafność przy niższym MRR – parafraza nic nie dodaje, a rozcieńcza dopasowanie leksykalne. **Decyzja: tabele wyjmujemy z prozy i indeksujemy wiersz po wierszu, z powtórzonym nagłówkiem kolumn i kontekstem sekcji.** Koszt to 84 dodatkowe chunki, poniżej dwóch procent indeksu.

Zaskakuje środkowy wiersz: tabela w całości jako jeden chunk wypada **gorzej** niż baseline. Przegląd baz wektorowych z rozdziału 7 to siedem kolumn i osiem wierszy o zupełnie różnych rzeczach, a jeden wektor na taki tekst jest średnią ze wszystkiego, czyli punktem, który nie leży blisko żadnego konkretnego pytania. To ta sama pułapka, którą rozdział 2 opisywał przy zbyt dużych chunkach, tylko w skrajnej postaci. Dochodzi obcięcie: trzy z czternastu tabel przekraczają w tej postaci limit 512 tokenów modelu e5, więc lądują w indeksie w połowie, bez żadnego ostrzeżenia.

Dwa pytania nie trafiają w wartość w żadnym wariancie: pytanie o cenę `claude-opus-5` konkuruje z kilkunastoma innymi fragmentami o cenach, a pytanie o metryki agentów – z bardzo długą sekcją „Ewaluacje”. To nie problem serializacji, tylko rankingu, i wraca w rozdziale 3.

## Kod w dokumentacji: blok jest jednostką, nie oknem

Korpus zawiera 156 bloków kodu o medianie 238 tokenów, a 123 z nich są dłuższe niż okno 128 tokenów – w baseline większość snippetów jest więc pocięta. Blok z rozdziału o obserwowalności rozpada się na pięć chunków; oto dwa pierwsze:

```text
'```python from opentelemetry import trace from opentelemetry.sdk.trace import TracerProvid'
'_provider(provider) tracer = trace.get_tracer("acme.support-bot") def fake_model_call(prom'
```

Żaden z tych pięciu chunków nie jest kompletnym programem, a drugi zaczyna się od `_provider(provider)`, czyli od końca identyfikatora przeciętego w środku. Do promptu taki fragment nadaje się wyłącznie jako materiał na halucynację: model dostaje pół wywołania i drugie pół dopisuje z pamięci. Naprawa nie wymaga niczego poza parsowaniem grawisów – blok kodu jest jednostką, nie oknem, więc trzymamy go w całości jako jeden chunk, a prozę tniemy jak dotąd.

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

Wypisany początek pierwszego chunku kodu nie jest kodem, tylko akapitem, który go zapowiada – i o to chodzi w parametrze `attach_lead`. Sam blok kodu jest kiepskim materiałem na embedding: składa się z nazw funkcji, nawiasów i stringów, a pytanie użytkownika jest zdaniem po polsku. Doklejamy więc akapit, w którym autor napisał ludzkimi słowami, co ten kod robi. Bloki dłuższe niż 512 tokenów dzielimy po pustych liniach, powtarzając ten akapit na początku każdej części.

Pomiar idzie na dziesięciu pytaniach o identyfikatory występujące w korpusie **wyłącznie wewnątrz bloków kodu** – `create_payload_index`, `start_as_current_span`, `output_dimensionality` i podobne. Obok trafności po sekcjach sprawdzamy, czy identyfikator pojawił się dosłownie w piątce.

| Wariant | recall@5 | Identyfikator w top-5 | Pytań bez trafienia |
|---|---|---|---|
| stałe okno (baseline) | 0,90 | 0,40 | 1 |
| blok kodu w całości | 1,00 | 0,30 | 0 |
| blok kodu + poprzedzający akapit | 1,00 | 0,70 | 0 |

Skrypt: `experiments/05_code.py`.

Dopiero oba kroki naraz robią robotę: blok w całości z doklejonym akapitem daje szukany identyfikator w piątce dla siedmiu pytań na dziesięć. Chunk ma wtedy jedno i drugie – zdanie po polsku, po którym da się go znaleźć, i kod, który jest odpowiedzią. Kontrolnie sprawdziliśmy pytania o prozę: ich recall@5 nie drgnął w żadnym wariancie, a indeks skurczył się z 1550 chunków do 1299.

Najciekawszy jest wiersz środkowy, bo psuje prostą historię. Sam blok w całości podnosi trafność po sekcjach do jedności, ale **obniża** udział identyfikatorów w piątce. Powód jest ten sam co przy tabeli jako jednym chunku: blok kodu embeduje się w rozmytą średnią, więc trafia do właściwej sekcji, ale przegrywa z prozą o tej samej tematyce.

Zwróć na koniec uwagę, gdzie ta droga się kończy. Nawet w najlepszym wariancie trzy pytania na dziesięć nie dostają szukanego identyfikatora w pięciu zwróconych fragmentach. To nie wina chunkera: `query_points` czy `max_seq_length` to dla modelu embeddingowego kilka mało znaczących podsłów, a wielojęzyczny e5 nie ma czym odróżnić nazwy metody od innej nazwy metody. Takie zapytania wygrywa wyszukiwanie leksykalne i zbuduje je rozdział 3. Zapamiętaj tylko, że chunker trzymający blok kodu w całości jest warunkiem wstępnym – hybryda nie pomoże, jeśli identyfikator jest przecięty na pół.

## Obrazy i diagramy w PDF-ie

Nasz PDF nie ma ani jednego obrazu rastrowego, bo diagramy w tomie 1 są rysowane znakami w blokach kodu. W prawdziwej dokumentacji jest inaczej i obowiązuje tam jedna zasada: obraz, którego nie opiszesz tekstem, nie istnieje dla wyszukiwania. Potok jest krótki – wykryj obrazy (`page.get_images(full=True)`) albo wyrenderuj obszar strony do PNG (`page.get_pixmap(dpi=150, clip=rect).tobytes("png")`), poproś model multimodalny o opis i zaindeksuj ten opis jako zwykły chunk z metadanymi wskazującymi stronę; wywołanie jest to z tomu 1, rozdział 13, z blokiem `image` ułożonym **przed** blokiem tekstowym, bo taką kolejność zaleca dokumentacja Anthropic (stan na wrzesień 2026). W prompcie żądaj dosłownego wymienienia wszystkich etykiet, bo opis „diagram architektury systemu” jest w wyszukiwaniu bezużyteczny, a lista nazw komponentów już nie. I oznacz opis w metadanych jako treść pochodną, wygenerowaną przez model, żeby przy cytowaniu nie udawał tekstu z dokumentu.

## Gotowe parsery: kiedy nie pisać własnego

Sto linijek z `ragbook/pdf.py` wystarczyło, bo nasz PDF jest born-digital, jednołamowy i wygenerowany przez znany nam skład. Przy tysiącu PDF-ów z pięciu źródeł ta droga kończy się szybko. Narzędzia poniżej są zweryfikowane w ich oficjalnej dokumentacji (stan na wrzesień 2026).

| Narzędzie | Licencja | Tryb | Wyjście | Tabele | OCR | Ciężar |
|---|---|---|---|---|---|---|
| pdfplumber | MIT | lokalnie | obiekty Pythona, tekst | `extract_tables()`, geometria | brak | znikomy |
| PyMuPDF | AGPL v3 lub komercyjna | lokalnie | tekst, dict, HTML, XML | `find_tables()`, geometria | brak | mały |
| Docling | MIT | lokalnie | Markdown, HTML, JSON | model TableFormer | tak | modele lokalne |
| unstructured | Apache 2.0 (OSS) + SaaS | lokalnie i chmura | lista elementów, JSON | `infer_table_structure=True` | tak | duży w `hi_res` |
| marker | kod Apache 2.0, wagi OpenRAIL-M | lokalnie | Markdown, JSON, HTML | modelowo (Surya) | tak | GPU zalecane |
| LlamaParse | usługa komercyjna | chmura | Markdown, tekst, JSON | modele generatywne | tak | brak (SaaS) |

**pdfplumber** jest najlżejszy i najlepszy do tabel z widocznymi liniami: nadbudowa nad `pdfminer.six`, dostęp do znaków z fontem i pozycją, kilkanaście strategii w `extract_tables()` i żadnego modelu w środku. Skanów nie obsłuży. **PyMuPDF**, na którym stoi ten rozdział, jest szybszy i bogatszy, ale ma haczyk licencyjny: AGPL v3 albo licencja komercyjna od Artifexu, czyli decyzja do podjęcia świadomie, a nie przy `pip install`.

**Docling** to dziś domyślny wybór, gdy potrzebujesz jakości bez wysyłania dokumentów na zewnątrz: MIT, praca lokalna także bez sieci, na wejściu PDF, DOCX, PPTX, XLSX, HTML i obrazy, struktura tabel z modelu TableFormer. Ceną jest pierwsze uruchomienie, które ściąga setki megabajtów modeli. **unstructured** wygrywa liczbą formatów (ponad sześćdziesiąt) i modelem elementów – `Title`, `NarrativeText`, `Table` – czyli dokładnie tym, co odtwarzaliśmy tu z rozmiarów fontu; jego własna dokumentacja zastrzega jednak, że wersja open source jest do prototypowania, nie do produkcji.

**marker** daje najlepszą jakość spośród lokalnych kosztem GPU i licencji na wagi (OpenRAIL-M, darmowa dla badań i firm poniżej pięciu milionów dolarów przychodu), a **LlamaParse** rozlicza się w kredytach za stronę: od jednego w trybie Fast do 45 w Agentic Plus, przy 1,25 USD za tysiąc kredytów.

Reguła wyboru jest krótka. Jeden znany szablon dokumentu – własny kod na PyMuPDF albo pdfplumberze. Wiele źródeł, dużo tabel, dane zostają u Ciebie – Docling. Dużo formatów innych niż PDF – unstructured. Skany i dokumenty, których nie umiesz opanować – usługa, i zmierz, czy jest warta rachunku.

## Podsumowanie

- PDF zapisuje wygląd, nie strukturę – ale wygląd zdradza strukturę, bo generator zakodował ją w rozmiarze i rodzinie fontu, a `get_text("dict")` oddaje je w polach `size` i `font`. Klasyfikuj linie względem dominującego rozmiaru prozy, nie po stałych progach.
- Sam tekst z PDF-a wyszukuje się prawie tak dobrze jak źródło (recall@5 0,95 wobec 0,90). Traci się **metadane**: heurystyczne zgadywanie nagłówków zbija recall@5 do 0,35 i zostawia 13 z 20 pytań bez trafienia.
- Żywą paginę wykrywaj statystycznie, po tekście powtarzalnym w pasie u góry i u dołu strony, a akapit przecięty granicą stron sklejaj po tym, że jego linie sięgają prawego marginesu.
- `sort=True` porządkuje dokumenty z pomieszaną kolejnością rysowania, ale nie rozwiązuje dwułamowości – do tego trzeba najpierw wykryć kolumny (`multi_column.py` albo `pymupdf4llm`).
- Tabelę indeksuj wiersz po wierszu, z powtórzonym nagłówkiem kolumn i nazwą sekcji: recall@5 rośnie z 0,92 do 1,00, a udział poprawnej wartości w piątce z 0,69 do 0,85. Tabela jako jeden chunk wypada gorzej niż stałe okno.
- Blok kodu trzymaj w całości i doklejaj do niego poprzedzający akapit prozy: sam blok obniża trafność identyfikatorów (0,40 → 0,30), a z akapitem podnosi ją do 0,70.
- Wyszukiwanie gęste zostaje słabe na identyfikatorach nawet przy dobrym chunkingu. To zadanie dla hybrydy z rozdziału 3, nie dla kolejnej strategii cięcia.

## Co dalej

Wiemy już, jak zamienić trudny dokument w chunki, które da się przeczytać i zacytować. Rozdział 6 pyta, co model z nimi robi: jak zbudować prompt, który nie pozwala wyjść poza kontekst, jak wymusić cytowanie z dokładnością do fragmentu, jak wykryć odpowiedź bez podstawy i jak zmierzyć wierność sędzią LLM. Zanim tam przejdziesz, podmień ścieżkę w `ragbook/pdf.py` na własny PDF i wypisz sto losowych linii z ich klasyfikacją. Jeśli progi nie trafiają w Twoje nagłówki, policz rozkład par (rozmiar, font) w swoim dokumencie i przesuń je względem dominanty.

## Źródła

- PyMuPDF: https://pymupdf.readthedocs.io/en/latest/ – strony `page`, `textpage`, `app1`, `recipes-text`, `changes`, `pymupdf4llm`
- https://github.com/pymupdf/PyMuPDF-Utilities/blob/master/text-extraction/multi_column.py
- https://github.com/jsvine/pdfplumber, https://github.com/datalab-to/marker
- https://docling-project.github.io/docling/ oraz .../usage/advanced_options/
- https://docs.unstructured.io/open-source/introduction/overview oraz .../core-functionality/partitioning
- https://developers.llamaindex.ai/llamaparse/parse/ oraz .../general/pricing/
- https://platform.claude.com/docs/en/build-with-claude/vision
- https://huggingface.co/intfloat/multilingual-e5-small
