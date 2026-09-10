"""Automated tests for Mis-Clear cleaners using synthetic browser DBs.

Run: python tests\test_cleaners.py
Creates temp fake browser profiles and verifies scan/clean behaviour.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleaner import (  # noqa: E402
    browser_paths,
    cache_cleaner,
    cookie_cleaner,
    history_cleaner,
    autofill_cleaner,
)
from cleaner.matching import matches, matched_by  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def make_history(profile):
    dbp = os.path.join(profile, "History")
    conn = sqlite3.connect(dbp)
    conn.executescript(
        """
        CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER);
        CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER);
        CREATE TABLE visit_source (id INTEGER PRIMARY KEY, visit_id INTEGER);
        """
    )
    conn.execute("INSERT INTO urls (url,title,visit_count) VALUES ('https://pornhub.com/a','P',1)")
    conn.execute("INSERT INTO urls (url,title,visit_count) VALUES ('https://www.pornhub.com/v','P2',1)")
    conn.execute("INSERT INTO urls (url,title,visit_count) VALUES ('https://google.com','G',2)")
    conn.execute("INSERT INTO urls (url,title,visit_count) VALUES ('https://xvideos.com/v','X',1)")
    conn.execute("INSERT INTO visits (url) VALUES (1)")
    conn.execute("INSERT INTO visits (url) VALUES (2)")
    conn.execute("INSERT INTO visits (url) VALUES (4)")
    conn.commit()
    conn.close()
    return dbp


def make_cookies(profile):
    dbp = os.path.join(profile, "Cookies")
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
    conn.execute("INSERT INTO cookies VALUES ('xvideos.com','sid')")
    conn.execute("INSERT INTO cookies VALUES ('gmail.com','lsid')")
    conn.commit()
    conn.close()
    return dbp


def make_autofill(profile):
    dbp = os.path.join(profile, "Web Data")
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE autofill (url TEXT, name TEXT)")
    conn.execute("INSERT INTO autofill VALUES ('https://pornhub.com/search','q1')")
    conn.execute("INSERT INTO autofill VALUES ('https://maps.google.com','q2')")
    conn.commit()
    conn.close()
    return dbp


def make_cache(profile):
    cdir = os.path.join(profile, "Cache")
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "f1.dat"), "wb") as f:
        f.write(b"x" * 1000)
    with open(os.path.join(cdir, "f2.dat"), "wb") as f:
        f.write(b"y" * 500)
    return cdir


def make_firefox_places(profile):
    dbp = os.path.join(profile, "places.sqlite")
    conn = sqlite3.connect(dbp)
    conn.executescript(
        """
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT);
        CREATE TABLE moz_historyvisits (id INTEGER PRIMARY KEY, place_id INTEGER);
        CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, fk INTEGER);
        """
    )
    conn.execute("INSERT INTO moz_places (url,title) VALUES ('https://pornhub.com/p','P')")
    conn.execute("INSERT INTO moz_places (url,title) VALUES ('https://xvideos.com/v','X')")
    conn.execute("INSERT INTO moz_places (url,title) VALUES ('https://www.xvideos.com/bookmarked','B')")
    conn.execute("INSERT INTO moz_places (url,title) VALUES ('https://news.example.com','N')")
    conn.execute("INSERT INTO moz_historyvisits (place_id) VALUES (1)")
    conn.execute("INSERT INTO moz_historyvisits (place_id) VALUES (2)")
    conn.execute("INSERT INTO moz_historyvisits (place_id) VALUES (3)")
    conn.execute("INSERT INTO moz_bookmarks (fk) VALUES (3)")
    conn.commit()
    conn.close()
    return dbp


def make_firefox_cookies(profile):
    dbp = os.path.join(profile, "cookies.sqlite")
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, host TEXT, name TEXT)")
    conn.execute("INSERT INTO moz_cookies (host,name) VALUES ('xvideos.com','sid')")
    conn.execute("INSERT INTO moz_cookies (host,name) VALUES ('gmail.com','lsid')")
    conn.commit()
    conn.close()
    return dbp


def make_firefox_formhistory(profile):
    dbp = os.path.join(profile, "formhistory.sqlite")
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE moz_formhistory (id INTEGER PRIMARY KEY, fieldname TEXT, value TEXT)")
    conn.execute("INSERT INTO moz_formhistory (fieldname,value) VALUES ('email','test@pornhub.com')")
    conn.execute("INSERT INTO moz_formhistory (fieldname,value) VALUES ('city','Lahore')")
    conn.commit()
    conn.close()
    return dbp


def db_count(path, table):
    if not os.path.isfile(path):
        return -1
    conn = sqlite3.connect(path)
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return n


def test_matching():
    print("matching")
    check("keyword substring matches", matches("https://pornhub.com/a", set(), ["pornhub"]))
    check("exact domain matches", matches("https://pornhub.com/a", {"pornhub.com"}, []))
    check("subdomain matches domain", matches("https://m.pornhub.com/a", {"pornhub.com"}, []))
    check("www prefix matches", matches("https://www.pornhub.com/a", {"pornhub.com"}, []))
    check("no false positive", not matches("https://example.com/a", {"pornhub.com"}, ["xvideo"]))
    check("matched_by returns keyword", matched_by("https://pornhub.com/a", set(), ["pornhub"]) == "pornhub")
    check("matched_by returns domain", matched_by("https://pornhub.com/a", {"pornhub.com"}, []) == "pornhub.com")
    check("matched_by subdomain", matched_by("https://m.pornhub.com/a", {"pornhub.com"}, []) == "pornhub.com")
    check("matched_by case-insensitive", matched_by("HTTPS://PornHub.COM/a", {"pornhub.com"}, []) == "pornhub.com")
    check("matched_by None when no match", matched_by("https://example.com", {"pornhub.com"}, ["xvideo"]) is None)


def test_history():
    print("history_cleaner")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_hist")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    dbp = make_history(profile)
    check("scan finds 3 matches (pornhub x2, xvideos)", history_cleaner.scan(profile, {"pornhub.com", "xvideos.com"}, []) == 3)
    det = history_cleaner.details(profile, {"pornhub.com", "xvideos.com"}, [])
    check("details returns 3 items", len(det) == 3)
    check("details has matched_by per item", all("matched_by" in d and d["matched_by"] for d in det))
    check("details matching domain recorded", any(d["url"].startswith("https://pornhub.com") and d["matched_by"] == "pornhub.com" for d in det))
    check("scan 0 for no-match", history_cleaner.scan(profile, {"nonexistent.com"}, []) == 0)
    rows = history_cleaner.clean(profile, {"pornhub.com", "xvideos.com"}, [])
    check("clean removes 6 rows (3 urls + 3 visits)", rows == 6)
    check("only google url remains", db_count(dbp, "urls") == 1)
    check("no visits remain", db_count(dbp, "visits") == 0)
    shutil.rmtree(profile, ignore_errors=True)


def test_cookies():
    print("cookie_cleaner")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_cook")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    dbp = make_cookies(profile)
    check("scan finds 1 xvideos cookie", cookie_cleaner.scan(profile, {"xvideos.com"}, []) == 1)
    det = cookie_cleaner.details(profile, {"xvideos.com"}, [])
    check("details returns 1 cookie", len(det) == 1 and det[0]["host"] == "xvideos.com")
    check("cookie details include name+matched_by", det[0]["name"] == "sid" and det[0]["matched_by"] == "xvideos.com")
    rows = cookie_cleaner.clean(profile, {"xvideos.com"}, [])
    check("clean removes 1 cookie", rows == 1)
    check("gmail cookie remains", db_count(dbp, "cookies") == 1)
    shutil.rmtree(profile, ignore_errors=True)


def test_autofill():
    print("autofill_cleaner")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_auto")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    dbp = make_autofill(profile)
    check("scan finds 1 pornhub autofill", autofill_cleaner.scan(profile, {"pornhub.com"}, []) == 1)
    det = autofill_cleaner.details(profile, {"pornhub.com"}, [])
    check("details returns 1 autofill", len(det) == 1 and det[0]["url"].startswith("https://pornhub.com"))
    check("autofill details include name+matched_by", det[0]["name"] == "q1" and det[0]["matched_by"] == "pornhub.com")
    rows = autofill_cleaner.clean(profile, {"pornhub.com"}, [])
    check("clean removes 1 autofill", rows == 1)
    check("google autofill remains", db_count(dbp, "autofill") == 1)
    shutil.rmtree(profile, ignore_errors=True)


def test_firefox_history():
    print("history_cleaner (firefox places)")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_ff_hist")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    dbp = make_firefox_places(profile)
    check("ff scan finds 3 matches", history_cleaner.scan(profile, {"pornhub.com", "xvideos.com"}, []) == 3)
    det = history_cleaner.details(profile, {"pornhub.com", "xvideos.com"}, [])
    check("ff details returns 3 with matched_by", len(det) == 3 and all("matched_by" in d for d in det))
    rows = history_cleaner.clean(profile, {"pornhub.com", "xvideos.com"}, [])
    check("ff clean removes 5 rows (3 visits + 2 places)", rows == 5)
    check("ff bookmarked place kept", db_count(dbp, "moz_places") == 2)
    check("ff visits all cleared (visit history removed even for bookmarked)", db_count(dbp, "moz_historyvisits") == 0)
    shutil.rmtree(profile, ignore_errors=True)


def test_firefox_cookies():
    print("cookie_cleaner (firefox moz_cookies)")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_ff_cook")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    dbp = make_firefox_cookies(profile)
    check("ff cookie scan finds 1", cookie_cleaner.scan(profile, {"xvideos.com"}, []) == 1)
    det = cookie_cleaner.details(profile, {"xvideos.com"}, [])
    check("ff cookie details correct", det and det[0]["host"] == "xvideos.com" and det[0]["name"] == "sid")
    rows = cookie_cleaner.clean(profile, {"xvideos.com"}, [])
    check("ff clean removes 1 cookie", rows == 1 and db_count(dbp, "moz_cookies") == 1)
    shutil.rmtree(profile, ignore_errors=True)


def test_firefox_autofill():
    print("autofill_cleaner (firefox moz_formhistory)")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_ff_auto")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    dbp = make_firefox_formhistory(profile)
    check("ff autofill keyword scan finds 1", autofill_cleaner.scan(profile, set(), ["pornhub"]) == 1)
    check("ff autofill ignores blocklist (no url)", autofill_cleaner.scan(profile, {"xvideos.com"}, []) == 0)
    det = autofill_cleaner.details(profile, set(), ["pornhub"])
    check("ff autofill details correct", len(det) == 1 and det[0]["matched_by"] == "pornhub")
    rows = autofill_cleaner.clean(profile, set(), ["pornhub"])
    check("ff clean removes 1 form entry", rows == 1 and db_count(dbp, "moz_formhistory") == 1)
    shutil.rmtree(profile, ignore_errors=True)


def test_cache():
    print("cache_cleaner")
    profile = os.path.join(tempfile.gettempdir(), "mc_test_cache")
    shutil.rmtree(profile, ignore_errors=True)
    os.makedirs(profile, exist_ok=True)
    make_cache(profile)
    size = cache_cleaner.scan(profile, [])
    check("scan reports 1500 bytes cache", size == 1500)
    freed = cache_cleaner.clean(profile, [])
    check("clean frees 1500 bytes", freed == 1500)
    cdir = os.path.join(profile, "Cache")
    remaining = os.listdir(cdir) if os.path.isdir(cdir) else []
    check("cache dir empty after clean", remaining == [])
    shutil.rmtree(profile, ignore_errors=True)


def test_browser_detection():
    print("browser_paths")
    browsers = browser_paths.detect_browsers()
    check("detect_browsers returns a list", isinstance(browsers, list))
    for b in browsers:
        check(f"BrowserInfo {b.name} has key", bool(b.key))


if __name__ == "__main__":
    test_matching()
    test_browser_detection()
    test_history()
    test_cookies()
    test_autofill()
    test_firefox_history()
    test_firefox_cookies()
    test_firefox_autofill()
    test_cache()
    print(f"\n===== RESULT: {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)