"""Real local ONNX embedding; no random or keyword fallback."""
import hashlib
import math
from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, question: str) -> list[float]: ...


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int) -> None:
    if len(vectors) != count:
        raise ValueError("Embedding count does not match input count")
    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(x) for x in vector):
            raise ValueError("Embedding dimension mismatch or non-finite value")
        if not any(x != 0 for x in vector):
            raise ValueError("Zero vector cannot be used for cosine search")


class MyEmbedder:
    def __init__(self, model_name: str, cache_dir: str = ".cache/fastembed") -> None:
        from fastembed import TextEmbedding
        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name, cache_dir=cache_dir,
                                   providers=["CPUExecutionProvider"], threads=2)
        self.dimensions = len(list(self.model.query_embed("dimension check"))[0])
        self.model_files = {}
        for path in sorted(Path(cache_dir).rglob("*")):
            if path.is_file() and path.suffix in {".onnx", ".json", ".txt"}:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                self.model_files[str(path.relative_to(cache_dir))] = digest.hexdigest()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = [v.tolist() for v in self.model.passage_embed(texts, batch_size=32)]
        validate_vectors(vectors, len(texts), self.dimensions)
        return vectors

    def embed_query(self, question: str) -> list[float]:
        vector = list(self.model.query_embed(question))[0].tolist()
        validate_vectors([vector], 1, self.dimensions)
        return vector
