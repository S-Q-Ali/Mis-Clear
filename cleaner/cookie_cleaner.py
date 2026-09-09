from utils import sqlite_helper as db


COOKIE_DB = "Cookies"


def _like(domains):
    where = " OR ".join(["host_key LIKE ?"] * len(domains))
    params = tuple(f"%{d}%" for d in domains)
    return where, params


def scan(profile_dir, domains):
    db_path = db.find_db_file(profile_dir, COOKIE_DB)
    if not db_path or not domains:
        return 0
    where, params = _like(domains)
    rows = db.read_rows(db_path, f"SELECT COUNT(*) AS c FROM cookies WHERE {where}", params)
    return rows[0]["c"] if rows else 0


def clean(profile_dir, domains):
    """Delete matching cookies. Browsers must be closed."""
    db_path = db.find_db_file(profile_dir, COOKIE_DB)
    if not db_path or not domains:
        return 0
    where, params = _like(domains)
    rows, err = db.execute_write(db_path, [(f"DELETE FROM cookies WHERE {where}", params)])
    if not err:
        db.vacuum_db(db_path)
    return rows
