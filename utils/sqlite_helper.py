import copy
import os
import shutil
import sqlite3
import tempfile


def find_db_file(profile_dir, db_name):
    candidate = os.path.join(profile_dir, db_name)
    return candidate if os.path.isfile(candidate) else None


def make_working_copy(db_path):
    """Copy a browser DB to temp so the live process never holds it open."""
    if not db_path or not os.path.isfile(db_path):
        return None
    tmp_dir = os.path.join(tempfile.gettempdir(), "mis_clear")
    os.makedirs(tmp_dir, exist_ok=True)
    dest = os.path.join(tmp_dir, f"{os.path.basename(db_path)}.work")
    try:
        shutil.copy2(db_path, dest)
        return dest
    except OSError:
        return None


def read_rows(db_path, sql, params=()):
    if not db_path or not os.path.isfile(db_path):
        return []
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.DatabaseError:
        return []
    finally:
        if conn:
            conn.close()


def execute_write(db_path, statements):
    """statements: iterable of (sql, params). Returns (rows_affected, error)."""
    if not db_path or not os.path.isfile(db_path):
        return 0, None
    conn = None
    total = 0
    try:
        conn = sqlite3.connect(db_path)
        for sql, params in statements:
            cur = conn.execute(sql, params)
            total += cur.rowcount
        conn.commit()
        return total, None
    except sqlite3.DatabaseError as e:
        return total, str(e)
    finally:
        if conn:
            conn.close()


def vacuum_db(db_path):
    if not db_path or not os.path.isfile(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
    except sqlite3.DatabaseError:
        pass
