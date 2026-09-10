import json
import os

DEFAULTS = {
    "keywords": ["porntube", "adult", "xxx", "sex"],
    "selected_browsers": ["chrome", "edge", "firefox", "brave", "opera"],
}


def config_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def load_config():
    path = config_path()
    if not os.path.isfile(path):
        return dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_config(cfg):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
