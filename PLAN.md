# Plan książki „AI Engineer. Praktyczny przewodnik po roadmapie roadmap.sh/ai-engineer”

Źródło struktury: https://roadmap.sh/ai-engineer (JSON: https://roadmap.sh/ai-engineer.json, 22 tematy, 167 podtematów).
Zasady pisania: BRIEF.md. Skład: `.venv/bin/python build/build.py` → build/book.pdf (Markdown → HTML → headless Chrome, KaTeX dla wzorów).

| Nr | Plik | Tytuł | Strony (cel) | Status |
|---|---|---|---|---|
| 1 | chapters/01-wprowadzenie.md | Kim jest AI Engineer | 5 | gotowy |
| 2 | chapters/02-jak-dzialaja-llm.md | Jak działają LLM-y | 8 | gotowy |
| 3 | chapters/03-prompt-engineering.md | Prompt engineering | 14 | gotowy |
| 4 | chapters/04-context-engineering.md | Context engineering | 10 | gotowy |
| 5 | chapters/05-modele-i-platformy.md | Modele i platformy (typy modeli, closed/open, self-hosting, wybór, katalog, HF, Ollama, LM Studio, OpenRouter, API & SDK) | 12 | gotowy |
| 6 | chapters/06-embeddingi.md | Embeddingi | 7 | gotowy |
| 7 | chapters/07-bazy-wektorowe.md | Bazy wektorowe | 8 | gotowy |
| 8 | chapters/08-rag.md | RAG | 12 | – |
| 9 | chapters/09-agenci.md | Agenci AI | 12 | – |
| 10 | chapters/10-mcp.md | Model Context Protocol | 8 | – |
| 11 | chapters/11-bezpieczenstwo.md | Bezpieczeństwo i etyka | 7 | – |
| 12 | chapters/12-obserwowalnosc-i-ewaluacje.md | Obserwowalność, ewaluacje, testy regresyjne | 10 | – |
| 13 | chapters/13-multimodalnosc.md | Multimodalność | 7 | – |
| 14 | chapters/14-narzedzia.md | Narzędzia AI do kodowania | 3 | – |

Węzły roadmapy per rozdział: patrz blok „Z roadmapy” na początku każdego pliku; dla nienapisanych rozdziałów lista w analizie z sesji 2026-09-16 (sekcje JSON roadmapy).

## Ustalenia z pierwszych trzech rozdziałów (2026-09-16)

- Dokumentacja Anthropic przeniosła się na platform.claude.com, OpenAI na developers.openai.com/api/docs. Agenci mają używać tych adresów.
- `temperature`/`top_p`/`top_k` są wycofane na modelach po Claude Opus 4.6 i na flagowcach OpenAI; rolę pokrętła przejął `effort`. Przykłady samplowania idą na `claude-haiku-4-5`.
- Identyfikatory modeli używane w książce: `claude-opus-5` (domyślny), `claude-haiku-4-5` (sampling), `gpt-6-astra`.
- Agenci nie mają kluczy API, więc wyniki wywołań API są opisane w prozie albo oznaczone jako „Przykładowy wynik”. Wyniki lokalne (tiktoken, numpy) są realnie uruchomione.
- Dobór modeli agentów: rozdziały opisowe → Sonnet, rozdziały z kodem i researchem → Opus.

## Stan na 2026-09-16 wieczór (sesja przerwana limitem)

Rozdziały 1–7 gotowe i przejrzane. Rozdziały 8–14 pisali równolegle subagenci (Opus; 14 na Sonnet) z promptami opisanymi poniżej w skrócie. Jeśli plik rozdziału istnieje i kończy się sekcją `## Źródła`, uznaj go za napisany, ale nieprzejrzany: sprawdź nagłówki, brak dywizów jako myślników, brak cyrylicy, oznaczenie „Przykładowy wynik:” przy nieuruchomionych wywołaniach API. Jeśli pliku brak albo jest urwany, uruchom agenta od nowa.

Węzły roadmapy per brakujący rozdział:
- 8 RAG: What are RAGs?, RAGs, RAG Usecases, RAG vs Fine-tuning; Implementing RAG: Chunking, Embedding, Vector Database, Retrieval Process, Generation; Ways of Implementing RAG: Using SDKs Directly, Langchain, Llama Index, Haystack, RAGFlow. Snippety na sentence-transformers + Qdrant :memory: (spójnie z 6 i 7), cross-encoder rerank, citations Anthropic.
- 9 Agenci: AI Agents, Agents Usecases, ReAct Prompting, Tools & Function Calling, Multi-agents; Building AI Agents: Manual Implementation, OpenAI AgentKit & Agent SDK, Claude Agent SDK, Vertex AI Agent Builder, Google ADK. Ręczna pętla agenta na SDK anthropic, tool_runner, orkiestrator–pracownicy.
- 10 MCP: Model Context Protocol (MCP), MCP; Core Components: MCP Host, MCP Client, MCP Server, Data Layer, Transport Layer; Building an MCP Server, Building an MCP Client, Connect to Local Server, Connect to Remote Server. FastMCP serwer + klient uruchomione lokalnie, MCP connector Anthropic, konfiguracja Claude Code.
- 11 Bezpieczeństwo: AI Safety and Ethics; Prompt Injection Attacks, Security and Privacy Concerns, Bias and Fairness; Content Moderation APIs, Adding end-user IDs in prompts, Conducting adversarial testing, Robust prompt engineering, Know your Customers / Usecases, Constraining outputs and inputs.
- 12 Obserwowalność i ewaluacje: Tracing & logging, Cost/latency monitoring, Production monitoring; LangSmith, Langfuse, Helicone, Arize AI; LLM Evaluations; Deterministic Evals, Model-Based Evals, Human Evals, Evaluation Metrics; DeepEval, RAGAS; Regression Testing.
- 13 Multimodalność: Multimodal AI, Multimodal AI Usecases; Image Understanding, Image Generation, Video Understanding, Audio Processing, Text-to-Speech, Speech-to-Text; OpenAI Vision API, DALL-E API, NanoBanana API, Whisper API, Hugging Face Models, LangChain for Multimodal Apps, LlamaIndex for Multimodal Apps.
- 14 Narzędzia: Development Tools; Claude Code, Gemini, Codex, Cursor, Devin, Replit; Vibe Coding. Ostatni rozdział, zamyka książkę sekcją „Co dalej po tej książce”.

Do zrobienia po rozdziałach: krótki `chapters/00-wstep.md` (dla kogo książka, jak korzystać z kodu, konwencje), finalny skład `.venv/bin/python build/build.py`, przegląd PDF (tabele, wzory), aktualizacja tej tabeli statusów.
