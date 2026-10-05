# Synthetic fixtures

These files are invented demonstrations, not experimental or simulation results.

intake.csv/intake.json add an explicitly assigned 11-node CV loop and column
mapping. Its formula, units and analysis convention are in the mapping and
[tables.md](../references/tables.md); no measured capacitance is implied.
Generate the same source CSVs and config in a **new** directory:

~~~sh
python scripts/make_samples.py --out work/new-synthetic-sources
~~~

- XY: 41 coordinates; damped sine/cosine formulas. The ±0.12 / ±0.10
  envelopes are assigned display bands, not confidence intervals.
- Heatmap: 13 × 9 signed values from two opposite Gaussian-shaped features.
  Coordinate row/column and shared limits [-1, 1] are explicit.
- Raincloud: seed 1729; independent synthetic normal draws in three groups
  (24 / 32 / 20), with an explicitly assigned outlier in each group.
  Negative observations and every outlier remain visible. Per-group Scott KDE bandwidth
  is an illustrative display choice, not an estimate of physical resolution.

- XRD scan map: assigned Gaussian peaks on invented 2-theta and scan axes.
  The 9×141 original nodes in xrd.csv become 65×1121 display nodes;
  bilinear factor 8, no extrapolation, 256 blue-white-red levels, range [0,1].
  White means 0.5 assigned intensity, not zero. No phase or measured XRD claim.
- Full violin: the same invented observations as the half-cloud, shown with
  symmetric density silhouettes and rain, no mean/summary box/median/whiskers.
  The disclosed Gaussian KDE is unchanged; cut=0 limits visible extent to
  each group's raw min/max and equal peak widths are display normalization.
  No taper, gap splitting or density-based fabrication of observations.

origin-*.png are actual Origin exports. Unprefixed PNG/SVG belong to the
Python route. Their acceptance scopes are separate; see ../VALIDATION.md.
The compact distribution includes xy.png/xy.svg as its Python example;
other Python gallery files named here or in historical receipts stay local.
The included configs reproduce them with --backend python and optional --svg.

colors.json adds six palette comparisons: seven invented curves and the same
invented 9×13 positive field under Blue–white–red, Purple–green–yellow,
Violet–orange–yellow, Rainbow and Reversed rainbow. Only colors differ
between the five maps; their raw/derived grids
are identical. Factor-4 bilinear display interpolation is disclosed. Color
registry provenance and range/midpoint meaning are in ../references/colors.md.

walkthrough.json/csv is a new end-to-end synthetic cycling example: 120 ordered
cycles × three curves = 360 unchanged marker observations. The caption states
seed 20261004 and every assigned formula parameter. mAh g^-1 is a chosen toy
capacity basis; no experimental cell/current/mass evidence is implied.
Only direct point/line connections are drawn, with no filtering, smoothing,
normalization, fit or statistical analysis. Its accepted native export is
actual native result; unprefixed walkthrough.png/svg are the Python route.
