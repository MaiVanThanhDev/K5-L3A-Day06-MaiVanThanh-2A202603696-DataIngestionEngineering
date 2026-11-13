"""Evidence retrieval scoring; never infer human audit labels from matches."""
import re
from collections import Counter
from typing import Any
from .store import validate_filters


def comparable(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def golds(question: dict) -> list[dict]:
    return [{"source_id": question["gold_source_id"], "page": question["gold_page"],
             "evidence_quote": question["evidence_quote"]}, *question.get("alternative_gold", [])]


def validate_benchmark(questions: list[dict], pages: list) -> None:
    counts = Counter(q.get("split") for q in questions)
    if counts["dev"] < 15 or counts["test"] < 5 or set(counts) - {"dev", "test"}:
        raise ValueError("Need >=15 dev and >=5 test; allowed splits: dev/test")
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Question IDs must be unique")
    page_map = {(p.document_id, p.page): p for p in pages}
    for q in questions:
        for field in ("id", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote"):
            if not q.get(field):
                raise ValueError(f"Question missing {field}")
        filters = validate_filters(q.get("filter"))
        for gold in golds(q):
            page = page_map.get((gold["source_id"], gold["page"]))
            if not page or not comparable(gold["evidence_quote"]) or comparable(gold["evidence_quote"]) not in comparable(page.text):
                raise ValueError(f"Gold evidence not found in normalized source: {q['id']}")
            if any(page.metadata.get(k) != v for k, v in filters.items()):
                raise ValueError(f"Filter contradicts gold: {q['id']}")
    if sum(bool(q.get("filter")) for q in questions) < 3 or not any(q.get("filter") and q["split"] == "test" for q in questions):
        raise ValueError("Need >=3 filter questions including >=1 test")


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = []
    for rank, hit in enumerate(hits[:3], 1):
        metadata = hit["metadata"]
        match = any(bool(comparable(g["evidence_quote"]))
                    and metadata.get("document_id") == g["source_id"]
                    and metadata.get("page") == g["page"]
                    and comparable(g["evidence_quote"]) in comparable(hit["text"])
                    for g in golds(question))
        evaluated.append({**hit, "rank": rank, "evidence_hit": match})
    return {"question_id": question["id"], "split": question["split"],
            "question": question["question"], "expected_answer": question["expected_answer"],
            "gold": golds(question), "requested_filter": question.get("filter", {}),
            "hits": evaluated, "hit1": bool(evaluated and evaluated[0]["evidence_hit"]),
            "hit3": any(h["evidence_hit"] for h in evaluated)}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for strategy, split in sorted({(t["strategy"], t["split"]) for t in traces}):
        rows = [t for t in traces if t["strategy"] == strategy and t["split"] == split]
        n = len(rows)
        hit1, hit3 = sum(t["hit1"] for t in rows), sum(t["hit3"] for t in rows)
        result[f"{strategy}/{split}"] = {"strategy": strategy, "split": split, "questions": n,
                                          "hit1_n": hit1, "hit1": hit1 / n,
                                          "hit3_n": hit3, "hit3": hit3 / n}
    return result
