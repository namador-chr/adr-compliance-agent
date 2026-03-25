#!/usr/import/env python3
import time
import json
import logging
from pathlib import Path

from config import config
from tools import list_files, dispatch_tool
from prompts import get_analysis_system_prompt, get_reflection_system_prompt
from llm_clients import create_llm_client, BaseLLMClient, GPT4AllClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Silence noisy third-party HTTP loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

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
                # Human-readable progress logging
                if tc.name == "read_file":
                    file_name = Path(tc.arguments.get("path", "")).name
                    logger.info(f"  ↳ Reading: {file_name}")
                elif tc.name == "list_files":
                    folder_name = Path(tc.arguments.get("folder", "")).name
                    logger.info(f"  ↳ Scanning directory: {folder_name}")
                else:
                    logger.info(f"  ↳ Using tool: {tc.name}")

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
    adr_files  = sorted(str(config.ADR_DIR / f) for f in list_files(str(config.ADR_DIR)))
    repo_files = sorted(str(config.REPO_DIR / f) for f in list_files(str(config.REPO_DIR)))
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
    Returns a raw Markdown string — free-form reasoning, no JSON.
    """
    adr_name = Path(adr_path).name
    logger.info(f"Analyzing: {adr_name}")

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
    logger.info("Reflection Step: reviewing and formatting final Markdown report...")

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
    logger.info(f"Full report saved to: {output_path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("ADR Compliance Agent Starting...")
    logger.info(f"ADR directory : {config.ADR_DIR}")
    logger.info(f"Repo directory: {config.REPO_DIR}")

    logger.info("Initialising LLM client...")
    client = create_llm_client()

    react_mode = isinstance(client, GPT4AllClient)

    # Phase 1: Discover files
    logger.info("Discovering files...")
    adr_files, repo_files = discover_files()
    logger.info(f"ADRs found : {len(adr_files)}")
    logger.info(f"Code files : {len(repo_files)}")

    # Phase 2: Free-form Markdown analysis
    markdown_analyses: list[str] = []
    for adr_path in adr_files:
        md = analyze_adr(client, adr_path, repo_files, react_mode=react_mode)
        markdown_analyses.append(md)

    adr_names = [Path(f).name for f in adr_files]

    # Phase 3: Reflection + formatted Markdown output
    final_report = reflect_on_results(
        client, markdown_analyses, adr_names, repo_files, react_mode=react_mode
    )

    # Phase 4: Report
    print_report(final_report)
    save_report(final_report)

    logger.info("ADR Compliance Agent finished.")

if __name__ == "__main__":
    main()
