# Verification notes

Release 0.3.6 keeps the plotting and method implementations, with updated
entry-point text and version labels. All bundled data are invented examples.
Earlier frozen packages retain their original bytes and evidence generations.

## What has been checked

| Check | Evidence |
| --- | --- |
| Public regressions | 262 tests against the extracted public code in Python3.11; the source owner's frozen package has261 |
| Plotting | 42 recipes; repeated Python PNG/SVG with identical bytes |
| Native recipe figures | Origin2021 evidence from0.3.4:42 graphs,178,414 exact worksheet cells, saved/reopened projects and matching repeated pixels |
| Optional calculations | 15 synthetic jobs and46 figures; numerical and Python export repeats |
| Native calculated figures | Origin2021 evidence from0.3.5:46 graphs,58,364 exact worksheet cells, save/reopen and repeated pixels |
| Data intake | Explicit CSV/TSV/TXT/DPT/XLSX mappings, source rows/lexemes, signs, units and paired refusal cases |
| Package use | Chinese/space paths, callers outside the package, exact inventories and preserved sources |
| Editable bindings | Worksheet edits change plotted pixels; restoring values restores pixels; saved originals preserved |

The0.3.6 version fields change provenance text only. Plot objects, styles, source
values and numerical results match the retained generations. Their native
evidence remains0.3.4/0.3.5; no new native generation is implied.

The public sample revision removes Toy from the signed-field and palette-curve
axes. Both graphs were regenerated in two Origin2021 sessions:714 worksheet
cells read back exactly per session, projects saved/reopened, styles checked
and repeated pixels matched. Python PNG/SVG repeats also matched. Source values
and palettes are unchanged. The separate Field heatmap has1840 checked cells
and the same save/reopen/repeat checks; its caption update changes no drawing
objects. Per-image records distinguish these revisions from retained figures.

Synthetic-generator checks retain exact headers, labels and row order, while
allowing numeric roundoff with rtol=atol=1e-12 across environments. Source-file
hashes and repeated exports still require exact bytes.

## Environments

The full local run uses Python3.11.15, NumPy2.4.3, Matplotlib3.10.9,
Pillow12.2.0 and optional SciPy1.17.1. Native evidence uses Origin 2021
and installed Arial.

Core drawing also repeats with SciPy imports blocked. Local portable-test
simulation passes190 cases with7 skips for core and261 with3 skips for analysis;
these simulate absent optional dependencies, Arial and PowerShell.
They are not clean-machine results. Three native consumer tests skip when
Windows PowerShell is unavailable. Optional analysis modules skip without SciPy.

Fresh Linux GitHub Actions jobs pass on Python3.10 and3.12 in both core and
analysis profiles. Each job discovers all test modules and repeats the example
exports; Windows-only checks skip there. Dependency-range endpoints and clean
Windows installation remain untested. See GitHub Actions for the current result.
Other systems should be checked
by the user's assistant using the tools and fonts actually available there.
Different versions and fonts may produce different pixels or fit rounding.

## Limits

The bundled renderer checks its documented shapes and settings. Unequal or
missing branches, grouped/negative bars, error bars, ECDF, histograms,
multipanels, reversed axes and complex text shaping need another checked route
where the built-in script does not support them. Arbitrary OPJ/OPJU import,
image digitization and proprietary formats need appropriate adapters.

Other Origin versions and native SVG/PDF/TIFF are unverified. Python SVG
acceptance does not establish native Origin SVG support.

Calculations retain their raw/processed comparisons, controls and residuals.
DRT recovery does not prove inverse resolution or physical assignment;
CPE/Warburg/KK, spectral quantification and uncertainty remain unverified.
Real GITT geometry/equilibrium, nonfaradaic Cdl, CV correction provenance,
Tafel conditions and chemical identities require experiment-specific evidence.
The real incomplete CV and excessive RC/DRT model residuals keep their original
holds; thresholds are not relaxed. Large-input stress remains untested.

[Method contracts and citations](references/analysis.md) explain calculations
when used. A successful export, good fit or synthetic test does not establish
a real-material mechanism.
