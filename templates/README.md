# Scientific recipe gallery

42 canonical recipes; all values and axes are invented. Each recipe has one
maintained definition. Display variants do not count as independent evidence.
The 32 article recipes share [paper.json](paper.json); there are no copied
family configs. Use --select to render only the scientifically relevant IDs.

| Goal | Config and recipe IDs |
| --- | --- |
| Curves/bands, signed map, XRD-like map | [demo](../samples/demo.json): xy, heatmap, smooth |
| Seven consistent series colors | [colors](../samples/colors.json): palette-lines |
| Retention/capacity/CE, rate and impedance | [paper](paper.json): cycling, cycle-capacity, coulombic, rate, nyquist, bode-magnitude, bode-phase |
| Updated six-rate CV and derived observables | [analysis](../samples/analysis.json): cv, peaks, cdl, correction; [method contracts](../references/analysis.md) |
| Generic A/B CV drawing style | [paper](paper.json): cv; this basic example does not perform scan-rate analysis |
| GITT pulse display and DRT | [paper](paper.json): gitt, drt, drt-map |
| Spectra and diffraction | [paper](paper.json): spectra, stack, diffraction |
| Energy paths and atomistic observables | [paper](paper.json): migration, dos, rdf, msd |
| Stored association and residuals | [paper](paper.json): association, residual |
| Mechanics and thermal/conversion traces | [paper](paper.json): stress-strain, tga, dsc, kinetics |
| Magnetism, optics and biology | [paper](paper.json): hysteresis, susceptibility, uvvis, photoluminescence, fluorescence-decay, dose-response, growth, enzyme-kinetics |
| Solid-line voltage–capacity/time battery curves | [battery](battery.json): battery-capacity, battery-rate, battery-time |
| Three deliberately distinct cloud styles | [clouds](clouds.json): cloud-horizontal, cloud-vertical, violin-vertical |

~~~sh
python scripts/ai2origin.py templates/paper.json --select cv nyquist --out work/echem --backend python
python scripts/ai2origin.py templates/paper.json --select drt drt-map --out work/drt --backend prepare
~~~

Selection preserves catalog order and binds the requested IDs in the plan.
Unknown/duplicate IDs fail before output creation. Adapt units, series and
captions from verified observations; a template never supplies missing mass,
reference electrode, equilibrium, normalization or peak identity.

## Presentation choices, not extra recipes

Heatmap color ramps are options in [the palette registry](../references/colors.md);
one map can use redwhiteblue, purplegreen/reimu26, violetgold/reimu27, rainbow
or rainbow_r without a second dataset or template. The five former palette-only
maps are retired. Full branch-aware battery recipes replace the simplified
capacity/time loops. cycle-capacity is the single capacity-cycling example.
DRT stack offsets remain a drawing option; the catalog shows curves and a map.
General XY drawing can represent learning curves without a separate toy recipe.

Cloud styles intentionally share the same76 invented observations: Scott KDE,
observed min/max support, fixed seed1729, transparent fill, no summary strokes.
Half-cloud point spacing is0.24 group units; full violin rejects that setting.
No taper, gap splitting, invented points or density-based filtering is used.
Display geometry needs regeneration after changes to raw observations.

The plots below are actual current Origin exports. Exact inputs, configurations,
preparer/runner and PNG hashes are in the included validation records; runtime
and remaining limits are in [VALIDATION](../VALIDATION.md).

## Cloud styles

| cloud-horizontal | cloud-vertical | violin-vertical |
| --- | --- | --- |
| ![cloud-horizontal](origin-cloud-horizontal.png) | ![cloud-vertical](origin-cloud-vertical.png) | ![violin-vertical](origin-violin-vertical.png) |

## Battery branches

| battery-capacity | battery-rate | battery-time |
| --- | --- | --- |
| ![battery-capacity](origin-battery-capacity.png) | ![battery-rate](origin-battery-rate.png) | ![battery-time](origin-battery-time.png) |

## Electrochemistry

| Updated six-rate CV | cycling | cycle-capacity |
| --- | --- | --- |
| ![Six-rate CV](../samples/origin-analysis-cv.png) | ![cycling](origin-cycling.png) | ![cycle-capacity](origin-cycle-capacity.png) |

The CV preview uses the later analysis demonstration: six scan rates from
0.2 to2 mV/s, declared acquisition-order branches and402 stored nodes per loop.
Endpoints coincide in the invented source; the renderer does not force closure.
Reproduce it from samples/analysis.json, then select cv-cv from its generated
plot.json. The simpler paper.json cv remains available as a drawing-style example;
its different data are not the source of this preview.

| coulombic | rate | nyquist |
| --- | --- | --- |
| ![coulombic](origin-coulombic.png) | ![rate](origin-rate.png) | ![nyquist](origin-nyquist.png) |

| bode-magnitude | bode-phase | gitt |
| --- | --- | --- |
| ![bode-magnitude](origin-bode-magnitude.png) | ![bode-phase](origin-bode-phase.png) | ![gitt](origin-gitt.png) |

| drt | drt-map |
| --- | --- |
| ![drt](origin-drt.png) | ![drt-map](origin-drt-map.png) |

## Spectra and atomistic displays

| spectra | stack | diffraction |
| --- | --- | --- |
| ![spectra](origin-spectra.png) | ![stack](origin-stack.png) | ![diffraction](origin-diffraction.png) |

| migration | dos | rdf |
| --- | --- | --- |
| ![migration](origin-migration.png) | ![dos](origin-dos.png) | ![rdf](origin-rdf.png) |

| msd |
| --- |
| ![msd](origin-msd.png) |

## Data, mechanics and thermal displays

| association | residual | stress-strain |
| --- | --- | --- |
| ![association](origin-association.png) | ![residual](origin-residual.png) | ![stress-strain](origin-stress-strain.png) |

| tga | dsc | kinetics |
| --- | --- | --- |
| ![tga](origin-tga.png) | ![dsc](origin-dsc.png) | ![kinetics](origin-kinetics.png) |

## Magnetic, optical and biological displays

| hysteresis | susceptibility | uvvis |
| --- | --- | --- |
| ![hysteresis](origin-hysteresis.png) | ![susceptibility](origin-susceptibility.png) | ![uvvis](origin-uvvis.png) |

| photoluminescence | fluorescence-decay | dose-response |
| --- | --- | --- |
| ![photoluminescence](origin-photoluminescence.png) | ![fluorescence-decay](origin-fluorescence-decay.png) | ![dose-response](origin-dose-response.png) |

| growth | enzyme-kinetics |
| --- | --- |
| ![growth](origin-growth.png) | ![enzyme-kinetics](origin-enzyme-kinetics.png) |

## Calculations have a separate method contract

[The analysis route](../references/analysis.md) offers12 opt-in methods,
illustrated by15 jobs/46 diagnostic figures: CV components/fractions and peaks,
conditional Cdl/corrections, GITT, ICA/DVA, CE/EE, Tafel, RC/DRT and spectral models.
Raw/processed comparisons and residuals are necessary diagnostics, not redundant
style templates. No experimental mechanism is inferred from a toy fit.

| CV components/fractions | Conditional GITT | Tafel |
| --- | --- | --- |
| ![Fractions](../samples/origin-analysis-fractions.png) | ![GITT](../samples/origin-analysis-gitt.png) | ![Tafel](../samples/origin-analysis-tafel.png) |

| DRT map | Spectral components/residuals |
| --- | --- |
| ![DRT](../samples/origin-analysis-drt-map.png) | ![Spectra](../samples/origin-analysis-spectra.png) |

## Complete analysis gallery — all46 figures

The five selected previews above are an overview, not the complete method output.
The four sheets below cover every figure exactly once. These are browsing
composites of accepted Origin PNGs, not a native multipanel capability. Source
plot IDs and image hashes are bound in [analysis validation](../samples/analysis.validation.json).
All analyses remain callable through the same15-job synthetic configuration;
raw/processed comparisons, fit windows, residuals and condition-specific plots
are retained because they answer different questions.

~~~sh
python scripts/analyze.py samples/analysis.json --out work/analysis
python scripts/ai2origin.py work/analysis/plot.json --select cv-cv cv-components-0 cv-fractions --out work/cv --backend python
~~~

| Family | Complete outputs |
| --- | --- |
| CV —12 | Six-rate closed loops, one combined forward/return map, components/residuals at two rates, contribution fractions, peak/sqrt-rate and log/log b-value fits, conditional Cdl, raw/corrected comparison |
| Battery —10 | Three GITT pulses and three sqrt-time fitting windows, conditional diffusivity/SOC, dQ/dV, dV/dQ and branch capacities |
| Impedance —12 | RC fit/residual, three DRT forward fits/residuals/distributions and condition-dependent DRT map |
| Catalysis/spectra —12 | LSV/apparent Tafel, Raman/FTIR/XPS fits and residuals, constrained doublet and Shirley-background fits/residuals |

The optional gallery contains CV, battery, impedance and catalysis/spectra
sheets. It is for browsing; use the generated individual PNGs and editable
Origin project for final dimensions. Every current figure can be regenerated
from the included analysis configuration, without that optional download.

These analysis images retain their declared0.3.5 native generation. Current
recipe acceptance does not relabel them or replace scientific applicability checks.
Read [article semantics](../references/paper.md) for acquisition order, physical
scales and caption requirements; units and transformation records belong with data.
