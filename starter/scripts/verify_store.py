"""Verify live store behavior using real vectors already ingested by the lab."""
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from dotenv import load_dotenv
import psycopg
from src.models import Chunk
from src.run import write_json
from src.store import PgVectorStore


def main() -> None:
    load_dotenv(ROOT / "starter/.env")
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (metadata->>'category')
            chunk_id,document_id,source,page,text,metadata,embedding::text
            FROM lab6_chunks WHERE strategy='B'
            ORDER BY metadata->>'category',chunk_id""")
        rows = cur.fetchall()
    if len(rows) < 2:
        raise ValueError("Run the real pipeline first; need two source categories")
    chunks = [Chunk(*row[:6]) for row in rows[:2]]
    vectors = [json.loads(row[6]) for row in rows[:2]]
    store = PgVectorStore(url, len(vectors[0]))
    strategy = "verification_" + uuid.uuid4().hex
    results = {"vector_source": "existing strategy B embeddings; no mock vectors", "checks": {}}
    try:
        store.upsert(strategy, chunks, vectors)
        results["checks"]["initial_count"] = store.count(strategy) == 2
        store.upsert(strategy, chunks, vectors)
        results["checks"]["reingest_no_duplicates"] = store.count(strategy) == 2
        category = chunks[1].metadata["category"]
        hits = store.search(strategy, vectors[0], filters={"category": category})
        results["checks"]["metadata_filter"] = len(hits) == 1 and hits[0]["metadata"]["category"] == category
        hostile = "' OR TRUE; DROP TABLE lab6_chunks; --"
        results["checks"]["filter_value_parameterized"] = store.search(strategy, vectors[0], filters={"category": hostile}) == []
        store.upsert(strategy, chunks[:1], vectors[:1])
        remaining = store.search(strategy, vectors[0])
        results["checks"]["obsolete_chunks_removed"] = store.count(strategy) == 1 and remaining[0]["chunk_id"] == chunks[0].chunk_id
        results["checks"]["cosine_self_match"] = abs(remaining[0]["score"] - 1) < 1e-5
        results["passed"] = all(results["checks"].values())
        write_json(ROOT / "results/store_verification.json", results)
        print(json.dumps(results, indent=2))
        if not results["passed"]:
            raise SystemExit(1)
    finally:
        # Only temporary records created under this unique strategy are removed.
        with store.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM lab6_chunks WHERE strategy=%s", (strategy,))


if __name__ == "__main__":
    main()
