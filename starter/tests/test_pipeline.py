"""Core correctness tests use synthetic fixtures, never reported as lab results."""
import json
import hashlib
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from src.chunking import by_paragraph, fixed_size
from src.embeddings import validate_vectors
from src.evaluation import evaluate_query, summarize, validate_benchmark
from src.ingestion import load_corpus, normalize_text
from src.models import DocumentPage
from src.run import digest
from src.store import validate_filters
from scripts.prepare_pdf import page_numbers
from scripts.summarize_audit import load_review


class ChunkTests(unittest.TestCase):
    def setUp(self):
        self.page = DocumentPage("test-only", "test fixture", 7,
                                 "First paragraph. " * 30 + "\n\n" + "Second paragraph. " * 30,
                                 {"category": "test", "section": "unit"})

    def check_chunks(self, chunks, maximum):
        self.assertTrue(chunks)
        covered = set()
        for chunk in chunks:
            start, end = chunk.metadata["char_start"], chunk.metadata["char_end"]
            self.assertEqual(chunk.text, self.page.text[start:end])
            self.assertLessEqual(len(chunk.text), maximum)
            self.assertEqual(chunk.metadata["category"], "test")
            self.assertEqual(chunk.page, 7)
            covered.update(range(start, end))
        self.assertTrue(all(i in covered for i, char in enumerate(self.page.text) if not char.isspace()))
        self.assertEqual(len(chunks), len({c.chunk_id for c in chunks}))

    def test_fixed_coverage_offsets_and_stability(self):
        chunks = fixed_size(self.page, 100, 20)
        self.check_chunks(chunks, 100)
        self.assertEqual([asdict(c) for c in chunks], [asdict(c) for c in fixed_size(self.page, 100, 20)])
        self.page.text += "changed"
        self.assertNotEqual(chunks[-1].chunk_id, fixed_size(self.page, 100, 20)[-1].chunk_id)

    def test_paragraph_coverage_and_hard_limit(self):
        self.check_chunks(by_paragraph(self.page, 100), 100)

    def test_long_word_and_empty_document(self):
        self.page.text = "x" * 301
        self.check_chunks(by_paragraph(self.page, 100), 100)
        self.assertEqual(by_paragraph(DocumentPage("x", "x", 1, ""), 100), [])

    def test_invalid_settings(self):
        for size, overlap in ((0, 0), (5, 5), (5, -1)):
            with self.assertRaises(ValueError):
                fixed_size(self.page, size, overlap)

    def test_normalization_keeps_paragraphs(self):
        self.assertEqual(normalize_text("  Cafe\u0301\r\n\r\n  A\t B\x00  "), "Caf\u00e9\n\nA B")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.q = {"id": "test-only", "split": "test", "question": "Question", "expected_answer": "Answer",
                  "gold_source_id": "doc", "gold_page": 2, "evidence_quote": "full evidence with condition"}
        self.hit = {"chunk_id": "fixture", "text": "The full evidence with condition.", "score": 0.8,
                    "metadata": {"document_id": "doc", "source": "fixture", "page": 2}}

    def test_wrong_page_and_partial_evidence_are_not_hits(self):
        wrong = {**self.hit, "metadata": {**self.hit["metadata"], "page": 3}}
        partial = {**self.hit, "text": "full evidence"}
        trace = evaluate_query(self.q, [wrong, partial, self.hit])
        self.assertFalse(trace["hit1"])
        self.assertTrue(trace["hit3"])
        self.assertEqual([h["evidence_hit"] for h in trace["hits"]], [False, False, True])

    def test_alternative_gold_and_whitespace(self):
        q = {**self.q, "alternative_gold": [{"source_id": "alt", "page": 8, "evidence_quote": "equivalent evidence"}]}
        hit = {**self.hit, "text": "equivalent\n evidence", "metadata": {"document_id": "alt", "page": 8}}
        self.assertTrue(evaluate_query(q, [hit])["hit1"])
        self.assertFalse(evaluate_query(q, [])["hit3"])

    def test_aggregate_split_counts(self):
        a = {**evaluate_query(self.q, [self.hit]), "strategy": "A"}
        b = {**evaluate_query(self.q, []), "strategy": "A", "split": "dev"}
        summary = summarize([a, b])
        self.assertEqual(summary["A/test"]["hit3_n"], 1)
        self.assertEqual(summary["A/dev"]["hit3_n"], 0)

    def test_filters_refuse_gold_leaks_and_bad_types(self):
        self.assertEqual(validate_filters({"category": "design", "year": 2025}), {"category": "design", "year": 2025})
        for filters in ({"document_id": "gold"}, {"category": ["x"]}, {"x; DROP TABLE": "x"}):
            with self.assertRaises(ValueError):
                validate_filters(filters)

    def test_benchmark_validates_evidence_and_filter(self):
        pages = [DocumentPage("doc", "fixture", 2, "The full evidence with condition.", {"category": "design"})]
        qs = [{**self.q, "id": f"q{i}", "split": "dev" if i < 15 else "test",
               "filter": {"category": "design"} if i in (0, 1, 15) else {}} for i in range(20)]
        validate_benchmark(qs, pages)
        qs[0]["evidence_quote"] = "fabricated"
        with self.assertRaises(ValueError):
            validate_benchmark(qs, pages)

    def test_vectors_reject_mismatch_nan_and_zero(self):
        for vectors, count, dim in (([[1]], 2, 1), ([[1]], 1, 2), ([[float("nan")]], 1, 1), ([[0, 0]], 1, 2)):
            with self.assertRaises(ValueError):
                validate_vectors(vectors, count, dim)


class GuardTests(unittest.TestCase):
    def test_pdf_snapshot_counts_short_physical_pages_and_checks_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = [{"page": i, "text": f"Physical PDF content {i}", "metadata": {"category": "one" if i < 16 else "two"}} for i in range(1, 31)]
            snapshot = root / "snapshot.jsonl"
            snapshot.write_text("".join(json.dumps(row) + "\n" for row in data), encoding="utf-8")
            entry = {"source_id": "fixture", "title": "Synthetic unit test only", "path": "snapshot.jsonl",
                     "source_url": "fixture.pdf", "license_or_permission": "test fixture",
                     "accessed_at": "test", "page_ids": list(range(1, 31)), "format": "jsonl", "unit_type": "pdf_page",
                     "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()}
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sources": [entry]}), encoding="utf-8")
            self.assertEqual(len(load_corpus(manifest)[0]), 30)
            snapshot.write_text(snapshot.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_corpus(manifest)

    def test_blank_evidence_cannot_score_a_hit(self):
        q = {"id": "fixture", "split": "dev", "question": "fixture", "expected_answer": "fixture",
             "gold_source_id": "doc", "gold_page": 1, "evidence_quote": ""}
        hit = {"text": "anything", "metadata": {"document_id": "doc", "page": 1}}
        self.assertFalse(evaluate_query(q, [hit])["hit3"])

    def test_hash_changes_when_holdout_or_config_changes(self):
        self.assertNotEqual(digest({"questions": ["a"]}), digest({"questions": ["b"]}))
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))

    def test_page_ranges_and_invalid_input(self):
        self.assertEqual(page_numbers("3-5,7"), {3, 4, 5, 7})
        for spec in ("0", "5-3", "1,,2", "abc"):
            with self.assertRaises(ValueError):
                page_numbers(spec)

    def test_manual_audit_requires_real_labels_and_unchanged_source(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            template = {"strategy": "A", "id": "x", "text": "original", "label_0_1_2": None, "reason": "", "reviewer": ""}
            (p / "coherence.template.jsonl").write_text(json.dumps(template) + "\n", encoding="utf-8")
            (p / "coherence.jsonl").write_text(json.dumps(template) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_review(p, "coherence", ("strategy", "id"), "label_0_1_2", (0, 1, 2))
            filled = {**template, "label_0_1_2": 1, "reason": "Missing context", "reviewer": "test fixture"}
            (p / "coherence.jsonl").write_text(json.dumps(filled) + "\n", encoding="utf-8")
            self.assertEqual(len(load_review(p, "coherence", ("strategy", "id"), "label_0_1_2", (0, 1, 2))), 1)
            filled["text"] = "changed"
            (p / "coherence.jsonl").write_text(json.dumps(filled) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_review(p, "coherence", ("strategy", "id"), "label_0_1_2", (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
