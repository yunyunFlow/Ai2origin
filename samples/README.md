# Synthetic inputs

These are independently assigned demonstration values, not measured data.
[samples/demo.json](demo.json) contains three distinct representations:
XY curves with assigned display bands, a signed field and an XRD-like scan map.
[colors.json](colors.json) contains one seven-color curve display; heatmap ramps
are configuration options, not five copies of the same observation grid.

~~~sh
python scripts/make_samples.py --out work/new-synthetic-sources
~~~

XY:41 nodes with assigned sine/cosine values and ±0.12/±0.10 bands; not confidence
intervals. Signed map:13×9 Gaussian-shaped features. XRD-like map:9×141 invented
nodes, disclosed factor8 bilinear display interpolation, 256 colors, [0,1],
white=0.5. Original nodes remain; no diffraction or phase claim.

raincloud.csv supplies the three styles in [the canonical cloud config](../templates/clouds.json):
seed1729, groups24/32/20 with assigned outliers. Every value, including negative
and repeated observations, is retained. Cloud shape/bandwidth/support/seed are
explicit; they do not establish sample independence or statistical inference.

intake.csv/intake.json supplies an explicit11-node CV loop for the
[column/unit adapter](../references/tables.md). The optional
[analysis contract](../references/analysis.md) uses independently invented forward
models and declared truth; fit success is not real-material validation.

The included PNGs are actual native exports. Reproduce Python PNG or requested
SVG from the configs; duplicate Python galleries are not shipped. Per-image
records bind source/config/plan/image hashes and their exact native generation.
