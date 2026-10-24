#!/usr/bin/env python3
"""Compute the CI matrix from recipe metadata.

The workflow calls this instead of hardcoding libraries and runner labels:
each recipe in recipes/ advertises the OS/triple combinations it supports, so
adding a new library never requires touching the workflow file.

Usage:
  python scripts/build_matrix.py --libs all
  python scripts/build_matrix.py --libs sqlite,rocksdb-8.10.0
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import discover_recipes, require_python


def main() -> None:
    require_python()
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--libs",
        default="all",
        help="comma-separated recipe names, or 'all'",
    )
    args = ap.parse_args()
    sel = [x.strip() for x in args.libs.split(",") if x.strip()]

    rows = []
    for name, recipe in discover_recipes().items():
        if "all" not in sel and name not in sel and recipe.LIB not in sel:
            continue
        for os_name, triple in recipe.TRIPLES.items():
            rows.append({"lib": name, "os": os_name, "triple": triple})
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
