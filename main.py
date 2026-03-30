"""
main.py - Entry point for the ADR Compliance Agent.

Usage:
    python main.py                        # run full compliance analysis
    python main.py --reingest             # force re-ingestion of all data
    python main.py --output my_report.json  # override default output filename
"""

import os
import json
import argparse

from dotenv import load_dotenv
from src.agent import ComplianceAgent

load_dotenv()

DEFAULT_OUTPUT = "report.json"


def build_config() -> dict:
    return {
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "gemini_model": os.getenv("GEMINI_MODEL"),
        "embedding_model": os.getenv("GEMINI_EMBEDDING_MODEL"),
        "chroma_persist_dir": os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
        "data_dir": os.getenv("DATA_DIR", "./data"),
        "chunk_size": int(os.getenv("CHUNK_SIZE", "1000")),
        "chunk_overlap": int(os.getenv("CHUNK_OVERLAP", "200")),
        "top_k_results": int(os.getenv("TOP_K_RESULTS", "5")),
        "llm_delay": float(os.getenv("LLM_REQUEST_DELAY", "4")),
    }


def main():
    parser = argparse.ArgumentParser(description="ADR Compliance Agent")
    parser.add_argument("--reingest", action="store_true", help="Force re-ingestion of all data")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help=f"Output JSON report filename (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    config = build_config()
    if not config["gemini_api_key"]:
        print("Error: GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
        raise SystemExit(1)

    agent = ComplianceAgent(config)

    print("Setting up vector store...")
    agent.setup(force_reingest=args.reingest)

    print("\nRunning compliance analysis...")
    agent.run()

    if agent._analyses:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(agent._analyses, f, indent=2)
        print(f"\nDetailed analysis saved to: {args.output}")


if __name__ == "__main__":
    main()
