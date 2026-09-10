from utils import sqlite_helper as db
from cleaner.matching import matched_by

COOKIE_DB = "Cookies"

_CHUNK = 500


def _prep(profile_dir, domains_set, keywords):
    db_path = db.find_db_file(profile_dir, COOKIE_DB)
    if not db_path:
        return None, None, None
    return db_path, domains_set, keywords


def _load_matches(db_path, domains_set, keywords):
    rows = db.read_rows(db_path, "SELECT rowid, host_key, name FROM cookies")
    out = []
    for r in rows:
        m = matched_by(r["host_key"], domains_set, keywords)
        if m:
            out.append(
                {
                    "rowid": r["rowid"],
                    "host_key": r["host_key"],
                    "name": r["name"],
                    "matched_by": m,
                }
            )
    return out


def _chunks(ids):
    for i in range(0, len(ids), _CHUNK):
        yield ids[i:i + _CHUNK]


def scan(profile_dir, domains_set, keywords):
    db_path, dset, kws = _prep(profile_dir, domains_set, keywords)
    if not db_path or (not dset and not kws):
        return 0
    return len(_load_matches(db_path, dset, kws))


def details(profile_dir, domains_set, keywords):
    """Return matched cookies as [{host, name, matched_by}, ...]."""
    db_path, dset, kws = _prep(profile_dir, domains_set, keywords)
    if not db_path or (not dset and not kws):
        return []
    return [
        {
            "host": m["host_key"],
            "name": m["name"],
            "matched_by": m["matched_by"],
        }
        for m in _load_matches(db_path, dset, kws)
    ]


def clean(profile_dir, domains_set, keywords):
    """Delete matching cookies. Browsers must be closed."""
    db_path, dset, kws = _prep(profile_dir, domains_set, keywords)
    if not db_path or (not dset and not kws):
        return 0
    rows = [m["rowid"] for m in _load_matches(db_path, dset, kws)]
    if not rows:
        return 0
    total = 0
    for chunk in _chunks(rows):
        marks = ",".join("?" * len(chunk))
        n, _ = db.execute_write(
            db_path, [(f"DELETE FROM cookies WHERE rowid IN ({marks})", tuple(chunk))]
        )
        total += n
    db.vacuum_db(db_path)
    return total