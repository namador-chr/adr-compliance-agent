#!/usr/bin/env python3

import json
import time
from pathlib import Path

# Import extracted configurations and logic
from config import ADR_DIR, REPO_DIR
from tools import list_files, dispatch_tool
from prompts import get_analysis_system_prompt, get_reflection_system_prompt
from llm_clients import create_llm_client, BaseLLMClient, GPT4AllClient


# ---------------------------------------------------------------------------
# Agent loop — provider-agnostic tool-use loop (Phase 2 & 3)
# ---------------------------------------------------------------------------

def run_agent(
    client: BaseLLMClient,
    messages: list[dict],
    max_iterations: int = 20,
) -> str:
    """
    Run the agentic tool-use loop using any BaseLLMClient.
    """
    for _ in range(max_iterations):
        response = client.complete(messages)
        messages.append(response.raw_message)

        if response.tool_calls:
            for tc in response.tool_calls:
                print(f"  [tool] {tc.name}({json.dumps(tc.arguments)})")
                result = dispatch_tool(tc.name, tc.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                })
                # Brief pause to respect rate limits
                time.sleep(10)
        elif response.content:
            return response.content

    return "[Agent] Reached maximum iterations without a final answer."


# ---------------------------------------------------------------------------
# Phase 1: Discovery
# ---------------------------------------------------------------------------

def discover_files() -> tuple[list[str], list[str]]:
    """Return sorted absolute paths for ADR files and code files."""
    adr_files  = sorted(str(ADR_DIR  / f) for f in list_files(str(ADR_DIR)))
    repo_files = sorted(str(REPO_DIR / f) for f in list_files(str(REPO_DIR)))
    return adr_files, repo_files


# ---------------------------------------------------------------------------
# Phase 2: Analysis 
# ---------------------------------------------------------------------------

def analyze_adr(
    client: BaseLLMClient,
    adr_path: str,
    repo_files: list[str],
    react_mode: bool = False,
) -> str:
    """
    Phase 2: Analyze a single ADR against the codebase.
    Returns a raw Markdown string — free-form reasoning.
    """
    adr_name = Path(adr_path).name
    print(f"\n{'='*60}")
    print(f"Analyzing: {adr_name}")
    print(f"{'='*60}")

    messages = [
        {"role": "system", "content": get_analysis_system_prompt(react_mode)},
        {
            "role": "user",
            "content": (
                f"Please analyze ADR compliance for: {adr_name}\n\n"
                f"ADR file path: {adr_path}\n\n"
                f"Code files to analyze:\n{json.dumps(repo_files, indent=2)}\n\n"
                f'1. Call read_file("{adr_path}") to read the ADR rules.\n'
                f"2. Call read_file(path) for each code file in the list above.\n"
                f"3. Write your detailed Markdown analysis (no JSON)."
            ),
        },
    ]

    return run_agent(client, messages)


# ---------------------------------------------------------------------------
# Phase 3: Reflection + Markdown Formatting
# ---------------------------------------------------------------------------

def reflect_on_results(
    client: BaseLLMClient,
    markdown_analyses: list[str],
    adr_names: list[str],
    repo_files: list[str],
    react_mode: bool = False,
) -> str:
    """
    Phase 3 — Reflection and Markdown Report Generation.
    """
    print(f"\n{'='*60}")
    print("Reflection Step: reviewing and formatting final Markdown report...")
    print(f"{'='*60}")

    analyses_block = "\n\n".join(
        f"--- Analysis for {name} ---\n{md}"
        for name, md in zip(adr_names, markdown_analyses)
    )

    messages = [
        {"role": "system", "content": get_reflection_system_prompt(react_mode)},
        {
            "role": "user",
            "content": (
                f"Here are the drafts of the Markdown analyses for each ADR:\n\n{analyses_block}\n\n"
                f"Code files available for re-reading if needed:\n{json.dumps(repo_files, indent=2)}\n\n"
                "Review the analyses, verify uncertain findings by re-reading code files if needed, "
                "then output the final polished Markdown report."
            )
        },
    ]

    return run_agent(client, messages)


# ---------------------------------------------------------------------------
# Phase 4: Report
# ---------------------------------------------------------------------------

def print_report(report_md: str) -> None:
    """Print the human-readable compliance report to stdout."""
    print("\n")
    print("╔" + "═" * 70 + "╗")
    print("║" + " ADR COMPLIANCE REPORT ".center(70) + "║")
    print("╚" + "═" * 70 + "╝")
    print("\n" + report_md + "\n")
    print("─" * 72)


def save_report(report_md: str, output_path: str = "compliance_report.md") -> None:
    """Save the full Markdown report to a file."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"\n📄 Full report saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("🔍 ADR Compliance Agent Starting...")
    print(f"   ADR directory : {ADR_DIR}")
    print(f"   Repo directory: {REPO_DIR}\n")

    print("🔌 Initialising LLM client...")
    client = create_llm_client()

    react_mode = isinstance(client, GPT4AllClient)

    print("\n📂 Discovering files...")
    adr_files, repo_files = discover_files()
    print(f"   ADRs : {[Path(f).name for f in adr_files]}")
    print(f"   Code : {[Path(f).name for f in repo_files]}")

    markdown_analyses: list[str] = []
    for adr_path in adr_files:
        md = analyze_adr(client, adr_path, repo_files, react_mode=react_mode)
        markdown_analyses.append(md)

    adr_names = [Path(f).name for f in adr_files]

    final_report = reflect_on_results(
        client, markdown_analyses, adr_names, repo_files, react_mode=react_mode
    )

    print_report(final_report)
    save_report(final_report)

    print("✅ ADR Compliance Agent finished.")


if __name__ == "__main__":
    main()
