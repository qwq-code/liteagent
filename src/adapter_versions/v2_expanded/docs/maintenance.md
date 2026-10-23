# Maintenance Guide

Updated: 2026-09-15

[Back to project index](index.md)

For the active serial API goal, use the independent worktree and accepted/candidate
branch procedure in the [API review](archive/v337-workflow-api-review-20260915.md).
The integrated development tree and all historical full-run numerators remain preserved.
Retest only the current API's affected task and leave skipped APIs unchanged on the accepted branch.

## Current Sources Of Truth

| Question | Canonical source |
|---|---|
| What evaluation or repair is active? | root `GOAL.md` and [`current-repair-reference.md`](current-repair-reference.md) |
| What architecture is active? | [`architecture.md`](architecture.md) |
| What is the promoted baseline? | `experiments/baselines/current.json` and [`evaluation-protocol.md`](evaluation-protocol.md) |
| What happened in one repair? | its immutable experiment directory plus the dated entry in `project-progress.md` |
| What rules always apply? | root `AGENTS.md`; do not duplicate changing scores, endpoints, or queue counts there |

The user cancelled the pure-Qwen fixed-189 run on 2026-09-15. Condition
`qwen35-all-roles-fixed189-20260915-v1` retains 80 passes among 148 terminal outcomes and 41 tasks without
a terminal result; it is incomplete. The supervisor and workers have exited. Use the
[report](archive/all-qwen-fixed189-20260915.md) and [current reference](current-repair-reference.md).
Both inference roles select Qwen explicitly; the existing `provider=holo` label names only the grounding
implementation. No runtime or validator rewrite is required for the model switch.

The all-Holo **95/189 (50.26%)** result and its [94-task repair ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
are paused and preserved at 32 isolated PASS, 48 skips, 118 actual attempts and 80/94 processed, with Order 151
prepared/unrun. The new full run does not resume this queue or consume its planned attempt. Individual repair
still prohibits regression/control episodes. The earlier Qwen-Holo **119/189** and promoted v337 pointer remain
unchanged. Never add isolated repairs to any full-run numerator.

The independently released v337-derived `clean-hardened-v2` source (158/189) is linked through remote
`v337-archive`, branch `codex/archive-v337-clean-hardened-v2`, and pinned tag
`archive/v337-clean-hardened-v2-20260816` at commit `83530dd`. The original two commits and all 374 sealed
source blobs are present in this project's Git. See [archive identity and checkout instructions](archive/version-control.md#linked-v337-derived-release).
This release is distinct from original v337 (157/189) and does not replace the active runtime or baseline pointer.

The historical hybrid repair source is preserved by tag `archive/qwen35-holo31-hybrid-20260831-a1dfe6` at commit
`88484bcea3238c53fec993eb312f7d9269ccda79`. Its active-v2 seal is documented in the current reference page.
Inspect or restore it in a separate detached worktree; never reset the shared dirty worktree. The new archive
remote does not back up this hybrid history, and the tag does not contain the three referenced LFS payloads. Until a durable remote or
independent backup exists, preserve the local `.git/lfs/objects` store and verify it with `git lfs fsck`.

### Documentation Update Checklist

For an isolated task repair, add or update its dated report, add the report to `docs/archive/index.md`, and update
`project-progress.md`; do not edit the full-189 numerator or the frozen repair-reference page. For an integrated
repair-reference rerun, also update `current-repair-reference.md`, `index.md`, and `evaluation-protocol.md` with
the complete status denominator and new source archive. Update the promoted baseline pointer only through an
explicitly authorized promotion. Date-specific environment handoffs are snapshots; model, endpoint, VM, and
concurrency facts come from the condition config.

## Where Changes Belong

| Change | Location |
|---|---|
| Runtime compatibility imports | `integrations/lite_agent/runtime.py` (facade only) |
| Generic action ranking and staging | `integrations/lite_agent/action_selection.py` |
| Unresolved single-local-input discovery stage | `integrations/lite_agent/local_file_discovery.py`, integrated by `action_selection.py` and `tool_surface.py` |
| Source edit plus persisted-output phase control | `integrations/lite_agent/source_execution_semantics.py`, integrated by selection, surface, protocol, and semantic requirements |
| Natural-language VS Code configuration staging | `integrations/lite_agent/vscode_configuration_semantics.py`; application mappings stay in `vscode_adapter/` |
| Visible terminal-output staging | `integrations/lite_agent/terminal_output_semantics.py`; live directory resolution and execution stay in `os_adapter/active_directory.py` and `visible_terminal.py` |
| Cross-application spreadsheet composition | `multi_apps.adapter.call` routes each model-selected read or mutation to `calc_adapter/`; Multi-Apps has no column-combination or batch-table facade |
| Thunderbird filter intent and public action staging | `integrations/lite_agent/thunderbird_filter_semantics.py`; native conversion and persistence stay in `thunderbird_adapter/filter_contract.py` |
| Verified producer-to-consumer local path handoff | `integrations/lite_agent/verified_artifact_handoff.py`; producers and consumers remain in their owning Adapters |
| PDF inspection and extraction | `os_adapter/pdf_tools.py`; LiteAgent may retrieve the two public contracts but must not plan or loop over sections |
| PDF AcroForm fields | `os_adapter/pdf_forms.py` owns paginated field metadata and one-output filling of explicit text field/value pairs. Field mappings, source-data reads and filenames remain model-selected; unselected fields and source pages are preserved. |
| Model-authored alternative search after a repeated block | `integrations/lite_agent/recovery_alternative.py`, integrated by `tool_surface.py` and `execution_engine.py` |
| Visible application-launch verification | `os_adapter/worker.py` and `verifier.py`; verify action params/results without reading instruction or evaluator state |
| Default GNOME Terminal preferences | `os_adapter/terminal_profile.py` owns read-only key/value inspection and one model-selected scalar setting; native GSettings resolves the live default profile, and window operations remain separate |
| Application-semantic overlap between public actions | `integrations/lite_agent/impress_tool_routing.py`, `impress_cover_semantics.py`, or `impress_semantics.py` |
| One-task-macro audit state | `experiments/analysis-generic-tool-granularity/one-task-macro-ledger.json`; immutable per-condition audit and source-seal files stay beside it |
| Homogeneous Impress all-textbox completion | `integrations/lite_agent/impress_textboxes.py` and `impress_role_formatting.py`; heterogeneous targets use explicit `shape.format_text` calls |
| Impress physical image insertion staging | `integrations/lite_agent/impress_image_insertion.py`; unit conversion and slide resolution stay in `impress_adapter/image_contract.py` and `slide_reference.py` |
| Impress personal-information cleanup | `presentation.inspect` exposes live text/selectors and each model-selected `shape.delete` removes one observed object; there is no content classifier or cleanup macro |
| Impress canvas dimensions | `impress_adapter/` owns explicit `presentation.set_page_size` for slides and masters; shape layout and save remain separate model-selected operations |
| Writer paragraph/table composition | `writer_adapter/` owns `document.inspect`, `table.read`, `paragraph.set_format`, exact `paragraph.replace_text`, literal `text.find_replace`, explicit `document.append_paragraphs`, and `table.set_cell_text_color`; LiteAgent only retrieves and projects those contracts |
| Matching-file copy composition | `os_adapter/` owns read-only `filesystem.find`, one-path `filesystem.create_directory`, and one-file `filesystem.copy`; the model may explicitly set `create_parents=true` for that exact output file, with default behavior and replacement policy unchanged; generic retrieval handles only lexical recall and negated-operation suppression |
| Age-based file organization composition | `os_adapter/` owns read-only `filesystem.find`, one-path `filesystem.rename`, and one-file gzip `archive.compress_file`; the model owns time classification and every exact source/destination pair |
| Explicit file-permission composition | `os_adapter/permissions.py` owns `filesystem.set_permissions`; `filesystem.find` discovers ordinary files, while the model supplies every exact path and one shared mode |
| Reviewed cross-Adapter read support | `integrations/lite_agent/generic_routing.py` and `tool_catalog.py` expose bounded public routes; the model selects each route and argument, while deployment attests every owning Adapter and never transfers a result into a later call |
| Git and other finite CLI composition | `os_adapter/` owns one-command `command.run`; `generic_routing.py` and `tool_catalog.py` provide generic command/resource discovery only, while the model supplies each argv and sequence step |
| Model tool surface and recovery tools | `integrations/lite_agent/tool_surface.py` |
| Model messages and proposal transport | `integrations/lite_agent/agent_protocol.py` and `model_client.py` |
| Same-VM soft restart and bounded recovery projection | `integrations/lite_agent/episode_control.py`; reasoning summaries belong in `reasoning.py` |
| Runtime state and evidence | `state_model.py`, `state_core.py`, `state_calc.py`, `state_impress.py` |
| Request signatures and normalization | `integrations/lite_agent/runtime_policy.py` |
| Instruction operation classes | `integrations/lite_agent/instruction_semantics.py` |
| Reusable intent, staged action, or semantic argument check | a focused `integrations/lite_agent/*_semantics.py` module |
| Adapter-result field extraction | `integrations/lite_agent/observation_fields.py` |
| OpenAI-compatible model transport | `integrations/lite_agent/model_client.py` |
| Tool schema and retrieval | `integrations/lite_agent/tool_catalog.py` or a focused extracted module |
| Adapter execution policy and guest HTTP | `integrations/lite_agent/adapter_executor.py` |
| Adapter result compaction/context hints | `integrations/lite_agent/adapter_results.py` |
| Completion schema and shared evidence policy | `integrations/lite_agent/completion_policy.py`, `generic_completion.py` |
| Reusable semantic completion coverage | `integrations/lite_agent/semantic_requirements.py` |
| Application operation | the relevant `*_adapter/` |
| Native desktop window readiness | the relevant Adapter UI module, such as `thunderbird_adapter/ui.py` |
| Docker/KVM allocation and port discovery | `integrations/openapa_osworld/provider.py` |
| Screenshot capture validation and episode classification | `scripts/run_lite_agent_pilot.py` |
| VM lifecycle | `scripts/run_lite_agent_pilot.py` |
| Strict-only Runner helpers and loaded-source boundary | `scripts/strict_runner_support.py` |
| Agent/evaluator data separation | `scripts/evaluation_boundary.py` |
| Strict guest package policy | `scripts/strict_deployment.py` plus each `deploy_host.py` |
| GUI schema and command conversion | `integrations/lite_agent/gui_actions.py` |
| Holo visual grounding and delegation boundary | `integrations/holo_agent/grounding.py`, `gateway.py`, and `tools.py` |
| Strict evidence audit | Per-run worker audit records/manifests in the immutable result directory; condition checks via `scripts/frozen_condition.py`; promotion-gate host audit via the separately sealed `experiments/work/audit_hybrid_schema_v5.py` |
| Source-tree seal and frozen-condition enforcement | `scripts/condition_seal.py`, `scripts/frozen_condition.py` |
| Prospective config generation | Hand-authored condition JSON validated by `scripts/frozen_condition.py` (historical freeze helper is not in this checkout) |
| Trusted baseline promotion | Immutable baseline record plus explicit review of `experiments/baselines/current.json` (no standalone promote helper is shipped) |
| Offline baseline failure taxonomy | Dated reports and `experiments/analysis-*` artifacts (historical analyzer is not in this checkout) |
| Parallel scheduling | `scripts/supervise_lite_agent_parallel.py` |
| Baseline pointer and promotion records | `experiments/baselines/current.json` and `experiments/baselines/*.json` |
| Current documentation | `docs/` |
| Detailed historical report | `docs/archive/` |
| Raw run output | a new directory under `experiments/` |
| Model-free public API validation | `scripts/run_direct_api_validation.py`; analysis ledger under `experiments/analysis-v337-bounded-granularity/`; never the Agent baseline registry |

## Module Selection

Use the smallest owning module and keep dependencies flowing toward application-neutral helpers:

| Need | Start here | Do not put it in |
|---|---|---|
| Add a reusable application operation | relevant `*_adapter/` schema, manifest, worker | `runtime.py`, `tool_surface.py` |
| Expose or search an existing operation | `tool_catalog.py` and focused routing tests | an Adapter worker or task parser |
| Track observed state or read-back | `state_calc.py` or `state_impress.py` | model messages or evaluator code |
| Change shared completion evidence | `completion.py`, `generic_completion.py` | a task-specific branch in execution |
| Check explicit semantic subgoal coverage | `semantic_requirements.py` plus counterfactual parser tests | argument injection or an evaluator oracle |
| Reject/retry an executed proposal | `execution_engine.py`, `runtime_policy.py` | application semantics |
| Parse a user instruction into operation classes | `instruction_semantics.py` | `runtime.py` or a task-ID lookup |
| Stage dependent public actions or reject an inconsistent call | a focused `*_semantics.py` module | Runner argument rewriting or task plans |
| Ground one unresolved local input before consumption | `local_file_discovery.py` plus counterfactual surface tests | A guessed path, task lookup, or Runner-filled argument |
| Discover files from the live active VS Code workspace | generic `tool_catalog.py` retrieval plus `vscode_adapter/workspace_discovery.py` | A dedicated instruction parser, forced consumer sequence, guessed root, task lookup, or Runner-filled glob |
| Stage source read/reference/edit/capture/read-back | `source_execution_semantics.py` plus counterfactual phase tests | A task plan, fixed filename, expected output, or Runner-selected call |
| Stage a natural-language VS Code setting | `vscode_configuration_semantics.py` plus the owning `vscode_adapter` semantic contract | A parsed value in LiteAgent or a task-shaped raw settings key |
| Run a finite command with visible terminal output | `terminal_output_semantics.py` plus `os_adapter/visible_terminal.py` | A shell string, inferred argv, fixed directory, or expected output in LiteAgent |
| Combine ordered single-column spreadsheets | model-selected Calc reads and writes reached through `multi_apps.adapter.call` | A combined facade, inferred paths/order, or Runner-generated values |
| Require complete batch tables and explicit sort/save/read-back | owning Calc actions reached through `multi_apps.adapter.call` | Extracted values, expected rows, inferred paths, or Runner-generated sort arguments |
| Configure a Thunderbird filter | `thunderbird_filter_semantics.py` plus `thunderbird_adapter/filter_contract.py` | Raw native filter text, an inferred condition, task-specific folder/name, or Runner-repaired arguments |
| Ground a consumer path from a prior verified artifact | `verified_artifact_handoff.py` plus producer/consumer counterfactual tests | An instruction-derived filename, preferred enum member, task lookup, or Runner-filled path |
| Compose contact-record cleanup | `presentation.inspect` followed by explicit `shape.delete` calls for observed selectors | A content-classification macro, inferred icon association, fixed shape path, or task-specific object list |
| Convert a public representation to an application identifier | the owning Adapter contract | LiteAgent or Runner mutation of model arguments |
| Compose a Writer document from text sources | owning file reads followed by explicit `document.append_paragraphs`/`paragraph.replace_text`, formatting, and save calls | A multi-file join macro, file-order parser, implicit formatting, or Runner-selected sequence |
| Copy a discovered file set | `os_adapter/` read-only `filesystem.find`, optional `filesystem.create_directory`, then one `filesystem.copy` call per exact pair | A search-and-copy macro, inferred destination tree, hidden flattening policy, or Runner-generated mappings |
| Move and compress a classified file set | `os_adapter/` read-only `filesystem.find`, then one `filesystem.rename` or `archive.compress_file` call per exact pair | A clock-based classifier, implicit discovery, derived basenames/destinations, or a combined organize workflow |
| Change permissions on a discovered file set | `os_adapter/permissions.py` through exact-path `filesystem.set_permissions` | An implicit current directory, recursive traversal, glob expansion, hidden target classification, or Runner-owned chmod plan |
| Drive a native file chooser | the owning Adapter UI module with observed readiness | fixed sleeps followed by blind typing |
| Fix a parallel Docker container race | `integrations/openapa_osworld/provider.py` plus provider tests | task routing or a per-task retry |
| Handle a missing screenshot | bounded Runner observation validation | `Path.write_bytes` on an unchecked value |
| Change the model request shape | `agent_protocol.py`, `model_client.py` | an Adapter |

`runtime.py` is deliberately not an implementation target. Its only job is compatibility re-export. A new
import from `runtime.py` is acceptable while migrating a caller, but new behavior must be added to the focused
module and covered there directly. Focused boundary tests, especially `tests/test_clean_boundaries.py`, enforce
the facade and dependency direction; do not cite a layout-check script that is not present in the active tree.

## Adding an API

1. Read the instruction, evaluator, and golden offline if useful.
2. State the application-level capability without mentioning task identity or the answer artifact.
3. Define a parameterized schema and deterministic read-back.
4. Implement it in the owning Adapter, not in LiteAgent planning code.
5. Add focused positive and negative contract tests. If the API was informed by golden semantics or has an
   overfitting history, include suitable paraphrased, different-value, or structurally different cases; require
   the full three-way set for promotion-quality evidence rather than every small repair.
6. Verify the deployed runtime contains no golden file, answer mapping, or fixed task constants.
7. Record the evidence without replacing prior failures.

Before adding or retaining a convenience API, ask whether one call can complete an entire benchmark instruction.
An operation that hides discovery plus several independently parameterized mutations must be split even when the
model supplies a top-level batch object. Homogeneous collection operations are acceptable only when they apply
one semantic rule over explicit model-selected members and have structurally different counterfactual tests.
Record a convenience API with task-level scope risk in the granularity ledger before treating it as a clean
candidate. Freeze a new audit and source seal before a scored candidate run, not before ordinary offline repair.
Baseline promotion requires its stable small condition and explicit fixed-189 authorization. The separately
authorized 2026-09-15 pure-Qwen exploration reuses existing checks; it does not require a new promotion campaign.

For filesystem composition, require one exact source and destination in every mutation call. Each singular API
validates its pair before writing; the model owns the complete sequence and must not receive a Runner-generated
batch plan. Keep discovery, classification, movement, compression, and deletion as separately selected
semantics. Internal verification may hash or reopen content, but those implementation details must not become
answer-bearing model output.

Permission batches follow the same rule: every regular-file path must be explicit, symlinks and directories fail
before mutation, and one shared mode is the only homogeneous operation. Keep prior modes long enough to roll back
a partially applied batch. Do not accept roots, recursion, globs, or an active-terminal selector on the mutation
API; those belong to separate observable discovery.

When a frozen/scored composition validation fails, preserve the result and classify whether discovery, argument
use, sequencing, or completion evidence failed. Do not repair the model call, inject observed paths, restore the
old macro, or silently rerun the same frozen condition. A later generic improvement requires a new source seal and
a new prospectively frozen affected/control directory; ordinary offline diagnosis may use synthetic fixtures.

When a target mechanism succeeds but an unrelated control fails, record both facts separately. Retain a generic
fix only when focused tests and the target trace support it, but do not call the frozen condition stable or
advance to a larger gate. Freeze the next hypothesis around the actual residual factor rather than rerunning the
same condition. For overlapping semantic and exact-selector tools, use counterfactual routing tests that cover
instruction-level descriptors, explicit observed identities, and unrelated negative intents; never fill the
selector for the model.

v390 is the reference implementation of that rule. Its policy suppresses only the overlapping exact action from
an instruction-level semantic fit surface; explicit model search or identity grounding restores it. Any extension
must include paraphrased semantic positives, explicit-selector counterfactuals, unrelated negatives, single-domain
and Multi-Apps search coverage, and unchanged model-call-to-payload integrity checks.

Every action dispatched through a worker must have nonempty default verification or require an explicit verify
contract. Add a worker/verifier test that rejects at least one false-positive result. An implemented action with
an empty default check list fails closed and must not be treated as a model failure or accepted from evaluator
reward alone.

When the application supplies a stable environmental default, document it as part of the public contract and
resolve it inside the Adapter. Examples are the visible terminal working directory or a semantic keybinding
operation's natural VS Code trigger condition. Do not make the model repeat a redundant field that can conflict
with the operation it already selected.

Keep semantic destination components separate when that is the natural application contract. For example, a
workspace-save action may accept a model-selected directory and name while the Adapter appends the documented
`.code-workspace` suffix and resolves the observable active project. If an experiment accepts filesystem path
equivalence, freeze that comparison rule before launch and use it only for offline acceptance. The captured
model call and executed event must remain auditable; any declared Adapter/Gateway representation conversion must
preserve the model-selected semantic values, record its provenance, and be compared canonically at the execution
boundary. Do not silently replace, infer, or inject a semantic argument.

## LiteAgent Rules

- Do not add new `requested_*` task parsers to `runtime.py`; reusable operation parsing belongs in
  `instruction_semantics.py` and must remain task-identity-free.
- Do not let completion logic reconstruct a benchmark answer.
- Semantic completion checks may compare instruction-derived requirements with successful model-selected calls,
  but may only reject completion and request replanning. They must not execute a missing action or fill its
  parameters.
- Do not treat an unstated semantic selector as an instruction fact. If the instruction says only "picture" but
  live application inspection distinguishes foreground content from a slide cover, the model must select a live
  target descriptor; LiteAgent must not lock a guessed role and reject a later evidence-grounded correction.
- Do not infer an overwrite policy only from missing instruction wording. Preserve the model-selected policy and
  let the owning Adapter apply it to live state. A Runner may reject an explicit protection conflict observed
  through a public read API, but it must not replace `preserve` with `replace` or the reverse.
- Focused semantic modules may return required action names or validation errors, but must not parse answer
  values into tool arguments, choose files, or turn an instruction into an executable plan.
- When two public facades overlap, disambiguate them from instruction-derived public action names in a focused
  module. Preserve genuinely combined operations and explicit tool-search recovery; never manufacture fields.
- A discovery-only surface may be selected from instruction semantics, but it must release only after a
  successful model-selected read-only discovery call. Rejected calls remain truthful failures; never infer the
  root, glob, returned path, consumer action, or output path for the model.
- A source-output phase may advance only from successful verified model-selected events. A named supporting
  document can be required by public instruction semantics, but its path, the source edit, argv, stdout path,
  provenance, read-back path, and completion claim must remain model-selected and unchanged.
- A VS Code semantic classifier may stage a reusable action name, but it must not parse a boolean, number,
  severity, pattern, or raw setting key from the instruction. The model selects those public fields; stable key
  translation and deterministic read-back belong behind the owning Adapter contract.
- Thunderbird filter calls must state `condition_mode` and `conditions` consistently. LiteAgent may stage the
  semantic action but never infer a condition or destination; the Adapter converts only accepted model-selected
  semantics to native storage and verifies the persisted rule.
- A downstream typed path may enumerate only compatible local files from preceding successful and verified
  Adapter results. The model must select one enum member unchanged; LiteAgent may reject an unobserved path but
  must not choose, inject, rewrite, or automatically execute a consumer call.
- PDF work must separate read-only `pdf.outline.inspect` from one-output `pdf.pages.extract`. Never infer a
  filename, page range, backend, overwrite policy, or repeated extraction sequence in LiteAgent. The Adapter may
  reject an existing destination when the model did not explicitly select overwrite, but it must not silently
  reuse or compare that file as a reference answer.
- After a repeated blocked action, a model-authored search may explicitly request an alternative. The next
  catalog surface may omit only that currently blocked action; it must not choose or rank a substitute on behalf
  of the model, and the omission expires with that recovery turn.
- Keep the public `propose_done` schema and Runtime validation on the same definition; malformed, truncated, or
  contradictory completion calls must fail closed and remain visible to the model as truthful state.
- Audited Holo GUI results may support an explicit completion claim through the existing deferred terminal
  audit. Do not demand an extra Adapter mutation as proof of GUI work. Later read-only checks preserve that
  evidence; later Adapter writes restore API completion checks. A command with stdout_path is a write.
  A GUI event alone must not infer completion or restrict the ordinary tool surface.
- Keep safety checks independent and fail closed.
- Treat `AdapterExecutor` as the final policy boundary; forbidden calls must be rejected before HTTP.
- Enforce the same policy inside generic Multi-Apps forwarding so a nested call cannot bypass the host gateway.
- Keep task identity out of final serialized model messages and tools, not only out of the system prompt.
- Prefer small modules with one ownership boundary over large utility collections.
- Preserve stable public imports while moving implementation.
- Unit-test every extracted module directly and retain integration tests through the old public entry point.
- Writer table.set_cell_text_color permits repeated explicit cell names because its shared-color operation is
  idempotent. Keep the list unchanged through dispatch and response; cells_changed counts distinct targets.
- Successful read-only calls may be repeated with unchanged model arguments to refresh an observation.
  Do not reject them as duplicate writes or replace them with cached results. Reuse the existing
  equivalent-read stall policy for loops; actual read failures keep the ordinary error/recovery path.
  Selection and catalog search must not suppress parameterless inspections solely because they succeeded.
- A no-progress window must contain events from one retry. Keep earlier events as evidence without letting
  their stall immediately terminate a same-VM soft restart; global limits and repeated-error blocks still apply.
- Command stall identity uses the existing canonical forwarding parser for argv/stdout_path. Reading only an
  adapter.call envelope loses distinct operations; terminal-mode-only churn remains the same operation.
- When moving a method, keep one compatibility path and add a focused test that exercises both the focused
  module and the `runtime.py` re-export. Do not duplicate the implementation in both files.
- After a successful instruction-relevant mutation, expose only the persistence/read-back actions still needed
  by the generic completion gate. Do not rely on the model to stop repeating a completed mutation.

## Model-Facing Schemas

- Writer `paragraph.split` accepts one literal or an ordered list of up to 32
  model-selected literals in one paragraph. Resolve successive first matches
  before editing, then insert native breaks in reverse offset order. Preserve
  source characters and the raw literal/list, report each offset and final
  right-paragraph index, and never infer sentences or subsequent calls.
- Writer tab insertion remains a separate literal `text.find_replace` call with a model-selected anchor.
  Keep complete-paragraph replacement distinct and retain native `document.inspect.page_layouts` measurements
  in the model context; page body width does not include paragraph-indent or column adjustments.
- Calc `pivot.create.destination` preserves A1 anchors and supports explicit
  `{below_range, blank_rows}` placement in the selected sheet. Keep its schema
  in the owning Calc module; the Adapter records the requested object and
  resolved A1 cell. Never infer the reference, gap or subsequent pivot call.
- Use structured semantic fields instead of raw LibreOffice/UNO filter strings or similar expert escape hatches.
- Represent physical dimensions as `{value, unit}` and convert them only inside the owning Adapter. If an action
  supports equivalent zero-based and one-based target references, accept both only when consistent, preserve both
  fields unchanged, and reject conflicts at both strict-semantic and Adapter boundaries.
- Keep optional fields out of the strict schema when omission is the deterministic application default.
- Prefer one complete semantic operation over multiple correlated enums when one combination defines the
  application's stable behavior. Verify counterfactual operations use different mappings.
- Avoid regex features unsupported by the vLLM guided-decoding compiler, including look-around assertions.
- The deployed xgrammar 0.2.4 treats patterns as full-string matches. Express path continuations explicitly
  (for example, ^/.* rather than ^/) so a prefix rule does not force the model to emit only a bare root.
  Preserve the owning Adapter's existing path semantics and validation.
- Run a real endpoint preflight with the complete post-inspection tool set; `jsonschema` validation alone does
  not prove that the serving stack can compile the schema.
- A schema compiler failure is `environment_failure` and requires a new result directory after the fix.

## Git Source Versioning

The root Git repository is authoritative for source changes after the 2026-08-27 import. Commit one coherent
implementation hypothesis at a time. A clean scored or promotion condition records `source_git_commit` and
`source_dirty: false`; an exploratory condition may use a dirty tree only when it records the source seal and dirty
status honestly, is marked non-promotable, and is never reused as baseline evidence. Do not create copied source
trees for v-numbered experiments. Tags are reserved for promoted baselines and other meaningful immutable milestones.

Raw trajectories, screenshots, serialized model calls, videos, and evaluator artifacts remain immutable under
`experiments/` but are ignored by Git. Git tracks experiment configs and compact baseline records. Never use
`git clean` as an artifact-retention mechanism. See [Version Control](archive/version-control.md) for the complete
boundary and the known v337/v386 history limitations.

## Experiments

- The supervisor forwards explicit --temperature to each worker and records it in result metadata.
  Its default remains 0.0. A different value must match protocol.temperature in a newly sealed
  condition; the existing worker condition check enforces that match. Holo temperature is separate.
- Existing experiment directories are immutable.
- For a scored/frozen comparison, a changed prompt, tool set, model, Adapter version, max steps, VM, or concurrency
  requires a new directory. A local test or diagnostic scratch change does not need a result directory by itself.
- Use a descriptive prefix in new experiment names: `generic-only-` for strict API-only comparisons and a distinct
  `qwen35-holo-`/hybrid prefix for conditions that include Holo delegation. The name must not imply promotion status.
- Never select a best attempt as a single-run baseline.
- A full baseline config must set its candidacy and promotion authorization before the first full-run result
  exists. A completed development run may remain descriptive evidence but cannot be relabeled prospectively.
- Keep task ID in internal metadata and filesystem naming only; strip it from model-visible content.
- A frozen validation config is immutable. A generic fix discovered during validation requires preserved v1
  evidence and a new config/result version, not an edit to completed tasks or a replacement task.
- If a frozen config cites a mutable analysis ledger, freeze an immutable snapshot or embed the exact selected
  records before launch. Do not edit a cited source path while its run is active.
- If a frozen ledger snapshot later proves to contain a bookkeeping error, preserve it unchanged, add an
  immutable correction record, prove the runtime config and actual selection separately, and repair only the
  mutable ledger. Never silently replace the cited snapshot.
- A stopped partial run remains stopped. Do not resume it into a changed code condition or report its terminal
  subset as a success rate.
- Classify failures only after strict worker audits pass, using preserved routing records, manifests, dated reports,
  and `experiments/analysis-*` artifacts. The historical `analyze_clean_baseline_failures.py` helper is not in this
  checkout; all such output is diagnostic and must never be imported by Runtime code or fed back into model requests.

## Baseline Bookkeeping

Read `experiments/baselines/current.json` first. It points to the current immutable promotion record; do not
infer the baseline from the newest directory name or the highest score. The record is the compact index for the
full seal and raw evidence, and its hashes must be checked before reporting a score.

When a candidate is ready, create a new record and a new raw-result directory, verify the complete promotion
gate, and update the pointer last. Never edit `v337.json`, `v335.json`, `v252.json`, their seals, or any raw trace. A failed,
interrupted, or changed-condition run remains diagnostic evidence and must not replace the pointer. Keep the
active docs' score, model, condition, and pointer synchronized; detailed failure lists belong in `docs/archive/`
or the machine-readable analysis directory.

The current trusted pointer resolves to v337. v335 is immutable descriptive evidence only; its additive
admissibility correction is `experiments/analysis-v335-trust-boundary-adjudication/manifest.json`. Do not edit
the old v335 promotion record to express that correction.

## Environment Reliability

- The supervisor's `--min-free-gib` defaults to 30 GiB, as authorized on 2026-09-05.
  Its existing disk check stops workers when available space falls below that threshold;
  an explicit CLI value overrides the default. Historical runs retain their recorded limits.
- Treat VM allocation, screenshot capture, endpoint availability, evaluator transport, and artifact fetch as
  environment boundaries. They may retry only within explicit bounded policies and must never change model
  actions or application arguments.
- When enumerating Docker containers under concurrency, use low-level summaries that already contain published
  ports. Do not enumerate high-level objects and inspect each one afterward; another worker can remove a
  container between those operations.
- Require non-empty byte-like screenshot data before persistence or model use. A supplied observation plus two
  further fetches is the current fixed budget; exhaustion is a typed `environment_failure`.
- If screenshot capture fails after an application action, persist the model call and executed event before
  terminating. Do not lose an executed mutation or relabel it as a model failure.
- Every environment fix needs a counterfactual unit test and a new immutable real-task recovery directory linked
  to the original preserved failure. It does not justify replaying or overwriting the failed trace.

## Native Desktop UI

- VS Code debugger verification keeps its existing active-session predicate,
  but reports an observed active-to-inactive transition as started then ended.
  Variable context preserves live item names/count/session before whole-body
  compaction. A variable read does not execute code or expand native scopes;
  breakpoint placement and any subsequent execution remain model-selected.
- Observe the expected native window before sending input; fixed sleeps are not readiness evidence.
- Activate the observed window, then focus its location or text field and enter the model-selected value.
- Visible GNOME terminal output attempts one native overview close after observing its launched window and
  before ordinary activation. Keep the same deadline and focused-terminal read-back; overview dismissal alone
  is not evidence that a command or visibility check succeeded.
- Keep visible execution and pixel capture separate. `terminal.show_output` may create and await one terminal;
  `window.capture` may only target one already visible exact model-selected title and write one PNG.
- Share one deadline across open, wait, activate, input, and accessibility read-back stages.
- Verify the resulting application state through accessibility or another deterministic API.
- Add a delayed-window counterfactual proving that input is not sent to the previous window.

## Local Files

- `vs_code.file.replace_literal` matches exact text, including whitespace and newlines, and supports multiline
  strings. Zero matches return `TEXT_NOT_FOUND` without writing, even if the replacement text occurs elsewhere.
  A repeated completed replacement may therefore report no match; inspect current text instead of inferring a write.
  Only `old` is replaced, not surrounding or following lines. Replacing a whole function requires its complete
  current text in `old`; a declaration alone does not include its body. Active read feedback must not recommend
  the retired `file.write_text` action.
- `.venv-openapa/` and `.venv-qwen-agent/` are local environments. Do not import them as source or package
  them for deployment.
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, logs, and temporary VM output are generated data.
- Large vendored assets require an explicit deployment need. Golden assets are never part of generic-only
  deployment.

## Strict Guest Deployment

- Do not use task ID or a task manifest to choose the generic Multi-Apps Adapter set.
- Deploy no golden cache. Install the one-action (`adapter.call`) generic Multi-Apps overlay and an empty task manifest.
- Legacy task modules and assets may remain in the source tree for labeled historical reproduction, but generic
  workers must not import them at startup and `scripts/strict_deployment.py` must exclude them before upload.
  Post-reset sanitization is defense in depth, not a substitute for clean packaging.
- Remove VLC reference profiles and golden media from both payload and install locations.
- Treat an unparseable sanitization response or any remaining forbidden path as a hard failure before the first
  model request.
- A deployment change needs both unit coverage and a clean-VM inventory; static source scanning alone is not
  sufficient evidence.

## Evaluator And GUI Evidence

- The Agent process receives only the isolated setup projection. Do not read a full OSWorld task JSON in the
  parent Runner before the episode, even if later code promises not to use its evaluator fields.
- Prefetch setup downloads before reset; prefetch evaluator cloud/golden resources only after the Agent loop and
  final screenshot.
- Keep `GUI_ACTION_SCHEMA` and `build_gui_command` together in `gui_actions.py`. Do not accept aliases in one
  layer and read another field in execution.
- Persist `gui_calls.jsonl` before `env.step`. A run without this trace cannot prove GUI execution integrity and
  fails closed under the applicable audit-v5 boundary (or the audit version explicitly recorded by an older report).
- Persist the Holo request, complete response, selected grounding action, gateway dispatch, and gateway result as
  linked host-only records in `holo_grounding_calls.jsonl`. The trajectory manifest must seal this file, and the
  next Qwen request must not contain Holo transport, response, reasoning, or request-ID evidence.
- Audit IDs from the complete frozen config, not only the worker-local result shard. Audit failed Adapter forwards
  as well as successful ones and compare guest hashes with the OSWorld cache.

## Verification

```bash
cd /home/liuhao/computer_use/adapter_versions/v2_expanded
PYTHONPATH=. .venv-openapa/bin/python -m pytest -q tests/<focused-test>.py
.venv-openapa/bin/ruff check <changed-python-files>
git diff --check
```

For a fast modularization check before the full suite:

```bash
PYTHONPATH=. .venv-openapa/bin/python -m compileall -q integrations scripts tests *_adapter
ruff check integrations/lite_agent/runtime.py integrations/lite_agent/runtime_policy.py \
  integrations/lite_agent/instruction_semantics.py integrations/lite_agent/observation_fields.py \
  integrations/lite_agent/semantic_requirements.py \
  integrations/lite_agent/state_*.py integrations/lite_agent/action_selection.py \
  integrations/lite_agent/tool_surface.py integrations/lite_agent/agent_protocol.py \
  integrations/lite_agent/completion.py integrations/lite_agent/execution_engine.py \
  integrations/lite_agent/agent.py
ruff format --check integrations/lite_agent/runtime.py integrations/lite_agent/runtime_policy.py \
  integrations/lite_agent/instruction_semantics.py integrations/lite_agent/observation_fields.py \
  integrations/lite_agent/semantic_requirements.py \
  integrations/lite_agent/state_*.py integrations/lite_agent/action_selection.py \
  integrations/lite_agent/tool_surface.py integrations/lite_agent/agent_protocol.py \
  integrations/lite_agent/completion.py integrations/lite_agent/execution_engine.py \
  integrations/lite_agent/agent.py
```

For a completed strict run, also recompute every `artifact_sha256` and `canonical_request_sha256` in
`llm_request_index.jsonl`, recompute `guest_file_inventory.json`, and search model-visible strings separately
from screenshots for the task UUID, UUID prefix, and forbidden route names. The historical
`audit_generic_only_run.py` is not part of this checkout. Promotion-gate hybrid runs instead use the host-only
`experiments/work/audit_hybrid_schema_v5.py` auditor, whose script, fixture, tests, and SHA-256 manifest are sealed
separately from runtime source and copied or referenced by hash in the immutable audit output. It must remain
outside deployed/model-facing packages and must never modify raw evidence. A trusted candidate requires schema v5
with complete frozen task coverage, config-snapshot identity, startup and immediately-pre-model process boundaries,
strict guest source allowlist, Qwen and Holo identity/reasoning attestations, exact Qwen-to-Adapter and
Qwen-to-Holo-to-Gateway execution joins, and artifact hashes all valid.
