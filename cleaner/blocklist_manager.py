import os
import re

# StevenBlack/hosts "porn-only" blocklist (76K+ adult domains)
BLOCKLIST_URL = (
    "https://raw.githubusercontent.com/StevenBlack/hosts/"
    "master/alternates/porn-only/hosts"
)

DEFAULT_KEYWORDS = [
    "pornhub",
    "xvideos",
    "xhamster",
    "redtube",
    "youporn",
    "adult",
    "sex",
    "xxx",
]

_domain_re = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1)\s+([^\s#]+)", re.IGNORECASE)


def default_blocklist_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blocklist.txt")


def download_blocklist(dest=None, timeout=30):
    """Download StevenBlack porn-only hosts and save domains (one per line)."""
    import urllib.request

    dest = dest or default_blocklist_path()
    domains = []
    try:
        with urllib.request.urlopen(BLOCKLIST_URL, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="ignore").strip()
                m = _domain_re.match(line)
                if m:
                    domains.append(m.group(1).lower())
    except Exception:
        return False, 0

    seen = set()
    uniq = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            uniq.append(d)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(uniq))
    return True, len(uniq)


def load_blocklist(path=None):
    """Load domains from blocklist file. Returns list (maybe empty)."""
    path = path or default_blocklist_path()
    if not os.path.isfile(path):
        return []
    domains = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            d = line.strip()
            if d:
                domains.append(d.lower())
    return domains
