"""Aggregate completed reviewer labels; refuse blanks or altered evidence."""
import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from src.run import read_questions, write_json

SPECS = {
    "coherence": (("strategy", "document_id", "page", "anchor", "chunk_id"), "label_0_1_2", (0, 1, 2)),
    "metadata": (("strategy", "question_id", "chunk_id"), "complete_and_correct", (True, False)),
    "grounding": (("strategy", "question_id"), "label_0_1_2", (0, 1, 2)),
}


def validate_record(row: dict, template: dict, name: str, *, allow_blank=False) -> bool:
    """Check immutable evidence even for partially completed audit files."""
    _, label, allowed = SPECS[name]
    mutable = {label, "reason", "reviewer"}
    if name == "metadata":
        mutable.add("obeys_requested_filter")
    if {k: v for k, v in row.items() if k not in mutable} != {k: v for k, v in template.items() if k not in mutable}:
        raise ValueError(f"{name}: source/trace fields changed")
    if not all(isinstance(row.get(k), str) for k in ("reason", "reviewer")):
        raise ValueError(f"{name}: reviewer and reason must be text")
    value = row.get(label)
    if allow_blank and value is None:
        return False
    if type(value) not in {type(x) for x in allowed} or value not in allowed:
        raise ValueError(f"{name}: blank/invalid label")
    if not row["reason"].strip() or not row["reviewer"].strip():
        raise ValueError(f"{name}: record reviewer and reason")
    if name == "metadata" and row["requested_filter"] and type(row.get("obeys_requested_filter")) is not bool:
        raise ValueError("Fill obeys_requested_filter for each filtered question, including baselines A/B")
    return True


def load_review(folder: Path, name: str, keys: tuple, label: str, allowed: tuple) -> list[dict]:
    template = read_questions(folder / f"{name}.template.jsonl")
    reviewed = read_questions(folder / f"{name}.jsonl")
    expected = {tuple(row[k] for k in keys): row for row in template}
    actual = {tuple(row[k] for k in keys): row for row in reviewed}
    if len(actual) != len(reviewed) or actual.keys() != expected.keys():
        raise ValueError(f"{name}: missing/duplicate/unexpected audit records")
    for identity, row in actual.items():
        validate_record(row, expected[identity], name)
    return reviewed


def aggregate(output: Path) -> dict:
    folder = output / "audit"
    coherence, metadata, grounding = [load_review(folder, name, *SPECS[name]) for name in SPECS]
    traces = read_questions(output / "traces_test.jsonl")
    result = {}
    for strategy in ("A", "B", "C"):
        cs = [r for r in coherence if r["strategy"] == strategy]
        ms = [r for r in metadata if r["strategy"] == strategy]
        gs = [r for r in grounding if r["strategy"] == strategy]
        # Compliance is per question against the requested filter, including baselines.
        filter_ids = {r["question_id"] for r in gs if any(
            t["question_id"] == r["question_id"] and t.get("requested_filter")
            for t in traces if t["strategy"] == strategy)}
        compliant = 0
        for qid in filter_ids:
            hits = [r for r in ms if r["question_id"] == qid]
            compliant += bool(hits) and all(r["obeys_requested_filter"] for r in hits)
        result[strategy] = {
            "reviewer_counts": dict(Counter(r["reviewer"] for r in [*cs, *ms, *gs])),
            "coherence_n": len(cs), "coherence_mean_2": statistics.mean(r["label_0_1_2"] for r in cs),
            "metadata_correct_n": sum(r["complete_and_correct"] for r in ms), "metadata_total": len(ms),
            "filter_compliant_n": compliant if filter_ids else None, "filter_questions_n": len(filter_ids),
            "grounding_n": len(gs), "grounding_mean_2": statistics.mean(r["label_0_1_2"] for r in gs),
            "grounding_counts": {str(label): sum(r["label_0_1_2"] == label for r in gs) for label in (0, 1, 2)}}
    return result


def sync_report(result: dict, root: Path = ROOT) -> None:
    """Update only derived audit sections; never change benchmark or traces."""
    import re
    report = root / "report/individual/2A202603696_MaiVanThanh.md"
    text = report.read_text(encoding="utf-8")
    table = ["| Strategy | Coherence /2 (n=10) | Metadata đúng/đủ (n=15) | Filter tuân thủ theo nhãn trên test | Grounding /2 (n=5) |",
             "|---|---|---|---|---|"]
    for s, r in result.items():
        table.append(f"| {s} | {r['coherence_mean_2']:.2f} | {r['metadata_correct_n']}/{r['metadata_total']} | "
                     f"{r['filter_compliant_n']}/{r['filter_questions_n']} câu | {r['grounding_mean_2']:.2f} |")
    start = text.index("| Strategy | Coherence")
    end = text.index("\n\n", start)
    text = text[:start] + "\n".join(table) + text[end:]
    text = re.sub(r"Tổng cộng \*\*30 dòng coherence, 45 dòng metadata, 15 dòng grounding\*\*[^\n]*",
                  "Tổng cộng **30 dòng coherence, 45 dòng metadata, 15 dòng grounding**, đã lưu nhãn/lý do/người chấm trong results/audit/*.jsonl. Bảng trên dùng nhãn đánh giá; kiểm tra filter tự động là phép kiểm tra riêng. Phương pháp và nguồn gốc người chấm được khai báo trong phần này.", text)
    text = text.replace("Chưa kết luận coherence tốt hơn trước khi có nhãn thủ công.", "Đối chiếu thêm điểm đánh giá coherence trong bảng audit.")
    text = text.replace("Nếu làm tiếp: hoàn thiện audit trước,", "Nếu làm tiếp:")
    distribution = "\n\n<!-- audit-distribution -->\nSố câu grounding ở từng mức (0 / 1 / 2): " + "; ".join(
        f"{s}: {r['grounding_counts']['0']} / {r['grounding_counts']['1']} / {r['grounding_counts']['2']}"
        for s, r in result.items()) + ".\n<!-- /audit-distribution -->"
    text = re.sub(r"\n\n<!-- audit-distribution -->[\s\S]*?<!-- /audit-distribution -->", "", text)
    text = text.replace("\n\n## Phân tích và kết luận", distribution + "\n\n## Phân tích và kết luận")
    report.write_text(text, encoding="utf-8")
    summary = root / "results/summary.md"
    value = summary.read_text(encoding="utf-8").replace(
        "Human coherence, metadata correctness and grounding labels are pending.",
        "Audit labels are complete; see audit_metrics.json and reviewer provenance in the individual report.")
    summary.write_text(value, encoding="utf-8")
    log = root / "artifacts/experiment_log.csv"
    if log.exists():
        log.write_text(log.read_text(encoding="utf-8").replace("manual audit pending", "audit labels complete; reviewers recorded; see results/audit_metrics.json"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    parser.add_argument("--sync", action="store_true", help="Sync the individual report for the primary results folder")
    args = parser.parse_args()
    try:
        if args.sync and args.output.resolve() != (ROOT / "results").resolve():
            raise ValueError("--sync is only for the primary results folder")
        result = aggregate(args.output)
        write_json(args.output / "audit_metrics.json", result)
        if args.sync:
            sync_report(result)
        print(json.dumps(result, indent=2))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, f"Audit incomplete: {exc}\n")


if __name__ == "__main__":
    main()
