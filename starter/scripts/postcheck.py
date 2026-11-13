"""Recompute saved results and verify frozen inputs without rerunning the test."""
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "starter"), str(ROOT / "ui")]
from src.evaluation import evaluate_query, summarize, validate_benchmark
from src.ingestion import load_corpus
from src.run import build_chunks, digest, read_questions, write_json
from server import audit_state


def check(root=ROOT):
    results = root / "results"
    load = lambda name: json.loads((results / name).read_text(encoding="utf-8"))
    pages, _ = load_corpus(root / "data/manifest.json")
    questions = read_questions(root / "benchmark/questions.jsonl")
    config = json.loads((root / "starter/configs/strategies.json").read_text(encoding="utf-8"))
    validate_benchmark(questions, pages)
    fingerprint = digest({"pages": [asdict(p) for p in pages], "questions": questions, "config": config})
    selection = load("selection.json")
    checks = {"frozen_inputs_unchanged": fingerprint == selection["fingerprint"] == load("validation.json")["fingerprint"]}
    chunks = {}
    for s in "ABC":
        chunks[s] = read_questions(results / f"chunks_{s}.jsonl")
        checks[f"chunks_{s}_reproduced"] = chunks[s] == [asdict(c) for c in build_chunks(pages, config["strategies"][s])]
    question_map = {q["id"]: q for q in questions}
    traces = []
    for split in ("dev", "test"):
        saved = read_questions(results / f"traces_{split}.jsonl")
        expected_ids = {(s, q["id"]) for s in "ABC" for q in questions if q["split"] == split}
        checks[f"{split}_trace_coverage"] = len(saved) == len(expected_ids) and {(t["strategy"], t["question_id"]) for t in saved} == expected_ids
        checks[f"{split}_metrics_recomputed"] = summarize(saved) == load(f"metrics_{split}.json")
        trace_ok = True
        for t in saved:
            recomputed = evaluate_query(question_map[t["question_id"]], t["hits"])
            trace_ok &= all(t[k] == v for k, v in recomputed.items())
            strategy = config["strategies"][t["strategy"]]
            trace_ok &= t["applied_filter"] == (t["requested_filter"] if strategy["use_filter"] else {})
            chunk_map = {c["chunk_id"]: c for c in chunks[t["strategy"]]}
            for hit in t["hits"]:
                c = chunk_map[hit["chunk_id"]]
                trace_ok &= hit["text"] == c["text"]
                trace_ok &= all(hit["metadata"].get(k) == v for k, v in {**c["metadata"], "document_id": c["document_id"], "source": c["source"], "page": c["page"]}.items())
        checks[f"{split}_evidence_and_provenance"] = trace_ok
        checks[f"{split}_frozen_run"] = load(f"run_{split}.json")["fingerprint"] == fingerprint
        traces.extend(saved)
    index = {(t["strategy"], t["question_id"]): t for t in traces}
    checks["unfiltered_B_C_identical"] = all(index["B", q["id"]]["hits"] == index["C", q["id"]]["hits"] for q in questions if not q.get("filter"))
    checks["same_model_files"] = load("run_dev.json")["model_files_sha256"] == load("run_test.json")["model_files_sha256"]
    checks["selection_precedes_test"] = selection["frozen_at_utc"] <= load("run_test.json")["timestamp_utc"]
    metrics = load("metrics_dev.json")
    expected_strategy = min("ABC", key=lambda s: (-metrics[f"{s}/dev"]["hit3"], -metrics[f"{s}/dev"]["hit1"], len(chunks[s]), s))
    checks["selection_matches_dev_policy"] = selection["selected_strategy"] == expected_strategy
    audits = {name: {k: state[k] for k in ("completed", "total")} for name in ("coherence", "metadata", "grounding") if (state := audit_state(root, name))}
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "method": "Read-only recomputation of saved inputs/chunks/traces; no test rerun or gold edits", "fingerprint": fingerprint, "checks": checks, "passed": all(checks.values()), "audit_labels": audits}


if __name__ == "__main__":
    result = check()
    prior = ROOT / "artifacts/postcheck.json"
    if prior.exists():
        previous = json.loads(prior.read_text(encoding="utf-8"))
        for key in ("cleanup", "ui_verification", "audit_verification", "reviewer_attribution",
                    "author_confirmation_record", "sharing_permission_confirmation", "full_verification"):
            if key in previous:
                result[key] = previous[key]
    write_json(ROOT / "artifacts/postcheck.json", result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
