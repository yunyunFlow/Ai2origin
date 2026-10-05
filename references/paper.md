# Build figures around the article's evidence

First write one sentence per figure: what comparison or claim should this
panel support, and which observation could contradict it? Then bind source,
observable/unit, independent sample, processing, uncertainty and caption.
Use a supplied article/accepted figure as a visual reference; record its
caption, physical size and relevant conventions. Do not copy its numbers,
sample identities, conclusions or protected artwork into a public example.

## Recipe and evidence map

| Family | Typical panels | Data/interpretation checks |
| --- | --- | --- |
| Electrochemistry | CV, GCD, cycling/rate, EIS/Nyquist | Acquisition order, voltage reference, mass/area basis, cycle identity, sign of imaginary impedance; fitting and circuit selection require separate validation |
| Spectroscopy | Raman/IR/UV-vis/XPS overlays or stacks | X-axis calibration/direction, baseline and normalization, raw/fitted/residual distinction; offsets are display values, not intensity changes |
| Characterization | Diffraction profiles, size distributions, images with quantified measures | Instrument/scale calibration and sampling; a plotted peak is not a validated phase assignment |
| Data analysis | Scatter, uncertainty bands, residuals, distributions | Independent unit, missingness, group order, repeated measures, model/weights, train/test separation and uncertainty definition |
| DFT | Relative energies, migration, DOS/PDOS, charges/fields | Reference energy, spin/normalization and occupations, path endpoints/image identity, convergence and parser provenance |
| MD | RDF/CN, MSD, distributions, time-frequency maps | PBC/unwrapping, atom selections, units, sampling windows, independent blocks and stationarity; more pixels do not provide more sampled information |

The runnable template catalog covers the accepted XY/stack examples in these
families, including mixed scatter/stored-line overlays and equal-scale Nyquist.
Every synthetic recipe declares a caption retained with its source hash.
Error-bar adapters, native reversed axes, general fits, images with
scale bars, electronic-field processing and multipanel assembly are extension
work, not hidden features. No computational engine is launched by a template.
Native log10 X is implemented for positive XY/map data with explicit decade
endpoints; it does not imply reversed axes or logarithmic cloud-density support.

The OLS demo's calculation is confined to deterministic sample generation;
the plotter imports existing predicted/residual columns. Display acceptance
does not test a real model's adequacy, causal interpretation or extrapolation.

## Two heatmap templates

- samples/demo.json heatmap: original signed cells, 16 explicit color levels,
  diverging range [-1,1], no resampling.
- samples/demo.json smooth: positive invented XRD scan map, 256 color levels,
  declared bilinear factor 8. Original 9×141 XRD grid is kept in a Raw worksheet;
  the 65×1121 display grid preserves original nodes and synthetic coordinates.
  No extrapolation, denoising, extra observations or missing-cell filling.

The invented DRT map retains 9×81 raw nodes and displays 65×641 nodes, using
bilinear interpolation in log10(tau) and condition index. CSV/native axes bind
positive tau in seconds over 10^-3–10^5. This is not an EIS inversion.

The NEB-like recipe draws a shape-preserving PCHIP guide through seven assigned
energy nodes, with 16 display subdivisions per interval and original markers.
Barriers remain node-based. The guide is not extra NEB images, a force-based
interpolation, a fitted transition state or a converged minimum-energy path.
Disclose this display interpolation to the author in the caption.

The positive example is an invented XRD scan map with invented axes and
assigned Gaussian peaks, not measured diffraction or phase identification.
For real time-frequency analysis, first record the signal, sample interval,
detrending, window/overlap, estimator, frequency convention and normalization
with the appropriate parser/analysis method. The visualization consumes its
result; this plotting adapter does not estimate spectra from a screenshot.

## Two cloud templates

- raincloud: horizontal half-cloud silhouette and original rain points only.
- violin: vertical bilateral translucent silhouette, original
  points, no summary box/mean/median/whiskers. Same disclosed Gaussian KDE and bandwidth;
  this is explicit imported geometry, not an Origin-native Violin statistics
  object or a reconstruction of an earlier project's data.

Both preserve negative values, repeated observations and outliers. The
synthetic groups contain 24/32/20 observations. Kernels, physical bounds,
declared density scale and sample independence remain part of the method.
Public defaults use Scott bandwidth h=sample SD*n^(-1/5), cut=0 (display each group's raw min/max),
and equal maximum display width per group. This changes display extent/width,
not observations or the Gaussian estimate. No gap splitting, tapered density,
hidden filtering or density-based invented points is permitted.

## Article layout and caption

Start from the target journal's current author guide and the actual figure
reference. Use consistent fonts/frame/units and same-object colors; choose
single/double-column physical dimensions explicitly. Avoid a universal journal
style, silent smoothing and unnecessary dual axes. Panels should contribute
distinct evidence. Specify shared axes/color ranges and a/b/c ordering before
assembling an editable native multipanel figure.

A caption should identify objects, observable and units, n and its independent
unit, displayed statistic/error definition, processing and the exact scope of
the comparison. A synthesis panel cannot upgrade correlation to causality.
