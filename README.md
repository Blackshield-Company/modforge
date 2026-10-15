![modforge](.github/preview.png)

# Modforge

Free Skyrim Special Edition load-order and conflict checker for Linux. Point it at a Proton prefix or a Data folder. It reads `plugins.txt` / `loadorder.txt` and plugin headers, then reports missing masters, masters loaded after a dependent, ESL flags that do not match the FormID range, duplicate editor-ID prefixes, script name collisions, and plugins that override the same FormID. It does not modify the game.

Modforge is free. Donations are optional. No feature is gated. There is no license check, no paid tier, and no rule pack for sale. The binary is complete without a donation.

Author: synthalorian
Contact: blackshield@mail.grokbot.com
License: Apache-2.0

## Build

No compile step and no third-party packages. Python 3 standard library only.

```
python3 -m modforge --help
```

`pyproject.toml` defines a setuptools console script named `modforge` (`modforge.cli:cli_entry`). An editable install is optional and is not required to run or test.

## Run

Default Steam appid is 489830 (Skyrim Special Edition). Pass `--appid` for another title. `--data` skips library discovery.

```
python3 -m modforge
python3 -m modforge --data /path/to/Skyrim\ Special\ Edition/Data
python3 -m modforge --appid 489830 --json
python3 -m modforge --data /path/to/Data --mods /path/to/mods --rules rules/series.json
python3 -m modforge --data /path/to/Data --export /tmp/modforge-report.txt
```

Steam discovery reads `libraryfolders.vdf`, then `steamapps/common/<installdir>/Data` and `steamapps/compatdata/<appid>`. `plugins.txt` is read from the Data folder or from the Proton prefix under `AppData/Local/Skyrim Special Edition`. `Skyrim.esm` and `Update.esm` are treated as loaded when those files are present and not explicitly disabled.

The text report is an ASCII table. `--json` prints the same report as JSON. Exit code 1 means at least one hard conflict. Notes (FormID overrides, masters that differ from the series rule) do not change the exit code. Nothing is written into the Data folder or the prefix. `--export` is refused when the path is inside the game folder (the parent of a `Data` directory) or the compatdata prefix.

Series rules live in `rules/series.json`: plugin file, editor-ID prefix, masters, and `edits_vanilla`. Add a row to cover another plugin. Do not treat that file as a product.

## Test

```
python3 -m unittest discover -s tests -v
```

Tests build synthetic plugin binaries in a temporary directory. A fixture test parses `local-fixtures/` when that folder is present and skips when it is absent.

## Known gaps

- Mod Organizer 2 profiles and the VFS are not read. `--mods` is a plain directory of mod folders. Loose scripts are matched by filename under `Scripts/*.pex` and `Source/Scripts/*.psc`, not by the script name stored inside a `.pex`.
- No Papyrus compile check, no load-order suggestions, and no write to `plugins.txt` or `loadorder.txt`.
- The seed file has the ten documented series plugins. Turncoat Contract, Ledger of Ash, Oathbreaker's Price, Champion's Reforge, and Barrow-Iron Pact are not rows yet. Add them in `rules/series.json` if you want those prefixes enforced.
- No global-name, voice, SEQ, mesh, or installed-file collision checks beyond scripts. No simulated light-plugin runtime FormID (`FE` slot) check.
- ESL object indexes below `0x800` are not flagged. The hard check is a new-record object index above `0xFFF` on an ESL-flagged plugin (or a `.esl` file).
- Vanilla masters are header-only. Other plugins larger than 16 MiB are header-only and reported as a note.
- Localized string records are not decoded. EditorIDs are.
- Discovery looks at common Steam roots and `libraryfolders.vdf`. Unusual Proton layouts need `--data` and `--prefix`.
- There is no interactive TUI. Donations are not linked. Nothing in the report depends on payment.
