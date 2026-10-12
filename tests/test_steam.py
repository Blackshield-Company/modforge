import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_plugin
from modforge.cli import main
from modforge.steam import discover, parse_vdf


class SteamTests(unittest.TestCase):
    def test_parse_vdf_nested(self):
        data = parse_vdf(
            '"libraryfolders"\n{\n"0"\n{\n"path"\t"/opt/steam lib"\n"apps"\n{\n"489830"\t"1"\n}\n}\n}\n'
        )
        root = data["libraryfolders"]
        self.assertEqual(root["0"]["path"], "/opt/steam lib")
        self.assertIn("489830", root["0"]["apps"])

    def test_old_libraryfolders_and_default_appid(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            steam = root / "steam"
            apps = steam / "steamapps"
            data = apps / "common" / "Skyrim Special Edition" / "Data"
            data.mkdir(parents=True)
            (apps / "compatdata" / "489830" / "pfx").mkdir(parents=True)
            other = root / "other"
            (other / "steamapps").mkdir(parents=True)
            vdf = apps / "libraryfolders.vdf"
            vdf.write_text(
                "\n".join(
                    [
                        '"LibraryFolders"',
                        "{",
                        '"TimeNextStatsReport"\t\t"0"',
                        f'"1"\t\t"{other}"',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            found = discover(489830, steam=steam)
            self.assertEqual(found.data, data)
            self.assertEqual(found.prefix, apps / "compatdata" / "489830")
            self.assertEqual(found.game, data.parent)

    def test_configurable_appid_skips_other_compatdata(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty"
            (empty / "steamapps" / "common").mkdir(parents=True)
            steam = root / "steam"
            apps = steam / "steamapps"
            game = apps / "common" / "ExampleGame" / "Data"
            game.mkdir(parents=True)
            (apps / "compatdata" / "489830").mkdir(parents=True)
            (apps / "compatdata" / "123456").mkdir(parents=True)
            (apps / "appmanifest_123456.acf").write_text(
                '"AppState"\n{\n"appid"\t\t"123456"\n"installdir"\t\t"ExampleGame"\n}\n',
                encoding="utf-8",
            )
            (apps / "libraryfolders.vdf").write_text(
                "\n".join(
                    [
                        '"libraryfolders"',
                        "{",
                        '"0"',
                        "{",
                        f'"path"\t\t"{empty}"',
                        '"apps"',
                        "{",
                        "}",
                        "}",
                        '"1"',
                        "{",
                        f'"path"\t\t"{steam}"',
                        '"apps"',
                        "{",
                        '"123456"\t\t"10"',
                        "}",
                        "}",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            found = discover(123456, steam=steam)
            self.assertEqual(found.data, game)
            self.assertEqual(found.prefix, apps / "compatdata" / "123456")

    def test_cli_reads_prefix_plugins_txt(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            steam = root / "steam"
            data = steam / "steamapps" / "common" / "Skyrim Special Edition" / "Data"
            data.mkdir(parents=True)
            build_plugin.write_plugin(
                data / "Hello.esp",
                records=[{"type": "GLOB", "formid": 0x00000801, "edid": "HEL_One"}],
            )
            lists = (
                steam
                / "steamapps"
                / "compatdata"
                / "489830"
                / "pfx"
                / "drive_c"
                / "users"
                / "steamuser"
                / "AppData"
                / "Local"
                / "Skyrim Special Edition"
            )
            lists.mkdir(parents=True)
            (lists / "plugins.txt").write_text("# enabled\n*Hello.esp\n", encoding="utf-8")
            (steam / "steamapps" / "libraryfolders.vdf").write_text(
                f'"libraryfolders"\n{{\n"0"\n{{\n"path"\t\t"{steam}"\n}}\n}}\n',
                encoding="utf-8",
            )
            code, out, err = _run(
                ["--steam", str(steam), "--json", "--rules", str(ROOT / "rules" / "series.json")]
            )
            self.assertEqual(code, 0, err + out)
            report = json.loads(out)
            self.assertEqual(report["appid"], 489830)
            self.assertEqual(report["plugins"][0]["file"], "Hello.esp")
            self.assertTrue(str(report["prefix"]).endswith("489830"))


def _run(argv):
    from io import StringIO
    from contextlib import redirect_stderr, redirect_stdout

    out = StringIO()
    err = StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
