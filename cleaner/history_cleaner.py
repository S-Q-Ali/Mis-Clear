from utils import sqlite_helper as db
from cleaner.matching import matched_by

HISTORY_DB = "History"

_CHUNK = 500


def _prep(profile_dir, domains_set, keywords):
    db_path = db.find_db_file(profile_dir, HISTORY_DB)
    if not db_path:
        return None, None, None
    return db_path, domains_set, keywords


def _load_matches(db_path, domains_set, keywords):
    rows = db.read_rows(db_path, "SELECT id, url FROM urls")
    out = []
    for r in rows:
        m = matched_by(r["url"], domains_set, keywords)
        if m:
            out.append({"id": r["id"], "url": r["url"], "matched_by": m})
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
    """Return matched history entries as [{url, matched_by}, ...]."""
    db_path, dset, kws = _prep(profile_dir, domains_set, keywords)
    if not db_path or (not dset and not kws):
        return []
    return [
        {"url": m["url"], "matched_by": m["matched_by"]}
        for m in _load_matches(db_path, dset, kws)
    ]


def clean(profile_dir, domains_set, keywords):
    """Delete matching URLs and their visits. Browsers must be closed."""
    db_path, dset, kws = _prep(profile_dir, domains_set, keywords)
    if not db_path or (not dset and not kws):
        return 0
    ids = [m["id"] for m in _load_matches(db_path, dset, kws)]
    if not ids:
        return 0
    total = 0
    for chunk in _chunks(ids):
        marks = ",".join("?" * len(chunk))
        ids_t = tuple(chunk)
        stmts = [
            (f"DELETE FROM visits WHERE url IN ({marks})", ids_t),
        ]
        rows, err = db.execute_write(db_path, stmts)
        total += rows
        if err and "no such table: visits" not in (err or ""):
            # don't abort on missing visits table; try urls anyway
            pass
        rows, err = db.execute_write(db_path, [(f"DELETE FROM urls WHERE id IN ({marks})", ids_t)])
        total += rows
    db.vacuum_db(db_path)
    return total