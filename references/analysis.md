# Opt-in analysis: contracts, equations and limits

The callable entry point is `scripts/analyze.py`, independent of Origin.
Use `requirements-analysis.txt` for optional SciPy methods; ordinary plotting
keeps its original dependencies. All included examples are invented forward
models, never digitized publication or experimental data.

~~~sh
python scripts/analyze.py samples/analysis.json --out work/analysis-a
python scripts/analyze.py samples/analysis.json --out work/analysis-b
python scripts/analyze.py samples/analysis.json --check work/analysis-a --repeat work/analysis-b
python scripts/ai2origin.py work/analysis-a/plot.json --out work/figures --backend python
~~~

Add `--svg` to the drawing command for editable vector output. Prepare the same
plot.json and use the documented [Origin runner](origin2021.md) for native
OPJU. Analysis completion alone is neither visual nor native acceptance.

An agent should inspect inputs, pick the useful analyses, write the contract
and report choices briefly. Do not run every method just because it is present.
Reuse verified units, processing and conditions; infer routine layout, never
mass, area, voltage reference, equilibrium, peak identity or missing data.
If a required scientific condition is unknown, preserve observations and mark
the affected inference HOLD. Do not turn a template's toy declarations into
attestations about someone else's experiment.

## File and output contract

`schema_version:1` contains an ordered `jobs` list. Each job declares `id`,
`method`, `sample_id`, boolean `synthetic`, `inputs` and `parameters`.
Job IDs use1..32 ASCII letters/digits/underscore/hyphen, starting with a letter;
the bound keeps every derived plot/file name within the drawing contract.
Each input specifies file, sample_id, processing history and roles:
`"potential":{"column":"E","unit":"V"}`. Input sample IDs must match
the job. `metadata` holds method-specific branch/condition declarations;
`table` uses the existing [reader options](tables.md). A `selection` is an
explicit zero-based half-open table-row interval, never a guessed branch.

CSV/TSV/TXT/DPT/XLSX contracts use the existing reader. Proprietary files need
a validated parser and provenance-preserving export. Images and arbitrary
Origin projects are not silently converted into quantitative tables.
Explicit units cover V/mV, A/mA/uA, A/m2/mA/cm2/A/cm2, s/ms, C/mAh/Ah,
Hz/kHz, ohm, eV, cm^-1, counts, CPS, absorbance and a.u. No mass/area inference.
Canonical charge conversion is 1 mAh = 3.6 C.

Outputs preserve complete lexical source tables once by content hash, plus
selected source row identities, raw arrays, parameters, transformed arrays,
diagnostics, signed residuals, plot-ready CSVs and plot.json. The receipt binds
config, original input, parser, method modules and every emitted file.
Within one run, immutable lexical tables are cached by content hash, file type
and explicit reading options. Each input still keeps its own selections, units,
roles and source identity; hash changes refuse reuse. The cache is discarded
after the run and never supplies a stale result across tasks.
Failed jobs leave FAILED.txt and cannot pass the checker. Use a new directory;
duplicates, missing observations, nonfinite/underflowing numbers, unsupported
fields and unknown output entries are refused. Repeats are exact in the tested
environment; dependency versions can affect fitting and pixels.

## CV

`cv_dunn`: at each actual shared potential node and within separately declared
monotonic branches, fit signed `I = k1*ν + k2*sqrt(ν)`. `fit_space:"raw"`
fits current; `"normalized"` fits `I/sqrt(ν)` against sqrt(ν), which changes
the residual weighting. Never claim they are interchangeable.
Rates are distinct positive V/s, in identical declared order for each branch.
Grids must match exactly; no implicit alignment, sorting or clipping.
Compatible forward/return branches produce one signed map: F in the upper
block, R below, with categorical row labels giving actual positive scan rates.
Return columns reverse only for display alignment. No interpolation crosses
branch/rate categories; both blocks share a zero-centered color range. If
branch coordinates are not exact reversals, separate maps preserve them; the
agent must not snap measured nodes to make a combined map.
Current can be true A or explicit `current_density_A_m2`; charge then has C
or C/m2 units. A selected complete cycle requires exactly matching endpoints.

Signed components, reconstructed current and residual are retained. Exact
piecewise-linear zero crossings define absolute integrated charge, rather than
trapezoids of absolute endpoint currents. Fractions use
`Q_component_abs / Q_reconstructed_abs`; observed-normalized and signed/path
quantities have separate named denominators. Opposing components, significant
residuals, ill conditioning or incomplete cycles hold aggregate fractions.
The displayed stacked bar is conditional empirical ν/sqrt(ν) share, not proof
of capacitive versus diffusion mechanisms. Raw closed loops are preserved;
real unclosed curves are never forced closed. CV maps keep branches separate,
use a common signed red-white-blue range, and disclose display interpolation.

`cv_peaks`: select an inclusive potential window and anodic/cathodic polarity.
Use actual observed extrema; edge peaks are HOLD. Fits of |Ip| against sqrt(ν)
use a free intercept; `ln|Ip| = intercept + b*lnν` describes an empirical b.
No solid-electrode diffusion coefficient follows automatically.
Optional Randles–Sevcik uses strictly SI:
`|Ip| = 0.4463*n*F*A*c*sqrt(n*F*D*ν/(R*T))`.
Thus `D = (sqrt-rate slope / prefactor)^2` only under explicitly reversible,
planar, semi-infinite **solution** conditions. Porous battery CV is not covered.

`cv_cdl`: fit `(Ia-Ic)/2 = intercept + C_app*ν` at an explicit shared
nonfaradaic node/window. Cathodic reversal must be declared and exactly paired.
Conditions concerning nonfaradaic current, sampling, ohmic drop and repeatability
must be recorded. Units give F; no automatic ECSA or specific capacitance.
The simpler intake loop-capacitance summary retains its own apparent convention.

`cv_correct`: independently supplied signed `E_corrected=E-I_A*Ru*(1-f)`;
optional declared reversal-tail fit `A_current*exp(-progress_V/scale_V)` with
known baseline/window/bounds; subtract an independently mapped background;
then explicitly align a monotonic branch by bounded piecewise-linear interpolation.
Raw nodes, folded corrected paths, full tail/model extrapolation and diagnostics
remain visible. Do not infer Ru from peak motion, force zero endpoints, fit a
convenient background, extrapolate alignment, or mix cathodic/anodic branches.
The numerical API also computes constant-C background as `C*dE_corrected/dt`;
after iR correction it is generally not `C*nominal_scan_rate`.
These are independently implemented conditional primitives, not an automatic
replication of a paper's three-way mechanism assignment.

Sources: [scan-rate separation](https://doi.org/10.1021/jp074464w),
[CV calibration and residual/background discussion](https://cpb-us-e1.wpmucdn.com/blog.umd.edu/dist/7/477/files/2021/07/307.pdf).

## GITT, capacity and derivatives

`gitt`: explicit pulse time/current, pre/post equilibrium potentials, pulse
duration τ, E-vs-sqrt(t) fitting window and effective length
`L = active_volume/effective_area` in meters. Fit `E=a+b*sqrt(t)`;
`ΔEτ=b*sqrt(τ)`, `ΔEs=Eeq_after-Eeq_before`,
`D=4*L^2/(π*τ)*(ΔEs/ΔEτ)^2` in m2/s.
The intercept/constant instantaneous jump does not enter ΔEτ. Check current
constancy, measured τ endpoint, direction, response size, linearity and
`τ*D/L^2 < short_time_limit`; require equilibrium/transient and small-perturbation,
diffusion-dominance/effective-geometry declarations. Missing geometry retains
the fit and holds D. Do not substitute particle radius or coating thickness
without a justified model. Candidate/held pulses stay in results; log-Y D plots
identify only accepted conditional pulses. No automatic extraction from a
whole time series or inference of equilibrium from a flat-looking rest.
The independent finite-slab forward fixture tests the short-time inverse.
See [original method](https://doi.org/10.1149/1.2133112) and
[thin-film theory and limits](https://doi.org/10.1002/cphc.202001025).

`ica`: one explicit monotonic voltage/charge branch; use interval
`dQ/dV=ΔQ/ΔV` and `dV/dQ=ΔV/ΔQ` with interval centers. Retain interval widths,
charge closure and sign convention. Repeated/folded nodes are refused;
there is no hidden smoothing, differentiation across turns, mass conversion
or degradation-mode assignment.
See [ICA practices](https://doi.org/10.3389/fenrg.2022.1023555) and
[corrigendum](https://doi.org/10.3389/fenrg.2023.1203569): the correction replaces
a duplicated Figure 13, rather than changing the derivative formula.

`cycle_efficiency`: explicitly paired complete charge/discharge branch capacity
and full-cell terminal voltage. `CE=Qdis/Qchg`, `EE=Wdis/Wchg`,
`W=integral V dQ`, joules for Q in C, Wh = J/3600. Partial branches retain
descriptive accounting and HOLD full-cycle efficiencies. Absolute capacity
does not silently become specific capacity. Curves use solid lines, no points.

## LSV/Tafel and impedance

`tafel`: retain anodic-positive raw current, explicit current/area unit and
voltage-reference convention. Additional iR removal must account for already
applied compensation. RHE conversion is either a documented direct offset or
`E_RHE=E_reference+E_reference_vs_SHE+(R*T/F)*ln(10)*pH`, with junction treatment.
Define `η=E_RHE-E_equilibrium_RHE`; an explicit branch/window and sign polarity
give `η=intercept+b*log10(|I or j|/declared_reference)`.
The explicit iR object uses `Ru_ohm`, `input_compensation` (`none`, `partial`,
or `full`), `prior_fraction` and the additional `residual_fraction` of the original
Ru. Prior plus additional fractions must not exceed one; density input requires
the independently known area. These settings are retained in the result.
Report signed slope and its magnitude in mV/dec, selected nodes, residuals,
curvature/window sensitivity and condition declarations. No automatic window,
j0, transfer coefficient, corrosion current or rate-determining-step claim.
See [Tafel interpretation cautions](https://doi.org/10.1021/acsenergylett.4c00266).

`eis_rc`: mathematical `Z=Zreal+j*Zimag`, Hz gives `ω=2πf`;
`Z=Rs+Σ Rk/(1+jωτk)+jωL`, `Ck=τk/Rk` when positive.
Explicit bounds, multiple initial guesses and unit/modulus/declared weights;
record condition/rank, boundary hits and conditional covariance. A model does not
automatically pass goodness-of-fit: `model_residual_limit` defaults to0.05
for relative complex RMSE; exceeding it holds the displayed model while retaining
all points, residuals and diagnostic plots. A small RMSE is not physical validation.
Rk does not automatically identify Rct. There is no CPE/Warburg fit or KK validation.
Nyquist draws -Im(Z) against Re(Z) with equal physical X/Y range and scale.
Frequency and tau source endpoints need not be powers of ten. Generated log
display bounds enclose the actual nodes at adjacent decade endpoints, without
resampling observations, extrapolating fitted arrays or changing the lnτ grid.
Analysis figures also declare readable linear-X major intervals; equal-range
Nyquist figures share the same X/Y interval. These are display settings only.

`drt`: nonnegative RC kernel
`Z=Rinf+jωL+integral γ(lnτ)/(1+jωτ) dlnτ`.
Trapezoid weights integrate **natural** log time; γ is in ohms per lnτ.
For `g=γ/Zscale`, minimize
`||W*(Zfit-Z)/Zscale||²/(2N)+λ||D_order*g||²`.
The derivative discretization uses a uniform lnτ grid and
`D_order=diff(order)/h^(order-0.5)`. λ is dimensionless under this normalization,
not transferable from another solver. Retain every requested λ; display selection
is explicit. Report signed complex residuals and signal outside the frequency
supported τ interval. KK, inverse resolution and physical assignment remain HOLD.
DRT maps use identical grid/kernel/weights/λ across declared conditions;
log10 physical τ is only an axis/display coordinate, never the integral measure.
See [regularization context](https://doi.org/10.1016/j.electacta.2015.03.123).
This implementation is deterministic Tikhonov, not the paper's Bayesian solver.

## Raman, FTIR and XPS

`spectra_peaks` and `spectra_doublet` use normalized Gaussian/Lorentzian profiles;
areas are whole-line model integrals, widths are FWHM in coordinate units.
Specify regions, centers/center bounds, widths, weights and multiple starts.
Doublet separation/area ratio are declared constraints, not inferred chemistry.
Rank/condition/bound hits can HOLD a successful optimizer. Report the baseline,
components, residual, window areas and all starts; uncertainty is not estimated.

Baselines: none, explicit linear anchors, joint linear, or explicitly supplied.
XPS additionally allows iterative fixed-endpoint Shirley. In increasing BE,
`B(E)=B_low+(B_high-B_low)*integral_low^E(Y-B)/integral_low^high(Y-B)`.
Retain endpoints, units, source, damping/tolerance/convergence and all raw points;
nonpositive area or nonconvergence is refused. No clipping or endpoint guessing.
See [Shirley definition](https://goldbook.iupac.org/terms/view/09355) and
[background guidance](https://doi.org/10.1116/6.0000661).

XPS needs binding/kinetic energy, counts/CPS, high-resolution identity, previous
background and calibration history. Unknown previous processing holds the model;
double background subtraction is refused. Explicit `BE=hν-KE-φ+assigned_shift`
uses a declared instrument convention; no automatic C1s calibration. Descending
input requires an explicit paired working-copy reversal. No survey deconvolution,
chemical assignment, RSF quantification or area-to-population interpretation.
FTIR fitting requires absorbance. The numerical API's opt-in conversion
`A=-log10(percentT/100)` does not perform baseline/ATR/scattering correction.
Raman D/G-like peaks are synthetic examples, not a crystallite-size estimator.
