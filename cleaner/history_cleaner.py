from utils import sqlite_helper as db


HISTORY_DB = "History"


def _like(domains):
    where = " OR ".join(["url LIKE ?"] * len(domains))
    params = tuple(f"%{d}%" for d in domains)
    return where, params


def _url_ids(work, domains):
    where, params = _like(domains)
    rows = db.read_rows(work, f"SELECT id FROM urls WHERE {where}", params)
    return [r["id"] for r in rows]


def scan(profile_dir, domains):
    db_path = db.find_db_file(profile_dir, HISTORY_DB)
    if not db_path or not domains:
        return 0
    work = db.make_working_copy(db_path) or db_path
    return len(_url_ids(work, domains))


def clean(profile_dir, domains):
    """Delete matching URLs and their visits. Returns total rows affected."""
    db_path = db.find_db_file(profile_dir, HISTORY_DB)
    if not db_path or not domains:
        return 0
    work = db.make_working_copy(db_path) or db_path

    ids = _url_ids(work, domains)
    if not ids:
        return 0

    id_marks = ",".join("?" * len(ids))
    stmts = [
        (f"DELETE FROM visits WHERE url IN ({id_marks})", tuple(ids)),
        (f"DELETE FROM visit_source WHERE visit_id NOT IN (SELECT id FROM visits)", ()),
        (f"DELETE FROM urls WHERE id IN ({id_marks})", tuple(ids)),
    ]
    rows, err = db.execute_write(work, stmts)
    if err is None:
        db.vacuum_db(work)
    return rows
