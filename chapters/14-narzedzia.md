# Rozdział 14. Narzędzia AI do kodowania

> **Z roadmapy:** Development Tools, AI Assisted Coding Tools, Claude Code, Gemini, Codex, Cursor, Devin, Replit, Vibe Coding
>
> **Pakiety:** brak

Przez cały ten podręcznik AI Engineer był kimś, kto buduje produkty na bazie modeli językowych. W tym rozdziale model językowy trafia po drugiej stronie klawiatury: staje się narzędziem, którym piszesz kod, a nie tylko komponentem, który wbudowujesz w cudzy system. To zamyka pętlę – umiejętności z poprzednich trzynastu rozdziałów, prompt engineering, kontekst, agentowość, MCP, ewaluacja, przydają się nie tylko wtedy, gdy projektujesz cudzy system, ale też wtedy, gdy codziennie korzystasz z agenta kodującego we własnym terminalu.

Te narzędzia rozwijały się w trzech wyraźnych generacjach. Pierwsza to autouzupełnianie – podpowiedzi kolejnych linii w edytorze, bez rozumienia całego projektu, bez możliwości wykonania czegokolwiek. Druga to czat w IDE: rozmawiasz z modelem o swoim kodzie, dostajesz sugestie i diffy, ale to Ty klikasz „zastosuj”. Trzecia, dominująca dziś, to agent działający w terminalu albo w IDE, który samodzielnie czyta kod, planuje wieloetapowe zmiany, uruchamia komendy, testy i polecenia gita, i wraca do Ciebie dopiero z gotowym wynikiem albo pytaniem o decyzję, której nie powinien podejmować sam. Ta trzecia generacja zmienia jednostkę pracy z „linijki kodu” na „zadanie” – opisujesz cel, agent wykonuje kroki, Ty weryfikujesz rezultat, a nie każdy krok po drodze.

Ta zmiana ma konkretne pułapki, do których będziemy wracać w dalszej części rozdziału. Przegląd kodu przestaje być formalnością, bo agent potrafi wygenerować setki linijek zmian w jednej turze – łatwo je zaakceptować bez faktycznego przeczytania. Agent z dostępem do terminala i plików projektu ma też dostęp do wszystkiego, co tam leży, łącznie z plikami `.env` i kluczami API, więc bezpieczeństwo sekretów przestaje być czysto teoretycznym tematem z rozdziału 11. Wreszcie koszt: sesja agentowa, która sama iteruje, czyta pliki i uruchamia narzędzia, zużywa znacznie więcej tokenów niż pojedyncze zapytanie do czatu, a to przekłada się wprost na rachunek albo na zużycie limitu w abonamencie.

## Przegląd narzędzi

Poniższa tabela porównuje sześć najczęściej spotykanych narzędzi agentowych do kodowania. Ceny i limity sprawdziłem w oficjalnej dokumentacji dostawców (stan na wrzesień 2026) – w tej kategorii zmieniają się miesiącami, nie latami, więc traktuj je jako punkt odniesienia, nie ostateczną prawdę.

| Narzędzie | Forma | Model(e) | Tryb autonomii | MCP | Cena wejściowa | Dla kogo |
|---|---|---|---|---|---|---|
| Claude Code (Anthropic) | CLI, wtyczki VS Code i JetBrains, desktop app, przeglądarka | modele Claude (w książce: `claude-opus-5` domyślnie) | tryby uprawnień: Auto (klasyfikator akceptuje większość akcji, domyślny na planach Pro/Max/Team) i Manual; przełączanie `Shift+Tab` | natywne, `claude mcp add`, transporty HTTP, SSE, stdio, WebSocket | Pro 20 USD/mies. (17 USD/mies. przy rozliczeniu rocznym) lub Max od 100 USD/mies.; też płatność per token przez Claude Console | developerzy pracujący w terminalu, chcący jednego narzędzia na wielu maszynach i urządzeniach |
| Gemini (CLI + Code Assist) | CLI (open source, terminal) + Code Assist (wtyczka IDE) | Gemini 3, okno kontekstu do 1 mln tokenów | Gemini CLI: tryb non-interaktywny (`-p`, `--output-format json`); Code Assist: agentic chat z narzędziami | Gemini CLI: `~/.gemini/settings.json`; Code Assist: natywna integracja MCP | Gemini CLI: darmowy z limitem 60 zapytań/min i 1000/dzień; Code Assist Standard 19 USD/stanowisko/mies. rocznie (22,80 USD miesięcznie) | Gemini CLI: indywidualni developerzy; Code Assist: zespoły w ekosystemie Google Cloud |
| Codex (OpenAI) | CLI, rozszerzenie IDE, chmura w ramach ChatGPT | modele rozumujące OpenAI (w książce: `gpt-6-astra`) | tryby sandboksa (read-only, workspace-write, danger-full-access, egzekwowane na poziomie jądra) i tryby akceptacji (untrusted, on-request, never) | klient MCP przez komendę `codex mcp`; osobny serwer MCP eksponujący Codeksa został wycofany | wliczony w plany ChatGPT: Free, Go 8 USD/mies., Plus 20 USD/mies., Pro od 100 USD/mies. | użytkownicy już płacący za ChatGPT, chcący jednego rachunku za czat i kodowanie |
| Cursor | IDE (fork VS Code) | ponad 40 modeli od Anthropic, OpenAI, Google i innych, przełączanych per zapytanie | Agent mode i Tab; domyślnie Auto-review (klasyfikator ocenia akcje), opcjonalnie pełne YOLO mode bez pytań | `.cursor/mcp.json` (projekt) lub `~/.cursor/mcp.json` (globalnie) | Hobby darmowy, Pro 20 USD/mies., Pro+ 60 USD/mies., Ultra 200 USD/mies. | developerzy chcący wyboru modelu i pracy w jednym, dedykowanym IDE |
| Devin (Cognition) | agent chmurowy: przeglądarka (app.devin.ai) z wbudowanym IDE, Slack/Teams, CLI | nieujawniony publicznie | w pełni autonomiczny na zgłoszeniach i tiketach; można podejrzeć postęp i przejąć kontrolę w dowolnym momencie | brak jasno udokumentowanego wsparcia w publicznych materiałach | rozliczenie w ACU (Agent Compute Unit, około 15 minut pracy agenta); cennik zmieniał się w 2026, wejście zespołowe od około 80 USD/mies. | zespoły inżynierskie z zaległym backlogiem (Linear, Jira), rzadziej pojedynczy developer |
| Replit Agent | część przeglądarkowego IDE Replit | tryby jakości Power (modele średniej klasy) i Max (modele frontier), plus tryb planowania | iteracyjny: pisze kod, konfiguruje infrastrukturę, testuje, tworzy checkpointy pozwalające cofnąć się do wcześniejszego stanu | integracje z BigQuery, Slack, Notion, Linear (poza standardowym MCP) | Starter darmowy, Core około 20–25 USD/mies. (20 USD kredytów w cenie), Pro 100 USD/mies.; rozliczenie effort-based, per checkpoint | osoby bez doświadczenia programistycznego i zespoły chcące szybkich prototypów end-to-end |

Claude Code wyróżnia się tym, że to jeden silnik agentowy dostępny na wielu powierzchniach naraz – terminal, IDE, aplikacja desktopowa, przeglądarka, a nawet telefon przez przekazanie sesji – i wszystkie współdzielą te same pliki `CLAUDE.md`, ustawienia i serwery MCP. Ma wbudowaną koncepcję podagentów, hooków, „skilli” i harmonogramowanych zadań w chmurze (routines), więc nadaje się nie tylko do pojedynczej sesji, ale do budowania wokół siebie całych zautomatyzowanych przepływów. Domyślny tryb Auto ogranicza liczbę pytań o zgodę, oddając wstępną ocenę bezpieczeństwa akcji klasyfikatorowi, ale zostawia Ci pełną kontrolę przez przełączanie trybów jednym klawiszem.

Gemini pod tym węzłem roadmapy oznacza dziś w praktyce dwa różne produkty. Gemini CLI to otwarty kod źródłowy, darmowe narzędzie terminalowe z bardzo szerokim oknem kontekstu i hojnym darmowym limitem zapytań – dobre na start bez żadnych kosztów. Gemini Code Assist to osobna wtyczka IDE, rozliczana per stanowisko, kierowana do firm już w ekosystemie Google Cloud. Warto odnotować zmianę: warstwa „Individual” Code Assista została wycofana w połowie 2026 roku na rzecz osobnego produktu Antigravity, więc dziś granica między darmowym CLI a płatnym Code Assistem jest ostrzejsza niż jeszcze rok wcześniej.

Codex wyróżnia się ścisłą integracją z abonamentem ChatGPT – nie płacisz za niego osobno, tylko korzystasz z limitu wiadomości, który już masz. Model bezpieczeństwa opiera się na dwóch niezależnych osiach: piaskownicy egzekwowanej na poziomie systemu operacyjnego (co agent w ogóle może zrobić) i polityce akceptacji (kiedy pyta Cię o zgodę), co daje precyzyjniejszą kontrolę niż pojedynczy przełącznik „autonomiczny/nie”. To Codex spopularyzował konwencję pliku `AGENTS.md` jako miejsca na instrukcje projektowe, którą przejęły potem inne narzędzia, w tym Cursor jako alternatywę dla własnego formatu.

Cursor różni się tym, że to osobne środowisko programistyczne, a nie dodatek do terminala – dostajesz pełny fork VS Code z wbudowanym przełącznikiem modeli, więc do jednego zadania możesz wziąć tańszy model, a do trudniejszego refaktoru droższy, bez zmiany narzędzia. Domyślny tryb pracy, Auto-review, przepuszcza znane bezpieczne wywołania od razu, resztę kieruje do subagenta-klasyfikatora oceniającego ryzyko, co według dokumentacji producenta radykalnie zmniejsza liczbę pytań o zgodę względem starszego modelu akceptacji. Reguły projektowe trzymasz w katalogu `.cursor/rules` jako osobne pliki `.mdc` z metadanymi, a nie w jednym monolitycznym pliku `.cursorrules`, który ten mechanizm zastąpił.

Devin różni się celem, nie tylko formą: to nie asystent do pracy obok Ciebie, tylko agent, któremu zlecasz tiket i wracasz po godzinach. Rozliczenie w jednostkach obliczeniowych (ACU) zamiast prostego abonamentu odzwierciedla to, że zadania mogą trwać różnie długo i angażować różną moc obliczeniową. Devin jest budowany z myślą o zespołach zarządzających kolejką pracy w Linear czy Jirze, a nie o pojedynczym developerze piszącym kod w danej chwili – to najbardziej „menedżerskie” z opisywanych tu narzędzi.

Replit Agent jako jedyny z tej listy celuje wprost w osoby bez doświadczenia programistycznego, budując całe aplikacje od pomysłu do wdrożenia w jednym środowisku przeglądarkowym, bez lokalnej instalacji czegokolwiek. Rozliczenie effort-based, per checkpoint, jest nietypowe – nie znasz ceny zanim zadanie się nie wykona, co bywa zaskakujące przy bardziej złożonych krokach. Skoro hosting i wdrożenie są częścią tego samego środowiska, znika typowy krok „teraz to wdrożę” – aplikacja jest online, zanim skończysz opisywać kolejną funkcję.

## Jak pracować z agentem kodującym

Niezależnie od tego, które narzędzie wybierzesz, kilka praktyk działa wszędzie tam, gdzie agent sam pisze i wykonuje kod. Pierwsza to plik z kontekstem projektu, czytany automatycznie na starcie każdej sesji: `CLAUDE.md` w Claude Code, `AGENTS.md` jako konwencja przyjęta przez Codeksa i coraz szerzej (w tym jako fallback w Cursorze), albo `.cursor/rules/*.mdc` w samym Cursorze. Taki plik to nie dokumentacja dla ludzi, tylko instrukcja dla agenta: stos technologiczny, konwencje nazewnictwa, czego nie wolno ruszać, jakimi komendami uruchomić testy i linter.

```markdown
# Project context

Stack: Python 3.12, FastAPI, PostgreSQL, pytest.
Package manager: uv (never pip install directly).

## Conventions
- Type hints required on all public functions.
- Business logic lives in `services/`, not in route handlers.
- New endpoints need a pytest test in `tests/` before merge.

## Commands
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`

## Do not
- Do not modify files under `migrations/` by hand.
- Do not commit secrets; use `.env` (already gitignored).
```

Druga praktyka to rozmiar zadania. Agentowi zlecaj jedną, konkretną zmianę z jasnym kryterium „done” – „dodaj endpoint X, zwróć 404 gdy zasób nie istnieje, dodaj test” działa lepiej niż „popraw API użytkowników”. Im mniejsze zadanie, tym łatwiej zweryfikować wynik i tym mniejsza szansa, że agent zboczy w stronę zmian, o które nie prosiłeś. Testy w tym układzie pełnią rolę kontraktu: jeśli masz testy przed zleceniem zadania, agent ma jasne kryterium sukcesu i sam może je uruchomić, zamiast czekać na Twoją ręczną weryfikację.

Przegląd diffów zostaje Twoim obowiązkiem, nawet jeśli narzędzie działa w trybie ograniczającym liczbę pytań o zgodę. Klasyfikator w Cursorze czy tryb Auto w Claude Code decydują, czy dana komenda jest wystarczająco bezpieczna, żeby wykonać ją bez pytania – nie oceniają, czy wynikowy kod jest dobry. Te dwie rzeczy są niezależne, a druga wciąż należy do Ciebie. Z tego samego powodu warto świadomie dobierać uprawnienia i piaskownicę: tryb w pełni autonomiczny (YOLO w Cursorze, `danger-full-access` w Codeksie) ma sens w izolowanym środowisku na projekcie eksperymentalnym, nie na repozytorium produkcyjnym z dostępem do prawdziwych poświadczeń.

MCP, opisany szczegółowo w rozdziale 10, w narzędziach kodujących pełni rolę rozszerzenia – to przez MCP agent dostaje dostęp do Twojego trackera zadań, bazy danych czy dokumentacji wewnętrznej, zamiast zgadywać na podstawie samego kodu. Każdy z sześciu opisanych tu narzędzi ma własny format konfiguracji serwerów, ale mechanizm pod spodem jest ten sam protokół. Koszty i limity wreszcie: sesja agentowa czyta wiele plików i uruchamia wiele komend, więc zużywa więcej tokenów niż pojedynczy prompt do czatu – warto obserwować limity swojego planu, zanim zaplanujesz na nich cały sprint.

```bash
# instalacja Claude Code (macOS, Linux, WSL)
curl -fsSL https://claude.ai/install.sh | bash

# start sesji w katalogu projektu
cd my-project
claude

# dodanie serwera MCP (transport HTTP, zakres projektu)
claude mcp add --transport http --scope project github \
  https://api.githubcopilot.com/mcp/ \
  --header "Authorization: Bearer $GITHUB_TOKEN"

# jednorazowe zapytanie bez trybu interaktywnego, np. w CI
claude -p "review uncommitted changes for security issues"
```

## Vibe coding

Vibe coding to nazwa dla pracy, w której opisujesz efekt w naturalnym języku i akceptujesz kolejne wersje kodu na podstawie tego, czy działają, bez czytania każdej linijki po drodze – termin spopularyzowany w środowisku programistów korzystających z narzędzi takich jak Cursor, Codex czy Claude Code do szybkiego prototypowania. Roadmap.sh poświęca mu osobną roadmapę, bo to nie jest technika programistyczna w tradycyjnym sensie, tylko styl pracy z zupełnie innym zestawem kompromisów niż reszta tej książki – stąd osobny temat, a nie kolejny podrozdział o narzędziach.

Ten styl sprawdza się tam, gdzie koszt błędu jest niski, a szybkość ważniejsza od precyzji: prototypy do walidacji pomysłu, jednorazowe skrypty, wewnętrzne narzędzia bez użytkowników zewnętrznych, nauka nowego frameworka przez eksperymentowanie. Nie sprawdza się w kodzie produkcyjnym bez przeglądu – dokładnie te elementy, które w vibe codingu świadomie pomijasz, ewaluacja jakości, testy na reprezentatywnym zbiorze przypadków, kontrola bezpieczeństwa, są tematem rozdziałów 11 i 12 tej książki, i to nie przypadek. Vibe coding i praktyki AI Engineera z tej książki nie są sobie przeciwne, tylko odpowiadają na różne pytania: pierwszy optymalizuje czas do pierwszej działającej wersji, drugie optymalizują pewność, że system nadal działa za sześć miesięcy, na cudzych danych, pod obciążeniem.

## Co dalej po tej książce

To ostatni rozdział, więc zamiast wskazywać kolejny, warto powiedzieć, jak korzystać z całej mapy, którą przeszedłeś. Roadmapa roadmap.sh/ai-engineer, z której zbudowana jest ta książka, nie kończy się na czternastu rozdziałach – warto do niej wracać jako do listy kontrolnej, sprawdzając, które węzły pogłębiłeś praktyką, a które zostały na poziomie definicji. Nie musisz znać każdego elementu jednakowo dobrze: wybierz obszar bliski Twojej pracy (RAG, jeśli budujesz wyszukiwanie po dokumentach firmowych; agentów, jeśli automatyzujesz procesy wieloetapowe) i tam pogłębiaj wiedzę najpierw.

Najlepszym testem tego, czego się nauczyłeś, jest jeden projekt portfolio łączący kilka rozdziałów naraz: agent, który odpowiada na pytania na podstawie Twoich własnych dokumentów przez RAG (rozdziały 6 do 8), korzysta z narzędzi zewnętrznych przez MCP (rozdział 10), ma zestaw ewaluacji uruchamiany przy każdej zmianie promptu czy modelu (rozdział 12), i loguje wystarczająco dużo, żebyś widział, dlaczego dana odpowiedź wypadła słabo (ten sam rozdział, sekcja o obserwowalności). Taki projekt, nawet mały, pokazuje pracodawcy albo samemu sobie, że rozumiesz nie tylko pojedyncze API, ale całość: koszt, jakość, bezpieczeństwo.

Wiedza w tym obszarze starzeje się w miesiącach, nie w latach, co ten rozdział pokazał dosłownie – część opisanych tu cen i planów zmieni się, zanim skończysz czytać następny rozdział innej książki. Śledź zmiany bezpośrednio u źródła: dokumentację dostawców (platform.claude.com, developers.openai.com, ai.google.dev), ich changelogi i blogi produktowe, oraz samą roadmapę na roadmap.sh, która jest aktualizowana w miarę jak pojawiają się nowe węzły. Nawyk sprawdzania dokumentacji zamiast polegania na pamięci, który towarzyszył pisaniu każdego rozdziału tej książki, jest ostatecznie najbardziej przenośną umiejętnością, jaką z niej wynosisz.

## Podsumowanie

- Narzędzia AI do kodowania przeszły trzy generacje: autouzupełnianie, czat w IDE, autonomiczny agent w terminalu lub IDE wykonujący wieloetapowe zadania.
- Agentowa praca zmienia jednostkę zlecenia z linijki kodu na zadanie z kryterium „done”, ale nie zwalnia Cię z przeglądu diffów, kontroli sekretów i pilnowania kosztów.
- Claude Code, Gemini, Codex, Cursor, Devin i Replit Agent różnią się formą (terminal, IDE, chmura), modelem rozliczeń i stopniem autonomii, a nie tylko marką.
- Węzeł „Gemini” oznacza dziś dwa produkty: darmowy, open source’owy Gemini CLI i płatny Gemini Code Assist dla firm, po wycofaniu warstwy indywidualnej w połowie 2026 roku.
- Plik z kontekstem projektu (`CLAUDE.md`, `AGENTS.md`, `.cursor/rules`) i jasno zdefiniowane, małe zadania z testami jako kontraktem to praktyki niezależne od wybranego narzędzia.
- MCP, opisany w rozdziale 10, jest wspólnym mechanizmem rozszerzania agentów kodujących o dostęp do trackerów zadań, baz danych i dokumentacji firmowej.
- Vibe coding sprawdza się w prototypach i narzędziach jednorazowych, nie w kodzie produkcyjnym bez przeglądu – tam wracają ewaluacja i bezpieczeństwo z rozdziałów 11 i 12.
- Najlepszym sposobem utrwalenia całej książki jest jeden projekt portfolio łączący RAG, agenta, MCP, ewaluacje i obserwowalność, oraz nawyk śledzenia dokumentacji dostawców zamiast polegania na pamięci.

## Źródła

- https://code.claude.com/docs/en/overview
- https://code.claude.com/docs/en/quickstart
- https://code.claude.com/docs/en/mcp
- https://claude.com/pricing
- https://github.com/google-gemini/gemini-cli
- https://codeassist.google/
- https://docs.cloud.google.com/gemini/docs/codeassist/overview
- https://github.com/openai/codex
- https://learn.chatgpt.com/docs/codex/cli
- https://learn.chatgpt.com/docs/pricing
- https://cursor.com/docs
- https://cursor.com/docs/context/rules
- https://cursor.com/docs/context/mcp
- https://cursor.com/docs/agent/security/run-modes
- https://cursor.com/pricing
- https://devin.ai/
- https://docs.devin.ai/
- https://docs.replit.com/replitai/agent
- https://roadmap.sh/vibe-coding
