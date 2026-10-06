# Brief dla autorów rozdziałów – tom 2: „RAG w produkcji”

Obowiązuje wszystko z `books/ai-engineer/BRIEF.md` (język, styl, kod, research, typografia, ustalenia o SDK i identyfikatorach modeli). Ten plik opisuje tylko różnice i rzeczy specyficzne dla tomu 2. Przeczytaj oba przed pisaniem.

## Czym jest ten tom

Tom 1 („AI Engineer”, `books/ai-engineer/chapters/`) był szeroki i płytki: jeden rozdział na węzeł roadmapy, poziom „rozumiem i umiem uruchomić”. Tom 2 jest wąski i głęboki: jeden temat (RAG), jeden projekt przewodni budowany od naiwnego prototypu do systemu produkcyjnego, każda decyzja poparta pomiarem.

Odbiorca: czytelnik tomu 1 (albo ktoś o równoważnej wiedzy). Zna embeddingi, bazy wektorowe, podstawowy pipeline RAG, ewaluacje na poziomie definicji. **Nie tłumacz od nowa pojęć z tomu 1** – odsyłaj: „tom 1, rozdział 6”. Numeracja tomu 1: 1 Kim jest AI Engineer, 2 Jak działają LLM-y, 3 Prompt engineering, 4 Context engineering, 5 Modele i platformy, 6 Embeddingi, 7 Bazy wektorowe, 8 RAG, 9 Agenci, 10 MCP, 11 Bezpieczeństwo, 12 Obserwowalność i ewaluacje, 13 Multimodalność, 14 Narzędzia.

Wzorzec tonu i głębokości: `books/ai-engineer/chapters/08-rag.md` (przeczytaj w całości, to punkt wyjścia, którego ten tom nie powtarza, tylko pogłębia).

## Projekt przewodni

Budujemy asystenta odpowiadającego na pytania po dokumentacji technicznej. Korpusem jest **tom 1 tej serii**: 14 plików Markdown w `books/ai-engineer/chapters/` (ok. 65 tys. słów po polsku, nagłówki, bloki kodu, tabele, przypisy). Powody: czytelnik ma go pod ręką, jest po polsku, ma prawdziwą strukturę i prawdziwe pułapki (kod, tabele), a pytania mają sprawdzalne odpowiedzi. Wersja PDF (`build/ai-engineer.pdf`) służy w rozdziale o trudnych danych.

Kod projektu żyje w `books/rag-w-produkcji/code/`:

```
code/
  ragbook/            pakiet współdzielony przez rozdziały (corpus, chunking, embed, store, evaluate, ...)
  data/golden.jsonl   zestaw ewaluacyjny (powstaje w rozdziale 1)
  experiments/NN_*.py skrypty odtwarzające każdą tabelę z pomiarami w rozdziale NN
  .cache/             cache embeddingów (ignorowany przez git)
```

Zasady kodu w tym tomie (uzupełnienie zasad z tomu 1):

- Snippety w rozdziale importują z `ragbook` i uruchamia się je z katalogu `code/`: `cd books/rag-w-produkcji/code && ../.venv/bin/python experiments/02_chunking.py`. Napisz to raz na początku rozdziału, nie powtarzaj przy każdym snippecie.
- Snippet w książce pokazuje **istotę** (10–40 linii). Pełny, uruchamialny kod idzie do `ragbook/<modul>.py` i `experiments/NN_*.py`. Każda tabela z liczbami w rozdziale musi mieć skrypt, który ją odtwarza, i zdanie „Skrypt: `experiments/NN_nazwa.py`”.
- Moduły fundamentu (`ragbook/corpus.py`, `evaluate.py`, `embed.py`, `store.py`) już istnieją – przeczytaj je i **używaj ich interfejsów**. Możesz dodać nowe moduły dla swojego rozdziału. Nie zmieniaj sygnatur istniejących funkcji; jeśli potrzebujesz zmiany, dodaj nową funkcję i napisz o tym w raporcie końcowym.
- Venv: `books/rag-w-produkcji/.venv` (sentence-transformers, qdrant-client, rank_bm25, fastembed, pymupdf, anthropic, openai, networkx zainstalowane). Maszyna ma GPU NVIDIA GTX 1650 (4 GB VRAM) i PyTorch z CUDA (od 17 września 2026 wieczorem; wcześniejsze pomiary czasu w rozdziałach 1–8 były robione na CPU i tak są opisane). sentence-transformers i CrossEncoder wybierają GPU automatycznie. Doinstalowanie: `uv pip install --python books/rag-w-produkcji/.venv <pakiet>`; sam torch: `--torch-backend=auto`.
- **Pamięć jest ograniczona (ok. 4 GB wolne, kilku agentów pracuje równolegle).** Używaj małych modeli: `intfloat/multilingual-e5-small` (domyślny embedder projektu, w cache HF), `paraphrase-multilingual-MiniLM-L12-v2`, reranker `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (w cache). `BAAI/bge-reranker-v2-m3` jest w cache, ale duży – ładuj go tylko sam, nigdy równolegle z innym modelem. Nie pobieraj modeli większych niż 600 MB. Nie trzymaj dwóch modeli w pamięci naraz, jeśli nie musisz. Korzystaj z cache embeddingów w `ragbook.embed` (drugie uruchomienie tego samego eksperymentu ma nie liczyć embeddingów od nowa).
- Brak kluczy API (jak w tomie 1): wywołania Claude/OpenAI w kodzie są poprawne wg dokumentacji, a ich wyniki opisujesz w prozie albo blokiem ```text po zdaniu „Przykładowy wynik:”. **Wszystko, co lokalne (retrieval, chunking, BM25, rerankery, metryki), uruchamiasz naprawdę i podajesz prawdziwe liczby.** Nie wymyślaj wyników pomiarów. Jeśli jakiś eksperyment wymaga LLM-a, powiedz to wprost i pokaż, jak czytelnik go odtworzy z własnym kluczem.

## Zestaw ewaluacyjny (golden set)

Plik `code/data/golden.jsonl`, jedno pytanie na linię:

```json
{"id": "q001", "question": "Jaki jest limit długości wejścia modelu paraphrase-multilingual-MiniLM-L12-v2?", "type": "factual", "relevant": [{"chapter": 8, "section": "Pipeline krok po kroku"}], "answer": "128 tokenów (max_seq_length)."}
```

- `type`: `factual` (jeden fakt), `procedural` (jak coś zrobić), `comparative` (porównanie, zwykle 2+ sekcje), `negative` (odpowiedzi nie ma w korpusie; `relevant` puste).
- `relevant` wskazuje **sekcje** (numer rozdziału tomu 1 + dokładny tekst nagłówka `##`), nie chunki. Dzięki temu zestaw nie zależy od strategii chunkowania: chunk jest trafny, jeśli należy do trafnej sekcji. Tak liczą metryki w `ragbook.evaluate`.
- Zestaw tworzy rozdział 1. Pozostałe rozdziały go **nie modyfikują** (mogą dodać własny plik, np. `data/golden_tables.jsonl`, jeśli potrzebują pytań specjalnych).

Metryki (w `ragbook.evaluate`): recall@k po sekcjach, MRR, nDCG@k, plus liczba pytań bez żadnego trafienia. Standardowe `k` w tomie: 5 (do promptu) i 20 (przed rerankingiem). Każda liczba w tabeli ma być z tego samego zestawu i tego samego `k`, żeby rozdziały były porównywalne.

## Styl rozdziału w tomie 2

- Rozdział zaczyna się od problemu widzianego w liczbach (np. „baseline z rozdziału 1 ma recall@5 równy 0,61; ten rozdział podnosi go do …”) i kończy tabelą „przed / po” oraz decyzją: co zostaje w projekcie i dlaczego.
- Każda technika: po co, jak działa (krótko), kod, pomiar, kiedy nie warto. Nie opisuj technik, których nie zmierzyłeś, chyba że wyraźnie oznaczysz je jako przegląd.
- Docelowa objętość podana w PLAN.md; ±20%.
- Blok na początku pliku (zamiast „Z roadmapy”):

```
> **Cel rozdziału:** jedno zdanie.
>
> **Kod:** `ragbook/<moduły>`, `experiments/NN_*.py`. **Pakiety poza fundamentem:** `pip install ...` albo „brak”.
```

- Sekcja końcowa `## Podsumowanie` (5–8 punktów), `## Co dalej` (jeden akapit), `## Źródła` (tylko oficjalna dokumentacja i prace źródłowe, np. arXiv dla HyDE/RAPTOR/GraphRAG).
- Odwołania między rozdziałami tomu 2: „rozdział 3” bez „tom 2”. Do tomu 1: „tom 1, rozdział 6”.

## Raport końcowy agenta

Po zakończeniu napisz w odpowiedzi: liczba słów prozy, lista utworzonych/zmienionych plików w `code/`, kluczowe liczby z pomiarów (tabela przed/po), co wymagało LLM-a i nie zostało uruchomione, wszelkie odstępstwa od tego briefu.
