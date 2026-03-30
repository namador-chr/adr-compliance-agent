"""
embeddings.py - Gemini embedding service.

Wraps the google-genai embed_content API with separate task types
for indexing documents vs querying.
"""

import time
from google import genai
from google.genai import types


class EmbeddingService:
    def __init__(self, api_key: str, model: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        """Embed a single text string."""
        result = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        return result.embeddings[0].values

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query (uses RETRIEVAL_QUERY task type)."""
        return self.embed(text, task_type="RETRIEVAL_QUERY")

    def embed_batch(
        self,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
        delay: float = 0.1,
    ) -> list[list[float]]:
        """Embed a list of texts, with a small delay to respect rate limits."""
        embeddings = []
        for text in texts:
            embeddings.append(self.embed(text, task_type=task_type))
            if delay > 0:
                time.sleep(delay)
        return embeddings
