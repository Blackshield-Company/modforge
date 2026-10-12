import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_plugin
from modforge.checks import analyze, load_rules
from modforge.plugin import parse_plugin

FIXTURES = ROOT / "local-fixtures"

SERIES_ORDER = [
    "BlackshieldCompany.esp",
    "BountiesOfOblivion.esp",
    "ContractHunter.esp",
    "SteelOath.esp",
    "EmberSmithing.esp",
    "GrayManeDebt.esp",
    "BlackshieldCodex.esp",
    "WarBanners.esp",
    "Roadwarden.esp",
    "SellswordRoster.esp",
    "TurncoatContract.esp",
    "LedgerOfAsh.esp",
    "OathbreakersPrice.esp",
    "ChampionsReforge.esp",
    "BarrowIronPact.esp",
]


class FixtureTests(unittest.TestCase):
    @unittest.skipUnless(FIXTURES.is_dir(), "local-fixtures not present")
    def test_series_plugins_and_sellsword_roster(self):
        esps = sorted(FIXTURES.glob("*.esp"))
        self.assertTrue(esps, "local-fixtures has no plugins")
        for path in esps:
            plugin = parse_plugin(path)
            self.assertIsNone(plugin.parse_error, f"{path.name}: {plugin.parse_error}")
            self.assertGreater(plugin.hedr_records or 0, 0, path.name)
            self.assertTrue(plugin.records, path.name)
        roster = parse_plugin(FIXTURES / "SellswordRoster.esp")
        self.assertTrue(roster.esl)
        self.assertEqual(roster.masters, ["Skyrim.esm"])
        self.assertTrue(any(rec.edid and rec.edid.startswith("SSR_") for rec in roster.records))

    @unittest.skipUnless(FIXTURES.is_dir(), "local-fixtures not present")
    def test_series_load_has_no_hard_conflicts(self):
        from tempfile import TemporaryDirectory
        import shutil

        with TemporaryDirectory() as tmp:
            data = Path(tmp) / "Data"
            data.mkdir()
            build_plugin.write_plugin(data / "Skyrim.esm", esm=True)
            present = []
            for name in SERIES_ORDER:
                source = FIXTURES / name
                if source.is_file():
                    shutil.copy(source, data / name)
                    present.append(name)
            for source in FIXTURES.glob("*.esp"):
                if source.name not in present:
                    shutil.copy(source, data / source.name)
                    present.append(source.name)
            rules = load_rules(ROOT / "rules" / "series.json")
            report = analyze(data, ["Skyrim.esm", *present], rules, mod_roots=[])
            hard = [issue for issue in report["issues"] if issue["severity"] == "hard"]
            self.assertEqual(hard, [], hard)
            row = next(plugin for plugin in report["plugins"] if plugin["file"] == "SellswordRoster.esp")
            self.assertTrue(row["esl"])
            self.assertEqual(row["masters"], ["Skyrim.esm"])
            self.assertEqual(row["result"], "ok  ESL")


if __name__ == "__main__":
    unittest.main()
