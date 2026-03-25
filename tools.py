import json
from pathlib import Path

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
