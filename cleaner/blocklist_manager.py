import os
import re

# StevenBlack/hosts "porn-only" blocklist (76K+ adult domains)
# Primary: raw.githubusercontent.com. Fallback: official non-GitHub mirror.
BLOCKLIST_URLS = [
    "https://raw.githubusercontent.com/StevenBlack/hosts/"
    "master/alternates/porn-only/hosts",
    "http://sbc.io/hosts/alternates/porn-only/hosts",
    "https://sbc.io/hosts/alternates/porn-only/hosts",
]

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


def _parse_hosts_text(text):
    domains = []
    for raw in text.splitlines():
        line = raw.strip()
        m = _domain_re.match(line)
        if m:
            domains.append(m.group(1).lower())
    seen = set()
    uniq = []
    for d in domains:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def download_blocklist(urls=None, dest=None, timeout=30):
    """Download StevenBlack porn-only hosts and save domains (one per line).

    Tries each URL in order until one succeeds. Returns (success, domain_count).
    """
    import urllib.request

    urls = urls or BLOCKLIST_URLS
    dest = dest or default_blocklist_path()
    last_error = None
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mis-Clear/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            uniq = _parse_hosts_text(text)
            if uniq:
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                with open(dest, "w", encoding="utf-8") as f:
                    f.write("\n".join(uniq))
                return True, len(uniq)
        except Exception as e:  # noqa: BLE001
            last_error = e
            continue
    if last_error is not None:
        return False, str(last_error)
    return False, "no content"


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