#!/usr/bin/env python3
"""Build RocksDB as a static library and package it.

Cross-platform (Python >= 3.12, stdlib only). The build goes through a scratch
consumer crate (`rocksdb` 0.22 + `librocksdb-sys` 0.16.0, bundled), so the
compile flags exactly match what real consumers use — ABI compatibility is
guaranteed. Upstream RocksDB sources are unpacked into the scratch crate so
bindgen headers and the AUTHORS marker are present.

Usage:
  python recipes/rocksdb-8.10.0.py --triple <triple> --out <staging-out> \
      [--version 8.10.0] [--cache <dir>]
"""
import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import (
    cargo_env,
    download,
    extract_tarball,
    log,
    package_artifact,
    REPO_ROOT,
    require_python,
    run,
)

ROCK_VERSION = "8.10.0"
CARGO_TOML = """[package]
name = "rdb_prebuilt_consumer"
version = "0.0.0"
edition = "2021"

[dependencies]
rocksdb = "=0.22.0"
librocksdb-sys = "=0.16.0"
"""

LIB = "rocksdb"
UPSTREAM_VERSION = ROCK_VERSION
FEATURE = "rocksdb"
ENV_PREFIX = "ROCKSDB"
TRIPLES = {
    "windows-2022": "x86_64-pc-windows-msvc",
    "ubuntu-22.04": "x86_64-unknown-linux-gnu",
    "macos-15-intel": "x86_64-apple-darwin",
    "macos-26": "aarch64-apple-darwin",
}


def build(triple: str, out: Path, cache: Path, rock_version: str = ROCK_VERSION) -> None:
    src = cache / f"rocksdb-{rock_version}"
    if not (src / "AUTHORS").exists():
        tgz = cache / f"rocksdb-{rock_version}.tar.gz"
        if not tgz.exists():
            download(
                f"https://github.com/facebook/rocksdb/archive/refs/tags/v{rock_version}.tar.gz",
                tgz,
            )
        extract_tarball(tgz, src)

    scratch = cache / f"rdb-consumer-{rock_version}"
    (scratch / "src").mkdir(parents=True, exist_ok=True)
    (scratch / "Cargo.toml").write_text(CARGO_TOML, encoding="utf-8")
    main_rs = scratch / "src/main.rs"
    if not main_rs.exists():
        main_rs.write_text("fn main() {}\n", encoding="utf-8")
    upstream_in_scratch = scratch / "rocksdb"
    if not (upstream_in_scratch / "AUTHORS").exists():
        shutil.copytree(src, upstream_in_scratch)

    env = cargo_env()
    if "windows-msvc" in triple:
        env = ensure_msvc_env(env)
    env["CARGO_TARGET_DIR"] = str(scratch / "target")
    env["ROCKSDB_INCLUDE_DIR"] = str(upstream_in_scratch / "include")
    run(["cargo", "build", "--release"], cwd=scratch, env=env)

    build_dir = scratch / "target/release/build"
    candidates = sorted(
        build_dir.glob("librocksdb-sys-*/out/*"),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    lib_file = next((p for p in candidates if p.suffix in (".a", ".lib")), None)
    if lib_file is None:
        raise RuntimeError("no static rocksdb library found in OUT_DIR")

    staging = out / "rocksdb"
    libdir, incdir = staging / "lib", staging / "include"
    libdir.mkdir(parents=True, exist_ok=True)
    incdir.mkdir(parents=True, exist_ok=True)
    lib_name = "rocksdb.lib" if "windows-msvc" in triple else "librocksdb.a"
    shutil.copy2(lib_file, libdir / lib_name)
    shutil.copytree(upstream_in_scratch / "include", incdir, dirs_exist_ok=True)

    toolchain = f"cargo + librocksdb-sys 0.16.0+8.10.0 (bundled {rock_version})"
    zip_path = package_artifact(
        lib="rocksdb",
        version=rock_version,
        ref=f"v{rock_version}",
        triple=triple,
        toolchain=toolchain,
        flags=[],
        features=[],
        staging=staging,
        outdir=out,
    )
    log(f"rocksdb [{triple}] done: lib={lib_name} zip={zip_path.name}")


def verify(out: Path, triple: str, cache: Path) -> None:
    """Link and run the consumer fixture against the staged build."""
    del cache
    staging = out / LIB
    env = dict(os.environ)
    env[f"{ENV_PREFIX}_LIB_DIR"] = str(staging / "lib")
    env[f"{ENV_PREFIX}_INCLUDE_DIR"] = str(staging / "include")
    env[f"{ENV_PREFIX}_STATIC"] = "1"
    if "windows-msvc" in triple:
        env = ensure_msvc_env(env)
    cargo = shutil.which("cargo")
    log(f"cargo binary: {cargo}  (path={env.get('PATH', '')[:200]})")
    if cargo:
        run([cargo, "--version"], env=cargo_env(env))
    run(
        ["cargo", "run", "--release", "--no-default-features", "--features", FEATURE],
        cwd=REPO_ROOT / "tests" / "consumer-fixture",
        env=cargo_env(env),
    )
    log(f"rocksdb consumer fixture PASSED ({triple})")


def main() -> None:
    require_python()
    ap = argparse.ArgumentParser()
    ap.add_argument("--triple", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default=ROCK_VERSION)
    ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "native-libs-cache"))
    ap.add_argument("--verify", action="store_true", help="run the consumer fixture instead of building")
    args = ap.parse_args()
    if args.verify:
        verify(Path(args.out), args.triple, Path(args.cache))
        return
    build(args.triple, Path(args.out), Path(args.cache), args.version)


if __name__ == "__main__":
    main()
