# OSWorld API Project

Updated: 2026-09-15

This is the current documentation entry. Open archive reports only when investigating a specific result.

## Current Operating Context

- Active root GOAL: optimize the six identified workflow APIs serially from the recovered
  clean-hardened-v2 source in an independent worktree. Accept each change only after its
  affected task passes; skipped APIs keep their accepted implementation. No regression
  episodes or new gates. See [API audit and live ledger](archive/v337-workflow-api-review-20260915.md).
- The pure-Qwen fixed-189 evaluation was **cancelled by the user** on 2026-09-15. Condition
  `qwen35-all-roles-fixed189-20260915-v1` retains 80 passes among 148 terminal outcomes and 41 tasks without
  a terminal result. The supervisor and workers have exited; this is not a full-run score.
  See the [pure-Qwen report](archive/all-qwen-fixed189-20260915.md).
- The all-Holo **95/189 (50.26%)** result and its [repair ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
  remain preserved. Individual repair is paused at 32 isolated PASS, 48 skips, 118 actual attempts, 80/94
  processed, with Order 151 prepared/unrun. The earlier Qwen-Holo **119/189 (62.96%)** result is historical
  evidence. Isolated repairs do not add to either full-run numerator or the new pure-Qwen score.
- Promoted baseline pointer: v337 at 157/189 (83.07%), retained as an older-architecture comparison rather than
  the active failure queue.
- Linked source archive: the independently evaluated **v337-derived clean-hardened-v2, 158/189 (83.60%)**.
  It is available in this project's Git under tag `archive/v337-clean-hardened-v2-20260816` and branch
  `codex/archive-v337-clean-hardened-v2`, with remote `v337-archive`. See
  [identity, hashes and checkout instructions](archive/version-control.md#linked-v337-derived-release).
- Canonical condition, denominator explanation, source archive, and current per-task evidence:
  [Current Evaluation And Preserved Repair Reference](current-repair-reference.md).
- Stable repository rules: [root AGENTS](../../../AGENTS.md). Active objective: [root GOAL](../../../GOAL.md).

These distinctions supersede older “current objective” wording later in the chronological material. Historical
scores remain valid for their own frozen conditions but do not change the new run's scope or resume paused repairs.

2026-08-29 的运行环境与模型服务快照见[环境交接](environment-handoff-2026-08-29.md)；实际端点和资源
以当前 condition/config 为准，不把该日期快照当作持续更新的运行事实。

源码现由根目录 Git 仓库管理；原始实验轨迹继续作为不可变外部制品保留。提交、标签、Git LFS 和
实验目录的边界见[版本管理](archive/version-control.md)。

第一次了解本项目，先阅读[项目原理：从任务到可审计桌面操作](archive/how-the-project-works.md)。

## Historical Development Record

The dated research and diagnostic summaries below remain valid only for their recorded conditions. They are
retained for provenance and do not replace the current operating context above or the active goal below.

论文初稿见[证据承载语义执行：面向小参数模型的可审计 API-GUI 混合 Computer Use Agent](archive/paper-evidence-carrying-semantic-actuation.md)。论文以独立 clean-hardened-v2 artifact 及其三次复现为研究对象，不代表当时的 post-decomposition 开发条件 v393，也不声称是完整 369 题 OSWorld 榜单成绩。

该时期的架构研究包含默认关闭的 CCAG/progressive GUI 原型，以及 v404 新增的 Adapter-declared
auxiliary observation lease。后者让 Adapter 用类型化结果声明辅助视觉界面不阻塞后续 API，Runner
只管理通用租约生命周期，不再识别具体预览工具名。v404 在冻结的同一 16 题小集上完成 `16/16`，
六份 audit-v5 均有效且可采信；这是小集单次门禁结果，不是新的 189 题 baseline。详细记录见
[v399-v404 辅助观测租约](archive/generic-only-v399-v404-observation-lease.md)；CCAG 文献边界与 A/B
记录见[归档研究记录](archive/innovation-ccag-20260825.md)。

此前 v410 的 route-owned missing-path recovery 通过 clean-VM smoke `2/2`，但在 4 题定向集和完整
v409 失败集上分别仅为 `0/4` 和 `0/25`。25 题 reward 向量与 v409 完全相同，因此它是有效的
负结果，不是改进后的 baseline。详见
[v410 失败集结果](archive/generic-only-v410-v409-failures25-result.md)。

此前的完整 v422 在同一不可变 27 题失败集中完成 `5 pass / 22 fail / 0 environment failure`。六份
audit-v5 均有效且可采信。22 个失败已经逐题归为结果绑定 6、多步/过早完成 5、PDF 表单能力缺口
1、路由/GUI 1、模型语义/视觉推理 3、输出保真 3、数据/参考不一致 3；其中 10 题具有较高的通用
工程修复价值，5 题不应针对单一 Golden 调参。详见
[v422 失败分类](archive/generic-only-v422-remaining27-failure-classification.md)，机器清单位于
`experiments/analysis-v422-literal-control-consistency/remaining27-failure-classification.json`。v422 是
开发诊断，不替换 v337。

首轮架构召回配对实验在 4 条 affected 和 2 条 control 上比较了默认词法检索与可审计的全目录
LLM Router。两者均为 `2/6` 且 reward sum 相同；Router 消除了一个上下文溢出环境标签，但没有新增
binary pass，额外 12 次 Router 调用的平均输入为 33.2k token，总耗时也更高。两份候选 worker
audit-v5 均有效，泄漏、参数改写/注入和执行错配均为 0。该 Router 保持默认关闭。详见
[Router 配对诊断](archive/architecture-recall-tool-router-ab.md)。

后续两个三题配对门禁分别验证了 observed attachment selector 和 token-accurate context budget。选择器
候选与对照均为 `2/3`，但目标题的附件保存从四次尝试降为一次，模型原样选择了查询结果中暴露的
完整 selector；后续 PDF/表格阶段仍失败，因此不记为新增 pass。上下文预算的 live synthetic preflight
把 238,494 token 请求压到 35,806 token，服务计数完全一致；三条真实候选任务最高仅 18,152 token，
一次投影也未触发。对照 Order 108 又暴露了三次 HTTP 200 但零 structured tool call 的传输失败，故
context pair 不能作因果提分结论。详见[选择器与上下文预算诊断](archive/architecture-recall-selector-context-budget-ab.md)。

Holo3.1-4B 的冻结 GUI-only 随机 10 条本地评测完成 `5 pass / 5 fail / 0 environment failure`。官方
未公布 4B 的单独 OSWorld 分数，80.0% 对应 35B-A3B 和未公开的内部实现，因此该结果不是官方成绩
复现，也不替换 v337。环境、审计与失败边界见
[Holo3.1-4B 本地评测](archive/holo31-4b-osworld-local-evaluation-2026-08-29.md)。

## Current Objective

### Current All-Qwen Agent Configuration

The new v2 condition uses Qwen 3.5 4B for reasoning, Tool selection and review. A separate Qwen call receives
the latest screenshot and grounds the model-selected, coordinate-free `gui_request` into one GUI action.
The existing shared gateway validates and executes it, and every result returns to the main Qwen call for audit.
The generic API/GUI workflow and runtime remain unchanged; `provider=holo` is the historical implementation
label, while both actual inference roles use Qwen without a Holo fallback. Six workers share the direct
`http://192.168.0.138:8001/v1` endpoint, with each worker's two roles called sequentially. Both roles use thinking;
retain 100 global / 50 local steps, one restart, 1800 Agent seconds and the 30 GiB disk floor. See
[Architecture](architecture.md) and the [current reference](current-repair-reference.md).

The all-Holo 94-task repair queue is paused and preserved; the cancelled pure-Qwen full run does not consume
Order 151's prepared isolated attempt. The pure-Qwen configuration above describes that preserved partial run.
v337 remains the current trusted promoted baseline at `157/189` (`83.07%`), but it is an older-architecture
comparison and no longer supplies the active repair queue.

The current strict tool surface exposes only `adapter.call` in Multi-Apps; tool search binds that call to one
public action on its owning Adapter. Oversized Calc, Writer, Impress, OS, GIMP, and VLC actions identified by the
granularity review have been removed from their public manifests, validation sets, dispatch tables, catalog
signatures, and semantic shortcuts. Multi-step work is now composed from the remaining owning-Adapter actions.

### Historical v337-Derived API Composition Coverage

The historical v337-derived bounded decomposition pass reviewed 24 actions in the clean-hardened-v2-derived tree. Sixteen
task-shaped, hidden-discovery, policy-solving, or heterogeneous workflow actions were removed; eight native or
explicit homogeneous transactions were retained. The source phase is complete with 289 public actions and 36
focused counterfactual checks passing. The subsequent model-free direct campaign exercised all 17 evidence
tasks in fresh guests with operator-authored public API calls, no model requests, and no direct Runner GUI
actions. Its 25 scored attempts each invoked the evaluator once after the sequence; one additional exploration
was stopped before mutation or evaluation. Here `gui_actions=0` means that the direct Runner issued no raw GUI
command; a public semantic Adapter such as `ui.open_view` may still implement a generic keyboard shortcut behind
its contract. Corrective compositions and reusable Writer and VS Code primitives brought the final task result
to `17/17 api_composition_pass`. The same-commit VS Code affected/control gate passed `2/2` on Orders 189 and
187. This is API composition coverage, not an Agent success rate; v337 remains the frozen trusted baseline. See
the [result ledger](../experiments/analysis-v337-bounded-granularity/direct-api-composition-ledger.json),
[archived report](archive/direct-api-composition-validation-2026-08-28.md), and
`experiments/analysis-v337-bounded-granularity/macro-ledger.json` inventory.

v335 remains immutable descriptive evidence at `158/189`, but audit-v5 rejects it as a trusted baseline because
it lacks prospective condition and pre-model process-boundary evidence and its old Agent process could reach a
legacy answer-bearing Runner module. Its 1595 captured requests showed no observed dynamic exploitation. The old
`125/189` result is contaminated historical evidence. The later v247 result observed `135/189`, but a
stronger audit found deployment, evaluator-boundary, and GUI-trace defects, so v247 is baseline-inadmissible. Its
raw evidence remains immutable and useful for diagnosis; it is not a model or Agent success-rate baseline.

## Current State

| Item | Current fact |
|---|---|
| Active source | `adapter_versions/v2_expanded/` |
| Active evaluation / repair reference | Pure-Qwen `qwen35-all-roles-fixed189-20260915-v1`, running/result pending; all-Holo repair queue paused; see [`current-repair-reference.md`](current-repair-reference.md) |
| Historical Qwen-Holo source archive | tag `archive/qwen35-holo31-hybrid-20260831-a1dfe6`, commit `88484bcea3238c53fec993eb312f7d9269ccda79` |
| Frozen v1 | `adapter_versions/v1_baseline/`, never modify |
| OSWorld | commit `091f5ef1d5544bc74953c77875d5feb5bed30108`, tracked tree clean |
| Model / Agent | Qwen3.5-4B planning, API selection, review and grounding; existing LiteAgent strict generic-only API/GUI mode |
| Reportable model, endpoint, VM, and resource settings | the immutable condition config; dated environment handoffs are snapshots only |
| Current valid baseline | v337: 157 pass / 32 fail / 0 environment failure; 83.07% |
| Baseline pointer | [`experiments/baselines/current.json`](../experiments/baselines/current.json) -> immutable v337 promotion record |
| Current development condition | one user-authorized pure-Qwen fixed-189 exploration; no baseline promotion or change to historical scores |
| Preserved repair workflow | all-Holo queue paused at 32 isolated PASS / 48 skips / 118 actual attempts; individual repair prohibits regression/control episodes |

## Why v247 Is Not A Baseline

The corrected read-only audit checked all 189 tasks and 1911 captured model requests. It found no task ID,
task-prefix, evaluator artifact URL, `task.execute`, or golden route in model requests or Adapter payloads, and
no Adapter argument rewrite or injection. Those are useful negative findings, but they do not repair the run.

The disqualifying findings are:

- every one of the 48 Multi-Apps guests contained a copied golden GIMP image in payload and install locations,
  for 96 forbidden path and OSWorld-cache hash matches;
- the old Runner loaded evaluator data before all 189 Agent episodes;
- 123 GUI proposals had no independent command-handoff trace because that evidence did not exist in v247;
- three VLC proposals used `hotkey` with `key="F"`, while the Runner executed an empty hotkey command.

All six corrected audits therefore fail closed. The old audit JSON files remain untouched; the correction lives
in `experiments/analysis-v247-baseline-audit-correction/`.

## Historical Clean-Candidate Changes

- Strict deployment centrally excludes legacy task modules, task manifests, reference profiles, README content,
  and golden assets. Multi-Apps installs only the three-action generic overlay and an empty manifest.
- A short-lived process projects only task setup fields. Evaluator configuration and evaluator-only artifacts are
  loaded into the Runner only after the Agent loop and final screenshot.
- GUI tools use one action-specific schema and one canonical command converter. A single key uses `press`; a
  `hotkey` requires a `keys` array. The exact command handed to OSWorld is recorded.
- Historical audit schema v4 checked all IDs from that frozen config, actual serialized model requests, successful and failed
  Adapter forwards, GUI proposal-to-command equality, guest paths, and hashes against the OSWorld cache.
- `source_execution_semantics.py` advances source-edit tasks only from verified model-selected events; it never
  supplies a path, edit, command, output destination, or completion claim.
- `vscode_configuration_semantics.py` stages a reusable VS Code configuration action from public instruction
  semantics. The model still selects every semantic field; only the VS Code Adapter translates those fields to
  stable application identifiers and verifies JSON read-back.
- The historical v337-derived bounded granularity pass reviewed all 24 candidates: 16 task-shaped or composite actions were
  decomposed and eight native or explicit homogeneous transactions retained. The active public inventory is 289
  actions. The five source batches have 36 focused counterfactual checks; the completed 17-task direct campaign
  measured API composability separately from Agent performance.
- Writer paragraph groups are now composed from one unchanged model-selected `paragraph.set_format` call per
  independent formatting rule. Writer table color grouping uses `document.inspect` to identify the table,
  `table.read` to obtain exact cells and text, and one explicit `table.set_cell_text_color` call per homogeneous
  cell group; the removed vowel-classification macro is not present in the generic worker.
- The fixed `paragraph.separate_sentences` wording alias was removed. The model now selects explicit paragraph
  indices from `document.inspect`, exact output strings, and the blank-paragraph count through
  `paragraph.replace_text`; the Adapter performs no sentence segmentation and the Runner supplies none of those
  values.
- The combined `document.add_numbered_reference` macro and its Runner-owned marker/number locks were removed.
  `document.inspect` exposes document structure, while `text.find_replace` and `document.append_paragraphs`
  perform two separate model-selected mutations with unchanged literal text and append content. The direct test
  confirmed that these plain-text primitives still cannot express a native Writer numbered-reference field.
- The six-command `git.commit_and_push` facade and its exact required-action/completion shortcut were removed.
  Strict retrieval now maps generic Git/version-control language to the existing `os.command.run` contract; the
  model separately selects every argv, working-directory source, provenance policy, and accepted return code.
- The combined `terminal.capture_command_screenshot` facade was removed from both OS and Multi-Apps. A visible
  command now uses `terminal.show_output`; a separate OS-owned `window.capture` call requires the model to copy an
  exact live window title and choose the PNG destination. Missing or duplicate titles fail closed, and no Runner
  module launches a command or chooses a window on the model's behalf.
- The Writer `document.create_from_text_files` whole-task macro and Multi-Apps facade were removed. The model now
  creates one blank document, inserts one explicit file or literal separator per call, formats through a separate
  paragraph action, and saves separately. The removed workspace-file parser no longer stages or orders the sequence.
- The OS `filesystem.copy_matching` macro and its instruction parser, forced route, schema lock, default search,
  implicit glob expansion, destination derivation, legacy task route, and regression entry were removed. The model
  now calls `filesystem.find`, optionally creates explicit directories, and invokes `filesystem.copy` once per
  exact source/destination pair; strict retrieval suppresses explicitly negated mutations.
- The OS `filesystem.organize_by_age` macro was removed. It no longer discovers a tree, classifies files against
  the current clock, derives flattened destinations, moves recent files, and compresses old files in one call.
  The model now reads paths and timestamps with `filesystem.find`, calls `filesystem.rename` for each exact move,
  and calls `archive.compress_file` for each exact gzip source/destination pair. Each single-file mutation
  validates its explicit paths and policy before writing.
- The OS `filesystem.chmod_tree` macro and dedicated LiteAgent permission planner were removed. In v337, one
  model-selected mode expanded to 6,495 implicitly discovered files under `/home/user`, including unrelated home
  state. The replacement composes `filesystem.find` with `filesystem.set_permissions`; the latter accepts only
  exact model-selected non-symlink regular-file paths and one shared mode, rejects roots/globs/recursion, verifies
  each path, and rolls back earlier changes if a later write fails.
- The prospectively frozen v376 OS affected/control check completed `0/4` with no environment failure; all four
  strict audits are valid and show zero leakage, rewrite, injection, or trace mismatch. The three affected tasks
  exposed model-side path grounding and multi-call composition failures, while the unchanged control also failed
  on newline construction. This negative result is preserved and does not justify restoring a whole-task macro.
- v377 removed VLC `playback.open_unique` and the implicit-discovery mode of `playback.open`. A VLC episode may
  now expose the reviewed read-only OS `filesystem.find` support route, but the model must select discovery and
  exact-source `playback.open` separately; the Runner neither copies the observed path nor chains playback. The
  frozen affected/control validation passed `2/2`, and both audit-v5 reports found zero leakage, rewrite,
  injection, action, or trace mismatch. The affected task reached verified playback on step 3, then failed to
  terminate, used GUI fallback, and stopped at 300 seconds. This validates the decomposition boundary, not stable
  API-only completion.
- v381-v384 removed `desktop.set_default_application`, which previously selected an installed application,
  expanded a MIME category, and changed every matching association in one call. The model now composes bounded
  `desktop.applications.inspect` reads with exact `desktop.mime_associations.set` mutations. The preserved v384
  trace validates unchanged-argument composition but records paging and grounding failures.
- v385 first removed `pdf.split_by_outline`, its all-output transaction, backend inference, generated filenames,
  and dedicated Runner parser, but its extraction backend remained optional; that condition is preserved as
  superseded evidence. v386 requires the model to select `outline_level`, `overwrite`, and `output_backend`.
  `pdf.outline.inspect` exposes bounded titles and inclusive ranges without writing, and each
  `pdf.pages.extract` persists exactly one model-named range. The v386 strict trace explicitly selected Cairo,
  created the first of eight outputs, and then terminated early, so the 0/1 result remains a model
  cardinality/completion residual rather than being hidden by restoring the macro.
- Picture-container recognition includes direct graphics, bitmap-filled shapes, and groups containing either.
  v284's unaccepted atomic batch/completion layer is not active; its evidence showed that instruction-derived
  validation must not lock a layout role that the instruction never states when live inspection contradicts it.
- Removed Calc and Impress macros are composed from model-visible reads and one explicit mutation per independent
  target. In particular, title-to-notes now uses inspect, `slide.set_notes`, and `shape.format_text`; heterogeneous
  textbox work uses one `shape.format_text` call per live selector. Homogeneous semantic-role formatting remains a
  reusable application operation.
- `shape.insert_image` accepts a model-selected local path/file URL and structured physical dimensions in mm, cm,
  or inches. It accepts both slide representations only when consistent, preserves all arguments unchanged, and
  verifies the loaded shape and physical size after save.
- Impress personal-information cleanup now uses `presentation.inspect` followed by one model-selected
  `shape.delete` call per observed text or icon selector. The retired semantic cleanup macro no longer classifies
  content or expands one call into a whole-slide deletion plan.
- `terminal.show_output` executes a finite model-selected argv in a visible terminal and derives its working
  directory from the focused terminal or Files window. LiteAgent exposes it only for explicit terminal-output
  intent; the OS Adapter alone resolves live context, executes, verifies, and leaves the result visible.
- `workspace.find_files` resolves only the currently active VS Code workspace from live window and workspace
  metadata, fails closed on ambiguity, and searches model-selected globs. Generic tool search may retrieve it from
  workspace/file vocabulary, but LiteAgent has no dedicated parser that supplies globs, orders files, or stages a
  downstream consumer.
- `spreadsheet.concatenate_single_columns` accepts model-selected ordered CSV/ODS/XLSX inputs, output path,
  separator semantic, and overwrite policy. It validates one used column per source, equal row counts, and a
  single-column CSV result; `spreadsheet.open_in_terminal` separately opens a model-selected result through an
  isolated LibreOffice Calc process.
- Explicit one-record-per-observed-input spreadsheet workflows retain only a public batch count, require the
  model to supply every header and cell, expose a model-selected `table.sort`, verify the selected XLSX/ODS
  package format, and require final structural read-back. No extracted or expected value is supplied.
- OS `terminal.launch` now has a default verifier for exact argv, launch return code, an observable terminal
  window, truthful child status, and explicitly requested shell-history evidence. An empty verifier can no
  longer turn a real launch into a misleading downstream failure.
- The visible-terminal probe now tolerates bounded startup delay instead of treating the first empty `wmctrl`
  read as final. Order 118 subsequently passed through separate `terminal.show_output` and `window.capture`
  calls; this is a reusable timing fix, not a task route.
- Strict VS Code deployment no longer ships the task-shaped array-variable extension. `ui.open_view` and
  `ui.expand_section` bind the requested `wmctrl` ID to the unique active Code frame and verify selected or
  expanded accessibility state. The host now caches hash-pinned, VS Code 1.85-compatible official Python and
  Debugpy VSIX packages for explicit offline installation. `debug.breakpoint.set` verifies an exact checked
  source breakpoint, debug controls classify real running/paused state, and `debug.variables.read` reads only a
  standard paused `Debug Variables` tree. Order 189 passed without restoring the removed task-shaped extension.
- `workspace.inspect` reads the exact active VS Code workspace roots from observable state without mutation.
  For a saved workspace it also returns the exact `.code-workspace` path. Saving those roots requires a separate
  `workspace.write` call whose destination path and complete folder list are selected explicitly by the model;
  adding folders uses `workspace.add_folders` with the inspected path. Verified workspace mutations expose compact
  result-derived completion evidence.
- Strict Thunderbird filtering exposes `filters.configure`, not raw native storage. The model supplies the rule
  name, explicit `condition_mode`, complete conditions, action, and destination unchanged. The Adapter alone
  converts those public semantics to native syntax and verifies the persisted rule; missing or inconsistent
  conditionality fails before execution.
- `verified_artifact_handoff.py` may constrain one downstream typed path to compatible local files from a prior
  successful, verified Adapter result. The model still selects the consumer, one observed path, and every other
  argument; an unobserved path is rejected without repair or automatic execution.
- Strict semantic search retains only instruction-declared mutations plus read-only observations. A successful
  parameterless inspection is omitted from later recovery search until a real mutation invalidates it, avoiding
  redundant reads without selecting the remaining action or supplying any model-facing argument.
- `editor.inspect_active_file` provides bounded, model-selected VS Code resource inspection, but the v389y
  three-task run did not cause the model to call it. Its `3/3` evaluator result therefore failed the prospective
  mechanism gate and did not authorize a larger run.
- The historical `impress_adapter/persistence_contract.py` behavior is now implemented in `impress_adapter/uno_worker.py`:
  native `store` is used only when the requested URL canonically identifies the current document and no filter is
  supplied; otherwise the Adapter retains `storeAsURL`. The v389z target passed after
  both the Adapter and evaluator saved the file, while the unrelated image-selection control failed. The change
  is retained as generic persistence behavior, but the `1/2` condition is not a promotion gate.
- `impress_cover_semantics.py` validates `shape.fit_to_slide` calls that use one exact path or index copied from
  `presentation.inspect`, plus the model-selected slide and fit mode. Semantic picture-role and geometry-rank
  facades are no longer public. The earlier v390 result remains historical evidence for its sealed condition; it
  does not describe the current action surface.

## Canonical Evidence

The current baseline is resolved through the [current baseline pointer](../experiments/baselines/current.json),
which names the immutable [v337 promotion record](../experiments/baselines/v337.json). The record pins the
active runtime/test tree, model, OSWorld commit, complete fixed-189 condition, result hashes, trajectory seal,
and audit-v5 admissibility counters. The pointer may move only when a new record has passed the full promotion
gate; raw runs, seals, and old promotion records are never overwritten.

- v247 config: `experiments/configs/generic-only-fixed189-v247-concurrency6.json`, SHA-256
  `d5352da67a05bc618bff2090d41e5597d0f7b91f0361569157c4f39bc99b2bff`;
- preserved v247 results: `experiments/generic-only-fixed189-v247-concurrency6-run1/results.json`, SHA-256
  `1ddbc98b1532a723303312a45f35c39b5c5f3f7d1810162440758a640777096e`;
- machine-readable correction: `experiments/analysis-v247-baseline-audit-correction/manifest.json`;
- detailed correction: [v247 audit correction](archive/generic-only-fixed189-v247-audit-correction.md);
- original run report, retained with corrected status: [v247 historical observation](archive/generic-only-fixed189-v247.md);
- v249 smoke config/results: `experiments/configs/generic-only-clean-boundary-smoke2-v249-concurrency2.json`
  and `experiments/generic-only-clean-boundary-smoke2-v249-concurrency2-run1/`;
- clean code baseline seal: `experiments/analysis-v249-clean-code-baseline/manifest.json`;
- smoke report: [v248-v249 clean boundary](archive/generic-only-clean-boundary-v248-v249.md);
- validation config/results: `experiments/configs/generic-only-validation16-v250-concurrency6.json` and
  `experiments/generic-only-validation16-v250-concurrency6-run1/`;
- validation seal/report: `experiments/analysis-v250-clean-validation/manifest.json` and
  [v250 validation](archive/generic-only-validation16-v250.md);
- interrupted full run: `experiments/generic-only-fixed189-v251-concurrency6-run1/` and
  [v251 interrupted report](archive/generic-only-fixed189-v251-interrupted.md);
- complete v252 config/results: `experiments/configs/generic-only-fixed189-v252-concurrency6.json` and
  `experiments/generic-only-fixed189-v252-concurrency6-run1/`;
- v252 baseline seal and failure analysis: `experiments/analysis-v252-clean-fixed189-baseline/manifest.json`
  and [v252 baseline report](archive/generic-only-fixed189-v252.md).
- v252 immutable promotion record: [`experiments/baselines/v252.json`](../experiments/baselines/v252.json),
  SHA-256 `c04028f57bf29add2f58a7dce22f54c43a26ed0508d3c458839746b06fdb460c`.
- complete v335 config/results: `experiments/configs/generic-only-fixed189-v335-development-concurrency6.json`
  and `experiments/generic-only-fixed189-v335-development-concurrency6-run1/`;
- v335 historical seal: `experiments/analysis-v335-clean-fixed189-baseline/manifest.json`, SHA-256
  `053e13f631694170d5fb28597c6e9381c207f48e2a1093c2c1f97016b3fe0e3e`;
- v335 immutable historical promotion record: [`experiments/baselines/v335.json`](../experiments/baselines/v335.json),
  SHA-256 `9d0703eb1014816fc35e0fbad57602aabc5ddec11e3df1a9291b82dda2192a87`;
- v335 detailed report: [v335 historical result](archive/generic-only-fixed189-v335.md);
- v335 audit-v5 correction: `experiments/analysis-v335-trust-boundary-adjudication/manifest.json`;
- complete v337 config/results: `experiments/configs/generic-only-fixed189-v337-trusted-concurrency6.json`
  and `experiments/generic-only-fixed189-v337-trusted-concurrency6-run1/`;
- v337 trusted seal: `experiments/analysis-v337-trusted-fixed189-baseline/manifest.json`;
- v337 immutable promotion record: [`experiments/baselines/v337.json`](../experiments/baselines/v337.json);
- v337 detailed report: [v337 trusted baseline](archive/generic-only-fixed189-v337-trusted.md);
- historical v307 residual ledger: `experiments/analysis-v307-residual-optimization/ledger.json`;
- historical v307 chronology: [v307 residual Phase 1](archive/generic-only-v307-residual-phase1-v308-v320.md).

## Promotion Gate

1. Completed: project layout, static tests, frozen-tree checks, and two clean-VM smoke tasks.
2. Completed: independently selected 16-task multi-domain validation; 15/16 pass and 6/6 audits admissible.
3. Stopped: v251 fixed-189 was interrupted by the user and is not a baseline.
4. Completed: v252 fixed-189 from Order 1 with no resume inputs; 6/6 audit-v4 reports are admissible and the
   result remains an immutable historical baseline.
5. Corrected: v335 remains `158/189` descriptive evidence, but audit-v5 and static boundary review make it
   baseline-inadmissible under the current rules.
6. Completed: v337 prospective smoke `2/2`, validation `15/16`, and fixed-189 `157/189`; all 14 audit-v5 worker
   reports across the three gates are valid and admissible. The immutable v337 record is promoted.
7. Failed development gate: v391 completed `15/30`; only 9/24 targets recovered and the repeated-loop threshold
   failed, so it did not authorize confirmation.
8. Diagnostic only: the user-authorized v393 fixed-189 run completed `92/189` passes with five environment
   failures, but one strict work-state transition mismatch invalidated Worker 3. It is not promotable.
9. Current: repair the 70 non-passing tasks from the preserved Qwen-Holo hybrid condition one at a time. Isolated
   results remain non-aggregate; do not launch another fixed-189 run without explicit user authorization.

## Current Documents

| Document | Purpose |
|---|---|
| [项目原理](archive/how-the-project-works.md) | 面向新读者解释 OSWorld、LiteAgent、工具路由、Adapter、审计和 baseline |
| [Project progress](project-progress.md) | Current candidate, audit findings, verification, and next gate |
| [Architecture](architecture.md) | Runtime ownership and data flow |
| [Maintenance](maintenance.md) | Code placement, tests, and experiment hygiene |
| [Evaluation protocol](evaluation-protocol.md) | Generic-only promotion and evidence rules |
| [Active Goal](../GOAL.md) | Repair the preserved Qwen-Holo hybrid full-189 non-passing queue |
| [Archive](archive/index.md) | Historical reports and detailed evidence |
