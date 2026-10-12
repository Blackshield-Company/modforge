import json


def short_path(path, limit=42):
    text = str(path)
    if len(text) <= limit:
        return text
    return "..." + text[-(limit - 3) :]


def _fmt_masters(masters, width):
    if not masters:
        return "--"
    text = ", ".join(masters)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def render_text(report):
    appid = report.get("appid", 489830)
    game = "Skyrim SE" if appid == 489830 else f"app {appid}"
    header_left = f"MODFORGE   {game}   free"
    header_right = f"data: {short_path(report.get('data') or '')}"
    plugins = report.get("plugins") or []
    issues = report.get("issues") or []
    name_w = max([6, *[len(plugin["file"]) for plugin in plugins]])
    prefix_w = max([6, *[len(plugin.get("prefix") or "--") for plugin in plugins]])
    masters_w = 24
    rows = [
        f"{'#':<3} {'plugin':<{name_w}} {'prefix':<{prefix_w}} {'masters':<{masters_w}} result"
    ]
    by_file = {}
    for issue in issues:
        for name in issue.get("plugins") or []:
            by_file.setdefault(name.casefold(), []).append(issue)
    for plugin in plugins:
        prefix = plugin.get("prefix") or "--"
        rows.append(
            f"{plugin['index']:<3} {plugin['file']:<{name_w}} {prefix:<{prefix_w}} "
            f"{_fmt_masters(plugin.get('masters') or [], masters_w):<{masters_w}} {plugin['result']}"
        )
        seen = set()
        for issue in by_file.get(plugin["file"].casefold(), []):
            marker = (issue["code"], issue["message"])
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(f"    {issue['message']}")
    loose = [issue for issue in issues if not issue.get("plugins")]
    if loose:
        rows.append("")
        for issue in loose:
            rows.append(issue["message"])
    summary = report.get("summary") or {}
    conflicts = summary.get("conflicts", 0)
    word = "conflict" if conflicts == 1 else "conflicts"
    footer_left = f"{conflicts} {word}, {summary.get('missing_masters', 0)} missing masters"
    notes = summary.get("notes", 0)
    if notes:
        footer_left += f", {notes} note" if notes == 1 else f", {notes} notes"
    footer_right = "read-only, nothing written"
    width = max(
        66,
        len(header_left) + len(header_right) + 2,
        len(footer_left) + len(footer_right) + 2,
        *[len(row) for row in rows],
    )

    def bar():
        return "+" + "-" * (width + 2) + "+"

    def line(left, right=None):
        if right is None:
            body = left
        else:
            gap = width - len(left) - len(right)
            if gap < 1:
                body = left + " " + right
            else:
                body = left + (" " * gap) + right
        return "| " + body.ljust(width) + " |"

    parts = [bar(), line(header_left, header_right), bar()]
    parts.extend(line(row) for row in rows)
    parts.extend([bar(), line(footer_left, footer_right), bar()])
    if report.get("exported"):
        parts.append(f"exported: {report['exported']}")
    return "\n".join(parts) + "\n"


def render_json(report):
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"
