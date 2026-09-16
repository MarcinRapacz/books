# Wstęp

Ta książka jest przewodnikiem po roadmapie „AI Engineer" z serwisu roadmap.sh. Roadmapa to mapa: 22 tematy główne i ponad 160 podtematów ułożonych w kolejności, w jakiej warto się ich uczyć, ale przy każdym węźle jest tylko akapit i lista linków. Książka wypełnia tę mapę treścią. Każdy rozdział odpowiada fragmentowi roadmapy, zaczyna się od listy węzłów, które pokrywa, i kończy podsumowaniem oraz wskazówką, co zrobić samodzielnie.

## Dla kogo

Piszemy dla programisty, który zna Pythona i budował już backendy, ale nie tworzył jeszcze systemów opartych na modelach językowych. Nie zakładamy wiedzy z uczenia maszynowego: rozdział 2 tłumaczy, jak działa model na tyle, na ile potrzebuje tego inżynier, i nie głębiej. Zakładamy natomiast, że umiesz uruchomić skrypt, zainstalować pakiet i przeczytać dokumentację API.

Jeśli już budujesz aplikacje na LLM-ach, rozdziały 1 i 2 możesz przekartkować. Rozdziały 3 i 4 (prompt engineering i context engineering) warto przeczytać w całości nawet wtedy, bo porządkują pojęcia, do których wracamy w każdym kolejnym rozdziale.

## Jak ułożona jest książka

Rozdziały układają się w cztery bloki. Pierwszy (rozdziały 1–5) to fundamenty: rola AI Engineera, mechanika modeli, prompty, kontekst, wybór modelu i platformy. Drugi (rozdziały 6–8) prowadzi od embeddingów przez bazy wektorowe do kompletnego systemu RAG. Trzeci (rozdziały 9–10) dotyczy agentów i protokołu MCP. Czwarty (rozdziały 11–14) to wszystko, co odróżnia prototyp od produktu: bezpieczeństwo, obserwowalność, ewaluacje, multimodalność i narzędzia, którymi sam będziesz pisać kod.

Rozdziały odsyłają do siebie nawzajem, ale każdy da się przeczytać osobno. Jeśli interesuje Cię tylko RAG, zacznij od rozdziału 8 i cofnij się do 6 i 7, gdy zabraknie Ci podstaw.

## Kod

Prawie każdy rozdział ma snippety w Pythonie. Zasady są stałe w całej książce:

- Każdy snippet jest kompletny: ma importy, czyta klucze API ze zmiennych środowiskowych (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) i da się uruchomić jako osobny plik.
- Na początku rozdziału jest blok „Pakiety" z poleceniem `pip install` obejmującym wszystko, czego rozdział potrzebuje. Zalecamy osobne środowisko wirtualne na książkę. Przy pakietach ciągnących PyTorch (sentence-transformers, transformers) instaluj wersję CPU, chyba że masz kartę graficzną i wiesz, po co.
- Domyślnym SDK jest `anthropic`, drugim `openai`. Gemini pojawia się tam, gdzie roadmapa wprost go wymienia. Po stronie open source używamy `sentence-transformers`, Qdranta w trybie in-memory i FAISS, żeby przykłady działały bez serwera.
- Bloki „Wynik" po snippetach lokalnych pochodzą z prawdziwych uruchomień. Bloki po wywołaniach API są oznaczone jako „Przykładowy wynik", bo dokładne liczby zależą od modelu i dnia.
- Identyfikatory modeli, ceny, limity i nazwy parametrów były sprawdzane w oficjalnej dokumentacji dostawców we wrześniu 2026 i tak są opisane w tekście. Zanim wkleisz liczbę do kalkulacji budżetu, zajrzyj do cennika, bo to jedyna część tej książki, która na pewno się zdezaktualizuje.

## Jak powstała ta książka

Tekst został napisany z pomocą modeli Claude pod redakcją autora: każdy rozdział powstał na podstawie aktualnej dokumentacji dostawców, a snippety lokalne były uruchamiane przed umieszczeniem w tekście. Struktura i lista tematów pochodzą z roadmapy roadmap.sh, której autorem jest Kamran Ahmed i społeczność projektu developer-roadmap.
