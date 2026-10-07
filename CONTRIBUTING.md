# Contributions

Use small, reproducible changes with a synthetic failing/successful fixture.
Preserve existing supported workflows and state the actual tested version.
Run the Python tests; only claim native acceptance after an actual licensed
Origin run, project reopen and inspection of the exported images.

Contribute only material you may share under the project's chosen license.
Keep provenance and third-party notices. AI-assisted contributions have the
same data, permission and verification requirements. No copyright transfer
or separate CLA is introduced here.

Do not commit raw research data, private paths, accounts, activation details,
working projects or unreviewed runtime logs. Report compatibility bugs using
minimal invented data and the exact software version.

## Development checks

Run these when changing or packaging the code:

```sh
sha256sum -c SHA256SUMS
python -m unittest discover -s tests
```

Install the analysis dependencies to run tests that need SciPy.
Compare two exports when changing a template, checking reproducibility, or
investigating a problem:

```sh
python scripts/ai2origin.py samples/demo.json --out work/repeat-a --backend python
python scripts/ai2origin.py samples/demo.json --out work/repeat-b --backend python
python scripts/check_reproducibility.py work/repeat-a work/repeat-b --config samples/demo.json
```

Use the same config, style, dependencies and font. Add `--svg` to both render
commands when testing vectors. These are maintenance checks; normal plotting
does not require a manual hash check or a full test run.
