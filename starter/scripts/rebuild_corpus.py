"""Reproduce the reviewed corpus using saved preparation parameters."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter/scripts"))
from prepare_pdf import main

if __name__ == "__main__":
    cfg = json.loads((ROOT / "data/preparation.json").read_text(encoding="utf-8"))
    sys.argv = [sys.argv[0], "--pdf", str(ROOT / cfg["pdf"]),
                "--source-id", cfg["source_id"], "--title", cfg["title"],
                "--permission", cfg["permission"], "--pages", cfg["pages"],
                "--sections", str(ROOT / cfg["sections"]), "--language", cfg["language"],
                "--header-pattern", cfg["header_pattern"], "--footer-pattern", cfg["footer_pattern"]]
    main()
