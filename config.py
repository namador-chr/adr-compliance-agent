import os
from pathlib import Path
from dataclasses import dataclass

@dataclass
class AppConfig:
    """Central configuration for paths and environment variables."""
    # Paths
    BASE_DIR: Path = Path(__file__).parent
    ADR_DIR: Path = BASE_DIR / "data" / "adrs"
    REPO_DIR: Path = BASE_DIR / "data" / "repo"
    
    # Model Defaults
    MODEL_DEFAULTS = {
        "gemini":  "gemini-2.0-flash",
        "gpt4all": "Meta-Llama-3-8B-Instruct.Q4_0.gguf",
    }
    
    # LLM Settings
    PROVIDER: str = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()
    API_KEY: str = os.environ.get("LLM_API_KEY", "")
    MODEL: str = os.environ.get("LLM_MODEL", MODEL_DEFAULTS.get(PROVIDER, ""))

config = AppConfig()
