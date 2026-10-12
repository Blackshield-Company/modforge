import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_plugin
from modforge.checks import analyze, load_rules
from modforge.loadorder import read_order


def rules_empty():
    return {"vanilla": ["Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm"], "by_file": {}, "path": None}


def rec(rtype, formid, edid, compress=False):
    return {"type": rtype, "formid": formid, "edid": edid, "compress": compress}


class LoadOrderTests(unittest.TestCase):
    def test_plugins_and_loadorder_and_utf16(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            data = Path(tmp)
            build_plugin.write_plugin(data / "Skyrim.esm", esm=True)
            build_plugin.write_plugin(data / "On.esp")
            build_plugin.write_plugin(data / "Off.esp")
            (data / "loadorder.txt").write_text("Skyrim.esm\nOff.esp\nOn.esp\n", encoding="utf-8")
            (data / "plugins.txt").write_bytes(b"\xff\xfe" + "*On.esp\nOff.esp\n".encode("utf-16-le"))
            names, source = read_order(data, data / "plugins.txt", data / "loadorder.txt")
            self.assertEqual(source, "plugins.txt+loadorder.txt")
            self.assertEqual(names, ["Skyrim.esm", "On.esp"])

    def test_implicit_base_masters_and_explicit_disable(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            data = Path(tmp)
            build_plugin.write_plugin(data / "Skyrim.esm", esm=True)
            build_plugin.write_plugin(data / "Update.esm", esm=True)
            build_plugin.write_plugin(data / "Child.esp")
            (data / "plugins.txt").write_text("*Child.esp\nUpdate.esm\n", encoding="utf-8")
            names, _source = read_order(data, data / "plugins.txt", None)
            self.assertEqual(names, ["Skyrim.esm", "Child.esp"])


class CheckTests(unittest.TestCase):
    def test_each_check(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            data = Path(tmp) / "Data"
            data.mkdir()
            mods = Path(tmp) / "mods"
            (mods / "ModA" / "Scripts").mkdir(parents=True)
            (mods / "ModB" / "Source" / "Scripts").mkdir(parents=True)
            (mods / "ModA" / "Scripts" / "Foo.pex").write_bytes(b"pex")
            (mods / "ModB" / "Source" / "Scripts" / "Foo.psc").write_text("scriptname Foo", encoding="utf-8")
            (mods / "ModA" / "Source" / "Scripts").mkdir(parents=True)
            (mods / "ModA" / "Source" / "Scripts" / "Foo.psc").write_text("scriptname Foo", encoding="utf-8")
            build_plugin.write_plugin(data / "Skyrim.esm", esm=True, records=[rec("GLOB", 0x00000100, "GameHour")])
            build_plugin.write_plugin(
                data / "Late.esm",
                esm=True,
                records=[rec("GLOB", build_plugin.new_formid(0, 0x801), "LAT_One")],
            )
            build_plugin.write_plugin(
                data / "Child.esp",
                masters=["Late.esm", "Missing.esm"],
                records=[rec("GLOB", build_plugin.new_formid(2, 0x801), "CHD_One")],
            )
            build_plugin.write_plugin(
                data / "Wide.esl",
                esl=True,
                masters=["Skyrim.esm"],
                records=[rec("GLOB", build_plugin.new_formid(1, 0x1000), "WID_Over")],
            )
            build_plugin.write_plugin(
                data / "Roster.esp",
                esl=True,
                masters=["Skyrim.esm"],
                records=[rec("GLOB", build_plugin.new_formid(1, 0x801), "SSR_Alpha")],
            )
            build_plugin.write_plugin(
                data / "Patch.esp",
                masters=["Skyrim.esm"],
                records=[
                    rec("GLOB", build_plugin.new_formid(1, 0x810), "PAT_Main"),
                    rec("GLOB", build_plugin.new_formid(1, 0x811), "SSR_Stolen"),
                ],
            )
            build_plugin.write_plugin(
                data / "OverA.esp",
                masters=["Skyrim.esm"],
                records=[rec("GLOB", build_plugin.override_formid(0, 0x1234), "OVA_Edit")],
            )
            build_plugin.write_plugin(
                data / "OverB.esp",
                masters=["Skyrim.esm"],
                records=[rec("GLOB", build_plugin.override_formid(0, 0x1234), "OVB_Edit")],
            )
            build_plugin.write_plugin(
                data / "VanillaTouch.esp",
                masters=["Skyrim.esm"],
                records=[rec("GLOB", build_plugin.override_formid(0, 0x00014), "VAN_Edit")],
            )
            rules = {
                "vanilla": rules_empty()["vanilla"],
                "by_file": {
                    "roster.esp": {
                        "file": "Roster.esp",
                        "prefix": "SSR_",
                        "masters": ["Skyrim.esm"],
                        "edits_vanilla": False,
                    },
                    "vanillatouch.esp": {
                        "file": "VanillaTouch.esp",
                        "prefix": "VAN_",
                        "masters": ["Skyrim.esm"],
                        "edits_vanilla": False,
                    },
                    "overa.esp": {
                        "file": "OverA.esp",
                        "prefix": "OVA_",
                        "masters": ["Skyrim.esm"],
                        "edits_vanilla": True,
                    },
                },
                "path": None,
            }
            order = [
                "Skyrim.esm",
                "Child.esp",
                "Late.esm",
                "Wide.esl",
                "Roster.esp",
                "Patch.esp",
                "OverA.esp",
                "OverB.esp",
                "VanillaTouch.esp",
            ]
            report = analyze(
                data,
                order,
                rules,
                mod_roots=[mods / "ModA", mods / "ModB"],
            )
            codes = {}
            for issue in report["issues"]:
                codes.setdefault(issue["code"], []).append(issue)
            self.assertIn("missing_master", codes)
            self.assertTrue(any(issue["details"]["master"] == "Missing.esm" for issue in codes["missing_master"]))
            self.assertTrue(any("Late.esm" in issue["message"] for issue in codes["master_order"]))
            self.assertTrue(any("0xFFF" in issue["message"] for issue in codes["esl_range"]))
            self.assertTrue(any("duplicate prefix SSR_" in issue["message"] for issue in codes["duplicate_prefix"]))
            self.assertTrue(any(issue["severity"] == "note" for issue in codes["formid_override"]))
            self.assertTrue(any("Skyrim.esm" in issue["message"] for issue in codes["vanilla_edit"]))
            self.assertTrue(all(issue["severity"] == "hard" for issue in codes["vanilla_edit"]))
            self.assertTrue(any("foo" in issue["message"] for issue in codes["script_collision"]))
            self.assertNotIn("OverA.esp", [issue["plugins"][0] for issue in codes["vanilla_edit"]])
            self.assertEqual(report["summary"]["conflicts"], report["summary"]["hard"])
            self.assertGreater(report["summary"]["notes"], 0)

    def test_clean_esl_and_same_mod_scripts_are_not_conflicts(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            data = Path(tmp) / "Data"
            mod = Path(tmp) / "mods" / "Only"
            (mod / "Scripts").mkdir(parents=True)
            (mod / "Source" / "Scripts").mkdir(parents=True)
            (mod / "Scripts" / "Only.pex").write_bytes(b"pex")
            (mod / "Source" / "Scripts" / "Only.psc").write_text("scriptname Only", encoding="utf-8")
            build_plugin.write_plugin(data / "Skyrim.esm", esm=True)
            build_plugin.write_plugin(
                data / "Clean.esp",
                esl=True,
                masters=["Skyrim.esm"],
                records=[rec("GLOB", build_plugin.new_formid(1, 0xFFF), "CLN_Edge")],
            )
            report = analyze(
                data,
                ["Skyrim.esm", "Clean.esp"],
                rules_empty(),
                mod_roots=[mod],
            )
            self.assertEqual(report["summary"]["hard"], 0)
            self.assertEqual(report["plugins"][1]["result"], "ok  ESL")
            self.assertEqual(report["plugins"][1]["hedr_records"], 2)

    def test_series_rules_file(self):
        rules = load_rules(ROOT / "rules" / "series.json")
        self.assertEqual(len(rules["by_file"]), 10)
        roster = rules["by_file"]["sellswordroster.esp"]
        self.assertEqual(roster["prefix"], "SSR_")
        self.assertEqual(roster["masters"], ["Skyrim.esm"])
        self.assertIs(roster["edits_vanilla"], False)
        for row in rules["by_file"].values():
            self.assertIs(row["edits_vanilla"], False)
            self.assertIn("prefix", row)
            self.assertIn("masters", row)


if __name__ == "__main__":
    unittest.main()
