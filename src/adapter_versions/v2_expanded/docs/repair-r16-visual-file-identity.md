# Visual file identity repair

A preserved multi-application image naming run successfully renamed three files,
then rediscovered the destination paths. The tool surface only remembered source
paths, so it offered the renamed images again. A later rename replaced another
output. This is a state tracking failure independent of visual recognition quality.

The surface now follows each observed image through successful renames, using
resolved result paths when available. Rediscovery keeps the completed identity;
new files at the vacated path or changed comparable metadata require inspection.
Failed operations and failed verification do not complete a file. When no observed
images remain pending, normal completion controls are restored alongside search.
The model still chooses names and completion; the normal completion gate remains.

Validation: five new regression cases failed before the change. After repair,
107 related tests passed and Ruff/diff checks passed. Two additional filesystem
search ranking tests failed on both the prior frozen r15 and the development tree.
Preserved trajectory replay makes no model calls and is not an evaluation score.

Predeclared diagnostic cohort: image naming and ordinary file rename (124, 138).
A separately frozen full 189-task evaluation is required before score promotion.
Metadata detects observed changes but cannot guarantee identical bytes when an
external edit preserves size and timestamp and no content hash was observed.
