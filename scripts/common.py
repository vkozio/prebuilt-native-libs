"""Shared helpers for prebuilt-native-libs tooling.

Requires Python >= 3.12. Standard library only — no third-party dependencies.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import types
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

MIN_PYTHON = (3, 12)
REPO_ROOT = Path(__file__).resolve().parent.parent
WHITESPACE = re.compile(r"\s+")


def require_python() -> None:
    if sys.version_info[:2] < MIN_PYTHON:
        raise SystemExit(
            f"requires Python {'.'.join(map(str, MIN_PYTHON))}+ "
            f"(got {platform.python_version()})"
        )


def log(message: str) -> None:
    print(f"[native-libs] {message}", flush=True)


def discover_recipes() -> dict[str, types.ModuleType]:
    """Import every recipe module from recipes/ (filename stem -> module).

    Recipes are plain Python files; the workflow, fetch script and matrix
    builder consume their module-level metadata instead of hardcoding library
    lists. Required metadata: ``LIB``, ``TRIPLES`` (os -> triple),
    ``ENV_PREFIX``, ``FEATURE`` and a ``verify(out, triple, cache)`` hook.
    """
    recipes: dict[str, types.ModuleType] = {}
    for path in sorted((REPO_ROOT / "recipes").glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"recipes.{path.stem}", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        recipes[path.stem] = module
    return recipes


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(list(command), cwd=cwd, env=env, check=check, text=True)


def download(url: str, dest: Path) -> Path:
    """Download to dest unless it already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        log(f"cached: {dest}")
        return dest
    log(f"download: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest


def extract_zip_strip(archive: Path, dest: Path) -> None:
    """Extract a zip, stripping the single top-level folder, if any."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            parts = member.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            target = dest / parts[1]
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))


def extract_tarball(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    run(["tar", "-xzf", str(archive), "-C", str(dest), "--strip-components=1"])


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def detect_triple() -> str:
    """Detect the host Rust triple (rustc host, else platform fallback)."""
    rustc = shutil.which("rustc")
    if rustc:
        out = subprocess.run(
            [rustc, "-vV"], capture_output=True, text=True, check=False
        ).stdout
        m = re.search(r"^host:\s*(\S+)", out, re.M)
        if m:
            return m.group(1)
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows":
        return "aarch64-pc-windows-msvc" if "arm" in machine else "x86_64-pc-windows-msvc"
    if system == "Darwin":
        return "aarch64-apple-darwin" if "arm" in machine else "x86_64-apple-darwin"
    return "aarch64-unknown-linux-gnu" if "aarch" in machine else "x86_64-unknown-linux-gnu"


def ensure_msvc_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Activate the MSVC developer environment for this process (Windows)."""
    merged = dict(os.environ if env is None else env)
    if shutil.which("cl"):
        return merged
    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(program_files) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if not vswhere.exists():
        raise RuntimeError("MSVC toolchain not found (cl.exe missing, vswhere missing)")
    out = subprocess.run(
        [
            str(vswhere), "-latest", "-products", "*",
            "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property", "installationPath",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not out:
        raise RuntimeError("Visual Studio with C++ workload not found")
    vsdevcmd = Path(out) / "Common7/Tools/VsDevCmd.bat"
    if not vsdevcmd.exists():
        raise RuntimeError(f"VsDevCmd.bat not found: {vsdevcmd}")
    lines = subprocess.run(
        ["cmd", "/d", "/s", "/c", f'call "{vsdevcmd}" >nul && set'],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    for line in lines:
        if "=" in line:
            key, _, value = line.partition("=")
            merged[key] = value
    return merged


def package_artifact(
    *,
    lib: str,
    version: str,
    ref: str,
    triple: str,
    toolchain: str,
    flags: Sequence[str],
    features: Sequence[str],
    staging: Path,
    outdir: Path,
    sums: Path | None = None,
) -> Path:
    """Zip staging (lib/ + include/) with MANIFEST.json + sha256."""
    staging, outdir = Path(staging), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for root in ("lib", "include"):
        base = staging / root
        if not base.is_dir():
            raise SystemExit(f"error: staging dir missing: {base}")
        for p in sorted(base.rglob("*")):
            if p.is_file():
                files[p.relative_to(staging).as_posix()] = f"sha256:{sha256_file(p)}"
    if not files:
        raise SystemExit("error: no files to package")
    manifest = {
        "lib": lib,
        "upstream_version": version,
        "upstream_ref": ref,
        "triple": triple,
        "toolchain": toolchain,
        "flags": list(flags),
        "features": list(features),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    zip_name = f"native-libs-{lib}-{version}-{triple}.zip"
    zip_path = outdir / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True))
        for rel in files:
            zf.write(staging / rel, rel)
    if sums is not None:
        with Path(sums).open("a", encoding="utf-8") as sf:
            sf.write(f"{sha256_file(zip_path)}  {zip_name}\n")
    return zip_path


def validate_artifact(source: Path) -> tuple[dict, int]:
    """Validate MANIFEST.json + sha256 for a zip or extracted directory."""
    source = Path(source)
    if source.is_dir():
        manifest = json.loads((source / "MANIFEST.json").read_text(encoding="utf-8"))
        members = {p.relative_to(source) for p in source.rglob("*") if p.is_file()}

        def read(rel: str) -> bytes:
            if rel not in {p.as_posix() for p in members}:
                raise KeyError(rel)
            return (source / rel).read_bytes()
    else:
        with zipfile.ZipFile(source) as zf:
            members = {i.filename for i in zf.infolist()}
            manifest = json.loads(zf.read("MANIFEST.json"))
            data = {
                name: zf.read(name)
                for name in members
                if not name.endswith("/")
            }

        def read(rel: str) -> bytes:
            if rel not in data:
                raise KeyError(rel)
            return data[rel]
    required = ("lib", "upstream_version", "triple", "files")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"manifest missing keys: {missing}")
    errors: list[str] = []
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        errors.append("manifest['files'] empty or not an object")
    for rel, spec in files.items():
        if not isinstance(spec, str) or not spec.startswith("sha256:"):
            errors.append(f"bad hash spec for {rel}")
            continue
        try:
            digest = sha256_bytes(read(rel))
        except KeyError:
            errors.append(f"missing file in archive: {rel}")
            continue
        if digest != spec[len("sha256:"):]:
            errors.append(f"hash mismatch: {rel}")
    if errors:
        raise ValueError("\n".join(errors))
    return manifest, len(files)


def merge_env_config(path: Path, pairs: Iterable[str]) -> None:
    """Merge key=value pairs into the [env] section of a Cargo config.

    Creates the file if missing, updates existing keys in place, appends new
    ones, and never touches other sections.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    env_idx = next(
        (i for i, ln in enumerate(lines) if re.match(r"^\s*\[env\]\s*(#.*)?$", ln)),
        None,
    )
    if env_idx is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("[env]")
        for pair in pairs:
            lines.append("  " + pair)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return
    existing: dict[str, int] = {}
    end = len(lines)
    for i in range(env_idx + 1, len(lines)):
        if re.match(r"^\s*\[.+", lines[i]):
            end = i
            break
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*", lines[i])
        if m:
            existing[m.group(1)] = i
    new_pairs: list[str] = []
    for pair in pairs:
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*=\s*(.*)$", pair)
        if m and m.group(1) in existing:
            lines[existing[m.group(1)]] = pair
        else:
            new_pairs.append(pair)
    if new_pairs:
        lines = lines[:end] + ["  " + p for p in new_pairs] + lines[end:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
