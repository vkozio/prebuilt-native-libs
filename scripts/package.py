#!/usr/bin/env python3
"""Package a staged native build into a release zip with MANIFEST.json.

Thin CLI wrapper over common.package_artifact.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import package_artifact, require_python


def main() -> None:
    require_python()
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--ref", default="")
    ap.add_argument("--triple", required=True)
    ap.add_argument("--toolchain", default="")
    ap.add_argument("--flags", default="[]")
    ap.add_argument("--features", default="[]")
    ap.add_argument("--dir", required=True, help="staging dir with lib/ and include/")
    ap.add_argument("--out", required=True, help="output dir for the zip")
    ap.add_argument("--sums", default="", help="optional SHA256SUMS file path")
    args = ap.parse_args()

    zip_path = package_artifact(
        lib=args.lib,
        version=args.version,
        ref=args.ref,
        triple=args.triple,
        toolchain=args.toolchain,
        flags=json.loads(args.flags),
        features=json.loads(args.features),
        staging=args.dir,
        outdir=args.out,
        sums=Path(args.sums) if args.sums else None,
    )
    print(f"zip: {zip_path}")


if __name__ == "__main__":
    main()
