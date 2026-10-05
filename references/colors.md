# Baseline color choices

Seven qualitative identities, in order: red #B2182B, blue #2166AC,
green #1B9E77, purple #7560A8, orange #E4872A, gray #737373, pink #CC79A7.
The same identity colors its line, symbols and cloud. Stable series overrides
remain available. Seven colors are a display baseline, not a significance code.

Heatmap presets are packaged in assets/colormaps.json; no workspace dependency.
Set a plot's cmap to one of these names:

| Display name | Config name | Low → high |
| --- | --- | --- |
| Blue–white–red | redwhiteblue | Blue → white → red; neutral is the range midpoint |
| Purple–green–yellow | purplegreen | Purple → blue → green → yellow-green → yellow |
| Violet–orange–yellow | violetgold | Deep violet → purple → pink → orange → yellow |
| Rainbow | rainbow | Violet → blue → green → yellow/orange → red |
| Reversed rainbow | rainbow_r | Red → yellow/orange → green → blue → violet |

The two five-color presets preserve the supplied SVG stops at 0/25/50/75/100%.
Legacy keys reimu26/reimu27 remain exact aliases for purplegreen/violetgold.
Piecewise linear RGB interpolation is sampled directly at declared levels.
They are five-stop ramps; they are not aliases for the full viridis/plasma
tables. The color-board SHA is bound in the registry; no original board,
private path or research data is distributed. All Matplotlib named colormaps
and explicit hex lists remain available. Explicit cmap wins over the default.
Rainbow options do not silently replace an article's existing red-white-blue.

Native fill colors and the embedded strip share the same sampled hex palette.
The strip ascends bottom-to-top; increasing Z follows low-to-high color.
256 levels describes display quantization, not new data or resolution.
Changing a palette changes the displayed colors and requires regeneration;
it never normalizes or changes Z. Range, midpoint meaning, source nodes and
interpolation stay declared. Redwhiteblue needs >=3 bins to retain its neutral.

Run samples/colors.json for seven curves and five identical-grid map comparisons:

~~~sh
python scripts/ai2origin.py samples/colors.json --out /path/to/task/colors --backend python --font-file /path/to/arial.ttf
~~~

Use the native runner on the resulting plan for Origin output. Invented
axes/values are labeled in every caption. See VALIDATION.md for accepted scope.
