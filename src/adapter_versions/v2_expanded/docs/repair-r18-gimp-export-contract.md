# GIMP saved-image export contract

A preserved image-to-document run searched for gimp.image.export and supplied
params.path/file_type plus target.path. The executor requires params.input_path
and output_path, but the model-facing catalog exposed an unconstrained params
object. The operation therefore failed before native execution.

The adapter-owned manifest now declares the real source, destination, loader and
JPEG quality fields. The catalog signature agrees with it. Unknown export fields
are rejected by the adapter validator instead of being silently ignored. Source
selection and output naming remain model decisions; the native export is unchanged.

Validation: 11 new contract cases failed before the fix. Afterwards 52 related
checks passed, including direct and forwarded schemas, parser validation and
native dispatch forwarding. Ruff and diff checks passed. A disposable real GIMP
VM exported a synthetic PNG to XCF and back to PNG with identical pixels and
unchanged inputs. No benchmark data or model requests in that smoke test.

Diagnostic cohort: image-to-document transfer and a neighboring image adjustment
workflow (115, 119). A separate full 189-task run uses the exact frozen source.
Other GIMP operations still lacking typed model parameter schemas are inventoried
outside runtime; this repair does not claim to fix every generic wrapper.
