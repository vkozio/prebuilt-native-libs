use std::env;
use std::fs;
use std::path::Path;

fn main() {
    // librocksdb-sys unconditionally runs `git submodule update` unless
    // `<crate>/rocksdb/AUTHORS` exists. When linking a prebuilt library we do
    // not want any git network activity, so mark the tree as present.

    if env::var("CARGO_FEATURE_ROCKSDB").is_ok() {
        let marker = Path::new("rocksdb/AUTHORS");
        if !marker.exists() {
            fs::create_dir_all(marker.parent().unwrap()).unwrap();
            fs::write(marker, "prebuilt: headers provided via ROCKSDB_INCLUDE_DIR\n").unwrap();
        }
        if env::var("TARGET").unwrap().contains("windows") {
            println!("cargo:rustc-link-lib=rpcrt4");
            println!("cargo:rustc-link-lib=shlwapi");
        }
    }
}
