from utils import sqlite_helper as db


WEB_DATA_DB = "Web Data"


def _like(col, domains):
    where = " OR ".join([f"{col} LIKE ?"] * len(domains))
    params = tuple(f"%{d}%" for d in domains)
    return where, params


def scan(profile_dir, domains):
    db_path = db.find_db_file(profile_dir, WEB_DATA_DB)
    if not db_path or not domains:
        return 0
    work = db.make_working_copy(db_path) or db_path
    where, params = _like("url", domains)
    rows = db.read_rows(work, f"SELECT COUNT(*) AS c FROM autofill WHERE {where}", params)
    return rows[0]["c"] if rows else 0


def clean(profile_dir, domains):
    db_path = db.find_db_file(profile_dir, WEB_DATA_DB)
    if not db_path or not domains:
        return 0
    work = db.make_working_copy(db_path) or db_path
    where, params = _like("url", domains)
    rows, err = db.execute_write(work, [(f"DELETE FROM autofill WHERE {where}", params)])
    if err is None:
        db.vacuum_db(work)
    return rows
