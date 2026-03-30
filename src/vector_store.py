"""
vector_store.py - ChromaDB persistence layer.

Manages two collections (adrs, code) and exposes add/search/count/clear.
Embeddings are computed externally by EmbeddingService and passed in directly
so ChromaDB never calls its own embedding logic.
"""

import os
import time
import chromadb
from src.embeddings import EmbeddingService
from src.ingestion import Document

COLLECTION_ADRS = "adrs"

# Small delay between embedding calls to stay within rate limits
_EMBED_DELAY = 0.15


class VectorStore:
    def __init__(self, persist_dir: str, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)

    def _collection(self, name: str):
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, documents: list[Document], collection_name: str):
        """Embed and upsert a list of documents into the named collection."""
        collection = self._collection(collection_name)

        ids, embeddings, texts, metadatas = [], [], [], []

        for doc in documents:
            doc_id = f"{doc.source}::chunk_{doc.metadata.get('chunk_index', 0)}"
            embedding = self.embedding_service.embed(doc.content)
            time.sleep(_EMBED_DELAY)

            ids.append(doc_id)
            embeddings.append(embedding)
            texts.append(doc.content)
            metadatas.append({
                "source": doc.source,
                "doc_type": doc.doc_type,
                "filename": doc.metadata.get("filename", ""),
            })

        # Upsert in batches of 50
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[i:i + batch_size],
                embeddings=embeddings[i:i + batch_size],
                documents=texts[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )

    def search(self, query: str, collection_name: str, n_results: int = 5) -> list[dict]:
        """Semantic search — returns ranked results with content and metadata."""
        collection = self._collection(collection_name)
        count = collection.count()
        if count == 0:
            return []

        query_embedding = self.embedding_service.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )

        return [
            {
                "id": results["ids"][0][j],
                "content": results["documents"][0][j],
                "metadata": results["metadatas"][0][j],
                "distance": results["distances"][0][j],
            }
            for j in range(len(results["ids"][0]))
        ]

    def collection_count(self, collection_name: str) -> int:
        try:
            return self._collection(collection_name).count()
        except Exception:
            return 0

    def clear_collection(self, collection_name: str):
        try:
            self.client.delete_collection(collection_name)
        except Exception:
            pass
