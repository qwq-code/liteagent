# Atomic creation of a blank Writer document

Preserved failures repeatedly searched for document.create or create_new after
reading source data, but the public Writer catalog offered no blank-document
creation operation. The new document.create accepts only a destination path
(.docx or .odt), creates a native blank document, saves and activates it, and
returns its observed identity. Reading, transforming and inserting content remain
separate model-selected operations. Existing destinations, including dangling
symlinks, are rejected. The parent directory must already exist.

Example: adapter.call with adapter=libreoffice_writer, action=document.create,
payload.params.path=/home/user/Desktop/report.docx. Later editing can use the
returned identity URL; creation alone does not satisfy a content-transfer task.

Validation: 8 new tests failed before implementation. After implementation and
verification read-back checks, 54 related tests pass; Ruff and diff checks pass.
A disposable real LibreOffice VM verified both formats, subsequent separate
paragraph insertion, destination collision rejection, and preservation of another
open document with unsaved changes. No model or benchmark calls in native smoke.

Diagnostic cohort predeclared: source-data filtering, presentation text transfer,
and image-to-document transfer (109, 114, 115). All still need original evaluators.
A separately frozen full 189-task run follows the diagnostic run.
