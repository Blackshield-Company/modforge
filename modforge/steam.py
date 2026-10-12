from dataclasses import dataclass
from pathlib import Path

GAME_DIR = {
    489830: "Skyrim Special Edition",
}

LOCAL_NAME = {
    489830: "Skyrim Special Edition",
}


@dataclass
class GamePaths:
    appid: int
    library: Path | None = None
    game: Path | None = None
    data: Path | None = None
    prefix: Path | None = None
    plugins_txt: Path | None = None
    loadorder_txt: Path | None = None


def parse_vdf(text):
    i = 0
    n = len(text)

    def skip():
        nonlocal i
        while i < n:
            if text[i] in " \t\r\n":
                i += 1
                continue
            if text.startswith("//", i):
                while i < n and text[i] not in "\r\n":
                    i += 1
                continue
            break

    def parse_string():
        nonlocal i
        skip()
        if i >= n:
            raise ValueError("unexpected end of vdf")
        if text[i] == '"':
            i += 1
            out = []
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    return "".join(out)
                out.append(ch)
                i += 1
            raise ValueError("unterminated string in vdf")
        start = i
        while i < n and text[i] not in " \t\r\n{}\"":
            i += 1
        if start == i:
            raise ValueError(f"unexpected character in vdf at {i}")
        return text[start:i]

    def parse_value():
        nonlocal i
        skip()
        if i < n and text[i] == "{":
            i += 1
            obj = {}
            while True:
                skip()
                if i >= n:
                    raise ValueError("unterminated object in vdf")
                if text[i] == "}":
                    i += 1
                    return obj
                key = parse_string()
                obj[key] = parse_value()
        return parse_string()

    skip()
    if i < n and text[i] == "{":
        return parse_value()
    key = parse_string()
    return {key: parse_value()}


def default_steam_roots():
    home = Path.home()
    return [
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
    ]


def _unique(paths):
    out = []
    seen = set()
    for path in paths:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def paths_from_vdf(vdf_path):
    text = vdf_path.read_text(encoding="utf-8-sig", errors="replace")
    data = parse_vdf(text)
    root = data
    if len(data) == 1 and isinstance(next(iter(data.values())), dict):
        root = next(iter(data.values()))
    paths = []
    if isinstance(root, dict):
        for key, val in root.items():
            if isinstance(val, dict) and isinstance(val.get("path"), str) and val["path"]:
                paths.append(Path(val["path"]))
            elif isinstance(val, str) and str(key).isdigit() and val:
                paths.append(Path(val))
    if vdf_path.parent.name == "steamapps":
        paths.append(vdf_path.parent.parent)
    return paths


def libraries_from(steam):
    steam = Path(steam)
    vdfs = []
    roots = []
    if steam.is_file() and steam.name == "libraryfolders.vdf":
        vdfs.append(steam)
    else:
        for rel in (Path("steamapps") / "libraryfolders.vdf", Path("libraryfolders.vdf")):
            candidate = steam / rel
            if candidate.is_file():
                vdfs.append(candidate)
        if (steam / "steamapps").is_dir():
            roots.append(steam)
        if steam.name == "steamapps":
            roots.append(steam.parent)
    for vdf in vdfs:
        try:
            roots.extend(paths_from_vdf(vdf))
        except (OSError, ValueError):
            continue
    return _unique(roots)


def steamapps_dir(library):
    library = Path(library)
    if (library / "steamapps").is_dir():
        return library / "steamapps"
    if library.name == "steamapps":
        return library
    return library / "steamapps"


def read_installdir(manifest):
    if not manifest.is_file():
        return None
    try:
        data = parse_vdf(manifest.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, ValueError):
        return None
    state = data.get("AppState", data)
    if isinstance(state, dict) and state.get("installdir"):
        return state["installdir"]
    return None


def find_game(libraries, appid):
    fallback = None
    for library in libraries:
        apps = steamapps_dir(library)
        installdir = read_installdir(apps / f"appmanifest_{appid}.acf")
        if installdir is None and appid in GAME_DIR:
            installdir = GAME_DIR[appid]
        if not installdir:
            continue
        game = apps / "common" / installdir
        data = game / "Data"
        manifest = apps / f"appmanifest_{appid}.acf"
        if data.is_dir():
            return library, game, data
        if game.is_dir() or manifest.is_file():
            fallback = (library, game, data if data.is_dir() else None)
    return fallback if fallback is not None else (None, None, None)


def find_prefix(libraries, appid, preferred=None):
    ordered = []
    if preferred is not None:
        ordered.append(preferred)
    ordered.extend(libraries)
    seen = set()
    for library in ordered:
        if library is None:
            continue
        key = str(library)
        if key in seen:
            continue
        seen.add(key)
        pref = steamapps_dir(library) / "compatdata" / str(appid)
        if pref.is_dir():
            return pref
    return None


def normalize_prefix(path):
    path = Path(path)
    if path.name.lower() == "pfx":
        return path.parent
    return path


def find_lists_in_prefix(prefix, appid):
    if prefix is None:
        return None, None
    prefix = normalize_prefix(Path(prefix))
    wine = prefix / "pfx" if (prefix / "pfx").is_dir() else prefix
    users = wine / "drive_c" / "users"
    if not users.is_dir():
        return None, None
    known = LOCAL_NAME.get(appid)
    preferred = []
    fallback_dirs = []
    for user in sorted(users.iterdir(), key=lambda p: p.name.casefold()):
        if not user.is_dir() or user.name.casefold() == "public":
            continue
        local = user / "AppData" / "Local"
        if known:
            preferred.append(local / known)
            preferred.append(user / "Documents" / "My Games" / known)
        if local.is_dir():
            for child in sorted(local.iterdir(), key=lambda p: p.name.casefold()):
                if child.is_dir():
                    fallback_dirs.append(child)
    plugins = None
    loadorder = None

    def take(folder):
        nonlocal plugins, loadorder
        if plugins is None and (folder / "plugins.txt").is_file():
            plugins = folder / "plugins.txt"
        if loadorder is None and (folder / "loadorder.txt").is_file():
            loadorder = folder / "loadorder.txt"

    for folder in preferred:
        take(folder)
    if plugins is None or loadorder is None:
        for folder in fallback_dirs:
            take(folder)
            if plugins and loadorder:
                break
    return plugins, loadorder


def discover(appid, steam=None, prefix=None):
    libraries = []
    if steam is not None:
        libraries = libraries_from(steam)
    else:
        for root in default_steam_roots():
            if root.exists():
                libraries.extend(libraries_from(root))
        libraries = _unique(libraries)
    library, game, data = find_game(libraries, appid)
    ordered = [library] if library is not None else []
    ordered.extend(libraries)
    found_prefix = normalize_prefix(prefix) if prefix else find_prefix(ordered, appid)
    plugins_txt, loadorder_txt = find_lists_in_prefix(found_prefix, appid)
    return GamePaths(
        appid=appid,
        library=library,
        game=game,
        data=data,
        prefix=found_prefix,
        plugins_txt=plugins_txt,
        loadorder_txt=loadorder_txt,
    )
