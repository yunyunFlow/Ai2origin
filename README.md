# Ai2origin

Give your agent scientific data and a plotting goal. Ai2origin helps it inspect
the files, choose a suitable plot and keep the result reproducible.

**Origin 2021:** PNG and editable OPJU. **Python:** PNG, with optional SVG.
Version **0.2.4**. All examples are synthetic.

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

| XY bands | Heatmap | Raincloud |
| --- | --- | --- |
| ![XY](samples/origin-xy.png) | ![Heatmap](samples/origin-heatmap.png) | ![Raincloud](samples/origin-raincloud.png) |

Browse [samples](samples/README.md) and [templates](templates/README.md).
Sparse line-symbol curves can use 5–6 pt markers through a
[style override](references/style.md); keep dense data readable.

~~~sh
python -m unittest discover -s tests
python scripts/check_reproducibility.py work/repeat-a work/repeat-b --config samples/demo.json
~~~

Generate repeat-a and repeat-b with the same config, style and font.
See [tested scope and remaining limits](VALIDATION.md): the current flat-table
and Python routes are tested; new native combinations and other versions need
their own checks. EIS fitting, DRT inversion and general statistical analysis
are not included.

[MIT license](LICENSE) · [Dependencies and sources](THIRD_PARTY_NOTICES.md) ·
[Use notice](DISCLAIMER.md). Fonts, commercial software and real research data
are not distributed.
