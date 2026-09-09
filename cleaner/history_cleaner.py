from utils import sqlite_helper as db


HISTORY_DB = "History"


def _like(domains):
    where = " OR ".join(["url LIKE ?"] * len(domains))
    params = tuple(f"%{d}%" for d in domains)
    return where, params


def _url_ids(db_path, domains):
    where, params = _like(domains)
    rows = db.read_rows(db_path, f"SELECT id FROM urls WHERE {where}", params)
    return [r["id"] for r in rows]


def scan(profile_dir, domains):
    """Read-only scan. Returns matched URL count."""
    db_path = db.find_db_file(profile_dir, HISTORY_DB)
    if not db_path or not domains:
        return 0
    return len(_url_ids(db_path, domains))


def clean(profile_dir, domains):
    """Delete matching URLs and their visits. Browsers must be closed.

    Works directly on the live DB. Returns total rows affected.
    """
    db_path = db.find_db_file(profile_dir, HISTORY_DB)
    if not db_path or not domains:
        return 0
    ids = _url_ids(db_path, domains)
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    stmts = [
        (f"DELETE FROM visits WHERE url IN ({marks})", tuple(ids)),
        (f"DELETE FROM urls WHERE id IN ({marks})", tuple(ids)),
    ]
    rows, err = db.execute_write(db_path, stmts)
    if not err:
        db.vacuum_db(db_path)
    elif "no such table: visits" in (err or ""):
        # fallback for DBs without a visits table
        only_urls = [(f"DELETE FROM urls WHERE id IN ({marks})", tuple(ids))]
        rows, err = db.execute_write(db_path, only_urls)
        if not err:
            db.vacuum_db(db_path)
    return rows
