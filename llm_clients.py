import os
import re
import json
import abc
from dataclasses import dataclass, field
from typing import Optional, Any

from config import MODEL_DEFAULTS
from tools import TOOLS_SCHEMA

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

class BaseLLMClient(abc.ABC):
    """
    All LLM adapters implement this interface.
    The agent loop only ever calls .complete().
    """
    @abc.abstractmethod
    def complete(self, messages: list[dict]) -> LLMResponse:
        ...

class GeminiClient(BaseLLMClient):
    """
    Adapter for Google Gemini via the google-genai SDK.
    Uses native function calling for Phase 2.
    """
    def __init__(self, api_key: str, model: str):
        from google import genai
        from google.genai import types as genai_types

        self._genai       = genai
        self._types       = genai_types
        self._model_name  = model
        self._client      = genai.Client(api_key=api_key)

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


    def complete(self, messages: list[dict]) -> LLMResponse:
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        history    = [m for m in messages if m["role"] != "system"]

        contents = []
        for m in history:
            role = "model" if m["role"] == "assistant" else "user"
            content_text = m.get("content") or ""

            if m["role"] == "tool":
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

        generate_config = self._types.GenerateContentConfig(
            system_instruction=system_msg or None,
            tools=self._tools,
        )

        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=generate_config,
        )

        candidate = response.candidates[0]
        tool_calls: list[ToolCall] = []

        if candidate.content and candidate.content.parts:
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

        text = "".join(p.text for p in candidate.content.parts if hasattr(p, "text")) if candidate.content else ""
        return LLMResponse(
            content=text,
            tool_calls=[],
            raw_message={"role": "assistant", "content": text},
        )


REACT_TOOL_PATTERN = re.compile(r"TOOL_CALL:\s*(\{.*?\})", re.DOTALL)

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

def _flatten_messages_to_prompt(messages: list[dict]) -> str:
    """Flatten chat messages to a single prompt string."""
    parts = []
    for m in messages:
        role    = m.get("role", "user").upper()
        content = m.get("content") or ""
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts) + "\n\n[ASSISTANT]\n"

class GPT4AllClient(BaseLLMClient):
    """
    Adapter for GPT4All local inference (ReAct text-based tool calling).
    """
    def __init__(self, model: str):
        from gpt4all import GPT4All
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


def create_llm_client() -> BaseLLMClient:
    """Create and return the appropriate LLM client."""
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
