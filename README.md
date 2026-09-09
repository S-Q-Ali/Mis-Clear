# Mis-Clear

**Windows Online Activity Trace Cleaner**

Mis-Clear helps you wipe traces of specific websites (e.g. accidentally visited adult sites) from your browsers — history, cookies, cache, and autofill — so they don't show up in address-bar suggestions or your browsing history.

## Features

- **Multi-browser** — works with Google Chrome, Microsoft Edge, Brave, Opera, and Firefox
- **4 cleanup types** per browser:
  - History entries (SQLite)
  - Cookies (SQLite)
  - Autofill / address-bar suggestions (SQLite)
  - Cache files (disk)
- **Blocklist** — download the StevenBlack adult-content blocklist (76K+ domains)
- **Custom keywords** — add your own domains/terms
- **Scan mode** — preview matches before deleting anything
- **Safe** — requires browsers to be closed, confirmation before clean, DB `VACUUM` after delete

## Requirements

- Python 3.x (uses only the standard library — tkinter, sqlite3, urllib, shutil, os)
- No external dependencies

## Usage

```
python main.py
```

1. **Scan & Clean** tab: pick browsers, click **Scan** to preview matches, then **Clean** (after closing the browsers).
2. **Settings** tab: add custom keywords, download the blocklist, save defaults.

## Project layout

```
├── main.py                 # Entry point
├── requirements.txt        # (no external deps)
├── cleaner/
│   ├── engine.py           # Orchestrates cleanup across browsers
│   ├── browser_paths.py    # Detects installed browsers/profiles
│   ├── history_cleaner.py  # History SQLite cleanup
│   ├── cookie_cleaner.py   # Cookies SQLite cleanup
│   ├── cache_cleaner.py    # Cache file cleanup
│   ├── autofill_cleaner.py # Autofill SQLite cleanup
│   ├── blocklist_manager.py# StevenBlack blocklist download/load
│   └── processes.py        # Browser process / lock checks
├── gui/app.py              # tkinter GUI
└── utils/
    ├── config.py           # config.json load/save
    └── sqlite_helper.py    # safe SQLite helpers
```

## Privacy

Everything runs locally on your machine. The only network request is the optional, user-triggered blocklist download.
