#!/usr/bin/env python3

import os
import json
import re
import abc
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ADR_DIR  = Path(__file__).parent / "data" / "adrs"
REPO_DIR = Path(__file__).parent / "data" / "repo"

# Default model for each provider
MODEL_DEFAULTS: dict[str, str] = {
    "gemini":  "gemini-3.1-flash-lite-preview",
    "gpt4all": "Meta-Llama-3-8B-Instruct.Q4_0.gguf",
}

# ---------------------------------------------------------------------------
# Unified data types
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """Represents a single tool/function call requested by the LLM."""
    id:        str
    name:      str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """
    Unified response from any LLM provider.

    - If the model wants to call tools: tool_calls is populated, content is None.
    - If the model has a final answer:  content is populated, tool_calls is empty.
    - raw_message is the provider-native dict to append to the conversation history.
    """
    content:     Optional[str]  = None
    tool_calls:  list[ToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool definitions (shared across providers that support function calling)
# ---------------------------------------------------------------------------

TOOLS_SCHEMA: list[dict] = [
    {
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
    },
    {
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
]


# ---------------------------------------------------------------------------
# Helper tools (executed locally — same for every provider)
# ---------------------------------------------------------------------------

def list_files(folder: str) -> list[str]:
    """List all files recursively under folder. Returns relative paths."""
    base = Path(folder)
    if not base.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    return sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file())


def read_file(path: str) -> str:
    """Read and return the full text content of a file."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return file_path.read_text(encoding="utf-8")


def dispatch_tool(name: str, arguments: dict) -> str:
    """Execute a tool call by name and return the result as a string."""
    if name == "list_files":
        return json.dumps(list_files(arguments["folder"]), indent=2)
    elif name == "read_file":
        return read_file(arguments["path"])
    return f"ERROR: Unknown tool '{name}'"


# ---------------------------------------------------------------------------
# ReAct-style tool call parser
# (used by providers without native function calling, e.g. GPT4All)
# ---------------------------------------------------------------------------

REACT_TOOL_PATTERN = re.compile(r"TOOL_CALL:\s*(\{.*?\})", re.DOTALL)

REACT_TOOL_INSTRUCTIONS = """
When you need to call a tool, output it on its own line in this exact format:
  TOOL_CALL: {"name": "<tool_name>", "arguments": {<args as JSON>}}

Available tools:
  - list_files(folder)   : list all files in a directory
  - read_file(path)      : read the full contents of a file

After receiving the tool result, continue your analysis.
Do NOT wrap your final answer in markdown fences.
"""


def _parse_react_tool_calls(text: str) -> list[ToolCall]:
    """Extract TOOL_CALL directives from a ReAct-style LLM response."""
    calls = []
    for i, m in enumerate(REACT_TOOL_PATTERN.finditer(text)):
        try:
            data = json.loads(m.group(1))
            calls.append(ToolCall(
                id=f"react_{i}",
                name=data["name"],
                arguments=data.get("arguments", {}),
            ))
        except (json.JSONDecodeError, KeyError):
            pass
    return calls


# ---------------------------------------------------------------------------
# Abstract base class for LLM clients
# ---------------------------------------------------------------------------

class BaseLLMClient(abc.ABC):
    """
    All LLM adapters implement this interface.
    The agent loop only ever calls .complete() and .complete_json().
    """

    @abc.abstractmethod
    def complete(self, messages: list[dict]) -> LLMResponse:
        """
        Tool-use completion: send messages, handle tool calls, return a response.
        Messages follow the standard OpenAI chat format.
        """
        ...


# ---------------------------------------------------------------------------
# Provider: Gemini  (uses the new google-genai SDK — google.generativeai is deprecated)
# ---------------------------------------------------------------------------

class GeminiClient(BaseLLMClient):
    """
    Adapter for Google Gemini via the google-genai SDK (replaces google-generativeai).
    Uses native function calling for Phase 2 and mime_type JSON mode for Phase 3.
    Install: pip install google-genai

    Switch to Gemini:
      $env:LLM_PROVIDER = "gemini"
      $env:LLM_API_KEY  = "AIza..."          # from https://aistudio.google.com/app/apikey
      $env:LLM_MODEL    = "gemini-2.0-flash" # or gemini-1.5-pro, gemini-2.5-pro-exp-03-25
    """

    def __init__(self, api_key: str, model: str):
        from google import genai                       # lazy import (google-genai SDK)
        from google.genai import types as genai_types

        self._genai       = genai
        self._types       = genai_types
        self._model_name  = model
        self._client      = genai.Client(api_key=api_key)

        # Build the tool declaration for the new SDK
        self._tools = [
            genai_types.Tool(function_declarations=[
                genai_types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            k: genai_types.Schema(
                                type=genai_types.Type.STRING,
                                description=v.get("description", "")
                            )
                            for k, v in t["parameters"]["properties"].items()
                        },
                        required=t["parameters"].get("required", [])
                    )
                )
                for t in TOOLS_SCHEMA
            ])
        ]

    def _chat_config(self, system: str) -> Any:
        return self._types.GenerateContentConfig(
            system_instruction=system,
            tools=self._tools,
        )

    def complete(self, messages: list[dict]) -> LLMResponse:
        """
        Multi-turn tool-use call using the new google-genai SDK.
        Converts the OpenAI-format message list to Gemini Content objects.
        """
        # Separate system message from the rest
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        history    = [m for m in messages if m["role"] != "system"]

        # Build Gemini Content objects
        contents = []
        for m in history:
            role = "model" if m["role"] == "assistant" else "user"
            content_text = m.get("content") or ""

            if m["role"] == "tool":
                # Wrap tool result as a function response part
                contents.append(self._types.Content(
                    role="user",
                    parts=[self._types.Part(
                        function_response=self._types.FunctionResponse(
                            name=m.get("name", "tool"),
                            response={"result": content_text},
                        )
                    )]
                ))
            else:
                if content_text:
                    contents.append(self._types.Content(
                        role=role,
                        parts=[self._types.Part(text=content_text)]
                    ))

        config = self._types.GenerateContentConfig(
            system_instruction=system_msg or None,
            tools=self._tools,
        )

        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        tool_calls: list[ToolCall] = []

        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append(ToolCall(
                    id=f"gemini_{fc.name}",
                    name=fc.name,
                    arguments=dict(fc.args),
                ))

        if tool_calls:
            return LLMResponse(
                content=None,
                tool_calls=tool_calls,
                raw_message={"role": "assistant", "content": None},
            )

        text = "".join(p.text for p in candidate.content.parts if hasattr(p, "text"))
        return LLMResponse(
            content=text,
            tool_calls=[],
            raw_message={"role": "assistant", "content": text},
        )


# ---------------------------------------------------------------------------
# Provider: GPT4All (fully local, no API key required)
# ---------------------------------------------------------------------------

class GPT4AllClient(BaseLLMClient):
    """
    Adapter for GPT4All local inference (ReAct text-based tool calling).
    Install: pip install gpt4all

    Switch to GPT4All:
      $env:LLM_PROVIDER = "gpt4all"
      $env:LLM_MODEL    = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
    """

    def __init__(self, model: str):
        from gpt4all import GPT4All  # lazy import
        print(f"  [gpt4all] Loading model '{model}' (may download on first run)...")
        self._client = GPT4All(model)

    def complete(self, messages: list[dict]) -> LLMResponse:
        prompt = _flatten_messages_to_prompt(messages)
        with self._client.chat_session():
            text = self._client.generate(prompt, max_tokens=4096)
        parsed = _parse_react_tool_calls(text)
        return LLMResponse(
            content=None if parsed else text,
            tool_calls=parsed,
            raw_message={"role": "assistant", "content": text},
        )


def _flatten_messages_to_prompt(messages: list[dict]) -> str:
    """Flatten chat messages to a single prompt string for providers without chat APIs."""
    parts = []
    for m in messages:
        role    = m.get("role", "user").upper()
        content = m.get("content") or ""
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts) + "\n\n[ASSISTANT]\n"


# ---------------------------------------------------------------------------
# Factory — create the right client from environment variables
# ---------------------------------------------------------------------------

def create_llm_client() -> BaseLLMClient:
    """
    Create and return the appropriate LLM client.

    Environment variables:
      LLM_PROVIDER  : "gemini" (default) | "gpt4all"
      LLM_API_KEY   : API key (not needed for gpt4all)
      LLM_MODEL     : Override the default model for the chosen provider
    """
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()
    api_key  = os.environ.get("LLM_API_KEY", "")
    model    = os.environ.get("LLM_MODEL", MODEL_DEFAULTS.get(provider, ""))

    print(f"  Provider : {provider}")
    print(f"  Model    : {model}")

    if provider == "gemini":
        if not api_key:
            raise EnvironmentError(
                "LLM_API_KEY must be set for provider 'gemini'.\n"
                "  Get one at: https://aistudio.google.com/app/apikey"
            )
        return GeminiClient(api_key=api_key, model=model)

    elif provider == "gpt4all":
        return GPT4AllClient(model=model)

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. "
            "Valid options: gemini, gpt4all"
        )


# ---------------------------------------------------------------------------
# Agent loop — provider-agnostic tool-use loop (Phase 2)
# ---------------------------------------------------------------------------

def run_agent(
    client: BaseLLMClient,
    messages: list[dict],
    max_iterations: int = 20,
) -> str:
    """
    Run the agentic tool-use loop using any BaseLLMClient.

    1. Calls client.complete(messages)
    2. If the response contains tool_calls → executes them, appends results, loops
    3. If the response contains content → returns it as the final answer
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
                #print("Waiting 10 seconds...")
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
# Phase 2: Analysis — free-form Markdown reasoning (NO JSON pressure)
# ---------------------------------------------------------------------------

def _analysis_system_prompt(react_mode: bool = False) -> str:
    """
    Phase 2 system prompt: asks for detailed Markdown reasoning.
    Deliberately avoids any JSON schema — the model reasons freely.
    JSON formatting is handled exclusively in Phase 3.
    """
    base = (
        "You are an expert software architect and code reviewer specializing in "
        "Architecture Decision Records (ADR) compliance analysis.\n\n"
        "Your task is to analyze a C# codebase for compliance with a given ADR.\n\n"
        "You have access to two tools:\n"
        "- list_files(folder): lists files in a directory\n"
        "- read_file(path):    reads a file's contents\n\n"
        "Workflow:\n"
        "1. Read the ADR file to understand its rules.\n"
        "2. Read each relevant code file from the provided list.\n"
        "3. For each numbered rule in the ADR, evaluate the code carefully.\n\n"
        "Output format — write a detailed Markdown report with:\n"
        "## Rule-by-rule analysis\n"
        "For each rule state:\n"
        "  - The rule ID and description\n"
        "  - The exact code snippet(s) you found (use code blocks)\n"
        "  - COMPLIANT or VIOLATES, with a clear explanation\n\n"
        "## Overall assessment\n"
        "A short paragraph summarising the compliance status.\n\n"
        "Do NOT output JSON. Write in plain, readable Markdown.\n"
        "Be thorough — your output will be reviewed and structured by a second model."
    )
    if react_mode:
        base += REACT_TOOL_INSTRUCTIONS
    return base


def analyze_adr(
    client: BaseLLMClient,
    adr_path: str,
    repo_files: list[str],
    react_mode: bool = False,
) -> str:
    """
    Phase 2: Analyze a single ADR against the codebase.
    Returns a raw Markdown string — free-form reasoning, no JSON.
    Structured output is produced exclusively in Phase 3.
    """
    adr_name = Path(adr_path).name
    print(f"\n{'='*60}")
    print(f"Analyzing: {adr_name}")
    print(f"{'='*60}")

    messages = [
        {"role": "system", "content": _analysis_system_prompt(react_mode)},
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
#
# This phase receives the free-form Markdown from Phase 2 and is responsible for:
#   a) Reviewing the analysis for accuracy (missed violations, false positives)
#   b) Producing the final polished Markdown report.
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

    Receives free-form Markdown analyses from Phase 2 and:
      1. Reviews them for missed violations or false positives.
      2. Produces the final polished Markdown report summarizing all findings.

    Returns the full Markdown report as a string.
    """
    print(f"\n{'='*60}")
    print("Reflection Step: reviewing and formatting final Markdown report...")
    print(f"{'='*60}")

    analyses_block = "\n\n".join(
        f"--- Analysis for {name} ---\n{md}"
        for name, md in zip(adr_names, markdown_analyses)
    )

    system = (
        "You are a senior software architect reviewing ADR compliance analyses.\n\n"
        "Your two responsibilities:\n"
        "1. REVIEW: Check each analysis for missed violations or false positives.\n"
        "   You may call read_file(path) to re-read any code file for verification.\n"
        "2. FORMAT: Output a final, polished, highly readable Markdown report summarizing "
        "   the compliance of the codebase against all provided ADRs.\n\n"
        "The report should include:\n"
        "- An executive summary at the top.\n"
        "- A detailed section for each ADR, clearly stating whether it is COMPLIANT or NOT COMPLIANT.\n"
        "- Clear descriptions of any violations found, quoting relevant code snippets.\n"
        "- Clear descriptions of compliant aspects.\n\n"
        "Do NOT output JSON. Output ONLY the polished Markdown report."
    )
    if react_mode:
        system += "\n" + REACT_TOOL_INSTRUCTIONS

    user = (
        f"Here are the drafts of the Markdown analyses for each ADR:\n\n{analyses_block}\n\n"
        f"Code files available for re-reading if needed:\n{json.dumps(repo_files, indent=2)}\n\n"
        "Review the analyses, verify uncertain findings by re-reading code files if needed, "
        "then output the final polished Markdown report."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    # For Phase 3, we run the agent normally, allowing it to use tools to review,
    # and eventually it will return its final markdown report.
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

    # GPT4All has no native function calling — use ReAct text-based tool calls
    react_mode = isinstance(client, GPT4AllClient)

    # Phase 1: Discover files
    print("\n📂 Discovering files...")
    adr_files, repo_files = discover_files()
    print(f"   ADRs : {[Path(f).name for f in adr_files]}")
    print(f"   Code : {[Path(f).name for f in repo_files]}")

    # Phase 2: Free-form Markdown analysis (one call per ADR, no JSON pressure)
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
    #print_report(final_report)
    save_report(final_report)

    print("\n✅ ADR Compliance Agent finished.")


if __name__ == "__main__":
    main()
