# Visual grammar distilled from working Origin outputs

This example profile comes from inspecting existing native graph outputs and
their drawing recipes. Only general methods are retained; no original plot,
workbook, sample identity, numerical result or private provenance is shipped.

## Retained decisions

- White background, black axes, a clean four-sided frame, no default grid.
- Readable axis titles/ticks; Arial for the Windows Origin examples.
  Python checks explicit fallback fonts and records the actual font; a real
  local font can also be supplied without distributing it.
- Red/blue/green/purple/orange/gray/pink identities; the same group keeps the same hue in
  its curve, cloud, box and observations. Colors remain editable.
- Real observations remain visible over a transparent density/interval
  layer; fill is separated from line/symbol settings.
- Axis unit, zero/reference meaning, shared colorbar range and explicit
  numerical bindings take precedence over cosmetic imitation.
- Single-layer overlays where possible, so density/points do not drift on
  differently rescaled hidden axes.

The inspected native distribution recipe uses a bilateral violin cloud and
source-bound scatter overlays. This package's first reusable CLI instead
constructs an explicit **horizontal half-cloud + rain** and a **vertical
bilateral cloud + rain** from disclosed
geometry. It preserves the overlay/data/opacity principles, and states that
shape difference rather than claiming an identical project reconstruction.
The bilateral mode imports explicit KDE geometry; it does not claim to use
Origin's statistical Violin object. Summary strokes are optional and off;
public cloud points use 2 pt and thin 0.6 pt contours. Horizontal clouds have
light transparent fill; vertical defaults show translucent silhouettes and all raw points.
Vertical native fill uses closed source-bound KDE polygons with zero stroke;
Origin 2021 otherwise strokes an unwanted implicit baseline closure.
Data/KDE shapes are never reshaped to imitate the reference. The reference's
native estimator and this disclosed Gaussian estimator are distinct.

## Configurable, not a universal house style

Edit assets/default.json in a maintained source checkout, or preferably
provide an override file. Do not force these defaults over an accepted template, journal
requirements or a scientifically meaningful color encoding. Sequential,
diverging and cyclic color maps have different meanings; don't inherit a
field-specific colormap into an unrelated heatmap.

## Display configuration

The built-in source stays read-only during runs. Priority is default < user
file (--user-style) < project style_file (relative to config) < inline style
< task file (--style). JSON dictionaries merge recursively, palettes replace
as a whole, and null/unknown/unsupported settings fail explicitly. Resolved
values and layer order are saved as style.resolved.json in the output folder.

| Settings | Mapping |
| --- | --- |
| figure.width_mm / height_mm | Python inches=mm/25.4; Origin page.resx/resy × inches |
| font family / sizes in pt | Real font lookup and actual fallback record in Python; exact installed family and native fsize in Origin |
| line.width_pt / default_style | Python linewidth/linestyle; Origin -w = pt×500 and -d = 0/1/2/3 |
| marker.size_pt | Python scatter area=pt²; Origin -z in points |
| axes color / width_pt / tick_direction / frame | Frame, tick and label styles; actual exported tick length checked on the tested 2021 build |
| colors.palette | Explicit series colors, no automatic palette inference |
| series_overrides | Stable ID → color, width_pt, line_style, marker_size_pt |
| export.raster_dpi | Python PNG DPI; Origin tr2.PNG.dotsperinch and explicit physical width |

Shared native DPI choices are 72/100/150/300/600/1200; unsupported values fail.

XY stable ID defaults to the source column, or an explicit series id. Grouped
data use the explicit group name/order. After exhausting the palette, colors
cycle in declared order; use overrides/line styles for unique identities.
Per-series explicit color is a declared plot override. Colorbar settings are
plot-specific and never silently copied from a group palette.

The supplied style example demonstrates sizes, palette and a stable series
override. Defaults use outward bottom/left ticks and a full
1 pt black frame. Top/right lines have no ticks. Arial ticks/legends are
10 pt, axis titles 12 pt and auxiliary colorbar ticks 8 pt.
Default top titles are empty. Vertical legends select
a corner by curve/band overlap; inspect actual
exports and move them if necessary. Baseline colors and optional heatmap ramps
are described in [colors.md](colors.md). Existing fields retain blue-white-red.
White means zero for signed [-1,1] fields and 0.5
for assigned [0,1] intensity maps. The physical 90×70 mm / 8–12 pt hierarchy
is adopted as a configurable example, not a universal journal requirement.

For sparse line-symbol data, try 5–6 pt with a task override
{"marker":{"size_pt":6}}; dense data may need smaller points.
Default marker values remain unchanged. Check the final-size preview and
legend; a marker override changes display only, not worksheet coordinates.

Minor grids, framed legends and transparent export are unsupported in this
version and explicitly rejected when enabled. Line style/width overrides
apply to XY central curves; raincloud summary geometry keeps its documented
fixed stroke construction. Input arrays, transforms, ranges, uncertainty,
KDE bandwidth and group order remain independent of display configuration.

## Arial scientific glyphs

Check the actual font file used for a preview and the installed native family.
Common Greek α β γ τ θ μ Ω Δ Γ χ λ σ ρ ν φ ψ ω η ε ζ π, Å (U+00C5),
± − ′ ″ × ∂ ∫ ∞ √ ≤ ≥ are supported by the inspected Windows Arial.
Use Å rather than the compatibility Angstrom sign Å (U+212B), and an ordinary
space or supported middle dot rather than an unsupported dot operator.
Unicode superscript minus is missing from this font. Unit input such as
cm^-1 or mAh g^-1 is converted through bounded integer-exponent formatting:
Origin rich text and Python mathtext use Arial digits/minus as superscripts.
Log axes use the same approach for decade labels. Unsupported glyphs fail
preview validation; do not silently mix font families or draw empty boxes.
Auxiliary size is configurable with font.annotation_size_pt; main text remains
10–12 pt by default. Titles/captions and legend positioning do not change data.
