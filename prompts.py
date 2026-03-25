REACT_TOOL_INSTRUCTIONS = """
When you need to call a tool, output it on its own line in this exact format:
  TOOL_CALL: {"name": "<tool_name>", "arguments": {<args as JSON>}}

Available tools:
  - list_files(folder)   : list all files in a directory
  - read_file(path)      : read the full contents of a file

After receiving the tool result, continue your analysis.
Do NOT wrap your final answer in markdown fences.
"""

def get_analysis_system_prompt(react_mode: bool = False) -> str:
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

def get_reflection_system_prompt(react_mode: bool = False) -> str:
    """
    Phase 3 system prompt: asks for final polished Markdown report formatting.
    """
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
    return system
