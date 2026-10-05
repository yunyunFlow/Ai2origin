# Article figure survey

Checked 2026-10-04. Figure grammar only: no copied figure, digitized value,
published measurement or author sample name enters the synthetic generators.
Public recipes are independently assigned formulas. Original papers and
research data are not redistributed.

Battery overlays, bounded lookup 2026-10-05:

| Primary article | Actual read scope | Display decision |
| --- | --- | --- |
| [High-Voltage Flexible Aqueous Zn-Ion Battery with Extremely Low Dropout Voltage and Super-Flat Platform](https://doi.org/10.1007/s40820-020-0414-6), 2020 | Publisher/PMC text and indexed Fig.3b caption: charge/discharge profiles at multiple rates; direct full-size figure unavailable in this lookup | Multi-rate voltage–specific-capacity pure-line template; no published trace, capacity endpoint or plateau copied |
| [An aqueous electrolyte densified by perovskite SrTiO3 enabling high-voltage zinc-ion batteries](https://doi.org/10.1038/s41467-023-40462-z), 2023 | Publisher text and indexed Fig.5h/6b descriptions: cycle-dependent branches and cell comparison; direct full-size figures blocked | Keep cycle identity and voltage/capacity convention; capacity and polarization in our demo are independently invented |
| [Potential-dependent interfacial specific adsorption accelerates charge transfer in sodium-ion batteries](https://doi.org/10.1038/s41467-026-69559-x), 2026 | Publisher search-index description of rate-dependent GCDs; direct page/figure blocked, no full-text/visual-read claim | Broader battery context only; invented rate labels and charge/discharge pairing do not reproduce a sodium-ion experiment |

The query targeted voltage/capacity GCD overlays at different cycles or current
densities; these three primary records are a bounded sample, not an exhaustive
survey. Only figure grammar informs templates/battery.json. Recorded mass basis,
full-cell/reference voltage, branches and direction must be checked on real
data; do not normalize, reverse, translate or resample to mimic a paper.

Additional cross-domain sampling, 2026-10-04:

| Primary article | Actual read scope | Display decision |
| --- | --- | --- |
| [Permalloy nanostructures and hyperthermia](https://www.nature.com/articles/s41598-019-43197-4), 2019 | Publisher full text, magnetic measurement/method description and indexed hysteresis caption | Preserve field sweep branches; invented A/B hysteresis does not reproduce their nanostructures or losses |
| [Unicolored phosphor-sensitized fluorescence](https://www.nature.com/articles/s41467-018-07432-2), 2018 | Publisher search-index Fig.2 caption; direct page/figure access blocked, no full-text/visual-read claim | Separate wavelength-dependent absorption and PL; no spectra copied or normalization inferred |
| [Expanding bacterial colonies](https://www.nature.com/articles/s41467-025-60004-z), 2025 | Publisher full-text page and indexed OD600/replicate caption | Distinguish time-dependent optical density and viable-cell counts; synthetic growth curve is neither cells/mL nor evidence of viability |

Susceptibility, fluorescence-decay, dose-response and enzyme-kinetics recipes
are assigned generic functions, not validated reproductions of these papers.
No biological sample, replicate, fitted lifetime/IC50/Km or mechanistic result
is invented as experimental evidence.

| Primary article | Actual read scope | Template decision / boundary |
| --- | --- | --- |
| [Super Strong and Tough Hydrogels Constructed via Network Uniformization of Macromolecular…](https://doi.org/10.1002/adfm.202419161), 2024 | Local PDF Fig.2 p3 rendered/inspected; Fig.3 p4 caption/body text | Stress versus strain; units and loading direction matter. Toy curve does not infer modulus, fracture energy or toughness |
| [Chaotropic Anion and Fast-Kinetics Cathode Enabling Low-Temperature Aqueous Zn Batteries](https://doi.org/10.1021/acsenergylett.1c01054), 2021 | Local PDF Fig.3–5 captions/body; Fig.5 p6 rendered/inspected | Voltage-capacity branches, capacity/CE/cycling, CV and log-coordinate comparisons. Real voltage reference and mass basis are mandatory |
| [Ionic Selective Separator Design Enables Long-Life Zinc Iodine Batteries via…](https://doi.org/10.1002/adfm.202410712), 2024 | Local PDF Fig.2 EIS caption/body; Fig.5 p8 rendered/inspected | Nyquist, rate recovery, GCD and capacity/CE. Separate CE panel avoids an unsupported dual-axis adapter |
| [Operando neutron radiography reveals calendar aging-induced lithium redistribution…](https://doi.org/10.1038/s44456-026-00015-3), 2026 | Primary full-text page, Fig.3 discussion/caption | Condition-resolved DRT field; relaxation features alone have nonunique assignments. Toy DRT is independent of toy EIS |
| [Spatial quantification of dynamic inter and intra particle crystallographic heterogeneities…](https://doi.org/10.1038/s41467-020-14467-x), 2020 | Primary full-text page, diffraction description/captions | Coordinate-resolved diffraction display; invented scan index and invented peak positions in our XRD map |
| [Single particles as resonators for thermomechanical analysis](https://doi.org/10.1038/s41467-020-15028-y), 2020 | Primary full-text page, thermal characterization/captions | Mass and thermal response require separate quantities/units. Toy TGA and DSC assign shapes; no transition/enthalpy claim |
| [Controlling selectivities in CO2 reduction through mechanistic understanding](https://doi.org/10.1038/s41467-017-00558-9), 2017 | Primary full-text page, Fig.1 time-resolved response/FTIR contour caption | Time curves and spectrum fields accompany method-specific observations; toy conversion curve is no catalytic mechanism |
| [In-situ positive electrode-electrolyte interphase construction enables stable Ah-level Zn-MnO2 batteries](https://doi.org/10.1038/s41467-025-57579-y), 2025 | Primary updated full-text page read; GITT-specific text was not recovered in this bounded lookup | Electrochemical article context only; not evidence validating our GITT-shaped pulses |
| [Physics-informed neural network for lithium-ion battery degradation stable modeling and prognosis](https://doi.org/10.1038/s41467-024-48779-z), 2024 | Crossref identity and search-visible figure description; full-page access failed | Candidate context only, no full-text claim. Toy train/validation loss illustrates display only |
| [Tough and tear resistant hydrogel with a sandwich mineralized structure…](https://doi.org/10.1038/s41467-025-66423-2), 2025 | Crossref identity and search-visible figure description; full-page access failed | Candidate only; local hydrogel PDF above supplies actual mechanical figure inspection |

Crossref verified the six initial online DOI identities separately from article
reading. A successful metadata lookup does not establish full-text or visual
acceptance. The PDF survey verifies complete relevant captions and selected
actual figure pages; it is not a literature precision-read or a Knowledge
promotion. Methods/SI not inspected remain outside the acceptance claim.

GITT demo stores assigned current pulses and voltage relaxation-like shapes.
Real diffusion analysis still needs current, pulse/rest durations, electrode
geometry, active mass, equilibrium criteria and validity of the diffusion
approximation. DRT demos contain assigned Gaussian gamma curves, no inverse
problem, regularization choice, residual or uncertainty evidence. Bode source
stores a toy complex impedance and explicit log10 frequency; the independent
Nyquist arc is not presented as the same spectrum.

