import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build_plugin
from modforge.plugin import parse_plugin


class PluginParserTests(unittest.TestCase):
    def test_header_flags_masters_hedr_and_edid(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            esp = Path(tmp) / "Sample.esp"
            build_plugin.write_plugin(
                esp,
                masters=["Skyrim.esm", "Update.esm"],
                esl=True,
                esm=True,
                records=[
                    {
                        "type": "GLOB",
                        "formid": build_plugin.new_formid(2, 0x801),
                        "edid": "SSR_Power",
                    }
                ],
            )
            plugin = parse_plugin(esp)
            self.assertIsNone(plugin.parse_error)
            self.assertTrue(plugin.esm)
            self.assertTrue(plugin.esl)
            self.assertEqual(plugin.masters, ["Skyrim.esm", "Update.esm"])
            self.assertEqual(plugin.hedr_records, 2)
            self.assertEqual(len(plugin.records), 1)
            self.assertEqual(plugin.records[0].edid, "SSR_Power")
            self.assertEqual(plugin.records[0].formid, build_plugin.new_formid(2, 0x801))
            self.assertFalse(plugin.records[0].compressed)

    def test_compressed_record_edid(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            esp = Path(tmp) / "Compressed.esp"
            formid = build_plugin.new_formid(0, 0x801)
            build_plugin.write_plugin(
                esp,
                records=[{"type": "GLOB", "formid": formid, "edid": "CMP_Value", "compress": True}],
            )
            plugin = parse_plugin(esp)
            self.assertIsNone(plugin.parse_error, plugin.parse_error)
            self.assertEqual(len(plugin.records), 1)
            self.assertTrue(plugin.records[0].compressed)
            self.assertEqual(plugin.records[0].edid, "CMP_Value")
            self.assertEqual(plugin.records[0].formid, formid)

    @unittest.skipUnless((ROOT / "reference" / "esp_check.py").is_file(), "reference/ not present (gitignored)")
    def test_reference_esp_check_accepts_synthetic(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            esp = Path(tmp) / "Checked.esp"
            build_plugin.write_plugin(
                esp,
                masters=["Skyrim.esm"],
                esl=True,
                records=[
                    {
                        "type": "GLOB",
                        "formid": build_plugin.new_formid(1, 0x801),
                        "edid": "SSR_One",
                    },
                    {
                        "type": "GLOB",
                        "formid": build_plugin.new_formid(1, 0x802),
                        "edid": "SSR_Two",
                        "compress": True,
                    },
                ],
            )
            proc = subprocess.run(
                [sys.executable, str(ROOT / "reference" / "esp_check.py"), str(esp)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("OK", proc.stdout)

    def test_not_a_plugin(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "nope.esp"
            bad.write_bytes(b"NOPE" + b"\x00" * 32)
            plugin = parse_plugin(bad)
            self.assertIsNotNone(plugin.parse_error)

    def test_header_only_still_reads_masters(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            esp = Path(tmp) / "Big.esp"
            build_plugin.write_plugin(
                esp,
                masters=["Skyrim.esm"],
                records=[{"type": "GLOB", "formid": 0x00000801, "edid": "BIG_One"}],
            )
            plugin = parse_plugin(esp, scan_records=False)
            self.assertIsNone(plugin.parse_error)
            self.assertTrue(plugin.header_only)
            self.assertEqual(plugin.masters, ["Skyrim.esm"])
            self.assertEqual(plugin.records, [])
            self.assertIsNotNone(plugin.hedr_records)


if __name__ == "__main__":
    unittest.main()
