# Public release checklist

- [ ] Preserve MIT and the confirmed public attribution yunyun.
- [ ] Read VALIDATION.md; do not promote untested templates/versions to PASS.
- [ ] Select only code/docs/styles and explicitly synthetic inputs/previews.
- [ ] Exclude qa/, work/, ZIP containers, OPJU working projects, session/temp receipts and logs.
- [ ] Inspect text, PNG/SVG metadata, local paths, private identifiers and links.
- [ ] Keep fonts, commercial binaries and third-party templates out of the bundle.
- [ ] Rebuild/check SHA256SUMS and verify every archive member against source.
- [ ] Publish only after the user's explicit publication authorization.

An ignore file is not a release allowlist. The local release archive is a
reviewable source bundle; it does not create a remote repository or release.

## Explicit source allowlist

Root files: DISCLAIMER.md, LICENSE, README.md, RELEASE.md,
SKILL.md, SOURCES.md, THIRD_PARTY_NOTICES.md, VALIDATION.md, WORKFLOW.md,
requirements.txt, requirements-analysis.txt and SHA256SUMS.

| Directory | Allowed file suffixes |
| --- | --- |
| agents/ | .yaml |
| assets/ | .json |
| references/ | .md |
| samples/ and templates/ | .md, .json, .csv, .png, .svg |
| scripts/ | .py, .ps1 |
| tests/ | .py |
| .github/workflows/ | .yml; explicitly reviewed portable QA only |

AGENTS.md and references/reuse.md stay local and are excluded. The release's
SHA256SUMS is the explicit file-by-file public selection (excluding itself);
archive members must equal that list plus SHA256SUMS. Folder/suffix rules
only bound candidates; they do not authorize future files automatically.

Repository-maintenance files (.gitattributes, .gitignore, CHANGELOG.md,
CONTRIBUTING.md, SECURITY.md) remain in the source, outside the portable bundle.
The GitHub candidate contains the same explicit portable selection plus these
five reviewed maintenance files, RELEASE.md,19 regression test modules and
.github/workflows/qa.yml. The four detailed contact sheets are a separate
optional gallery, not an installation or repository dependency.
These tests exercise the published implementation, not private projects.
Its SHA256SUMS binds every selected repository
file except itself. This selection is a local submission candidate; it does
not commit, upload, tag or publish anything. Preserve reviewed bytes on checkout
using the supplied .gitattributes before verifying hashes.
Keep current native recipe PNGs and original per-image validation records,
selected analysis previews. Detailed contact sheets stay in the optional gallery.
Duplicate Python PNG/SVG galleries remain local; regenerate them from configs.
Current records bind the included gallery. A new delivery may refresh synthetic
previews only after acceptance, recording the delta and preserving previous
bytes in the frozen prior delivery. Omitted Python previews are regenerable.

Review contents as well as names; reject unknown members and symbolic links.
The inventory is not recursive permission to bundle future private files.
qa/ is private even when it contains a historical public ZIP. Never package
the owner root wholesale or publish a handoff/local QA receipt.

Versioned delivery ZIPs are immutable. Their internal SHA256SUMS binds
the accepted delivery snapshot; checkout SHA256SUMS binds current public
source, excluding itself. Management notes can differ without invalidating
native image acceptance. Future release generations use a new filename.

## Installation-only selection

The slim installation ZIP excludes tests/, RELEASE.md and the five repository
maintenance files. They remain in the source checkout for development/review.
Runtime scripts, assets, task references, synthetic recipe sources, representative
gallery previews, validation records, installation instructions and legal/source
notices remain. Its own SHA256SUMS binds that exact installation selection.
Test the extracted installation with a temporary source test harness, then remove
the harness and require exact archive/inventory equality before freezing.
Repository review and installed-skill inventories are distinct; neither packages
qa/, work/, research originals, local receipts, fonts or commercial binaries.
