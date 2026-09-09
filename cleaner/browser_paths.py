import os


def _localappdata():
    return os.environ.get("LOCALAPPDATA", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local"))


def _roaming():
    return os.environ.get("APPDATA", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Roaming"))


def _chromium_profiles(user_data_root):
    """Return profile dirs under a Chromium 'User Data' root that hold a History DB."""
    if not user_data_root or not os.path.isdir(user_data_root):
        return []
    out = []
    for name in os.listdir(user_data_root):
        p = os.path.join(user_data_root, name)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "History")):
            out.append(p)
    return out


def _firefox_profiles():
    root = os.path.join(_roaming(), "Mozilla", "Firefox", "Profiles")
    if not os.path.isdir(root):
        return []
    return [os.path.join(root, name) for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))]


class BrowserInfo:
    def __init__(self, key, name, base_dir):
        self.key = key
        self.name = name
        self.base_dir = base_dir

    @property
    def exists(self):
        return bool(self.base_dir) and os.path.isdir(self.base_dir)


def detect_browsers():
    """Return list of BrowserInfo only for installed browsers (dir exists)."""
    local = _localappdata()
    roaming = _roaming()

    specs = [
        # Chromium: base_dir is the "User Data" root
        BrowserInfo("chrome", "Google Chrome", os.path.join(local, "Google", "Chrome", "User Data")),
        BrowserInfo("edge", "Microsoft Edge", os.path.join(local, "Microsoft", "Edge", "User Data")),
        BrowserInfo("brave", "Brave", os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data")),
        # Opera: base_dir IS a profile dir (no nested User Data)
        BrowserInfo("opera", "Opera", os.path.join(roaming, "Opera Software", "Opera Stable")),
    ]
    detected = [b for b in specs if b.exists]

    ff_root = os.path.join(roaming, "Mozilla", "Firefox")
    if os.path.isdir(ff_root):
        detected.append(BrowserInfo("firefox", "Mozilla Firefox", ff_root))

    return detected


def chrome_profiles(browser):
    return _chromium_profiles(browser.base_dir)


def firefox_profiles(browser):
    return _firefox_profiles()