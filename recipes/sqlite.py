#!/usr/bin/env python3
"""Build the SQLite amalgamation as a static library and package it.

Cross-platform (Python >= 3.12, stdlib only). On Windows the MSVC developer
environment is activated automatically when `cl` is not on PATH.

Usage:
  python recipes/sqlite.py --triple <triple> --out <staging-out> \
      [--version 3.50.2] [--year 2025] [--cache <dir>]
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import (
    download,
    ensure_msvc_env,
    extract_zip_strip,
    log,
    package_artifact,
    require_python,
    run,
)

SQLITE_VERSION = "3.50.2"
SQLITE_YEAR = "2025"
FLAGS = [
    "-DSQLITE_THREADSAFE=1",
    "-DSQLITE_ENABLE_COLUMN_METADATA",
    "-DSQLITE_ENABLE_FTS5",
    "-DSQLITE_ENABLE_RTREE",
    "-DSQLITE_ENABLE_JSON1",
    "-DNDEBUG",
]


def version_code(version: str) -> int:
    major, minor, patch = (int(part) for part in version.split("."))
    return major * 1_000_000 + minor * 10_000 + patch * 100


def build(
    triple: str,
    out: Path,
    cache: Path,
    version: str = SQLITE_VERSION,
    year: str = SQLITE_YEAR,
) -> None:
    code = version_code(version)
    src = cache / f"sqlite-amalgamation-{code}"
    if not (src / "sqlite3.c").exists():
        archive = cache / f"sqlite-amalgamation-{code}.zip"
        if not archive.exists():
            download(f"https://www.sqlite.org/{year}/sqlite-amalgamation-{code}.zip", archive)
        extract_zip_strip(archive, src)

    staging = out / "sqlite"
    libdir, incdir = staging / "lib", staging / "include"
    libdir.mkdir(parents=True, exist_ok=True)
    incdir.mkdir(parents=True, exist_ok=True)

    if "windows-msvc" in triple:
        env = ensure_msvc_env()
        obj = libdir / "sqlite3.obj"
        ms_flags = [re.sub(r"^-", "/", flag) for flag in FLAGS]
        run(["cl", "/nologo", "/O2", "/c", *ms_flags, f"/Fo{obj}",
             str(src / "sqlite3.c")], env=env)
        run(["lib", "/nologo", f"/OUT:{libdir / 'sqlite3.lib'}", str(obj)], env=env)
        obj.unlink()
        lib_name = "sqlite3.lib"
        toolchain = "msvc (cl/lib)"
    else:
        cc = os.environ.get("CC") or "cc"
        obj = libdir / "sqlite3.o"
        run([cc, "-O2", "-fPIC", "-c", *FLAGS, "-o", str(obj),
             str(src / "sqlite3.c")])
        run(["ar", "rcs", str(libdir / "libsqlite3.a"), str(obj)])
        obj.unlink()
        lib_name = "libsqlite3.a"
        toolchain = "cc + ar"

    shutil.copy2(src / "sqlite3.h", incdir)
    shutil.copy2(src / "sqlite3ext.h", incdir)

    zip_path = package_artifact(
        lib="sqlite",
        version=version,
        ref=f"amalgamation-{code}",
        triple=triple,
        toolchain=toolchain,
        flags=FLAGS,
        features=[],
        staging=staging,
        outdir=out,
    )
    log(f"sqlite [{triple}] done: lib={lib_name} zip={zip_path.name}")


def main() -> None:
    require_python()
    ap = argparse.ArgumentParser()
    ap.add_argument("--triple", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default=SQLITE_VERSION)
    ap.add_argument("--year", default=SQLITE_YEAR)
    ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "native-libs-cache"))
    args = ap.parse_args()
    build(args.triple, Path(args.out), Path(args.cache), args.version, args.year)


if __name__ == "__main__":
    main()
