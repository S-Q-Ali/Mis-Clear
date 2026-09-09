import os


def _folder_size(path):
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        return 0
    return total


def _cache_dirs(profile_dir):
    """Common chromium cache locations within a profile. Returns list of dirs."""
    candidates = [
        "Cache",
        "Code Cache",
        "GPUCache",
        "ShaderCache",
        "DawnCache",
        "GrShaderCache",
        "Service Worker/CacheStorage",
    ]
    out = []
    for c in candidates:
        p = os.path.join(profile_dir, c)
        if os.path.isdir(p):
            out.append(p)
    # Edge/Chrome also store under "Default"-level; already covered by profile_dir.
    return out


def scan(profile_dir, _domains):
    """Return total cache size in bytes for a profile (domains not needed for folder cache)."""
    total = 0
    for d in _cache_dirs(profile_dir):
        total += _folder_size(d)
    return total


def clean(profile_dir, _domains):
    """Delete contents of matching cache dirs. Returns freed bytes."""
    freed = 0
    for d in _cache_dirs(profile_dir):
        size = _folder_size(d)
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.isfile(p) or os.path.islink(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    import shutil
                    shutil.rmtree(p, ignore_errors=True)
            except (OSError, PermissionError):
                pass
        freed += size
    return freed
