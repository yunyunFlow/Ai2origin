# Origin 2021 native route

Baseline: Origin 2021/2021b, numeric version 9.8, licensed Windows installation.
Other versions are opt-in trials, not implicitly certified.
The shipped runner uses built-in COM/LabTalk; it does not require originpro,
OriginExt, a cloud model or a downloaded graph template.

## Existing projects as input

OPJ/OPJU may contain original tables, derived geometry, fits and linked graphs.
Preserve the original hash and operate only on a separate copy. Identify the
requested books/sheets/columns and actual graph/plot bindings before extracting
or restyling; a plotted density or offset column is not automatically raw data.
Confirm units, row order, missing cells and prior transforms through numerical
read-back. Reopen/export the changed copy for its own native/visual acceptance.
Do not run embedded project scripts or silently import external linked files.

The included origin.ps1 creates a project from origin-plan.json; it does not
ingest or edit arbitrary existing projects. Existing-project intake needs a
specific adapter and real project fixtures; that capability remains HOLD.
Origin export images can still serve as references while verified associated
tables are processed with the supported mapper. This avoids claiming an OPJU
parser merely because the package can produce OPJU output.

## Prepare, inspect, run

From the repository root, with your existing Python environment:

~~~sh
python scripts/ai2origin.py samples/demo.json --out work/prepared --backend prepare
~~~

Then in native Windows PowerShell:

~~~powershell
.\scripts\origin.ps1 -Plan .\work\prepared\origin-plan.json
.\scripts\origin.ps1 -Plan .\work\prepared\origin-plan.json -OutDir .\work\native -Run -TimeoutSeconds 180
~~~

The first command reads the plan and registry/version only. It does not start
Origin, install anything or create outputs.
It also validates identities, worksheet dimensions/finite numbers, drawing
statements and colorbar asset hashes before any COM activation.
If local script policy blocks a reviewed script, use your organization's
approved execution method. A per-process invocation, where permitted, is:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\origin.ps1 -Plan .\work\prepared\origin-plan.json -OutDir .\work\native -Run
~~~

This does not persist an execution-policy or registry change. Do not change
machine policy just to run a figure example.
The second draws all declared plots in one owned project and exports their
PNGs, figures.opju and a receipt. Keep working outputs outside public samples.
Do not run the native adapter on an untrusted or manually injected plan:
inspect the generated drawing statements before use.

An explicit -OriginExe must match the actual COM server. Origin.Application
creates a new session; ApplicationSI may attach to an existing author session.
This runner additionally refuses a busy Origin environment, resolves both
32-/64-bit registry views, and does not modify registration. It requires a
new output directory and checks every imported numerical cell by read-back.

The transport runs in a bounded PowerShell job. On timeout or failure,
partial files are unaccepted. Cleanup uses only the recorded process ID,
start time and executable of this invocation; it never kills by process name.
If COM activation fails before ownership can be established, any unidentified
process is left intact and requires a separate identity check.
Work outputs can contain local session identity; do not publish that folder.

## Implemented layers

- XY: native line/scatter and explicit stored upper/lower bands.
- Heatmap: virtual matrix with explicit coordinate row/column. This avoids
  automatic XYZ binning; no implicit interpolation or aggregation is performed.
  Explicit bilinear display resampling is optional and separately recorded;
  the original grid is preserved in a Raw workbook and is not overwritten.
  Color range is checked after auto-rescaling. The color strip is a generated
  palette bitmap embedded into the project with independent editable labels.
  This follows a working 2021 recipe and avoids the tested Spectrum property
  failure. It is a disclosed hybrid colorbar, not a native editable Spectrum.
  A WSL/UNC source strip is copied to one exclusive native temp PNG for the
  image X-function, hash checked, embedded, then cleaned up by exact identity.
- Raincloud: precomputed Gaussian KDE half-cloud silhouette and all raw
  points; summary strokes are disabled by default. Geometry is imported without recomputation.
- Full cloud: bilateral KDE geometry and rain, including the vertical
  complete-contour template; this is not an Origin statistical Violin object.

Python is a preparation/optional preview tool. The native figures are
rendered in Origin and must be reviewed directly.
Python defaults to PNG; --svg explicitly adds its vector preview. This does
not change native PNG/OPJU delivery or certify native SVG.

Origin 2021 auto-repositions its reserved YL label during export. The runner
uses an ordinary editable AxisTitleY object, measures actual black text bounds
in a first export, and matches its gap to the X title/number gap within 3 px.
The final position is saved and must survive reopened export. This is layout
calibration only; it never edits data or axes. An axis without numeric group
labels is explicitly recorded as not applicable to the numeric-gap comparison.

## Version/feature acceptance

| Version | Stance |
| --- | --- |
| 2021 / 2021b | Target version; verify the exact installed build and actual samples |
| 2022+ | Try -AllowOtherVersion; repeat numerical, export and visual acceptance |
| 2020 and earlier | No blanket promise; verify COM/virtual-matrix/plot commands individually |
| macOS / Linux only | Python workflow works; Windows Origin native route is unavailable |

Modern documentation may show features absent in 2021. Do not assume a
2024 split-tiles heatmap exists in 2021. The official raincloud template lists
2021 as its minimum; negative-value binning has reported issues, so test it
instead of using its mere installation as evidence.

PNG/OPJU are the baseline native deliverables. If editable SVG is needed,
verify actual export capability/text behavior on that edition/build. A
PDF-to-SVG bridge may outline text; retain its source and label editability
accurately. Do not silently substitute Python SVG for requested Origin SVG.
The runner reopens its saved OPJU, rechecks numerical sheets and expected
graph pages, and reexports every graph as *-reopened.png. Compare actual
image pixels (PNG metadata may differ), then inspect the reopened exports.
This verifies saved data/page/rendering presence. Exact future editing of
every Origin feature still needs the relevant consumer-specific acceptance.
Version 0.1.3 additionally tests changed/restored XY, heatmap, cloud-observation,
cloud-fill and DRT worksheet bindings. Each edit changes pixels and restores
exactly without saving the diagnostic project. Prepared KDE/interpolation is
not automatically recomputed when its raw inputs are edited; regenerate the
plan from the source CSV/config for that change.

The reserved missing-value sentinel -1.23456789E-300 is used only for padded
geometry, never as zero or as an observation. A real input equal to that
sentinel is refused by the native route.

Version 0.1 uses plain-text labels. Quotes, LabTalk substitutions, multiline
labels and rich-text control escapes need an explicit adapter; do not pass
untrusted strings as scripts. Literal Unicode units are acceptable where the
installed font/version renders them correctly.
