#!/usr/bin/env python3
"""Fetch prebuilt native libraries and install them into a local cache.

Cross-platform (Python >= 3.12, stdlib only). Assets are downloaded from a
GitHub Release (dev channel rejected unless --tag/--url given), verified
against MANIFEST.json sha256, unpacked into
`$HOME/.cache/native-libs/<triple>/<lib>/`, and the matching [env] block is
printed and optionally written/merged into `.cargo/config.toml`.

Usage:
  python fetch/fetch-native-libs.py --lib rocksdb,sqlite --channel release \
      [--triple auto] [--write-cargo-config .cargo/config.toml]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import (
    detect_triple,
    discover_recipes,
    log,
    merge_env_config,
    require_python,
    sha256_file,
)


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def resolve_asset(
    repo: str,
    lib: str,
    triple: str,
    channel: str,
    tag: str,
    url: str,
) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="native-libs-fetch-"))
    if url:
        zip_path = tmp / "asset.zip"
        log(f"download: {url}")
        urllib.request.urlretrieve(url, zip_path)
    else:
        if channel == "release":
            tag = tag or gh("api", f"repos/{repo}/releases/latest", "--jq", ".tag_name")
        elif not tag:
            raise SystemExit("dev channel requires --tag or --url")
        pattern = re.compile(rf"^native-libs-{re.escape(lib)}-.*-{re.escape(triple)}\.zip$")
        names = [
            name for name in gh("api", f"repos/{repo}/releases/tags/{tag}",
                                "--jq", ".assets[].name").splitlines()
            if pattern.match(name)
        ]
        if not names:
            raise SystemExit(f"no asset for lib={lib} triple={triple} in {repo} tag={tag}")
        name = sorted(names)[-1]
        zip_path = tmp / name
        gh("release", "download", tag, "--repo", repo, "--pattern", name,
           "--dir", str(tmp), "--clobber")
    extracted = tmp / "x"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    return extracted


def install(extracted: Path, lib: str, triple: str, cache_root: Path) -> Path:
    target = cache_root / triple / lib
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((extracted / "MANIFEST.json").read_text(encoding="utf-8"))
    for rel, spec in manifest["files"].items():
        file = extracted / rel
        if not file.is_file():
            raise SystemExit(f"missing file in archive: {rel}")
        if sha256_file(file) != spec[len("sha256:"):]:
            raise SystemExit(f"sha256 mismatch: {rel}")
    shutil.copytree(extracted, target, dirs_exist_ok=True)
    log(f"installed: {target}")
    return target


def main() -> None:
    require_python()
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default="rocksdb,sqlite")
    ap.add_argument("--triple", default="auto")
    ap.add_argument("--channel", choices=["release", "dev"], default="release")
    ap.add_argument("--tag", default="")
    ap.add_argument("--repo", default="vkozio/prebuilt-native-libs")
    ap.add_argument("--url", default="")
    ap.add_argument("--write-env", default="")
    ap.add_argument("--write-cargo-config", default="")
    ap.add_argument("--cache-root", default=str(Path.home() / ".cache" / "native-libs"))
    args = ap.parse_args()

    triple = args.triple if args.triple not in ("", "auto") else detect_triple()
    log(f"triple: {triple}")
    cache_root = Path(args.cache_root)
    recipes = discover_recipes()

    env_lines: list[str] = []
    for lib in (part.strip() for part in args.lib.split(",")):
        if not lib:
            continue
        recipe = recipes.get(lib)
        if recipe is None:
            recipe = next((r for r in recipes.values() if r.LIB == lib), None)
        if recipe is None:
            raise SystemExit(f"unknown lib: {lib} (no recipes/{lib}.py)")
        prefix = recipe.ENV_PREFIX
        short = recipe.LIB
        extracted = resolve_asset(args.repo, short, triple, args.channel, args.tag, args.url)
        target = install(extracted, short, triple, cache_root)
        env_lines.extend(
            [
                f"{prefix}_LIB_DIR={target / 'lib'}",
                f"{prefix}_INCLUDE_DIR={target / 'include'}",
                f"{prefix}_STATIC=1",
            ]
        )

    if args.write_env:
        Path(args.write_env).write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        log(f"env block written to: {args.write_env}")
    if args.write_cargo_config:
        merge_env_config(Path(args.write_cargo_config), env_lines)
        log(f"[env] block merged into: {args.write_cargo_config}")

    print("\n# add to .cargo/config.toml [env] (or re-run with --write-cargo-config)")
    for line in env_lines:
        print(line)


if __name__ == "__main__":
    main()
