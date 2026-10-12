import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_plugin
from modforge.cli import main


def run(argv):
    out = StringIO()
    err = StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def write_rules(path, plugins):
    path.write_text(
        json.dumps({"vanilla": ["Skyrim.esm", "Update.esm"], "plugins": plugins}),
        encoding="utf-8",
    )


class CliTests(unittest.TestCase):
    def test_module_help(self):
        proc = subprocess.run(
            [sys.executable, "-m", "modforge", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--data", proc.stdout)
        self.assertIn("free", proc.stdout.lower())

    def test_hard_conflict_exit_and_json(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "game" / "Data"
            data.mkdir(parents=True)
            build_plugin.write_plugin(
                data / "One.esp",
                records=[{"type": "GLOB", "formid": 0x00000801, "edid": "SSR_One"}],
            )
            build_plugin.write_plugin(
                data / "Two.esp",
                records=[{"type": "GLOB", "formid": 0x00000802, "edid": "SSR_Two"}],
            )
            (data / "plugins.txt").write_text("*One.esp\n*Two.esp\n", encoding="utf-8")
            rules = root / "rules.json"
            write_rules(rules, [])
            before = sorted(p.name for p in data.iterdir())
            code, out, err = run(["--data", str(data), "--rules", str(rules), "--json"])
            after = sorted(p.name for p in data.iterdir())
            self.assertEqual(before, after)
            self.assertEqual(code, 1, err + out)
            report = json.loads(out)
            self.assertTrue(report["free"])
            self.assertTrue(report["read_only"])
            self.assertTrue(any(issue["code"] == "duplicate_prefix" for issue in report["issues"]))
            self.assertIn("duplicate prefix", out)

    def test_text_report_and_note_exit_zero(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "game" / "Data"
            data.mkdir(parents=True)
            build_plugin.write_plugin(data / "Skyrim.esm", esm=True)
            build_plugin.write_plugin(
                data / "OverA.esp",
                masters=["Skyrim.esm"],
                records=[
                    {
                        "type": "GLOB",
                        "formid": build_plugin.override_formid(0, 0x1234),
                        "edid": "OVA_A",
                    }
                ],
            )
            build_plugin.write_plugin(
                data / "OverB.esp",
                masters=["Skyrim.esm"],
                records=[
                    {
                        "type": "GLOB",
                        "formid": build_plugin.override_formid(0, 0x1234),
                        "edid": "OVB_B",
                    }
                ],
            )
            (data / "plugins.txt").write_text("*OverA.esp\n*OverB.esp\n", encoding="utf-8")
            rules = root / "rules.json"
            write_rules(
                rules,
                [
                    {
                        "file": "OverA.esp",
                        "prefix": "OVA_",
                        "masters": ["Skyrim.esm"],
                        "edits_vanilla": True,
                    },
                    {
                        "file": "OverB.esp",
                        "prefix": "OVB_",
                        "masters": ["Skyrim.esm"],
                        "edits_vanilla": True,
                    },
                ],
            )
            code, out, err = run(["--data", str(data), "--rules", str(rules)])
            self.assertEqual(code, 0, err + out)
            self.assertIn("MODFORGE", out)
            self.assertIn("free", out)
            self.assertIn("read-only, nothing written", out)
            self.assertIn("base", out)
            self.assertIn("note", out)
            self.assertIn("override of Skyrim.esm:00001234", out)
            self.assertNotIn("CONFLICT", out)

    def test_export_refused_inside_game_and_prefix(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "game" / "Data"
            data.mkdir(parents=True)
            build_plugin.write_plugin(data / "Solo.esp", records=[{"type": "GLOB", "formid": 1, "edid": None}])
            (data / "plugins.txt").write_text("*Solo.esp\n", encoding="utf-8")
            rules = root / "rules.json"
            write_rules(rules, [])
            inside_data = data / "report.txt"
            inside_game = root / "game" / "report.txt"
            prefix = root / "compatdata" / "489830"
            inside_prefix = prefix / "pfx" / "report.txt"
            outside = root / "out" / "report.txt"
            for dest in (inside_data, inside_game, inside_prefix):
                code, _out, err = run(
                    [
                        "--data",
                        str(data),
                        "--prefix",
                        str(prefix),
                        "--rules",
                        str(rules),
                        "--export",
                        str(dest),
                    ]
                )
                self.assertEqual(code, 2, err)
                self.assertFalse(dest.exists())
                self.assertIn("inside the game or prefix", err)
            code, _out, err = run(
                ["--data", str(data), "--prefix", str(prefix), "--rules", str(rules), "--export", str(outside)]
            )
            self.assertEqual(code, 0, err)
            self.assertTrue(outside.is_file())
            self.assertIn("read-only, nothing written", outside.read_text(encoding="utf-8"))
            self.assertFalse(any(p.name == "report.txt" for p in data.iterdir()))

    def test_data_override_does_not_require_steam(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            data = Path(tmp) / "loose"
            data.mkdir()
            build_plugin.write_plugin(
                data / "Plain.esp",
                records=[{"type": "GLOB", "formid": 0x00000801, "edid": "PLN_One"}],
            )
            rules = Path(tmp) / "rules.json"
            write_rules(rules, [])
            code, out, err = run(["--data", str(data), "--rules", str(rules), "--appid", "123456", "--json"])
            self.assertEqual(code, 0, err + out)
            report = json.loads(out)
            self.assertEqual(report["appid"], 123456)
            self.assertEqual(report["plugins"][0]["file"], "Plain.esp")
            self.assertIsNone(report["prefix"])


if __name__ == "__main__":
    unittest.main()
