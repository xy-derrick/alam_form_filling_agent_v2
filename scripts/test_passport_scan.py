from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ocr import extract_passport_text  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_passport_scan.py <passport_path>")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    text, used_ocr = extract_passport_text(str(path))
    print(f"used_ocr={used_ocr}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
