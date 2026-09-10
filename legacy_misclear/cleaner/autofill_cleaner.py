from utils import sqlite_helper as db
from cleaner.matching import matched_by

WEB_DATA_DB = "Web Data"
FIREFOX_FORMHISTORY_DB = "formhistory.sqlite"

_CHUNK = 500


def _locate(profile_dir):
    path = db.find_db_file(profile_dir, WEB_DATA_DB)
    if path:
        return path, "chromium"
    path = db.find_db_file(profile_dir, FIREFOX_FORMHISTORY_DB)
    if path:
        return path, "firefox"
    return None, None


def _load_matches(db_path, schema, domains_set, keywords):
    out = []
    if schema == "firefox":
        # moz_formhistory has NO url column: blocklist cannot apply,
        # so match custom keywords only against fieldname + value.
        rows = db.read_rows(db_path, "SELECT id, fieldname, value FROM moz_formhistory")
        for r in rows:
            hay = f"{r['fieldname']} {r['value']}".strip()
            m = matched_by(hay, set(), keywords)
            if m:
                out.append(
                    {
                        "pk": r["id"],
                        "url": hay,
                        "name": r["fieldname"],
                        "matched_by": m,
                    }
                )
    else:
        rows = db.read_rows(db_path, "SELECT rowid, url, name FROM autofill")
        for r in rows:
            m = matched_by(r["url"], domains_set, keywords)
            if m:
                out.append(
                    {
                        "pk": r["rowid"],
                        "url": r["url"],
                        "name": r["name"],
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
    """Return matched autofill entries as [{url, name, matched_by}, ...]."""
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return []
    return [
        {
            "url": m["url"],
            "name": m["name"],
            "matched_by": m["matched_by"],
        }
        for m in _load_matches(db_path, schema, domains_set, keywords)
    ]


def clean(profile_dir, domains_set, keywords):
    """Delete matching autofill. Chromium: autofill/rowid. Firefox: moz_formhistory/id."""
    db_path, schema = _locate(profile_dir)
    if not db_path or (not domains_set and not keywords):
        return 0
    pks = [m["pk"] for m in _load_matches(db_path, schema, domains_set, keywords)]
    if not pks:
        return 0
    table = "autofill" if schema == "chromium" else "moz_formhistory"
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