"""CLI: validate, run dev, freeze a selection, then run held-out test."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize, validate_benchmark
from .ingestion import load_corpus
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def read_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(data) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_chunks(pages, cfg):
    if cfg["chunking"] == "fixed":
        return [c for page in pages for c in fixed_size(page, cfg["size"], cfg["overlap"])]
    if cfg["chunking"] == "paragraph":
        return [c for page in pages for c in by_paragraph(page, cfg["size"])]
    raise ValueError("Unknown chunking configuration")


def export_audit(output: Path, pages, chunks_by_strategy: dict, traces: list[dict]) -> None:
    # Deterministic locations are fixed independently of scores.
    sample_pages = sorted(pages, key=lambda p: (p.document_id, p.page))[:10]
    coherence, metadata, grounding = [], [], []
    for strategy, chunks in chunks_by_strategy.items():
        for page in sample_pages:
            anchor = len(page.text) // 2
            covering = [c for c in chunks if c.document_id == page.document_id and c.page == page.page
                        and c.metadata["char_start"] <= anchor < c.metadata["char_end"]]
            if not covering:
                candidates = [c for c in chunks if c.document_id == page.document_id and c.page == page.page]
                covering = [min(candidates, key=lambda c: abs(c.metadata["char_start"] - anchor))]
            for c in covering:
                coherence.append({"strategy": strategy, "document_id": page.document_id, "page": page.page,
                                  "anchor": anchor, "chunk_id": c.chunk_id, "text": c.text,
                                  "source_context": page.text, "label_0_1_2": None, "reason": "", "reviewer": ""})
    for trace in traces:
        if trace["split"] != "test":
            continue
        for hit in trace["hits"]:
            metadata.append({"strategy": trace["strategy"], "question_id": trace["question_id"],
                             "chunk_id": hit["chunk_id"], "metadata": hit["metadata"],
                             "requested_filter": trace["requested_filter"], "applied_filter": trace["applied_filter"],
                             "complete_and_correct": None, "obeys_requested_filter": None, "reason": "", "reviewer": ""})
        grounding.append({"strategy": trace["strategy"], "question_id": trace["question_id"],
                          "question": trace["question"], "gold": trace["gold"], "hits": trace["hits"],
                          "label_0_1_2": None, "reason": "", "reviewer": ""})
    # Templates are separate from the files a reviewer fills, so reruns preserve labels.
    write_jsonl(output / "audit" / "coherence.template.jsonl", coherence)
    if grounding:
        write_jsonl(output / "audit" / "metadata.template.jsonl", metadata)
        write_jsonl(output / "audit" / "grounding.template.jsonl", grounding)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifest.json")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "benchmark/questions.jsonl")
    parser.add_argument("--config", type=Path, default=ROOT / "starter/configs/strategies.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    stage = "validation"
    try:
        for path in (args.manifest, args.benchmark, args.config):
            if not path.is_file():
                raise ValueError(f"Missing input file: {path.name}; follow the repository README.md")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        strategies = config["strategies"]
        if set(strategies) != {"A", "B", "C"}:
            raise ValueError("Expected strategies A/B/C")
        if {k: v for k, v in strategies["B"].items() if k != "use_filter"} != {k: v for k, v in strategies["C"].items() if k != "use_filter"}:
            raise ValueError("B and C must differ only in filtering")
        if strategies["A"]["use_filter"] or strategies["B"]["use_filter"] or not strategies["C"]["use_filter"]:
            raise ValueError("Only C may use filters")
        pages, ingestion_log = load_corpus(args.manifest)
        write_jsonl(args.output / "ingestion_log.jsonl", ingestion_log)
        questions = read_questions(args.benchmark)
        validate_benchmark(questions, pages)
        chunks = {name: build_chunks(pages, cfg) for name, cfg in strategies.items()}
        fingerprint = digest({"pages": [asdict(p) for p in pages], "questions": questions, "config": config})
        validation = {"content_pages": len(pages), "questions": len(questions), "fingerprint": fingerprint,
                      "chunk_counts": {s: len(cs) for s, cs in chunks.items()}}
        write_json(args.output / "validation.json", validation)
        if args.validate_only:
            export_audit(args.output, pages, chunks, [])
            print(json.dumps(validation, indent=2))
            return
        freeze_path = args.output / "selection.json"
        if args.split == "dev" and (args.output / "traces_test.jsonl").exists():
            raise ValueError("Test was already viewed in this experiment. Do not tune on it; document exposure and create a fresh holdout")
        if args.split == "test":
            if not freeze_path.is_file():
                raise ValueError("Run --split dev before test to freeze selection")
            frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
            if frozen["fingerprint"] != fingerprint:
                raise ValueError("Corpus, benchmark or config changed after dev selection")
        from dotenv import load_dotenv
        load_dotenv(ROOT / "starter/.env")
        url = os.getenv("DATABASE_URL")
        if not url:
            raise ValueError("DATABASE_URL missing; copy starter/.env.example to starter/.env")
        stage = "embedding_model"
        started = time.perf_counter()
        embedder = MyEmbedder(config["model"], str(ROOT / ".cache/fastembed"))
        model_signature = digest(embedder.model_files)
        if args.split == "test" and frozen["model_signature"] != model_signature:
            raise ValueError("Local model weights changed after dev")
        stage = "database"
        store = PgVectorStore(url, embedder.dimensions)
        store.create_schema()
        statistics_rows, traces, vector_cache = [], [], {}
        selected_questions = [q for q in questions if q["split"] == args.split]
        # Embed each question once; only its text is passed to the model.
        query_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in selected_questions}
        for strategy, cfg in strategies.items():
            stage = f"ingest_{strategy}"
            chunk_list = chunks[strategy]
            text_key = digest([c.text for c in chunk_list])
            tick = time.perf_counter()
            reused = text_key in vector_cache
            if not reused:
                vector_cache[text_key] = embedder.embed_documents([c.text for c in chunk_list])
            vectors = vector_cache[text_key]
            embedding_seconds = time.perf_counter() - tick
            tick = time.perf_counter()
            store.upsert(strategy, chunk_list, vectors)
            first_count = store.count(strategy)
            # Real second upsert verifies duplicate prevention in the live store.
            store.upsert(strategy, chunk_list, vectors)
            second_count = store.count(strategy)
            if first_count != len(chunk_list) or second_count != first_count:
                raise ValueError(f"Re-ingestion count check failed: {strategy}")
            ingest_seconds = time.perf_counter() - tick
            write_jsonl(args.output / f"chunks_{strategy}.jsonl", [asdict(c) for c in chunk_list])
            stage = f"retrieval_{strategy}"
            tick = time.perf_counter()
            for question in selected_questions:
                filters = question.get("filter", {}) if cfg["use_filter"] else {}
                hits = store.search(strategy, query_vectors[question["id"]], 3, filters)
                trace = evaluate_query(question, hits)
                trace.update(strategy=strategy, applied_filter=filters)
                traces.append(trace)
            lengths = [len(c.text) for c in chunk_list]
            statistics_rows.append({"strategy": strategy, "chunk_count": len(chunk_list),
                                    "characters": sum(lengths), "length_min": min(lengths),
                                    "length_mean": statistics.mean(lengths), "length_max": max(lengths),
                                    "embedding_seconds": embedding_seconds, "embedding_reused": reused,
                                    "upsert_twice_seconds": ingest_seconds, "first_count": first_count,
                                    "reingest_count": second_count,
                                    "query_seconds": time.perf_counter() - tick, "api_cost_usd": 0,
                                    "cost_note": "Local CPU; electricity/hardware not priced"})
        metrics = summarize(traces)
        write_jsonl(args.output / f"traces_{args.split}.jsonl", traces)
        write_json(args.output / f"metrics_{args.split}.json", metrics)
        write_json(args.output / f"resources_{args.split}.json", statistics_rows)
        export_audit(args.output, pages, chunks, traces)
        packages = {}
        for name in ("fastembed", "onnxruntime", "numpy", "psycopg", "pypdf", "python-dotenv"):
            packages[name] = importlib.metadata.version(name)
        run_info = {"status": "completed", "split": args.split, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "python": platform.python_version(), "packages": packages,
                    "all_packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
                    **store.versions(),
                    "model": embedder.model_name, "dimensions": embedder.dimensions,
                    "model_files_sha256": embedder.model_files,
                    "query_method": "FastEmbed.query_embed", "document_method": "FastEmbed.passage_embed",
                    "elapsed_seconds": time.perf_counter() - started, "fingerprint": fingerprint,
                    "config": config, "api_cost_usd": 0}
        write_json(args.output / f"run_{args.split}.json", run_info)
        if args.split == "dev":
            chosen = min(strategies, key=lambda s: (-metrics[f"{s}/dev"]["hit3"],
                                                    -metrics[f"{s}/dev"]["hit1"], len(chunks[s]), s))
            write_json(freeze_path, {"selected_strategy": chosen, "fingerprint": fingerprint,
                                    "model_signature": model_signature, "selection_policy": config["selection_policy"],
                                    "frozen_at_utc": run_info["timestamp_utc"]})
        # CSV is derived only from measured results; pre-run hypotheses live elsewhere.
        all_metrics = []
        for split in ("dev", "test"):
            path = args.output / f"metrics_{split}.json"
            if path.exists():
                all_metrics.extend(json.loads(path.read_text(encoding="utf-8")).values())
        with (args.output / "retrieval_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["strategy", "split", "questions", "hit1_n", "hit1", "hit3_n", "hit3"])
            writer.writeheader()
            writer.writerows(all_metrics)
        print(json.dumps(metrics, indent=2))
    except Exception as exc:
        # Connection/provider exceptions may contain secrets; persist type/stage only.
        write_json(args.output / "last_error.json", {"stage": stage, "error_type": type(exc).__name__,
                                                   "timestamp_utc": datetime.now(timezone.utc).isoformat()})
        detail = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else "Check dependencies, model/network or database. Credentials are not logged."
        print(f"Pipeline stopped at {stage}: {type(exc).__name__}: {detail}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
