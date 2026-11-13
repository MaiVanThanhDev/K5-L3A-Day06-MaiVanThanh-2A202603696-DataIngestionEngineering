"""Persistent PostgreSQL/pgvector store, parameterized filters, exact cosine search."""
import json
from typing import Any
from .embeddings import validate_vectors
from .models import Chunk

FILTER_FIELDS = {"category", "language", "version", "section", "year"}


def validate_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValueError("filter must be an object")
    for key, value in filters.items():
        if key not in FILTER_FIELDS or type(value) not in (str, int, bool):
            raise ValueError(f"Unsupported filter field/type: {key}")
    return filters


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if type(dimensions) is not int or dimensions < 1:
            raise ValueError("dimensions must be a positive integer")
        self.database_url, self.dimensions = database_url, dimensions

    def connect(self):
        import psycopg
        return psycopg.connect(self.database_url, connect_timeout=5)

    def create_schema(self) -> None:
        from psycopg import sql
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS lab6_chunks (
                    strategy text NOT NULL,
                    chunk_id text NOT NULL,
                    document_id text NOT NULL,
                    source text NOT NULL,
                    page integer NOT NULL,
                    text text NOT NULL,
                    metadata jsonb NOT NULL,
                    embedding vector({}),
                    PRIMARY KEY (strategy, chunk_id)
                )
            """).format(sql.Literal(self.dimensions)))
            cur.execute("""SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a JOIN pg_class c ON a.attrelid=c.oid
                JOIN pg_namespace n ON c.relnamespace=n.oid
                WHERE n.nspname=current_schema() AND c.relname='lab6_chunks'
                AND a.attname='embedding'""")
            if cur.fetchone()[0] != f"vector({self.dimensions})":
                raise ValueError("Existing database has different embedding dimensions; use a separate database")
            cur.execute("CREATE INDEX IF NOT EXISTS lab6_strategy_idx ON lab6_chunks(strategy)")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        from psycopg.types.json import Jsonb
        validate_vectors(vectors, len(chunks), self.dimensions)
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate chunk IDs in input")
        if not chunks:
            raise ValueError("Refusing to replace an index with empty input")
        rows = [(strategy, c.chunk_id, c.document_id, c.source, c.page, c.text,
                 Jsonb(c.metadata), vector_literal(v)) for c, v in zip(chunks, vectors)]
        # The input is the complete new strategy snapshot. One transaction updates
        # current chunks and removes obsolete chunks, including changed sources.
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("lab6:" + strategy,))
            cur.executemany("""
                INSERT INTO lab6_chunks VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)
                ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                document_id=EXCLUDED.document_id, source=EXCLUDED.source,
                page=EXCLUDED.page, text=EXCLUDED.text, metadata=EXCLUDED.metadata,
                embedding=EXCLUDED.embedding
            """, rows)
            cur.execute("DELETE FROM lab6_chunks WHERE strategy=%s AND NOT (chunk_id = ANY(%s))", (strategy, ids))

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from psycopg.types.json import Jsonb
        validate_vectors([query_vector], 1, self.dimensions)
        filters = validate_filters(filters)
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be in 1..100")
        vector = vector_literal(query_vector)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT chunk_id,text,document_id,source,page,metadata,
                       1-(embedding <=> %s::vector) AS score
                FROM lab6_chunks
                WHERE strategy=%s AND metadata @> %s::jsonb
                ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s
            """, (vector, strategy, Jsonb(filters), vector, top_k))
            return [{"chunk_id": row[0], "text": row[1], "score": float(row[6]),
                     "metadata": {**row[5], "document_id": row[2], "source": row[3], "page": row[4]}}
                    for row in cur.fetchall()]

    def count(self, strategy: str) -> int:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM lab6_chunks WHERE strategy=%s", (strategy,))
            return cur.fetchone()[0]

    def versions(self) -> dict:
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_setting('server_version'), extversion FROM pg_extension WHERE extname='vector'")
            row = cur.fetchone()
            return {"postgresql": row[0], "pgvector": row[1], "metric": "cosine", "search": "exact"}
