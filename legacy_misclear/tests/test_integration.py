"""Integration tests: config, blocklist parser, engine scan, GUI build."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def test_config():
    print("utils.config round-trip")
    from utils import config
    path = config.config_path()
    if os.path.isfile(path):
        os.remove(path)
    cfg = config.load_config()
    check("defaults loaded with keywords", isinstance(cfg.get("keywords"), list))
    cfg["keywords"] = ["a.com", "b.com"]
    config.save_config(cfg)
    cfg2 = config.load_config()
    check("saved keywords persist", cfg2["keywords"] == ["a.com", "b.com"])


def test_blocklist_parser():
    print("blocklist_manager parser")
    from cleaner import blocklist_manager as bm
    sample = os.path.join(tempfile.gettempdir(), "mc_sample_hosts.txt")
    with open(sample, "w", encoding="utf-8") as f:
        f.write("0.0.0.0 site1.com\n")
        f.write("# comment line\n")
        f.write("127.0.0.1 site2.net\n")
        f.write("\n")
        f.write("0.0.0.0 www.site3.org\n")
    domains = []
    for line in open(sample, encoding="utf-8"):
        m = bm._domain_re.match(line.strip())
        if m:
            domains.append(m.group(1).lower())
    check("parses 3 domains, skips comment/blank", domains == ["site1.com", "site2.net", "www.site3.org"])


def test_engine_domains():
    print("engine._domains_for")
    from cleaner import engine
    combined = engine._domains_for(["pornhub"], ["adultblock.com"])
    check("domains combine keywords+blocklist as set",
          "adultblock.com" in combined and "pornhub" in combined)


def test_engine_synthetic_scan():
    print("engine.scan_all (synthetic profiles)")
    from cleaner import engine

    tmp = os.path.join(tempfile.gettempdir(), "mc_tmp_profiles")
    shutil.rmtree(tmp, ignore_errors=True)
    base = os.path.join(tmp, "User Data")
    os.makedirs(base, exist_ok=True)
    prof = os.path.join(base, "Default")
    os.makedirs(prof, exist_ok=True)

    import sqlite3
    conn = sqlite3.connect(os.path.join(prof, "History"))
    conn.executescript(
        "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT);"
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER);"
    )
    conn.execute("INSERT INTO urls (url) VALUES ('https://adultsite.org/x')")
    conn.commit()
    conn.close()

    # base_dir mimics detect_browsers: points at the "User Data" root
    from cleaner.browser_paths import BrowserInfo
    fake = BrowserInfo("chrome", "FakeChrome", base)
    results = engine.scan_all([], ["adultsite.org"], [fake])
    check("synthetic scan finds 1 match", results and results[0]["history"] == 1)


def test_engine_details():
    print("engine.details_profile (synthetic profile)")
    from cleaner import engine

    tmp = os.path.join(tempfile.gettempdir(), "mc_tmp_details")
    shutil.rmtree(tmp, ignore_errors=True)
    prof = tmp
    os.makedirs(prof, exist_ok=True)

    import sqlite3
    conn = sqlite3.connect(os.path.join(prof, "History"))
    conn.executescript(
        "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT);"
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER);"
    )
    conn.execute("INSERT INTO urls (url) VALUES ('https://adultsite.org/x')")
    conn.execute("INSERT INTO urls (url) VALUES ('https://okay.example.com')")
    conn.commit()
    conn.close()

    from cleaner.browser_paths import BrowserInfo
    fake = BrowserInfo("chrome", "FakeChrome", tmp)
    detail = engine.details_profile(fake, prof, [], ["adultsite.org"])
    check("details_profile returns history list", isinstance(detail["history"], list))
    check("details_profile matched_by set", detail["history"] and detail["history"][0]["matched_by"] == "adultsite.org")
    check("details_profile excludes other rows", len(detail["history"]) == 1)
    shutil.rmtree(tmp, ignore_errors=True)


def test_real_scan_no_crash():
    print("engine.scan_all on real browsers (no delete)")
    from cleaner import browser_paths, engine
    browsers = browser_paths.detect_browsers()
    results = engine.scan_all(["definitely-not-a-real-site-xyz"], [], browsers)
    check("real scan returns results", isinstance(results, list))
    for r in results:
        for k in ("history", "cookies", "autofill", "cache_bytes"):
            check(f"  field {k} present", k in r)


def test_gui_builds():
    print("gui builds + pump (no freeze)")
    import tkinter as tk
    import time
    from gui.app import MisClearApp
    root = tk.Tk()
    root.withdraw()
    app = MisClearApp(root)
    deadline = time.time() + 1.5
    while time.time() < deadline:
        root.update()
        time.sleep(0.02)
    check("MisClearApp created + event loop pumps", app is not None)
    root.destroy()


if __name__ == "__main__":
    test_config()
    test_blocklist_parser()
    test_engine_domains()
    test_engine_synthetic_scan()
    test_engine_details()
    test_real_scan_no_crash()
    test_gui_builds()
    print(f"\n===== RESULT: {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)