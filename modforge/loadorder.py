from pathlib import Path

from modforge.plugin import find_plugin_file

BASE_MASTERS = ("Skyrim.esm", "Update.esm")
ALWAYS = {name.casefold() for name in BASE_MASTERS}
PLUGIN_SUFFIXES = {".esp", ".esm", ".esl"}


def read_text(path):
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    elif b"\x00" in raw[:200]:
        text = raw.decode("utf-16-le")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    return text.lstrip("\ufeff")


def _plugin_name(token):
    token = token.strip()
    if token.startswith("*"):
        token = token[1:].strip()
    token = token.replace("\\", "/")
    return Path(token).name


def parse_plugins_txt(text):
    enabled = []
    disabled = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        on = raw.startswith("*")
        name = _plugin_name(raw)
        if not name:
            continue
        (enabled if on else disabled).append(name)
    return enabled, disabled


def parse_loadorder_txt(text):
    names = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        name = _plugin_name(raw)
        if name:
            names.append(name)
    return names


def merge_order(enabled, disabled, load_names, plugins_present):
    disabled_keys = {name.casefold() for name in disabled}
    enabled_keys = {name.casefold() for name in enabled}
    if load_names:
        out = []
        seen = set()
        for name in load_names:
            key = name.casefold()
            if key in seen or key in disabled_keys:
                continue
            if not plugins_present or key in enabled_keys or key in ALWAYS:
                out.append(name)
                seen.add(key)
        if plugins_present:
            for name in enabled:
                key = name.casefold()
                if key not in seen:
                    out.append(name)
                    seen.add(key)
        return out
    return list(enabled)


def scan_data_plugins(data_dir):
    data_dir = Path(data_dir)
    files = []
    if not data_dir.is_dir():
        return files
    for child in data_dir.iterdir():
        if child.is_file() and child.suffix.lower() in PLUGIN_SUFFIXES:
            files.append(child.name)
    special = {
        "skyrim.esm": 0,
        "update.esm": 1,
        "dawnguard.esm": 2,
        "hearthfires.esm": 3,
        "dragonborn.esm": 4,
    }
    rank = {".esm": 0, ".esl": 1, ".esp": 2}

    def sort_key(name):
        ext = Path(name).suffix.lower()
        return (rank.get(ext, 9), special.get(name.casefold(), 10), name.casefold())

    files.sort(key=sort_key)
    return files


def prepend_base(names, data_dir, disabled, search_dirs):
    disabled_keys = {name.casefold() for name in disabled}
    existing = {name.casefold() for name in names}
    folders = [data_dir, *search_dirs]
    front = []
    for base in BASE_MASTERS:
        key = base.casefold()
        if key in existing or key in disabled_keys:
            continue
        if find_plugin_file(base, folders) is not None:
            front.append(base)
    return front + names


def read_order(data_dir, plugins_path, loadorder_path, search_dirs=None):
    search_dirs = list(search_dirs or [])
    enabled = []
    disabled = []
    plugins_present = plugins_path is not None and Path(plugins_path).is_file()
    if plugins_present:
        enabled, disabled = parse_plugins_txt(read_text(plugins_path))
    load_names = None
    if loadorder_path is not None and Path(loadorder_path).is_file():
        load_names = parse_loadorder_txt(read_text(loadorder_path))
    if plugins_present or load_names is not None:
        names = merge_order(enabled, disabled, load_names, plugins_present)
        names = prepend_base(names, data_dir, disabled, search_dirs)
        if plugins_present and load_names is not None:
            source = "plugins.txt+loadorder.txt"
        elif plugins_present:
            source = "plugins.txt"
        else:
            source = "loadorder.txt"
        return names, source
    names = scan_data_plugins(data_dir)
    names = prepend_base(names, data_dir, [], search_dirs)
    return names, "directory"
