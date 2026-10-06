# Plan tomu 2: „RAG w produkcji. Od naiwnego prototypu do mierzalnego systemu”

Zasady pisania: `BRIEF.md` (ten katalog) + `books/ai-engineer/BRIEF.md`. Skład: `.venv/bin/python build/build.py rag-w-produkcji` (z katalogu głównego repo) → `build/rag-w-produkcji.pdf`.

Projekt przewodni: asystent Q&A po dokumentacji, korpus = tom 1 (`books/ai-engineer/chapters/`), kod w `code/`, zestaw ewaluacyjny w `code/data/golden.jsonl`. Każdy rozdział mierzy swój wpływ tym samym zestawem i tymi samymi metrykami.

| Nr | Plik | Tytuł | Strony (cel) | Zależy od | Status |
|---|---|---|---|---|---|
| 0 | chapters/00-wstep.md | Wstęp | 2 | wszystkie | gotowy |
| 1 | chapters/01-projekt-i-pomiar.md | Projekt, korpus, baseline i pomiar | 12 | – | gotowy, przejrzany |
| 2 | chapters/02-chunking-i-embeddingi.md | Chunking i model embeddingowy z pomiarem | 12 | 1 | gotowy, przejrzany |
| 3 | chapters/03-hybryda-i-reranking.md | Wyszukiwanie hybrydowe i reranking | 12 | 1 | gotowy, przejrzany |
| 4 | chapters/04-zapytania.md | Przekształcanie zapytań, filtry i routing | 10 | 1 | gotowy, przejrzany |
| 5 | chapters/05-trudne-dane.md | Trudne dane: PDF-y z układem, tabele, kod | 10 | fundament | gotowy, przejrzany |
| 6 | chapters/06-generacja-i-wiernosc.md | Generacja, cytowania i wierność odpowiedzi | 10 | fundament | gotowy, przejrzany |
| 7 | chapters/07-graf-i-agentic-rag.md | GraphRAG i agentic RAG | 8 | fundament | gotowy, przejrzany |
| 8 | chapters/08-produkcja.md | Indeks w ruchu: aktualizacje, cache, koszty, bezpieczeństwo, monitoring | 12 | fundament | gotowy, przejrzany |

Razem ok. 88 stron.

## Zakres rozdziałów

1. **Projekt, korpus, baseline i pomiar.** Czym różni się RAG produkcyjny od prototypu (lista trybów awarii z praktyki). Korpus i jego statystyki (rozdziały, sekcje, długości, ile kodu/tabel). Fundament kodu: `corpus`, `embed`, `store`, `evaluate`. Naiwny baseline: stałe okno + e5-small + Qdrant, top-5 do promptu. Budowa golden setu: jak wybierać pytania (rozkład typów, pytania negatywne, pytania wielosekcyjne), 50–60 pytań, jak weryfikować trafność ręcznie. Metryki retrievalu (recall@k, MRR, nDCG) i dlaczego mierzymy retrieval osobno od generacji. Pierwszy pomiar baseline'u i analiza błędów: kategorie porażek, które napędzają kolejne rozdziały. Pętla pracy: zmiana → pomiar → decyzja.
2. **Chunking i model embeddingowy.** Stałe okno (kilka rozmiarów i zakładek), podział po strukturze Markdown (sekcje, akapity), rekurencyjny, semantyczny, parent-child (small-to-big: mały chunk do wyszukiwania, rodzic do promptu), contextual chunk headers (tytuł rozdziału + sekcji doklejony do chunku), contextual retrieval (opis chunku generowany LLM-em – pokazać kod, wynik jako „przykładowy”). Porównanie modeli embeddingowych: MiniLM vs e5-small vs jeden większy (jeśli mieści się w pamięci), prefiksy `query:`/`passage:`, wymiar a koszt indeksu. Tabela zbiorcza, decyzja.
3. **Hybryda i reranking.** BM25 (rank_bm25 i sparse vectors w Qdrant/fastembed), fuzja RRF vs ważona, kiedy leksykalne wygrywa (identyfikatory, nazwy parametrów, kod). Reranking cross-encoderem (mmarco-mMiniLM; bge-reranker-v2-m3 osobno, z uwagą o pamięci), reranking LLM-em (kod, przykładowy wynik), koszt i latencja rerankingu (pomiar czasu). Retrieve 20 → rerank → top 5. Tabela, decyzja.
4. **Zapytania.** Query rewriting, multi-query, HyDE, step-back, dekompozycja pytań złożonych (wszystkie wymagają LLM-a: kod poprawny, wyniki jako przykładowe, plus symulacja z ręcznie napisanymi wariantami tam, gdzie da się coś zmierzyć lokalnie). Filtrowanie po metadanych (rozdział, typ treści) i self-query. Routing: pytanie globalne vs lokalne, kiedy nie szukać wcale. Klasyfikacja intencji małym modelem. Pomiar tego, co mierzalne lokalnie.
5. **Trudne dane.** PDF z układem: pymupdf na `build/ai-engineer.pdf`, kolejność czytania, nagłówki/stopki, dwułamowość, porównanie z Markdown jako ground truth. Tabele: wykrywanie, serializacja (Markdown, JSON, zdania), osobny indeks na tabele, pytania o wartości w tabelach (mały dodatkowy zestaw). Kod w dokumentacji: chunkowanie bloków kodu w całości, wyszukiwanie po identyfikatorach. Multimodalność jako przegląd (obrazy w PDF, odsyłacz do tomu 1, rozdział 13). Docling/unstructured jako przegląd narzędzi (tabela).
6. **Generacja i wierność.** Prompt „odpowiadaj tylko z kontekstu” i jego granice. Cytowania: Anthropic citations API (kod), własne cytowania z numerowanymi fragmentami, weryfikacja cytatów po stronie kodu. Odmowa, gdy brak podstaw (pytania negatywne z golden setu). Faithfulness/groundedness: LLM-as-judge (kod, kalibracja), RAGAS/DeepEval jako przegląd. Structured outputs dla odpowiedzi z cytatami. Streaming z cytowaniami. Prompt caching dla stałej części promptu. Wszystko wymaga LLM-a: kod poprawny, wyniki przykładowe, jasno oznaczone.
7. **GraphRAG i agentic RAG.** Kiedy podobieństwo nie wystarcza (pytania „jak X wiąże się z Y”, pytania globalne). Ekstrakcja encji i relacji (kod, wynik przykładowy), graf w networkx, wyszukiwanie po sąsiedztwie, community summaries jako idea. Agentic RAG: iteracyjne wyszukiwanie, self-RAG/corrective RAG (ocena trafności → ponowne zapytanie), RAG jako narzędzie agenta (tom 1, rozdział 9). Uczciwa ocena: koszt vs zysk, kiedy nie warto.
8. **Produkcja.** Pipeline indeksowania: przyrostowe aktualizacje, hash treści, usuwanie, wersjonowanie indeksu, reindeksacja przy zmianie modelu (blue/green kolekcji). Cache: embeddingów zapytań, semantyczny cache odpowiedzi, prompt caching. Koszty: model kosztu jednego zapytania (tokeny wejścia z kontekstem, reranker, LLM), budżet latencji per etap (pomiar). Bezpieczeństwo: prompt injection przez dokumenty, kontrola dostępu na poziomie dokumentu (filtr ACL w zapytaniu, nie po nim), PII. Obserwowalność: trace zapytania (retrieved ids, scores, prompt, odpowiedź), metryki online, dryf po zmianie modelu, feedback użytkownika jako źródło nowych pytań do golden setu. Lista kontrolna wdrożeniowa.

## Ustalenia

- Domyślny embedder projektu: `intfloat/multilingual-e5-small` (384 wymiary, 512 tokenów, prefiksy `query:`/`passage:`). Baza: Qdrant `:memory:`. LLM w kodzie: `claude-opus-5` (jak w tomie 1).
- Golden set: 50–60 pytań, powstaje w rozdziale 1, potem zamrożony.
- Standardowe `k`: 5 i 20.
- Dobór modeli agentów: wszystkie rozdziały są kodowo-pomiarowe → Opus.
- Kolejność pracy: fundament (redaktor) → rozdział 1 równolegle z 5, 6, 7, 8 → po zamrożeniu golden setu rozdziały 2, 3, 4 → wstęp, przegląd, skład.

## Stan na 17 września 2026, późny wieczór

Wszystkie rozdziały napisane przez agentów (Opus) i przejrzane przez redaktora. Golden set zamrożony: 56 pytań, md5 `d067da14…`. Baseline (rozdz. 1): recall@5 0,72, recall@20 0,96, MRR@5 0,67, nDCG@5 0,64, 9 pytań bez trafienia. Konfiguracja projektu po rozdziałach 2–3 (`project_chunks` + `project_retriever`): recall@5 0,88, MRR@5 0,81, 3 pytania bez trafienia; przekształcanie zapytań (rozdz. 4) na tym potoku nie podnosi już recall@5, podnosi recall@20 z 0,92 do 0,99.

Decyzje redakcyjne:
- Domyślny embedder zostaje `multilingual-e5-small` mimo pomiaru w rozdz. 2 (e5-base +0,08 recall@5), żeby rozdziały 1 i 5–8 pozostały porównywalne; rozdział 2 mówi o tym wprost.
- `ragbook/generate.py` (rozdz. 1, jedno wywołanie) i `ragbook/answer.py` (rozdz. 6, structured outputs + cytowania) współistnieją; rozdz. 6 opisuje drugi jako następcę pierwszego. Moduł rozdz. 5 `answers.py` przemianowany na `value_check.py`, żeby nie mylił się z `answer.py`.
- W trakcie pracy venv przeszedł z PyTorch CPU na CUDA (GTX 1650); pomiary czasu w rozdziałach mają jawnie oznaczone urządzenie.
- Rozdziały są dłuższe niż cel (ok. 13–16 stron zamiast 10–12); zaakceptowane, bo nadwyżka to tabele pomiarów, nie proza.

## Drugi przebieg redakcyjny (18 września 2026, noc)

Po pierwszym spojrzeniu autor ocenił wersję pierwszą jako „suche laboratorium” i poprosił o ton tłumaczący, jak w tomie 1. Brief drugiego przebiegu: `REDAKCJA.md`. Każdy rozdział przepisany przez osobnego agenta bez zmiany liczb i bez uruchamiania kodu; pierwsze wersje zachowane w `drafts/v1/`. Efekt: proza krótsza o 20–30%, tabele skrócone do 3–6 wierszy (pełne siatki w skryptach), identyfikatory pytań usunięte z prozy, każdy rozdział zaczyna się od problemu i przykładu. PDF: 107 stron. Sprawdzono programowo, że żadna liczba w nowych wersjach nie pojawiła się spoza wersji pierwszej (poza różnicami wyliczonymi z tabel). Poprawki redaktora po raportach: przykładowy blok cytowań w rozdz. 6 (zdanie „bez podparcia” było w cytacie), tabela indeksowania w rozdz. 8 (0,0 → 0,04 s) i zdanie wyjaśniające rozjazd czasów 158 s (rozdz. 1) vs 71 s (rozdz. 8).
