# Explicit table intake

scripts/intake.py reads flat exports using an explicit mapping; the agent
inspects actual headers/units and writes it. Use an existing environment.

~~~sh
python scripts/intake.py samples/intake.csv --map samples/intake.json --out work/table
python scripts/intake.py --check work/table
python scripts/ai2origin.py work/table/plot.json --out work/figure --backend python
~~~

source-table.csv keeps every source column/value lexeme and row order.
mapped.csv adds original record indices. summary.json records declared skips,
missing/invalid values, exact duplicates, finite ranges/means and adjacent
sampling steps (pooled across rows, including group boundaries). Counts mean
observations, not independent replicates. CSV quoting/line endings may change;
source SHA and cell lexemes stay bound. Originals are never rewritten.
intake-receipt.json binds source/processor/output hashes. --check rejects
unlisted, missing or altered outputs; --repeat checks exact repetition.
These checks cannot prove permissions, physical units or scientific validity.

## Contract

schema_version=1 and columns are required. Each role declares source header,
type (numeric/text), and a unit for numeric data; 1 means known dimensionless.
Do not infer units from curve shape. In audit-only work, explicitly mark an
unverified unit and resolve it before interpretation. Missing values stay
empty; invalid/nonfinite text is retained and counted. No sorting, filtering,
filling, smoothing, normalization, calibration, background removal or fitting.
Nonzero numeric text that cannot be represented as a nonzero float is retained
but counted as invalid, never silently drawn as zero. Finite means use the
standard-library exact-sum mean to avoid premature overflow/underflow.

CSV defaults to comma, TSV to tab. TXT/DPT require table.delimiter (one
character or whitespace). table.encoding defaults to strict utf-8-sig.
Explicit skip_rows excludes declared leading records; header=false requires
unique names. CSV indices refer to logical records, not physical lines.
Unequal widths/duplicate headers are refused.

XLSX reads stored OOXML values without executing Excel. Multi-sheet files need
an exact table.sheet. Numeric lexemes and absent cells, including blanks,
are preserved. Formulas/cached results, merged/hidden cells/rows/columns,
absent rows, macros, external links, date/error cells and unsupported
addresses are refused. Export a values table or use the owner's parser.
XLS/XLSM and proprietary binaries are unsupported. Reading XLSX is not
Excel-native acceptance. The bounded reader accepts at most 128 MiB expanded
workbook XML; it does not interpret date/number formatting as physical units.

profile is generic, spectrum, battery or xps. Battery requires metadata.level
(record/step/cycle), current_sign_convention and text sample/channel/cycle.
Record data also need step/branch/time/voltage/current; step summaries need
step/branch. Map all useful units explicitly; keep raw signs and order.
No branch inversion, inferred capacity basis or automatic cycle aggregation.

XPS requires sample/region text identities, energy in eV, intensity counts/CPS,
metadata.energy_type (binding/kinetic), scan_type
(survey/high_resolution/mixed) and previous processing. Selecting raw versus
corrected columns is explicit. No kinetic-energy conversion, time division,
C1s calibration, background removal or peak fitting occurs.
Neware/LANHE/XPS/XRD/Raman/NMR binaries need an established parser plus real
fixtures; the table reader does not certify vendor-format support.

Optional plot declares x, y (role list), group_by, x_label/y_label,
kind (line/line_symbol/scatter) and marker_size_pt. Selected roles must be
complete finite numeric data; otherwise keep audit-only and resolve an
explicit policy. Groups retain first-seen order, with acquisition-order
connections. Battery plots separate sample/channel; XPS separates
sample/region. Declare cycle/step/branch grouping when needed. Different y
units require separate figures. At most 128 groups are accepted.
inputN.csv/plot.json feed prepare or Python; actual native acceptance of a
new prepared generation is still required for an Origin claim.

## Optional CV loop quotient

analysis.kind=cv_loop_capacitance is opt-in. Map voltage/current with V/mV
and A/mA/uA/µA units; supply scan_rate_V_s>0. Select one potential-closed
cycle with one direction reversal. Pooled specimens/channels/cycles and
incomplete loops are refused. closure_tolerance_V defaults to 1e-9 V.

Stored-order trapezoids give A=integral(I dV), in A·V, **not charge**.
The explicit convention is C_apparent=abs(A)/(2*scan_rate*DeltaV), in F;
2 represents two sweeps. Unit factors affect only this summary. Optional
positive mass_g/area_cm2 gives F/g or F/cm². No inferred rate/mass/area,
Faradaic subtraction or CDL/ECSA/mechanism claim is supplied.
Unrepresentable unit conversions, integral terms and quotients are refused
before output creation; this adapter does not return a fabricated zero.

[Gamry's capacitor CV note](https://www.gamry.com/application-notes/battery-research/testing-electrochemical-capacitors-cyclic-voltammetry-leakage-current/)
discusses the ideal I=C*scan_rate relation.
[Gamry's integration note](https://www.gamry.com/application-notes/physechem/cyclic-voltammetry-integrating-cv/)
uses time integration for charge, unlike our potential-loop integral.
Nonideal/Faradaic contributions can affect the apparent quotient; these
sources do not certify this adapter or a real sample.
The invented 11-node example gives A=0.0036 A·V and C_apparent=0.018 F,
an arithmetic check of assigned values only.

Keep reminders brief: “先保留原始顺序和单位；面积按你指定的速率算～”.
Do not apply analysis automatically because a file resembles a CV.
