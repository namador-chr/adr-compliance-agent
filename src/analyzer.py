"""
analyzer.py - LLM-based compliance analysis and self-reflection.

ComplianceAnalyzer uses Gemini to:
  1. analyze()  - check a code file against retrieved ADR rules
  2. reflect()  - self-critique the analysis for quality and completeness
"""

import json
import time
from google import genai
from google.genai import types


_COMPLIANCE_SYSTEM = """You are an expert C# .NET code reviewer specialising in architectural compliance.
Respond ONLY with valid JSON — no markdown fences, no extra text."""

_COMPLIANCE_PROMPT = """You will be given a C# source file and the Architectural Decision Records (ADRs) that apply to this project.

Analyse the code and determine whether it complies with the ADR rules.

ADRs:
{adr_context}

---

File: {filename}
```
{code}
```

Return a JSON object with exactly this shape:
{{
  "filename": "<filename>",
  "overall_status": "compliant" | "partial" | "non-compliant",
  "compliance_score": <integer 0-100>,
  "violations": [
    {{
      "adr_reference": "<ADR title or file>",
      "description": "<what rule was violated>",
      "location": "<class/method/line hint>",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "compliant_aspects": ["<patterns or practices that correctly follow the rules>"],
  "recommendations": ["<specific, actionable fix for each violation>"]
}}
"""

_REFLECTION_SYSTEM = """You are a senior reviewer auditing the quality of a compliance analysis report.
Respond ONLY with valid JSON — no markdown fences, no extra text."""

_REFLECTION_PROMPT = """Review the following ADR compliance analysis for accuracy, completeness, and usefulness.

Analysis:
{analysis}

Return a JSON object with exactly this shape:
{{
  "confidence": <integer 0-100>,
  "missed_issues": ["<anything the analysis may have overlooked>"],
  "quality_notes": "<brief assessment of analysis quality>",
  "final_verdict": "<one-sentence summary of this file's overall compliance health>"
}}
"""


class ComplianceAnalyzer:
    def __init__(self, client: genai.Client, model: str, llm_delay: float = 4.0):
        self.client = client
        self.model = model
        self.llm_delay = llm_delay

    def analyze(self, code_content: str, filename: str, relevant_adrs: list[dict]) -> dict:
        """Analyse a code file against retrieved ADR chunks."""
        adr_context = "\n\n---\n\n".join(
            f"### {item['metadata'].get('source', 'ADR')}\n{item['content']}"
            for item in relevant_adrs
        )

        prompt = _COMPLIANCE_PROMPT.format(
            adr_context=adr_context or "(no ADRs found — check data/adrs/)",
            filename=filename,
            code=code_content[:8000],  # guard against huge files
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_COMPLIANCE_SYSTEM,
                response_mime_type="application/json",
            ),
        )

        time.sleep(self.llm_delay)
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            return {"filename": filename, "error": "parse_failed", "raw": response.text}

    def reflect(self, analysis: dict) -> dict:
        """Self-critique the compliance analysis for quality and missed issues."""
        prompt = _REFLECTION_PROMPT.format(analysis=json.dumps(analysis, indent=2))

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_REFLECTION_SYSTEM,
                response_mime_type="application/json",
            ),
        )

        time.sleep(self.llm_delay)
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            return {"error": "parse_failed", "raw": response.text}
