#!/usr/bin/env python3
"""Validate a packaged native-libs archive.

Thin CLI wrapper over common.validate_artifact.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import require_python, validate_artifact


def main() -> None:
    require_python()
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--zip")
    group.add_argument("--dir")
    args = ap.parse_args()

    try:
        manifest, count = validate_artifact(Path(args.zip or args.dir))
    except (ValueError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(
        f"OK: {manifest['lib']} {manifest['upstream_version']} "
        f"{manifest['triple']} — {count} files verified"
    )


if __name__ == "__main__":
    main()
