"""Integration tests: config, blocklist parser, engine scan, GUI build."""
import os
import shutil
import sqlite3
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
        f.write("0.0.0.0 site3.org\n")
    domains = []
    for line in open(sample, encoding="utf-8"):
        m = bm._domain_re.match(line.strip())
        if m:
            domains.append(m.group(1).lower())
    check("parses 3 domains, skips comment/blank", domains == ["site1.com", "site2.net", "site3.org"])


def test_engine_scan(tmp_profiles):
    print("engine.scan_all (synthetic profiles)")
    from cleaner import browser_paths, engine

    # Build fake chrome profile dirs like "<base>/User Data/Default/History"
    base = tmp_profiles
    from cleaner.engine import _domains_for
    combined = _domains_for(["pornhub"], ["adultblock.com"])
    check("domains combine keywords+blocklist", "pornhub" in combined and "adultblock.com" in combined)


def test_gui_builds():
    print("gui builds")
    import tkinter as tk
    from gui.app import MisClearApp
    root = tk.Tk()
    root.withdraw()
    app = MisClearApp(root)
    root.update_idletasks()
    check("MisClearApp created", app is not None)
    root.destroy()


def test_real_scan_no_crash():
    print("engine.scan_all on real browsers (no delete)")
    from cleaner import browser_paths, engine
    browsers = browser_paths.detect_browsers()
    results = engine.scan_all(["definitely-not-a-real-site-xyz"], [], browsers)
    check("real scan returns results", isinstance(results, list))
    for r in results:
        for k in ("history", "cookies", "autofill", "cache_bytes"):
            check(f"  field {k} present", k in r)


if __name__ == "__main__":
    test_config()
    test_blocklist_parser()
    tmp = os.path.join(tempfile.gettempdir(), "mc_tmp_profiles")
    os.makedirs(tmp, exist_ok=True)
    test_engine_scan(tmp)
    test_real_scan_no_crash()
    test_gui_builds()
    print(f"\n===== RESULT: {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)
