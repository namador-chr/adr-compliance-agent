import os
from pathlib import Path

# Paths
ADR_DIR  = Path(__file__).parent / "data" / "adrs"
REPO_DIR = Path(__file__).parent / "data" / "repo"

# Default model for each provider
MODEL_DEFAULTS: dict[str, str] = {
    "gemini":  "gemini-3.1-flash-lite-preview",
    "gpt4all": "Meta-Llama-3-8B-Instruct.Q4_0.gguf",
}
