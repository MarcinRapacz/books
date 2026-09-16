# Rozdział 1. Kim jest AI Engineer

> **Z roadmapy:** What is an AI Engineer?, Roles and Responsiblities, Impact on Product Development, AI Engineer vs ML Engineer, AI vs AGI, Large Language Model (LLM), Embeddings, Training, Inference, Vector DBs, AI Agents, RAGs, Context Window, Fine-tuning, Prompt Engineering, Context Engineering
>
> **Pakiety:** brak

Jeszcze kilka lat temu, żeby dodać do aplikacji cokolwiek, co „rozumie" tekst, trzeba było albo zatrudnić zespół data science i wytrenować własny model, albo poprzestać na regułach i wyrażeniach regularnych. Dziś ten sam efekt – a często znacznie lepszy – dostajesz jednym wywołaniem API do modelu językowego (large language model, LLM). To właśnie ta zmiana, dostępność potężnych, gotowych modeli za cenę requestu HTTP, powołała do życia rolę AI Engineera: kogoś, kto potrafi wziąć taki model i zbudować wokół niego działający, bezpieczny i opłacalny produkt.

To zadanie różni się od typowego backendu bardziej, niż mogłoby się wydawać. W klasycznym systemie ta sama funkcja z tymi samymi argumentami zawsze zwraca ten sam wynik – testy jednostkowe zakładają ten determinizm jako oczywistość. Model językowy tej gwarancji nie daje: ten sam prompt może za każdym razem wygenerować nieco inną odpowiedź, a jakość tej odpowiedzi zależy od sformułowania pytania, długości i doboru kontekstu czy wręcz od wersji modelu, na której akurat działasz. AI Engineer projektuje systemy, które mimo tej niepewności działają przewidywalnie na poziomie produktu – nawet jeśli pojedyncza odpowiedź modelu przewidywalna nie jest.

Jeśli programujesz w Pythonie i budowałeś już backendy, ale nie miałeś jeszcze do czynienia z LLM-ami, ten rozdział jest twoim punktem startowym. Nie znajdziesz tu jeszcze ani linijki kodu – to zamierzone. Zanim sięgniemy po pierwsze API w rozdziale 2, potrzebujesz mapy pojęć i decyzji, z którymi będziesz się mierzyć w kolejnych rozdziałach. Traktuj ten rozdział jak słownik i punkt odniesienia, do którego będziesz wracać.

## Czym zajmuje się AI Engineer

Najkrótsza definicja brzmi tak: AI Engineer buduje produkty na bazie gotowych, wytrenowanych modeli (pre-trained models), zamiast trenować własne od zera. Bierze model językowy – dostępny przez API dostawcy takiego jak Anthropic czy OpenAI, albo uruchomiony lokalnie z Hugging Face – i integruje go z danymi firmy, narzędziami zewnętrznymi i interfejsem użytkownika tak, żeby powstało coś użytecznego. Ta praktyczność, „stosowanie" AI zamiast „tworzenia" AI, jest cechą definiującą tę rolę.

Typowy dzień pracy wygląda inaczej niż w czystym data science. Zamiast czyścić dane treningowe, projektujesz przepływ (flow) między wywołaniami modelu: jak podzielić duży dokument na fragmenty, co umieścić w prompcie systemowym, kiedy model powinien sięgnąć po narzędzie zewnętrzne, a kiedy odpowiedzieć wprost z pamięci. Sporo czasu zajmuje też to, co w klasycznym backendzie jest marginesem: obsługa błędów modelu, halucynacji, pustych lub nietrafionych odpowiedzi, oraz mierzenie, czy zmiana w prompcie faktycznie poprawiła jakość, czy tylko naprawiła jeden przykład kosztem dziesięciu innych.

Decyzje, które podejmuje AI Engineer, rzadko mają jedną oczywistą odpowiedź. Który model wybrać do danego zadania – droższy i dokładniejszy, czy tańszy i szybszy? Czy potrzebny jest RAG, czy wystarczy dobrze napisany prompt? Ile kontekstu przekazać modelowi, zanim koszt i czas odpowiedzi zaczną boleć? Jak w ogóle zmierzyć „czy to działa", skoro nie ma jednej poprawnej odpowiedzi do porównania? Odpowiedzi na te pytania wracają w kolejnych rozdziałach tej książki, jedno po drugim.

## Role i odpowiedzialności

Zakres obowiązków AI Engineera skupia się wokół kilku powtarzalnych elementów. Pierwszy to integracja modeli: wybór dostawcy, obsługa jego SDK, projektowanie promptów i formatu odpowiedzi. Drugi to wyszukiwanie oparte na wiedzy firmy, czyli RAG – łączenie bazy wektorowej, procesu wyszukiwania i generowania odpowiedzi w jeden spójny mechanizm. Trzeci to agenci: systemy, które nie tylko odpowiadają na pytanie, ale wykonują wieloetapowe zadania, korzystając z narzędzi i podejmując decyzje po drodze.

Za samą budową stoi odpowiedzialność, która w tradycyjnym backendzie bywa mniej widoczna. AI Engineer odpowiada za jakość i trafność odpowiedzi systemu – a więc za ewaluację (evaluation), czyli systematyczne sprawdzanie wyników na zbiorze przykładów, nie tylko „ręczne klikanie" w trakcie developmentu. Odpowiada też za koszty: każde wywołanie modelu to realny wydatek liczony od liczby tokenów, więc decyzje architektoniczne mają bezpośrednie przełożenie na rachunek od dostawcy. Do tego dochodzi bezpieczeństwo – ochrona przed wstrzyknięciem promptu (prompt injection), wyciekiem danych wrażliwych do modelu zewnętrznego czy generowaniem treści niezgodnych z polityką firmy.

W praktyce AI Engineer rzadko pracuje w izolacji. Ściśle współpracuje z osobami odpowiedzialnymi za dane i modele – jeśli te istnieją w zespole jako osobne role – z product ownerem definiującym, co właściwie oznacza „dobra odpowiedź" w kontekście danego produktu, oraz z zespołem odpowiedzialnym za infrastrukturę i monitoring produkcyjny. Jego rolą jest spięcie tych elementów w system, który da się utrzymać i rozwijać, a nie tylko zademonstrować raz na spotkaniu.

## Wpływ na rozwój produktu

Obecność niedeterministycznego komponentu w środku systemu zmienia sposób, w jaki prowadzi się projekt produktowy. W klasycznym podejściu funkcjonalność uznaje się za gotową, gdy przechodzi zestaw testów z jasno określonym oczekiwanym wynikiem. Przy komponencie opartym na LLM taki test w ogóle nie ma sensu dla większości zadań – nie istnieje jedna „poprawna" odpowiedź na pytanie otwarte, więc kryterium „zdał albo nie zdał" trzeba zastąpić czymś bardziej subtelnym.

Prototypowanie z LLM-ami jest paradoksalnie bardzo szybkie – działającą wersję demonstracyjną chatbota czy asystenta da się skleić w ciągu dnia, korzystając z gotowego API. To złudnie łatwy początek: droga od efektownego demo do wersji produkcyjnej okazuje się dłuższa niż w klasycznym oprogramowaniu, bo dopiero na tym etapie trzeba dodać brakujące elementy – ewaluację na reprezentatywnym zbiorze przypadków, obsługę przypadków brzegowych, mechanizmy zabezpieczające (guardrails) i plan awaryjny na wypadek, gdy model się myli albo odpowie czymś niepożądanym.

Z tego powodu ewaluacja staje się w projektach z LLM-ami częścią definicji „done", obok tradycyjnych testów. Zanim funkcję uzna się za gotową do wdrożenia, sprawdza się ją na zestawie przykładów reprezentujących realne zapytania użytkowników, z metrykami dopasowanymi do zadania – trafność, kompletność, brak halucynacji, koszt na zapytanie. Sam cykl pracy też się zmienia: przypomina bardziej eksperymentowanie znane z data science – postaw hipotezę o tym, co poprawi wynik, zmień prompt albo kontekst, zmierz efekt na całym zbiorze testowym, dopiero potem wdróż – niż liniowe „napisz kod, napisz test, scal".

## AI Engineer a ML Engineer

Te dwie role często się myli, bo obie pracują z modelami sztucznej inteligencji, ale ich punkt wyjścia i codzienne narzędzia są inne. AI Engineer konsumuje modele – bierze gotowy, gdzieś już wytrenowany model i buduje wokół niego produkt. ML Engineer te modele trenuje albo dostraja – zajmuje się danymi treningowymi, architekturą sieci, metrykami uczenia.

| Aspekt | AI Engineer | ML Engineer |
|---|---|---|
| Punkt wyjścia | gotowy, wytrenowany model (API lub open source) | surowe dane, model budowany lub dostrajany od podstaw |
| Narzędzia | SDK dostawców modeli, frameworki do RAG i orkiestracji agentów, bazy wektorowe | frameworki do treningu (np. PyTorch), pipeline'y danych, infrastruktura GPU |
| Praca z danymi | dane głównie jako kontekst zapytania – dokumenty, embeddingi | duże, oznaczone zbiory treningowe, walidacyjne i testowe |
| Cykl iteracji | prompt, kontekst, ewaluacja – iteracje liczone w godzinach lub dniach | zbieranie danych, trening, walidacja – iteracje liczone w dniach lub tygodniach |
| Miara sukcesu | jakość odpowiedzi w produkcie, koszt, latencja, satysfakcja użytkownika | metryki modelu: dokładność, F1, funkcja straty (loss) |
| Typowy efekt pracy | działająca funkcja lub usługa korzystająca z modelu | wytrenowany albo dostrojony model gotowy do udostępnienia |

Ten podział jest jednak coraz mniej ostry. AI Engineer sięga po fine-tuning, gdy prompt engineering i RAG przestają wystarczać – co omawiamy w rozdziale 8. Z drugiej strony ML Engineerzy coraz częściej sami zaczynają od gotowego modelu bazowego (foundation model) zamiast trenować sieć od zera, co upodabnia ich pracę do konsumowania modeli. W mniejszych zespołach obie role często wykonuje jedna osoba, przełączając się między nimi w zależności od zadania. Warto znać ten podział jako punkt odniesienia, ale nie traktować go jako sztywnej granicy stanowisk.

## Słownik pojęć, do których będziemy wracać

Poniższe dwanaście pojęć pojawi się w tej książce wielokrotnie. Tutaj dostajesz ich pierwszą, zwięzłą definicję – każde z nich rozwijamy osobno w dalszych rozdziałach, z kodem i przykładami.

### AI vs AGI

AI (sztuczna inteligencja) w praktycznym, dzisiejszym rozumieniu oznacza systemy wyspecjalizowane w konkretnym zadaniu: rozpoznawaniu obrazu, generowaniu tekstu, rekomendacjach. AGI (Artificial General Intelligence, ogólna sztuczna inteligencja) to hipotetyczny system zdolny uczyć się i rozumować w dowolnej dziedzinie na poziomie człowieka – dziś to pojęcie teoretyczne, nie inżynierska rzeczywistość. Cała ta książka dotyczy wąskiej AI, konkretnie modeli językowych i systemów budowanych wokół nich; AGI pojawia się tu wyłącznie jako punkt odniesienia w dyskusjach o możliwościach i ograniczeniach. Rozróżnienie tych dwóch pojęć pomaga trzeźwo oceniać, co narzędzia, z którymi pracujesz na co dzień, faktycznie potrafią.

### Large Language Model (LLM)

LLM (duży model językowy) to sieć neuronowa wytrenowana na ogromnych zbiorach tekstu, która w istocie przewiduje kolejny token na podstawie poprzedzającego kontekstu. Z tej pozornie prostej mechaniki wyłaniają się zdolności do tłumaczenia, streszczania, pisania kodu i prowadzenia rozmowy. Sam model nie ma dostępu do internetu ani nie wykonuje kodu – takie możliwości dokładają narzędzia i warstwy oprogramowania wokół niego. Zrozumienie mechaniki przewidywania kolejnego tokenu tłumaczy zarówno siłę LLM-ów, jak i ich typowe słabości, na przykład halucynacje czy wrażliwość na sformułowanie promptu. Szczegółowo LLM-y, tokeny i okno kontekstu omawiamy w rozdziale 2.

### Embeddings

Embedding to liczbowa reprezentacja tekstu, obrazu czy dźwięku w postaci wektora, w której bliskość w przestrzeni wielowymiarowej odpowiada bliskości znaczeniowej. Dwa zdania o podobnym sensie, nawet zapisane zupełnie innymi słowami, dostają wektory leżące blisko siebie – to podstawa wyszukiwania semantycznego (semantic search), w odróżnieniu od wyszukiwania po dokładnych słowach kluczowych. Embeddingi liczy osobny, zwykle znacznie mniejszy model niż ten generujący tekst. Techniczne detale liczenia i porównywania embeddingów, razem z kodem w Pythonie, poznasz w rozdziale 6.

### Training

Training (trenowanie) to proces, w którym model dostosowuje swoje wewnętrzne parametry, żeby minimalizować różnicę między swoimi przewidywaniami a rzeczywistymi danymi ze zbioru treningowego. Jako AI Engineer najprawdopodobniej nigdy nie wytrenujesz dużego modelu językowego od zera – wymaga to zasobów obliczeniowych dostępnych garstce firm na świecie. Warto jednak rozumieć ten proces, bo wyjaśnia ograniczenia modeli, z których korzystasz: datę odcięcia wiedzy, koszt powstania modelu i różnice między jego kolejnymi wersjami. Wątek treningu wraca przy okazji fine-tuningu w rozdziale 8 oraz przy wyborze modeli i platform w rozdziale 5.

### Inference

Inference (wnioskowanie) to moment, w którym już wytrenowany model dostaje nowe dane wejściowe i zwraca wynik – w przypadku LLM-a: odpowiedź na prompt. To właśnie inference kosztuje cię pieniądze przy każdym wywołaniu API i to jego czas odczuwasz jako latencję w swoim produkcie. W odróżnieniu od treningu, inference nie zmienia wag modelu – te same zapytanie i parametry dają, pomijając pewną losowość, zbliżony wynik za każdym razem. Praktyczne aspekty inference – wybór modelu, streaming odpowiedzi, koszt liczony w tokenach – wracają przy platformach modeli w rozdziale 5.

### Vector DBs

Baza wektorowa (vector database) to magazyn danych zoptymalizowany pod przechowywanie embeddingów i szybkie wyszukiwanie najbliższych sąsiadów w przestrzeni wielowymiarowej, zamiast dokładnego dopasowania jak w klasycznej bazie SQL. To komponent infrastrukturalny, na którym opiera się większość systemów wyszukiwania semantycznego i RAG. Wybór między bazą wektorową jako osobnym serwisem a rozszerzeniem istniejącej bazy danych o taką funkcję to jedna z pierwszych decyzji architektonicznych przy budowie takiego systemu. Instalację, indeksowanie i zapytania do konkretnej bazy wektorowej przećwiczysz w rozdziale 7.

### AI Agents

Agent to system zbudowany wokół LLM, który nie tylko odpowiada na pojedynczy prompt, ale samodzielnie planuje kolejne kroki, korzysta z narzędzi zewnętrznych i podejmuje decyzje na podstawie wyników poprzednich akcji, aż osiągnie zadany cel. W odróżnieniu od prostego wywołania modelu, pętla agenta jest wieloetapowa i częściowo autonomiczna – potężniejsza, ale trudniejsza do przewidzenia i przetestowania niż pojedyncze zapytanie. Budowa agentów to dziś jeden z głównych obszarów pracy AI Engineera, od prostych asystentów z dostępem do kilku funkcji po systemy wieloagentowe. Wzorce projektowe agentów, wywoływanie narzędzi i sterowanie ich zachowaniem poznasz w rozdziale 9.

### RAGs

RAG (Retrieval-Augmented Generation, generowanie wzbogacone o wyszukiwanie) łączy wyszukiwanie odpowiednich fragmentów wiedzy z generowaniem odpowiedzi przez LLM, zamiast polegać wyłącznie na tym, czego model nauczył się podczas treningu. Zapytanie użytkownika zamieniasz na embedding, wyszukujesz najbliższe fragmenty w bazie wektorowej, a następnie dołączasz je do promptu jako dodatkowy kontekst dla modelu. Dzięki temu odpowiedzi są aktualniejsze, oparte na twoich danych i łatwiejsze do zweryfikowania niż surowa wiedza modelu, bo widać, z jakiego źródła pochodzą. RAG jest dziś domyślnym sposobem podłączania LLM-a do prywatnych danych firmy – pełną architekturę takiego systemu, razem z fine-tuningiem jako alternatywą, budujemy krok po kroku w rozdziale 8.

### Context Window

Okno kontekstu (context window) to maksymalna ilość tekstu, mierzona w tokenach, którą model może przyjąć i przetworzyć w jednym zapytaniu – licząc razem prompt systemowy, historię rozmowy, dołączone dokumenty i generowaną odpowiedź. Kiedy suma przekracza limit, starsze lub mniej istotne fragmenty trzeba obciąć, streścić albo w inny sposób wyprowadzić poza aktywny kontekst. Większe okno kontekstu nie oznacza automatycznie lepszych odpowiedzi – model wciąż może gubić informacje umieszczone w środku długiego kontekstu. Zarządzaniu tym, co trafia do okna kontekstu, poświęcamy rozdział 4, a mechanikę tokenów i limitów tłumaczymy już w rozdziale 2.

### Fine-tuning

Fine-tuning (dostrajanie) polega na wzięciu gotowego, wytrenowanego modelu i douczeniu go na mniejszym, wyspecjalizowanym zbiorze danych, żeby lepiej radził sobie z konkretnym zadaniem lub stylem odpowiedzi. To rozwiązanie kosztowniejsze i wolniejsze do iterowania niż prompt engineering czy RAG, więc sięga się po nie zwykle dopiero wtedy, gdy te tańsze metody nie wystarczają. Decyzja „RAG czy fine-tuning" to jedna z częstszych rozmów architektonicznych, jakie prowadzi AI Engineer z zespołem. Kiedy fine-tuning ma sens i jak go przeprowadzić, pokazujemy w rozdziale 8 obok RAG, a wybór modelu bazowego do dostrajania wraca w rozdziale 5.

### Prompt Engineering

Prompt engineering to świadome projektowanie treści promptu – instrukcji, przykładów, formatu odpowiedzi – tak, by zwiększyć szansę na trafną i użyteczną odpowiedź modelu. To nie jednorazowa sztuczka, tylko iteracyjny proces: piszesz wersję promptu, sprawdzasz wyniki na zestawie przypadków, poprawiasz sformułowanie lub strukturę i mierzysz ponownie. Dobry prompt engineering wymaga rozumienia ograniczeń konkretnego modelu i wykorzystania technik takich jak przykłady w treści zapytania (few-shot) czy rozbicie zadania na mniejsze kroki. Pełny warsztat prompt engineeringu – wzorce, techniki, typowe błędy – jest tematem rozdziału 3.

### Context Engineering

Context engineering (inżynieria kontekstu) to pojęcie szersze niż prompt engineering – obejmuje nie tylko treść samego zapytania, ale całe środowisko informacyjne dostarczane modelowi: historię rozmowy, wyniki wywołań narzędzi, dokumenty z RAG, pamięć długoterminową i sposób, w jaki to wszystko jest ułożone i przycięte do okna kontekstu. W miarę jak systemy stają się bardziej agentowe i wieloetapowe, o jakości wyniku decyduje coraz częściej nie pojedynczy prompt, tylko to, co dokładnie trafia do modelu na każdym kroku jego pracy. Pojęcie to zyskało na znaczeniu wraz z rozwojem agentów – dobrze zaprojektowany kontekst bywa różnicą między agentem, który działa niezawodnie, a takim, który się gubi. Context engineering jako osobną dyscyplinę, z konkretnymi technikami zarządzania kontekstem, rozwijamy w rozdziale 4.

## Podsumowanie

- AI Engineer buduje produkty na bazie gotowych, wytrenowanych modeli – nie trenuje ich od zera, tym różni się od ML Engineera.
- Codzienna praca to integracja modeli, budowa RAG i agentów, projektowanie promptów i kontekstu, ewaluacja jakości oraz kontrola kosztów i bezpieczeństwa.
- Niedeterminizm modeli językowych zmienia proces produktowy: ewaluacja na zbiorze przykładów staje się częścią definicji „done", obok klasycznych testów.
- Prototyp z LLM-em powstaje szybko, ale droga od demo do produkcji jest dłuższa niż w klasycznym oprogramowaniu, bo dopiero tam dochodzą ewaluacja i zabezpieczenia.
- Granica między AI Engineerem a ML Engineerem zaciera się w praktyce, zwłaszcza w mniejszych zespołach, ale ich narzędzia, dane i miary sukcesu wciąż się różnią.
- AGI to punkt odniesienia teoretyczny, nie codzienne narzędzie pracy – ta książka koncentruje się na wąskiej AI, głównie modelach językowych.
- Dwanaście pojęć poznanych w tym rozdziale – od LLM po context engineering – to słownik, do którego wracamy w każdym kolejnym rozdziale, tym razem już z kodem.

## Co dalej

W rozdziale 2, „Jak działają LLM-y", wejdziesz pod maskę modelu językowego: zobaczysz, czym naprawdę jest token, jak działa przewidywanie kolejnych słów i dlaczego okno kontekstu ma twarde granice – wraz z pierwszymi wywołaniami API w Pythonie. Zanim tam przejdziesz, spisz dwa lub trzy zadania z własnej pracy, w które dziś wkładasz dużo ręcznej roboty związanej z tekstem – do nich będziesz wracać jako do przykładów w kolejnych rozdziałach, sprawdzając, które z poznanych technik faktycznie rozwiązują twój problem.
