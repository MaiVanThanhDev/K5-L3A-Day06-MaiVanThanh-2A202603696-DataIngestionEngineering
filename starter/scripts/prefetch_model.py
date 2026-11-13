"""Optional stdlib/curl prefetch into FastEmbed's Hugging Face snapshot cache."""
import hashlib
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REPO = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
FILES = {"config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "model_optimized.onnx"}


def request(url):
    return urlopen(Request(url, headers={"User-Agent": "LAB6-local-model-prefetch"}), timeout=60)


def download_ranges(url, target, size, block_size=4 * 1024 * 1024, workers=12):
    """Use bounded HTTP ranges on slow links; verify the full upstream hash later."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required for optional parallel prefetch")
    part_dir = ROOT / ".cache/model_parts" / target.parent.name[:12]
    if target.name != "model_optimized.onnx":
        part_dir = part_dir / hashlib.sha256(target.name.encode()).hexdigest()[:12]
    part_dir.mkdir(parents=True, exist_ok=True)
    spans = [(i, start, min(size - 1, start + block_size - 1))
             for i, start in enumerate(range(0, size, block_size))]

    def download(span):
        index, start, end = span
        part = part_dir / f"{index:04}.part"
        if part.exists() and part.stat().st_size == end - start + 1:
            return
        for attempt in range(12):
            offset = part.stat().st_size if part.exists() else 0
            remaining = end - start + 1 - offset
            if remaining == 0:
                break
            if remaining < 0:
                raise ValueError(f"Oversized cached range: {index}")
            segment = part.with_suffix(".next")
            proc = subprocess.run([curl, "-L", "--fail", "--silent", "--show-error",
                                   "--connect-timeout", "20", "--max-time", "120",
                                   "--range", f"{start + offset}-{end}", "--output", str(segment),
                                   "--write-out", "%{http_code}", url], capture_output=True, text=True)
            if proc.stdout.strip() == "206" and segment.exists():
                received = segment.stat().st_size
                if received > remaining:
                    raise ValueError("Server returned more bytes than requested")
                if received:
                    with part.open("ab") as destination, segment.open("rb") as source:
                        shutil.copyfileobj(source, destination)
            # Interrupted requests preserve their bytes and continue from the next offset.
            if proc.returncode and attempt == 11:
                raise RuntimeError(f"Download still unavailable for part {index}")
        if part.stat().st_size != end - start + 1:
            raise ValueError(f"Invalid HTTP range length for part {index}")
        print(f"Downloaded {target.name} part {index + 1}/{len(spans)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(download, spans))
    temporary = target.with_suffix(target.suffix + ".part")
    with temporary.open("wb") as stream:
        for index, _, _ in spans:
            with (part_dir / f"{index:04}.part").open("rb") as source:
                shutil.copyfileobj(source, stream)
    temporary.replace(target)


def main():
    config = json.loads((ROOT / "starter/configs/strategies.json").read_text(encoding="utf-8"))
    if config["model"] != "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2":
        raise ValueError("This helper is only for the documented multilingual MiniLM model")
    with request(f"https://huggingface.co/api/models/{REPO}/revision/main?blobs=true") as response:
        info = json.load(response)
    revision = info["sha"]
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Invalid upstream revision")
    cache = ROOT / ".cache/fastembed"
    model_cache = cache / ("models--" + REPO.replace("/", "--"))
    snapshot = model_cache / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    manifest = {"repository": REPO, "revision": revision, "files": {}}
    siblings = {row["rfilename"]: row for row in info["siblings"]}
    if not {"model_optimized.onnx", "tokenizer.json", "config.json"} <= siblings.keys():
        raise ValueError("Required model files not present upstream")
    for name in sorted(FILES & siblings.keys()):
        meta = siblings[name]
        target = snapshot / name
        expected = meta.get("lfs", {}).get("sha256")
        size = meta.get("size")
        if not target.exists():
            print(f"Downloading {name} ({size or 'unknown'} bytes)", flush=True)
            url = f"https://huggingface.co/{REPO}/resolve/{revision}/{name}?download=true"
            if size and size > 8 * 1024 * 1024:
                download_ranges(url, target, size)
            else:
                temporary = target.with_suffix(target.suffix + ".part")
                with request(url) as response, temporary.open("wb") as stream:
                    while block := response.read(64 * 1024):
                        stream.write(block)
                temporary.replace(target)
        content = target.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if size is not None and target.stat().st_size != size:
            raise ValueError(f"Size verification failed: {name}")
        if expected and digest != expected:
            raise ValueError(f"Upstream SHA256 verification failed: {name}")
        if not expected and meta.get("blobId"):
            git_hash = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if git_hash != meta["blobId"]:
                raise ValueError(f"Upstream git blob verification failed: {name}")
        manifest["files"][name] = {"sha256": digest, "bytes": target.stat().st_size,
                                    "upstream_lfs_sha256_checked": bool(expected)}
        print(f"Verified {name}", flush=True)
    (model_cache / "refs").mkdir(exist_ok=True)
    (model_cache / "refs/main").write_text(revision, encoding="utf-8")
    (cache / "prefetch_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Model snapshot ready for local FastEmbed loading.", flush=True)


if __name__ == "__main__":
    main()
