# Checks

The repository tests cover input checks, source values, PNG/SVG export,
layout warnings and repeatability. See the [development instructions](https://github.com/yunyunFlow/Ai2origin/blob/main/CONTRIBUTING.md)
to run them from a source checkout. CI tests Python 3.10 and 3.12 with drawing
and optional-analysis profiles.

Inspect the actual figure before sharing it. Check labels, units, legends,
clipping and source points. Python layout reports flag intersections, text
outside the canvas and geometry that needs a manual check.

The bundled native workflow targets Origin 2021. Check worksheet values and
the saved/reopened project using the [native workflow](references/origin2021.md).
Other Origin versions, existing-project imports and vendor formats need an
appropriate adapter and output checks. Python SVG does not verify native SVG.

For a requested calculation, follow the relevant [method contract](references/analysis.md)
and keep its parameters, controls and residuals. Synthetic examples and good
fits do not establish a material mechanism.
