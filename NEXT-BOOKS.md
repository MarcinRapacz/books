# Kolejne książki – plan rozszerzeń

Notatka z 17 września 2026, po ukończeniu pierwszej książki (`books/ai-engineer/`) („AI Engineer. Praktyczny przewodnik po roadmapie roadmap.sh/ai-engineer”, 143 strony, poziom „mocny junior”).

## Zasada ogólna

Pierwsza książka jest szeroka i płytka: każdy rozdział to jeden węzeł roadmapy rozwinięty do poziomu „rozumiem i umiem uruchomić”. Kolejne pozycje mają być wąskie i głębokie: jeden temat, jeden projekt przewodni budowany od zera do wersji produkcyjnej, z realnymi danymi, pomiarami i decyzjami. Objętość 50–90 stron wystarczy, bo nie trzeba już tłumaczyć podstaw.

## Propozycje (w kolejności wartości)

### 1. RAG w produkcji

Najbardziej praktyczny temat i najpłycej pokryty względem liczby pułapek. Rozdziały 6, 7 i 8 dają pipeline „szczęśliwej ścieżki”.

Do pogłębienia:
- strategie chunkowania z pomiarem wpływu na jakość,
- hybrid search (BM25 + wektory), reranking,
- query rewriting, HyDE,
- RAG na tabelach i PDF-ach z układem, GraphRAG,
- ewaluacja retrievalu osobno od generacji (recall@k, MRR, faithfulness),
- koszty i cache.

Projekt: asystent po dokumentacji firmowej z zestawem testowym i metrykami.

### 2. Agenci od projektu do wdrożenia

Rozdział 9 pokazuje pętlę ReAct i przegląd frameworków.

Do pogłębienia:
- projektowanie narzędzi (granularność, opisy, błędy zwracane modelowi),
- maszyny stanów i grafy (LangGraph),
- planowanie i dekompozycja zadań,
- pamięć krótko- i długoterminowa,
- human-in-the-loop,
- sandboxing wykonania kodu,
- wzorce wieloagentowe z realnym porównaniem kosztu,
- tryby awarii (pętle, halucynowane narzędzia) i jak je łapać.

Projekt: agent operacyjny wykonujący wieloetapowe zadanie z odzyskiwaniem po błędach.

### 3. Ewaluacje i obserwowalność jako inżynieria

Rozdział 12 to wstęp; to umiejętność, która najbardziej odróżnia juniora od mida.

Do pogłębienia:
- budowanie golden setu,
- LLM-as-judge z kalibracją do ocen ludzkich,
- ewaluacje offline i online,
- testy regresyjne promptów w CI,
- tracing (OpenTelemetry, Langfuse),
- koszt i latencja jako metryki pierwszej klasy,
- A/B na promptach,
- monitoring dryfu jakości po zmianie modelu.

Projekt: harness ewaluacyjny podpięty pod projekt z książki 1 lub 2.

### 4. Bezpieczeństwo aplikacji LLM

Rozdział 11 daje listę kontrolną.

Do pogłębienia:
- taksonomia prompt injection (direct, indirect, przez narzędzia i dokumenty),
- guardrails wejścia i wyjścia,
- red teaming z automatyzacją,
- izolacja uprawnień agentów i serwerów MCP,
- PII i DLP,
- OWASP Top 10 for LLM z przykładami ataku i obrony w kodzie.

Projekt: zaatakować i zabezpieczyć własnego agenta.

### 5. Fine-tuning i modele otwarte

W pierwszej książce fine-tuning to podsekcja rozdziału 5.

Do pogłębienia:
- kiedy fine-tuning naprawdę wygrywa z RAG i promptowaniem,
- przygotowanie danych,
- LoRA i QLoRA,
- distillation z dużego modelu do małego,
- kwantyzacja,
- serwowanie (vLLM, Ollama, TGI),
- ewaluacja po treningu,
- koszty GPU.

Projekt: mały model dostrojony do jednego wąskiego zadania, porównany z API.

### 6. Context engineering i pamięć

Rozdział 4 jest dobrym wstępem, temat rośnie szybko.

Do pogłębienia:
- architektury pamięci (epizodyczna, semantyczna, proceduralna),
- kompresja i podsumowywanie kontekstu,
- prompt caching i jego wpływ na projekt systemu,
- zarządzanie kontekstem w długich sesjach agentowych,
- wzorce typu „plik jako pamięć”.

Nadaje się na krótszą pozycję albo na połączenie z książką o agentach.

### 7. MCP od środka

Rozdział 10 uczy budować serwer i klienta.

Do pogłębienia:
- autoryzacja OAuth dla serwerów zdalnych,
- zasoby i prompty (nie tylko narzędzia),
- sampling i elicitation,
- testowanie serwerów,
- publikacja do rejestru,
- projektowanie narzędzi z myślą o tym, jak model je wybiera.

Raczej ok. 40 stron niż osobna książka.

### 8. Aplikacja LLM jako system produkcyjny

Temat przekrojowy, którego w pierwszej książce nie ma wcale.

Do pogłębienia:
- streaming end-to-end,
- obsługa rate limitów i retry,
- routing między modelami i fallbacki,
- cache semantyczny,
- kolejki i zadania asynchroniczne,
- strukturyzowane wyjścia i walidacja,
- wersjonowanie promptów,
- koszt per użytkownik,
- wdrożenie i skalowanie.

Projekt: jedna usługa od endpointu do metryk w produkcji.

## Czego nie robić

Multimodalność i narzędzia do kodowania (rozdziały 13 i 14) starzeją się najszybciej i mają najmniej „inżynierii” do pogłębienia. Prompt engineering jako osobna książka też się nie broni, bo w praktyce rozpuszcza się w ewaluacjach i context engineeringu.

## Sugerowana kolejność

1. RAG w produkcji
2. Agenci
3. Ewaluacje i obserwowalność

Te trzy tworzą spójną ścieżkę i można je oprzeć na jednym rozrastającym się projekcie, co daje czytelnikowi jeden system oglądany z coraz bliższej odległości.

4. Bezpieczeństwo
5. System produkcyjny
6. Fine-tuning na końcu, bo jest najdroższy w praktyce i najrzadziej potrzebny.

Context engineering i MCP: jako krótsze pozycje albo dołączone do książki o agentach.
