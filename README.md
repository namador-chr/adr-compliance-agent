# ADR Compliance Agent

An AI agent that analyzes a C# codebase for compliance with Architecture Decision Records (ADRs) using the OpenAI API.

## Project Structure

```
adr-compliance-agent/
├── main.py                    # Python agent (entry point)
├── requirements.txt           # Python dependencies
├── architecture.mmd           # Mermaid diagram of agent workflow
├── compliance_report.json     # Generated after running the agent
├── data/
│   ├── adrs/                  # Architecture Decision Records
│   │   ├── ADR-001-restful-resource-naming.md
│   │   ├── ADR-002-http-status-codes.md
│   │   ├── ADR-003-structured-logging.md
│   │   ├── ADR-004-input-validation.md
│   │   └── ADR-005-separation-of-concerns.md
│   └── repo/                  # Sample C# API (with intentional ADR violations)
│       ├── Program.cs
│       ├── Controllers/
│       │   └── UsersController.cs
│       ├── Services/
│       │   ├── IUserService.cs
│       │   └── UserService.cs
│       ├── Models/
│       │   └── User.cs
│       └── DTOs/
│           ├── CreateUserRequest.cs
│           └── UpdateUserRequest.cs
```

## Prerequisites

- Python 3.10+
- An OpenAI API key with access to `gpt-4o`

## Setup

### 1. Install dependencies

```bash
pip install openai
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

### 2. Set your OpenAI API key

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY = "sk-your-key-here"
```

**Windows (Command Prompt):**
```cmd
set OPENAI_API_KEY=sk-your-key-here
```

**macOS/Linux:**
```bash
export OPENAI_API_KEY="sk-your-key-here"
```

## Running the Agent

```bash
python main.py
```

The agent will:
1. **Discover** all ADR files and code files
2. **Analyze** each ADR against the C# codebase using the OpenAI API
3. **Reflect** on the results to catch any missed violations
4. **Print** a formatted compliance report to the console
5. **Save** the full report to `compliance_report.json`

## Expected Output

The agent analyzes 5 ADRs and will find the following intentional violations in the sample C# code:

| ADR | Expected Status | Key Violations |
|-----|----------------|----------------|
| ADR-001: RESTful Resource Naming | ❌ NOT COMPLIANT | Singular route `api/user`, `{userId}` param, action name in URL |
| ADR-002: HTTP Status Codes | ❌ NOT COMPLIANT | POST returns `Ok()` instead of `CreatedAtAction`, DELETE returns `Ok(true)` instead of `NoContent()`, missing `[ProducesResponseType]` |
| ADR-003: Structured Logging | ❌ NOT COMPLIANT | `Console.WriteLine` in service and controller, string interpolation in log calls, no `ILogger` injection |
| ADR-004: Input Validation | ❌ NOT COMPLIANT | `CreateUserRequest` has no validation attributes, missing `[ApiController]` on controller |
| ADR-005: Separation of Concerns | ✅ COMPLIANT | Controller uses `IUserService` interface; slight concern in service layer |

## How It Works

### Agent Loop
The agent uses OpenAI's **function calling** API. It has access to two tools:
- `list_files(folder)` — discovers available files
- `read_file(path)` — reads file contents

For each ADR, the agent:
1. Reads the ADR to understand its rules
2. Reads each code file
3. Evaluates compliance rule-by-rule
4. Returns a structured JSON report

### Reflection Step
After analyzing all ADRs, the agent **reviews its own output** to catch missed violations, correct false positives, and improve evidence quality.

## Customization

- **Add new ADRs**: Drop a `.md` file into `data/adrs/` following the same format (include numbered rules with RULE-XXX-Y identifiers).
- **Analyze different code**: Replace or add files in `data/repo/`.
- **Change model**: Edit the `MODEL` constant in `main.py` (e.g., `"gpt-4o-mini"` for lower cost).
- **Output format**: Modify `print_report()` or `save_report()` in `main.py`.
