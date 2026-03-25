#!/usr/bin/env python3
"""
ADR Compliance Agent — LLM-Agnostic Version
============================================
Analyzes a C# codebase for compliance with Architecture Decision Records (ADRs).

Architecture: "Reasoning first, Formatting second"
  Phase 2 — Free Markdown reasoning  (no JSON pressure on the analysis step)
  Phase 3 — JSON-only formatting call (provider JSON modes + retry loop)

Supported providers (set via environment variables):
  LLM_PROVIDER = "openai"   (default) — requires: pip install openai
  LLM_PROVIDER = "gemini"             — requires: pip install google-genai
  LLM_PROVIDER = "hf"                 — requires: pip install huggingface_hub
  LLM_PROVIDER = "gpt4all"            — requires: pip install gpt4all

  LLM_API_KEY  = your API key (not needed for gpt4all local inference)
  LLM_MODEL    = override the default model for the chosen provider

Usage:
  # OpenAI (default)
  $env:LLM_PROVIDER = "openai";  $env:LLM_API_KEY = "sk-..."
  python main.py

  # Gemini
  $env:LLM_PROVIDER = "gemini";  $env:LLM_API_KEY = "AIza..."
  $env:LLM_MODEL = "gemini-2.0-flash"   # or gemini-1.5-pro, gemini-2.5-pro-exp-03-25 etc.
  python main.py

  # Hugging Face Inference API
  $env:LLM_PROVIDER = "hf";  $env:LLM_API_KEY = "hf_..."
  python main.py

  # GPT4All (fully local — no API key needed)
  $env:LLM_PROVIDER = "gpt4all"
  python main.py
"""

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
    "openai":  "gpt-4o",
    "gemini":  "gemini-2.0-flash",
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

# OpenAI / HF-compat tool list
OPENAI_TOOLS = [{"type": "function", "function": t} for t in TOOLS_SCHEMA]

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

    def complete_json(self, messages: list[dict]) -> str:
        """
        JSON-mode completion: ask the model to respond with valid JSON only.
        Default implementation: plain text completion with a strong JSON prompt.
        Override in subclasses that have a native JSON mode for guaranteed output.
        """
        response = self.complete(messages)
        return response.content or ""


# ---------------------------------------------------------------------------
# Provider: OpenAI
# ---------------------------------------------------------------------------

class OpenAIClient(BaseLLMClient):
    """
    Adapter for the OpenAI Chat Completions API.
    Uses native function calling for Phase 2 and response_format JSON mode for Phase 3.
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
        raw: dict[str, Any] = {"role": "assistant", "content": msg.content}
        tool_calls: list[ToolCall] = []

        if msg.tool_calls:
            raw["tool_calls"] = [
                {
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
            tool_calls = [
                ToolCall(id=tc.id, name=tc.function.name,
                         arguments=json.loads(tc.function.arguments))
                for tc in msg.tool_calls
            ]

        return LLMResponse(
            content=msg.content if not tool_calls else None,
            tool_calls=tool_calls,
            raw_message=raw,
        )

    def complete_json(self, messages: list[dict]) -> str:
        """
        Uses OpenAI's native response_format=json_object mode — guaranteed valid JSON output.
        No tool calls: this is a pure formatting call.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""


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

    def complete_json(self, messages: list[dict]) -> str:
        """
        Uses Gemini's response_mime_type='application/json' for guaranteed JSON output.
        No tool calls: this is a pure formatting call.
        """
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_parts = [m["content"] for m in messages
                      if m["role"] in ("user", "assistant") and m.get("content")]

        config = self._types.GenerateContentConfig(
            system_instruction=system_msg or None,
            response_mime_type="application/json",
        )

        response = self._client.models.generate_content(
            model=self._model_name,
            contents=user_parts,
            config=config,
        )
        return response.text or ""


# ---------------------------------------------------------------------------
# Provider: Hugging Face Inference API
# ---------------------------------------------------------------------------

class HuggingFaceClient(BaseLLMClient):
    """
    Adapter for Hugging Face Inference API via huggingface_hub.
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

    def _hf_tools(self) -> list[dict]:
        return [{"type": "function", "function": t} for t in TOOLS_SCHEMA]

    def complete(self, messages: list[dict]) -> LLMResponse:
        try:
            response = self._client.chat_completion(
                messages=messages,
                tools=self._hf_tools(),
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
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]
                return LLMResponse(
                    content=None,
                    tool_calls=tool_calls,
                    raw_message={"role": "assistant", "content": None, "tool_calls": raw_tc},
                )

            text   = msg.content or ""
            parsed = _parse_react_tool_calls(text)
            if parsed:
                return LLMResponse(
                    content=None, tool_calls=parsed,
                    raw_message={"role": "assistant", "content": text},
                )
            return LLMResponse(
                content=text, tool_calls=[],
                raw_message={"role": "assistant", "content": text},
            )

        except Exception as e:
            print(f"  [hf] Tool-calling failed, using ReAct fallback: {e}")
            return self._complete_react(messages)

    def _complete_react(self, messages: list[dict]) -> LLMResponse:
        response = self._client.chat_completion(messages=messages)
        text     = response.choices[0].message.content or ""
        parsed   = _parse_react_tool_calls(text)
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
      LLM_PROVIDER  : "openai" (default) | "gemini" | "hf" | "gpt4all"
      LLM_API_KEY   : API key (not needed for gpt4all)
      LLM_MODEL     : Override the default model for the chosen provider
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower().strip()
    api_key  = os.environ.get("LLM_API_KEY", "")
    model    = os.environ.get("LLM_MODEL", MODEL_DEFAULTS.get(provider, ""))

    print(f"  Provider : {provider}")
    print(f"  Model    : {model}")

    if provider == "openai":
        if not api_key:
            raise EnvironmentError("LLM_API_KEY must be set for provider 'openai'.")
        return OpenAIClient(api_key=api_key, model=model)

    elif provider == "gemini":
        if not api_key:
            raise EnvironmentError(
                "LLM_API_KEY must be set for provider 'gemini'.\n"
                "  Get one at: https://aistudio.google.com/app/apikey"
            )
        return GeminiClient(api_key=api_key, model=model)

    elif provider == "hf":
        if not api_key:
            raise EnvironmentError("LLM_API_KEY must be set for provider 'hf'.")
        return HuggingFaceClient(api_key=api_key, model=model)

    elif provider == "gpt4all":
        return GPT4AllClient(model=model)

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. "
            "Valid options: openai, gemini, hf, gpt4all"
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
                print("Waiting 10 seconds...")
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
# Phase 3: Reflection + JSON formatting
#
# This is the ONLY phase that produces JSON. It receives the free-form
# Markdown from Phase 2 and is responsible for:
#   a) Reviewing the analysis for accuracy (missed violations, false positives)
#   b) Producing the final structured JSON via provider JSON modes + retry loop
# ---------------------------------------------------------------------------

# The strict JSON schema given exclusively to Phase 3
_JSON_SCHEMA_EXAMPLE = """\
[
  {
    "adr": "<ADR filename, e.g. ADR-001-restful-resource-naming.md>",
    "status": "COMPLIANT" or "NOT COMPLIANT",
    "violations": [
      {
        "rule": "<rule ID, e.g. RULE-001-A>",
        "description": "<what the rule requires>",
        "finding": "<what was found in the code>",
        "file": "<source filename>",
        "snippet": "<quoted code snippet as evidence>"
      }
    ],
    "compliant_aspects": ["<what IS compliant>"],
    "summary": "<one paragraph summary>"
  }
]"""

_JSON_RULES = (
    "Rules for the JSON output:\n"
    "- Output a JSON ARRAY, one object per ADR, in the same order as the analyses.\n"
    "- If an ADR has no violations, set status to COMPLIANT and violations to [].\n"
    "- Always include at least one compliant_aspects entry.\n"
    "- Quote real code snippets from the files as evidence for every violation.\n"
    "- Output ONLY the JSON array — no preamble, no markdown fences, no trailing text."
)


def _extract_json(raw: str) -> Optional[list[dict]]:
    """
    Try to parse a JSON array from the model response.
    Strips markdown fences if present, attempts to locate the first '[' array start.
    Returns the parsed list or None if it cannot be parsed.
    """
    cleaned = raw.strip()

    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    # Find the start of a JSON array (handles accidental preamble text)
    bracket = cleaned.find("[")
    if bracket != -1:
        cleaned = cleaned[bracket:]

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]  # model returned a single object instead of array
    except json.JSONDecodeError:
        pass
    return None


def reflect_on_results(
    client: BaseLLMClient,
    markdown_analyses: list[str],
    adr_names: list[str],
    repo_files: list[str],
    react_mode: bool = False,
    max_retries: int = 3,
) -> list[dict]:
    """
    Phase 3 — Reflection and structured JSON formatting.

    Receives free-form Markdown analyses from Phase 2 and:
      1. Reviews them for missed violations or false positives.
      2. Produces the final structured JSON via provider JSON mode (if available)
         or a retry loop with parse validation (for providers without JSON mode).

    Returns a list of compliance result dicts, one per ADR.
    """
    print(f"\n{'='*60}")
    print("Reflection Step: reviewing and formatting final report...")
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
        "2. FORMAT: Output the final corrected result as a strict JSON array.\n\n"
        f"Required JSON structure:\n{_JSON_SCHEMA_EXAMPLE}\n\n"
        f"{_JSON_RULES}"
    )
    if react_mode:
        system += "\n" + REACT_TOOL_INSTRUCTIONS

    user = (
        f"Here are the Markdown analyses for each ADR:\n\n{analyses_block}\n\n"
        f"Code files available for re-reading if needed:\n{json.dumps(repo_files, indent=2)}\n\n"
        "Review the analyses, verify uncertain findings by re-reading code files if needed, "
        "then output the final JSON array."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    # ── Strategy 1: Use provider-native JSON mode (guaranteed valid JSON) ────
    # Providers that override complete_json() get reliable JSON without retries.
    # For providers that don't (HF, GPT4All), complete_json() falls back to
    # complete() and we apply the retry loop below.

    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            raw = client.complete_json(messages)
        else:
            # ── Strategy 2: Retry loop with escalating correction prompt ────
            print(f"  [reflect] JSON parse failed — retry {attempt}/{max_retries}")
            correction = (
                "Your previous response was not valid JSON. "
                "Output ONLY the raw JSON array with no preamble or markdown fences. "
                f"Required structure:\n{_JSON_SCHEMA_EXAMPLE}"
            )
            retry_messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user",      "content": correction},
            ]
            raw = client.complete_json(retry_messages)

        result = _extract_json(raw)
        if result is not None:
            print(f"  [reflect] JSON parsed successfully (attempt {attempt})")
            return result

    # ── Strategy 3: Fallback — return minimal dicts so the report renders ────
    print("[Warning] All reflection attempts failed — returning raw Markdown as summary.")
    return [
        {
            "adr":               name,
            "status":            "PARSE_ERROR",
            "violations":        [],
            "compliant_aspects": [],
            "summary":           md[:500] + "..." if len(md) > 500 else md,
        }
        for name, md in zip(adr_names, markdown_analyses)
    ]


# ---------------------------------------------------------------------------
# Phase 4: Report
# ---------------------------------------------------------------------------

def print_report(results: list[dict]) -> None:
    """Print a human-readable compliance report to stdout."""
    print("\n")
    print("╔" + "═" * 70 + "╗")
    print("║" + " ADR COMPLIANCE REPORT ".center(70) + "║")
    print("╚" + "═" * 70 + "╝")

    total           = len(results)
    compliant_count = sum(1 for r in results if r.get("status") == "COMPLIANT")
    non_compliant   = total - compliant_count

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

    # Phase 3: Reflection + structured JSON output (provider JSON mode + retry loop)
    results = reflect_on_results(
        client, markdown_analyses, adr_names, repo_files, react_mode=react_mode
    )

    # Phase 4: Report
    print_report(results)
    save_report(results)

    print("\n✅ ADR Compliance Agent finished.")


if __name__ == "__main__":
    main()
