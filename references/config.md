# Config and reproducibility

Layout reports flag intersections, clipped text and geometry needing a manual check.

Python labels may contain literal percentages: `(%)`, `(at.%)` and `(wt.%)`.
Native preparation still rejects percent substitutions until a native text
adapter is verified. A Python percent-label geometry file is marked unavailable
for native execution and contains no drawing commands. Other text control
characters and command separators remain rejected.

Python exports include `<plot-id>-layout.json`. `NEEDS_REVIEW` flags possible
legend intersections or text outside the canvas; the CLI also prints a warning.
Set task-level axis ranges or canvas dimensions, render to a new directory and
inspect the actual image. A clear geometry result does not replace visual review.

Use samples/demo.json for three baseline examples or templates/paper.json
for the 32 article recipes. These are invented numbers, not scientific evidence.
Use --select ID [ID ...] for an explicit task subset in catalog order; selection
is hash-bound in the plan and verified against the original config. No row-level
filtering is performed.
CSV files are UTF-8/UTF-8 BOM, with nonempty unique headers, fixed row width and
finite numeric observables. Missing values, duplicate heatmap cells and implicit
aggregation are refused. CSV/style_file paths resolve from the config; CLI
paths resolve from the caller. Resources resolve from the skill package.

The project is an object with schema_version: 1 and a nonempty plots array.
Optional style_file and inline style follow references/style.md. Each plot
needs a unique id (letter first; letters/digits/underscore/hyphen; <=48 chars),
kind, csv and nonempty labels.x/labels.y. synthetic, when supplied, is a real
JSON boolean. title is optional; defaults have no text above the frame.
caption records provenance and processing; it is metadata, not a top title.

| Kind | Required mappings | Implemented options |
| --- | --- | --- |
| line / line_symbol / scatter | x; nonempty series list with column and label | Per-series x/id/color/offset/kind/legend; lower+upper with uncertainty_definition; connect_order increasing or acquisition; connection pchip for increasing line_symbol without bands |
| heatmap | x/y/z; labels.color; color_range [low,high] | Complete unique grid; packaged/Matplotlib cmap name or hex list; color_levels 2..256; center at range midpoint; interpolation method none or bilinear with integer factor 2..12; optional y_tick_labels for consecutive categorical row indices0..N-1, unique safe tokens, no cross-row interpolation or Y geometry overrides |
| raincloud | group/value; bandwidth positive number or "scott" | order contains every group once; integer seed; bounds; orientation horizontal/vertical; cloud_shape half/full; summary boolean; cloud_support kde/observed; density_scale shared/width; cloud_fill boolean; group_labels; half-only point_cloud_gap |

Ranges are increasing finite JSON-number pairs; tick steps are positive numbers.
Plot IDs must be safe Windows file stems, cannot end in -reopened, and cannot
collide with another plot's generated asset/export names. Collisions fail before
output creation. This also applies when names differ only by letter case.
XY plots accept `y_ticks:false` for explicitly offset spectra. This hides only
Y ticks and their numbers, preserving the Y title, black frame, raw values and
declared offsets. It cannot be combined with `y_tick_step`.
Booleans are not numbers. x_scale linear/log10 applies to XY/maps; log10 needs
positive source X and explicit positive decade-endpoint x_range, and does not
accept linear x_tick_step. equal_xy requires XY, linear axes, both explicit
ranges and a physical aspect fitting the page. Reversed/log cloud axes need
separate adapters. Unknown and ineffective settings fail instead of being
accepted silently. Error-bar/bar/ECDF/multipanel/general fit adapters remain HOLD.

Connected curves and bands require increasing X; acquisition loops preserve
their order but cannot carry connected uncertainty bands. PCHIP is a display
guide with raw nodes retained, never additional calculations. Display offsets
retain raw Y separately. Color limits cannot clip source values silently.

An optional series.x names that curve's independent X column, overriding
plot.x. Every supplied row must remain finite; unequal record counts and
missing branch cells are still refused, never silently interpolated. Log-X
positivity is checked for every series. legend:false omits a duplicate key
only; the curve and worksheet stay intact. At least one key must remain.
Battery pairs use solid charge and solid discharge in the same color, with
one group key. Unit exponents use g^-1 etc., rendered with the chosen Arial
digits and minus rather than unavailable Unicode superscript glyphs.
Both backends use the declared discrete palette. A declared center requires
at least three levels; even palettes use two adjacent neutral bins so the
midpoint color is exact. Adaptive colorbar precision keeps ticks distinct and
rounding error <=1% of tick spacing.
Without cmap, redwhiteblue is the packaged default. The descriptive keys
purplegreen and violetgold retain the exact original reimu26/reimu27 palettes;
legacy keys remain valid. See colors.md for ramps and seven series identities.
Preset/catalog SHA is bound to the plan; custom stops are sampled directly.

Clouds retain every value and only jitter the group coordinate.
For half clouds, `point_cloud_gap` is the
distance from the unjittered point center to the flat cloud edge in group-axis
units: 0.06..0.45, default0.32. The compact style uses0.24. It translates only
the group coordinate; the fixed jitter, raw values and KDE stay unchanged.
The setting is refused for full clouds. Scott uses
sample SD*n^(-1/5). Each drawn group grid resolves its own density; narrow fixed
kernels add evaluated grid points, not observations. Physical-bound reflection
is normalized by analytic Gaussian mass. Groups with <3 observations or
constant values retain all points but omit the density; Scott bandwidth is
recorded null there. No taper, gap splitting or filtering. Width normalization
uses the actual drawn density peak. Grid*sample work above 20 million
evaluations is refused; use an explicit upstream density method rather than
an undocumented approximation. cut=0 restricts visible extent to raw min/max.
Density between raw points is estimator output. Pair/sample IDs remain in the
original CSV; they are not inferred from native numerical geometry columns.

## Repeat and inspect

XY figures additionally allow positive `y_scale:"log10"` with explicit decade
range endpoints; no zero/negative observations or linear Y tick increments.
`legend_columns:2` places compact keys in two columns (default remains1).
`kind:"bar"` currently supports explicitly stacked nonnegative components,
2..7 series, consecutive category positions0..N-1 and matching safe
`x_tick_labels`. It preserves the numeric component worksheet, rather than
simulating columns with filled line bands. General grouped/negative bars remain
outside this adapter. Analysis-generated figures use explicit display ranges
and tick spacing; raw numeric arrays remain unchanged.

--backend python exports PNG only by default. Add --svg for an author-requested
editable vector copy; PNG is still exported. The receipt records actual formats.
--svg with --backend prepare is refused before output creation. Historical
receipts without this field retain their old PNG-plus-SVG requirement.

Use an existing Python environment; do not install as an implied drawing step.
For Arial-specific output, supply your own installed font file:

~~~sh
python scripts/ai2origin.py samples/demo.json --out work/repeat-a --backend python --font-file /path/to/arial.ttf
python scripts/ai2origin.py samples/demo.json --out work/repeat-b --backend python --font-file /path/to/arial.ttf
python scripts/check_reproducibility.py work/repeat-a work/repeat-b --config samples/demo.json
~~~

Use new output directories outside an installed skill. The receipt binds
config/source/geometry/output hashes, resolved style and dependency/font
versions. In a fixed environment Python files must repeat byte-for-byte;
SVG Date is omitted and IDs have a fixed salt. Cross-version pixel identity
is untested. The selected installed font and its hash are recorded; missing
fonts/glyphs fail. Preparation alone does not test Origin or rendered glyphs.

For native output, use references/origin2021.md and then:

~~~sh
python scripts/check_reproducibility.py work/native-a
python scripts/check_reproducibility.py work/native-a work/native-b
~~~

The checker verifies hashes, saved-project cell counts, actual reopened RGB
pixels and SVG text. Different OPJU bytes can be session metadata; native
repeat compares provenance and PNG pixels. A checker PASS still requires
visual review and cannot certify scientific validity or arbitrary future edits.
Use --config with prepared/Python outputs to check the live config, CSVs and
referenced project style. Native receipts bind the prepared plan hash; native
--config is refused. CLI user/task styles are hash-bound in style_inputs;
keep those original files for reproduction. Live rechecking of their paths
is not implied by --config, since public plans deliberately omit private paths.
Failure markers or missing/tampered outputs are rejected. Numerical/config
failures occur before output creation; rendering failures retain marked,
unaccepted partial evidence. Fix the cause and choose a new directory.
Existing directories and Origin sessions are preserved.
