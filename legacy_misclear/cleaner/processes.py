import subprocess

# Map browser key -> typical process names
BROWSER_PROCESSES = {
    "chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "brave": ["brave.exe"],
    "opera": ["opera.exe"],
    "firefox": ["firefox.exe"],
}


def browser_running(browser_key):
    names = BROWSER_PROCESSES.get(browser_key, [])
    if not names:
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"], stderr=subprocess.DEVNULL, text=True
        )
    except Exception:
        return False
    for name in names:
        if name.lower() in out.lower():
            return True
    return False


def running_browsers(browsers):
    return [b for b in browsers if browser_running(b.key)]
