"""
ingestion.py - File loading and chunking.

Loads ADR markdown files and C# source files from the data directory,
then splits them into overlapping chunks for embedding.
"""

import pathlib
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

SUPPORTED_ADR_EXTENSIONS = {".md"}
SUPPORTED_CODE_EXTENSIONS = {".cs", ".csproj", ".json", ".xml"}


@dataclass
class Document:
    content: str
    source: str       # relative path from data_dir
    doc_type: str     # 'adr' or 'code'
    metadata: dict = field(default_factory=dict)


def load_adrs(data_dir: str) -> list[Document]:
    """Load all ADR markdown files from data/adrs/."""
    adrs_path = pathlib.Path(data_dir) / "adrs"
    documents = []

    if not adrs_path.exists():
        return documents

    for file_path in sorted(adrs_path.rglob("*")):
        if file_path.suffix.lower() in SUPPORTED_ADR_EXTENSIONS:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if content.strip():
                documents.append(Document(
                    content=content,
                    source=str(file_path.relative_to(data_dir)),
                    doc_type="adr",
                    metadata={"filename": file_path.name, "path": str(file_path)},
                ))

    return documents


def load_code_files(data_dir: str) -> list[Document]:
    """Load all C# source files from data/repo/."""
    repo_path = pathlib.Path(data_dir) / "repo"
    documents = []

    if not repo_path.exists():
        return documents

    for file_path in sorted(repo_path.rglob("*")):
        if file_path.suffix.lower() in SUPPORTED_CODE_EXTENSIONS:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if content.strip():
                documents.append(Document(
                    content=content,
                    source=str(file_path.relative_to(data_dir)),
                    doc_type="code",
                    metadata={"filename": file_path.name, "path": str(file_path)},
                ))

    return documents


def chunk_document(doc: Document, chunk_size: int = 1000, overlap: int = 200) -> list[Document]:
    """Split a document into overlapping chunks using LangChain's RecursiveCharacterTextSplitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    texts = splitter.split_text(doc.content)

    if not texts:
        return [doc]

    return [
        Document(
            content=chunk,
            source=doc.source,
            doc_type=doc.doc_type,
            metadata={**doc.metadata, "chunk_index": i},
        )
        for i, chunk in enumerate(texts)
    ]
