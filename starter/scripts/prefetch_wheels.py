"""Recover a slow Docker install using verified Linux CPython 3.12 wheels."""
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

from pip._vendor.packaging.tags import cpython_tags, compatible_tags
from pip._vendor.packaging.utils import parse_wheel_filename
from prefetch_model import download_ranges

ROOT = Path(__file__).resolve().parents[2]
PLATFORMS = ["manylinux_2_28_x86_64", "manylinux_2_27_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64", "manylinux1_x86_64"]


def main():
    target = ROOT / "starter/wheels"
    target.mkdir(exist_ok=True)
    tags = list(cpython_tags((3, 12), abis=["cp312"], platforms=PLATFORMS))
    tags += list(compatible_tags((3, 12), interpreter="cp312", platforms=PLATFORMS))
    priority = {tag: i for i, tag in enumerate(tags)}
    saved = ROOT / "artifacts/wheels_manifest.json"
    if saved.exists():
        versions = {}
        for item in json.loads(saved.read_text(encoding="utf-8")):
            name, version, _, _ = parse_wheel_filename(item["filename"])
            versions[str(name)] = str(version)
    else:
        versions = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions(path=[str(ROOT / ".venv/Lib/site-packages")])
                    if d.metadata["Name"].lower() not in {"pip", "setuptools", "wheel"}}
    if not versions:
        raise ValueError("Need the saved wheel manifest or prepared Windows venv metadata")

    def metadata(item):
        name, version = item
        with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
            info = json.load(response)
        candidates = []
        for row in info["urls"]:
            if not row["filename"].endswith(".whl"):
                continue
            _, _, _, wheel_tags = parse_wheel_filename(row["filename"])
            ranks = [priority[tag] for tag in wheel_tags if tag in priority]
            if ranks:
                candidates.append((min(ranks), row["filename"], row))
        if not candidates:
            raise ValueError(f"No Linux CPython 3.12 wheel for {name}=={version}")
        return min(candidates)[2]

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = list(pool.map(metadata, versions.items()))
    curl = shutil.which("curl.exe") or shutil.which("curl")

    def download(row):
        path = target / row["filename"]
        if not path.exists():
            print("Downloading " + path.name, flush=True)
            if row["size"] > 1024 * 1024:
                download_ranges(row["url"], path, row["size"], block_size=1024 * 1024, workers=4)
            else:
                subprocess.run([curl, "-L", "--fail", "--silent", "--show-error", "--retry", "5",
                                "--connect-timeout", "20", "--max-time", "120", "--output", str(path), row["url"]], check=True)
        if path.stat().st_size != row["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != row["digests"]["sha256"]:
            raise ValueError("Wheel integrity failed: " + path.name)
        print("Verified " + path.name, flush=True)
        return {"filename": path.name, "sha256": row["digests"]["sha256"], "bytes": row["size"]}

    with ThreadPoolExecutor(max_workers=3) as pool:
        verified = list(pool.map(download, files))
    (ROOT / "artifacts/wheels_manifest.json").write_text(json.dumps(verified, indent=2) + "\n", encoding="utf-8")
    (target / "COMPLETE").write_text("Verified against PyPI SHA256; Linux CPython 3.12\n", encoding="utf-8")
    print("Verified offline wheelhouse complete.", flush=True)


if __name__ == "__main__":
    main()
