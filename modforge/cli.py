import argparse
import sys
from pathlib import Path

from modforge import __version__
from modforge.checks import analyze, collect_mod_roots, default_rules_path, load_rules
from modforge.loadorder import read_order
from modforge.report import render_json, render_text
from modforge.steam import discover, find_lists_in_prefix, normalize_prefix


def build_parser():
    parser = argparse.ArgumentParser(
        prog="modforge",
        description="Free Skyrim load order and conflict checker. Read-only. No feature is gated.",
    )
    parser.add_argument("--data", type=Path, help="Game Data folder. Skips Steam discovery.")
    parser.add_argument("--appid", type=int, default=489830, help="Steam appid (default: 489830)")
    parser.add_argument("--steam", type=Path, help="Steam root, library, or libraryfolders.vdf")
    parser.add_argument("--prefix", type=Path, help="Proton compatdata/<appid> directory (or its pfx)")
    parser.add_argument("--plugins", type=Path, help="plugins.txt path")
    parser.add_argument("--loadorder", type=Path, help="loadorder.txt path")
    parser.add_argument("--mods", type=Path, help="Directory of mod folders to scan for loose scripts")
    parser.add_argument("--rules", type=Path, help="Rules JSON (default: rules/series.json)")
    parser.add_argument("--json", action="store_true", help="Write a JSON report to stdout")
    parser.add_argument("--export", type=Path, help="Write the report to PATH. Refused inside the game or prefix.")
    parser.add_argument("--version", action="version", version=f"modforge {__version__}")
    return parser


def _is_inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def forbidden_roots(data, game, prefix):
    roots = []
    if data is not None:
        data = Path(data)
        roots.append(data)
        if data.name.lower() == "data":
            parent = data.parent
            if parent != data and str(parent) not in ("/", ""):
                roots.append(parent)
    if game is not None:
        roots.append(Path(game))
    if prefix is not None:
        roots.append(normalize_prefix(Path(prefix)))
    return roots


def export_allowed(path, data, game, prefix):
    target = Path(path)
    for root in forbidden_roots(data, game, prefix):
        if _is_inside(target, root):
            return False
    return True


def locate_lists(data, prefix, appid):
    plugins = None
    loadorder = None
    for folder in (data, data.parent):
        if plugins is None and (folder / "plugins.txt").is_file():
            plugins = folder / "plugins.txt"
        if loadorder is None and (folder / "loadorder.txt").is_file():
            loadorder = folder / "loadorder.txt"
    if prefix is not None and (plugins is None or loadorder is None):
        found_plugins, found_load = find_lists_in_prefix(prefix, appid)
        if plugins is None:
            plugins = found_plugins
        if loadorder is None:
            loadorder = found_load
    return plugins, loadorder


def run(args):
    if args.rules is not None:
        if not args.rules.is_file():
            print(f"modforge: rules file not found: {args.rules}", file=sys.stderr)
            return 2
        try:
            rules = load_rules(args.rules)
        except ValueError as exc:
            print(f"modforge: {exc}", file=sys.stderr)
            return 2
    else:
        rules_path = default_rules_path()
        if rules_path.is_file():
            try:
                rules = load_rules(rules_path)
            except ValueError as exc:
                print(f"modforge: {exc}", file=sys.stderr)
                return 2
        else:
            print(f"modforge: rules file not found: {rules_path}", file=sys.stderr)
            rules = load_rules(None)

    game = None
    prefix = None
    appid = args.appid
    if args.data is not None:
        data = args.data
        if not data.is_dir():
            print(f"modforge: data folder not found: {data}", file=sys.stderr)
            return 2
        if args.prefix is not None:
            prefix = normalize_prefix(args.prefix)
        if data.name.lower() == "data":
            game = data.parent
    else:
        found = discover(appid, steam=args.steam, prefix=args.prefix)
        data = found.data
        game = found.game
        prefix = found.prefix
        if data is None or not Path(data).is_dir():
            print(
                f"modforge: data folder not found for app {appid} (pass --data)",
                file=sys.stderr,
            )
            return 2
        data = Path(data)

    if args.mods is not None and not args.mods.is_dir():
        print(f"modforge: mods folder not found: {args.mods}", file=sys.stderr)
        return 2

    plugins_path = args.plugins
    loadorder_path = args.loadorder
    if plugins_path is None or loadorder_path is None:
        found_plugins, found_load = locate_lists(data, prefix, appid)
        if plugins_path is None:
            plugins_path = found_plugins
        if loadorder_path is None:
            loadorder_path = found_load

    search_dirs = []
    if args.mods is not None and args.mods.is_dir():
        search_dirs = [child for child in args.mods.iterdir() if child.is_dir()]
    order, source = read_order(data, plugins_path, loadorder_path, search_dirs)
    mod_roots = collect_mod_roots(data, args.mods)
    analysis = analyze(data, order, rules, mod_roots=mod_roots, search_dirs=search_dirs)
    report = {
        "tool": "modforge",
        "version": __version__,
        "free": True,
        "appid": appid,
        "data": str(Path(data).resolve()),
        "game": str(Path(game).resolve()) if game else None,
        "prefix": str(Path(prefix).resolve()) if prefix else None,
        "read_only": True,
        "load_order_source": source,
        "rules": rules.get("path"),
        "plugins": analysis["plugins"],
        "issues": analysis["issues"],
        "summary": analysis["summary"],
    }

    if args.export is not None:
        if not export_allowed(args.export, data, game, prefix):
            print(
                f"modforge: export path is inside the game or prefix folder: {args.export}",
                file=sys.stderr,
            )
            rendered = render_json(report) if args.json else render_text(report)
            sys.stdout.write(rendered)
            return 2
        report["exported"] = str(args.export.resolve())

    rendered = render_json(report) if args.json else render_text(report)
    if args.export is not None:
        try:
            dest = args.export.resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"modforge: cannot write export: {exc}", file=sys.stderr)
            sys.stdout.write(rendered)
            return 2
    sys.stdout.write(rendered)
    if analysis["summary"]["hard"]:
        return 1
    return 0


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code is None else int(code)
    return run(args)


def cli_entry():
    sys.exit(main())
