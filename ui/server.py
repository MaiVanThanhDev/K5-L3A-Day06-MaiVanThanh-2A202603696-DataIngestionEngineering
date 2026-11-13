"""Local results dashboard. Standard library only; no model/database required."""
import argparse
import hashlib
import json
import mimetypes
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "starter"), str(ROOT / "starter/scripts")]
from summarize_audit import SPECS, aggregate, sync_report, validate_record

LOCK = threading.Lock()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def audit_state(root, kind):
    if kind not in SPECS:
        raise ValueError("Loại đánh giá không hợp lệ.")
    folder = root / "results/audit"
    templates = read_rows(folder / f"{kind}.template.jsonl")
    path = folder / f"{kind}.jsonl"
    rows = read_rows(path) if path.exists() else templates
    keys = SPECS[kind][0]
    identity = lambda r: tuple(r[k] for k in keys)
    actual = {identity(r): r for r in rows}
    if len(actual) != len(rows) or set(actual) != {identity(r) for r in templates}:
        raise ValueError("Tệp nhãn bị thiếu/trùng bản ghi. Kiểm tra trước khi lưu.")
    rows = [actual[identity(t)] for t in templates]
    complete = [validate_record(r, t, kind, allow_blank=True) for r, t in zip(rows, templates)]
    revision = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "new"
    return {"rows": rows, "completed": sum(complete), "total": len(rows), "revision": revision}


def save_label(root, payload):
    kind = payload["kind"]
    state = audit_state(root, kind)
    if payload.get("revision") != state["revision"]:
        raise RuntimeError("Nhãn đã thay đổi ở cửa sổ khác. Tải lại trang trước khi lưu.")
    index = payload["index"]
    if type(index) is not int or not 0 <= index < state["total"]:
        raise ValueError("Bản ghi không hợp lệ.")
    fields = {SPECS[kind][1], "reason", "reviewer"}
    if kind == "metadata":
        fields.add("obeys_requested_filter")
    labels = payload["labels"]
    if set(labels) - fields:
        raise ValueError("Chỉ được chỉnh nhãn, lý do và người chấm.")
    row = {**state["rows"][index], **labels}
    template = read_rows(root / f"results/audit/{kind}.template.jsonl")[index]
    validate_record(row, template, kind)
    state["rows"][index] = row
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in state["rows"])
    atomic_write(root / f"results/audit/{kind}.jsonl", text)
    # Any previous aggregation is stale after editing a label.
    metrics = root / "results/audit_metrics.json"
    if metrics.exists():
        result = aggregate(root / "results")
        sync_report(result, root)
        atomic_write(metrics, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return audit_state(root, kind)


def dashboard(root):
    results = root / "results"
    data = {"validation": read_json(results / "validation.json"),
            "selection": read_json(results / "selection.json"),
            "metrics": {**read_json(results / "metrics_dev.json"), **read_json(results / "metrics_test.json")},
            "resources": read_json(results / "resources_test.json"),
            "traces": read_rows(results / "traces_dev.jsonl") + read_rows(results / "traces_test.jsonl"),
            "chunks": {s: read_rows(results / f"chunks_{s}.jsonl") for s in "ABC"},
            "pages": read_rows(root / "data/processed/do-an-ca-nhan.jsonl"),
            "audits": {name: audit_state(root, name) for name in SPECS},
            "audit_metrics": read_json(results / "audit_metrics.json") if (results / "audit_metrics.json").exists() else None}
    return data


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data, mime="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if mime.startswith("application/json") else data
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, mutation=False):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        return not mutation or (origin in {"http://" + h for h in hosts} and self.headers.get("Content-Type", "").split(";")[0] == "application/json")

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {"error": "Chỉ truy cập trên localhost."})
        try:
            if self.path == "/api/data":
                with LOCK:
                    return self.reply(200, dashboard(self.server.root))
            files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if self.path not in files:
                return self.reply(404, {"error": "Không tìm thấy."})
            path = ROOT / "ui/dist" / files[self.path]
            return self.reply(200, path.read_bytes(), (mimetypes.guess_type(path)[0] or "text/plain") + "; charset=utf-8")
        except (ValueError, KeyError, OSError) as exc:
            return self.reply(422, {"error": str(exc)})

    def do_POST(self):
        if not self.allowed(mutation=True):
            return self.reply(403, {"error": "Yêu cầu lưu phải xuất phát từ giao diện local."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32768:
                raise ValueError("Dữ liệu lưu không hợp lệ hoặc quá lớn.")
            payload = json.loads(self.rfile.read(size))
            with LOCK:
                if self.path == "/api/audit":
                    return self.reply(200, save_label(self.server.root, payload))
                if self.path == "/api/sync":
                    result = aggregate(self.server.root / "results")
                    sync_report(result, self.server.root)
                    atomic_write(self.server.root / "results/audit_metrics.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                    return self.reply(200, {"metrics": result})
                return self.reply(404, {"error": "Không tìm thấy."})
        except RuntimeError as exc:
            return self.reply(409, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, OSError) as exc:
            return self.reply(422, {"error": str(exc)})


def create_server(root=ROOT, port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.root = root
    server.daemon_threads = True
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(port=args.port)
    print(f"LAB6 UI: http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
