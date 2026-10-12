import json
from pathlib import Path

from modforge.plugin import find_plugin_file, parse_plugin

VANILLA_DEFAULT = [
    "Skyrim.esm",
    "Update.esm",
    "Dawnguard.esm",
    "HearthFires.esm",
    "Dragonborn.esm",
]


def default_rules_path():
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "rules" / "series.json",
        here.parent.parent / "rules" / "series.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def load_rules(path):
    vanilla = list(VANILLA_DEFAULT)
    by_file = {}
    if path is None:
        return {"vanilla": vanilla, "by_file": by_file, "path": None}
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"rules file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"rules file must be a JSON object: {path}")
    if isinstance(data.get("vanilla"), list):
        vanilla = [str(item) for item in data["vanilla"]]
    plugins = data.get("plugins") or []
    if not isinstance(plugins, list):
        raise ValueError(f"rules plugins must be a list: {path}")
    for row in plugins:
        if isinstance(row, dict) and row.get("file"):
            by_file[str(row["file"]).casefold()] = row
    return {"vanilla": vanilla, "by_file": by_file, "path": str(path)}


def collect_mod_roots(data, mods):
    data = Path(data)
    roots = []
    if mods is not None:
        mods = Path(mods)
        if mods.is_dir():
            for child in sorted(mods.iterdir(), key=lambda p: p.name.casefold()):
                if child.is_dir():
                    roots.append(child)
    else:
        for candidate in (data / "mods", data.parent / "mods"):
            if candidate.is_dir():
                for child in sorted(candidate.iterdir(), key=lambda p: p.name.casefold()):
                    if child.is_dir():
                        roots.append(child)
                break
    if (data / "Scripts").is_dir() or (data / "Source" / "Scripts").is_dir():
        roots.append(data)
    return roots


def _issue(severity, code, message, plugins=None, details=None):
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "plugins": list(plugins or []),
        "details": details or {},
    }


def _infer_prefix(edids):
    counts = {}
    considered = 0
    for edid in edids:
        if not edid or "_" not in edid:
            continue
        head = edid.split("_", 1)[0]
        if not head.isalnum() or not (2 <= len(head) <= 8):
            continue
        considered += 1
        key = head + "_"
        counts[key] = counts.get(key, 0) + 1
    if not counts or considered == 0:
        return None
    best = max(counts, key=lambda item: (counts[item], item))
    if counts[best] * 2 >= considered:
        return best
    return None


def _edid_prefixes(edids):
    found = set()
    for edid in edids:
        if not edid or "_" not in edid:
            continue
        head = edid.split("_", 1)[0]
        if head.isalnum() and 2 <= len(head) <= 8:
            found.add(head + "_")
    return found


def _is_light(filename, esl_flag):
    return bool(esl_flag) or filename.lower().endswith(".esl")


def _canonical(filename, masters, formid):
    index = formid >> 24
    local = formid & 0x00FFFFFF
    if index == len(masters):
        return filename, local
    if index < len(masters):
        return masters[index], local
    return None


def _script_issues(roots, data):
    data_key = str(Path(data).resolve()) if data else None
    found = {}
    for root in roots:
        try:
            root_key = str(root.resolve())
        except OSError:
            root_key = str(root)
        label = "Data" if root_key == data_key else root.name
        seen = set()
        for base, ext in ((root / "Scripts", ".pex"), (root / "Source" / "Scripts", ".psc")):
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or path.suffix.lower() != ext:
                    continue
                stem = path.stem.casefold()
                if stem in seen:
                    continue
                seen.add(stem)
                found.setdefault(stem, []).append((root_key, label, str(path)))
    issues = []
    for stem in sorted(found):
        hits = found[stem]
        roots_hit = {item[0] for item in hits}
        if len(roots_hit) < 2:
            continue
        labels = []
        files = []
        for _root, label, path in hits:
            if label not in labels:
                labels.append(label)
            files.append(path)
        issues.append(
            _issue(
                "hard",
                "script_collision",
                f"script name collision: {stem} ({', '.join(labels)})",
                [],
                {"script": stem, "mods": labels, "files": files},
            )
        )
    return issues


def _summarize(issues):
    hard = sum(1 for issue in issues if issue["severity"] == "hard")
    notes = sum(1 for issue in issues if issue["severity"] == "note")
    missing = sum(1 for issue in issues if issue["code"] == "missing_master")
    return {
        "hard": hard,
        "notes": notes,
        "missing_masters": missing,
        "conflicts": hard,
    }


def _result_for(filename, esl, vanilla_keys, issues):
    mine = [issue for issue in issues if filename in issue["plugins"]]
    if any(issue["severity"] == "hard" for issue in mine):
        return "CONFLICT"
    if any(issue["severity"] == "note" for issue in mine):
        return "note"
    if filename.casefold() in vanilla_keys:
        return "base"
    if esl:
        return "ok  ESL"
    return "ok"


def analyze(data_dir, order, rules, mod_roots=None, search_dirs=None):
    data_dir = Path(data_dir)
    search_dirs = list(search_dirs or [])
    folders = [data_dir, *search_dirs]
    vanilla_keys = {name.casefold() for name in rules.get("vanilla", VANILLA_DEFAULT)}
    by_file = rules.get("by_file") or {}
    deduped = []
    seen_names = set()
    for name in order:
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        deduped.append(name)
    order = deduped
    loaded = []
    issues = []
    for name in order:
        path = find_plugin_file(name, folders)
        if path is None:
            loaded.append(
                {
                    "file": name,
                    "path": None,
                    "plugin": None,
                    "prefix": None,
                    "edids": [],
                    "found": False,
                }
            )
            issues.append(
                _issue(
                    "hard",
                    "missing_plugin",
                    "plugin file not found",
                    [name],
                    {"file": name},
                )
            )
            continue
        scan = path.name.casefold() not in vanilla_keys
        plugin = parse_plugin(path, scan_records=scan)
        edids = [rec.edid for rec in plugin.records if rec.edid]
        rule = by_file.get(plugin.filename.casefold())
        if rule and rule.get("prefix"):
            prefix = str(rule["prefix"])
        else:
            prefix = _infer_prefix(edids)
        loaded.append(
            {
                "file": plugin.filename,
                "path": str(path),
                "plugin": plugin,
                "prefix": prefix,
                "edids": edids,
                "found": True,
                "rule": rule,
            }
        )
        if plugin.parse_error:
            issues.append(
                _issue(
                    "hard",
                    "parse_error",
                    f"parse error: {plugin.parse_error}",
                    [plugin.filename],
                    {"error": plugin.parse_error},
                )
            )
            continue
        if plugin.header_only and plugin.scan_skipped and plugin.filename.casefold() not in vanilla_keys:
            issues.append(
                _issue(
                    "note",
                    "scan_skipped",
                    f"record scan skipped ({plugin.scan_skipped})",
                    [plugin.filename],
                    {},
                )
            )
        order_index = {item.casefold(): idx for idx, item in enumerate(order)}
        self_index = order_index.get(plugin.filename.casefold())
        for master in plugin.masters:
            if master.casefold() == plugin.filename.casefold():
                continue
            master_index = order_index.get(master.casefold())
            if master_index is None:
                issues.append(
                    _issue(
                        "hard",
                        "missing_master",
                        f"missing master {master}",
                        [plugin.filename],
                        {"master": master},
                    )
                )
            elif self_index is not None and master_index > self_index:
                issues.append(
                    _issue(
                        "hard",
                        "master_order",
                        f"master {master} loaded after dependent",
                        [plugin.filename],
                        {"master": master},
                    )
                )
        if _is_light(plugin.filename, plugin.esl):
            bad = []
            for rec in plugin.records:
                if (rec.formid >> 24) != len(plugin.masters):
                    continue
                local = rec.formid & 0x00FFFFFF
                if local > 0xFFF:
                    bad.append(f"{local:03X}")
            if bad:
                shown = ", ".join(bad[:8])
                extra = f" (+{len(bad) - 8} more)" if len(bad) > 8 else ""
                issues.append(
                    _issue(
                        "hard",
                        "esl_range",
                        f"ESL object index exceeds 0xFFF ({shown}{extra})",
                        [plugin.filename],
                        {"object_indexes": bad},
                    )
                )
        if rule is not None and rule.get("edits_vanilla") is False:
            origins = []
            for rec in plugin.records:
                canon = _canonical(plugin.filename, plugin.masters, rec.formid)
                if canon is None:
                    continue
                origin, _local = canon
                if origin.casefold() in vanilla_keys and origin.casefold() not in origins:
                    origins.append(origin.casefold())
            if origins and plugin.filename.casefold() not in vanilla_keys:
                display = []
                for origin in origins:
                    match = next((name for name in rules.get("vanilla", []) if name.casefold() == origin), origin)
                    display.append(match)
                issues.append(
                    _issue(
                        "hard",
                        "vanilla_edit",
                        f"edits vanilla records ({', '.join(display)})",
                        [plugin.filename],
                        {"vanilla": display, "count": _vanilla_count(plugin, vanilla_keys)},
                    )
                )
        if rule is not None and "masters" in rule:
            actual = [master.casefold() for master in plugin.masters]
            expected = [str(master).casefold() for master in rule.get("masters") or []]
            if actual != expected:
                issues.append(
                    _issue(
                        "note",
                        "masters_differ",
                        "masters differ from series rule",
                        [plugin.filename],
                        {"actual": list(plugin.masters), "expected": list(rule.get("masters") or [])},
                    )
                )

    claimed = {}
    for item in loaded:
        if item["prefix"]:
            claimed.setdefault(item["prefix"].casefold(), []).append(item)
    for key, group in claimed.items():
        if len(group) < 2:
            continue
        display = group[0]["prefix"]
        names = [item["file"] for item in group]
        issues.append(
            _issue(
                "hard",
                "duplicate_prefix",
                f"duplicate prefix {display}",
                names,
                {"prefix": display, "plugins": names},
            )
        )
    owners = {key: [item["file"] for item in group] for key, group in claimed.items()}
    for item in loaded:
        plugin = item["plugin"]
        if plugin is None:
            continue
        for prefix in sorted(_edid_prefixes(item["edids"])):
            if item["prefix"] and item["prefix"].casefold() == prefix.casefold():
                continue
            other = [name for name in owners.get(prefix.casefold(), []) if name.casefold() != item["file"].casefold()]
            if not other:
                continue
            issues.append(
                _issue(
                    "hard",
                    "duplicate_prefix",
                    f"duplicate prefix {prefix}",
                    [item["file"]],
                    {"prefix": prefix, "plugins": other + [item["file"]]},
                )
            )

    groups = {}
    for item in loaded:
        plugin = item["plugin"]
        if plugin is None or plugin.parse_error:
            continue
        seen = set()
        for rec in plugin.records:
            if rec.formid == 0:
                continue
            canon = _canonical(plugin.filename, plugin.masters, rec.formid)
            if canon is None:
                continue
            origin, local = canon
            key = (origin.casefold(), local)
            if key in seen:
                continue
            seen.add(key)
            bucket = groups.setdefault(key, {"origin": origin, "local": local, "plugins": []})
            if plugin.filename not in bucket["plugins"]:
                bucket["plugins"].append(plugin.filename)
    for bucket in groups.values():
        if len(bucket["plugins"]) < 2:
            continue
        local = bucket["local"]
        issues.append(
            _issue(
                "note",
                "formid_override",
                f"override of {bucket['origin']}:{local:08X}",
                list(bucket["plugins"]),
                {
                    "origin": bucket["origin"],
                    "local_id": f"{local:08X}",
                    "plugins": list(bucket["plugins"]),
                },
            )
        )

    if mod_roots is None:
        mod_roots = collect_mod_roots(data_dir, None)
    issues.extend(_script_issues(mod_roots, data_dir))

    plugins_out = []
    for index, item in enumerate(loaded, start=1):
        plugin = item["plugin"]
        filename = item["file"]
        esl = bool(plugin and _is_light(plugin.filename, plugin.esl))
        esm = bool(plugin and plugin.esm)
        masters = list(plugin.masters) if plugin else []
        plugins_out.append(
            {
                "index": index,
                "file": filename,
                "path": item["path"],
                "prefix": item["prefix"],
                "masters": masters,
                "esl": bool(plugin.esl) if plugin else False,
                "esm": esm,
                "light": esl,
                "hedr_records": plugin.hedr_records if plugin else None,
                "records": len(plugin.records) if plugin else 0,
                "header_only": bool(plugin.header_only) if plugin else False,
                "result": _result_for(filename, esl, vanilla_keys, issues),
                "found": item["found"],
            }
        )
    return {
        "plugins": plugins_out,
        "issues": issues,
        "summary": _summarize(issues),
    }


def _vanilla_count(plugin, vanilla_keys):
    count = 0
    for rec in plugin.records:
        canon = _canonical(plugin.filename, plugin.masters, rec.formid)
        if canon is None:
            continue
        origin, _local = canon
        if origin.casefold() in vanilla_keys:
            count += 1
    return count
