# Local font names

Arial is the default. Select fonts by an installed family name; Ai2origin
does not bundle, copy or download fonts. The system registry also discovers
Windows fonts available to WSL at `/mnt/c/Windows/Fonts`.

~~~sh
python scripts/ai2origin.py --list-fonts
python scripts/ai2origin.py input.json --out work/figure --backend python --font "DejaVu Sans"
~~~

`--list-fonts` prints a JSON array of available local family names without
reading a config, preparing a figure or writing outputs. If Arial or another
requested family is unavailable, choose an available local font explicitly.
No fallback family silently replaces the request. Unsupported label glyphs
also require a suitable installed font.

The receipt records the requested and actual family, local font filename and
SHA256. An explicit substitute is the recorded family. Optional SVG retains
editable text in that family; anyone editing it needs that font locally.
