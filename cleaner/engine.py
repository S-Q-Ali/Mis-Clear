from cleaner import (
    browser_paths,
    history_cleaner,
    cookie_cleaner,
    cache_cleaner,
    autofill_cleaner,
)


def _domains_for(keywords, blocklist):
    """Combine custom keywords + blocklist into one match set."""
    domains = list(keywords)
    for d in blocklist:
        if d not in domains:
            domains.append(d)
    return domains


def scan_all(keywords, blocklist, browsers):
    """Return a list of result dicts per browser/profile."""
    domains = _domains_for(keywords, blocklist)
    results = []
    for browser in browsers:
        if browser.key == "firefox":
            profiles = browser_paths.firefox_profiles(browser)
            for prof in profiles:
                results.append(_scan_profile(browser, prof, domains))
        else:
            profiles = browser_paths.chrome_profiles(browser)
            if not profiles:
                profiles = [browser.base_dir]
            for prof in profiles:
                results.append(_scan_profile(browser, prof, domains))
    return results


def _scan_profile(browser, profile_dir, domains):
    hist = history_cleaner.scan(profile_dir, domains)
    cook = cookie_cleaner.scan(profile_dir, domains)
    auto = autofill_cleaner.scan(profile_dir, domains)
    cache_bytes = cache_cleaner.scan(profile_dir, domains)
    return {
        "browser": browser.name,
        "profile": profile_dir,
        "history": hist,
        "cookies": cook,
        "autofill": auto,
        "cache_bytes": cache_bytes,
    }


def clean_all(keywords, blocklist, browsers):
    """Run cleanup, returns (summary_items, total_counts)."""
    domains = _domains_for(keywords, blocklist)
    summary = []
    totals = {"history": 0, "cookies": 0, "autofill": 0, "cache_bytes": 0}
    for browser in browsers:
        if browser.key == "firefox":
            profiles = browser_paths.firefox_profiles(browser)
            for prof in profiles:
                _clean_profile(browser, prof, domains, summary, totals)
        else:
            profiles = browser_paths.chrome_profiles(browser)
            if not profiles:
                profiles = [browser.base_dir]
            for prof in profiles:
                _clean_profile(browser, prof, domains, summary, totals)
    return summary, totals


def _clean_profile(browser, profile_dir, domains, summary, totals):
    h = history_cleaner.clean(profile_dir, domains)
    c = cookie_cleaner.clean(profile_dir, domains)
    a = autofill_cleaner.clean(profile_dir, domains)
    cb = cache_cleaner.clean(profile_dir, domains)
    totals["history"] += h
    totals["cookies"] += c
    totals["autofill"] += a
    totals["cache_bytes"] += cb
    summary.append(
        {
            "browser": browser.name,
            "profile": profile_dir,
            "history": h,
            "cookies": c,
            "autofill": a,
            "cache_bytes": cb,
        }
    )
