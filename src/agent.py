"""
agent.py - Agentic loop with Gemini tool-calling.

ComplianceAgent orchestrates the full pipeline:
  - setup()  : ingest files, build ChromaDB index
  - run()    : agentic loop where Gemini calls tools to drive analysis

Tools exposed to the LLM:
  list_code_files        - enumerate C# files available
  analyze_file           - compliance check for one file (RAG + LLM + reflection)
  generate_final_report  - compile all findings into a summary
"""

import json
import time
from google import genai
from google.genai import types

from src.ingestion import load_adrs, load_code_files, chunk_document, Document
from src.embeddings import EmbeddingService
from src.vector_store import VectorStore, COLLECTION_ADRS
from src.analyzer import ComplianceAnalyzer


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_AGENT_SYSTEM = """You are an ADR Compliance Agent for a C# .NET codebase.

Your job: systematically check every source code file against the project's
Architectural Decision Records (ADRs) and produce a compliance report.

Workflow (follow this order):
1. Call `list_code_files` to discover what files exist.
2. Call `analyze_file` for EVERY file returned.
3. After all files are analyzed, call `generate_final_report`.
4. Summarise the key findings and top recommendations in plain language.

Be thorough — do not skip files."""


# ---------------------------------------------------------------------------
# Tool declarations
# ---------------------------------------------------------------------------

_LIST_CODE_FILES = types.FunctionDeclaration(
    name="list_code_files",
    description="List all C# source files available for compliance analysis.",
    parameters=types.Schema(type=types.Type.OBJECT, properties={}),
)

_ANALYZE_FILE = types.FunctionDeclaration(
    name="analyze_file",
    description=(
        "Analyze one source file for ADR compliance. "
        "Retrieves relevant ADRs via semantic search, runs LLM compliance check, "
        "then self-reflects on the analysis quality."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "filename": types.Schema(
                type=types.Type.STRING,
                description="Relative path of the file (as returned by list_code_files).",
            )
        },
        required=["filename"],
    ),
)

_GENERATE_FINAL_REPORT = types.FunctionDeclaration(
    name="generate_final_report",
    description="Compile all per-file analyses into a consolidated compliance report.",
    parameters=types.Schema(type=types.Type.OBJECT, properties={}),
)

_TOOLS = types.Tool(function_declarations=[_LIST_CODE_FILES, _ANALYZE_FILE, _GENERATE_FINAL_REPORT])


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ComplianceAgent:
    def __init__(self, config: dict):
        self.config = config
        self.data_dir = config["data_dir"]

        self._gemini = genai.Client(api_key=config["gemini_api_key"])
        self._embeddings = EmbeddingService(
            api_key=config["gemini_api_key"],
            model=config["embedding_model"],
        )
        self._store = VectorStore(
            persist_dir=config["chroma_persist_dir"],
            embedding_service=self._embeddings,
        )
        self._analyzer = ComplianceAnalyzer(
            client=self._gemini,
            model=config["gemini_model"],
            llm_delay=config.get("llm_delay", 4.0),
        )

        # Populated during setup / analysis
        self._code_docs: dict[str, Document] = {}
        self._analyses: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Setup: ingest files and build vector index
    # ------------------------------------------------------------------

    def setup(self, force_reingest: bool = False):
        """Load data files and populate the ChromaDB vector store."""
        if force_reingest:
            print("Clearing existing ADR index...")
            self._store.clear_collection(COLLECTION_ADRS)

        # Code files only need to be in memory — they are read in full per analysis
        for doc in load_code_files(self.data_dir):
            self._code_docs[doc.source] = doc

        self._ingest_collection(
            name="ADR",
            documents=load_adrs(self.data_dir),
            collection=COLLECTION_ADRS,
        )

    def _ingest_collection(self, name: str, documents: list[Document], collection: str):
        existing = self._store.collection_count(collection)
        if existing > 0:
            print(f"Using existing {name} index ({existing} chunks).")
            return

        if not documents:
            print(f"Warning: no {name} files found.")
            return

        chunks = []
        for doc in documents:
            chunks.extend(chunk_document(
                doc,
                chunk_size=self.config.get("chunk_size", 1000),
                overlap=self.config.get("chunk_overlap", 200),
            ))

        print(f"Embedding {len(chunks)} {name} chunks...")
        self._store.add_documents(chunks, collection)
        print(f"Done — {len(documents)} {name} file(s) indexed.")

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_list_code_files(self) -> dict:
        files = list(self._code_docs.keys())
        if not files:
            return {"files": [], "message": "No code files found in data/repo/"}
        return {"files": files, "count": len(files)}

    def _tool_analyze_file(self, filename: str) -> dict:
        doc = self._code_docs.get(filename)
        if not doc:
            return {"error": f"File not found: {filename}"}

        print(f"  Analyzing: {filename}")

        relevant_adrs = self._store.search(
            query=doc.content[:2000],
            collection_name=COLLECTION_ADRS,
            n_results=self.config.get("top_k_results", 5),
        )

        analysis = self._analyzer.analyze(
            code_content=doc.content,
            filename=filename,
            relevant_adrs=relevant_adrs,
        )
        analysis["reflection"] = self._analyzer.reflect(analysis)
        self._analyses[filename] = analysis

        return {
            "filename": filename,
            "status": analysis.get("overall_status", "unknown"),
            "score": analysis.get("compliance_score", 0),
            "violations_count": len(analysis.get("violations", [])),
        }

    def _tool_generate_final_report(self) -> dict:
        if not self._analyses:
            return {"error": "No files analyzed yet."}

        scores = [a.get("compliance_score", 0) for a in self._analyses.values()]
        statuses = [a.get("overall_status", "unknown") for a in self._analyses.values()]
        all_violations = [
            {**v, "file": fname}
            for fname, a in self._analyses.items()
            for v in a.get("violations", [])
        ]

        return {
            "summary": {
                "total_files": len(self._analyses),
                "average_score": round(sum(scores) / len(scores), 1),
                "compliant": statuses.count("compliant"),
                "partial": statuses.count("partial"),
                "non_compliant": statuses.count("non-compliant"),
                "total_violations": len(all_violations),
                "high_severity": sum(1 for v in all_violations if v.get("severity") == "high"),
            },
            "per_file": [
                {
                    "file": f,
                    "status": a.get("overall_status"),
                    "score": a.get("compliance_score"),
                    "violations": len(a.get("violations", [])),
                    "reflection_confidence": a.get("reflection", {}).get("confidence", "N/A"),
                    "final_verdict": a.get("reflection", {}).get("final_verdict", ""),
                }
                for f, a in self._analyses.items()
            ],
            "top_violations": [v for v in all_violations if v.get("severity") == "high"][:10],
        }

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------

    def run(self, query: str | None = None) -> str:
        """Run the compliance agent. Returns the agent's final narrative."""
        if not query:
            query = (
                "Analyze all code files in the repository for ADR compliance. "
                "List the files, analyze each one, then generate a final report."
            )

        print("\nStarting compliance analysis agent...")

        contents = [types.Content(role="user", parts=[types.Part(text=query)])]
        max_iterations = 30

        for iteration in range(max_iterations):
            response = self._gemini.models.generate_content(
                model=self.config["gemini_model"],
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[_TOOLS],
                    system_instruction=_AGENT_SYSTEM,
                ),
            )

            time.sleep(self.config.get("llm_delay", 4.0))
            candidate = response.candidates[0]
            contents.append(types.Content(role="model", parts=candidate.content.parts))

            function_calls = [
                p.function_call for p in candidate.content.parts if p.function_call
            ]

            if not function_calls:
                # No more tool calls — agent produced its final answer
                return "".join(p.text for p in candidate.content.parts if p.text)

            # Execute each tool call and return results
            tool_results = []
            for fc in function_calls:
                print(f"  Tool: {fc.name}({dict(fc.args) if fc.args else ''})")

                if fc.name == "list_code_files":
                    result = self._tool_list_code_files()
                elif fc.name == "analyze_file":
                    result = self._tool_analyze_file(fc.args.get("filename", ""))
                elif fc.name == "generate_final_report":
                    result = self._tool_generate_final_report()
                else:
                    result = {"error": f"Unknown tool: {fc.name}"}

                tool_results.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response=result,
                    )
                ))

            contents.append(types.Content(role="user", parts=tool_results))

        return "Max iterations reached — analysis may be incomplete."
