"""Audit writes and HTTP boundaries, using temporary synthetic labels only."""
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "starter/scripts")]
from server import audit_state, create_server, save_label
from summarize_audit import aggregate, sync_report, validate_record


class AuditWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / "results/audit"
        folder.mkdir(parents=True)
        self.row = {"strategy":"A", "document_id":"fixture", "page":1, "anchor":5, "chunk_id":"fixture-id", "text":"test fixture", "source_context":"test fixture", "label_0_1_2":None, "reason":"", "reviewer":""}
        (folder / "coherence.template.jsonl").write_text(json.dumps(self.row)+"\n", encoding="utf-8")

    def payload(self, revision="new"):
        return {"kind":"coherence", "index":0, "revision":revision, "labels":{"label_0_1_2":1, "reason":"Synthetic test only", "reviewer":"unit fixture"}}

    def test_save_preserves_source_and_rejects_stale_edit(self):
        state = save_label(self.root, self.payload())
        self.assertEqual(state["completed"], 1)
        self.assertEqual(state["rows"][0]["text"], "test fixture")
        with self.assertRaises(RuntimeError):
            save_label(self.root, self.payload())
        self.assertIsNone(json.loads((self.root / "results/audit/coherence.template.jsonl").read_text())["label_0_1_2"])

    def test_rejects_invalid_label_or_evidence_edit_before_writing(self):
        for labels in ({"label_0_1_2":True}, {"text":"changed"}, {"reason":""}):
            payload = self.payload()
            payload["labels"].update(labels)
            with self.assertRaises(ValueError):
                save_label(self.root, payload)
        self.assertFalse((self.root / "results/audit/coherence.jsonl").exists())

    def test_source_tampering_detected_in_partial_audit(self):
        changed = {**self.row, "text":"altered"}
        (self.root / "results/audit/coherence.jsonl").write_text(json.dumps(changed)+"\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            audit_state(self.root, "coherence")

    def test_metadata_requires_filter_decision(self):
        template = {"strategy":"A", "question_id":"fixture", "chunk_id":"x", "requested_filter":{"category":"a"}, "complete_and_correct":None, "obeys_requested_filter":None, "reason":"", "reviewer":""}
        row = {**template,"complete_and_correct":True,"reason":"fixture","reviewer":"fixture"}
        with self.assertRaises(ValueError):
            validate_record(row, template, "metadata")
        row["obeys_requested_filter"] = False
        self.assertTrue(validate_record(row, template, "metadata"))

    def test_complete_audit_syncs_only_temporary_report(self):
        for rel in ("README.md", "results/summary.md", "report/individual/2A202603696_MaiVanThanh.md", "results/traces_test.jsonl"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, target)
        for kind in ("coherence", "metadata", "grounding"):
            source = ROOT / f"results/audit/{kind}.template.jsonl"
            shutil.copyfile(source, self.root / f"results/audit/{kind}.template.jsonl")
            rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                row.update(reason="Synthetic test fixture, not a human lab label",reviewer="unit test")
                row["complete_and_correct" if kind=="metadata" else "label_0_1_2"] = True if kind=="metadata" else 1
                if kind=="metadata": row["obeys_requested_filter"]=False if row["requested_filter"] else None
            (self.root / f"results/audit/{kind}.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
        result = aggregate(self.root / "results")
        self.assertEqual(result["A"]["coherence_mean_2"],1)
        self.assertEqual(result["C"]["metadata_correct_n"],15)
        sync_report(result,self.root)
        report = (self.root / "report/individual/2A202603696_MaiVanThanh.md").read_text(encoding="utf-8")
        self.assertIn("| C | 1.00 | 15/15 | 0/2",report)
        self.assertEqual((self.root / "results/traces_test.jsonl").read_bytes(),(ROOT / "results/traces_test.jsonl").read_bytes())
        self.assertEqual((self.root / "README.md").read_bytes(),(ROOT / "README.md").read_bytes())


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=create_server(port=0)
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_data_and_static_are_available_but_private_files_are_not(self):
        with urlopen(self.url+"/api/data") as response:
            data=json.load(response)
        self.assertEqual(data["validation"]["content_pages"],32)
        for path in ("/data/private/bao_cao.pdf","/../STUDENT.md","/.git/config"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url+path)
            self.assertEqual(error.exception.code,404)
        with urlopen(self.url) as response:
            self.assertEqual(response.status,200)

    def test_cross_origin_write_and_wrong_host_rejected(self):
        request=Request(self.url+"/api/audit",data=b"{}",headers={"Origin":"http://example.test","Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as error: urlopen(request)
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error: urlopen(Request(self.url,headers={"Host":"example.test"}))
        self.assertEqual(error.exception.code,403)


if __name__ == "__main__":
    unittest.main()
