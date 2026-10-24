use std::path::PathBuf;

fn temp_path(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("consumer-fixture-{}-{}", name, std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

#[cfg(feature = "rocksdb")]
fn test_rocksdb() {
    let dir = temp_path("rocksdb");
    let db = rocksdb::DB::open_default(&dir).expect("rocksdb open");
    db.put(b"key1", b"value1").expect("put");
    db.put(b"key2", b"value2").expect("put");
    let got = db.get(b"key1").expect("get").expect("value");
    assert_eq!(got.as_slice(), b"value1");

    // The iterator borrows the DB; keep it scoped so the borrow ends before
    // exclusive use of `db` below (drop/delete).
    {
        let mut it = db.iterator(rocksdb::IteratorMode::Start);
        let mut n = 0;
        while let Some(Ok(kv)) = it.next() {
            assert!(kv.0.len() > 0);
            n += 1;
        }
        assert_eq!(n, 2);
    }

    db.delete(b"key2").expect("delete");
    assert!(db.get(b"key2").expect("get").is_none());
    drop(db);
    let _ = std::fs::remove_dir_all(&dir);
    println!("PASS rocksdb");
}

#[cfg(feature = "sqlite")]
fn test_sqlite() {
    let dir = temp_path("sqlite");
    let db_path = dir.join("test.db");
    let conn = sqlite::Connection::open(&db_path).expect("sqlite open");
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)").expect("create");
    conn.execute("INSERT INTO t (v) VALUES ('hello')").expect("insert");
    let n: i64 = conn
        .prepare("SELECT COUNT(*) FROM t")
        .unwrap()
        .iter()
        .next()
        .unwrap()
        .unwrap()
        .read(0)
        .unwrap();
    assert_eq!(n, 1);
    let mut stmt = conn.prepare("SELECT v FROM t").unwrap();
    while let Ok(Some(row)) = stmt.next() {
        assert_eq!(row.read::<&str, _>(0).unwrap(), "hello");
    }
    drop(conn);
    let _ = std::fs::remove_dir_all(&dir);
    println!("PASS sqlite");
}

fn main() {
    #[cfg(feature = "rocksdb")]
    test_rocksdb();
    #[cfg(feature = "sqlite")]
    test_sqlite();
    println!("consumer-fixture OK");
}
