# ADR Compliance Agent

An AI agent that analyzes a C# codebase for compliance with Architecture Decision Records (ADRs).  
Now **LLM-agnostic** — works with OpenAI, Gemini, Hugging Face, or GPT4All via environment variables.

## Project Structure

```
adr-compliance-agent/
├── main.py                    # Python agent (entry point)
├── requirements.txt           # Python dependencies
├── architecture.mmd           # Mermaid diagram of agent workflow
├── compliance_report.json     # Generated after running the agent
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

### OpenAI (default)

```bash
pip install openai
```

```powershell
$env:LLM_PROVIDER = "openai"
$env:LLM_API_KEY  = "sk-..."
# Optional: $env:LLM_MODEL = "gpt-4o"
python main.py
```

---

### Gemini

```bash
pip install google-generativeai
```

```powershell
$env:LLM_PROVIDER = "gemini"
$env:LLM_API_KEY  = "AIza..."     # from https://aistudio.google.com/app/apikey
# Optional: $env:LLM_MODEL = "gemini-1.5-pro"   # or gemini-1.5-flash, gemini-2.0-flash
python main.py
```

---

### Hugging Face Inference API

```bash
pip install huggingface_hub
```

```powershell
$env:LLM_PROVIDER = "hf"
$env:LLM_API_KEY  = "hf_..."      # from https://huggingface.co/settings/tokens
# Optional: $env:LLM_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"
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
| `LLM_PROVIDER` | `openai`    | Provider: `openai`, `gemini`, `hf`, `gpt4all`            |
| `LLM_API_KEY`  | _(none)_    | API key for the chosen provider (not needed for gpt4all) |
| `LLM_MODEL`    | _(per provider)_ | Override the default model for the chosen provider  |

## Default Models

| Provider | Default Model                               |
|----------|---------------------------------------------|
| openai   | `gpt-4o`                                    |
| gemini   | `gemini-1.5-pro`                            |
| hf       | `meta-llama/Meta-Llama-3-8B-Instruct`       |
| gpt4all  | `Meta-Llama-3-8B-Instruct.Q4_0.gguf`       |

## How It Works

### Abstraction Layer

```
┌─────────────────────────────────────────────┐
│              Agent Logic (main.py)           │
│  analyze_adr()  reflect_on_results()        │
│              run_agent()                     │
└──────────────────┬──────────────────────────┘
                   │ calls  .complete(messages)
          ┌────────▼────────┐
          │ BaseLLMClient   │  (abstract interface)
          └────────┬────────┘
    ┌──────────────┼──────────────────┐
    ▼              ▼                  ▼              ▼
OpenAIClient  GeminiClient  HuggingFaceClient  GPT4AllClient
(native FC)   (native FC)   (FC or ReAct)      (ReAct)
```

- **Native function calling** (OpenAI, Gemini, HF capable models): the LLM requests tool calls in a structured API format.
- **ReAct fallback** (GPT4All, unsupported HF models): the LLM emits `TOOL_CALL: {...}` in its text output; the agent parses and executes these.

### Agent Loop (provider-agnostic)

1. **Discover** — `list_files` on ADR and repo directories
2. **Analyze** — for each ADR: read rules, read code files, check compliance, return JSON
3. **Reflect** — review all results for missed violations or false positives
4. **Report** — print to console + save `compliance_report.json`

## Expected Output

| ADR | Expected Status | Key Violations |
|-----|----------------|----------------|
| ADR-001: RESTful Resource Naming | ❌ NOT COMPLIANT | Singular `api/user` route, `{userId}` param, action name in URL |
| ADR-002: HTTP Status Codes | ❌ NOT COMPLIANT | POST returns `Ok()`, DELETE returns `Ok(true)`, missing `[ProducesResponseType]` |
| ADR-003: Structured Logging | ❌ NOT COMPLIANT | `Console.WriteLine` everywhere, no `ILogger` injection |
| ADR-004: Input Validation | ❌ NOT COMPLIANT | `CreateUserRequest` has no validation attributes, missing `[ApiController]` |
| ADR-005: Separation of Concerns | ✅ COMPLIANT | Controller uses `IUserService` interface correctly |
