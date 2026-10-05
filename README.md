# Ai2origin

Give your agent scientific data and a plotting goal. Ai2origin helps it inspect
the files, choose a suitable plot and keep the result reproducible.

**Origin 2021:** PNG and editable OPJU. **Python:** PNG, with optional SVG.
Version **0.2.4**. All examples are synthetic.

Created by [yunyun](https://github.com/yunyunFlow).

## Try it

Python 3.10+; install the dependencies, then run an example:

~~~sh
python -m pip install -r requirements.txt
python scripts/ai2origin.py samples/demo.json --out work/demo --backend python
~~~

Use a new output directory. Add --svg for an editable vector copy, or
--font-file /path/to/arial.ttf for your installed Arial font.

For Codex, put this repository's contents in a skill folder named ai2origin
and invoke $ai2origin. You can also ask your agent to read [SKILL.md](SKILL.md).

> Plot these battery tables as voltage–specific-capacity curves, compare the
> selected cycles, and keep all measured points.

The agent handles routine configuration. The [table adapter](references/tables.md)
supports explicit flat CSV/TSV/TXT/XLSX mappings; instrument binaries and arbitrary
existing Origin projects need a separate adapter.

## Origin output

Requires Windows and a separately licensed Origin 2021 installation.

~~~sh
python scripts/ai2origin.py samples/demo.json --out work/prepared --backend prepare
~~~

~~~powershell
.\scripts\origin.ps1 -Plan .\work\prepared\origin-plan.json -OutDir .\work\native -Run
~~~

Save and close any open Origin session first. The runner checks values,
saves/reopens the project and exports its graphs. [Native details](references/origin2021.md).

## Examples and checks

### Gallery

All values are invented. These are Origin exports; the three battery overlays
are labeled separately as Python outputs.

| XY bands | Heatmap | Raincloud |
| --- | --- | --- |
| ![XY](samples/origin-xy.png) | ![Heatmap](samples/origin-heatmap.png) | ![Raincloud](samples/origin-raincloud.png) |

| CV loop | Capacity cycling | Nyquist |
| --- | --- | --- |
| ![CV](templates/origin-cv.png) | ![Capacity cycling](templates/origin-cycle-capacity.png) | ![Nyquist](templates/origin-nyquist.png) |

| Spectral stack | DRT map | Energy-path guide |
| --- | --- | --- |
| ![Stack](templates/origin-stack.png) | ![DRT map](templates/origin-drt-map.png) | ![Energy path](templates/origin-migration.png) |

| RDF-shaped curve | MSD-shaped curve | Bilateral cloud |
| --- | --- | --- |
| ![RDF](templates/origin-rdf.png) | ![MSD](templates/origin-msd.png) | ![Cloud](samples/origin-violin.png) |

| Red–white–blue | Ramp 26 | Rainbow |
| --- | --- | --- |
| ![Red–white–blue](samples/origin-palette-redwhiteblue.png) | ![Ramp 26](samples/origin-palette-reimu26.png) | ![Rainbow](samples/origin-palette-rainbow.png) |

Battery overlays — **Python**:

| Selected cycles | Current-density comparison | Voltage–time |
| --- | --- | --- |
| ![Cycles](templates/python-battery-capacity.png) | ![Rates](templates/python-battery-rate.png) | ![Voltage–time](templates/python-battery-time.png) |

Browse [samples](samples/README.md) and [templates](templates/README.md).
Sparse line-symbol curves can use 5–6 pt markers through a
[style override](references/style.md); keep dense data readable.

Try a family with Python:

~~~sh
python scripts/ai2origin.py templates/battery.json --out work/battery --backend python
python scripts/ai2origin.py templates/electrochem.json --out work/echem --backend python
python scripts/ai2origin.py templates/drt.json --out work/drt --backend python
python scripts/ai2origin.py templates/dft-md.json --out work/atomistic --backend python
~~~

### Check the download

From the repository root, Linux/WSL can verify every bundled file:

~~~sh
sha256sum -c SHA256SUMS
~~~

Every entry should report OK. Run the regressions next:

~~~sh
python -m unittest discover -s tests
~~~

The tested version runs **90 tests**. Missing values, invalid settings, source
changes, missing glyphs and incomplete outputs are among the checked cases.

### Repeat a plot

Use two new directories and the same config, style, dependencies and font:

~~~sh
python scripts/ai2origin.py samples/demo.json --out work/repeat-a --backend python
python scripts/ai2origin.py samples/demo.json --out work/repeat-b --backend python
python scripts/check_reproducibility.py work/repeat-a work/repeat-b --config samples/demo.json
~~~

Expected: status PASS and repeat BYTE_IDENTICAL. The checker also rejects
extra files and failure markers. For vector delivery, add --svg to both
generation commands; SVG text and the declared output set are checked too.

### From a table to a figure

The included 11-point toy CV example exercises column mapping and plotting:

~~~sh
python scripts/intake.py samples/intake.csv --map samples/intake.json --out work/table
python scripts/intake.py --check work/table
python scripts/ai2origin.py work/table/plot.json --out work/table-figure --backend python
~~~

The mapping declares columns and units; [table details](references/tables.md)
explain the optional summary. Use your own verified mapping for real data.

### Before sharing a figure

- Open the actual export: readable labels, correct units, clean legends and no clipping.
- Check every assigned point, branch and group against its source.
- Keep the config and receipt with the figure; state requested processing.
- For Origin delivery, check the saved project's read-back and reopen results.

See [tested scope and remaining limits](VALIDATION.md): the current flat-table
and Python routes are tested; new native combinations and other versions need
their own checks. EIS fitting, DRT inversion and general statistical analysis
are not included.

[MIT license](LICENSE) · [Dependencies and sources](THIRD_PARTY_NOTICES.md) ·
[Use notice](DISCLAIMER.md). Fonts, commercial software and real research data
are not distributed.
