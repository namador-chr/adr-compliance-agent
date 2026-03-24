#!/usr/bin/env python3
"""
ADR Compliance Agent
====================
An AI agent that analyzes a C# codebase for compliance with Architecture Decision Records (ADRs).

How it works:
1. Loads all ADRs from /data/adrs/
2. Loads all code files from /data/repo/
3. For each ADR, sends the ADR + code to the OpenAI API for analysis
4. Performs a reflection step to catch missed violations
5. Outputs a structured compliance report

Usage:
    Set OPENAI_API_KEY environment variable, then:
        python main.py

Requirements:
    pip install openai
"""

import os
import json
from pathlib import Path
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "gpt-4o"
ADR_DIR = Path(__file__).parent / "data" / "adrs"
REPO_DIR = Path(__file__).parent / "data" / "repo"

# ---------------------------------------------------------------------------
# Helper Tools (available to the agent)
# ---------------------------------------------------------------------------

def list_files(folder: str) -> list[str]:
    """
    List all files (recursively) under the given folder.
    Returns a sorted list of relative paths from the folder root.
    """
    base = Path(folder)
    if not base.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    return sorted(
        str(p.relative_to(base))
        for p in base.rglob("*")
        if p.is_file()
    )


def read_file(path: str) -> str:
    """
    Read and return the full text content of a file.
    path can be absolute or relative to the current working directory.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return file_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool definitions for OpenAI function calling
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List all files in a directory recursively. "
                "Use this to discover what ADR or code files are available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Absolute or relative path to the folder to list."
                    }
                },
                "required": ["folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full content of a file. "
                "Use this to read ADR markdown files or C# source code files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file to read."
                    }
                },
                "required": ["path"]
            }
        }
    }
]

# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, arguments: dict) -> str:
    """Execute a tool call and return its result as a string."""
    if name == "list_files":
        result = list_files(arguments["folder"])
        return json.dumps(result, indent=2)
    elif name == "read_file":
        return read_file(arguments["path"])
    else:
        return f"ERROR: Unknown tool '{name}'"


# ---------------------------------------------------------------------------
# Agent runner — handles tool call loops
# ---------------------------------------------------------------------------

def run_agent(client: OpenAI, messages: list[dict], max_iterations: int = 15) -> str:
    """
    Run the agent loop: send messages, handle tool calls, return final text response.
    Supports multi-turn tool use via the OpenAI function-calling interface.
    """
    for iteration in range(max_iterations):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message
        messages.append(message)  # Append assistant message to history

        # If the model wants to call tools, execute them all
        if message.tool_calls:
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                print(f"  [tool] {func_name}({json.dumps(func_args)})")
                result = dispatch_tool(func_name, func_args)

                # Append tool result to message history
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            # No more tool calls — model produced a final answer
            return message.content or ""

    return "[Agent] Reached maximum iterations without a final answer."


# ---------------------------------------------------------------------------
# Phase 1: Discovery — load ADR and repo metadata
# ---------------------------------------------------------------------------

def discover_files() -> tuple[list[str], list[str]]:
    """Return sorted lists of ADR file paths and code file paths."""
    adr_files = sorted([str(ADR_DIR / f) for f in list_files(str(ADR_DIR))])
    repo_files = sorted([str(REPO_DIR / f) for f in list_files(str(REPO_DIR))])
    return adr_files, repo_files


# ---------------------------------------------------------------------------
# Phase 2: Analysis — analyze each ADR against all code files
# ---------------------------------------------------------------------------

def analyze_adr(client: OpenAI, adr_path: str, repo_files: list[str]) -> dict:
    """
    Use the agent to analyze compliance of the codebase against a single ADR.
    Returns a dict with keys: adr, status, violations, evidence, summary.
    """
    adr_name = Path(adr_path).name
    print(f"\n{'='*60}")
    print(f"Analyzing: {adr_name}")
    print(f"{'='*60}")

    repo_files_json = json.dumps(repo_files, indent=2)

    system_prompt = """You are an expert software architect and code reviewer specializing in \
Architecture Decision Records (ADR) compliance analysis.

Your task is to analyze a C# codebase for compliance with a given ADR.

You have access to two tools:
- list_files(folder): lists files in a directory
- read_file(path): reads a file's contents

Workflow:
1. Read the ADR file to understand its rules.
2. Read each relevant code file from the provided list.
3. For each rule in the ADR, determine if the code complies or violates it.
4. Produce a structured JSON report.

Your final answer MUST be valid JSON (no markdown fences) with this exact structure:
{
  "adr": "<ADR filename>",
  "status": "COMPLIANT" or "NOT COMPLIANT",
  "violations": [
    {
      "rule": "<rule ID, e.g. RULE-001-A>",
      "description": "<what the rule requires>",
      "finding": "<what was found in the code>",
      "file": "<filename>",
      "snippet": "<relevant code snippet>"
    }
  ],
  "compliant_aspects": [
    "<description of what IS compliant>"
  ],
  "summary": "<one paragraph summary of the compliance status>"
}

If there are no violations, set "status" to "COMPLIANT" and "violations" to [].
Be precise — quote actual code from the files as evidence.
"""

    user_prompt = f"""Please analyze the following ADR for compliance against the codebase.

ADR file: {adr_path}

Code files to analyze:
{repo_files_json}

Steps:
1. Call read_file("{adr_path}") to read the ADR rules.
2. Call read_file(path) for each code file listed above.
3. Check each rule in the ADR against the code.
4. Return your analysis as a JSON object (no markdown).
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    raw_result = run_agent(client, messages)

    # Parse JSON response
    try:
        # Strip any accidental markdown fences
        cleaned = raw_result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: return raw as summary
        return {
            "adr": adr_name,
            "status": "PARSE_ERROR",
            "violations": [],
            "compliant_aspects": [],
            "summary": raw_result,
        }


# ---------------------------------------------------------------------------
# Phase 3: Reflection — improve analysis quality
# ---------------------------------------------------------------------------

def reflect_on_results(client: OpenAI, results: list[dict], repo_files: list[str]) -> list[dict]:
    """
    Reflection step: the agent reviews its own analysis and checks for missed violations.
    Returns an updated list of results.
    """
    print(f"\n{'='*60}")
    print("Reflection Step: Reviewing analysis for missed violations...")
    print(f"{'='*60}")

    results_json = json.dumps(results, indent=2)
    repo_files_json = json.dumps(repo_files, indent=2)

    system_prompt = """You are a senior software architect performing a quality review of an \
ADR compliance analysis. Your goal is to identify any missed violations or incorrect assessments \
in the provided analysis.

You have access to:
- read_file(path): to re-read any code files for verification

Return ONLY valid JSON (no markdown) — an updated version of the full results array.
The structure must match the input exactly, but you may:
- Add missing violations to any ADR's violations list
- Correct the "status" field if violations were missed
- Improve evidence snippets
- Correct false positives (remove violations that don't actually exist)
- Improve summaries

Keep the same JSON structure as input.
"""

    user_prompt = f"""Here is the current ADR compliance analysis:

{results_json}

And here are the code files that were analyzed:
{repo_files_json}

Please review this analysis carefully:
1. Re-read any code files you need to verify findings.
2. Check for any violations that may have been missed.
3. Check for any false positives (violations that aren't actually violations).
4. Return the complete updated results array as JSON (same structure, no markdown).
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    raw_result = run_agent(client, messages)

    try:
        cleaned = raw_result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        updated = json.loads(cleaned)
        if isinstance(updated, list):
            return updated
        return results  # fallback if structure changed
    except json.JSONDecodeError:
        print("[Warning] Reflection step returned unparseable JSON — keeping original results.")
        return results


# ---------------------------------------------------------------------------
# Phase 4: Report — pretty-print the compliance report
# ---------------------------------------------------------------------------

def print_report(results: list[dict]) -> None:
    """Print a human-readable compliance report to stdout."""
    print("\n")
    print("╔" + "═" * 70 + "╗")
    print("║" + " ADR COMPLIANCE REPORT ".center(70) + "║")
    print("╚" + "═" * 70 + "╝")

    total = len(results)
    compliant_count = sum(1 for r in results if r.get("status") == "COMPLIANT")
    non_compliant_count = total - compliant_count

    print(f"\n📊 Summary: {compliant_count}/{total} ADRs COMPLIANT, "
          f"{non_compliant_count}/{total} NOT COMPLIANT\n")

    for result in results:
        adr = result.get("adr", "Unknown ADR")
        status = result.get("status", "UNKNOWN")
        icon = "✅" if status == "COMPLIANT" else "❌"

        print(f"\n{icon} {adr}")
        print(f"   Status: {status}")
        print(f"   Summary: {result.get('summary', 'N/A')}")

        violations = result.get("violations", [])
        if violations:
            print(f"\n   Violations ({len(violations)}):")
            for v in violations:
                print(f"   ── Rule: {v.get('rule', 'N/A')}")
                print(f"      Description: {v.get('description', 'N/A')}")
                print(f"      Finding: {v.get('finding', 'N/A')}")
                print(f"      File: {v.get('file', 'N/A')}")
                snippet = v.get("snippet", "")
                if snippet:
                    # Indent snippet for readability
                    indented = "\n".join("      │ " + line for line in snippet.splitlines())
                    print(f"      Code:\n{indented}")
                print()

        compliant_aspects = result.get("compliant_aspects", [])
        if compliant_aspects:
            print(f"   Compliant Aspects:")
            for aspect in compliant_aspects:
                print(f"   ✓ {aspect}")

        print(f"\n{'─' * 72}")


def save_report(results: list[dict], output_path: str = "compliance_report.json") -> None:
    """Save the full results to a JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Full report saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY environment variable is not set.\n"
            "Set it with: set OPENAI_API_KEY=sk-..."
        )

    client = OpenAI(api_key=api_key)

    print("🔍 ADR Compliance Agent Starting...")
    print(f"   Model: {MODEL}")
    print(f"   ADR directory: {ADR_DIR}")
    print(f"   Repository directory: {REPO_DIR}")

    # Phase 1: Discover files
    print("\n📂 Discovering files...")
    adr_files, repo_files = discover_files()
    print(f"   Found {len(adr_files)} ADR(s): {[Path(f).name for f in adr_files]}")
    print(f"   Found {len(repo_files)} code file(s): {[Path(f).name for f in repo_files]}")

    # Phase 2: Analyze each ADR
    results = []
    for adr_path in adr_files:
        result = analyze_adr(client, adr_path, repo_files)
        results.append(result)

    # Phase 3: Reflection
    results = reflect_on_results(client, results, repo_files)

    # Phase 4: Report
    print_report(results)
    save_report(results)

    print("\n✅ ADR Compliance Agent finished.")


if __name__ == "__main__":
    main()
