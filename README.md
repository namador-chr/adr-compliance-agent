# ADR Compliance Agent

An AI agent that analyzes a C# codebase for compliance with Architecture Decision Records (ADRs).  
Now **LLM-agnostic** — works with Gemini or GPT4All via environment variables.

## Project Structure

```text
adr-compliance-agent/
├── config.py                  # Environment config and paths
├── tools.py                   # File I/O tools and LLM tool schemas
├── prompts.py                 # System instructions for LLM prompt phases
├── llm_clients.py             # Provider-specific SDKs and adapters
├── main.py                    # Python agent (entry point orchestrator)
├── architecture.mmd           # Mermaid diagram of agent workflow
├── compliance_report.md       # Generated after running the agent
└── data/
    ├── adrs/                  # Architecture Decision Records
    │   ├── ADR-001-restful-resource-naming.md
    │   ├── ADR-002-http-status-codes.md
    │   ├── ADR-003-structured-logging.md
    │   ├── ADR-004-input-validation.md
    │   └── ADR-005-separation-of-concerns.md
    └── repo/                  # Sample C# API with intentional ADR violations
        ├── Program.cs
        ├── Controllers/UsersController.cs
        ├── Services/IUserService.cs
        ├── Services/UserService.cs
        ├── Models/User.cs
        └── DTOs/
            ├── CreateUserRequest.cs
            └── UpdateUserRequest.cs
```

## Prerequisites

- Python 3.10+
- An API key for your chosen provider (not required for GPT4All)

## Provider Setup

Install the dependency for your chosen provider, then set the environment variables below.

### Gemini (default)

```bash
pip install google-genai
```

```powershell
$env:LLM_PROVIDER = "gemini"
$env:LLM_API_KEY  = "AIza..."     # from https://aistudio.google.com/app/apikey
# Optional: $env:LLM_MODEL = "gemini-2.0-flash"   # or gemini-2.5-flash, gemini-1.5-pro etc.
python main.py
```

---

### GPT4All (fully local — no API key required)

```bash
pip install gpt4all
```

```powershell
$env:LLM_PROVIDER = "gpt4all"
# Optional: $env:LLM_MODEL = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
python main.py
```

> **Note:** GPT4All will download the model (~4–8 GB) on first run.  
> GPT4All uses **ReAct-style** text-based tool calling (no native function calling).

---

## Environment Variables

| Variable       | Default     | Description                                              |
|----------------|-------------|----------------------------------------------------------|
| `LLM_PROVIDER` | `gemini`    | Provider: `gemini`, `gpt4all`                            |
| `LLM_API_KEY`  | _(none)_    | API key for the chosen provider (not needed for gpt4all) |
| `LLM_MODEL`    | _(per provider)_ | Override the default model for the chosen provider  |

## Default Models

| Provider | Default Model                               |
|----------|---------------------------------------------|
| gemini   | `gemini-3.1-flash-lite-preview`                          |
| gpt4all  | `Meta-Llama-3-8B-Instruct.Q4_0.gguf`       |

## How It Works

### Abstraction Layer

```text
┌─────────────────────────────────────────────┐
│              Agent Logic (main.py)          │
│  analyze_adr()  reflect_on_results()        │
│              run_agent()                    │
└──────────────────┬──────────────────────────┘
                   │ calls  .complete(messages)
          ┌────────▼────────┐
          │ BaseLLMClient   │  (abstract interface)
          └────────┬────────┘
    ┌──────────────┴──────────────┐
    ▼                             ▼
GeminiClient                  GPT4AllClient
(native FC)                   (ReAct)
```

- **Native function calling** (Gemini capable models): the LLM requests tool calls in a structured API format.
- **ReAct fallback** (GPT4All): the LLM emits `TOOL_CALL: {...}` in its text output; the agent parses and executes these.

### Agent Loop (provider-agnostic)

1. **Discover** — `list_files` on ADR and repo directories
2. **Analyze** — for each ADR: read rules, read code files, write Markdown analysis
3. **Reflect** — review all analyses and compile a single, polished Markdown report
4. **Report** — print to console + save `compliance_report.md`

## Expected Output

Instead of strict JSON, the agent now produces a polished, highly readable Markdown report summarizing all compliance findings.

**Example Excerpt (`compliance_report.md`):**

```markdown
# ADR Compliance Review Report

## Executive Summary
This report provides a compliance analysis of the codebase against established Architectural Decision Records (ADRs). The analysis identifies critical non-compliance issues within the `UsersController`...

---

## ADR-001: RESTful Resource Naming
**Status: NOT COMPLIANT**

The `UsersController` consistently violates multiple rules defined in ADR-001.

### Violations

*   **RULE-001-A (Resource names MUST be lowercase plural nouns):**
    *   **Violation:** The controller uses `api/user` instead of `api/users`.
    *   **Code:** `[Route("api/user")]`

*   **RULE-001-D (Identifiers MUST use `{id}`):**
    *   **Violation:** The application uses `{userId}` throughout the controller instead of the mandated `{id}` parameter.
    *   **Code:** 
        ```csharp
        [HttpGet("{userId}")]
        [HttpPut("{userId}")]
        ```
```
