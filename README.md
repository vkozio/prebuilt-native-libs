# prebuilt-native-libs

Prebuilt static native libraries (C/C++), built once in CI and distributed as
zip assets (static libraries + headers + a MANIFEST with sha256)

## Supported platforms

| Triple                     | Runner                | Minimum OS                |
| -------------------------- | --------------------- | ------------------------- |
| `x86_64-pc-windows-msvc`   | `windows-2022` (MSVC) | Windows 10                |
| `x86_64-unknown-linux-gnu` | `ubuntu-22.04`        | glibc 2.35                |
| `x86_64-apple-darwin`      | `macos-15-intel`      | macOS 11+ (Intel)         |
| `aarch64-apple-darwin`     | `macos-26-arm64`      | macOS 11+ (Apple Silicon) |

Asset name (immutable):

```
native-libs-<lib>-<upstream_version>-<triple>.zip
```

Zip contents:

```
├── lib/          # static library (*.lib / *.a)
├── include/      # headers
└── MANIFEST.json # metadata + sha256 of every file
```

## Artifact schema

```
native-libs-<lib>-<upstream_version>-<triple>.zip
```

Zip contents:

```
├── lib/                       # static lib (*.lib / *.a)
├── include/                   # full header tree
└── MANIFEST.json
```

`MANIFEST.json`:

```json
{
  "lib": "rocksdb",
  "upstream_version": "8.10.0",
  "upstream_ref": "<commit/tag>",
  "triple": "x86_64-pc-windows-msvc",
  "toolchain": "msvc 19.4x / clang 17 / gcc 12",
  "flags": ["..."],
  "features": ["..."],
  "files": { "lib/rocksdb.lib": "sha256:...", "include/rocksdb/...": "sha256:..." }
}
```

First-wave triples: `x86_64-pc-windows-msvc` (Windows 10),
`x86_64-unknown-linux-gnu`, `x86_64-apple-darwin` (macOS Intel),
`aarch64-apple-darwin` (Apple Silicon). macOS: separate per-arch assets are
built; universal binaries via `lipo` are a next step if needed.

## Libraries

| Recipe                      | Version             | Consumer                                              |
| --------------------------- | ------------------- | ----------------------------------------------------- |
| `recipes/rocksdb-8.10.0.py` | RocksDB 8.10.0      | crate `rocksdb` 0.22 (`librocksdb-sys` 0.16.0+8.10.0) |
| `recipes/sqlite.py`         | amalgamation 3.50.2 | crate `sqlite` 0.36 (`sqlite3-sys` 0.17)              |

How to add a library: see [recipes/README.md](recipes/README.md).

## Requirements

- **Python >= 3.12** (standard library only — no third-party dependencies)
- `gh` CLI for release downloads (or `--url` to fetch an asset directly)
- On Windows, the MSVC developer environment is activated automatically by the
  recipes when `cl` is not on PATH.

## Usage

Download an asset and unpack it into a local cache:

```
python fetch/fetch-native-libs.py --lib rocksdb,sqlite --channel release [--triple auto]
```

The script downloads the zip, verifies sha256 against the MANIFEST and unpacks
into `$HOME/.cache/native-libs/<triple>/<lib>/` — the home directory is
resolved automatically via the `$HOME` variable (PowerShell, POSIX shells;
`%USERPROFILE%` in cmd), so there is nothing to hardcode.

### Automatic Cargo config (recommended)

Have the script write the `[env]` block into `.cargo/config.toml` for you:

```
python fetch/fetch-native-libs.py --lib rocksdb,sqlite --write-cargo-config .cargo/config.toml
```

The file is created if missing; existing `[env]` keys are updated in place, new
ones are appended. The written values are absolute paths resolved from your
home directory. To see the block without touching any file, use
`--write-env <path>` or read the printed output.

Note: Cargo's `.cargo/config.toml` does not expand `~` or `%VAR%` itself,
which is why the fetch script does the substitution for you and writes the real
paths.

## Channels

- **dev** — artifacts on every `workflow_dispatch` (`GitHub Actions` → Actions →
  `native-libs` → Run workflow). Kept for 14 days.
- **release** — GitHub Release under tag `native-libs-v<version>`: built by the
  same workflow with `publish_release=true` + `release_version`.

## License

Repo scripts and docs are MIT. Artifacts remain under their upstream licenses.
