# Brief dla autorów rozdziałów

Książka: **„AI Engineer. Praktyczny przewodnik po roadmapie roadmap.sh/ai-engineer”**.
Odbiorca: programista (Python, backend), który umie kodować, ale nie budował jeszcze systemów na LLM-ach.
Cel: po lekturze rozdziału czytelnik rozumie pojęcia z danego fragmentu roadmapy **i potrafi je uruchomić w Pythonie**.

## Język i styl

- Proza po polsku. Kod, nazwy identyfikatorów i komentarze w kodzie po angielsku.
- Terminologia: angielski termin przy pierwszym użyciu w nawiasie, potem po polsku, jeśli istnieje naturalne tłumaczenie (np. „okno kontekstu (context window)"). Terminy bez dobrego tłumaczenia zostają po angielsku: prompt, token, embedding, fine-tuning, streaming.
- Ton: rzeczowy, drugi osoba liczby pojedynczej („zobaczysz", „uruchom"). Bez marketingu, bez „w dzisiejszym dynamicznym świecie".
- Akapity 3–6 zdań. Listy tylko dla rzeczywiście równoległych elementów.
- Bez emoji. Bez dywizu jako myślnika; jeśli potrzebujesz myślnika, użyj półpauzy „–".
- Polska typografia: cudzysłowy „tak", przecinek dziesiętny w prozie (w kodzie kropka).

## Struktura pliku rozdziału

Plik: `chapters/NN-slug.md`. Zaczyna się od nagłówka `# Rozdział N. Tytuł`.

Zaraz po tytule blok:

```
> **Z roadmapy:** lista węzłów roadmapy, które ten rozdział pokrywa (dokładne etykiety z roadmap.sh, po przecinku).
>
> **Pakiety:** `pip install ...` (wszystko, czego potrzebują snippety w tym rozdziale) albo „brak", jeśli rozdział nie ma kodu.
```

Dalej:

1. Dwa–trzy akapity wprowadzenia: po co ten temat, gdzie boli w praktyce.
2. Sekcje `##` odpowiadające węzłom roadmapy (grupuj drobne węzły, nie rób sekcji na jedno zdanie).
3. Na końcu sekcja `## Podsumowanie` (5–8 punktów) i `## Co dalej` (jeden akapit: link do następnego rozdziału i co czytelnik może zrobić samodzielnie).

Nagłówki maksymalnie do `###`. Bez numerowania nagłówków ręcznie (numeracja dojdzie przy składzie).

## Kod

- Każdy snippet ma być **uruchamialny w izolacji**: importy, klucz API z `os.environ["..."]`, minimalny działający przykład. Bez `...` w środku kodu.
- Bloki kodu z językiem: ```` ```python ````. Wyniki uruchomienia jako ```` ```text ````.
- Snippet ma 10–40 linii. Jeśli potrzeba więcej, podziel na kroki z prozą między nimi.
- Po każdym snippecie akapit: co się stało i na co zwrócić uwagę.
- Klucze API przez zmienne środowiskowe: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
- Domyślne SDK: `anthropic` (Claude) i `openai`. Gemini tam, gdzie roadmapa wprost go wymienia. Open source: `sentence-transformers`, `qdrant-client`, `transformers`.
- Nazwy modeli: używaj **aktualnych** identyfikatorów zweryfikowanych w dokumentacji (patrz research). Nie zgaduj. Jeśli nie możesz zweryfikować, napisz identyfikator jako stałą `MODEL = "..."` na górze snippetu i dodaj komentarz `# check docs for the current model id`.

## Research (obowiązkowy przed kodem)

Wiedza o SDK i modelach starzeje się w miesiące. Zanim napiszesz snippet z użyciem API:

1. Pobierz odpowiednią stronę oficjalnej dokumentacji (WebFetch): `docs.anthropic.com` / `docs.claude.com`, `platform.openai.com/docs`, `ai.google.dev`, `huggingface.co/docs`.
2. Sprawdź: aktualne nazwy metod, kształt request/response, nazwy parametrów, aktualne identyfikatory modeli, limity, które wymieniasz w prozie (np. rozmiar okna kontekstu, minimalna liczba tokenów do cache).
3. Wszystkie liczby (ceny, limity, rozmiary kontekstu), które podajesz w prozie, muszą pochodzić z dokumentacji sprawdzonej dziś. Podaj datę sprawdzenia w przypisie w formie: „(stan na wrzesień 2026)".
4. Nie cytuj roadmap.sh ani blogów jako źródła faktów o API.

Na koniec pliku rozdziału dodaj sekcję `## Źródła` z listą URL-i dokumentacji, z których korzystałeś (tylko oficjalne).

## Objętość

Cel na stronę: około 400 słów prozy albo 45 linii kodu. Każdy rozdział ma podany docelowy zakres stron; trzymaj się go z dokładnością ±20%.

## Czego nie robić

- Nie przepisuj opisów z roadmap.sh. To są jednoakapitowe zajawki, książka ma być głębsza.
- Nie wymyślaj funkcji SDK, parametrów ani modeli.
- Nie pisz „w tej sekcji omówimy". Od razu omawiaj.
- Nie dodawaj disclaimerów o tym, że wiedza może być nieaktualna, poza datą przy liczbach.
- Nie twórz plików poza swoim rozdziałem.

## Ustalenia obowiązujące od rozdziału 4 (wynik researchu z rozdziałów 1–3)

- Dokumentacja Anthropic: `https://platform.claude.com/docs/...` (docs.claude.com przekierowuje). OpenAI: `https://developers.openai.com/api/docs/...` (platform.openai.com/docs przekierowuje). Gemini: `https://ai.google.dev/gemini-api/docs`.
- Identyfikatory modeli w książce: `claude-opus-5` (domyślny), `claude-haiku-4-5` (tani/szybki), `gpt-6-astra` (OpenAI). Inne tylko po weryfikacji w docs.
- `temperature`, `top_p`, `top_k` są wycofane na modelach po Claude Opus 4.6 i na flagowcach OpenAI (rozdział 2 to opisuje). Nie ustawiaj ich w snippetach; jakość/koszt steruje `output_config={"effort": ...}` (Anthropic) i `reasoning.effort` (OpenAI).
- Anthropic structured outputs: `client.messages.parse(..., output_format=PydanticModel)` → `response.parsed_output`; niskopoziomowo `output_config={"format": {"type": "json_schema", ...}}`. OpenAI: `client.responses.parse(..., text_format=Model)` → `response.output_parsed`. Function calling i streaming są opisane w rozdziale 3, nie tłumacz ich od nowa, odsyłaj.
- Nie masz kluczy API. Wyniki wywołań API opisuj w prozie albo daj blok ```text poprzedzony zdaniem „Przykładowy wynik:”. Wyniki kodu lokalnego (numpy, sentence-transformers, tokenizery, FAISS, Qdrant w trybie in-memory) uruchamiaj naprawdę w venv w scratchpadzie i wklejaj prawdziwe.
- Odwołania do innych rozdziałów wg numeracji z `PLAN.md` (przeczytaj go).
- Tematy-katalogi (lista narzędzi, lista modeli, lista baz) opisuj tabelą porównawczą plus akapit na pozycję, nie osobną sekcją na każdą.
- Zawsze zaczynaj od przeczytania jednego z gotowych rozdziałów (`chapters/03-prompt-engineering.md`) jako wzorca tonu i głębokości.
- Instalacja `sentence-transformers`/`torch` w venv: zawsze `uv pip install --torch-backend=cpu ...` (inaczej ciągnie pakiety CUDA i zapycha dysk). Sprawdź po instalacji `python -c "import torch, scipy"`.
- Nie edytuj PLAN.md, aktualizuje go redaktor.
