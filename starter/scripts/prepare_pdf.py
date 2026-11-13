"""Inspect a PDF, then prepare a manifest from explicitly reviewed page ranges."""
import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from src.ingestion import load_pdf, normalize_text
from src.run import write_json, write_jsonl


def page_numbers(spec: str) -> set[int]:
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if not re.fullmatch(r"[1-9]\d*(?:-[1-9]\d*)?", part):
            raise ValueError("Use physical page ranges such as 5-20,23,25-40")
        start, _, end = part.partition("-")
        low, high = int(start), int(end or start)
        if high < low:
            raise ValueError("Page range end precedes start")
        result.update(range(low, high + 1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true", help="Export page inventory/text without declaring any page eligible")
    parser.add_argument("--source-id", default="do-an-ca-nhan")
    parser.add_argument("--title")
    parser.add_argument("--permission", help="Actual ownership/permission and permitted sharing scope")
    parser.add_argument("--pages", help="Reviewed physical PDF pages; omit covers, TOC, blank pages, reference-only pages")
    parser.add_argument("--sections", type=Path, help="CSV: start_page,end_page,category,section")
    parser.add_argument("--language", default="vi")
    parser.add_argument("--version", default=None, help="Use a version from the document, not an inferred year")
    parser.add_argument("--header-pattern", help="Regex for verified repeated header lines to remove")
    parser.add_argument("--footer-pattern", help="Regex for verified repeated footer lines to remove")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.source_id):
        parser.error("source-id permits ASCII letters, numbers, underscore and hyphen")
    pdf = args.pdf.resolve()
    pages = load_pdf(pdf, args.source_id, pdf.name)
    for page in pages:
        lines = page.text.splitlines()
        page.text = normalize_text("\n".join(line for line in lines if not any(
            pattern and re.fullmatch(pattern, line) for pattern in (args.header_pattern, args.footer_pattern))))
    preview = ROOT / "results" / ("pdf_inspection_" + args.source_id)
    preview.mkdir(parents=True, exist_ok=True)
    write_jsonl(preview / "pages.jsonl", [{"page": p.page, "text": p.text, "status": p.metadata["read_status"]} for p in pages])
    with (preview / "inventory.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["page", "characters", "status", "preview"])
        writer.writeheader()
        writer.writerows({"page": p.page, "characters": len(p.text), "status": p.metadata["read_status"],
                          "preview": p.text[:160].replace("\n", " ")} for p in pages)
    print(f"Inspected {len(pages)} physical pages. Review text/counting in {preview.relative_to(ROOT)}")
    if args.inspect:
        return
    if not all((args.title, args.permission, args.pages, args.sections)):
        parser.error("Preparation needs --title, --permission, --pages and --sections after reviewing inspection")
    selected = page_numbers(args.pages)
    if len(selected) < 30:
        parser.error("Select >=30 actual content pages")
    page_map = {p.page: p for p in pages}
    if selected - set(page_map):
        parser.error("Selected page numbers exceed the PDF")
    mapping = {}
    with args.sections.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if not row.get("category") or not row.get("section"):
                parser.error("Each section row needs verified category/section values")
            for page in range(int(row["start_page"]), int(row["end_page"]) + 1):
                if page in mapping:
                    parser.error("Section ranges overlap")
                mapping[page] = {"category": row["category"], "section": row["section"]}
    if selected - set(mapping):
        parser.error("Every selected page needs a section/category mapping")
    if len({mapping[n]["category"] for n in selected}) < 2:
        parser.error("Need >=2 real category values for filter experiments")
    for number in selected:
        if not page_map[number].text or page_map[number].metadata["read_status"] != "ok":
            parser.error(f"Selected page {number} is empty/unreadable; OCR or choose other valid content")
    target = ROOT / "data/processed" / (args.source_id + ".jsonl")
    rows = [{"page": n, "text": page_map[n].text,
             "metadata": {**mapping[n], "language": args.language,
                          **({"version": args.version} if args.version else {})}} for n in sorted(selected)]
    write_jsonl(target, rows)
    entry = {"source_id": args.source_id, "title": args.title,
             "path": target.relative_to(ROOT / "data").as_posix(), "format": "jsonl", "unit_type": "pdf_page",
             "source_url": pdf.name, "original_pdf_name": pdf.name,
             "original_pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
             "license_or_permission": args.permission, "accessed_at": datetime.now(timezone.utc).isoformat(),
             "physical_pages": len(pages), "page_ids": sorted(selected),
             "counting_rule": "Physical PDF pages manually selected after excluding cover, TOC, blank and reference-only pages",
             "page_characters": {str(n): len(page_map[n].text) for n in sorted(selected)},
             "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
             "transformation": "pypdf layout extraction, Unicode NFC, normalized whitespace; no OCR",
             "removed_running_text_patterns": {"header": args.header_pattern, "footer": args.footer_pattern}}
    manifest_path = ROOT / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"schema_version": 1, "sources": []}
    manifest["sources"] = [e for e in manifest["sources"] if e["source_id"] != args.source_id] + [entry]
    write_json(manifest_path, manifest)
    print(f"Prepared {len(selected)} reviewed PDF pages; manifest written. Verify evidence before benchmarking.")


if __name__ == "__main__":
    main()
