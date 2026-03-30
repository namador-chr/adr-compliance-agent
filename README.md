# ADR Compliance Agent

An AI-Agentic system that checks C# .NET source code for compliance with Architectural Decision Records (ADRs).
Built as the Capstone Project for the **Ciklum AI Academy** Engineering Track.

---

## What it does

1. **Ingests** ADR markdown files, chunks them, embeds them with Gemini, and stores them in ChromaDB.
2. **Loads** C# source files into memory — full content, no chunking — so the LLM always sees the complete file.
3. **Retrieves** the most relevant ADR rules for each code file via semantic search over the ADR index.
4. **Analyses** each file using Gemini — producing a structured compliance report with violations and recommendations.
5. **Reflects** — the LLM self-critiques its own analysis for quality and missed issues.
6. **Orchestrates** the entire flow via a Gemini tool-calling agent loop (list → analyze → report).

---

## Project structure

```
.
├── data/
│   ├── adrs/           ← place your ADR .md files here
│   └── repo/           ← place your C# source files here
├── src/
│   ├── ingestion.py    ← file loading; chunking for ADRs only
│   ├── embeddings.py   ← Gemini embedding service
│   ├── vector_store.py ← ChromaDB (ADR collection only)
│   ├── analyzer.py     ← LLM compliance analysis + self-reflection
│   └── agent.py        ← agentic loop with Gemini tool-calling
├── main.py             ← CLI entry point
├── architecture.mmd    ← Mermaid architecture diagram
├── requirements.txt
└── .env.example
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd ard-compliance-agent

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY
```

Key variables:

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | Required |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite-preview` | LLM used for analysis |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `LLM_REQUEST_DELAY` | `4` | Seconds between LLM calls — set to `0` on paid tier |
| `TOP_K_RESULTS` | `5` | ADR chunks retrieved per file |

### 3. Add your data

- Drop ADR markdown files into `data/adrs/`
- Drop C# source files (`.cs`, `.csproj`, `.json`, `.xml`) into `data/repo/`

---

## Usage

```bash
# Run full analysis (always writes report.json)
python main.py

# Force re-ingestion (clears the ADR ChromaDB index and re-embeds)
python main.py --reingest

# Override the default output filename
python main.py --output my_report.json
```

---

## Technology stack

| Component       | Technology                          |
|-----------------|-------------------------------------|
| LLM             | Gemini 3.1 Flash Lite Preview (`google-genai`)   |
| Embeddings      | Gemini `gemini-embedding-001`         |
| Vector store    | ChromaDB (local persistent)         |
| Agent framework | Custom tool-calling loop            |
| Language        | Python 3.11+                        |
| Config          | `python-dotenv`                     |

---

## Architecture

See [architecture.mmd](architecture.mmd) for the full Mermaid diagram.
High-level flow:

```
CLI → ComplianceAgent
         ├── setup()  → ADRs: chunk → embed → ChromaDB
         │              code: load full files into memory
         └── run()    → Gemini tool-calling loop
                            ├── list_code_files   (reads memory)
                            ├── analyze_file × N  (memory + ChromaDB ADR search + LLM + reflection)
                            └── generate_final_report
```

**Why code files are not embedded:** compliance analysis requires the full file context. Chunking and embedding code would only surface fragments to the LLM, making it impossible to assess patterns that span the whole file (e.g. overall class structure, DI registration, error handling strategy). ADRs, by contrast, are rule definitions where retrieval of the most relevant subset is exactly the right approach.
