from cleaner import (
    browser_paths,
    history_cleaner,
    cookie_cleaner,
    cache_cleaner,
    autofill_cleaner,
)


def _domains_for(keywords, blocklist):
    """Combine custom keywords + blocklist into one match set."""
    domains = set(blocklist)
    for kw in keywords:
        if kw:
            domains.add(kw)
    return domains


def scan_all(keywords, blocklist, browsers):
    """Return a list of result dicts per browser/profile."""
    domains_set = _domains_for(keywords, blocklist)
    results = []
    for browser in browsers:
        if browser.key == "firefox":
            profiles = browser_paths.firefox_profiles(browser)
            for prof in profiles:
                results.append(_scan_profile(browser, prof, domains_set, keywords))
        else:
            profiles = browser_paths.chrome_profiles(browser)
            if not profiles:
                profiles = [browser.base_dir]
            for prof in profiles:
                results.append(_scan_profile(browser, prof, domains_set, keywords))
    return results


def _scan_profile(browser, profile_dir, domains_set, keywords):
    hist = history_cleaner.scan(profile_dir, domains_set, keywords)
    cook = cookie_cleaner.scan(profile_dir, domains_set, keywords)
    auto = autofill_cleaner.scan(profile_dir, domains_set, keywords)
    cache_bytes = cache_cleaner.scan(profile_dir, keywords)
    return {
        "browser": browser.name,
        "profile": profile_dir,
        "history": hist,
        "cookies": cook,
        "autofill": auto,
        "cache_bytes": cache_bytes,
    }


def details_profile(browser, profile_dir, keywords, blocklist):
    """Return the actual matched items for a single profile."""
    domains_set = _domains_for(keywords, blocklist)
    return {
        "browser": browser.name,
        "profile": profile_dir,
        "history": history_cleaner.details(profile_dir, domains_set, keywords),
        "cookies": cookie_cleaner.details(profile_dir, domains_set, keywords),
        "autofill": autofill_cleaner.details(profile_dir, domains_set, keywords),
        "cache_bytes": cache_cleaner.scan(profile_dir, keywords),
    }


def clean_all(keywords, blocklist, browsers):
    """Run cleanup, returns (summary_items, total_counts)."""
    domains_set = _domains_for(keywords, blocklist)
    summary = []
    totals = {"history": 0, "cookies": 0, "autofill": 0, "cache_bytes": 0}
    for browser in browsers:
        if browser.key == "firefox":
            profiles = browser_paths.firefox_profiles(browser)
            for prof in profiles:
                _clean_profile(browser, prof, domains_set, keywords, summary, totals)
        else:
            profiles = browser_paths.chrome_profiles(browser)
            if not profiles:
                profiles = [browser.base_dir]
            for prof in profiles:
                _clean_profile(browser, prof, domains_set, keywords, summary, totals)
    return summary, totals


def _clean_profile(browser, profile_dir, domains_set, keywords, summary, totals):
    h = history_cleaner.clean(profile_dir, domains_set, keywords)
    c = cookie_cleaner.clean(profile_dir, domains_set, keywords)
    a = autofill_cleaner.clean(profile_dir, domains_set, keywords)
    cb = cache_cleaner.clean(profile_dir, keywords)
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