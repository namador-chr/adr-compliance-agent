#!/usr/bin/env python3
"""
ADR Compliance Agent — LLM-Agnostic Version
============================================
Analyzes a C# codebase for compliance with Architecture Decision Records (ADRs).

Supported providers (set via environment variables):
  LLM_PROVIDER = "openai"   (default) — requires: pip install openai
  LLM_PROVIDER = "gemini"             — requires: pip install google-generativeai
  LLM_PROVIDER = "hf"                 — requires: pip install huggingface_hub
  LLM_PROVIDER = "gpt4all"            — requires: pip install gpt4all

  LLM_API_KEY  = your API key (not needed for gpt4all local inference)
  LLM_MODEL    = override the default model for the chosen provider

Usage:
  # OpenAI (default)
  $env:LLM_PROVIDER = "openai"
  $env:LLM_API_KEY  = "sk-..."
  python main.py

  # Gemini
  $env:LLM_PROVIDER = "gemini"
  $env:LLM_API_KEY  = "AIza..."
  python main.py

  # Hugging Face Inference API
  $env:LLM_PROVIDER = "hf"
  $env:LLM_API_KEY  = "hf_..."
  python main.py

  # GPT4All (fully local — no API key needed)
  $env:LLM_PROVIDER = "gpt4all"
  python main.py
"""

import os
import json
import re
import abc
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
    "openai":  "gpt-4o",
    "gemini":  "gemini-1.5-pro",
    "hf":      "meta-llama/Meta-Llama-3-8B-Instruct",
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
    content:     Optional[str]       = None
    tool_calls:  list[ToolCall]      = field(default_factory=list)
    raw_message: dict[str, Any]      = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool definitions (shared across all providers that support function calling)
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

# OpenAI-format tool list (wraps schema with "type": "function")
OPENAI_TOOLS = [{"type": "function", "function": t} for t in TOOLS_SCHEMA]

# ---------------------------------------------------------------------------
# Helper tools (callable locally — same for all providers)
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
# ReAct-style tool call parser (used by providers without native function calling)
#
# The LLM is prompted to output tool calls in this exact format:
#   TOOL_CALL: {"name": "read_file", "arguments": {"path": "..."}}
# The parser extracts these and converts them to ToolCall objects.
# ---------------------------------------------------------------------------

REACT_TOOL_PATTERN = re.compile(
    r"TOOL_CALL:\s*(\{.*?\})",
    re.DOTALL
)

REACT_TOOL_INSTRUCTIONS = """
When you need to call a tool, output it on its own line in this exact format:
  TOOL_CALL: {"name": "<tool_name>", "arguments": {<args as JSON>}}

Available tools:
  - list_files(folder)   : list all files in a directory
  - read_file(path)      : read the full contents of a file

After receiving the tool result, continue your analysis.
When you have your final answer (the JSON report), output it with no preamble.
Do NOT wrap JSON in markdown fences.
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
    All LLM provider adapters must implement this interface.
    The rest of the agent code only ever calls .complete().
    """

    @abc.abstractmethod
    def complete(self, messages: list[dict]) -> LLMResponse:
        """
        Send messages to the LLM and return a unified LLMResponse.
        Messages are in the standard OpenAI chat format:
          [{"role": "system"|"user"|"assistant"|"tool", "content": "..."}]
        """
        ...


# ---------------------------------------------------------------------------
# Provider: OpenAI
# ---------------------------------------------------------------------------

class OpenAIClient(BaseLLMClient):
    """
    Adapter for the OpenAI Chat Completions API.
    Uses native function calling.
    Install: pip install openai
    """

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI  # lazy import
        self._client = OpenAI(api_key=api_key)
        self._model  = model

    def complete(self, messages: list[dict]) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # Build a serialisable raw_message dict for history
        raw: dict[str, Any] = {"role": "assistant", "content": msg.content}
        tool_calls: list[ToolCall] = []

        if msg.tool_calls:
            raw["tool_calls"] = [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
                for tc in msg.tool_calls
            ]

        return LLMResponse(
            content=msg.content if not tool_calls else None,
            tool_calls=tool_calls,
            raw_message=raw,
        )


# ---------------------------------------------------------------------------
# Provider: Gemini
# ---------------------------------------------------------------------------

class GeminiClient(BaseLLMClient):
    """
    Adapter for Google Gemini via the google-generativeai SDK.
    Uses native function calling (Gemini supports it natively).
    Install: pip install google-generativeai
    Docs: https://ai.google.dev/gemini-api/docs/function-calling

    Switch to Gemini:
      $env:LLM_PROVIDER = "gemini"
      $env:LLM_API_KEY  = "AIza..."          # Google AI Studio key
      $env:LLM_MODEL    = "gemini-1.5-pro"   # or gemini-1.5-flash, gemini-2.0-flash, etc.
    """

    def __init__(self, api_key: str, model: str):
        import google.generativeai as genai  # lazy import
        genai.configure(api_key=api_key)

        # Convert shared tool schema to Gemini's FunctionDeclaration format
        gemini_tools = [
            genai.protos.Tool(function_declarations=[
                genai.protos.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            k: genai.protos.Schema(
                                type=genai.protos.Type.STRING,
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

        self._model_name = model
        self._genai      = genai
        self._model      = genai.GenerativeModel(model_name=model, tools=gemini_tools)
        self._chat       = self._model.start_chat(history=[])

    def complete(self, messages: list[dict]) -> LLMResponse:
        # Gemini's SDK manages history internally via chat sessions.
        # We send only the last user/tool turn.
        last = next(
            (m for m in reversed(messages) if m["role"] in ("user", "tool")),
            messages[-1]
        )
        response = self._chat.send_message(last["content"])
        part     = response.candidates[0].content.parts[0]

        tool_calls: list[ToolCall] = []
        if hasattr(part, "function_call") and part.function_call.name:
            fc = part.function_call
            tool_calls.append(ToolCall(
                id=f"gemini_{fc.name}",
                name=fc.name,
                arguments=dict(fc.args),
            ))
            return LLMResponse(
                content=None,
                tool_calls=tool_calls,
                raw_message={"role": "assistant", "content": None},
            )

        text = part.text
        return LLMResponse(
            content=text,
            tool_calls=[],
            raw_message={"role": "assistant", "content": text},
        )


# ---------------------------------------------------------------------------
# Provider: Hugging Face Inference API
# ---------------------------------------------------------------------------

class HuggingFaceClient(BaseLLMClient):
    """
    Adapter for Hugging Face Inference API via huggingface_hub.
    Many HF Inference Endpoints support tool calling for capable models.
    For models that don't, falls back to ReAct-style text parsing.
    Install: pip install huggingface_hub

    Switch to HF:
      $env:LLM_PROVIDER = "hf"
      $env:LLM_API_KEY  = "hf_..."
      $env:LLM_MODEL    = "meta-llama/Meta-Llama-3-8B-Instruct"
    """

    def __init__(self, api_key: str, model: str):
        from huggingface_hub import InferenceClient  # lazy import
        self._client = InferenceClient(model=model, token=api_key)
        self._model  = model

    def _to_hf_tools(self) -> list[dict]:
        """Convert shared schema to HF/OpenAI-compat tool format."""
        return [{"type": "function", "function": t} for t in TOOLS_SCHEMA]

    def complete(self, messages: list[dict]) -> LLMResponse:
        try:
            response = self._client.chat_completion(
                messages=messages,
                tools=self._to_hf_tools(),
                tool_choice="auto",
            )
            msg = response.choices[0].message

            tool_calls: list[ToolCall] = []
            if msg.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.id or f"hf_{i}",
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments,
                    )
                    for i, tc in enumerate(msg.tool_calls)
                ]
                raw_tc = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
                return LLMResponse(
                    content=None,
                    tool_calls=tool_calls,
                    raw_message={"role": "assistant", "content": None, "tool_calls": raw_tc},
                )

            text = msg.content or ""
            # Fallback: check for ReAct-style tool calls in the text
            parsed = _parse_react_tool_calls(text)
            if parsed:
                return LLMResponse(
                    content=None,
                    tool_calls=parsed,
                    raw_message={"role": "assistant", "content": text},
                )

            return LLMResponse(
                content=text,
                tool_calls=[],
                raw_message={"role": "assistant", "content": text},
            )

        except Exception as e:
            # Some models/endpoints don't support tool_choice — degrade gracefully
            print(f"  [hf] Tool-calling not supported by model, using ReAct fallback: {e}")
            return self._complete_react(messages)

    def _complete_react(self, messages: list[dict]) -> LLMResponse:
        """Fallback: plain completion with ReAct text-based tool calls."""
        response = self._client.chat_completion(messages=messages)
        text = response.choices[0].message.content or ""
        parsed = _parse_react_tool_calls(text)
        return LLMResponse(
            content=None if parsed else text,
            tool_calls=parsed,
            raw_message={"role": "assistant", "content": text},
        )


# ---------------------------------------------------------------------------
# Provider: GPT4All (fully local, no API key required)
# ---------------------------------------------------------------------------

class GPT4AllClient(BaseLLMClient):
    """
    Adapter for GPT4All local inference.
    No API key required. The model file must be downloaded first.
    Uses ReAct-style text parsing for tool calls (no native function calling).
    Install: pip install gpt4all

    Switch to GPT4All:
      $env:LLM_PROVIDER = "gpt4all"
      $env:LLM_MODEL    = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"  # or any .gguf model
      # No LLM_API_KEY needed

    Note: GPT4All will download the model on first run (~4-8 GB).
    """

    def __init__(self, model: str):
        from gpt4all import GPT4All  # lazy import
        print(f"  [gpt4all] Loading model '{model}' (may download on first run)...")
        self._client = GPT4All(model)

    def complete(self, messages: list[dict]) -> LLMResponse:
        # GPT4All doesn't have a chat API that handles dicts natively in all versions,
        # so we flatten messages into a single prompt string.
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
    """Convert a list of chat messages to a single text prompt string."""
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
    Create and return the appropriate LLM client based on environment variables.

    Environment variables:
      LLM_PROVIDER  : "openai" (default) | "gemini" | "hf" | "gpt4all"
      LLM_API_KEY   : API key (not needed for gpt4all)
      LLM_MODEL     : Override default model for the chosen provider
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower().strip()
    api_key  = os.environ.get("LLM_API_KEY", "")
    model    = os.environ.get("LLM_MODEL", MODEL_DEFAULTS.get(provider, ""))

    print(f"  Provider : {provider}")
    print(f"  Model    : {model}")

    if provider == "openai":
        if not api_key:
            raise EnvironmentError(
                "LLM_API_KEY must be set for provider 'openai'.\n"
                "  $env:LLM_API_KEY = 'sk-...'"
            )
        return OpenAIClient(api_key=api_key, model=model)

    elif provider == "gemini":
        if not api_key:
            raise EnvironmentError(
                "LLM_API_KEY must be set for provider 'gemini'.\n"
                "  $env:LLM_API_KEY = 'AIza...'  (from Google AI Studio)"
            )
        return GeminiClient(api_key=api_key, model=model)

    elif provider == "hf":
        if not api_key:
            raise EnvironmentError(
                "LLM_API_KEY must be set for provider 'hf'.\n"
                "  $env:LLM_API_KEY = 'hf_...'  (from huggingface.co/settings/tokens)"
            )
        return HuggingFaceClient(api_key=api_key, model=model)

    elif provider == "gpt4all":
        return GPT4AllClient(model=model)

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. "
            "Valid options: openai, gemini, hf, gpt4all"
        )


# ---------------------------------------------------------------------------
# Agent loop — provider-agnostic
# ---------------------------------------------------------------------------

def run_agent(
    client: BaseLLMClient,
    messages: list[dict],
    max_iterations: int = 20,
) -> str:
    """
    Run the agentic tool-use loop using any BaseLLMClient.

    The loop:
      1. Calls client.complete(messages)
      2. If the response contains tool_calls → executes them, appends results, loops
      3. If the response contains content → returns it as final answer
    """
    for iteration in range(max_iterations):
        response = client.complete(messages)

        # Append the assistant turn to history
        messages.append(response.raw_message)

        if response.tool_calls:
            # Execute all requested tool calls
            for tc in response.tool_calls:
                print(f"  [tool] {tc.name}({json.dumps(tc.arguments)})")
                result = dispatch_tool(tc.name, tc.arguments)

                # Append tool result — use "tool" role for OpenAI/HF,
                # embed inline for providers that don't support the "tool" role
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
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
# Phase 2: Analysis — per-ADR
# ---------------------------------------------------------------------------

def _build_system_prompt(react_mode: bool = False) -> str:
    """Build the system prompt, optionally including ReAct tool-call instructions."""
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
        "3. For each rule in the ADR, determine if the code complies or violates it.\n"
        "4. Produce a structured JSON report.\n\n"
        "Your final answer MUST be valid JSON (no markdown fences) with this exact structure:\n"
        "{\n"
        '  "adr": "<ADR filename>",\n'
        '  "status": "COMPLIANT" or "NOT COMPLIANT",\n'
        '  "violations": [\n'
        "    {\n"
        '      "rule": "<rule ID, e.g. RULE-001-A>",\n'
        '      "description": "<what the rule requires>",\n'
        '      "finding": "<what was found in the code>",\n'
        '      "file": "<filename>",\n'
        '      "snippet": "<relevant code snippet>"\n'
        "    }\n"
        "  ],\n"
        '  "compliant_aspects": ["<description of what IS compliant>"],\n'
        '  "summary": "<one paragraph summary>"\n'
        "}\n\n"
        "If there are no violations, set \"status\" to \"COMPLIANT\" and \"violations\" to [].\n"
        "Be precise — quote actual code from the files as evidence.\n"
    )
    if react_mode:
        base += REACT_TOOL_INSTRUCTIONS
    return base


def analyze_adr(
    client: BaseLLMClient,
    adr_path: str,
    repo_files: list[str],
    react_mode: bool = False,
) -> dict:
    """
    Analyze a single ADR against the codebase using the given LLM client.
    Returns a compliance result dict.
    """
    adr_name = Path(adr_path).name
    print(f"\n{'='*60}")
    print(f"Analyzing: {adr_name}")
    print(f"{'='*60}")

    messages = [
        {"role": "system", "content": _build_system_prompt(react_mode)},
        {
            "role": "user",
            "content": (
                f"Please analyze the following ADR for compliance against the codebase.\n\n"
                f"ADR file: {adr_path}\n\n"
                f"Code files to analyze:\n{json.dumps(repo_files, indent=2)}\n\n"
                f"Steps:\n"
                f'1. Call read_file("{adr_path}") to read the ADR rules.\n'
                f"2. Call read_file(path) for each code file listed above.\n"
                f"3. Check each rule in the ADR against the code.\n"
                f"4. Return your analysis as a JSON object (no markdown)."
            ),
        },
    ]

    raw = run_agent(client, messages)
    return _parse_json_result(raw, adr_name)


def _parse_json_result(raw: str, adr_name: str) -> dict:
    """Parse the JSON response from the agent, stripping any accidental markdown."""
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "adr":               adr_name,
            "status":            "PARSE_ERROR",
            "violations":        [],
            "compliant_aspects": [],
            "summary":           raw,
        }


# ---------------------------------------------------------------------------
# Phase 3: Reflection
# ---------------------------------------------------------------------------

def reflect_on_results(
    client: BaseLLMClient,
    results: list[dict],
    repo_files: list[str],
    react_mode: bool = False,
) -> list[dict]:
    """
    Reflection step: the agent reviews its own output to catch missed violations
    or false positives. Returns an updated results list.
    """
    print(f"\n{'='*60}")
    print("Reflection Step: reviewing analysis for missed violations...")
    print(f"{'='*60}")

    system = (
        "You are a senior software architect performing a quality review of an "
        "ADR compliance analysis. Your goal is to identify any missed violations "
        "or incorrect assessments in the provided analysis.\n\n"
        "You have access to read_file(path) to re-read any code files.\n\n"
        "Return ONLY valid JSON (no markdown) — the updated full results array "
        "with the same structure as the input.\n"
        "You may: add missing violations, correct 'status' fields, "
        "improve evidence, or remove false positives."
    )
    if react_mode:
        system += "\n" + REACT_TOOL_INSTRUCTIONS

    user = (
        f"Here is the current ADR compliance analysis:\n{json.dumps(results, indent=2)}\n\n"
        f"Code files that were analyzed:\n{json.dumps(repo_files, indent=2)}\n\n"
        "Please review this analysis carefully:\n"
        "1. Re-read any code files you need to verify findings.\n"
        "2. Check for any violations that may have been missed.\n"
        "3. Check for any false positives.\n"
        "4. Return the complete updated results array as JSON (same structure, no markdown)."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    raw = run_agent(client, messages)

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        updated = json.loads(cleaned)
        if isinstance(updated, list):
            return updated
    except json.JSONDecodeError:
        print("[Warning] Reflection returned unparseable JSON — keeping original results.")

    return results


# ---------------------------------------------------------------------------
# Phase 4: Report
# ---------------------------------------------------------------------------

def print_report(results: list[dict]) -> None:
    """Print a human-readable compliance report to stdout."""
    print("\n")
    print("╔" + "═" * 70 + "╗")
    print("║" + " ADR COMPLIANCE REPORT ".center(70) + "║")
    print("╚" + "═" * 70 + "╝")

    total            = len(results)
    compliant_count  = sum(1 for r in results if r.get("status") == "COMPLIANT")
    non_compliant    = total - compliant_count

    print(f"\n📊 Summary: {compliant_count}/{total} COMPLIANT, {non_compliant}/{total} NOT COMPLIANT\n")

    for result in results:
        adr    = result.get("adr", "Unknown ADR")
        status = result.get("status", "UNKNOWN")
        icon   = "✅" if status == "COMPLIANT" else "❌"

        print(f"\n{icon} {adr}")
        print(f"   Status : {status}")
        print(f"   Summary: {result.get('summary', 'N/A')}")

        violations = result.get("violations", [])
        if violations:
            print(f"\n   Violations ({len(violations)}):")
            for v in violations:
                print(f"   ── Rule       : {v.get('rule', 'N/A')}")
                print(f"      Description: {v.get('description', 'N/A')}")
                print(f"      Finding    : {v.get('finding', 'N/A')}")
                print(f"      File       : {v.get('file', 'N/A')}")
                snippet = v.get("snippet", "")
                if snippet:
                    indented = "\n".join("      │ " + line for line in snippet.splitlines())
                    print(f"      Code :\n{indented}")
                print()

        for aspect in result.get("compliant_aspects", []):
            print(f"   ✓ {aspect}")

        print(f"\n{'─' * 72}")


def save_report(results: list[dict], output_path: str = "compliance_report.json") -> None:
    """Save the full structured results to a JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Full report saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("🔍 ADR Compliance Agent Starting...")
    print(f"   ADR directory : {ADR_DIR}")
    print(f"   Repo directory: {REPO_DIR}\n")

    # Create the LLM client based on environment variables
    print("🔌 Initialising LLM client...")
    client = create_llm_client()

    # Providers without native function calling use ReAct-style text parsing
    react_mode = isinstance(client, (GPT4AllClient,))

    # Phase 1: Discover files
    print("\n📂 Discovering files...")
    adr_files, repo_files = discover_files()
    print(f"   ADRs : {[Path(f).name for f in adr_files]}")
    print(f"   Code : {[Path(f).name for f in repo_files]}")

    # Phase 2: Analyze each ADR
    results: list[dict] = []
    for adr_path in adr_files:
        result = analyze_adr(client, adr_path, repo_files, react_mode=react_mode)
        results.append(result)

    # Phase 3: Reflection
    results = reflect_on_results(client, results, repo_files, react_mode=react_mode)

    # Phase 4: Report
    print_report(results)
    save_report(results)

    print("\n✅ ADR Compliance Agent finished.")


if __name__ == "__main__":
    main()
