# Generic-Only Evaluation Protocol

Updated: 2026-09-15

[Back to project index](index.md)

The active root GOAL now authorizes affected-only serial API optimization from the
recovered clean-hardened-v2 archive in an independent worktree. A pass accepts that
API's decomposition only; it does not change any full-run numerator or promoted
baseline. A skipped candidate is not merged. The [API review](archive/v337-workflow-api-review-20260915.md)
links the current ledger. No regression/control episodes or new gates are part of this sequence.

## Preconditions

This document has two audiences. The current repair reference and its dated diagnostics support ordinary
single-task repair; the frozen-condition and promotion requirements below apply when producing comparable scored
evidence or a candidate for baseline promotion. Do not treat a promotion checklist as a prerequisite for a focused
offline test.

- Model: the condition records both roles independently. The new pure-Qwen condition uses `qwen3.5-4b`
  for planning, API selection, review and grounding; all-Holo and Qwen-Holo conditions remain historical evidence.
- Agent: LiteAgent strict generic-only mode.
- OSWorld commit: `091f5ef1d5544bc74953c77875d5feb5bed30108`.
- Adapter/runtime: one frozen active-tree hash.
- `runs=1` is the default for a comparable baseline; bounded repeats may be used for explicitly marked exploratory
  variance checks. Google Drive/OAuth tasks are excluded from the v337 baseline denominator.
- No task-specific tools, task-ID hints, golden profiles, evaluator oracle, or Runner argument repair.
- Qwen3.5-4B conditions use the model's native binary thinking control. Record
  `reasoning_mode` (`thinking` or `non_thinking`) in both the protocol and model
  sections, keep it consistent with `protocol.thinking`, and send
  `extra_body.chat_template_kwargs.enable_thinking` on every request. Do not
  send or require the generic OpenAI-compatible `reasoning_effort` tiers for
  Qwen3.5; the vLLM enum is not a Qwen3.5 capability declaration. Record any
  response `reasoning`/`reasoning_content` observation and reject an explicit
  mode mismatch, but do not interpret that text as a numeric effort level.
- Providers with a genuine tiered control may use the legacy
  `reasoning_effort` gate. Changing between a binary mode and a tiered control
  creates a new condition and result directory. Historical configs labelled
  `max` remain diagnostic/non-scoring unless their provider contract actually
  defines that tier.

Every material change to a frozen Prompt, schema, Adapter, Runner, auditor, VM image, step budget, endpoint
allocation, or concurrency is a new comparison condition and requires a new config and result directory for a
scored comparison. Local documentation, tests, and scratch diagnosis do not retroactively change an immutable
result or require a new result directory by themselves.

Holo-native GUI experiments use a separate Runner and cannot be mixed with LiteAgent baseline evidence. The
completed Holo3.1-4B random-10 condition is non-promotable local evidence on the fixed-189 non-OAuth pool, not an
official H Company score. Its frozen config, raw results, public-environment boundary, and integrity counts are
recorded in the [Holo3.1-4B local evaluation](archive/holo31-4b-osworld-local-evaluation-2026-08-29.md).

The user authorized and subsequently **cancelled** one pure-Qwen full run on 2026-09-15. Condition
`qwen35-all-roles-fixed189-20260915-v1` retains 80 passes among 148 terminal outcomes and 41 tasks without a
terminal result, from a schedule of 189 non-OAuth tasks once. Both roles used Qwen thinking at
`http://192.168.0.138:8001/v1`; six workers shared the endpoint and
each worker's main/grounding requests are sequential. Main settings are temperature 0 / 4096 output tokens /
240-second requests; grounding settings are temperature 0.8 / 1024 / 180 seconds. Keep 100 global / 50 local
steps, one restart, 1800 Agent seconds and the 30 GiB stop. Existing `provider=holo` and `--holo-*` labels name
the grounding implementation, not the actual inference model; all model IDs, accepted identities and served
roots select Qwen, with no Holo fallback. The [report](archive/all-qwen-fixed189-20260915.md) records the new
condition, launch and cancellation evidence. The raw aggregate still says running because termination preceded
finalization. Preserve every attempt and report this as incomplete; do not present a final PASS/189 rate,
promote it or claim a model-only ablation against older conditions. No new gates were introduced.

The preserved all-Holo architecture retained the LiteAgent API/GUI path: Holo 3.1 4B selected the coordinate-free
`gui_request` Tool, a separate Holo call grounds one action from the latest screenshot, and the shared GUI gateway
validates and executes it. Results return to the main Holo call for review. Each worker uses one endpoint for
both roles sequentially. Both roles explicitly record their own thinking, temperature and output settings.
The authorized `holo31-all-roles-fixed189-20260912-v1` run used 14 workers, seven per endpoint, and completed
with **95/189 = 50.26%**: 95 passed, 42 evaluator failed, 22 agent deadline, 10 model protocol, 16 model
transport and 4 environment failures. Its legacy metadata `success_rate=69.34%` is `95/(95+42)` and excludes
52 abnormal outcomes; it is not a full-189 rate. The finalized status is `completed`, final integrity is `ok`,
and the original source/config seals are unchanged. Its [report](archive/all-holo-fixed189-20260912.md)
records the condition, hashes and preserved outcomes. This is
an architecture exploration, not promotion. Its individual repair queue is now paused at 32 isolated PASS,
48 skips, 118 actual attempts and 80/94 processed, with Order 151 prepared but unrun. The new pure-Qwen run
does not consume that attempt. The preserved repair workflow retests only the current task, without
regression/control episodes or newly added gates.

The first exploratory random-20 hybrid condition is preserved separately from all baselines. It completed
`14 passed / 4 failed / 2 agent_deadline_exhausted`; three GUI requests reached Holo. The run demonstrates that the
binary request path and same-VM episode loop execute end to end, but it is not a promotion result and must not be
reported as a 20-task success rate without the failure and timeout breakdown.

The earlier frozen full-189 Qwen-Holo condition is preserved historical repair evidence. It completed
`119 passed / 33 evaluator failed / 21 agent deadline / 12 model protocol / 3 environment / 1 agent failure`, for
119/189 = 62.96% over all scheduled tasks. Its legacy metadata `success_rate=78.29%` uses only the 152 evaluator
terminal episodes and must not be reported as the full-189 rate. The exact condition, source archive, hashes, and
repair-queue interpretation are maintained in [Current Evaluation And Repair Reference](current-repair-reference.md).

## Repair Reference Versus Promotion Baseline

The cancelled evaluation, preserved repair queue and promoted baseline registry answer different questions.
The pure-Qwen run has partial results only. The paused all-Holo
[94-task queue](../experiments/work/all-holo-failed-task-ledger-20260912.json) comes from its non-passing
outcomes; its immutable measured result is 95/189. The historical Qwen-Holo 70-task queue
and 119/189 numerator remain immutable. The current baseline pointer still resolves to v337 at 157/189 because
it passed the historical promotion gates. Do not select active repairs from v337, mix isolated passes into an
integrated numerator, or update the baseline pointer because an isolated task passes. Future full runs and
promotion remain separately authorized decisions.

The independent `generic-only-fixed189-clean-hardened-v2` release is now linked to the root Git repository
at `archive/v337-clean-hardened-v2-20260816` (`83530dd`). Its verified source seal is
`d0ca0dd99ba6e1d8c6d6d1aaf8d3d923f4d9eb0a3465e6094aa62b903a858651`, with its own 158/189 result.
This historical v337 derivative is distinct from original v337 (157/189) and v335 (158/189); the association
does not promote a replacement baseline. [Version Control](archive/version-control.md#linked-v337-derived-release)
records the remote, branch, exact source/config/result hashes and separate-checkout instructions.

The binary interpretation follows the official [Qwen3.5-4B model card](https://huggingface.co/Qwen/Qwen3.5-4B),
the [Qwen vLLM deployment guidance](https://qwen.readthedocs.io/en/latest/deployment/vllm.html), and the
[vLLM reasoning-output documentation](https://docs.vllm.ai/en/stable/features/reasoning_outputs/). Qwen's
separate [thinking-budget documentation](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html#thinking-budget)
does not define `low`/`medium`/`high`/`max` modes for Qwen3.5.

## Model-Free Direct API Validation

`scripts/run_direct_api_validation.py` is a separate developer harness for checking public API composability. It
starts one fresh guest, deploys the strict generic Adapter stack, accepts only operator-authored public API calls,
records each response, and loads the original evaluator exactly once after `finish`. It sends no model request,
uses no Router or completion policy, and issues no direct Runner GUI command. A semantic Adapter may still use a
generic application shortcut behind its declared API contract.

This protocol cannot produce or promote an Agent baseline. The completed bounded campaign covered 16 retired
task-shaped actions through 17 evidence tasks and 26 immutable attempts: 25 scored attempts plus one exploration
stopped before mutation or evaluation. Corrective compositions and reusable Writer and VS Code primitives
produced 17/17 API composition passes. A same-commit VS Code stable control also passed, giving the API candidate
an affected/control gate of 2/2. Its machine-readable ledger is
[`experiments/analysis-v337-bounded-granularity/direct-api-composition-ledger.json`](../experiments/analysis-v337-bounded-granularity/direct-api-composition-ledger.json),
with the interpretation in the [archived report](archive/direct-api-composition-validation-2026-08-28.md).

## Current Promotion State

The current trusted baseline is v337. It completed all 189 fixed non-OAuth tasks under one prospectively frozen
condition and all six audit-v5 reports are `valid=true`, `evidence_valid=true`, and
`baseline_admissible=true`. It produced 157 passes, 32 normal failures, and zero environment failures: 83.07%
over 189 valid scored episodes. All 189 routes are `generic_api_only`.

The immutable v337 record predates the binary Qwen3.5 reasoning-schema rule above: its historical condition uses
the legacy provider setting recorded in that config. Do not retrofit the old record or treat its fields as a failure
of the current protocol; the binary `reasoning_mode` and `enable_thinking` requirements apply to new Qwen3.5
conditions and the historical binary-mode hybrid repair reference.

Before the fixed run existed, the v337 config set `baseline_candidate=true`,
`promotion_pre_authorized=true`, `runs=1`, `resume=false`, and `best_of=false`. The identical source seal first
passed a 2-task clean-VM smoke (`2/2`) and a frozen 16-task validation (`15/16`), with every audit-v5 worker
valid. The full run then covered 1606 captured requests and 189 guest inventories; all source, process, request,
execution, deployment, and trajectory gates passed.

v335 remains immutable descriptive evidence at `158/189`, not a trusted baseline. A read-only audit-v5 recheck
found no observed dynamic task-ID leak, forbidden-route call, argument rewrite/injection, or execution mismatch
across 1595 requests, but rejected all six workers: the old config lacks a prospective condition, all 189 tasks
lack the required immediately-pre-model process boundary, and the old process could reach a legacy module with
task IDs and answer-shaped constants. The correction is additive; never edit the old v335 record or traces.

v252 remains the first clean historical baseline, and v307 remains immutable development evidence at `146/189`.
The historical bounded granularity review covers 24 actions: 16 task-shaped or composite actions were decomposed and
eight native or explicit homogeneous transactions were retained. The subsequent model-free 17-task validation
is API capability evidence only and leaves v337 unchanged. v385 is preserved as superseded evidence because its PDF
backend remained optional. v386 is the completed decomposition boundary, not a baseline. Its frozen one-task
PDF validation completed `0/1` with no environment failure and a valid audit-v5 over three requests. The trace
proves separate model-selected `pdf.outline.inspect` and one exact `pdf.pages.extract` call, including explicit
outline depth, overwrite policy, and Cairo backend, but the model terminated after only one of eight required
outputs. Earlier positive and negative composition validations remain preserved. None changes the v337 pointer.
The negative check does not authorize baseline promotion. On 2026-08-21 the user separately authorized one fresh
fixed-189 diagnostic condition over v386. Its config records the negative predecessor,
`baseline_candidate=false`, `promotion_pre_authorized=false`, runs=1, no resume, and no best-of selection. It
completed `97/189` with 92 normal failures and zero environment failures. All six audit-v5 reports are valid and
evidence-valid across 1967 requests and 189 guest inventories, with every leakage, rewrite, injection, action,
trace, GUI, and guest-integrity counter at zero. Audit integrity does not override the frozen non-candidate
status: this result cannot replace v337. Any future promotion still requires a new prospective smoke, stable
small validation, and pre-authorized fixed condition.

The historical post-v386 recovery remained below that promotion sequence. v389y passed all three evaluators but
failed its prospective mechanism gate because the target never called the new active-editor inspection API.
v389z confirmed a generic Impress current-document save mechanism but completed `1/2`; v390 isolated the
remaining fit-route overlap and completed `2/2`. The authorized v391 30-task gate then completed `15/30` but
failed its target-recovery and repeated-loop thresholds. The later v392 three-task condition was interrupted
before any task completed.

On 2026-08-22 the user explicitly requested one full diagnostic despite those smaller gates. v393 was frozen as
`baseline_candidate=false` and `promotion_pre_authorized=false`, then ran all 189 tasks once with fresh resets,
six workers, no resume, and no best-of selection. It completed `92 pass / 92 fail / 5 environment failure`, or
`50.00%` over 184 scored episodes and `48.68%` over all scheduled tasks. Five audit-v5 workers passed, but Worker
3 found one Runtime work-state transition mismatch: delegated `state_changed=false` evidence was exposed and
accepted as a mutation. All leakage, forbidden-route, argument rewrite/injection, Adapter trace, transport, and
GUI mismatch counters remain zero. The state mismatch nevertheless makes the evidence invalid, so v393 is
diagnostic only and cannot enter the baseline registry. The records live under
`experiments/analysis-v393-fixed189-diagnostic/` and
`experiments/generic-only-fixed189-v393-diagnostic-concurrency6-run1/`. v337 remains the current pointer.

The v393 finding is fixed in the active development tree by a bounded, envelope-aware state-change reader shared by
Runtime, retry-block, completion, and CCAG code. Explicit nested `state_changed=false` is now treated as a no-op;
missing fields still use the documented legacy fallback. This is a new source condition, not a retroactive repair of
v393 evidence. At that stage, the next permitted run was a small fresh-VM affected/control condition with the changed source.

The historical v395-v398 CCAG/progressive-disclosure experiments are non-promotable A/B evidence. v398 treatment used the
same fixed 16-task template as control with `causal_affordance_graph=true`, `causal_context_event_limit=8`,
`causal_context_hint_chars=32000`, and `deferred_gui_fallback=true`; all six worker audits passed. Its measured
efficiency gain (18.2% fewer total prompt tokens and 51.9% fewer GUI executions) did not improve binary success,
so the switches remain opt-in and the v337 pointer is unchanged.

v247 observed `135/189`, but remains baseline-inadmissible because strict guests contained a golden file,
evaluator data was loaded before the Agent, and GUI handoff evidence was incomplete with three confirmed action
mismatches. Preserve it only as diagnostic evidence.

The v249 cleanup candidate passed static verification and its two-task clean-VM smoke: `2/2` original-evaluator
passes, 27 requests, and both audit-v4 workers valid. The independent v250 validation then completed `15/16`
with all six worker audits valid and baseline-admissible, 194 captured requests, and every integrity counter
zero. The subsequent v251 fixed-189 run was stopped by the user after 13 completed tasks and is not
baseline-admissible. The fresh v252 run then completed the unchanged fixed-189 condition from Order 1 in a new
directory and passed all six audits. Historical cohorts and incomplete runs do not substitute for that complete
gate.

## Baseline Registry

`experiments/baselines/current.json` is the only mutable baseline pointer. It must resolve to one immutable
promotion record under `experiments/baselines/`, whose recorded SHA-256 must match the pointer. The promotion
record must, at minimum, pin the active runtime/test tree hash, model, Agent, OSWorld commit, frozen config,
aggregate results, trajectory seal, and every strict-audit admissibility counter.

Promotion is a metadata operation, not a rerun shortcut:

1. Preserve the complete raw run and all audit outputs in a new directory.
2. Recompute and record every referenced hash; do not edit an older seal or result.
3. Confirm the full condition and all promotion gates, including prospective authorization, `runs=1`, no
   resume/best-of, complete task coverage, and strict audit-v5 admissibility.
4. Add a new immutable record, then update only `current.json` and the active docs.

If any gate is missing, leave the current pointer unchanged and label the candidate inadmissible. A changed
prompt, schema, Adapter, Runner, model, VM image, step budget, or concurrency is a new condition even when the
task pool is unchanged.

## Pre-Model Boundary

Before the first model request:

1. Load task setup in an isolated process and project only `id`, `instruction`, `config`, and `proxy`.
2. Do not parse, cache, prefetch, attach, or retain evaluator expected state in the Agent process.
3. Deploy every Adapter with centralized `strict_generic` packaging.
4. Install only generic Multi-Apps actions/schema and an empty task manifest.
5. Record guest inventory after reset and sanitization; reject forbidden paths, bytecode, or hashes matching the
   OSWorld cache.
6. Capture the exact messages and complete tool schemas submitted to the model client.
7. Reject task routes and nested equivalents before guest HTTP even if manually injected.
8. Record and validate the loaded-source boundary at Runner startup and again immediately before the first
   model request. A legacy Runner import or missing record is `invalid_leakage`.

The evaluator configuration and evaluator-only resources may be loaded only after the Agent loop and final
screenshot. The Runner then attaches them immediately before invoking the unchanged original evaluator.

## Execution Integrity

- The model selects every tool and every model-facing argument.
- Adapter raw arguments, normalized event arguments, and forwarded payload must be equal. Representation
  conversion occurs only behind a reusable Adapter contract.
  Calc literal-cell writes record `calc.range.write.literal_cells.v1` in host-only
  `adapter_calls.argument_conversion`: literal count, target geometry and canonical
  matrix SHA-256 (UTF-8 JSON, `ensure_ascii=False`, sorted keys, comma/colon separators).
  The raw call plus declared conversion reproduces this input representation;
  the digest alone does not establish storage or completion and adds no scoring gate.
- GUI uses the canonical action-specific schema. `press` accepts one `key`; `hotkey` accepts a `keys` array with
  at least two entries. No aliases, empty defaults, or argument repair are allowed.
- Record every Adapter forward, including failures, and every GUI command before handing it to OSWorld.
- Compare captured model calls with events and transport traces. Missing evidence, an action mismatch, rewrite,
  injection, or command mismatch invalidates the episode.
- Completion relies only on model-selected executed evidence, never evaluator state.
  An explicit API/GUI claim may use an acknowledged, screenshot-backed grounding result already audited by the main model,
  subject to the existing deferred terminal audit and claim validation. No redundant Adapter mutation is
  required. Acceptance of a completion claim is not an evaluator pass or proof of artifact correctness.

An integrity failure is `invalid_leakage`; it is excluded from both numerator and valid denominator. A normal
model/task failure remains in the denominator. Environment failures are reported separately.

## Promotion Sequence (Promotion Only)

1. Run the complete unit suite, Ruff, formatting, compileall, project layout/leakage checks, frozen-v1 hashes,
   and pinned OSWorld tree check.
2. Freeze the clean source commit, active runtime/test tree hash, Runner/Supervisor/Python entrypoints, VM and
   model conditions in machine-readable configs. The supervisor persists the exact gated config bytes as a
   read-only worker snapshot, binds every worker result to that hash and assigned task shard, and revalidates the
   config, source seal, and repository before publishing a terminal aggregate. Mark the full candidate and
   promotion authorization before any full-run result exists.
3. Run two clean-VM smoke tasks, one per endpoint. Only Runner/environment fixes are allowed during smoke; any
   code change creates a new candidate and directory.
4. Audit both smokes with schema v5. Integrity must pass even if the model receives reward zero.
5. Freeze a small, independently selected, source-order-preserving multi-domain validation set. Run once at the
   intended concurrency and audit every worker.
6. Only after the gate is stable, create a new directory and run all fixed 189 non-OAuth tasks from Order 1 with
   fresh VM reset per task.

Never resume a stopped run after a code change, select best attempts, replace failures, or merge configurations.

Model-facing error evidence retains ordinary validation language such as
`expected dict` and `cell reference`; those words alone are not hidden metadata.
Explicit internal keys/identifiers, task identity, and forbidden routes remain
filtered by the existing sanitizers. The raw event error remains unchanged;
an offline feedback regression is not an affected-task score.

## Required Evidence

- frozen config, immutable worker-config snapshot, clean source commit, active-tree hash, and initial/final
  repository attestations;
- internal task metadata kept outside model messages;
- requested/actual model identifier and exact serialized requests;
- Prompt and tool-catalog hashes;
- strict guest inventory and sanitization records;
- every model response, raw tool arguments, executed Adapter/GUI transport, and result; for Holo delegation this
  includes linked request, response, grounding selection, gateway dispatch, and gateway result records with exact
  request/response hashes and requested/actual model and reasoning-mode attestations;
- screenshots before/after each step and final screenshot;
- explicit evaluator-boundary timestamps/state;
- original evaluator reward and output;
- route class, failure class, steps, duration, and rerun reason;
- schema-v5 audit JSON for each worker, including frozen-condition and config-snapshot identity, source-tree and
  ending repository state, both model preflights, process-boundary, strict guest, exact request, Qwen-to-Adapter,
  Qwen-to-Holo-to-Gateway execution, artifact-manifest, and model-facing leakage checks.

## Canonical Historical Evidence

- v247 frozen config: `experiments/configs/generic-only-fixed189-v247-concurrency6.json`;
- v247 immutable results: `experiments/generic-only-fixed189-v247-concurrency6-run1/`;
- v247 corrected audits: `experiments/analysis-v247-baseline-audit-correction/`;
- correction report: [v247 audit correction](archive/generic-only-fixed189-v247-audit-correction.md);
- v249 smoke config/results: `experiments/configs/generic-only-clean-boundary-smoke2-v249-concurrency2.json`
  and `experiments/generic-only-clean-boundary-smoke2-v249-concurrency2-run1/`;
- v249 candidate seal: `experiments/analysis-v249-clean-code-baseline/manifest.json`.
- v250 validation config/results: `experiments/configs/generic-only-validation16-v250-concurrency6.json` and
  `experiments/generic-only-validation16-v250-concurrency6-run1/`;
- v250 validation seal: `experiments/analysis-v250-clean-validation/manifest.json`;
- v251 interrupted fixed-189 evidence: `experiments/generic-only-fixed189-v251-concurrency6-run1/` and
  `experiments/analysis-v251-interrupted-fixed189/manifest.json`;
- v252 fixed-189 config/results: `experiments/configs/generic-only-fixed189-v252-concurrency6.json` and
  `experiments/generic-only-fixed189-v252-concurrency6-run1/`;
- v252 machine-readable baseline seal and analyses:
  `experiments/analysis-v252-clean-fixed189-baseline/manifest.json`;
- v252 detailed report: [v252 clean baseline](archive/generic-only-fixed189-v252.md).
- current pointer: [`experiments/baselines/current.json`](../experiments/baselines/current.json);
- v335 fixed-189 config/results: `experiments/configs/generic-only-fixed189-v335-development-concurrency6.json`
  and `experiments/generic-only-fixed189-v335-development-concurrency6-run1/`;
- v335 historical seal/report: `experiments/analysis-v335-clean-fixed189-baseline/manifest.json` and
  [v335 historical result](archive/generic-only-fixed189-v335.md);
- v335 audit-v5 correction: `experiments/analysis-v335-trust-boundary-adjudication/manifest.json`;
- v337 smoke config/results: `experiments/configs/generic-only-clean-boundary-smoke2-v337-concurrency2.json`
  and `experiments/generic-only-clean-boundary-smoke2-v337-concurrency2-run1/`;
- v337 validation config/results: `experiments/configs/generic-only-validation16-v337-concurrency6.json` and
  `experiments/generic-only-validation16-v337-concurrency6-run1/`;
- v337 fixed-189 config/results: `experiments/configs/generic-only-fixed189-v337-trusted-concurrency6.json` and
  `experiments/generic-only-fixed189-v337-trusted-concurrency6-run1/`;
- v337 machine-readable seal: `experiments/analysis-v337-trusted-fixed189-baseline/manifest.json`;
- v337 detailed report: [v337 trusted baseline](archive/generic-only-fixed189-v337-trusted.md);
- immutable current promotion record: [`experiments/baselines/v337.json`](../experiments/baselines/v337.json).
- model-free direct API result ledger:
  [`experiments/analysis-v337-bounded-granularity/direct-api-composition-ledger.json`](../experiments/analysis-v337-bounded-granularity/direct-api-composition-ledger.json);
- model-free direct API report: [17-task composition validation](archive/direct-api-composition-validation-2026-08-28.md).

The fixed non-OAuth pool remains
`experiments/configs/qwen35-lite-agent-fixed-189-generic-only-v1.json`, SHA-256
`eab739e905ba4a93684c125aafd7f3ce06389771226da87d8e611fef6343cb8e`. A future full run copies the selection
into a new frozen condition; it never modifies or resumes v247.

## Reporting

Report `generic_api_only`, `api_plus_gui`, `gui_only`, `environment_failure`, and `invalid_leakage` separately.
A strict audit establishes episode integrity only. A result becomes a benchmark baseline only after independent
selection, complete coverage, one frozen condition, and successful promotion through every preceding gate.

For every completed scheduled run, report the full terminal-status counts and `passed / scheduled` rate. If an
evaluator-terminal-only or otherwise filtered rate is also useful, name its denominator and list every excluded
status; never present it as the scheduled-task success rate. Run failure classification only after every strict
worker audit passes. Use the preserved routing records, worker manifests, and dated `experiments/analysis-*`
artifacts for offline classification; the historical `analyze_clean_baseline_failures.py` helper is not shipped in
the current checkout. Such analysis must never enter Runtime routing, tool ranking, model requests, completion, or
Adapter arguments.
