from utils import sqlite_helper as db
from cleaner.matching import matched_by

COOKIE_DB = "Cookies"
FIREFOX_COOKIES_DB = "cookies.sqlite"

_CHUNK = 500


def _locate(profile_dir):
    path = db.find_db_file(profile_dir, COOKIE_DB)
    if path:
        return path, "chromium"
    path = db.find_db_file(profile_dir, FIREFOX_COOKIES_DB)
    if path:
        return path, "firefox"
    return None, None


def _load_matches(db_path, schema, domains_set, keywords):
    if schema == "firefox":
        pk, hostkey = "id", "host"
        rows = db.read_rows(db_path, "SELECT id, host, name FROM moz_cookies")
    else:
        pk, hostkey = "rowid", "host_key"
        rows = db.read_rows(db_path, "SELECT rowid, host_key, name FROM cookies")
    out = []
    for r in rows:
        m = matched_by(r[hostkey], domains_set, keywords)
        if m:
            out.append(
                {
                    "pk": r[pk],
                    "host_key": r[hostkey],
                    "name": r.get("name"),
                    "matched_by": m,
                }
            )
    return out


def _chunks(ids):
    for i in range(0, len(ids), _CHUNK):
        yield ids[i:i + _CHUNK]


def scan(profile_dir, domains_set, keywords):
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return 0
    return len(_load_matches(db_path, schema, domains_set, keywords))


def details(profile_dir, domains_set, keywords):
    """Return matched cookies as [{host, name, matched_by}, ...]."""
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return []
    return [
        {
            "host": m["host_key"],
            "name": m["name"],
            "matched_by": m["matched_by"],
        }
        for m in _load_matches(db_path, schema, domains_set, keywords)
    ]


def clean(profile_dir, domains_set, keywords):
    """Delete matching cookies. Chromium: cookies/rowid. Firefox: moz_cookies/id."""
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return 0
    pks = [m["pk"] for m in _load_matches(db_path, schema, domains_set, keywords)]
    if not pks:
        return 0
    table = "cookies" if schema == "chromium" else "moz_cookies"
    pkcol = "rowid" if schema == "chromium" else "id"
    total = 0
    for chunk in _chunks(pks):
        marks = ",".join("?" * len(chunk))
        n, _ = db.execute_write(
            db_path, [(f"DELETE FROM {table} WHERE {pkcol} IN ({marks})", tuple(chunk))]
        )
        total += n
    db.vacuum_db(db_path)
    return total