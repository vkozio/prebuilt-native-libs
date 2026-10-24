# Build recipes

Each library is a single cross-platform recipe file `recipes/<lib>.py`:

- Python >= 3.12, stdlib only — works on Windows/Linux/macOS

It accepts the same parameters:

```
--triple <rust-triple>   # required
--out <staging-dir>      # staging: lib/ and include/ are written here
--version <upstream-ver> # optional (recipe-specific default)
--cache <cache-dir>      # cache for downloaded sources (default: temp)
```

A recipe must:

1. download sources (or build through a consumer crate) into `--cache`;
2. build the static library natively (no cross-compilation — each runner
   builds its own triple) using `scripts/common.py` helpers (`download`,
   `extract_*`, `ensure_msvc_env`, ...);
3. put the result into `<out>/lib/` and `<out>/include/`;
4. call `common.package_artifact(...)` — it produces the zip + MANIFEST.json +
   sha256.

Validation after the build is done by `python scripts/check_manifest.py --zip <zip>`.

Shared logic (downloads, extraction, MSVC env, packaging, validation, env-block
merge, triple detection) lives in `scripts/common.py` and is reused by every
recipe and by `fetch/fetch-native-libs.py` — no duplicated shell/PowerShell
code.

## How to add a new library

1. Create `recipes/<lib>.py` following the `recipes/sqlite.py` example.
2. Add a row to the matrix in `.github/workflows/native-libs.yml`
   (os + triple + lib).
3. Add a consumer fixture to `tests/consumer-fixture/` (env variables).
4. Run it locally for one triple, then in CI.

## Cache

Downloaded tarballs are kept in `--cache`; do not rebuild what can be reused
within one runner.
