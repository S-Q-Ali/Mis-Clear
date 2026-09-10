from utils import sqlite_helper as db
from cleaner.matching import matched_by

HISTORY_DB = "History"
FIREFOX_PLACES_DB = "places.sqlite"

_CHUNK = 500


def _locate(profile_dir):
    path = db.find_db_file(profile_dir, HISTORY_DB)
    if path:
        return path, "chromium"
    path = db.find_db_file(profile_dir, FIREFOX_PLACES_DB)
    if path:
        return path, "firefox"
    return None, None


def _load_matches(db_path, schema, domains_set, keywords):
    table = "urls" if schema == "chromium" else "moz_places"
    rows = db.read_rows(db_path, f"SELECT id, url FROM {table}")
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
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return 0
    return len(_load_matches(db_path, schema, domains_set, keywords))


def details(profile_dir, domains_set, keywords):
    """Return matched history entries as [{url, matched_by}, ...]."""
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return []
    return [
        {"url": m["url"], "matched_by": m["matched_by"]}
        for m in _load_matches(db_path, schema, domains_set, keywords)
    ]


def clean(profile_dir, domains_set, keywords):
    """Delete matching URLs (+visits). Chromium: urls/visits. Firefox:
    moz_places/moz_historyvisits, keeping bookmarked places. Browsers closed."""
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return 0
    ids = [m["id"] for m in _load_matches(db_path, schema, domains_set, keywords)]
    if not ids:
        return 0
    total = 0
    for chunk in _chunks(ids):
        marks = ",".join("?" * len(chunk))
        ids_t = tuple(chunk)
        if schema == "firefox":
            rows, err = db.execute_write(
                db_path, [(f"DELETE FROM moz_historyvisits WHERE place_id IN ({marks})", ids_t)]
            )
            total += rows
            delete_places = (
                "DELETE FROM moz_places WHERE id IN ({marks}) "
                "AND id NOT IN (SELECT fk FROM moz_bookmarks WHERE fk IS NOT NULL)"
            ).format(marks=marks)
            rows, err = db.execute_write(db_path, [(delete_places, ids_t)])
            total += rows
        else:
            stmts = [(f"DELETE FROM visits WHERE url IN ({marks})", ids_t)]
            rows, err = db.execute_write(db_path, stmts)
            total += rows
            if err and "no such table: visits" not in (err or ""):
                pass
            rows, err = db.execute_write(db_path, [(f"DELETE FROM urls WHERE id IN ({marks})", ids_t)])
            total += rows
    db.vacuum_db(db_path)
    return total