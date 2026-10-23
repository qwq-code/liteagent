# Project Progress

Updated: 2026-09-18

## 2026-09-18 OCR text-click interface replaces model coordinates; affected retries complete

At the user's request, Codex click/double_click now use literal OCR `text` and an
explicit `occurrence` for repeated matches. Coordinates remain host-side under
the declared text-to-box-center conversion; raw-coordinate clicking and drag are
not exposed. The model keeps choosing every target. Keyboard tools handle controls
without text where feasible. A documented default 0.5-second settle precedes each
post-action screenshot. No new evaluation gate. MCP 17 / OCR 6 tests pass; Ruff
passes. An intermediate ID-based interface was superseded after the model repeatedly
assigned the wrong text to IDs; both interrupted attempts and zero scores remain
preserved.

Final literal-text trials: Order153 completes 13 calls / 260.710 seconds, reaches
the correct account signature but writes `AnonymXYZ Lab` without the requested
newline and falsely claims success; original evaluator 0. Order155 runs 10 calls /
312.776 seconds, reaches Bills via text, fails to star using chosen shortcuts, then
ends on upstream request transport failure (local bridge 502); evaluator 0. No
new PASS or aggregate rate. Both sources stayed frozen and both new VMs closed.
All attempts, limitations and evidence paths are in the
[trial report](archive/codex-qwen-failed-task-trial-20260918.md).

## 2026-09-18 Codex + Qwen + OCR affected-task trials expose coordinate-use failure

The user authorized testing previous failures with the new Codex development
loop. Two independent fresh-VM attempts used Qwen3.5-4B thinking, nine GUI tools,
post-action screenshots and English Tesseract OCR, with unchanged 100-call /
1800-second maximums. Order155 (Bills stars) stopped after 11 calls / 326.690
agent seconds; Order153 (account signature) after 9 calls / 157.199 seconds.
Both were developer-interrupted after repeated ineffective clicks. The original
post-stop evaluators each returned 0. These are not completed-budget trials or
a benchmark rate, and no new PASS is claimed.

PNG dimensions/hashes, current-image association and OCR delivery were correct.
The model's initial coordinates closely fit a 0–1000 normalized convention, while
tools execute original pixels; later guesses also drifted. Source remained frozen,
no runtime fix was applied during the test, and both new guest containers exited.
Full evidence and comparison limits are in the
[isolated trial report](archive/codex-qwen-failed-task-trial-20260918.md).
Older queues and baseline scores remain unchanged.

## 2026-09-17 Streaming enabled; previously timed-out input returns a tool call

At the user's request, candidate `ee409bf` enables streaming in the model client,
assembles indexed tool deltas without changing argument text, preserves reasoning
and usage, and returns no proposal on a disconnected or truncated response.
No execution or evaluation gate was added. Five transport tests use the installed
SDK against synthetic SSE frames; all 41 focused checks and Ruff pass.

The exact preserved v4 step3 request is replayed once without application execution.
Only stream/stream_options change. At https://qwen.jinmaoapi.cc.cd/v1, HTTP200 SSE
headers arrive after 3.326 seconds and one complete proposal returns at about
200.953 seconds, beyond the earlier HTTP524 cutoff. The model selects a Writer
reader for an observed TXT path, so the existing schema reports a business
argument error after streaming completes. No episode/evaluator runs or new task
PASS; the accepted source is unchanged and no process remains active. Full
diagnostic hashes and limits are in the
[candidate report](/home/liuhao/computer_use-v337-api-optimization/adapter_versions/v2_expanded/docs/tool-harness-132-20260917.md).
Any future scored attempt needs a newly frozen source/config recording streaming.

## 2026-09-17 03:51 UTC Requested Qwen endpoint retest blocked by repeated HTTP524

The user requested https://qwen.jinmaoapi.cc.cd/v1 after the previous timeout
explanation. This is the same endpoint as v3; it currently returns HTTP200 in
8.087 seconds for a synthetic thinking-mode GUI tool request with valid integer
arguments. One newly labeled Order132-only transport retest,
`v337-order132-tool-harness-20260917-v4-transport-retest`, used unchanged source
53abaf0, v3 source seal and 100-step / 1800-second / 30-GiB limits. The first two
task calls returned HTTP200, then step3 received HTTP524 at 03:46:32, 03:48:38
and 03:50:44 UTC. Developer stopped under the recorded signal. The task is
interrupted/unscored: 2 events, 627.115 wall seconds, no evaluator invocation.
Both processes exited and the source seal matches. Result SHA-256:
`f564e533dfb5cd35868634761351d7bf9f7de16948a0c0f088ef9afcafd6436a`.
All 21 attempts are preserved; no new PASS or accepted implementation. No runtime
edit, new gate, other-task episode or full run was introduced. No active process.
The [candidate report](/home/liuhao/computer_use-v337-api-optimization/adapter_versions/v2_expanded/docs/tool-harness-132-20260917.md)
records the bounded transport hypothesis and stop signal.

## 2026-09-17 Order132 tool-harness candidate complete; no new task PASS

The user authorized implementing simpler tool contracts after reviewing Order132.
Independent branch `codex/v337-tool-harness-132` retains API1's macro removal and
read fixes, adds explicit workbook identity across open/read/write/save, concise
owning descriptions, rectangular values, native readback and saved-state receipts,
and truthful wording in the existing completion feedback. Accepted runtime and
the five other skipped APIs are preserved. No new gates or task-specific plan.

First replay `v337-order132-tool-harness-20260917-v1` failed0 after 16 events,
481.325 seconds, stalled before extraction. Raw GUI schema errors were truncated
in model history and archive calls repeatedly omitted required fields. Source
`6165f7e` adds concise field errors and relevant usage without altering validators
or model arguments. The second replay was interrupted/unscored after 18 events
when repeated GUI string arguments persisted despite actionable feedback. A paired
synthetic probe isolates numeric-type loss with branch-only schemas; declaring
the same GUI types at the top level returns correct integers. Source `53abaf0`
implements that 13-line compatibility fix; 36 local checks and Ruff pass. Final
changed replay `v337-order132-tool-harness-20260917-v3-gui-types` verifies numeric
GUI calls and same-workbook open/live reads. It ends interrupted/unscored after
30 events / 1229.705 seconds when step31 receives three consecutive HTTP524
gateway timeouts. The developer stops under the documented signal; no student
paper reading, score writing or save was reached. Source seals match after exit.
This is not an accepted decomposition, benchmark PASS or integrated score.

The remaining offline diagnosis records wrong generic adapter/action pairings,
missing automatic list labels in Writer plain text and repeated reference reads.
Retain the implementation on its candidate branch. All three new attempts are
preserved (one scored failure, two unscored interruptions); all 17 older attempts
and the accepted original APIs remain unchanged. No processes remain active.

Details and preserved results: [tool-harness report](/home/liuhao/computer_use-v337-api-optimization/adapter_versions/v2_expanded/docs/tool-harness-132-20260917.md).
Original limits remain 100 steps / 1800 seconds / 30 GiB. No other task,
regression/control episode, full run or old repair queue was started.

## 2026-09-16 Serial API attempt queue closed without an accepted decomposition

All six workflow APIs were attempted and skipped under the user's skip rule.
Seventeen attempts are preserved: 10 scored failures, 5 unscored stops and
2 model transport failures. Zero affected-task PASS; zero accepted changes.
The accepted branch `codex/v337-api-optimization` retains the original six APIs
and its runtime diff against relocation `1249658` is empty.

API6/Order88 failed twice: 22 events before its command-feedback fix, then
48 events / 732.395 seconds afterward. The changed replay exposes native
stderr/stdout/cwd and the exact stdout_path recovery in actual model requests.
Both input conversions succeed, but the model's paste call never saves output
and it never opens the merged file. The original post-episode evaluator returns
0. Calc-backed calls also encounter `LIBREOFFICE_NOT_READY`; this availability
issue remains documented separately from the model's later output mistake.

Candidate `codex/v337-api-006-spreadsheet-columns` at `5acd319` preserves source,
26 focused checks, frozen configs and the detailed report. Both processes exited
and the complete source seal matches after exit. Latest result SHA-256:
`be20cf3e028593e0fbe904ab51102fb394b8b381452ecc48ae83f3d00f9734d6`.
The working model endpoint is https://qwen.jinmaoapi.cc.cd/v1; this replay had
no transport failure. Full evidence is in the
[independent ledger](/home/liuhao/computer_use-v337-api-optimization/adapter_versions/v2_expanded/docs/api-optimization-20260915.md).
No full run, regression episode, new gate or promotion was added. The attempt
queue is closed; no improved integrated score or optimized release is claimed.
Older progress snapshots below remain historical. Cancelled pure-Qwen and
paused all-Holo queues are not resumed.

## 2026-09-15 Serial API review and isolated decomposition

The recovered clean-hardened-v2 archive contains six obvious workflow facades.
The [review](archive/v337-workflow-api-review-20260915.md) records code evidence,
affected tasks and the accepted/candidate branch procedure. The root GOAL now
selects this serial work in `/home/liuhao/computer_use-v337-api-optimization`;
the dirty development checkout and cancelled full-run evidence are preserved.
Only affected tasks may run; no regression episodes, new gates or baseline promotion.
Current outcomes and source seals are maintained in the linked independent ledger.

2026-09-16 follow-up: missing-notes97 is also skipped after two attempts. Candidate
`74947af` preserves one unscored stop and one evaluator failure (84steps); actual
usage/search feedback improved but the model never read the source or saved.
Accepted decompositions 0/6, skips 3/6; ten attempts preserved, no passes.
The accepted runtime still matches the relocated archive; API4 personal-information54
is now under offline diagnosis. Prior skipped candidate fixes remain isolated.

API4 follow-up: both affected attempts failed0. Candidate `f30962e` preserves
full page-object feedback and removal of forced partial-task completion; the
second model still repeated title formatting without deletion. Skip with original
API intact. Current accepted0/6, skipped4/6, twelve attempts (seven scored failures,
four unscored stops, one transport failure). Continue API5 age-organization145.

API5 follow-up (2026-09-16): the candidate decomposes age organization into
explicit gzip/find/move operations and preserves observed modification ages.
25 focused checks passed. The first affected attempt stopped unscored after
45events: one real gzip and one incorrect extension-only rename. A small generic
rename-usage clarification then produced two correct gzip operations in the
second attempt, but all three step7 model requests failed with APIConnectionError
before evaluation (raw legacy category environment_failure). Host192.168.0.138
is unreachable on HTTP8001 and SSH22, with neighbor FAILED. Both processes exited,
source seal unchanged. Keep API5 pending for a bounded same-source transport
retest after recovery; API6 unstarted. Fourteen attempts total:7 scored failures,
5 unscored stops,2 model transport failures. Accepted0/6,skipped4/6 unchanged.
Details and hashes remain in the independent API ledger; baseline source/scores
and all skipped APIs remain unchanged. Candidate commit `7d4b5ee` preserves code,
both attempts and prepared/unrun `v337-api005-file-age-20260916-v3-transport-retest`.

API5 public-endpoint follow-up: user supplied https://qwen.jinmaoapi.cc.cd/v1.
The same advertised Qwen model id/root and a synthetic tool call were verified;
v4 separately registers the new route with unchanged source/limits. This third
actual attempt ended failed0 after11events/200.327seconds, stalled_no_progress.
Only one old file was compressed; the original evaluator rejected the remaining
uncompressed file. No transport failure. Skip API5, preserving candidate f924206
and original accepted API. Accepted0/6,skipped5/6;15 attempts (8 scored failures,
5 unscored stops,2 transport failures). API6/Order88 now begins from accepted
source. Prepared private v3 stays unrun. Historical full scores remain unchanged.

Serial follow-up: assessment132 and JSON-to-DOCX109 were each skipped after four
attempts. Accepted decompositions 0/6, skips 2/6; the original APIs remain intact
on `codex/v337-api-optimization`. Eight attempts are preserved: four scored
failures, three unscored stops and one model transport failure (legacy raw label
`environment_failure`). Candidate commits `d66d823` and `e4b6f80` retain all
changes and reports. Continue with missing-notes97 from the accepted source.

## 2026-09-15 v337-derived release linked into project Git; pure-Qwen cancellation recorded

At the user's request, import the existing release history from
`/home/liuhao/computer_use_cleen/v337-github-staging` into the development repository without checking out or
merging it. Remote `v337-archive` points to `https://github.com/liuhao-labs/computer-use-v337.git`; local branch
`codex/archive-v337-clean-hardened-v2` and annotated tag `archive/v337-clean-hardened-v2-20260816` retain
commit `83530ddff10e5fe6e0c3823147428cbdf229bd37` and its source parent `9a101b2`.

This is **clean-hardened-v2, 158/189 (83.60%)**, a v337 derivative, not original v337 (157/189) or v335 (158/189).
Recompute its source seal directly from the 374 imported Git blobs: 53,809,619 bytes,
`d0ca0dd99ba6e1d8c6d6d1aaf8d3d923f4d9eb0a3465e6094aa62b903a858651`; committed config and result hashes
also match the release record. No source LFS pointers are needed. GitHub HEAD lookup timed out; the
import uses the verified local history and does not publish development changes. Full provenance and commands:
[Version Control](archive/version-control.md#linked-v337-derived-release).

Also record the user's earlier cancellation of the pure-Qwen full run: supervisor and workers have exited.
Last aggregate update `2026-09-15T13:19:31.216136+00:00` retains **80 passed / 41 failed / 16 deadline /
6 transport / 3 protocol / 2 environment**, with **41 without a terminal result**. Raw aggregate status remains
running and final integrity is absent because termination preceded finalization. Preserve it unchanged as a
cancelled partial run, not a full score; see the [run report](archive/all-qwen-fixed189-20260915.md).
The all-Holo queue stays paused and the original-v337 promotion pointer remains unchanged.

## 2026-09-15 07:58 UTC Pure-Qwen fixed-189 running; all-Holo repair paused

Progress observation at **08:09 UTC**: the original supervisor and six workers are alive.
The aggregate updated at 08:08:13 UTC records **2 passed / 3 failed / 184 not_run**;
the latter includes running episodes. No terminal protocol, transport, environment or
deadline failure yet. Read-only early failure notes are in the linked report; no source
changes or repair replays were made. This is a partial count, not the full-run score.

The user separately authorizes one full run of the same ordered 189 non-OAuth tasks using Qwen 3.5 4B for
planning, API selection, screenshot grounding, result review and terminal review. Condition
`qwen35-all-roles-fixed189-20260915-v1` is **running; all 189 outcomes pending at launch**. The
[report](archive/all-qwen-fixed189-20260915.md) records service evidence, freeze and launch details.

Supervisor **59925** starts at `2026-09-15T07:58:02.847503+00:00`; workers **59954, 60224, 60463, 61256,
62300 and 63139** are initially alive/booting. The host-only synthetic probe passes for both Qwen thinking
roles in 15.587 seconds and is not a scored episode. Freeze `2026-09-15T07:54:51.859201+00:00` retains
the latest Order 151 source without runtime changes: **535 files / 81,415,767 bytes**, source SHA-256
`5e43a92fd5285c49ef23ae4af7f4649f99456a8f857f9eeca27fd1f011a431ad`.
[Config](../experiments/configs/qwen35-all-roles-fixed189-20260915-v1.json) SHA-256:
`b108b3e52a5ea9ad2c1afb8490b6cea6177d6b46b9d0d7899ba6a8c03777bfd6`.
Source/tests stay frozen through both worker and supervisor exit; results remain in the
[new result directory](../experiments/qwen35-all-roles-fixed189-20260915-v1-run1/).

Both roles select `qwen3.5-4b` on `http://192.168.0.138:8001/v1`, with six workers and sequential main/grounding
requests within each worker. Both use binary thinking. Main temperature 0 / 4096 output tokens / 240-second
requests; grounding temperature 0.8 / 1024 / 180 seconds. Retain 100 global / 50 local steps, one restart,
1800 Agent seconds and the 30 GiB disk stop. Existing `provider=holo` and Holo-named driver/CLI fields describe
the implementation, not actual inference; model identities and served roots are exclusively Qwen with no
Holo fallback. No runtime, validator or new gate is introduced for this switch. Results will use PASS/189 and
all terminal categories, not evaluator-terminal-only percentages or a model-only causal claim.

The all-Holo repair ledger is paused and unchanged at **32 isolated PASS, 48 skips, 118 actual attempts,
80/94 processed**, with **Order 151 prepared/unrun** and 13 other pending tasks. The new evaluation does not
consume its planned attempt or change all-Holo **95/189**, historical Qwen-Holo **119/189**, or the v337 pointer.
This is the newly authorized full evaluation, not a repair regression/control episode or baseline promotion.

## 2026-09-14 10:41 UTC Order143 missing-file failure and skip;151 sealed, waiting for disk space

Attempt **118** ends **failed0.0**, **5 events /6 actual requests /280.435 seconds**,agent_done and
zero completion rejections. Worker completes `2026-09-14T10:33:44.601898+00:00`; root completes
`10:33:50.764050 UTC`. Both integrity checks are `ok`,bothPIDs are gone,workerreturncode0; detached
supervisor exitcode was not captured. Root SHA-256
`8e7f1817698da3bdfa8d49c14d3d345883ed8ec45b578148e0d8de7cecf1b2f5`;
worker SHA-256 `7f48a5e1fbd16489582c398f531e52e7861eca24a56e1890496f8dcf7ea0899a`.

Fresh setup establishes the intended initialcwd,confirmed by normal screenshot/probe/systemmessage.
The model finds all3files but uses single-source copy_to_directories for onlythefirstfile and3destinations,
despite explicit same-source semantics and separatecopy guidance. The native call follows those values.
Review4continues with a nonrecursive destination search0,then completion5and review6 stillaccept. The
evaluator reports **2missingfiles**,with directorystructure preserved. [Skip143](archive/all-holo-order143-serial-setup-retest-20260914.md)
after one diagnostic; no new copycontract defect,host-filled missingcalls,copy macro/gate orunchangedrepeat.

Current **Order151**,queue81, has a [narrow terminal-review wording repair](archive/all-holo-order151-review-evidence-retest-20260914.md):
statusok/gatepassed acknowledges submitted actionevidence,not independent finalapplicationstate.
Root changes only agent_protocol.py guidance; Ruff and theexistingterminal-surface check **1pass**.
Same reviewer,fields,gates andabilitytochooseanotheraction. Earlier pageconfusion mayremain; onlya
future originalevaluatorPASS canestablishrecovery. No new gate,helper,route orregression/control.

151's prepared condition is `holo31-all-roles-order151-review-evidence-retest-20260914-v1`, frozen
`2026-09-14T10:36:22.029972+00:00`: **535 files / 81,415,767 bytes**. Source SHA-256
`5e43a92fd5285c49ef23ae4af7f4649f99456a8f857f9eeca27fd1f011a431ad`; config SHA-256
`8c39627750d42b8945804202a88a97617b4d3c1996695f7987a564a73d73e9ee`.
Existing frozen-input validation passes. The separate prepared record is planned campaign attempt 119,
with no launched repair_attempts entry and no result directory, supervisor, worker, VM or model request.

Latest root observation is approximately **22 GiB free**, below the unchanged **30 GiB floor**.
151 remains **prepared/waiting_disk**; no benchmark processes or exact 117/118 run-owner containers
remain, and no unrelated data was deleted. Counts: **32 isolated PASS, 48 skips, 118 actual attempts
+ 1 prepared, 80/94 processed, current 151 and 13 other pending**. Original **95/189** and baseline pointer
remain unchanged. The disk block is not a task failure or skip. Before a future launch, revalidate the
prepared frozen inputs; a source change requires a new condition. No new run below the existing disk floor.

## 2026-09-14 10:31 UTC Order143 fresh serial setup diagnostic running

Attempt **118**, condition `holo31-all-roles-order143-serial-setup-retest-20260914-v1`, starts
`2026-09-14T10:28:55.501218+00:00`. Detached supervisor **60320** has PPid1/SID60320; childworker
**60368** starts `10:29:03.386368 UTC`,SID60368. Both metadata statuses are running,only `[143]`
selected; stdout/stderr remain in a unique experiments/work log outside the new resultdir.
Freeze `10:28:13 UTC`,unchanged **535 files /81,415,510 bytes**, source SHA-256
`5b0e0f62b2751b4f2032c55edccda24b90f1d6c7f8a5f0af0f3441f6a4c63fe1`;
config SHA-256 `ec3b0120a1abdc75cc9cbffe235458a778e589dae8dfba2e98da15f76a1664d3`.
Existing frozen validation is `ok`; no source/test edits or repeated local checks. Source/tests remain
frozen through both exits; paired Holo thinking/T0.8/top_k7,100global/50local,one restart,1800Agentseconds
and30GiB floor are unchanged.

The [single diagnostic](archive/all-holo-order143-serial-setup-retest-20260914.md) observes ordinary
initial screenshot/cwd to see whether fresh serial setup reproduces the original directory mismatch.
No semantic setup input is replayed,no intendedcwd injected,and pinned setup/evaluator/gates remain.
The model chooses all paths; a separate hierarchy omission is still possible. If the discrepancy repeats
without a demonstrated generic repair,record and skip rather than repeat for a preferred result.

Counts: **32 isolated PASS,47 skips,118 attempts,79/94 processed,current143 running/retesting and14
other pending**. No score claimed at launch;117 remains interrupted/null and136/141skips add no episodes.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 10:27 UTC Order132 bounded stop;136/141 offline skips; next143 setup diagnostic

Attempt **117** ends worker **interrupted/null**, **14 events /15 actual requests /390.094 seconds**,
completed `2026-09-14T10:25:14.892197+00:00`, zero completion rejections and no evaluator. All14events
are tools_search; request15 has no event. No app/file read,terminal.show_output,grade write or done occurs.
Root sendsSIGINT to exact worker **37722** at10:24:53 while supervisor **37684** remains its parent,
following the declared unchanged-discovery stop. The supervisor finalizes `10:25:19.636031 UTC` with
both integrity checks `ok`,workerreturncode0 and existing interrupted-worker invalid_configuration/null
wrapper. Both processes are gone; detached supervisor exitcode was not captured. This is a launched
episode,distinct from116's pre-worker rejection. Root SHA-256
`6c4d15c73b1fa21c240209717dcdf589b15c19980fedf25ba91263522ff3c318`;
worker SHA-256 `3d127448059597c5c3f3abb7ad6e6f6441e7a60f3e8998e1816c7cda150f7e28`.

[Skip132](archive/all-holo-order132-terminal-receipt-retest-20260914.md): actual guidance already tells
the model to use returned actions after search hits; no missing discovery contract or new small grading
defect is established. Receipt/installer fixes retain focused evidence,but terminal.show_output is not
exercised here and no score is produced. Detached supervision survives this bounded run without proving
the priorSIGTERM cause. Preserve114/115infrastructure nulls and116setup mistake; no unchanged replay.

Then [skip136 offline](archive/all-holo-order136-volume-interpretation-skip-20260914.md): model explicitly
chooses150 despite existing100-normal/150-amplification guidance. [Skip141 offline](archive/all-holo-order141-terminal-observation-skip-20260914.md):
requested defaults persist,but no terminal opens despite existing instructions; scorerHTTP200/outputnull
does not establish wrong geometry or exact focus. Neither adds an episode,API,gate or model-value override.

Current **Order143**, queue80, has a [fresh setup diagnostic hypothesis](../experiments/work/all-holo-order143-triage-20260914.md):
ordinary setup's short waits may leave the terminal at home instead of its intended subdirectory.
Observe initial screenshot/cwd in one fresh serial run,without replaying semantic setup,injecting cwd or
changing pinned setup/evaluator. A separate hierarchy mistake remains model-selected. No118 registered.
Counts: **32 isolated PASS,47 skips,117 attempts,79/94 processed,current143 diagnosing/not_started
and14 other pending**. Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 10:21 UTC Order132 detached supervisor and worker actually running

Attempt **117**, condition `holo31-all-roles-order132-detached-supervisor-retest-20260914-v2`, starts
`2026-09-14T10:18:34.588145+00:00`. Supervisor **37684** has PPid1/SID37684; child worker **37722**
starts `10:18:44.028687 UTC`, SID37722. Both metadata statuses are running and only `[132]` is selected.
The detached launcher exit0 is not supervisor exit0; no persistent execsession is used. Stdout/stderr
are retained in the unique experiments/work condition-supervisor.log, allowing the unchanged supervisor
to create its fresh resultdir. Existing directory validation passes without any gate change.

Freeze `10:18:06 UTC`, unchanged **535 files /81,415,510 bytes**, source SHA-256
`5b0e0f62b2751b4f2032c55edccda24b90f1d6c7f8a5f0af0f3441f6a4c63fe1`;
config SHA-256 `a42d6c6f2b274a9e30f4dcf768ebe3c2a347a43f17fa32de99f4e640f0ee21d7`.
Existing frozen validation is `ok`. No source/test changes or repeated local checks; source/tests stay
frozen through both exits. Paired Holo thinking/T0.8/top_k7,100global/50local,one restart,1800Agentseconds
and30GiB floor remain. The [infrastructure experiment](archive/all-holo-order132-terminal-receipt-retest-20260914.md)
tests session coupling; priorSIGTERM source remains unknown and detachment is not yet a proven fix.
Any repeated unexpected detached-supervisor death requires investigation before further scored launch.

116 remains invalid_configuration/null with no worker;115 and114 remain interrupted/null with their
unfinalized supervisor records preserved. Counts: **32 isolated PASS,44 skips,117 attempts,76/94
processed,current132 running/retesting and17 other pending**. No score is claimed at launch; original
**95/189** and baseline pointer remain unchanged, with no regression/control,new gate or full rerun.

## 2026-09-14 10:17 UTC Order132 second supervisor interruption; detached launch setup error retained

Attempt **115** ends worker **interrupted/null**, **36 events /37 actual requests /1052.669 seconds**,
completed `2026-09-14T10:08:33.829197+00:00`, integrity `ok`, no evaluator and zero completion rejections.
Supervisor **41876** again unexpectedly exits **143/SIGTERM**, session **28439**. Root did not send that
signal, observes worker **41885** under PPid1 and interrupts the verified orphan. Both are gone; source
of supervisor termination remains unknown. Setup had completed09:54:10.871 without recorded deployment
retry and the model read the reference; external interruption is not a model failure or evaluatorzero.

Supervisor raw results remain **running/not_run**, last updated `2026-09-14T10:00:50.623987+00:00`, with
**no final_integrity** or workerreturncode. Preserve them unchanged. Root results SHA-256
`c5aee7d483ca432e4b964f1bc934f644ce23879d679e8502fb642d207b39376a`;
worker SHA-256 `429c0422d158bd5961e7cf7ee15d433367bf40e6c389830ee2eb3c58a54045f8`.

Attempt **116** invokes a detached supervisor but **never starts a worker**. Root precreates the new
result directory for stdout, so the existing check correctly returns **invalid_configuration/null**:
“trusted condition requires a new result directory.” Start `10:11:18.764749 UTC`, final update
`10:11:18.764766 UTC`, workers=[], zero events/requests; no scoring or newSIGTERM. Launcher exit0 does
not establish supervisor exit0. Result SHA-256
`b4932b994762065f2216b3d05f90a9de490617f0e3b96ef8460f258a50480a1b`.
Its unchanged source is535files/81,415,510bytes, SHA-256
`5b0e0f62b2751b4f2032c55edccda24b90f1d6c7f8a5f0af0f3441f6a4c63fe1`, frozen
`10:09:59.763529 UTC`; config SHA-256
`0434524b4102d8457e29d98603514891c11d393a5f605d1f8800aa22eba0d95b`.

The [report](archive/all-holo-order132-terminal-receipt-retest-20260914.md) records this infrastructure
checkpoint extension. Correct only detached stdout destination to a unique experiments/work log and
let the authoritative supervisor create a fresh resultdir. Preserve116; no gate/source/controller change.
If detached supervision also fails unexpectedly, investigate before further scored launch.117 is not
registered in this entry. Counts: **32 isolated PASS,44 skips,116 attempts,76/94 processed,current132
not_started/infrastructure_recovery and17 other pending**. Original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 09:52 UTC Order132 installer-stage budget recovery replay running

Attempt **115**, condition `holo31-all-roles-order132-deploy-budget-retest-20260914-v1`, starts
`2026-09-14T09:50:50.555165+00:00`, supervisor **41876** / session **28439**; worker **41885** starts
`09:50:59.590228 UTC`. Only `[132]` is selected and both metadata statuses are running. Freeze
`09:49:49.599116 UTC`: **535 files /81,415,510 bytes**, source SHA-256
`5b0e0f62b2751b4f2032c55edccda24b90f1d6c7f8a5f0af0f3441f6a4c63fe1`;
config SHA-256 `c05f2741ca354e26a44993f2de326da4f3749963d56d876081d27e1205401bb4`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain.

The [installer-only correction](archive/all-holo-order132-terminal-receipt-retest-20260914.md) moves
the90second deadline inside the existing update/install loop. Both stages retain45/60second command
caps and lock-only retries; combined setup budget is at most180seconds. The existing regression now
requires full installation allowance after long update waiting. **4 package-install tests pass in0.07seconds**,
with Ruff,bash-n and scoped diff. Terminal-receipt repair stays intact; its37 checks are not repeated.
No runtime CommandRunner/process-group policy,new package,helper,gate or Agent regression/control.

114 remains **infrastructure interrupted/null**, with its raw supervisor running/not_run and absent
final_integrity preserved. Worker integrity alone does not fill that gap. Its two deployment failures
recovered on the third; unexpected supervisorSIGTERM remains unexplained and is not claimed fixed by
the budget change. Counts: **32 isolated PASS,44 skips,115 attempts,76/94 processed,current Order132
running/retesting and17 other pending**. No score is claimed at launch; original **95/189** and baseline
pointer remain unchanged, with no full rerun or promotion.

## 2026-09-14 09:49 UTC Order132 deployment recovers; unexpected supervisor interruption preserves null

Attempt **114** ends as **infrastructure/supervisor interruption, null reward**. Worker records
**6 events /7 actual requests /520.739 seconds**, completed `2026-09-14T09:48:18.496547+00:00`,
zero completion rejections, integrity `ok` and no evaluator. Supervisor **16708** unexpectedly exits
**143/SIGTERM**, session **20525**; Root did not send that signal and its origin is unknown. Root then
observes worker **16764** under PPid1 and sends SIGINT to that exact orphan. Both processes are gone.
Worker returncode is not recorded by the departed supervisor and remains unknown.

The two [deployment failures](../experiments/work/all-holo-order132-attempt114-deploy-audit-20260914.md)
recover on the third attempt: OS health isok and task setup completes09:46:28.656, followed by Agent
requests. First,11PackageKit list-lock errors leave installation only1.273seconds from the shared90second
budget; second,23install attempts hit apt-get3594's frontend lock. Its parentage is unproven. **There is
no third deployment failure and no terminal environment_failure.** The later supervisor interruption is
separate from those recovered setup errors and does not test the terminal-receipt fix to completion.

Supervisor raw results stay **running/not_run**, last updated `2026-09-14T09:39:25.163393+00:00`,
with **no final_integrity**. Preserve that incomplete record; worker validation is not supervisor final
validation. Root results SHA-256 `011174b822d19e75275110af3ed834f8a99166170ee9a61f66333b7937d3b9f8`;
worker SHA-256 `51d36b92e0f09d31d9eeb6fb59ab7bdb8edcc2a2a07bd7d9628cd265df80f1e1`.
The [report](archive/all-holo-order132-terminal-receipt-retest-20260914.md) retains the process evidence.

Keep132 current. The next narrow repair gives update and installation separate90second budgets while
retaining45/60second command caps and existing lock retries in install.sh; runtime CommandRunner stays
unchanged. No115 is launched or registered by this entry. Counts remain **32 isolated PASS,44 skips,
114 attempts,76/94 processed,current132 preparing/not_started and17 other pending**. No new gate,
Agent regression/control or score; original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 09:40 UTC Order132 current terminal-receipt repair replay running

Attempt **114**, condition `holo31-all-roles-order132-terminal-receipt-retest-20260914-v1`, starts
`2026-09-14T09:39:25.160336+00:00`, supervisor **16708** / session **20525**; worker **16764** starts
`09:39:37.121679 UTC`. Only `[132]` is selected and both metadata statuses are running. Freeze
`09:38:25.142539 UTC`: **535 files /81,415,383 bytes**, source SHA-256
`abd0aee9a1cd8c6c1c1785cbd80431f72025ff51048d348b25497084917148a9`;
config SHA-256 `164169d29fa1e3257210b411637cd9fba5a1bb82739144e3fe56a324cda029c4`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain.

The [minimal repair](archive/all-holo-order132-terminal-receipt-retest-20260914.md) reuses only the
current action's complete matching verified terminal marker/transcript/window receipt inside the existing
verifier branch. Unrelated/incomplete contexts retain live probes; command argv/returncode checks stay
intact. No worker/spec/schema/new helper/gate or grading logic. Three focused existing-fixture cases
cover real worker reuse,missing window and unrelated observation; **37 relevant terminal/shell checks
pass in1.25seconds**, with Ruff/scoped diff. Architecture notes describe the current-call scope.
Truthful success feedback may help the model proceed, but absent document reads/grade writes remain
separate behavior; no task recovery is claimed from focused checks.

Counts: **32 isolated PASS,44 skips,114 attempts,76/94 processed,current Order132 running/retesting
and17 other pending**.131's skip adds no episode;113 stays failed0.0 and112 stays null. No new score is
claimed at launch. Original **95/189** and baseline pointer remain unchanged; no Agent regression/control,
full rerun or promotion.

## 2026-09-14 09:36 UTC Order130 invalid-DOCX failure;131 offline skip; next132 terminal receipt

Attempt **113** ends **failed, reward0.0**, **30 events /33 actual requests /980.744 seconds**,
agent_done and zero completion rejections. Worker completes `2026-09-14T09:33:57.484184+00:00`;
supervisor finalizes `09:34:01.797175 UTC`. Supervisor **34216** and worker **34283** are gone;
session **72194** and worker exit **0**, both integrity records are `ok`. Supervisor result SHA-256
`43ae6deb33056826dc94c88289e8e40a8beedf1b88b679fba248615dac4815e0`;
worker result SHA-256 `9ffc6ba91344c19f1006e943812497d2369fef9e38adfda9d54fe6e58fd0f26d`.

The GUI input description is delivered.11 persists all2249joined source bytes and19 loads them into
Writer, but21 copies the plain text to the DOCX filename.28 cancels Save As;29 still shows2249bytes.
30done and terminal review confirm. The evaluator fetches the file but reports **Package not found**:
invalid DOCX format, not missing file/content. The [final report](archive/all-holo-order130-paragraph-boundary-retest-20260914.md)
preserves112 interrupted/null and113 failed0.0. Skip130 after two hypotheses; retain paragraph/GUI
descriptions without a format gate, automatic conversion or third unchanged attempt.

Then [skip131 offline](archive/all-holo-order131-renderer-difference-skip-20260914.md), with **no isolated
episode**. All eight chapter ranges/names and raw source-text checks are correct. The user required
example naming, not its Cairo producer; golden-derived renderer prompting would add an unrequested
condition. Independent review supports no shared extraction defect. Preserve original fractional
**0.9954928416511726 as failed**, with no added PASS or attempt.

Current **Order132**, queue77, has a [documented terminal receipt defect](../experiments/work/all-holo-order132-triage-20260914.md):
a completed visible command has matching transcript/window evidence, then a redundant second observation
returns null and overrides it. Planned reuse stays within the existing verifier and current action's
complete matching receipt; unrelated/standalone checks retain live reads. This is secondary to the model
never reading/scoring the remaining students, so it does not establish task recovery. No new framework,
gate, grading macro or114 launch. Counts: **32 isolated PASS,44 skips,113 attempts,76/94 processed,
current132 diagnosing/not_started and17 other pending**. Original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 09:18 UTC Order130 GUI delegation input description replay running

Attempt **113**, condition `holo31-all-roles-order130-gui-literal-context-retest-20260914-v1`, starts
`2026-09-14T09:17:26.685373+00:00`, supervisor **34216** / session **72194**; worker **34283** starts
`09:17:35.916559 UTC`. Only `[130]` is selected and both metadata statuses are running. Freeze
`09:16:28.953969 UTC`: **535 files /81,411,991 bytes**, source SHA-256
`f9d54035e9f183599b4ef5a90d26a63e972b41b293f2d48bc7ddb401d9ec7eb7`;
config SHA-256 `e352fbca280f9eeda250ad3bc5a7520db1847b461ca5264c7e82428a5e5819a3`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain.

Only gui_actions.py's existing intent description changes relative112. It explains that grounding sees
the current request and screenshot, not prior tool results; typing needs explicit literal text, paste uses
existing clipboard contents, and long text can use separately searched Adapter operations. Generated
Writer/constrained Multi-Apps schemas retain the exact single contract and2000-character bound and
accept the same synthetic literal request unchanged. Ruff/scoped diff pass. No new tests, parameters,
routing, content injection, gateway, gate or Agent regression/control. The
[second hypothesis](archive/all-holo-order130-paragraph-boundary-retest-20260914.md) requires the model
to choose its own literal content or writing API, then format/save. Move on if it remains unsuccessful.

112 stays **interrupted/null**:22 recorded events plus unanswered actual request23, no evaluator or
actual write/save. Counts: **32 isolated PASS,42 skips,113 attempts,74/94 processed,current Order130
running/retesting and19 other pending**.131 remains pending. No score is claimed at launch. Original
**95/189** and baseline pointer remain unchanged; no full rerun or promotion.

## 2026-09-14 09:15 UTC Order130 bounded unscored GUI/read stop; delegation input hypothesis planned

Attempt **112** ends worker **interrupted/null**, **22 events /23 actual requests /794.564 seconds**,
zero completion rejections. Worker completes `2026-09-14T09:14:20.858426+00:00`; supervisor finalizes
`09:14:26.687392 UTC`. Supervisor **60155** and worker **60226** are gone; session **53859** exits **2**,
worker exits **0**, both integrity checks are `ok`. Supervisor `invalid_configuration/null` is its existing
interrupted-worker reportability wrapper. Root initiated SIGINT after21 under the declared unchanged
GUI/read-loop stop; in-flight22 GUI paste is preserved. No evaluator runs, so null is not a scored zero.
Supervisor result SHA-256 `de5c56800bc86eaf0d4754604adc2aca448828bbbb9dbf915025706a7b9823f1`;
worker result SHA-256 `600789f51182a23cea26a1a9aac246803fa8eeed6a03c7dac85f330c9470e448`.

Reads5–9 return all2249source characters and parent request11 retains each full string. The model never
discovers append/format/save schemas, so the paragraph wording remains unexercised. GUI11 delegates a
paste without literal text; the grounder receives only intent+screenshot and selects a click. Subsequent
Ctrl+V actions have no prior clipboard/text write; repeated font clicks do not enter the value.20 is blocked
by the existing duplicate-GUI rule and21 rereads the first source. No insertion/save is established. See
the [report](archive/all-holo-order130-paragraph-boundary-retest-20260914.md) and
[bounded audit](../experiments/work/all-holo-order130-attempt112-paragraph-audit-20260914.md).

Keep130 current for a distinct second hypothesis: clarify existing GUI_REQUEST_SCHEMA.intent wording
that grounding sees only the current request and screenshot, literal text must be supplied, clipboard
paste does not combine previous tool results, and long text can use searchable Adapter operations.
No argument, gateway or gate change; the model retains all content/action decisions. **113 has not launched
or been registered.**131's recommended skip has not yet changed its pending status or the counters.
Counts remain **32 isolated PASS,42 skips,112 attempts,74/94 processed,current130 preparing/not_started
and19 other pending**. Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 09:01 UTC Order130 paragraph-boundary description replay running

Attempt **112**, condition `holo31-all-roles-order130-paragraph-boundary-retest-20260914-v1`, starts
`2026-09-14T09:00:56.523271+00:00`, supervisor **60155** / session **53859**; worker **60226** starts
`09:01:05.523559 UTC`. Only `[130]` is selected and both metadata statuses are running. Freeze
`08:55:31.092297 UTC`: **535 files /81,411,548 bytes**, source SHA-256
`32b4a1c91aa330f921a7e50f03aa61f2ec3ddfdf1f67e5551594c709b0be4fdf`;
config SHA-256 `614289bf50128e042853bb3ebc1328d8d8eb2afdbd939e39001f01a09354b74b`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain.

Only writer_adapter/tool_manifest.py descriptions change relative111. Existing append action and
parameters explain that each array item creates a paragraph and zero extra blanks still retains
paragraph breaks. No-separator concatenation needs one string supplied by the model. Direct Writer/
constrained Multi-Apps schemas validate; synthetic one/two-string arguments pass existing native
validation with text unchanged. Ruff/scoped diff pass. No new tests, native behavior, implicit join,
semantic argument replacement, new route, gate or Agent regression/control. The
[hypothesis](archive/all-holo-order130-paragraph-boundary-retest-20260914.md) still requires the model
to preserve exact source/order, choose whole-document font scope and save.

The [closed111 audit](../experiments/work/all-holo-order128-attempt111-python-usage-audit-20260914.md)
settles the previous getter question: the exact requested path yielded a preserved **962x1280 RGB**
PNG, matching expected dimensions. `check_structure_sim` returns **binary0** with default threshold0.9;
no raw SSIM or measured margin was recovered or independently computed. It is an image-comparison-stage
failure after successful retrieval, with the unmodified save and missing reorder visible in the trace.
Terminal request23 retained that evidence but confirmed completion.111 remains failed0.0 and128 skipped.

Counts: **32 isolated PASS,42 skips,112 attempts,74/94 processed,current Order130 running/retesting
and19 other pending**. No score is claimed at launch. Original **95/189** and baseline pointer remain
unchanged; no full rerun or promotion.

## 2026-09-14 08:53 UTC Order128 scored failure and two-hypothesis skip; next130 paragraph contract

Attempt **111** ends **failed, reward0.0**, **22 events /23 actual requests /874.742 seconds**,
agent_done and zero completion rejections. Worker completes `2026-09-14T08:50:38.666298+00:00`;
supervisor finalizes `08:50:45.677070 UTC`. Supervisor **2461** and worker **2530** are gone;
session **37049** and worker exit **0**, both integrity checks are `ok`. Supervisor result SHA-256
`759e9d962e88c41202d05e1443a3281751e8d8dfe20f327e9a2b8d3b6c2df471`;
worker result SHA-256 `f0c565d567b8a32dc274c8a538c7dd7f41bd6ba081e08251b1485c316fdd1c7d`.

The Python usage description reaches actual requests.14/15/20 use valid comment-free simple statements
and create three in-memory crops;21 merely saves the original image as Desktop/rearranged.png.
22 claims rearrangement without any actual ordering/composition action. This is no PASS. Exact primary
getter/metric cause is still under offline review; the zero must not yet be attributed solely to an
image comparison. The [report](archive/all-holo-order128-structured-error-retest-20260914.md) and
[usage audit](../experiments/work/all-holo-order128-attempt111-python-usage-audit-20260914.md) preserve the evidence.
Skip128 after110 interrupted/null and111 failed0.0; retain the structured-error fix and minimal Python
usage guidance without a third unchanged replay, algorithm injection or new gate.

Current **Order130** has a [preserved content-boundary diagnosis](../experiments/work/all-holo-order130-triage-20260914.md):
all five source texts are saved in correct order, but five paragraphs introduce four separators that
violate the requested direct concatenation. Only paragraph0 receives10pt; the remaining paragraphs
inherit12pt. The first minimal hypothesis clarifies the existing append API's paragraph semantics;
the model must choose one exactly joined string when no separator is wanted. No new merge API,
content materialization, regression/control or112 registration.

Counts: **32 isolated PASS,42 skips,111 attempts,74/94 processed,current Order130 diagnosing/not_started
and19 other pending**. Original **95/189** and baseline pointer remain unchanged; no full rerun or promotion.

## 2026-09-14 08:37 UTC Order128 Python script usage description replay running

Attempt **111**, condition `holo31-all-roles-order128-python-script-usage-retest-20260914-v1`, starts
`2026-09-14T08:35:55.099685+00:00`, supervisor **2461** / session **37049**; worker **2530** starts
`08:36:02.927514 UTC`. Only `[128]` is selected and both metadata statuses are running. Freeze
`08:34:33.743284 UTC`: **535 files /81,411,002 bytes**, source SHA-256
`b158fee80ae1f8425b30b0aa5bcad1cd04f5ba23fc5749a8c69a415dbfd75a40`;
config SHA-256 `93dc0ff9c6c747c0161b33985cb3da5e38b7c2d9f958ae8dae99dd428f2c6317`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain.

Only os_adapter/tool_manifest.py changes relative110: one shared usage description in the existing
command.run and terminal.show_output argv schemas explains Python -c's single script argument,
newlines/indentation, JSON newline escaping and comment/semicolon semantics. Four generated direct/
constrained Multi-Apps schemas validate with unchanged argv types; Ruff/scoped diff pass. No added
tests, repeated module campaign, code coercion, helper, gate or Agent regression/control. The
[second hypothesis](archive/all-holo-order128-structured-error-retest-20260914.md) requires the model's
own valid script and actual analysis/composition/save. If unsuccessful, record the residual and move130.

Attempt110 remains **interrupted/null**. Its **30th actual request** dispatches step27 terminal audit
without receiving a response; completed event26 is propose_done reviewing25, not a completed terminal
audit. No original evaluator ran. Counts: **32 isolated PASS,41 skips,111 attempts,73/94 processed,
current Order128 running/retesting and20 other pending**. No score is claimed at launch. Original
**95/189** and baseline pointer remain unchanged; no full rerun or promotion.

## 2026-09-14 08:34 UTC Order128 bounded unscored command-loop stop; description hypothesis prepared

Attempt **110** ends worker **interrupted/null**, **26 events /30 actual requests /1562.783 seconds**,
zero completion rejections. Worker completes `2026-09-14T08:29:42.846748+00:00`; supervisor updates
`08:29:50.088135 UTC`. Supervisor **60104** and worker **60112** are gone; session **65020** exits **2**,
worker exits **0**, both integrity checks are `ok`. The supervisor `invalid_configuration/null` is its
existing interrupted-worker reportability wrapper. Root initiated SIGINT after observed25 repeated the
one-line Python comment loop. This is not a new user stop, deadline, environment failure or evaluator zero.
Supervisor result SHA-256 `107e1682bb00c2882db29fcfda615c4a563d9da8fab38475298e608522a12dbd`;
worker result SHA-256 `78be298d2ae1a56e8b77d274e828aea2f8aee82772f7f9b79b447fb3f2b96b34`.

Event10's native error reaches the next request and11 corrects the path. The error is2314 characters,
below6000, so the repaired large-error boundary has the four focused-test results, not live confirmation
from this event. Step10's first request is a recovered **protocol error**:4096-token truncation and a
string payload instead of an object. The actual call log corrects the earlier timeout inference.
Scripts10/11/25 place comments and later code on one physical line; `#` swallows the remaining operations.
14/16/24 save three crops only.25 emits opening/size stdout, with analysis, composition and final save
commented out. In-flight26 proposes done with fabricated warmth/save output and the gate accepts it;
neither terminal audit nor evaluator completes. Preserve null. See the
[report](archive/all-holo-order128-structured-error-retest-20260914.md) and
[bounded feedback audit](../experiments/work/all-holo-order128-attempt110-command-feedback-audit-20260914.md).

Order128 remains current, preparing a distinct second hypothesis: existing shared command argv descriptions
explain one Python -c script argument, actual newlines/indentation through JSON, JSON versus shell escaping,
and comment/semicolon rules. Only os_adapter/tool_manifest.py changes; four generated direct/forwarded
schemas validate and Ruff passes. The model still chooses and writes all code. No coercion, helper, gate,
regression/control or unchanged replay. If the second hypothesis fails, advance130.
Counts remain **32 isolated PASS,41 skips,110 attempts,73/94 processed,current128 preparing/not_started
and20 other pending**. **111 is not launched or registered.** Original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 08:05 UTC Order128 structured native-error repair replay running

Attempt **110**, condition `holo31-all-roles-order128-structured-error-retest-20260914-v1`, starts
`2026-09-14T08:03:29.902363+00:00`, supervisor **60104** / session **65020**; worker **60112**
starts `08:03:38.996445 UTC`. Only `[128]` is selected; both metadata statuses are running.
Source freeze `08:02:41.334632 UTC`: **535 files /81,410,429 bytes**, SHA-256
`17350fe89ad13de283f5ce3922c7d780ab9665a5a4ba3643dfd59a599458ae3b`;
config SHA-256 `1b4bc1621e944bc8a0be0d6cd9ac23e48558585c3cd788434258a81b13ce38b3`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain unchanged.

The [minimal repair](archive/all-holo-order128-structured-error-retest-20260914.md) retains structured
failed-response feedback_body instead of opaque compact preview, removing an unused import. Existing
sanitation/error-priority fitting,1200-character projected-error cap and message budgets are unchanged;
full raw failure remains in the host trace. Four focused cases pass through real LiteAgent/Executor/
failed-event/serialized normal-recovery paths with mocked large HTTP failures, preserving direct stderr
or nested terminal stdout diagnosis and selected argv while hiding metadata. **4/4 pass in1.42 seconds;
122 relevant module checks pass in5.19 seconds**, plus Ruff/scoped diff. No command correction, new
gate or Agent regression/control. Correct image thirds/order/save still require the model.

Counts: **32 isolated PASS,41 skips,110 attempts,73/94 processed,current Order128 running/retesting
and20 other pending**. No score is claimed at launch. Original **95/189** and baseline pointer remain
unchanged; no full rerun or promotion.

## 2026-09-14 07:55 UTC Order126 bounded discovery stop and skip; next128 error-boundary repair

Attempt **109** ends worker **interrupted/null**, **28 events /29 actual requests /943.481 seconds**,
zero completion rejections. Worker completes `2026-09-14T07:52:53.615311+00:00`; supervisor finalizes
`07:52:56.195683 UTC`. Supervisor **1482** and worker **1513** are gone; session **75782** exits **2**,
worker exits **0**, both integrity checks are `ok`. Supervisor `invalid_configuration/null` is the
existing interrupted-worker reportability wrapper. Root requested SIGINT after observed27 and sustained
input-discovery cycling; in-flight28 again opens Videos and is preserved. This is not a fresh user stop,
environment failure, source drift or evaluator zero. Supervisor result SHA-256
`d1f64b55b466d50427f849345a280e3087dc78d0ae8735b259417a6540e6e8e7`;
worker result SHA-256 `e67fa1b89970e86dada286b8c8b3c8ed4465f0586ae7b549816eead273f0bd30`.

Search2 improves on108's first search21 and descriptions reach actual requests. Grounder3 mislabels
and clicks Stop after an unnecessary repeated pause; execution matches its choice, and native stopped/
null-source feedback is truthful. Coordinate error13 reaches14 and recovers. Later discovery cycles
produce no extraction, background edit, save, done or evaluator outcome. The
[preserved report](archive/all-holo-order126-background-persistence-retest-20260914.md) retains both
attempts. Skip126 after two hypotheses;108's fractionalSSIM0.8819 remains failed, never a PASS.

Counts: **32 isolated PASS,41 skips,109 attempts,73/94 processed,current Order128 diagnosing/not_started
and20 other pending**. No110 attempt is registered. Its
[confirmed boundary review](../experiments/work/all-holo-order128-current-error-boundary-review-20260914.md)
shows a >6000-character failed Adapter body converted to opaque preview, then sanitized away before
the existing error fitter; original SyntaxError disappears from actual requests27–29. Root will make
the smallest structured-error repair through existing budgets/sanitation and focused real-executor
message verification. No semantic argument replacement, new gate, unchanged126 replay or full rerun;
original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 07:38 UTC Order126 exact-frame discovery description replay running

Attempt **109**, condition `holo31-all-roles-order126-exact-frame-discovery-retest-20260914-v1`,
starts `2026-09-14T07:37:01.086737+00:00`, supervisor **1482** / session **75782**;
worker **1513** starts `07:37:09.293579 UTC`. Only `[126]` is selected; both metadata statuses are
running. Source freeze `07:35:51.703789 UTC`: **535 files / 81,405,003 bytes**, SHA-256
`240a084f7883a4dec81eba7988f27b947dd8fb629d290418f497bcfa7b92a678`;
config SHA-256 `ece668fda0cac64322ca858dc77f9c40b4e12db8da5e396f4dd15663d683749c`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain unchanged.

Only tool_catalog.py descriptions change from108. Existing tools_search explains that searching
exposes Adapter calls; media.extract_frame explains exact model-selected source-time/frame-index PNG
extraction independent of GUI seeking. The old task-coincident timestamp example is removed. Direct
and actual constrained schemas preserve four parameters and exclusive selectors; structural checks,
Ruff/scoped diff pass. No test campaign, ranking/availability/parameter/frame-math/gate change or forced
API selection. The [second hypothesis](archive/all-holo-order126-background-persistence-retest-20260914.md)
requires the model to select its own extraction/background/save operations;108's exact frame mismatch
remains plausible, not a proven sole cause.

Preserve108's **failed rawSSIM0.8819290180289082**, with no added PASS or skip. Counts: **32 isolated
PASS,40 skips,109 attempts,72/94 processed,current Order126 running/retesting and21 other pending**.
No new score is claimed at launch. Original **95/189** and baseline pointer remain unchanged;
no regression/control, full rerun or promotion.

## 2026-09-14 07:35 UTC Order126 delivers a background but remains failed; second hypothesis retained

Attempt **108** ends **failed**, raw SSIM **0.8819290180289082**, with **27 events / 28 actual parent
requests / 1030.874 seconds**, `agent_done` and zero completion rejections. This is continuous image
similarity, not a PASS or an88.19% task-success rate. Worker completes
`2026-09-14T07:30:08.529460+00:00`; supervisor finalizes `07:30:13.923711 UTC`.
Supervisor **18735** and worker **18751** are gone; session **81495** and worker exit **0**, both
integrity checks are `ok`. Supervisor result SHA-256
`9840182583cb98760ceb4dcec46ab5711c389dda5ec430719cc2c0a473b75297`;
worker result SHA-256 `c383949fa20b10ad1e7c87d7ff1648e4ce2e702a2f107935c55c35174acc885d`.

The [closed actual audit](../experiments/work/all-holo-order126-attempt108-gui-discovery-audit-20260914.md)
counts25 GUI actions,1 search,1 done and0 Adapter dispatches. Search21 follows20 GUI steps and delivers
the new background/save description to actual22 through28, but no native receipt or Agent save occurs.
Evaluator postconfig saves a non-null embedded background, preserved as the finalized result PNG;
the remaining score is image mismatch. Whole-second GUI time does not identify an exact source frame.
Coarse sampling is plausible, with other image differences still possible; no sole timing cause is proven.

Keep **Order126 current/diagnosing** for a distinct second hypothesis: clarify that existing search
reveals Adapter calls, and describe exact-time/frame-index extraction independent of GUI seeking.
Remove the old task-coincident timestamp example without supplying a new target. Root is preparing
description/structural checks; availability, ranking, parameters, extraction math and gates stay unchanged.
No109 attempt is registered. Counts remain **32 isolated PASS,40 skips,108 attempts,72/94 processed
and21 other pending**. No skip,unchanged replay,regression/control or scorer change; original **95/189**
and baseline pointer are unchanged.

## 2026-09-14 07:14 UTC Order126 background/save guidance replay running; Order125 audit closed

Attempt **108**, condition `holo31-all-roles-order126-background-persistence-retest-20260914-v1`,
starts `2026-09-14T07:12:48.798703+00:00`, supervisor **18735** / session **81495**;
worker **18751** starts `07:12:56.800591 UTC`. Only `[126]` is selected; both metadata statuses are
running. Source freeze `07:11:46.354717 UTC`: **535 files / 81,403,980 bytes**, SHA-256
`fedb6f4be3b76634987a49e86af21d257810af5895309e4a72e2255ed7f5407e`;
config SHA-256 `c3844da15e403bf4cb1b4ec4f5e94bd0cffedbc82a5043384e3bf51f8ab9dc94`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain unchanged.

The [current repair](archive/all-holo-order126-background-persistence-retest-20260914.md) adds descriptions
to existing background/presentation.save schemas and returns `saved_by_action=false` plus separate-save
guidance from the owning background handler. Parameters, bitmap loading and save implementation are
unchanged. **22 existing background checks pass in0.96 seconds**, plus Ruff and scoped diff. Synthetic
real-worker/native color/selected-slide/no-auto-save, forwarded guidance, schema and discovery checks
pass; these verify scope/feedback, not persisted image content. The model must select save and inspect
delivery. No forced action, automatic save, new route/gate or Agent regression/control.

Order125's107 audit is now closed: finder description reaches schema6, and discovery/extraction/native
URL read-back are exercised with model-selected arguments. No Agent save/playback follows; formal
result=[null] scores zero before comparison. Its input-identical cached PPTX is supplementary mutable
evidence, not a finalized artifact; old cached WAVs are not attributable to107. Evaluator save-failure
mechanism remains unproven. Counts: **32 isolated PASS,40 skips,108 attempts,72/94 processed,current
Order126 running/retesting and21 other pending**. No new PASS is claimed at launch. Original **95/189**
and baseline pointer remain unchanged; no full rerun or promotion.

## 2026-09-14 07:06 UTC Order125 discovery and insertion improve but evaluator fails; next126

Attempt **107** returns original evaluator **failed/0.0**, `agent_done`, **10 events / 11 actual parent
requests / 294.341 seconds**, zero completion rejections. Request11 is terminal-only review. Worker
completes `2026-09-14T06:55:16.484605+00:00`; supervisor finalizes `06:55:23.385722 UTC`.
Supervisor **37826** and worker **37834** are gone; session **4956** and worker exit **0**, both final
integrity checks are `ok`. Supervisor result SHA-256
`8af206d5108f2781d4b7870aaad835bdf0dc3207e6e598a41e7379dc425928eb`;
worker result SHA-256 `62b301cd04810d927a74c0f4c92f08b4336564ba3ff871aaf3b2880b7f329cd8`.

Step6 finds the source,7 extracts audio and8 inserts it with independent native URL verification.
Step9 repeats the same insertion and is blocked;10 prematurely proposes done without an Agent save.
Formal evaluator artifact result is null. A supplementary run-local cached PPTX, mtime
`06:55:07.953176 UTC`, SHA-256 `662a929926e06d62024feb6df1e01555237fd894f7a173c22d7395fc20dd0f96`,
is byte-identical to input with no inserted audio on any slide. It is not a sealed scored artifact.
The failure is therefore not solely the selected zero-based slide1; the exact save/persistence mechanism
remains unproven. The [result report](archive/all-holo-order125-local-file-discovery-retest-20260914.md)
retains these limits; final literal audit is being closed.

Skip125 after two behavioral hypotheses and one setup-only failure, preserving105 environment_failure,
106 interrupted/null and107 scored0. Counts: **32 isolated PASS,40 skips,107 attempts,72/94 processed,
current Order126 diagnosing/not_started and21 other pending**. No108 attempt is registered.
Its [preserved triage](../experiments/work/all-holo-order126-triage-20260912.md) shows background bitmap
mutations without Agent save, an unchanged fetched file and save not exposed in late requests. Root is
preparing minimal truthful action/result save guidance after read-only diagnosis, keeping saving
model-selected. No automatic save, new gate, unchanged replay or speculative native persistence fix.
Original **95/189**, baseline pointer and no-regression policy remain unchanged.

## 2026-09-14 06:52 UTC Order125 local-file discovery and OCR budget replay running

Attempt **107**, condition `holo31-all-roles-order125-local-file-discovery-retest-20260914-v1`,
starts `2026-09-14T06:50:13.344295+00:00`, supervisor **37826** / session **4956**;
worker **37834** starts `06:50:21.388211 UTC`. Only `[125]` is selected; both metadata statuses are
running. Source freeze `06:48:55.226401 UTC`: **535 files / 81,402,940 bytes**, SHA-256
`94fdc47ff919460c9a11503958ad780b701fa37f4ab86f73f5d8b52760a6f98e`;
config SHA-256 `befd7159d7927cada6846ce67421327d01b09cedd4be7eb5e0b14bc46d3a1a1c`.
Existing frozen validation is `ok`; source/tests remain frozen through both exits. Paired Holo
thinking/T0.8/top_k7,100global/50local steps,one same-VM restart,1800Agent seconds and30GiB floor remain unchanged.

The [new report](archive/all-holo-order125-local-file-discovery-retest-20260914.md) records plain
filesystem.find purpose and corrected basename-glob help, without task/media words, added keywords,
ranking code, API semantics or model argument changes. Actual query rank6→5; current three-query
ranks are5/4/4 under the original instruction. **12 existing active-project search checks pass in1.45
seconds** and constrained-schema structural checks pass. OCR apt commands/backoff now share90 seconds,
with command timeouts capped to the remaining budget inside the existing120-second outer execute limit.
**6 installer checks pass in1.26 seconds**, plus Ruff/bash syntax/scoped diff. No Agent regression/control.

Attempt106's final audit is closed at **33 events / 34 actual parent requests**. In-flight32 repeats
the dock click and is blocked;33 repeats workspace search with changed patterns and fails;34 retains
the error/restored GUI and starts Cancel grounding, with no response, dispatch or event. All33 parent
raw/canonical calls,6 Adapter dispatches and15 GUI dispatches retain selected arguments and feedback.
There is no text entry, save, extraction or insertion. Preserve105 environment_failure and106 null.

Counts: **32 isolated PASS,39 skips,107 attempts,71/94 processed,current Order125 running/retesting
and22 other pending**. This is the second behavioral hypothesis after one setup-only failure, with
original evaluator PASS still required. No new gate/full rerun/promotion; original **95/189** and
baseline pointer remain unchanged.

## 2026-09-14 06:44 UTC Order125 lookup-loop stop; retain task for a distinct discovery hypothesis

Attempt **106** ends worker **interrupted/null**, **33 events / 1272.279 seconds**, zero completion
rejections. Worker completes `2026-09-14T06:41:07.020525+00:00`; supervisor finalizes
`06:41:10.986963 UTC`. Supervisor **42816** and worker **42827** are gone; session **25718** exits
**2**, worker exits **0**, both final integrity checks are `ok`. Supervisor `invalid_configuration/null`
is the existing interrupted-worker reportability wrapper. Root stops the sustained file-lookup/search
loop after31 and preserves final in-flight33. This is not a fresh user stop, source drift, environment
failure or evaluator zero. Supervisor result SHA-256
`0f5a475608a08353c701222c76bccc919862bce37f9379b907724dbe23470751`;
worker result SHA-256 `f9a96460daddf3c9dc5c54d92eaab2f0ff235cb9986b8a42f09de44686eba949`.

Setup completes without an apt-lock/retry log, so the retry branch is not exercised live. Audio
semantics reach actual requests11–13; GUI block9/search10 restores GUI11. Integer-coordinate errors
are fully returned despite continued arrays. Searches12/29 expose workspace.find_files, then14/30
fail native WORKSPACE_UNAVAILABLE outside an active VS Code project. No extraction or insertion
occurs, leaving native URL verification unexercised. See the
[preserved report](archive/all-holo-order125-audio-semantics-retest-20260914.md).

Offline actualquery12 ranks general filesystem.find6, outsideTop5; the route is truncated, not
forbidden. The next planned minimal change is its action description and clear simple-glob guidance,
distinguishing generic filesystem search from active-workspace discovery. Ranking algorithm, API
semantics, model arguments and gates stay unchanged. A separate planned deployment correction aligns
the whole OCR phase's90-second budget with the existing120-second outer execute limit;106's frozen
source had only a retry-decision deadline. Neither planned change is a registered107 attempt.

Keep **Order125 current/diagnosing**, preserving105 environment_failure and106 interrupted/null.
Counts remain **32 isolated PASS,39 skips,106 attempts,71/94 processed and22 other pending**.
No skip,107 launch, regression/control or full rerun. Original **95/189** and baseline pointer are unchanged.

## 2026-09-14 06:21 UTC Order125 deployment-lock follow-up running

Attempt **106**, condition `holo31-all-roles-order125-apt-lock-retest-20260914-v1`, starts
`2026-09-14T06:19:45.844019+00:00`, supervisor **42816** / session **25718**; worker **42827**
starts `06:19:53.949728 UTC`. Only `[125]` is selected; both metadata statuses are running.
Source freeze `06:18:54.184111 UTC`: **535 files / 81,400,833 bytes**, SHA-256
`2902d1ce0519cb540f9117a0370c260c671b19fe9de98c968091d6f274622bcc`;
config SHA-256 `913024dfc938aece44a07747623b9d9e0388813f16f70cd5c772ae0587176125`.
Existing frozen validation is `ok`. Source/tests stay frozen through both exits; paired Holo service,
100 global / 50 local steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor remain unchanged.

The [environment follow-up](archive/all-holo-order125-audio-semantics-retest-20260914.md) changes only the
existing OCR installer's native apt-lock retry and a focused test. It retries the same command only
for code100 / “Could not get lock”; unrelated failures propagate. **5 tests in1.44 seconds**, bash
syntax, Ruff and scoped diff pass. Audio semantics/native URL and GUI changes from105 are unchanged.
The shared90-second deadline limits lock retry decisions; original45/60-second command timeouts remain,
and the outer `/execute`120-second budget may cut a long sequence. It is not a90-second hard cap for
the entire phase. This limitation was identified after launch; observe actual setup without a live patch.

Preserve105's pre-Agent environment failure. Counts: **32 isolated PASS, 39 skips, 106 attempts,
71/94 processed, current Order125 running/retesting and22 other pending**. No PASS is claimed at launch.
No regression/control, lock deletion, PackageKit stop, new runtime API/gate, full rerun or promotion;
original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 06:17 UTC Order125 attempt105 fails during deployment; keep current task

Attempt **105** ends **environment_failure/null** after **70.995 seconds**, before any Agent event,
Agent request or audio operation. `os_adapter` deployment runs `apt-get update`, but
`/var/lib/apt/lists/lock` is held by process **1167 (packagekitd)**. All three existing deployment
attempts fail with apt exit **100**. Worker completion is `2026-09-14T06:15:44.216230+00:00`;
supervisor finalization is `06:15:49.154684 UTC`. Supervisor **31619** and worker **31655** are gone,
session **18254** exits **0**, and both final integrity checks are `ok`. Both metadata statuses are
completed with task status environment_failure; this is not the interrupted-worker wrapper.
Supervisor result SHA-256 `fc1bb589917861b2f8813fad500874d68eab21db1b79b711cf3a472c521fd09f`;
worker result SHA-256 `4136764657967b55258b2afd787f6e7deb6ba727f41e3d8c8b4771a724a64915`.

The [audio repair](archive/all-holo-order125-audio-semantics-retest-20260914.md) has not been exercised by
the Agent, so this outcome does not assess its semantics or native URL evidence. Preserve105 and keep
**Order125 current/diagnosing** while root diagnoses the smallest deployment fix. No skip or106 launch
is registered. Counts remain **32 isolated PASS, 39 skips, 105 attempts, 71/94 processed and 22 other
pending**. Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 06:15 UTC Order125 audio semantics and native URL read-back replay running

Attempt **105**, condition `holo31-all-roles-order125-audio-semantics-retest-20260914-v1`,
starts `2026-09-14T06:14:24.140734+00:00`, supervisor **31619** / session **18254**;
worker **31655** starts `06:14:32.479253 UTC`. Only `[125]` is selected and both metadata statuses
are running. Source freeze `06:13:19.339077 UTC`: **534 files / 81,398,040 bytes**, SHA-256
`0105850a088ee5fb9f25247cb16e8eda48a10b66b49a787a329b81a1cc2f16f2`;
config SHA-256 `827d3c08d1a28cc96ed8dc4f0b560dae75dc6f8b6b5bf6f88420e342b0191d84`.
Existing frozen validation is `ok`; source/tests stay frozen through both exits. Paired direct Holo2
thinking/T0.8/top_k7, 100 global / 50 local steps, one same-VM restart, 1800 Agent seconds and 30 GiB
floor remain unchanged.

The [minimal repair](archive/all-holo-order125-audio-semantics-retest-20260914.md) explains that audio.insert
inserts one audio object on a selected slide, separately from playback, looping, transition sound or
saving. Existing native shape-properties verification reads MediaURL against the model-selected path;
mismatch returns the existing HTTP422 verification error with observed partial insertion. It does not
claim playback or cross-slide behavior is verified. **32 focused tests in1.48 seconds**, Ruff for three
changed Python files and scoped diff pass. No new playback setting/API, macro, gate framework or
regression/control episode. Original WAV extraction/insertion already worked; remaining playback
configuration and save must still be model-selected, with original evaluator PASS required.

Counts: **32 isolated PASS, 39 skips, 105 attempts, 71/94 processed, current Order125 running/retesting
and 22 other pending**. No scored outcome is claimed at launch. Original **95/189** and baseline pointer
remain unchanged; no additional full run or promotion.

## 2026-09-14 06:03 UTC Order124 GUI recovery verified; bounded skip and Order125 diagnosis

Attempt **104** ends worker **interrupted/null**, **38 events / 41 actual parent requests / 1107.848 seconds**, one completion
rejection. Worker completion is `2026-09-14T06:01:39.460103+00:00`; supervisor finalization is
`06:01:42.531077 UTC`. Supervisor **32598** and worker **32663** are gone; session **9977** exits
**2**, worker exits **0**, both final integrity checks are `ok`. Supervisor `invalid_configuration/null`
is the existing interrupted-worker reportability wrapper. Root stopped the sustained image-open/close
loop; this is not a fresh user stop, environment failure, source drift or evaluator zero.
Supervisor result SHA-256 `bda59029e4191c6264e4565b87a98956708a32b7103b7ca9d71913470404ef39`;
worker result SHA-256 `e5f8eba45f803511709b03c473ad5fea885ffde471207854340b4f02469eb1a1`.

Final-audit correction: repeated GUI block18 is followed by `propose_done`19, rejected with `task_state`;
it is not a search. Request20 receives the complete rejection and restores/executes GUI, confirming
recovery after that replan. Events17–36 remain image-open/close cycles without rename. Search37 ranks
rename first and its full schema reaches actual request40; step38 still repeats the blocked close.
Steps30/31 each have one request retry; last request41 is step39 without a completed event. Event totals
are31 GUI,6 searches,1 done and0 Adapter calls. The
[closed literal audit](../experiments/work/all-holo-order124-attempt104-gui-audit-20260914.md) confirms
unchanged selected execution and delivered feedback, but no filename mutation. Preserve the
[Order124 outcome](archive/all-holo-order124-gui-recovery-retest-20260914.md) and skip without an unchanged
replay. Counts: **32 isolated PASS, 39 skips, 104 attempts, 71/94 processed, current Order125 diagnosing
and 22 other pending**. No105 attempt is registered.

The [Order125 review](../experiments/work/all-holo-order125-prospective-review-20260914.md) establishes
successful original extraction/insertion, followed by playback/search/reinsertion loops and no save.
The existing GUI restoration applies after its original block16/search17. The owning audio insertion
contract lacks clear playback semantics and its default native verification has no checks. A minimal
description/read-back repair is planned using existing shape properties; it must not claim playback
or cross-slide behavior is verified, infer arguments or add an extract-and-insert macro or new gate.

Order122's final audit is closed: **37 events / 38 actual parent requests**. Final36/37 remain drag
selection and leave a damaged filename without invoice save or tally edit. Complete write focus/selection
guidance reaches grounding16/25/30/33/36/37; raw actions, prepared commands and next-parent feedback
preserve model choices. No Ctrl+A is selected. GUI restores at10→11,19→20,23→24. These confirm
mechanisms without a PASS. Original **95/189**, baseline pointer and no-regression repair policy remain unchanged.

## 2026-09-14 05:44 UTC Order124 existing GUI-recovery repair replay running

Attempt **104**, condition `holo31-all-roles-order124-gui-recovery-retest-20260914-v1`,
starts `2026-09-14T05:43:02.404825+00:00`, supervisor **32598** / session **9977**;
worker **32663** starts `05:43:10.450170 UTC`. Only `[124]` is selected and both metadata statuses
are running. Source is unchanged from102/103: **534 files / 81,394,154 bytes**, frozen
`05:41:55.356675 UTC`, SHA-256 `b3768042a1b12f3cc145932eb75035209430d2251663c37b2212f708d3f11132`.
Config SHA-256 `9bcd76adcdc770b9a21e754620373b460e59e201963bcfe9b853a0c4feb25503`;
existing frozen validation is `ok`. Source/tests remain frozen through both exits. No new code or
test campaign; paired Holo thinking/T0.8/top_k7, 100 global / 50 local steps, one same-VM restart,
1800 Agent seconds and 30 GiB floor remain unchanged.

The [current report](archive/all-holo-order124-gui-recovery-retest-20260914.md) tests GUI restoration
after the replan turn against this task's actual six-step repeated-action windows. Offline actual-event
replay restores alternatives through11/15/21 while retaining active exact-request blocks; the old
window naturally expires at16. No source, target, history or argument is rewritten. Mountain identity
and correct renames remain model responsibilities; the rename API already existed and OCR cannot
identify unlabeled scenes. No new API/gate, regression/control, unchanged replay or full rerun.

Counts: **32 isolated PASS, 38 skips, 104 attempts, 70/94 processed, current Order124 running/retesting
and 23 other pending**. Order122's interrupted/null final evidence and pending36/37 literal audit are
preserved. Original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 05:41 UTC Order122 feedback mechanisms work; bounded unscored skip and Order124 diagnosis

Attempt **103** ends worker **interrupted/null**, **37 events / 1341.089 seconds**, zero completion
rejections. Worker completion is `2026-09-14T05:39:49.331419+00:00`; supervisor finalization is
`05:39:54.326659 UTC`. Supervisor **46598** and worker **46669** are gone; session **68364** exits
**2**, worker exits **0**, and both final integrity checks are `ok`. The supervisor's
`invalid_configuration/null` is the existing interrupted-worker reportability wrapper. Root stopped
the sustained naming loop; this is not a fresh user stop, environment failure, source drift or evaluator zero.
Supervisor result SHA-256 `a01d5081b7577697233c84ba0870136a8f6852e5ade0aaca2f1eb9b865118207`;
worker result SHA-256 `a583e2572d459447864bf0f32540677d2ed2ee1330134b0f6edbc61665604133`.

Errors2/3 reach actual grounding requests3/4, and4 uses valid coordinates. After repeated GUI block9,
request10 temporarily omits GUI; search10 restores it in11 and GUI12 executes. Scroll coordinates
are explicitly selected and valid. These are live confirmations of feedback retention and GUI recovery.
The model infers the correct intended filename at16 but types it into Search; screenshot20 retains
the old Name and disabled Save. Directory inspection28 shows only five existing PDFs. Events29–35
repeat Name concatenation/selection without saving the invoice or writing the tally; final in-flight
36/37 await literal audit. See the [preserved result](archive/all-holo-order122-feedback-retention-retest-20260914.md).

Skip122 without an unchanged repeat or new field-editing macro. Counts: **32 isolated PASS, 38 skips,
103 attempts, 70/94 processed, current Order124 diagnosing and 23 other pending**. Order123 is not
in the failure queue; no104 launch is registered. The
[Order124 follow-up](../experiments/work/all-holo-order124-prospective-review-20260914.md) supersedes its
earlier skip suggestion: original repeated blocks hide GUI beyond the replan turn, while current
exact-event replay restores alternatives after search11/API21 and retains active exact-request blocks.
This supports an affected check of existing source. Mountain identification and naming remain model
responsibilities. No new source/tests, regression/control, gate, full rerun or baseline change;
original **95/189** is unchanged.

## 2026-09-14 05:18 UTC Order122 accumulated-feedback replay running; Order121 audit closed

Attempt **103**, condition `holo31-all-roles-order122-feedback-retention-retest-20260914-v1`,
starts `2026-09-14T05:17:19.188249+00:00`, supervisor **46598** / session **68364**;
worker **46669** starts `05:17:27.410974 UTC`. Selected orders are `[122]`; both metadata statuses
are running. Source is unchanged from102: **534 files / 81,394,154 bytes**, frozen
`05:16:03.561669 UTC`, SHA-256 `b3768042a1b12f3cc145932eb75035209430d2251663c37b2212f708d3f11132`.
Config SHA-256 `67f6e0bcbce6294fe0dc16edf0ac25249f8eb1e0f22b10fe938d442725e35a41`;
existing frozen validation is `ok`. No new source or test campaign; source/tests stay frozen through
both exits. Paired direct Holo2 thinking/T0.8/top_k7 and 100 global / 50 local steps, one same-VM
restart, 1800 Agent seconds and 30 GiB floor remain unchanged.

The [Order122 hypothesis](archive/all-holo-order122-feedback-retention-retest-20260914.md) tests existing
schema-feedback retention, inspection discovery guidance and write semantics. Correct naming and
tally write/save remain model responsibilities. Counts: **32 isolated PASS, 37 skips, 103 attempts,
69/94 processed, current Order122 running/retesting and 24 other pending**. No regression/control,
unchanged repeat, new API/gate, full rerun or baseline change; original **95/189** is unchanged.

Order121's final audit is now closed: **9 actual parent requests / 8 events**. The recipient route
ranks4 in search1 and its new description reaches requests2/6/7/8/9. Four addresses come from the
visible table; this episode has no whole-table `workbook.read_file` or `range.read`. Raw, canonical,
gateway and native requested/added/observed recipients match, with append mode and no subject selector.
The initial screen already contains the same draft with an empty To field; it receives the four
recipient pills. No new message is created or sent despite the completion reason saying “created.”
Exact native feedback reaches8/9. There is no repeated-action block, so GUI restoration is not
exercised live. The [PASS report](archive/all-holo-order121-recipient-discovery-retest-20260914.md)
retains that causal limit and the original evaluator reward1.0.

## 2026-09-14 05:16 UTC Order121 recipient edit PASS; Order122 now diagnosing

Attempt **102** returns original evaluator **PASS / 1.0** after **8 events / 379.964 seconds**,
`agent_done`, with zero completion rejections. Worker completion is
`2026-09-14T05:13:46.093930+00:00`; supervisor finalization is `05:13:52.173087 UTC`.
Supervisor **26985** and worker **27013** have both exited successfully; session **24844** exits **0**.
Both final integrity checks are `ok`. Supervisor result SHA-256
`51a25f78826569e86debc6d8ffc174b6ecdd67740f79533838bc24939a7c8085`;
worker result SHA-256 `03c8cb82970414d021872fb182a8b475b71894d6e91df1df410166b9366a8d94`.

Step6 successfully inspects the workbook; step7 uses `compose.set_recipients` to append four
model-selected emails without a subject; step8 proposes done. Recipient discovery is exercised live.
This episode contains no `RepeatedActionBlocked`, so the GUI restoration branch remains an offline
verification and cannot receive sole causal credit for this PASS. Final literal audit remains in
progress. See the [Order121 result](archive/all-holo-order121-recipient-discovery-retest-20260914.md).

Counts: **32 isolated PASS, 37 skips, 102 Agent attempts and 69/94 processed**. Current task is
queue70 / **Order122, diagnosing**, with **24 other pending** and no new attempt registered.
Its [preserved-failure review and hypothesis](archive/all-holo-order122-feedback-retention-retest-20260914.md)
connect existing schema-feedback retention, public workbook inspection guidance and GUI write semantics
to the original errors. No new source or tests are proposed; correct filename inference and tally
write/save still require the model. The original explicit-path read already released inspection,
so this is not a new bare-name matching claim. Original **95/189**, baseline pointer, no-regression
repair policy and existing runtime limits remain unchanged.

## 2026-09-14 05:08 UTC Order121 recipient discovery and GUI restoration replay running

Agent attempt **102**, condition `holo31-all-roles-order121-recipient-recovery-retest-20260914-v1`,
starts `2026-09-14T05:07:17.126356+00:00`, supervisor **26985** / session **24844**, worker **27013**
(started `05:07:25.465072 UTC`), selected `[121]`. Existing frozen validation is `ok`.
Source **534 files / 81,394,154 bytes**, frozen `05:06:35.238159 UTC`, SHA-256
`b3768042a1b12f3cc145932eb75035209430d2251663c37b2212f708d3f11132`;
config SHA-256 `0f409ae96b475efa44ed96130dac1142a81bd4928a4ef977ffb16a0048cd8a09`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

Recipient usage/keywords and one-turn GUI restoration pass **56 existing module tests**, Ruff and
scoped diff. Actual recipient-query replay ranks1/1/1/1. Completed GUI replay through production
LiteAgent.tools keeps the tool hidden after blocked13, then restores it at14/19/33/34/37/38. The
exact failed request stays blocked, and all remaining tool dictionaries equal the same-source
GUI-disabled build. Original search hits and event bytes are retained; no model, Adapter or GUI call
occurs during replay. See the [second121 report](archive/all-holo-order121-recipient-discovery-retest-20260914.md).

These checks establish access, not task completion. The model must still open the actual draft and
choose recipients; no macro, new route/gate, block reset or argument injection. Only **Order121** is
retesting/running. Counts: **31 isolated PASS, 37 skips, 102 Agent attempts, 68/94 processed and25
other pending**. Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 05:05 UTC Order121 closed audit adds persistent GUI-tool suppression to second repair

Attempt101's final audit is closed: **38 events / 39 actual parent requests**. Last36 searches,
37 admits unfinished work again and38 queries Trash; the final application is Calc and no recipient
edit occurs. Both unfinished claims33/37 receive task_state unchanged in requests34/38. The prior
workbook read remains valid, but the old GUI block is a separate tool-surface problem: after13 receives
an exact-argument block, **every request14–39 omits gui_request**, even after successful active inspection.
This is not a fresh spreadsheet rejection. The recipient API does eventually reach requests35/37/38/39
after search34, so it was delayed discovery plus missing GUI, not an API absent throughout.

The [second121 repair](archive/all-holo-order121-recipient-discovery-retest-20260914.md) now covers
four existing files: recipient usage description, four generic keywords, the one-turn GUI suppression
scope, and focused recovery-surface tests. Only the latest repeated-GUI rejection temporarily hides
the tool; a model-selected search/API turn restores alternatives while the failed exact request remains
blocked. **56 existing module tests**, Ruff for four Python files and scoped diff pass. Final actual
recipient searches rank **1/1/1/1**, with unchanged schemas and Top5 budget. Actual GUI-surface replay
under the new source remains in progress. No new route, macro, gate, argument injection or block reset.

Counts remain **31 isolated PASS, 37 skips, 101 Agent attempts, 68/94 processed and 25 other pending**.
Order121 remains current/diagnosing; no102 launch/registration, skip, queue advance or original95/189 change.

## 2026-09-14 04:58 UTC Order121 workbook read succeeds; separate recipient-tool discovery repair retained

Attempt **101** finalizes `2026-09-14T04:56:28.754673+00:00`; worker completion was
`04:56:23.434640 UTC`. Worker **interrupted/null**, **38 events / 910.918 seconds**, two completion
rejections. Supervisor **38523** / session **12554** exits **2** with the existing interrupted-worker
`invalid_configuration/null` wrapper; worker **38560** exits **0**. Both processes are gone and both
final source/config integrity checks are `ok`. This was root's bounded draft/query-loop stop, not a
fresh user stop, environment failure, source drift or evaluator zero. Supervisor results SHA-256
`592e2d4fe11d71f8ce36ed4291a6c4022b45af99034f40b6243bd66fd9123efc`;
worker results SHA-256 `858eb6885b272b91962c38cdef4b7ced25b2b1a458bb3f33c1f15b1aee32a558`.

Active workbook inspection14 succeeds and18 delivers all27 rows; the model identifies four correct
emails. It then searches for drafts and guesses missing folders without editing recipients. At33
the unfinished completion claim correctly receives **task_state**, exercising the120 classifier
repair live without task recovery. Final36–38 remain preserved and await literal audit. Through the
audited32 slice no GUI follows14, so workbook reading alone does not prove later mail GUI release.
See the [first121 report](archive/all-holo-order121-observed-workbook-retest-20260914.md).

**Order121 stays current/diagnosing** for a distinct
[recipient-tool discovery repair](../experiments/work/all-holo-order121-mail-contract-review-20260914.md).
Actual searches19/21/23/24 rank the existing compose.set_recipients at **6/9/26/18**, outside Top5;
the route is not excluded. It lacks a top-level description and action keyword entry. Four generic
keywords alone give offline ranks **2/2/1/1**. Root will add generic usage/open-compose prerequisites;
a child handles the four keywords and focused retrieval checks. Parameters, native behavior and search
budget stay unchanged; no new route, macro, gate or automatic recipient/draft selection.

Counts remain **31 isolated PASS, 37 skips, 101 Agent attempts, 68/94 processed and 25 other pending**.
No102 registration, skip or queue advance; original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 04:42 UTC Order121 accumulated workbook-observation repair replay running

Agent attempt **101**, condition `holo31-all-roles-order121-observed-workbook-retest-20260914-v1`,
starts `2026-09-14T04:41:03.637118+00:00`, supervisor **38523** / session **12554**, worker **38560**
(started `04:41:11.681425 UTC`), selected `[121]`. Existing frozen validation is `ok`.
Source **534 files / 81,391,079 bytes**, frozen `04:40:19.570131 UTC`, SHA-256
`feabd5e55b959f68b21c8d667779fcc831307912b27a6b46a91db5e2f47ca0e2`;
config SHA-256 `15eca79b5e7ed478d41e2e8e1b8fbf674a6487cb16c59285bd6602548bb54524`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

This checks existing Order103 active-workbook basename handling with **no source/test change from100**.
Actual121 offline replay preserves unresolved focus after background read26 and clears it after active
inspection28, allowing later mail GUI. No new code, test campaign, gate or recipient materialization;
the model still chooses the draft and recipients. See the [Order121 report](archive/all-holo-order121-observed-workbook-retest-20260914.md).

Attempt100's final audit is now closed: **28 events / 29 parsed parent requests / 28 grounding requests /
24 executed actions**, all without modifiers. Coordinate-array errors4/21/24 fully reach5/22/25;
the final person remains damaged with residual sky/mountains, no undo/export/done/evaluator.
The classifier's live branch remains unexercised; its focused/offline evidence is separate.

Only **Order121** is retesting/running. Counts: **31 isolated PASS, 37 skips, 101 Agent attempts,
68/94 processed and 25 other pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control, full rerun or promotion.

## 2026-09-14 04:40 UTC Order120 editing damage and bounded skip; next121 existing workbook repair

Attempt **100** finalizes `2026-09-14T04:38:49.004854+00:00`; worker completion was
`04:38:45.988020 UTC`. Worker **interrupted/null**, **28 events / 1117.981 seconds**, zero completion
rejections. Supervisor **60201** / session **64760** exits **2** with the existing interrupted-worker
`invalid_configuration/null` wrapper; worker **60254** exits **0**. Both processes are gone and both
final source/config integrity checks are `ok`. This is root's predeclared loop stop, not a fresh user
stop, source drift or evaluator zero. Supervisor results SHA-256
`a28aac5e91b67995f1845a157e7c1321099aa662fa10fa0707d00e2b8f83450f`;
worker results SHA-256 `571185f09e7708a6fab292fb1c7d82285c634355acd8d8f6e2c33940a6a8208f`.

The checkerboard at10 becomes a full photograph after11; this transient display has an unknown cause,
not a confirmed environment failure. Clear14 removes upper sky, but selection15 and Clear17 erase
parts of the person's head, jacket and backpack while scenery remains. Steps18–28 repeat selection/
options/Clear without undo or export. No propose_done occurs, so the classifier fix is **unexercised
live**; its12 tests and actual99 offline replay remain separate evidence. Nonempty modifiers are not
seen, pending final audit. See the [final100 report](archive/all-holo-order120-incomplete-claim-retest-20260914.md).

**Order120 is skipped** after two distinct99/100 attempts with no PASS; no third unchanged repeat.
Actual next **queue69 / Order121** is **current/diagnosing**, with no101 episode registered. Its
[affected-check report](archive/all-holo-order121-observed-workbook-retest-20260914.md) uses the existing
Order103 active-workbook basename repair. Actual121 offline replay keeps the open unresolved after
background read26 and clears it after active inspect28, releasing subsequent mail GUI without inserted
events or arguments. No new code, test suite or gate is needed; draft/recipient choices remain model work.

Counts: **31 isolated PASS, 37 skips, 100 Agent attempts, 68/94 processed and 25 other pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control, full rerun or promotion.

## 2026-09-14 04:20 UTC Order120 unfinished-claim recovery priority replay running

Agent attempt **100**, condition `holo31-all-roles-order120-incomplete-claim-retest-20260914-v1`,
starts `2026-09-14T04:19:58.878499+00:00`, supervisor **60201** / session **64760**, worker **60254**
(started `04:20:07.100647 UTC`), selected `[120]`. Existing frozen validation is `ok`.
Source **534 files / 81,391,079 bytes**, frozen `04:15:08.207914 UTC`, SHA-256
`feabd5e55b959f68b21c8d667779fcc831307912b27a6b46a91db5e2f47ca0e2`;
config SHA-256 `01e65da81918652525d6d08558374d5c20aa5c914cc904350dba157f3be7a66e`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

Only two existing classifier branches change order: semantic unfinished-work errors select task_state,
while purely malformed claims with complete structural state keep claim_only. **12 existing focused
tests pass**, with Ruff/scoped diff passing. Actual99 step24 offline replay changes only recovery mode
and associated guidance; all three diagnostics, arguments and other fields remain unchanged, and
events/requests24–26 stay byte-identical. No acceptance criteria, contradiction pattern, gate or mode is
added. See the [second120 report](archive/all-holo-order120-incomplete-claim-retest-20260914.md).

This corrects false guidance; GUI was not locked out in99. Image opening, editing and JPEG export
remain model responsibilities. Only **Order120** is retesting/running. Counts: **31 isolated PASS,
36 skips, 100 Agent attempts, 67/94 processed and 26 other pending**. Outcome pending; no regression/
control, full rerun, promotion or original **95/189** change.

## 2026-09-14 04:12 UTC Order120 first replay unscored; independent unfinished-claim feedback defect retained

Attempt **99** finalizes `2026-09-14T04:10:25.213653+00:00`; worker completion was
`04:10:20.836002 UTC`. Worker **interrupted/null**, **37 events / 1051.64 seconds**, one completion
rejection. Supervisor **2994** / session **56392** exits **2** with the existing interrupted-worker
`invalid_configuration/null` wrapper; worker **3068** exits **0**. Both processes are gone and both
final source/config integrity checks are `ok`. This was root's bounded stop, not a fresh user stop,
environment failure, source drift or evaluator zero. Supervisor results SHA-256
`69b00a6279f1401f15deb6267004ec4066ab28a6ac405738dd03cb774b3b0567`;
worker results SHA-256 `9d618e9fb4c752104367d49b3de14e8b68bb5d8d9e7837851519978f33673cd5`.

The modifier schema is exposed, but observed clicks are ordinary; no nonempty modifier execution,
background edit, export or PASS is established. Root's stop decision followed navigation cycles35
and no-image evidence through33. In-flight36 selects a file and37 clicks Open; the final image-load
state awaits the literal-trace audit and is **not asserted to remain unloaded**. See the
[first120 report](archive/all-holo-order120-click-modifiers-retest-20260914.md).

**Order120 stays current/diagnosing** for an independent
[unfinished-claim feedback repair](archive/all-holo-order120-incomplete-claim-retest-20260914.md).
At24 a schema-valid claim admits work remains; semantic rejection correctly says so, but recovery
incorrectly chooses claim_only and says the task is already complete. Actual25/26 receive that full
conflict while retaining normal GUI tools, and both GUI actions execute. This is wrong guidance,
not a hard tool lockout. Root will prioritize the existing semantic task-state branch before
format-only claim recovery; acceptance criteria and contradiction patterns stay unchanged, with
no new gate or mode. Focused checks and a distinct seal precede any second120 episode.

Counts remain **31 isolated PASS, 36 skips, 99 Agent attempts, 67/94 processed and 26 other pending**.
No100 registration, skip or queue advance; original **95/189** and baseline pointer remain unchanged.

## 2026-09-14 03:53 UTC Order120 explicit click-modifier capability replay running

Agent attempt **99**, condition `holo31-all-roles-order120-click-modifiers-retest-20260914-v1`,
starts `2026-09-14T03:52:40.093842+00:00`, supervisor **2994** / session **56392**, worker **3068**
(started `03:52:48.342711 UTC`), selected `[120]`. Existing frozen validation is `ok`.
Source **534 files / 81,389,709 bytes**, frozen `03:51:28.146727 UTC`, SHA-256
`7acec88b9754f915a91b260935ee2755f500a04da648788a2824833c0f9b684d`;
config SHA-256 `5e4e5d935c591d4120cd945bc3305f32ce473dab54d246b5dc91970959e9c5d1`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

The existing click schema/preparation now supports explicitly model-selected ctrl/shift/alt/win
modifiers, and existing gateway/safe-result summaries preserve that list. Omitted modifiers keep the
ordinary click unchanged; no automatic mode or key rewriting occurs. **9 tools tests and17 delegation
tests pass**, covering selected and empty-list provenance, execution/next-parent feedback, and release
after a synthetic click exception. Generated commands compile with the exact pinned controller prefix;
Ruff/scoped diff pass. No new macro, gate, auditor or key-state framework. See the
[Order120 report](archive/all-holo-order120-click-modifiers-retest-20260914.md).

The original model did not select a dropped Shift modifier, and visible GIMP mode controls were
already an alternative. This adds a generic primitive; correct selection and JPEG export remain
model decisions. Only **Order120** is retesting/running. Counts: **31 isolated PASS, 36 skips,
99 Agent attempts, 67/94 processed and 26 other pending**. Outcome pending; no regression/control,
full rerun, promotion or original **95/189** change.

## 2026-09-14 03:46 UTC Order119 guidance delivered but no PNG; skip and next120

Attempt **98** finalizes `2026-09-14T03:44:25.867653+00:00`; worker completion was
`03:44:22.781653 UTC`. Worker **interrupted/null**, **28 events / 813.01 seconds**, zero completion
rejections. Supervisor **25563** / session **95047** exits **2** with the existing interrupted-worker
`invalid_configuration/null` wrapper; worker **25573** exits **0**. Both processes are gone and both
final source/config integrity checks are `ok`. This was root's bounded stop, not a fresh user stop,
environment failure, source drift or evaluator zero. Supervisor results SHA-256
`5fb53fa7345d0af5cd69e16e3cdd249b058cbdc11965e03172ab2dde15b9b9b1`;
worker results SHA-256 `68b8f6eeca6817e516a961bada6e24119325cece8bd52266f641f03c1ecf3584`.

New write guidance reaches Holo, but5 still appends **0%50%**. The UI later normalizes to **50%**
and the picture brightens, so this is not labeled a final brightness failure. The model chooses an
incorrect PPTX Save As8, submits an invalid export path21, then returns to scrolling despite inspect
ranking2 with its schema available22. It changes an unrelated background to white27 and scrolls28;
**no requested PNG or PASS** follows. See the [final119 report](archive/all-holo-order119-gui-write-guidance-retest-20260914.md).

**Order119 is skipped**. Next **queue68 / Order120** is **current/diagnosing**, with no episode
registered. The [bounded120 review](../experiments/work/all-holo-order120-repair-review-20260914.md)
distinguishes incorrect plain-click selection from a missing generic held-modifier click primitive.
Root plans optional explicitly model-selected click modifiers, preserving target/argument provenance
and ordinary clicks when omitted. The original did not select Shift, and visible GIMP mode controls
were an alternative; no executor-dropped modifier claim is made. This is not a task macro or gate.

Counts: **31 isolated PASS, 36 skips, 98 Agent attempts, 67/94 processed and 26 other pending**.
Original **95/189** and baseline pointer remain unchanged; no119 repeat, regression/control or full rerun.

## 2026-09-14 03:31 UTC Order119 GUI insertion/replacement guidance replay running

Agent attempt **98**, condition `holo31-all-roles-order119-gui-write-guidance-retest-20260914-v1`,
starts `2026-09-14T03:30:40.774922+00:00`, supervisor **25563** / session **95047**, worker **25573**
(started `03:30:48.896736 UTC`), selected `[119]`. Existing frozen validation is `ok`.
Source **534 files / 81,385,823 bytes**, frozen `03:29:34.919681 UTC`, SHA-256
`f449110414fb81bd7c9fee67a73000d5a015970afd6245ae3321005c0d0cdb4f`;
config SHA-256 `55c3810f3e4fdb5c837c7c436050c0ab19f99957a4639101829bedc15f378559`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

The original brightness field appended **0%20%** after a model-selected write with no selection.
Only the existing GUI write description changes: insert at the cursor, replace selected text only,
do not automatically clear, and focus/select on earlier separate turns. Native and delegated schemas
remain equal, valid arguments/prepared writes are unchanged, and the real mock grounding request
receives the explanation. Structural checks, Ruff and scoped diff pass; no new test file, suite,
auto-selection, clear flag, batch, API or gate. See the
[Order119 report](archive/all-holo-order119-gui-write-guidance-retest-20260914.md).

The malformed field's final numeric interpretation remains unknown. Whole-slide rather than picture
export is a separate confirmed failure that this wording does not fix by itself. Only original
evaluator PASS counts. **Order119** is retesting/running; counts **31 isolated PASS, 35 skips,
98 Agent attempts, 66/94 processed and 27 other pending**. No regression/control, full rerun,
promotion or original **95/189** change.

## 2026-09-14 03:26 UTC Order118 offline skip with no new episode; Order117 audit complete; next119

**Order118 is skipped without a new Agent attempt.** Its bounded
[current-source disposition](archive/all-holo-order118-disposition-20260914.md) confirms the same
Top6 terminal actions and relevant descriptions, plus complete background-versus-visible feedback
in actual requests4–6. No durable-history boundary occurs, the112 coexistence branch is uninvoked,
and source-output semantics are inactive. The original empty-terminal screenshot remains failed0;
no new shared defect or applicable repair warrants an unchanged behavioral replay. This does not
claim the model could never succeed. No screenshot gate, silent visible execution or macro is added.

The **Order117 attempt97 audit is complete**: 17 actual requests, with requests15–17 preserving exact
native DOCX/PDF members and the new correction guidance. Terminal review confirms completion and
the scorer's fetched ZIP members match the receipt. Correct input selection occurred before this
feedback, with no corrected-input overwrite needed, so wording alone is not established as the
cause of its measured PASS. See the [completed117 report](archive/all-holo-order117-archive-receipt-retest-20260914.md).

Actual next **queue67 / Order119** is **current/diagnosing**, with no episode registered. The
[preserved119 triage](../experiments/work/all-holo-order119-triage-20260912.md) confirms whole-slide
export where the requested output was an image; interpretation of the appended Brightness value is
uncertain. The model never searches for existing bitmap-export APIs. Current generic contracts will
be reviewed before selecting a repair/check, without an image-specific completion gate or combined macro.

Counts: **31 isolated PASS, 35 skips, 97 Agent attempts, 66/94 processed and 27 other pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control, full rerun or promotion.

## 2026-09-14 03:21 UTC Order117 original-evaluator PASS becomes31st recovery; next118

Attempt **97** finalizes `2026-09-14T03:19:57.425475+00:00` as **passed / reward1.0**,
**15 events / 534.623 seconds**, agent_done and zero completion rejections. Worker completion is
`03:19:50.655361 UTC`. Supervisor **48320** / session **39961** and worker **48376** both exit **0**
and are gone; both metadata states are completed and both final source/config integrity checks are `ok`.
Supervisor results SHA-256 `03a16287f3a96478ddb9c1a5d2713a5164b7faecb4160162e88c9aa3a80d9dde`;
worker results SHA-256 `966c4f0e24e0889d4c8d5434411fd1f972e4c2821a670ea3eb74efe3d11fc582`.

The model reads the full reminder4, opens the actual essay5, finds the actual PDF13, explicitly
selects the correct DOCX/PDF archive inputs14 and submits15. Correct input selection precedes the
changed archive receipt, so the measured task PASS is not solely attributable to new wording.
Actual guidance delivery still awaits the literal-trace audit; native success and offline projection
checks do not establish it. See the [Order117 report](archive/all-holo-order117-archive-receipt-retest-20260914.md).

Actual next **queue66 / Order118** is **current/diagnosing**, with no episode registered. Its
[preserved failed trajectory](../experiments/work/all-holo-order118-triage-20260912.md) saved an empty
terminal despite a successful background command. Visible/background guidance and terminal.show_output
were available, so this was action selection and completion composition, not swallowed feedback.
Root will inspect current accumulated contracts before deciding the smallest affected change/check;
historical helper coverage notes do not authorize a new completion gate or automatic visible command.

Counts: **31 isolated PASS, 34 skips, 97 Agent attempts, 65/94 processed and 28 other pending**.
Original **95/189** and baseline pointer remain unchanged; no117 repeat, regression/control or full rerun.

## 2026-09-14 03:11 UTC Order117 archive-success advice replay running

Agent attempt **97**, condition `holo31-all-roles-order117-archive-receipt-retest-20260914-v1`,
starts `2026-09-14T03:10:47.358908+00:00`, supervisor **48320** / session **39961**, worker **48376**
(started `03:10:55.298837 UTC`), selected `[117]`. Existing frozen validation is `ok`.
Source **534 files / 81,385,558 bytes**, frozen `03:09:32.241110 UTC`, SHA-256
`2031f810db161c3900722a927bf5b48d7919a32505ca7d55379d88fb5e4a98ab`;
config SHA-256 `16796442fffc9ee2162d1c4a60083a85d7049527638297599bed3cad1c4622e0`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

Only archive_context create guidance changes: verified integrity describes selected persisted members;
correct inputs still need comparison with the request, and explicit corrected inputs/overwrite can
replace an incorrectly assembled ZIP. Actual direct/forwarded projections preserve both synthetic
members, integrity and advice in **846/981 characters**, with original observations unchanged.
Ruff/scoped diff pass. Native archive code, schemas and arguments remain unchanged; no new test file,
suite, API, gate, automatic PDF export or required-member inference. See the
[Order117 report](archive/all-holo-order117-archive-receipt-retest-20260914.md).

The original wrong active document and two DOCX selections remain model errors. No correctly selected
replacement was blocked, so this advice's causal effect remains unproven until observed. Only
**Order117** is retesting/running. Counts: **30 isolated PASS, 34 skips, 97 Agent attempts,
64/94 processed and 29 other pending**. Outcome pending; no regression/control, full rerun, promotion
or original **95/189** change.

## 2026-09-14 03:07 UTC Order116 third bounded unscored stop and skip; next117 archive advice

Attempt **96** finalizes `2026-09-14T03:05:25.742430+00:00`; worker completion was
`03:05:21.290288 UTC`. Worker **interrupted/null**, **17 events / 551.561 seconds**, zero completion
rejections. Supervisor **17063** / session **40880** exits **2** with the existing interrupted-worker
`invalid_configuration/null` wrapper; worker **17090** exits **0**. Both processes are gone and both
final source/config integrity checks are `ok`. This is root's bounded stop, not a fresh user stop,
environment failure, source drift or evaluator zero. Supervisor results SHA-256
`008524c98aeda9ae5dc304ec2abc60e418d1dbdb476bf796628b7f4457aa6fc5`;
worker results SHA-256 `66bc1fdb246a5c54d899f3c5432ab2c0914c61be9f58b5c9fa81f543fb94723a`.

Root stops after cursor-click loop16. In-flight17 changes to workspace.find_files and returns
WORKSPACE_UNAVAILABLE because the focused application is gedit; it is a changed action, not another
unchanged click. No source edit, execution, capture or readback occurs. The two96 repair mechanisms
are therefore **unexercised live**; their 46+102 focused checks and actual95 offline surface/receipt
replays remain separate evidence. See the [final96 report](archive/all-holo-order116-readback-surface-retest-20260914.md).

**Order116 is skipped** after three distinct preserved attempts94–96 with no original-evaluator PASS.
The reference fix was observed live in95; no fourth unchanged repeat is scheduled. Next **queue65 /
Order117** is **current/diagnosing**, with no episode registered. Its
[prospective archive-advice repair](archive/all-holo-order117-archive-receipt-retest-20260914.md) narrows
an unconditional do-not-recreate/completion claim to actual archive integrity and members. The original
model selected the wrong active document and two DOCX inputs; native archiving preserved those inputs.
No correctly selected repair was blocked, so the proposed advice's causal benefit remains unproven.
The model still chooses corrected inputs and explicit overwrite; no automatic PDF or expected members.

Counts: **30 isolated PASS, 34 skips, 96 Agent attempts, 64/94 processed and 29 other pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control, new gate or full rerun.

## 2026-09-14 02:56 UTC Order116 required-reader and durable-receipt repair replay running

Agent attempt **96**, condition `holo31-all-roles-order116-readback-surface-retest-20260914-v1`,
starts `2026-09-14T02:56:00.670588+00:00`, supervisor **17063** / session **40880**, worker **17090**
(started `02:56:08.932474 UTC`), selected `[116]`. Existing frozen validation is `ok`.
Source **534 files / 81,385,347 bytes**, frozen `02:54:37.583483 UTC`, SHA-256
`e5e4d449a303ec0b16f291e2f07b245ebc7fa21cf7144bfecdb743d4adeda5b2`;
config SHA-256 `48fb6c454ab5a5668a39dac91dfbe02ecdb9f4e9fe8933e0a64a3de9964ed806`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

Existing recovery filtering now admits previously-discovered source capture/readback routes at their
declared phase across the Adapter boundary. Existing durable projection returns unused small-batch
reservation to ordinary receipts; total budgets and large-batch behavior remain unchanged. Validation:
**46 completion/source-output tests and 102 context tests pass**, with Ruff/scoped diff passing.
No new API, gate, framework, synthetic call/path or automatic content transfer.

Offline actual95 request31 replay retains complete edit23/command26 receipts and unchanged text22,
using **14,656/16,000 characters** in final recovery. Actual requests38–45 reconstructed through
LiteAgent.tools retain the two OS routes and add the discovered vs_code reader with its unchanged
request37 schema and valid original arguments. These checks establish repair behavior, not benchmark
PASS. See the [third116 report](archive/all-holo-order116-readback-surface-retest-20260914.md).

Only **Order116** is retesting/running. This third distinct condition follows the documented two-attempt
review checkpoint and new shared defects. Counts: **30 isolated PASS, 33 skips, 96 Agent attempts,
63/94 processed and 30 other pending**. Outcome pending; no regression/control, full rerun, promotion
or original **95/189** change.

## 2026-09-14 02:46 UTC Order116 reference fix works; newly exposed reader filter and receipt loss retained

Attempt **95** finalizes `2026-09-14T02:43:18.962150+00:00`: worker **interrupted/null**,
**51 events / 53 actual requests / 1271.027 seconds**, one completion rejection. Supervisor **8254** /
session **7805** exits **2** with the interrupted-worker `invalid_configuration/null` reportability
wrapper; worker **8289** exits **0**. Both processes are gone and both final source/config integrity
checks are `ok`. This is root's bounded stop, not a fresh user stop, environment failure, source drift
or evaluator zero. Supervisor results SHA-256
`aa20a3eb12cde6ef6725d6dfa20f4f8e3ff60afcb4990ee21de8577c9833193c`;
worker results SHA-256 `498ac8cbf8f9a830e125f88a780df3526f0d94aa65007d2d6f24e28a794187c1`.

Correct source edit23, execution26 and **35-byte output save34** reach completion36's **READ_OUTPUT**:
the reference-phase fix works in this live episode. The next required vs_code.file.read_text is,
however, excluded by the recovery filter's latest-owner restriction to OS. Requests38–45 expose only
OS find/profile Adapter actions despite asking for the reader; tools_search cannot bypass that filter.
Separately, request31 reserves 97.5% of its 16k durable budget for a 2778-character text batch, leaving
100-character ordinary receipts and erasing newer edit23/command26 details. Earlier requests27–30
contained complete stdout/save guidance, so this later loss does not explain the initial command loop.

Late events remain part of the outcome: soft restart44, fail_task46 with a success claim, stale editor
buffer restored50 and a newly misindented edit51. **No final source consistency, output readback or PASS**
is established. See the [final95 report](archive/all-holo-order116-reference-completion-retest-20260914.md).

**Order116 stays current/diagnosing**. The two-attempt checkpoint is extended for the newly demonstrated
shared defects in the [third hypothesis](archive/all-holo-order116-readback-surface-retest-20260914.md):
permit already-discovered workflow readers across the owner filter at their declared phase, and return
unused small-batch reservation to ordinary receipts. Root and child repair these existing branches;
total budgets, arguments, large-batch behavior and other completion checks remain unchanged. Focused
checks and a distinct source seal precede a third episode; **none is registered or launched here**.

Counts remain **30 isolated PASS, 33 skips, 95 Agent attempts, 63/94 processed and 30 other pending**.
No skip, queue advance, new gate, regression/control, promotion or original **95/189** change.

## 2026-09-14 02:23 UTC Order116 reference-completion repair replay running

Agent attempt **95**, condition `holo31-all-roles-order116-reference-completion-retest-20260914-v1`,
starts `2026-09-14T02:21:53.798596+00:00`, supervisor **8254** / session **7805**, worker **8289**
(started `02:22:02.240805 UTC`), selected `[116]`. Existing frozen validation is `ok`.
Source **534 files / 81,379,348 bytes**, frozen `02:20:52.087968 UTC`, SHA-256
`a3e4e485d1c3555cc93e2cec5c0716bec17dc012c69bdd5ddf167843cdd117cb`;
config SHA-256 `cd64e424c67ae4d4a7d984e352c9688dcf9ababb10f3f0830e2e2e9105077444`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

Reference-reading guidance now applies before a verified successful source edit; subsequent capture
and output-readback checks remain. The existing command-output module passes **22 tests**, Ruff and
scoped diff pass. Replaying all **44 actual94 events** preserves edit6 and capture26 at the model's
exact output path and yields **READ_OUTPUT**, with no readback step. The remaining feedback asks for
file.read_text of that saved path; no automatic DONE or synthetic event is inserted. Offline state
repair is not a scored recovery. See the [second116 report](archive/all-holo-order116-reference-completion-retest-20260914.md).

Only **Order116** is retesting/running. Counts: **30 isolated PASS, 33 skips, 95 Agent attempts,
63/94 processed and 30 other pending**. Outcome pending; original **95/189** and baseline pointer
remain unchanged. No new gate/framework, regression/control or full rerun.

## 2026-09-14 02:20 UTC Order116 source execution improves; distinct reference-completion repair retained

Attempt **94** finalizes `2026-09-14T02:17:54.732164+00:00`: worker **interrupted/null**,
**44 events / 1296.792 seconds**, nine completion rejections. Supervisor **21695** / session **30045**
exits **2** with the interrupted-worker `invalid_configuration/null` reportability wrapper; worker
**21771** exits **0**. Both processes are gone and both final source/config integrity checks are `ok`.
This is root's bounded stop to repair a demonstrated issue, not an environment failure, source drift,
fresh user stop or evaluator zero. Supervisor results SHA-256
`fbf10f97fe9a5b33eef257640ada524c4c0ea5dfccfac4ff7d3d35419972cdfd`;
worker results SHA-256 `9c1e20912482d29f7d809097f80dbfd98b914054d57da23b33a1ed3ffd5bb306`.

There is real progress: source edit6 uses correct explicit indentation, execution11 succeeds, and26
saves the requested **35-byte output**. However, repeated done calls remain blocked by a requirement
to read the original supporting DOCX basename through one API after the source edit already succeeded.
Converted tutorial TXT reads37/43 deliver only **2000/3425 characters**, and **res.txt remains unread**.
Successful source execution is not a scored PASS. See the
[first116 report](archive/all-holo-order116-disk-edit-guidance-retest-20260914.md).

**Order116 stays current/diagnosing** for the distinct
[reference-completion repair](archive/all-holo-order116-reference-completion-retest-20260914.md).
After both processes exit, root limits the existing reference guidance to before a verified successful
source edit. Capture and output-readback obligations still apply; the preserved state should advance
to READ_OUTPUT, never directly DONE. **22 focused command/output tests**, Ruff and scoped diff pass.
This adds no gate or framework, does not infer reference content and does not run or alter model actions.
Attempt95 requires its own source seal and has **not been registered or launched** in this entry.

Counts remain **30 isolated PASS, 33 skips, 94 Agent attempts, 63/94 processed and 30 other pending**.
No skip or queue advance; original **95/189** and baseline pointer remain unchanged. No regression/control.

## 2026-09-14 01:58 UTC Order116 existing disk/buffer/indentation guidance replay running

Agent attempt **94**, condition `holo31-all-roles-order116-disk-edit-guidance-retest-20260914-v1`,
starts `2026-09-14T01:56:04.593171+00:00`, supervisor **21695** / session **30045**, worker **21771**
(started `01:56:12.899719 UTC`), selected `[116]`. Existing frozen validation is `ok`.
Source **534 files / 81,378,145 bytes**, frozen `01:54:18.001375 UTC`, SHA-256
`83cfa903f903f26f2652ebe1439d243da0f205d37a23e20b122ec3d2f3b097ae`;
final config SHA-256 `d76b7fcfd96779a779336dee85def2b49757ecb5500b44a25cab9e4b136cdd8e`.
Both paired direct Holo2 roles retain thinking/T0.8/top_k7, 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

This checks existing Order94 disk-versus-editor-buffer, exact substring and per-line indentation
explanations plus accumulated command-output guidance; **no new116 runtime fix** is claimed. The
post93 extract/text aliases are separately checked metadata carried into this seal, with no third114
episode or claimed116 mechanism. No new gate, API, automatic buffer sync or indentation correction.
No extra local test campaign is needed for already-tested wording. See the
[Order116 report](archive/all-holo-order116-disk-edit-guidance-retest-20260914.md).

Only **Order116** is retesting/running. Counts: **30 isolated PASS, 33 skips, 94 Agent attempts,
63/94 processed and 30 other pending**. Outcome pending; original **95/189** and baseline pointer
remain unchanged. No regression/control or full rerun.

## 2026-09-14 01:53 UTC Order114 bounded unscored skip; next116 verifies existing edit guidance

Attempt **93** finalizes `2026-09-14T01:49:02.213990+00:00`: worker **interrupted/null**,
**25 events / 744.343 seconds**, zero completion rejections. Supervisor **45442** / session **23283**
exits **2** with its `invalid_configuration/null` wrapper because the interrupted worker is not
completed/reportable; worker **45481** exits **0**. Both processes are gone and both final source/config
integrity checks are `ok`. This was root's predeclared sustained-loop stop, not a fresh user stop,
environment failure, source drift or evaluator reward zero.

Supervisor results SHA-256 `cd99a4a9706c051e4939257002b8f6ee297ae852c7d13a7656c22155fa1fe3f7`;
worker results SHA-256 `48cdfc336bba457c2e9f0b90562dd6d69f5f80dcd86ea7f917bd3163fcc36238`.
The model never calls presentation.inspect, so the projection repair is not exercised live.
Formatting feedback21 does deliver **four short text values**; some body text was visible through
another path. Successful Outline/menu actions and the already-in-flight Export25 still produce
no source-text copy, Writer body write, native output save or completed artifact. Repeated-action
feedback reaches request20; event24 exposes an invalid GUI coordinate-type error. See the
[final114 report](archive/all-holo-order114-presentation-context-retest-20260914.md).

**Order114 is skipped** after its two preserved attempts. The repair retains focused/offline replay
evidence but has no live task-level improvement or recovered PASS. After both processes exit, root
adds generic extract/text aliases to the existing presentation.inspect keyword map for the next seal;
these were absent from93 and receive no third114 episode. No new API, framework, gate or text transfer.

Next **queue64 / Order116** is **current/diagnosing**, with no episode registered. Its
[affected-check report](archive/all-holo-order116-disk-edit-guidance-retest-20260914.md) tests existing
Order94 disk/buffer/indentation wording plus command-output guidance. The original six disk reads and
command error were delivered; stale-buffer choices and literal indentation were model errors.
No new116 runtime fix is claimed. Freeze and one affected launch remain root's next steps.

Counts: **30 isolated PASS, 33 skips, 93 Agent attempts, 63/94 processed and 30 other pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 01:37 UTC Order114 bounded presentation-body context repair replay running

Agent attempt **93**, condition `holo31-all-roles-order114-presentation-context-retest-20260914-v1`,
starts `2026-09-14T01:36:22.015053+00:00`, supervisor **45442** / session **23283**, worker **45481**
(started `01:36:30.119311 UTC`), selected `[114]`. Existing frozen validation is `ok`.
Source **534 files / 81,378,071 bytes**, frozen `01:34:46.238203 UTC`, SHA-256
`e0b64fdc2b114c5d19b20e79733db43c0b16ed6cc81de7496daae09ec9adbeb6`;
config SHA-256 `d274fb4ecb04db1cdaa01d47b0614ba5061342303293f8b07d73d63c65e3e364`.
Both direct Holo2 roles retain thinking/T0.8/top_k7; limits remain 100 global / 50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through both exits.

The existing selector-preserving presentation helper now runs before destructive shape deletion,
retains complete reading guidance and reports omitted slides/shapes. The runtime budget remains
12,000 nested characters plus 1,000 envelope; no new API, framework, gate or automatic text transfer.
The existing context module passes **101 tests**, with Ruff/scoped diff passing. An old incidental
under-10,000 assertion was aligned to the existing nested/envelope contract after the first run's
100 passes and one failure; runtime budgets were not raised.

Offline replay of preserved attempt92 events 1–5 now retains **6 slides, 6 text shapes, 11 exact lines**,
complete IDs and **22 omitted slides**; nested context is 11,803 characters, wrapper 11,973, guidance
1,036. Retained text and targets match native evidence; raw events are unchanged. This verifies the
projection repair but is not Agent PASS. The separate extraction-alias suggestion was not implemented
and authorizes no third episode. See the [Order114 report](archive/all-holo-order114-presentation-context-retest-20260914.md).

Only **Order114** is retesting/running. Counts: **30 isolated PASS, 32 skips, 93 Agent attempts,
62/94 processed and 31 pending**. Live task outcome is pending. Original **95/189** and baseline
pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 01:33 UTC Order114 first replay ends deadline; confirmed presentation-text loss retained

Attempt **92** finalizes `2026-09-14T01:30:58.086217+00:00` as **agent_deadline_exhausted/null**,
**1932.407 total seconds**,54recorded events; result`steps`remainsnull and no evaluator runs.
Supervisor **34425** / session **62252** and worker **34478** both exit **0** and are gone;
both final source/config integrity records are `ok`. Results SHA-256
`8531a139d790c63595e92bdfb9930a9ba7318bdc45b6a81eb16b3ff619ba25d9`.
See the [first Order114 report](archive/all-holo-order114-text-file-contract-retest-20260914.md).

The changedfile.create description is never exposed/called,so no behavior effect is established.
A separate body-context defect is confirmed: native inspection5returns28slides/41textshapes,
the owning projection removes all shapes yet still exceeds its12000character budget,and the actual
nextrequest receives0textshapes. Final12slide context also retains a stale zero omitted-slide count.
Synthetic offline reproduction confirms the same loss without changing source evidence.

**Order114 remains current/diagnosing** for the
[prospective presentation-context repair](archive/all-holo-order114-presentation-context-retest-20260914.md).
Root will reuse the existing bounded selector-preserving helper,keeping the budget,exact retained
text/targets and speaker-note guidance,with truthful omissions. No automatic text transfer,newAPI,
framework or gate. **Attempt93 has not been registered or launched**; this is a distinct evidenced
second hypothesis,not an unchanged replay.

Counts remain **30 isolated PASS,32 skips,92 Agent attempts,62/94 processed and31 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 01:00 UTC Order114 UTF8 text versus native-document usage replay running

Agent attempt **92**, condition `holo31-all-roles-order114-text-file-contract-retest-20260914-v1`,
starts `2026-09-14T00:58:32.866960+00:00`, supervisor **34425** / session **62252**, worker **34478**
(started `00:58:40.984991 UTC`), selected `[114]`. Existing frozen validation is `ok`.
Source **534 files /81,375,929 bytes**, frozen `00:57:09.887314 UTC`, SHA-256
`ee9ad5a341c24191dfe806d1675b6e4abd8932fda2a0e119d0b5f11c2e32c34d`;
config SHA-256 `d581600bb0515fb720d2780a73d1ed44f58f7cd0c36d309aef6961acb49b3f2e`.
Both roles retain direct138Holo2,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

Only existingfile.create descriptions clarify UTF8text,emptycontent and extension/native-format
distinctions. Direct/forwarded structural checks preserve all accepted parameters/defaults,including
blankDOCX-suffixed text; Ruff/scoped diff pass. No new API,test campaign,blacklist or gate.
Content extraction,owning-app creation and save remain model responsibilities. See the
[Order114 report](archive/all-holo-order114-text-file-contract-retest-20260914.md).

Only **Order114** is retesting/running. Counts: **30 isolated PASS,32 skips,92 Agent attempts,
62/94 processed and31 pending**. Outcome pending; original **95/189** and baseline pointer remain
unchanged. No regression/control or full rerun.

## 2026-09-14 00:55 UTC Order112 original-evaluator PASS becomes30th recovery; next114

Attempt **91** finalizes `2026-09-14T00:52:23.028812+00:00` as **PASS/1.0**, **16 events /
571.023 seconds**, `agent_done`,zero completion rejections. Supervisor **1004** / session **34083**
and worker **1098** both exit **0** and are gone; both final source/config integrity records are `ok`.
Results SHA-256 `79c0e5e61b4ec756f7518a8bb19c5913e08aa8dcba59b0abea52a754250d11c4`.
See the [Order112 report](archive/all-holo-order112-terminal-coexistence-retest-20260914.md).

The model launches its own correctbash/sarredirect command11,reads the selectedabsoluteoutputpath15
and receives complete30samples plusAverage,then submits16. **No terminal.show_output occurs**.
This is a measured taskPASS; the implicit-shutdown fix is not exercised live and has no standalone
causal claim. Its34focused checks remain separate evidence; no112repeat is needed.

Actual next **queue63 / Order114**,multi-app task `bb83cab4-e5c7-42c7-a67b-e46068032b86`,is
**current/diagnosing**,with no episode registered. Its
[preserved review](../experiments/work/all-holo-order114-repair-review-20260913.md) identifies unclear
UTF8text/native-document wording in existingfile.create. The original emptyDOCX-named textfile and
later visible errors do not establish lost nativeWritercontent. A description-only clarification
retains empty-text creation and accepted parameters; no formatblacklist,macro or gate is proposed.

Counts: **30 isolated PASS,32 skips,91 Agent attempts,62/94 processed and31 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 00:44 UTC Order112 existing producer-terminal coexistence replay running

Agent attempt **91**, condition `holo31-all-roles-order112-terminal-coexistence-retest-20260914-v1`,
starts `2026-09-14T00:42:37.961563+00:00`, supervisor **1004** / session **34083**, worker **1098**
(started `00:42:45.673449 UTC`), selected `[112]`. Existing frozen validation is `ok`.
Source **534 files /81,375,552 bytes**, frozen `00:41:00.422563 UTC`, SHA-256
`64a8113127e17bc93d709101cd3b3ba931bdbdc130d4747c55b128730d75eb68`;
config SHA-256 `9d0614720a930eaec327ddcdac67cc15ea793f6e01ad62ccb4f22a1b80a7cc43`.
Both roles retain direct138Holo2,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

Only the implicit shutdown before ordinary visible-terminal output is removed. Existing producer
windows coexist with the new observer's unique title; explicit teardown,exact-title focus/readback,
deadline and model-selected command remain unchanged. **34 focused checks pass**,plus Ruff/diff.
Separate accumulated post109reader/clipboard wording passes structural checks; no109repeat.
See the [Order112 report](archive/all-holo-order112-terminal-coexistence-retest-20260914.md).

Only **Order112** is retesting/running. Counts: **29 isolated PASS,32 skips,91 Agent attempts,
61/94 processed and32 pending**. Outcome pending; original **95/189** and baseline pointer remain
unchanged. No new wait,process registry,completion gate,regression/control or full rerun.

## 2026-09-14 00:39 UTC Order109 bounded unscored skip; next112 terminal side-effect repair

Attempt **90** finalizes `2026-09-14T00:36:22.123197+00:00`. Worker **13990** is **interrupted/null**,
**39 events /1166.139 seconds**,exit **0**,after registered rootSIGINT around00:36:08UTC.
Supervisor **13895** / session **40188** exits **2**,recording **invalid_configuration** because
interrupted worker metadata/task status is not completed/reportable. Both PIDs are gone; both final
source/config integrity records are **ok**. Preserve these labels separately; no scored0,source drift
or new environment failure. No evaluator runs. Supervisor results SHA-256
`eaebe854878f4b6a0d1e41185d3c19263f5d973d7a3f678922b8410b16f817a7`;
worker results SHA-256 `75709571f639a8b0b62f7df7fecaa10e7845da0f780689fadd309fa76cf9d916`.

The model selects the ordinary reader but no JSONparsequery/command.run. Writer24returns0characters
afterCtrl+Vwithout a preceding copy. Reads25–31start0,32requests50k,and33–36returnto12744;
**38/39advance again before stop**. Persistent prefix reading prevents delivery,but not every late
read is identical. **Skip109** after two distinct attempts,retaining89deadline/null separately and
avoiding a third unchanged replay. See the [second Order109 report](archive/all-holo-order109-json-discovery-retest-20260914.md).

Actual next **queue62 / Order112**,multi-app task `2373b66a-092d-44cb-bfd7-82e86e7a3b4d`,is
**current/diagnosing**,with no episode registered. Its
[preserved review](../experiments/work/all-holo-order112-repair-review-20260913.md) confirms ordinary
visible-command execution still implicitly closes other Adapter terminal windows,including an
existing producer. Removing that side effect is the bounded candidate; keep explicit teardown and
exact model commands. The original submission occurred85seconds after launch,so do not mislabel it
as before the requested30seconds. No new wait,semantic replacement or completion gate is proposed.

Counts: **29 isolated PASS,32 skips,90 Agent attempts,61/94 processed and32 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 00:18 UTC Order109 second affected JSON-discovery replay running

Agent attempt **90**, condition `holo31-all-roles-order109-json-discovery-retest-20260914-v1`,
starts `2026-09-14T00:16:41.997302+00:00`, supervisor **13895** / session **40188**, worker **13990**
(started `00:16:50.162986 UTC`), selected `[109]`. Existing frozen validation is `ok`.
Source **534 files /81,374,952 bytes**, frozen `00:15:14.339995 UTC`, SHA-256
`dd57a71327e604420a537a1c7d7258bb964ae0a8b5982d9dd4c1db61aabb1f14`;
config SHA-256 `a7af50f65d56b37a150477fa2c759dc8a73733d998dc27bcdc3cb51b23799e70`.
Both roles retain direct138Holo2,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

Only four generic discovery aliases change after89: command.run`json/parse/parsing`and reader`json`.
Actual and synthetic structural search checks pass; PDFtable discovery retains its prior routes.
Ruff/scoped diff pass. Tool schemas,command semantics and completion remain unchanged; the model
still authors every program/argument. No parser API,command template,automatic parsing or gate.
See the [second Order109 report](archive/all-holo-order109-json-discovery-retest-20260914.md).

Only **Order109** is retesting/running. Preserve89deadline/null separately; outcome90is pending.
Counts: **29 isolated PASS,31 skips,90 Agent attempts,60/94 processed and33 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-14 00:15 UTC Order109 first replay ends deadline; distinct JSON-discovery hypothesis retained

Attempt **89** finalizes `2026-09-14T00:13:05.833965+00:00` as **agent_deadline_exhausted/null**,
**1935.095 total seconds** with64recorded events; result`steps`remainsnull and no evaluator runs.
Supervisor **6656** / session **3901** and worker **6731** both exit **0** and are gone; both final
source/config integrity records are `ok`. Results SHA-256
`e053d73ecf8e7d0e3e7b37cb1adc11e264af66ff7e465d4b4d26ed9a238917ff`.
See the [Order109 continuation report](archive/all-holo-order109-reader-continuation-retest-20260913.md).

Order109 stays **current/diagnosing**,without a skip or next launch. Its separate
[JSON-discovery review](../experiments/work/all-holo-order109-json-discovery-review-20260913.md)
shows an actual parse query omits the generic command executor and a JSON-file query ranks the
ordinary reader second. In-memory additions of ordinary`json/parse/parsing`command aliases and
`json`reader alias move those tools to rank1. Synthetic queries also improve,with PDF-table discovery
unchanged. Root selects this distinct small second hypothesis after the first attempt's terminal result.

No dedicated JSON API,command template,automatic parsing,semantic value or gate is proposed.
Correct continuation guidance was delivered in89; retrieval improvement alone would not prove
output creation or PASS. No second episode is registered yet; a new seal follows metadata checks.
Counts remain **29 isolated PASS,31 skips,89 Agent attempts,60/94 processed and33 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 23:42 UTC Order109 truthful reader flags and Writer continuation replay running

Agent attempt **89**, condition `holo31-all-roles-order109-reader-continuation-retest-20260913-v1`,
starts `2026-09-13T23:40:35.614891+00:00`, supervisor **6656** / session **3901**, worker **6731**
(started `23:40:43.685384 UTC`), selected `[109]`. Existing frozen validation is `ok`.
Source **534 files /81,374,884 bytes**, frozen `23:39:17.450903 UTC`, SHA-256
`13318eccb3c2cc82abe707a03cd1cc8a9f656a1e3b6cab149d4a09c9ae825d3d`;
config SHA-256 `f51e697f5202ef1fd433fbe0851368ac652751654ce096a48525f33cada05cd0`.
Both roles retain Holo2direct138,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

Existing file/batch flags now reflect final-fit context loss,with Writer identity and real
`path/start_char/max_chars` continuation guidance retained. Source EOF/native cursors,absolute offsets,
raw results and total budget remain unchanged; no automatic read or argument injection.
**Context99,Writer19 and accumulatedCalc overwrite4 checks pass**,plus Ruff/scoped diff.
The source seal includes the post108overwrite repair,with no second108episode. See the
[Order109 report](archive/all-holo-order109-reader-continuation-retest-20260913.md).

Only **Order109** is retesting/running. Counts: **29 isolated PASS,31 skips,89 Agent attempts,
60/94 processed and33 pending**. Useful extraction/output creation remains unproven; original
**95/189** and baseline pointer remain unchanged. No new gate,regression/control or full rerun.

## 2026-09-13 23:38 UTC Order108 wrong counts and unsaved data remain; next109

Attempt **88** finalizes `2026-09-13T23:30:11.502308+00:00` as **failed/0.0**, **48 events /
1787.837 seconds**, `agent_done`; done48and terminalaudit49 confirm. Supervisor **58165** / session
**29594** and worker **58247** both exit **0** and are gone; both final source/config integrity records
are `ok`. Results SHA-256 `39e391eaf939b2df4e30f3b397693bc83f820d8378d12d9d82a7682ff08f1721`.
See the [Order108 report](archive/all-holo-order108-boundary-feedback-retest-20260913.md) and
[final boundary/artifact audit](../experiments/work/all-holo-order108-attempt88-final-audit-20260913.md).

All10model-selected counts and5rates are wrong. Step25saves four headers; native overwrite attempts
26/28fail. Accepted cell edits33/38are never saved later: the evaluator-preserved workbook ZIP contains
onlyA1:D1. Its fixed`Sheet1.csv`getter also returns404,but the actual conversion filename was not
retained; that evaluator limitation is separate from wrong source values and the proven header-only
artifact. The model receives target source rows in later requests and still uses incorrect counts.

Explicit oversized-timeout clipping is **not exercised**. Schema-only correction is delivered and
consumed once for same-intent retries; this does **not** establish the widened changed-intent behavior
live. Local11timeout/47Holo checks remain the boundary-fix evidence. Root fixes the separate Calc
overwrite contract after both processes exit; that later repair is outside88and does not justify a
second108episode. **Skip108**,with no scorer workaround,new completion gate or unchanged replay.

Actual next **queue61 / Order109**,multi-app task `5bc63fb9-276a-4439-a7c1-9dc76401737f`,is
**current/diagnosing**,with no episode registered. Counts: **29 isolated PASS,31 skips,88 Agent
attempts,60/94 processed and33 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or full rerun.

## 2026-09-13 23:02 UTC Order108 owning timeout and schema-feedback replay running

Agent attempt **88**, condition `holo31-all-roles-order108-boundary-feedback-retest-20260913-v1`,
starts `2026-09-13T23:00:11.301282+00:00`, supervisor **58165** / session **29594**, worker **58247**
(started `23:00:19.342657 UTC`), selected `[108]`. Existing frozen validation is `ok`.
Source **533 files /81,364,250 bytes**, frozen `22:58:59.431125 UTC`, SHA-256
`2bc06dac2734a09706caee55ea1c3003ba4c8a80ab20f1073e8618d483116bc9`;
config SHA-256 `1a846cda354d9b644f45eff37f7a484eddf3ed833c39edc8ca291b134c2d2742`.
Both roles retain Holo2direct138,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

The existing timeout minimum includes the owning cap. Sanitized schema-only grounding correction
is retained for one next request under the same public tools contract, preserving the current intent
and screenshot and carrying no prior target or semantic value. **11 timeout and47Holo tests pass**;
Ruff/scoped diff pass. No new API,retry loop,gate or semantic argument injection. See the
[Order108 report](archive/all-holo-order108-boundary-feedback-retest-20260913.md).

Only **Order108** is retesting/running. Counts: **29 isolated PASS,30 skips,88 Agent attempts,
59/94 processed and34 pending**. Outcome pending; original **95/189** and baseline pointer remain
unchanged. No regression/control or full rerun.

## 2026-09-13 23:00 UTC Order107 deadline with no writes; next108 boundary repair prepared

Attempt **87** finalizes `2026-09-13T22:53:38.628508+00:00` as **agent_deadline_exhausted/null**,
**1932.388 total seconds**,43recorded events; result`steps`remainsnull. No evaluator runs.
Supervisor **47059** / session **78033** and worker **47097** both exit **0** and are gone;
both final source/config integrity records are `ok`. Results SHA-256
`92d85633936d6a56544b3ad9d106065996fdddf83deb5a8251ffa7d164884768`.
See the [final Order107 report](archive/all-holo-order107-direct-transport-retest-20260913.md).

No values are written or saved; read42shows all72targetcells empty. Actual-request audits confirm
complete latest table matrices/merges in most immediate feedback,with one explicitly marked temporary
truncation later restored. The model confuses counts/funding and repeats PDF binary-warning detours.
Steps40/43each recover one4096-token no-call response. A217-secondHTTP200response completes through
direct138; final44times out near the remaining Agent deadline. Its32.75-second observed interval is
not an exact SDK timeout measurement; no new524or separate transport failure is established.
**Skip107** without a wording-only replay or new table-reading gate.

Actual next **queue60 / Order108**,multi-app task `7e287123-70ca-47b9-8521-47db09b69b14`,is
**current/preparing**,with no episode registered. Its
[boundary repair report](archive/all-holo-order108-boundary-feedback-retest-20260913.md) records
owner-cap inclusion in the existing timeout minimum and schema-only error feedback retained for the
next grounding request under the same public tool contract. Old semantic values/targets are never
carried forward; changed contracts clear feedback. **11 timeout and47Holo tests pass**,plus Ruff/diff,
with no new API,retry loop or gate. Root will freeze before the next launch.

Counts: **29 isolated PASS,30 skips,87 Agent attempts,59/94 processed and34 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 22:23 UTC Order107 existing direct-route replay running after original524

Agent attempt **87**, condition `holo31-all-roles-order107-direct-transport-retest-20260913-v1`,
starts `2026-09-13T22:21:13.409652+00:00`, supervisor **47059** / session **78033**, worker **47097**
(started `22:21:21.490162 UTC`), selected `[107]`. Existing frozen validation is `ok`.
Source **533 files /81,361,545 bytes**, frozen `22:20:16.428637 UTC`, SHA-256
`6462348f5e2923b25653c5faa5129f57a350c8d52241d1b54a40d266fde612c6`;
config SHA-256 `f4409c3a4c2b9309be9ceac040ff0a8a424cf9b276bc1be58342f7826ff5d28a`.
Both roles retain Holo2direct138,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

This uses the existing direct route past original Cloudflare524without a transport patch or retry
change. The seal carries post86key/hotkey description examples and separate repeated presses;
structural checks preserve accepted arguments/toolset,with no enum,validator or gate change.
Ruff/scoped diff pass. Complete original table feedback and incorrect denominator selection remain
separate from transport. See the [Order107 report](archive/all-holo-order107-direct-transport-retest-20260913.md).

Only **Order107** is retesting/running. Counts: **29 isolated PASS,29 skips,87 Agent attempts,
58/94 processed and35 pending**. Original **95/189** and baseline pointer remain unchanged;
outcome pending,no regression/control or full rerun.

## 2026-09-13 22:21 UTC Order106 reads and launches but never edits successfully; next107

Attempt **86** finalizes `2026-09-13T22:17:34.354275+00:00` as **failed/0.0**, **27 steps /
780.561 seconds**, `agent_done`,zero completion rejections. Supervisor **12394** / session **29865**
and worker **12405** both exit **0** and are gone; both final source/config integrity records are `ok`.
Results SHA-256 `efe70847aa4f1437b631090dabdd159966890590fb1a75737b23cfca2d92e559`.
See the [final Order106 report](archive/all-holo-order106-reader-discovery-retest-20260913.md).

Full source reads5/6/16precede edits; the model launches9,installs pygame10and relaunches12.
Original plural queries are not replayed,so earlier reading does not establish alias-only causality.
The sole edit26uses nonexistent `**` in its literal oldtext. `TEXT_NOT_FOUND`,the unchanged-file
statement and exact-match guidance reach requests27/28completely. The model still submits and confirms
completion; **zero code changes succeed**,and the original evaluator returns0. **Skip106** with
delivered-error evidence; no new completion gate or unchanged replay.

After both processes exit,root clarifies only existing Holo key/hotkey descriptions using supported
key examples and separate repeated presses. This later wording was not in86and adds no validator,
enum,argument rewrite or gate; it supplies no106PASS claim or justification for another106episode.

Actual next **queue59 / Order107**,multi-app task `881deb30-9549-4583-a841-8270c65f2a17`,is
**current/diagnosing**,with no episode registered. The
[transport report](archive/all-holo-order107-direct-transport-retest-20260913.md) records original
Cloudflare524after12events,three identical final requests and complete table feedback. Existing
direct138can bypass that proxy; correct denominator selection remains independently unproven.

Counts: **29 isolated PASS,29 skips,86 Agent attempts,58/94 processed and35 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 22:06 UTC Order106 ordinary reader-alias replay running

Agent attempt **86**, condition `holo31-all-roles-order106-reader-discovery-retest-20260913-v1`,
starts `2026-09-13T22:04:19.265616+00:00`, supervisor **12394** / session **29865**, worker **12405**
(started `22:04:27.333338 UTC`), selected `[106]`. Existing frozen validation is `ok`.
Source **533 files /81,361,100 bytes**, frozen `22:03:37.742175 UTC`, SHA-256
`487936299dedf3e084eaaedf6c6ec8b0af57adb99ff63d155130cf6a8dffdaa3`;
config SHA-256 `5ee920ae0e7fc173c3258144afcf60139ea521daeea56da72d1e384e11e24b31`.
Both roles retain Holo2direct138,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

Only ordinary **files /contents** aliases were added to the existing `file.read_text` metadata.
Pure local search moves the reader from outsideTop7to1for both original queries and one synthetic
project-folder query; another generic query improves2to1. Schemas and semantic arguments are
unchanged. Ruff/scoped diff pass; no new test file,test campaign,API,guard or mandatory-read gate.
See the [Order106 report](archive/all-holo-order106-reader-discovery-retest-20260913.md).

Only **Order106** is retesting/running. Earlier reader discovery is the observable target;
source-debugging/body-replacement mistakes may remain,and search ranks do not establishPASS.
Counts: **29 isolated PASS,28 skips,86 Agent attempts,57/94 processed and36 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 22:02 UTC Order104 original-evaluator PASS becomes29th recovery; next106

Attempt **85** finalizes `2026-09-13T21:59:28.399566+00:00` as **PASS/1.0**, **46 steps /
1651.830 seconds**, `agent_done`,zero completion rejections. Supervisor **14307** / session **10973**
and worker **14366** both exit **0** and are gone; both final source/config integrity records are `ok`.
Results SHA-256 `570eae1783eca8e43cc2ca9d416a6824bdb3f4889e13f1b84ede33cf0d289f37`.
No deadline,protocol/transport or terminal environment failure. Initial deployment apt-lock recovery
used the existing retry. See the [final Order104 report](archive/all-holo-order104-writer-listener-retest-20260913.md).

Writer reads succeed,but **no passive-prepare lifecycle record is observed**; actions use the
already-ready path. The listener repair remains supported by focused tests and original evidence;
do not attribute this PASS specifically to that branch. The model recovers scroll and active-document
mistakes:40opens the answer document,42/43replace and persist its selected strings,44readsback,
45explicitly saves byGUI and46submits. Original evaluator confirmsPASS. Read-only scroll/document
reviews establish no further runtime defect requiring another104attempt or new gate.

Actual next **queue58 / Order106**,multi-app task `9219480b-3aed-47fc-8bac-d2cffc5849f7`,is
**current/diagnosing**,with no episode registered. Its
[current-source triage](../experiments/work/all-holo-order106-triage-20260913.md) preserves early
editing without reading,repeated function-body accumulation and no program execution despite complete
earlier feedback. Ordinary plural aliases for the existing reader are a small discovery candidate;
they do not solve the demonstrated debugging/scope failures by themselves or justify a read gate.

Counts: **29 isolated PASS,28 skips,85 Agent attempts,57/94 processed and36 pending**.
Original **95/189** and baseline pointer remain unchanged. No104regression/control or repeat.

## 2026-09-13 21:33 UTC Order104 existing Writer listener recovery replay running

Agent attempt **85**, condition `holo31-all-roles-order104-writer-listener-retest-20260913-v1`,
starts `2026-09-13T21:31:43.203068+00:00`, supervisor **14307** / session **10973**, worker **14366**
(started `21:31:51.315214 UTC`), selected `[104]`. Existing frozen validation is `ok`.
Source **533 files /81,361,063 bytes**, frozen `21:31:01.526979 UTC`, SHA-256
`031aa0cd9ada4d2ebffbc013267fdc2eea5969932bc7b6a452447d89d433360b`;
config SHA-256 `aecd8aa2572924d64c8b1be672f058419d33edba8044034c84cacd077e582a87`.
Both roles use **Holo2direct138**,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Read-onlymodels confirms the expected Holo3.1-4B snapshot;
no extra model episode. Source/tests stay frozen through both exits.

Owning Writer service reuses existing passive preparation under the action lock and original deadline,
deducting lock/preparation time from the worker budget. It preserves requestID/action/document/params/
verify and dispatches once after preparation succeeds; native failure/deadline exhaustion never
dispatches. Ready requests avoid preparation. Existing lifecycle implementation remains unchanged,
with no restart,document selection,new API,gate or retry framework.

**24 checks pass** across five focused service cases and existing Writer file-read coverage;
Ruff/scoped diff pass. See the [Order104 report](archive/all-holo-order104-writer-listener-retest-20260913.md).
Only **Order104** is retesting/running. Counts: **28 isolated PASS,28 skips,85 Agent attempts,
56/94 processed and37 pending**. Outcome pending; original **95/189** and baseline pointer stay
unchanged. No regression/control or full rerun.

## 2026-09-13 21:27 UTC Order103 observed-workbook repair recovers28th isolated PASS; next104

Attempt **84** finalizes `2026-09-13T21:24:48.562056+00:00` as original-evaluator **PASS/1.0**,
**11 steps /437.038 seconds**, `agent_done`,zero completion rejections. Supervisor **50057** / session
**13887** and worker **50064** both exit **0** and are gone. Both final source/config integrity records
are `ok`. Results SHA-256 `b5d35dc49441c611a44a0d3133aeebc3997d68aa229cce9005194073ab6d2ca4`.
See the [final Order103 report](archive/all-holo-order103-observed-workbook-retest-20260913.md).

Verified native inspection6now unlocks GUI7cell selection,GUI8model-selected typing andGUI9Enter.
The former false observation block is exercised and removed in this actual run. Model inspection10,
done11and terminal audit follow. **The Agent does not independently save**; native modified remains
true. The **unchanged pinned evaluator's existing postconfig activates the workbook and pressesCtrl+S**
before its three comparisons pass. Record the original scoring procedure explicitly; no new Runner
save or semantic argument injection occurred.

Actual next **queue57 / Order104**,multi-app task `1f18aa87-af6f-41ef-9853-cdb8f32ebdea`,is
**current/diagnosing**,with no episode registered. Its
[preserved follow-up review](../experiments/work/all-holo-order104-disposition-review-20260913.md)
finds ten Writer attempts rejected for a missing listener,with complete native errors already visible.
Reusing existing passive Writer preparation within the original request budget is the supported
candidate; wrong paths/source discovery/edit planning remain separate. No restart,document selection,
new model API or readiness gate is proposed.

Counts: **28 isolated PASS,28 skips,84 Agent attempts,56/94 processed and37 pending**.
Original **95/189** and baseline pointer remain unchanged. No103regression/control or repeat.

## 2026-09-13 21:18 UTC Order103 verified current-workbook observation replay running

Agent attempt **84**, condition `holo31-all-roles-order103-observed-workbook-retest-20260913-v1`,
starts `2026-09-13T21:17:18.510472+00:00`, supervisor **50057** / session **13887**, worker **50064**
(started `21:17:26.602753 UTC`), selected `[103]`. Existing frozen validation is `ok`.
Source **532 files /81,355,098 bytes**, frozen `21:16:40.814219 UTC`, SHA-256
`d2e6c6931262e6f40a2bf16fd7267c422c58e05842282ece508532c366843f1b`;
config SHA-256 `025c220800f09de46bc4ca7a80d45dce685162f8275df69fdb66afe0d0817436`.
Both roles retain Holo1direct224,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

The original23event episode falsely blocked writes after four successful current-workbook inspections.
For a filename-only GUI open,the existing observation check now accepts the exact basename from a
verified native `workbook.inspect`; later background reads do not supersede that current-focus evidence.
Explicit-location constraints remain unchanged,reads alone cannot establish focus,and errors name
the public API. No directory,sheet,range,value or subsequent action is inferred; no new gate.

**60 existing spreadsheet tests pass**,with unchanged state/arguments and explicit-location behavior;
Ruff/scoped diff pass. Offline replay before original9/10/12/18/22removes the false blocks without
rewriting evidence or proving PASS. The seal also carries the two stale action-name corrections from102.
See the [Order103 report](archive/all-holo-order103-observed-workbook-retest-20260913.md) and
[preserved triage](../experiments/work/all-holo-order103-triage-20260913.md).

Only **Order103** is retesting/running. Counts: **27 isolated PASS,28 skips,84 Agent attempts,
55/94 processed and38 pending**. Outcome pending; original **95/189** and baseline pointer remain
unchanged. No regression/control or full rerun.

## 2026-09-13 21:11 UTC Order101 field-name recovery with failed task;102 offline skip; next103

Attempt **83** finalizes `2026-09-13T21:07:42.075821+00:00` as **failed/0.0**, **35 steps /
1249.258 seconds**, `agent_done`,zero completion rejections. Supervisor **52435** / session **31601**
and worker **52446** both exit **0** and are gone; both final source/config integrity records are `ok`.
Results SHA-256 `77bfa006f872a9408dc98222f124d2fe59677def3c68db91939ba49b173ff25a`.
No protocol/transport failure or operator interruption. See the
[final Order101 report](archive/all-holo-order101-field-feedback-retest-20260913.md).

The exact-label error hint reaches requests22–25; step25corrects field names and successfully writes
26fields. This is observed recovery after the hint and further inspection, not proof of the hint's
sole causal benefit. Only **3 of7 outputs** are created,with wrong filenames,rating columns and marks.
Native read-back equals the model's submitted fields. Done35and terminal audit36accept the completion
claim; the pinned evaluator finds none of seven exact filenames. Missing deliverables are not a new
environment failure. The terminal request truthfully reports truncated table context,retaining3of8rows;
earlier requests had received the complete source table.

An independent [source/scorer evidence note](../experiments/work/all-holo-order101-source-scorer-mismatch-20260913.md)
also establishes that actual source rows for six of seven employees disagree with unchanged pinned
scorer rules. Preserve that concern separately from the model's real output errors. **Skip101** after
two distinct attempts,with no third unchanged replay,golden-value injection,scorer change or new gate.

**Skip102 offline,with no new episode.** Its [disposition](archive/all-holo-order102-offline-disposition-20260913.md)
records31original events/23GUI requests,no file movement,complete errors/1605character PDF feedback
and available read/rename APIs. No small causal runtime defect is established. Root corrects two stale
guidance action names after83exit and verifies those separately; the wording is not claimed to recover102.

Actual next **queue56 / Order103**,multi-app task `3a93cae4-ad3e-403e-8c12-65303b271818`,is
**current/diagnosing**,with no episode registered. Counts: **27 isolated PASS,28 skips,83 Agent
attempts,55/94 processed and38 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or full rerun.

## 2026-09-13 20:47 UTC Order101 existing protocol/PDF error-feedback replay running

Agent attempt **83**, condition `holo31-all-roles-order101-field-feedback-retest-20260913-v1`,
starts `2026-09-13T20:46:36.933338+00:00`, supervisor **52435** / session **31601**, worker **52446**
(started `20:46:44.915827 UTC`), selected `[101]`. Existing frozen validation is `ok`.
Source **532 files /81,351,381 bytes**, frozen `20:45:27.678621 UTC`, SHA-256
`5a45982afd34a91cdd9409e6c947fce7ea8e1c31c6b0a069ffb9e567252da6e4`;
config SHA-256 `8e523b04ffd344733de67d898e3abe8e68ae33b038d3cfed7a63435c401b8260`.
Both roles retain Holo1direct224,thinking/T0.8,top_k7,100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.

Existing `additionalProperties` errors now explain the rejected level and public allowed fields;
PDF unknown-name422errors list exact observed native-label/name candidates. No aliases,fuzzy matching,
automatic selection,execution on invalid names,validator/schema-acceptance change or new gate.
**PDF17passed; protocol/nested65passed and1known pre-existing matrix-branch hint failure**, already
recorded for96. New retry coverage passes, including unchanged raw/schema and actual PDF-error
delivery; Ruff/scoped diff pass. See the [Order101 feedback report](archive/all-holo-order101-field-feedback-retest-20260913.md).

Only **Order101** is retesting/running. Counts: **27 isolated PASS,26 skips,83 Agent attempts,
53/94 processed and40 pending**. Preserve82's protocol failure/null separately; outcome83is pending.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 20:46 UTC Order101 transport completes; protocol failure retained for feedback repair

Attempt **82** finalizes `2026-09-13T20:38:41.135868+00:00` as **model_protocol_failure/null**,
**816.352 seconds**. Results leave `steps` null; the trace contains **10 recorded events**, followed
by three protocol retries for step **11**. Supervisor **7629** / session **97952** and worker **7639**
both exit **0** and are gone. Both final source/config integrity records are `ok`; no evaluator loads.
Results SHA-256 `e29ddfd223e77e102bd84d894659a7da5fcb201c3569f8d39d991ff047aff1eb`.

There are **no transport errors**: a **167-second** model response completes through direct224.
Step10 PDF fill rejects17visible labels supplied as real field names and writes no fields.
Step11 retry1uses a JSON-string payload; retry2corrects it to an object but adds unsupported root
`timeout_ms`; retry3has both errors. All **208 table cells /109 field records** reach actual model
requests completely. See the [finalized direct-origin report](archive/all-holo-order101-direct-transport-retest-20260913.md).

**Order101 remains current/diagnosing** for a distinct
[field-feedback repair](archive/all-holo-order101-field-feedback-retest-20260913.md): list public
allowed fields in existing `additionalProperties` hints and exact observed label/name candidates in
PDF unknown-name errors. Preserve the existing validator,422rejection,noalias/noexecution and schema
acceptance. No second episode is registered yet; no new gate or unchanged replay.

Counts remain **27 isolated PASS,26 skips,82 Agent attempts,53/94 processed and40 pending**.
Original **95/189** and baseline pointer remain unchanged. Response completion establishes no task
PASS or endpoint-only causal benefit; no regression/control or additional full run.

## 2026-09-13 20:25 UTC Order101 direct-origin replay running after original proxy524

Agent attempt **82**, condition `holo31-all-roles-order101-direct-transport-retest-20260913-v1`,
started `2026-09-13T20:24:51.052366+00:00`, supervisor PID **7629** / session **97952**, worker PID
**7639** (started `20:24:58.807810 UTC`), selected orders `[101]`. Both roles use existing
**Holo1direct224**,thinking/T0.8,top_k7 and unchanged100/50 steps,one same-VM restart,1800Agent seconds
and30GiB floor. The original Cloudflare524is avoided; task completion remains unproven.

The source is unchanged from81: **532 files /81,347,451 bytes**, SHA-256
`62ddc4c6a826839ae40626e81e92ffdbe749bbf77e6ad3fc8d557ba774dd740d`,
refrozen at `20:23:47.786466 UTC`. Config SHA-256:
`152a465c0abd15d443fd4cced4e7b3b9e548eaa54aeb747d40ee878d2287b36d`.
Existing frozen validation passes. No source/test changes,extra health probes or new test campaign.
Source/tests stay frozen through both exits. See the
[Order101 report](archive/all-holo-order101-direct-transport-retest-20260913.md).

Only **Order101** is retesting/running. Counts: **27 isolated PASS,26 skips,82 Agent attempts,
53/94 processed and40 pending**. Original **95/189** and baseline pointer remain unchanged;
sampling/accumulated repairs prevent endpoint-only attribution. No new gate,regression/control or full rerun.

## 2026-09-13 20:23 UTC Order100 bounded unscored browsing skip; next101 transport repair

Attempt **81** finalizes `2026-09-13T20:22:14.700944+00:00`. Worker **29418** is **interrupted/null**,
**38 steps /1227.648 seconds**, exit **0**, after bounded root SIGINT. Supervisor **29353** / session
**5588** exits **2**, recording **metadata/task invalid_configuration** because the interrupted worker
is nonreportable. Both PIDs are gone; both final source/config integrity records are `ok`. No evaluator
loaded. Preserve the dual statuses; this is not scored0/PASS or source drift.
Supervisor results SHA-256 `981828e1a97950711e6beebb82e1b6c42437883e07d6c76589038ddde790c8bd`;
worker results SHA-256 `2aeadeaf1f6876524eafb72dd97545b918aad73e908077222d50cca197985381`.

The38events comprise29GUI,5Adapter calls(four opens plus mkdir),two searches and two premature done
proposals that do not terminate the episode. No `filesystem.find`,copy or archive occurs. The type-feedback
fix is **not exercised live**;25focused checks verify it locally. Exact screenshot delivery at22is
confirmed, with no new execution defect. **Skip100unresolved** after sustained whole-image browsing,
without unchanged replay or a new gate. See the
[Order100 report](archive/all-holo-order100-find-kind-feedback-retest-20260913.md).

Actual next queue **54 / Order101**, multi-app task `185f29bd-5da0-40a6-b69c-ba7f4e0324ef`, is
**current/diagnosing**, with no episode registered. Its
[preserved transport triage](../experiments/work/all-holo-order101-transport-triage-20260913.md) proves
Cloudflare524after29executed events and three identical step30requests without execution. One fresh
sealed direct224retest, with no source change or added retry machinery, will separate response recovery
from task success. Current sampling/accumulated repairs prevent an endpoint-only benefit claim.

Counts: **27 isolated PASS,26 skips,81 Agent attempts,53/94 processed and40 pending** behind current101.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 20:02 UTC Order100 filesystem type-filter feedback replay running

Existing filesystem-find feedback now retains the owner-returned `kind` and explains file-only or
directory-only exclusions for zero matches. Default type,model-selected arguments and native search
remain unchanged. **25 focused checks pass**, including a real directory search through forwarding and
actual parent requests; only an explicitly selected directory retry finds that directory. Ruff/scoped
diff pass, with no hidden search,inferred intent or new gate. See the
[Order100 report](archive/all-holo-order100-find-kind-feedback-retest-20260913.md).

Agent attempt **81**, condition `holo31-all-roles-order100-find-kind-feedback-retest-20260913-v1`,
started `2026-09-13T20:01:34.562616+00:00`, supervisor PID **29353** / session **5588**, worker PID
**29418** (started `20:01:42.647182 UTC`), selected orders `[100]`, existing frozen validation `ok`.
Source frozen at `20:00:28.882735 UTC`:
`62ddc4c6a826839ae40626e81e92ffdbe749bbf77e6ad3fc8d557ba774dd740d`
(532 files /81,347,451 bytes). Config SHA-256:
`5fa2cd07cd9de8809d805007956de055a7bfe8f6a2784956bf3fc5d8564db71f`.
Both roles use original-worker02 **Holo1direct224** pairing,thinking/T0.8,top_k7 and existing100/50
steps,one same-VM restart,1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits.
Outcome pending; fixing discovery feedback does not guarantee correct visual/output planning.

Only **Order100** is retesting/running. Counts: **27 isolated PASS,25 skips,81 Agent attempts,
52/94 processed and41 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or full rerun.

## 2026-09-13 19:56 UTC Order98 unscored bounded skip;99 offline skip; next100

Attempt **80** finalizes `2026-09-13T19:55:27.380754+00:00`. Worker **48609** is **interrupted/null**,
**32 steps /953.611 seconds**, exit **0**, after root SIGINT for repeated OCR/irrelevant-tool loops.
Supervisor **48597** / session **20496** exits **2**, recording **metadata/task invalid_configuration**
because an interrupted worker is nonreportable. Both PIDs are gone and both final source/config
integrity checks are `ok`. No evaluator loaded. Preserve both statuses; no scored0 or PASS.
Supervisor results SHA-256 `bc704565867644aed26acfac85060841a774dbbe11dc0f383fad45d3830aaba0`;
worker results SHA-256 `a7e8a68762ce7bcc48d5b9698fe506c3009e89d372cba749b0a00d5d46334c78`.

Four image OCR strings reach actual requests completely. Native PDF extraction returns0characters;
that PDF is not OCRed this round. `requirement.txt` is unrelated Python dependencies. No typing,
spreadsheet write or done occurs, so the boolean receipt fix is locally verified but **not exercised
in80**. **Skip98 unresolved** after two affected attempts, preserving79/80 separately with no third
unchanged replay. See the [Order98 report](archive/all-holo-order98-press-enter-feedback-retest-20260913.md).

**Skip99 offline, with no new episode.** Its
[aligned search review](../experiments/work/all-holo-order99-search-review-20260913.md) preserves original
instruction/recovery/exclusions and confirms complete errors/PDF text plus discoverable generic read/move
tools. Early vague queries and planning loops remain; no small causal runtime fix is established.
No benchmark mapping, speculative ranking change or unchanged replay.
The [Order99 disposition](archive/all-holo-order99-offline-disposition-20260913.md) records this offline skip.

Actual next queue **53 / Order100**, multi-app task `82e3c869-49f6-4305-a7ce-f3e64a0618e7`, is
**current/diagnosing**, with no episode registered. Its
[preserved triage](../experiments/work/all-holo-order100-triage-20260912.md) identifies returned
filesystem-find `kind` lost from model feedback, while the larger GUI viewing loop remains separate.
Its [pending repair hypothesis](archive/all-holo-order100-find-kind-feedback-retest-20260913.md) retains
the owning filter/default and reuses existing feedback without adding a gate or hidden search.
Counts: **27 isolated PASS,25 skips,80 Agent attempts,52/94 processed and41 pending** behind current100.
Original **95/189** and baseline pointer remain unchanged; no new gate,regression/control or full rerun.

## 2026-09-13 19:40 UTC Order98 selected Enter-flag feedback replay running

The existing gateway action receipt and GUI sanitizer now retain validated `press_enter` booleans,
including false, into parent feedback. Actual execution already respected the flag and remains
unchanged. **14 delegation checks pass**, including real normal typing paths for true/false and
unchanged raw input/text/executor commands, with transport metadata filtered. Ruff/scoped diff pass;
no automatic Enter,next-cell inference,GUI/completion gate or OCR change. See the
[new Order98 report](archive/all-holo-order98-press-enter-feedback-retest-20260913.md).

Agent attempt **80**, condition `holo31-all-roles-order98-press-enter-feedback-retest-20260913-v1`,
started `2026-09-13T19:39:22.270997+00:00`, supervisor PID **48597** / session **20496**, worker PID
**48609** (started `19:39:30.291119 UTC`), selected orders `[98]`, existing frozen validation `ok`.
Source frozen at `19:38:29.453247 UTC`:
`93086d9b8c5d56a0393cdc7394207b53f8e57ba9bdf6d65954b51c77de4cf75f`
(532 files /81,341,910 bytes). Config SHA-256:
`e616b37671fa1030ab5343058cf7771f3878c40ea0ef15a99553a7cdefe2af79`.
Both Holo2direct138 roles retain thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests stay frozen through both exits; outcome pending.

Only **Order98** is retesting/running. Preserve79's worker interrupted/null and supervisor
invalid_configuration as distinct statuses. Counts: **27 isolated PASS,23 skips,80 Agent attempts,
50/94 processed and43 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or full rerun.

## 2026-09-13 19:37 UTC Order98 OCR recovers; interrupted worker is nonreportable to supervisor

Attempt **79** final timestamp is `2026-09-13T19:35:28.419663+00:00`. The **worker episode is
interrupted/unscored**, rewardnull, **40 steps /1413.142 seconds**, after root SIGINT for repeated
OCR/click loops. Worker **58697** exits **0**. Supervisor **58645** / session **17167** exits **2** and
records **metadata/task `invalid_configuration`**, because an interrupted worker is not a completed,
reportable result. Both PIDs are gone and both final **source/config integrity records are `ok`**.
Preserve these distinct statuses: this is neither scored0/PASS nor source drift. No evaluator loaded.
Supervisor results SHA-256:
`f6c84f91559b0cb1f9efa74c57c287d6b57ceef9568aaa5f55fd568c506d7c18`;
worker results SHA-256:
`149345334a1761a9c3519add86473f4436daacd866c10de5b8ade95c4f75dc8a`.

The original missing-backend path is exercised successfully: OCR returns **5 files /2620 characters**,
fully visible in actual requests. Initial apt-lock diagnostics were preserved and existing deployment
retry recovered; no extra Agent attempt was added. Task completion still stalls. See the
[Order98 report](archive/all-holo-order98-ocr-dependency-retest-20260913.md).

Another concrete feedback issue is now under repair: Holo26 selects **`press_enter=false`**, but the
gateway action receipt loses false and GUI-result sanitation omits both boolean flags, leaving the next
parent request without the selected flag. **Current98 stays diagnosing** for a distinct minimal receipt
fix, with execution semantics unchanged and no automatic Enter or new gate. No next episode is registered.
Counts remain **27 isolated PASS,23 skips,79 Agent attempts,50/94 processed and43 pending**. Original
**95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 19:12 UTC Order98 existing OCR dependency preparation replay running

The single existing OS installer now prepares `tesseract-ocr` and English data when absent, before
Agent execution, through existing `CommandRunner.sudo`. It retains bounded native stdout/stderr and
uses45/60-second update/install limits without changing Agent budgets. No copied credential/default,
new helper, OCR API, inferred receipt values or gate. Shell syntax, embedded Python compilation,
Ruff and **2 existing OS deployment checks pass**. See the
[Order98 report](archive/all-holo-order98-ocr-dependency-retest-20260913.md).

Agent attempt **79**, condition `holo31-all-roles-order98-ocr-dependency-retest-20260913-v1`, started
`2026-09-13T19:11:43.197760+00:00`, supervisor PID **58645** / session **17167**, worker PID **58697**
(started `19:11:51.421912 UTC`), selected orders `[98]`, existing frozen validation `ok`.
Source frozen at `19:11:02.403260 UTC`:
`52eb6f3a0b9a9af5441c5e56d95e7cc1415acb916f2d80255ddc5f8f86463ab6`
(532 files /81,340,834 bytes). Config SHA-256:
`6a7e32a1157bcbfeb1766b352f10685d2c5d49beb58fc3951a2952d74d8dc5cb`.
Both Holo2direct138 roles retain thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests stay frozen through both exits. Outcome pending;
OCR availability and original-evaluator task PASS remain separate observations.

Only **Order98** is retesting/running. Counts: **27 isolated PASS,23 skips,79 Agent attempts,
50/94 processed and43 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or further full evaluation.

## 2026-09-13 19:05 UTC Order97 source-reading improvement still fails; bounded skip to98

Attempt **78** finalized `2026-09-13T19:01:11.555826+00:00` as original-evaluator **failed/reward0**,
**11 steps /340.283 seconds**, `agent_done`, zero completion rejections. Supervisor **27168** / session
**85441** and worker **27259** exited **0**, both PIDs are gone; both final integrity records are `ok`
with unchanged source/config. The evaluator loaded only after the episode. Results SHA-256:
`62c66cb0737d35b29da490a621fbe4b8f4646304906d4176101bc7b2647941df`.

The model now reads the full **952-character source**, retained exactly in actual first-write/final
requests. It writes indices **2,0,3,4,5**, omits **1**, saves10 and incorrectly claims completion11.
Empty index1 remains visible with correct identity; all five write receipts preserve model-selected
targets/text. Original strip-then-exact scoring matches **5/7 notes**: index1 stays empty, while index4
loses two internal spaces chosen by the model. Offline original scoring reproduces0. No new execution
defect is established; source-reading improvement is not a recovered PASS. See the
[final Order97 report](archive/all-holo-order97-notes-feedback-retest-20260913.md).

**Skip97 unresolved** at two affected attempts, preserving77failed0 and78failed0 separately and retaining
verified generic repairs. No third unchanged replay, reference-whitespace tuning or new gate. Actual
next queue **51 / Order98**, multi-app task `8e116af7-7db7-4e35-a68b-b0939c066c78`, is **current/diagnosing**,
with no new episode registered. Its [preserved triage](../experiments/work/all-holo-order98-triage-20260912.md)
shows legal OCR blocked by an absent guest backend despite a correctly delivered dependency error;
inspect current owning deployment before choosing the minimal remaining correction.

Counts: **27 isolated PASS,23 skips,78 Agent attempts,50/94 processed and43 pending** behind current98.
Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 18:55 UTC Order97 observed-note feedback and replacement-usage replay running

Observed note text now survives both existing Impress projection stages, using existing1200-character
truncation and text/content priority. Notes are retained only when the source supplied that field;
65Knormal/9Krecovery budgets and nonempty flags remain unchanged. The existing `slide.set_notes` schema
now lives in its owning manifest with unchanged constraints and explicit whole-note replacement/source-copy
usage. **97 context checks +20 focused inspection checks pass**, including actual normal/recovery requests,
unchanged raw events, long-note truncation and identical direct/forwarded schema structures apart from
descriptions. Ruff/scoped diff pass. See the
[new Order97 report](archive/all-holo-order97-notes-feedback-retest-20260913.md).

Completed offline replay of77through18 confirms original request19 has **0** exact note-body occurrences,
while current normal has **3** and both recovery modes have **2**. Latest18's full31-character note is
retained; normal state52,571characters and recovery8,978 remain within existing limits. Raw evidence is
unchanged. This verifies the prior feedback repair offline, not an additional episode or task PASS.

Agent attempt **78**, condition `holo31-all-roles-order97-notes-feedback-retest-20260913-v1`, started
`2026-09-13T18:55:16.510249+00:00`, supervisor PID **27168** / session **85441**, worker PID **27259**
(started `18:55:24.689784 UTC`), selected orders `[97]`, existing frozen validation `ok`.
Source frozen at `18:54:41.315046 UTC`:
`c77b35bf2c59d859cacf259541277502ca12558cff5d2eb13f415fe08ff5074d`
(532 files /81,340,131 bytes). Config SHA-256:
`bc9c56d07c0a54a2d79eeac877b826822cc8d76c5752f40e5f811e78827bbc7a`.
Both Holo2direct138 roles retain thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests stay frozen through both exits; outcome pending.

Only **Order97** is retesting/running, with **77failed0** preserved separately. Counts: **27 isolated
PASS,22 skips,78 Agent attempts,49/94 processed and44 pending**. Original **95/189** and baseline
pointer remain unchanged; no injected content, new gate,96regression/control or full rerun.

## 2026-09-13 18:49 UTC Order97 deployment recovers; task failed with notes feedback loss

Attempt **77** finalized `2026-09-13T18:47:28.579357+00:00` as original-evaluator **failed/reward0**,
**34 steps /831.837 seconds**, `agent_done`, zero completion rejections. Supervisor **47636** / session
**46601** and worker **47708** exited **0**, both PIDs are gone; both final integrity records are `ok`
with unchanged source/config. The evaluator loaded only after the episode. Results SHA-256:
`c4464e6a7f67f6b97cb29941ea97e56b141183c070ae2dea829427a929af139d`.

Deployment and Agent execution succeed; the original HTTP500 cause remains unproven. The model never
reads the desktop source, authors summaries at **9/12/14**, replaces already-nonempty notes at
**19/26/28**, then saves **33** and submits **34**. Task PASS is not recovered.

Precise feedback distinction: raw inspection/context hints contain note bodies, but strict compact
presentation projection drops their text. **Actual request19 contains only `has_speaker_notes`, not
the existing note body.** Reader and note-editing schemas were delivered. Losing text is a confirmed
framework defect; overwriting a known nonempty note and inventing source content remain model errors.
See the [Order97 report](archive/all-holo-order97-unused-java-deploy-retest-20260913.md).

**Order97 stays current/repairing** for a distinct minimal note-text projection and owning replacement/
source-copy usage fix. Keep existing budgets and model-selected content; no automatic source read or
mapping, new gate or96regression. **No attempt78 is registered yet.** Counts remain **27 isolated PASS,
22 skips,77 Agent attempts,49/94 processed and44 pending**. Original **95/189** and baseline pointer
remain unchanged.

## 2026-09-13 18:33 UTC Order97 unused Java-dependency removal replay running

The Multi-Apps installer now omits its unused mandatory Java/apt block and dedicated retry helper,
preserving existing package copy, systemd setup and health checks. This removes an unnecessary
dependency; the exact original HTTP500 cause remains unproven because response bodies were lost.
The condition also carries the minimal validated-hotkey-keys feedback repair observed in passed96,
with **no96regression episode**. Installer syntax, **9 existing deployment checks**, **12 Holo gateway
checks**, Ruff and scoped diff checks pass. See the
[Order97 report](archive/all-holo-order97-unused-java-deploy-retest-20260913.md).

Agent attempt **77**, condition `holo31-all-roles-order97-unused-java-deploy-retest-20260913-v1`,
started `2026-09-13T18:33:23.486005+00:00`, supervisor PID **47636** / session **46601**, worker PID
**47708** (started `18:33:31.509000 UTC`), selected orders `[97]`, existing frozen validation `ok`.
Source frozen at `18:32:50.882921 UTC`:
`97e82387fc593195280535391fa4f3c129921380b88fbf605538b3d3db204b05`
(532 files /81,335,663 bytes). Config SHA-256:
`a6d6d51bacaab934aa44ac08ab798ca42ec53a51ab8ce2dd43f1ed595849aa0a`.
Both Holo2 direct138 roles use thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests stay frozen through both exits. Outcome pending;
deployment health/Agent entry and original-evaluator task PASS are separate observations.

Only **Order97** is retesting/running. Counts: **27 isolated PASS,22 skips,77 Agent attempts,
49/94 processed and44 pending**. Original **95/189** and baseline pointer remain unchanged;
no new gate, regression/control or further full evaluation.

## 2026-09-13 18:30 UTC Order96 GUI/intermediate-workbook PASS; next Order97

Attempt **76** finalized `2026-09-13T18:29:07.145091+00:00` as original-evaluator **PASS/reward1**,
**14 steps /595.774 seconds**, `agent_done`, zero completion rejections. Supervisor **18837** / session
**41997** and worker **18913** exited **0**, both PIDs are gone; both final integrity records are `ok`
with unchanged source/config. The evaluator loaded only after the episode. Results SHA-256:
`36fd81b0da7591e3c9979ba1f5aa21dbe8d17cf21fefec7e9fbeddcb0fb26b90`.

The model reads the full displayed-string matrix, creates an intermediate workbook with the observed
header and selected row, copies those cells, returns to Writer, pastes at **13** and submits at **14**.
Patched `text.find` was never retrieved/called, so this adds a task PASS without a causal patch-benefit
claim. The known unrelated matrix-feedback test failure remains recorded. See the
[Order96 report](archive/all-holo-order96-optional-format-guidance-retest-20260913.md).

A separate observed defect drops ordered `hotkey` keys from model-facing feedback although raw
grounding evidence retains the executed ctrl+c. It did not prevent this PASS. Root is preparing the
minimal validated-list retention fix for the next source seal, with **no Order96 regression episode**.

Actual next queue **50 / Order97**, multi-app task `eb303e01-261e-4972-8c07-c9b4e7a4922a`, is
**current/diagnosing**, with no episode registered. Its
[preserved environment triage](../experiments/work/all-holo-order97-environment-triage-20260912.md)
shows deployment HTTP500 and an unnecessary original Java/apt dependency; the lost response bodies
prevent establishing the exact old exception. Compare current installation and accumulated repairs
before the fresh affected attempt. Counts: **27 isolated PASS,22 skips,76 Agent attempts,49/94
processed and44 pending** behind current97. Original **95/189** and baseline pointer remain unchanged;
no regression/control, new gate or full rerun.

## 2026-09-13 18:19 UTC Order96 optional-format guidance replay running

Existing schema feedback now explains `minProperties` in plain field-count terms, and owning Writer
literal-only search usage explains omitting unused `format` while retaining explicit `case_sensitive`.
Validators and model arguments are unchanged. **58 protocol checks pass**; the nested-schema file is
**4 passed/1 failed**. Its new actual retry-request test passes, while an existing matrix-branch hint
assertion fails. An isolated old-formatter replay is **3 passed/2 failed**, with that same matrix failure
plus the new test, confirming the matrix failure is unrelated. Ruff, scoped diff and structural checks
pass; this is **not an all-checks-pass claim**. See the
[Order96 report](archive/all-holo-order96-optional-format-guidance-retest-20260913.md).

Agent attempt **76**, condition `holo31-all-roles-order96-optional-format-guidance-retest-20260913-v1`,
started `2026-09-13T18:18:57.071953+00:00`, supervisor PID **18837** / session **41997**, worker PID
**18913** (started `18:19:05.337683 UTC`), selected orders `[96]`, existing frozen validation `ok`.
Source frozen at `18:18:23.031955 UTC`:
`3dacc5e84057a8f3c8bc03480762911aad6cd9ca357304793b23918d2415074b`
(532 files /81,333,799 bytes). Config SHA-256:
`cdea26846d5b7bc077814d6111caa294bbad69683d72254dd5e3addb3a93a84c`.
Both Holo2 direct138 roles use thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests stay frozen through both exits. Outcome pending.

Only **Order96** is retesting/running. Counts: **26 isolated PASS,22 skips,76 Agent attempts,
48/94 processed and45 pending**. Original **95/189** and baseline pointer remain unchanged;
no new gate, regression/control or further full evaluation.

## 2026-09-13 18:13 UTC Order95 bounded unscored navigation skip; next Order96

Attempt **75** finalized `2026-09-13T18:08:00.710896+00:00` as **interrupted / unscored**, reward
null, **21 steps /778.972 seconds**, zero completion rejections. Supervisor **35454** / session **6075**
exited **130**, worker **35487** exited **0**, both PIDs are gone. Worker final integrity is `ok`;
supervisor final integrity is absent/null. Source/config stayed frozen through exit; no evaluator loaded.
This developer stop is not a scored0 or deadline failure. Results SHA-256:
`bf93ee6108ae9595abecc031cab863c8af2e5b97404f17342fdcd899a1e28fb5`.

The first20steps repeatedly navigate the first PDF without completing extraction or creating a workbook.
Final **21** searches for PDF page navigation, with no subsequent API call. Actual request7 preserves
grounded click feedback; no runtime scroll-direction inversion is established. The repaired command-error
path never triggers live. Its original-trace replay and synthetic checks verify diagnostic retention,
but this episode establishes no live benefit or PASS. **Skip Order95 unresolved** at this bounded
checkpoint, with no impossibility claim or unchanged replay. See the
[Order95 report](archive/all-holo-order95-nested-error-priority-retest-20260913.md).

Actual next queue **49 / Order96**, multi-app task `00fa164e-2612-4439-992e-157d019a8436`, is
**current/diagnosing**, with no episode registered. Its
[preserved triage](../experiments/work/all-holo-order96-triage-20260912.md) shows empty optional format
and then missing case sensitivity exhausting protocol retries despite complete schemas and feedback.
Inspect existing usage descriptions and the technical `minProperties` hint for a minimal clarification.
Counts: **26 isolated PASS,22 skips,75 Agent attempts,48/94 processed and45 pending** behind current96.
Original **95/189** and baseline pointer remain unchanged; no regression/control, new gate or full rerun.

## 2026-09-13 17:55 UTC Order95 nested command-error priority replay running

Six lines in existing context fitting now propagate existing error priority through `error` and
`previous_error` descendants. Offline replay of preserved step23 confirms old recovery fitting loses
the missing-module cause while patched fitting retains it, at the same budget; normal fitting is
unchanged. Synthetic latest-failure fixtures change from **2 failed/1 passed** to **3 passed**.
The model-feedback module **16 checks** and context-projection/request-block modules **101 checks**,
Ruff and scoped diff checks pass. No new parser, envelope, API, automatic library installation or gate.
See the [Order95 report](archive/all-holo-order95-nested-error-priority-retest-20260913.md).

Agent attempt **75**, condition `holo31-all-roles-order95-nested-error-priority-retest-20260913-v1`,
started `2026-09-13T17:54:50.723947+00:00`, supervisor PID **35454** / session **6075**, worker PID
**35487** (started `17:54:58.624789 UTC`), selected orders `[95]`, existing frozen validation `ok`.
Source frozen at `17:54:15.472019 UTC`:
`45742b58bd4ec114163afd0aded8001293a0bd88118757013387ff689a4e245d`
(532 files /81,328,859 bytes). Config SHA-256:
`883fd7a487c3a16d74d8d29fe3f64f7b99ac237833a1fc39429000314d07b3a9`.
Same both Holo2 direct138 pairing,thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests remain frozen through both exits. Outcome pending;
feedback recovery alone does not fix the original model coverage/path/save errors.

Only **Order95** is retesting/running. Counts: **26 isolated PASS,21 skips,75 Agent attempts,
47/94 processed and46 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or full rerun.

## 2026-09-13 17:42 UTC Order94 bounded unscored GUI-loop skip; next Order95

Attempt **74** finalized `2026-09-13T17:41:37.676137+00:00` as **interrupted / unscored**, reward
null, **12 steps /514.224 seconds**, zero completion rejections. Supervisor **55541** / session
**99118** exited **130**, worker **55585** exited **0**, both PIDs are gone. Worker final integrity
is `ok`; supervisor final integrity is absent/null. Source/config stayed frozen through exit and
no evaluator loaded. This developer stop is not a scored0, deadline or new user stop. Results SHA-256:
`32b19a6329d71de916137e6073df1db2955dc540c2f8056755451cb6318fd2bc`.

The model opens source at **1**, clicks through **2–11**, and reaches an existing repeated-click block
at **12**. No source edit, save, execution or output capture occurs. Neither the whitespace-literal fix
nor the API error-counter fix is exercised; this episode establishes no live benefit. **Skip Order94**
unresolved at two affected attempts, preserving **73 and74 separately as interrupted/null**, with no
third unchanged replay. Retain tested generic fixes without a PASS claim. See the
[Order94 report](archive/all-holo-order94-disk-buffer-guidance-retest-20260913.md).

Actual next queue **48 / Order95**, multi-app task `b5062e3e-641c-4e3a-907b-ac864d2e7652`, is
**current/diagnosing**, with no episode started. Its
[preserved triage](../experiments/work/all-holo-order95-triage-20260912.md) establishes an absent output
workbook and missing causal command stderr in original next requests, alongside independent model
coverage/path/save errors. Compare that evidence with current projection and accumulated repairs before
choosing any further correction. Counts: **26 isolated PASS,21 skips,74 Agent attempts,47/94 processed
and46 pending** behind current95. Original **95/189** and baseline pointer remain unchanged; no
regression/control, new gate or full rerun.

## 2026-09-13 17:33 UTC Order94 whitespace-literal and retry-contract replay running

The owning native `old` check now accepts nonempty whitespace exactly as its public contract declares,
without trimming. Existing repeated-failure accumulation reuses the existing stale-block predicate so
an effective mutation invalidates older errors. Native replacement, model-selected source and error
signatures remain unchanged. **11 literal-contract tests** and **47 retry/recovery tests**, Ruff,
scoped diff checks and existing frozen validation pass. No new block type, gate, signature framework,
automatic program correction or editor synchronization. See the
[Order94 report](archive/all-holo-order94-disk-buffer-guidance-retest-20260913.md).

Agent attempt **74**, condition `holo31-all-roles-order94-literal-retry-contract-retest-20260913-v1`,
started `2026-09-13T17:32:52.720447+00:00`, supervisor PID **55541** / session **99118**, worker PID
**55585** (started `17:33:00.297336 UTC`), selected orders `[94]`, existing frozen validation `ok`.
Source frozen at `17:31:39.616151 UTC`:
`ef0c9dcd8ea77defa3a23d622736bb7304eea6fb35a83ce997e0a8e8b54a87e4`
(532 files /81,324,775 bytes). Config SHA-256:
`b7f157223be9b145a6e86d364aa0f9ea1e16f44041c6a03b3af9788f83d9ef4b`.
Same both Holo2 direct138 pairing, thinking/T0.8,top_k7 and existing100/50 steps,one same-VM restart,
1800Agent seconds and30GiB floor. Source/tests stay frozen through both exits. Outcome pending.

Only **Order94** is retesting/running, now its second affected attempt; **73 interrupted/null** remains
preserved separately. Counts: **26 isolated PASS,20 skips,74 Agent attempts,46/94 processed and47
pending**. Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 17:30 UTC Order94 unscored stop confirms two focused repair targets

Attempt **73** finalized `2026-09-13T17:28:31.934675+00:00` as **interrupted / unscored**, reward
null, **25 steps /878.904 seconds**, zero completion rejections. The developer initiated the stop;
the runner's generic user-interrupt label does not mean a new user stop, scored0 or deadline failure.
Supervisor **18696** / session **4748** exited **130**, worker **18750** exited **0**, both PIDs are
gone. Worker final integrity is `ok`; supervisor final integrity is absent/null. Source/config remained
frozen through exit; no evaluator loaded. Results SHA-256:
`6f21c8ee0e2ec966e6c238fede88f751f76a3e33bad4b482a09cb4a2251fa9fc`.

Complete saved-disk/buffer guidance reaches requests **4/10–12**, but GUI cursor loops and bad
indentation remain. The model now selects source execution, and actual stderr reaches it. Two concrete
defects support minimal repairs: **4** supplies a schema-valid `old` of twelve spaces but native
`.strip()` validation rejects it; **17** actually executes after successful file mutation **16**, then
receives a repeated-error label that counts an earlier failure invalidated by that mutation. This is
stale counting after execution, not a pre-execution block or suppressed native error. See the
[Order94 report](archive/all-holo-order94-disk-buffer-guidance-retest-20260913.md).

**Order94 stays current/repairing** for a distinct second condition: align the existing native nonempty
literal check and exclude invalidated prior failures from existing repetition counting. Focused fixes
and checks precede a new freeze; **no attempt74 is registered yet**. Guidance delivery alone does not
establish a PASS or causal benefit. Counts remain **26 isolated PASS,20 skips,73 Agent attempts,
46/94 processed and47 pending**. Original **95/189** and baseline pointer are unchanged; no skip,
regression/control, new gate or full rerun.

## 2026-09-13 17:16 UTC Order94 saved-disk and unsaved-buffer usage replay running

Existing file descriptions and read guidance now explicitly distinguish saved disk from an unsaved
editor buffer, direct exact `old` selection from the latest disk text, and require model-selected
indentation on every `new` line. Native editing semantics remain unchanged. **22 existing focused
checks**, Ruff and structural direct/forwarded-description checks pass; the complete639-character
read guidance fits its existing1200-character allowance. No new reader, automatic synchronization,
fuzzy matching, injected source, screenshot hiding or gate. See the
[Order94 report](archive/all-holo-order94-disk-buffer-guidance-retest-20260913.md).

Agent attempt **73**, condition `holo31-all-roles-order94-disk-buffer-guidance-retest-20260913-v1`,
started `2026-09-13T17:13:41.440429+00:00`, supervisor PID **18696** / session **4748**, worker PID
**18750** (started `17:13:49.886151 UTC`), selected orders `[94]`, existing frozen validation `ok`.
Source frozen at `17:13:14.517511 UTC`:
`245042a57766d46089095eb8389b733f6e03006e62c7cd34b421651907ff9b8d`
(532 files / 81,319,492 bytes). Config SHA-256:
`5e0ee02d7047264d624909662a2428bb500378ad0df75443ad2e2429488f9c68`.
Both Holo2 roles use original-worker10 pairing directly at `http://192.168.0.138:8001/v1`,
thinking/T0.8, top_k7 and existing100/50 steps, one same-VM restart,1800Agent seconds and30GiB floor.
Source/tests remain frozen through both process exits. Outcome pending; this is not a pure description
ablation because original sampling/transport and accumulated source differ.

Only **Order94** is retesting/running. Counts: **26 isolated PASS, 20 skips, 73 Agent attempts,
46/94 processed and47 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or further full evaluation.

## 2026-09-13 17:13 UTC Order93 bounded whitespace-residual skip; next Order94

Final host-only [PDF comparison](../experiments/work/all-holo-order93-pdf-comparison-20260913.json)
confirms **12/12 filenames** and per-file page counts match (**1523 pages total**). Nine extracted texts
match exactly; the other three differ only by space/newline exchanges. All twelve whole-document texts
match after whitespace normalization. This does not establish equal per-page text or visual rendering;
the exact wrapping/environment cause remains unproven despite both producer labels reporting LibreOffice7.3.
Archive component **0.9976401513848617** and history component **1** give official reward
**0.9988200756924308**, still **failed**, with **no PASS** or substituted scoring threshold.

**Skip Order93** after this bounded diagnosis and preserve attempt **72** unchanged. No unchanged replay,
reference-whitespace rewriting or reference injection. Generic terminal guidance remains, with no live
benefit claim because its error branch did not trigger. See the
[completed report](archive/all-holo-order93-terminal-literal-feedback-retest-20260913.md).

Actual next queue **47 / Order94**, multi-app task `f918266a-b3e0-4914-865d-4faa564f1aef`, is
**current/diagnosing**, with no episode started. Its
[preserved triage](../experiments/work/all-holo-order94-triage-20260912.md) shows unsaved editor/disk
confusion and stale/newline-free literal replacements despite complete disk text and native error feedback.
The small prospective clarification explains saved-disk scope, exact latest `old` and explicit per-line
indentation; no automatic edit correction or new gate is inferred.

Counts: **26 isolated PASS, 20 skips, 72 Agent attempts, 46/94 processed and47 pending** behind
current94. Original **95/189** and baseline pointer remain unchanged; no regression/control or full rerun.

## 2026-09-13 17:06 UTC Order93 creates twelve PDFs; non-unit score remains under offline diagnosis

Attempt **72** finalized `2026-09-13T17:05:22.446313+00:00` as **failed**, original reward
**0.9988200756924308**, 12 steps / 522.175 seconds, `agent_done`, one completion rejection. This remains
below the unchanged unit-pass criterion and adds **no PASS**. Supervisor **48005** / session **55046**
and worker **48015** exited **0**, both PIDs are gone; both final integrity records are `ok` with unchanged
source/config. The evaluator loaded only after the episode. Results SHA-256:
`1b9a6e342a69153344b76bd58683ec29f537147b3440a1e50b1c1f0f6021d3f8`.

GUI-entered conversion **2** produced **12 PDFs**, observed with timestamps at **9**. API **7/11** still
used literal globs, returning process code0 with native source-could-not-load diagnostics. The newly added
visible-terminal error guidance did **not trigger**, so output progress cannot be attributed to that fix.
The remaining scorer/artifact difference is being compared offline; no residual cause is established yet.
See the [Order93 report](archive/all-holo-order93-terminal-literal-feedback-retest-20260913.md).

**Order93 stays current/diagnosing**, with no skip, next episode or threshold change. Counts remain
**26 isolated PASS, 19 skips, 72 Agent attempts, 45/94 processed and48 pending**. Original **95/189**
and baseline pointer remain unchanged; no regression/control or reference-tuned change is inferred.

## 2026-09-13 16:57 UTC Order93 visible-terminal literal-argument feedback replay running

The visible-terminal `COMMAND_FAILED` branch now reuses existing conditional literal-argument guidance
with accurate combined-output wording and shell advice. Original errors already reached the model;
this adds usage context while preserving every argv string, native output/returncode and execution
behavior. No wildcard expansion, filename/script injection, conversion macro, rejection or gate.
**38 focused checks**, Ruff and diff checks passed, including real synthetic subprocess errors and
unchanged legitimate pattern handling. See the
[Order93 report](archive/all-holo-order93-terminal-literal-feedback-retest-20260913.md).

Agent attempt **72**, condition `holo31-all-roles-order93-terminal-literal-feedback-retest-20260913-v1`,
started `2026-09-13T16:56:27.388321+00:00`, supervisor PID **48005** / session **55046**, worker PID
**48015** (started `16:56:35.226907 UTC`), selected orders `[93]`, existing frozen validation `ok`.
Source frozen at `16:55:43.018964 UTC`:
`556af597c945ebcc6b0d03ef9b1bdd97bdc507cc3aa8316f76e1c18d56e5a27b`
(532 files / 81,318,701 bytes). Config SHA-256:
`2b5b3fd726dfe7446e50bca46f8999d687223421c28a0d9a40b23fb7f7f70149`.
Original worker09 Holo2 pairing uses direct `http://192.168.0.138:8001/v1`, both thinking/T0.8 roles,
top_k7, existing100/50 steps, one same-VM restart, 1800 Agent seconds and30GiB floor. Source/tests
remain frozen through supervisor and worker exit; model-selected commands and output checks determine
task behavior, with original evaluator scoring only after the episode.

Only **Order93** is retesting/running. Counts: **26 isolated PASS, 19 skips, 72 Agent attempts,
45/94 processed and48 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or further full evaluation.

## 2026-09-13 16:52 UTC Order91 bounded GUI-loop skip; next Order93

Attempt **71** finalized `2026-09-13T16:46:12.622915+00:00` as **interrupted / unscored**, reward null,
27 steps / 1142.957 seconds, zero completion rejections. Supervisor **54547** / session **89821** exited
**130**, worker **54621** exited **0**, both PIDs are gone. Worker final integrity is `ok`; supervisor
final integrity is absent/null, not an integrity PASS. Source/config stayed unchanged through exit and
no evaluator loaded. Results SHA-256:
`ecf911fe68d31f84b6451766933b2efa882a46b9f9fa7815d12661b1fd3f26d2`.

The model retrieved records at **6** but chose GUI workbook construction and repeatedly entered the
first subject. Reads **13/14/26** truthfully reported a missing target and unsaved workbook. Recovery
**25** then tools_search **27** exposed creation/inspection routes, but no API creation, numeric correction
or completed report occurred. This attempt does not establish scalar-ordering effectiveness. Grounding
**1/2** supplied arrays for separate integer coordinates; neither integral-float compatibility nor output
token-limit causality is established by those complete parseable arguments. See the
[Order91 report](archive/all-holo-order91-numeric-cell-usage-retest-20260913.md).

At two affected attempts, **skip Order91 unresolved** without an impossibility claim. Keep generic type/
readback descriptions and preserve **attempt70 failed0** separately from **71 interrupted/null**.
Counts: **26 isolated PASS, 19 skips, 71 Agent attempts and45/94 processed**. Actual next queue
position **46 / Order93**, multi-app task `f7dfbef3-7697-431c-883a-db8583a4e4f9`, is current/diagnosing,
with **48 pending** behind it. Its [preserved triage](../experiments/work/all-holo-order93-triage-20260912.md)
shows literal argv misuse and repeated unsuccessful conversion despite available source paths/stderr.
No current-task episode is launched. Original **95/189** and baseline pointer remain unchanged;
no regression/control, semantic argument injection or new gate.

## 2026-09-13 16:28 UTC Order91 scalar-type guidance replay running

The existing scalar `oneOf` alternatives now put number first and describe quantities versus text
identifiers, accepting the identical four JSON types with unchanged native conversion. `workbook.read_file`
explains its display-only scope and points to existing `range.read` for native kinds. Structural checks
verify direct/forwarded descriptions, accepted types and native kinds; Ruff/diff checks pass. No new
test campaign, coercion, reader/API or gate. Correction to the initial attempt70 ledger: preview step7
is **workbook.read_file**, not document.read_file; its display-only scope conclusion is unchanged.
See the [Order91 report](archive/all-holo-order91-numeric-cell-usage-retest-20260913.md).

Agent attempt **71**, condition `holo31-all-roles-order91-scalar-type-guidance-retest-20260913-v1`, started
`2026-09-13T16:26:58.191249+00:00`, supervisor PID **54547** / session **89821**, worker PID **54621**
(started `16:27:06.347404 UTC`), selected orders `[91]`, existing frozen validation `ok`. Source frozen
at `16:26:09.923780 UTC`:
`dcc40ad94110a4d60a60c90ced56b1122a826027512a03980d2709fde2c4843f`
(532 files / 81,315,224 bytes). Config SHA-256:
`696224fc30127d93d260e29848a0707778f4ad18b44b106d9b8ab9820c9975a6`.
Same paired Holo1 direct `http://192.168.0.224:8002/v1`, thinking/T0.8, top_k7 and existing100/50 steps,
one same-VM restart, 1800 Agent seconds and30GiB floor. Source/tests remain frozen through all exits.

Only **Order91** is retesting/running, at its second affected attempt. Counts: **26 isolated PASS,
18 skips, 71 Agent attempts, 44/94 processed and49 pending**. Attempt70 failed0 remains preserved;
original **95/189** and baseline pointer are unchanged. No regression/control or full rerun.

## 2026-09-13 16:25 UTC Order91 still quotes numeric cells; preview does not report types

Attempt **70** finalized `2026-09-13T16:22:13.031921+00:00` as original-evaluator **failed / reward0**,
8 steps / 501.314 seconds, `agent_done`, zero completion rejections. Supervisor **29030** / session
**64685** and worker **29110** exited **0**, both PIDs are gone and both final integrity records are `ok`
with unchanged source/config. The evaluator loaded only after the episode. Results SHA-256:
`d93c4ad53d0cab60f2225188ac796801555c38aa4a30baf810e4fcbf3e25f130`.

Query **3** returns the correct five records with numeric counts; creation **6** still sends the final
column as strings despite complete schema/usage. File preview **7** exposes all **6 × 5** display values,
then done **8** is accepted. Its raw result also lacks cell kinds because `document.read_file` is a
display-text reader; this is **not projection loss**. Existing `range.read` can report native cell kinds.
See the [Order91 report](archive/all-holo-order91-numeric-cell-usage-retest-20260913.md).

**Order91 stays current/repairing.** The second small hypothesis uses number-first descriptive scalar
alternatives with the same accepted types and adds a pointer from file preview to existing native type
readback. No coercion, new reader or gate. Structural checks and a new current-only condition precede
any replay; no next attempt is launched. Counts remain **26 isolated PASS, 18 skips, 70 Agent attempts,
44/94 processed and49 pending**. Original **95/189** and baseline pointer are unchanged.

## 2026-09-13 16:14 UTC Order 91 numeric-cell usage replay running

Only the existing `workbook.create_new.rows` description changed: JSON numbers create numeric cells,
quoted digits remain text, and quantities should retain source numeric types while identifiers retain
text. The example is synthetic `["item", 7, "007"]`. Direct/forwarded schemas accept that mixed row and
retain the new description; native scalar handling preserves number7 versus string007. Structural checks
and Ruff pass. No new tests, coercion, schema shape, attachment rule, report macro or gate is added.
See the [Order 91 report](archive/all-holo-order91-numeric-cell-usage-retest-20260913.md).

Agent attempt **70**, condition `holo31-all-roles-order91-numeric-cell-usage-retest-20260913-v1`, started
`2026-09-13T16:13:37.961808+00:00`, supervisor PID **29030** / session **64685**, worker PID **29110**
(started `16:13:46.096928 UTC`), selected orders `[91]`, existing frozen validation `ok`. Source frozen
at `16:12:51.675906 UTC`:
`a813f4fdf80c78492e280ffd62a267fe67d5ebf68b8dec2a10f2564a44cb968e`
(532 files / 81,314,297 bytes). Config SHA-256:
`c073936d6d063e70b55cd5457e829f3a63f5211d6a95ed67439836552fc20cbe`.
Original worker-07 Holo1 pairing uses direct `http://192.168.0.224:8002/v1`, both thinking/T0.8 roles,
top_k7, existing100/50 steps, one same-VM restart, 1800 Agent seconds and30GiB floor. Source/tests
remain frozen through all process exits. All values/types remain model-selected; original scoring is
required to establish task recovery.

Only **Order 91** is retesting/running. Counts: **26 isolated PASS, 18 skips, 70 Agent attempts,
44/94 processed and49 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control or further full evaluation.

## 2026-09-13 16:08 UTC Order 89 GUI-only PASS; next Order 91

Attempt **69** finalized `2026-09-13T16:05:23.668768+00:00` as original-evaluator **passed / reward1**,
11 steps / 520.817 seconds, `agent_done`, **gui_only**, zero completion rejections. Supervisor **57014** /
session **64728** and worker **57058** exited **0**, both PIDs are gone and both final integrity records
are `ok`; source/config stayed unchanged through exit. The evaluator loaded only after the episode.
Results SHA-256: `55c0eac23f262427fa0c136c2f6362903f9e214da5c055d00095badfb6e22f0b`.

The model used Settings/Default Applications, recovered invalid grounding coordinate **8** at **9**,
selected VLC at **10** and submitted done **11** with visible readback. **No tools_search or native MIME
API call occurred.** This PASS does not establish the player-vocabulary fix's live effectiveness or causal
benefit; its three local discovery checks remain separate evidence. See the
[Order 89 report](archive/all-holo-order89-default-player-discovery-retest-20260913.md).

Counts now **26 isolated PASS, 18 skips, 69 Agent attempts and 44/94 processed**. Actual next queue
position **45 / Order 91**, multi-app task `d9b7c649-c975-4f53-88f5-940b29c47247`, is current/diagnosing,
with **49 pending** behind it. Its [preserved triage](../experiments/work/all-holo-order91-triage-20260912.md)
isolates model-quoted numeric cells in an otherwise correct email report; native storage preserves the
selected scalar types. Inspect current generic row-type usage before repair/replay, without automatic
coercion or a task-specific report route. No Order91 episode is launched. Original **95/189** and baseline
pointer remain unchanged; no regression/control or new gate.

## 2026-09-13 15:56 UTC Order 89 existing default-player tools discovery replay running

The catalog's existing default-association vocabulary now includes the ordinary noun **player**. This
corrects omission of `desktop.applications.inspect` and `desktop.mime_associations.set` for default-player
searches. The model still selects `tools_search`, inspects live installed IDs and advertised MIME pages,
and supplies exact desktop/MIME arguments. Native APIs, initial discovery requirement and gates are
unchanged; no application name, MIME value or default-setting recipe is injected. **3 focused tests**,
Ruff and diff checks passed. See the
[Order 89 report](archive/all-holo-order89-default-player-discovery-retest-20260913.md).

Agent attempt **69**, condition `holo31-all-roles-order89-default-player-discovery-retest-20260913-v1`,
started `2026-09-13T15:56:28.602685+00:00`, supervisor PID **57014** / session **64728**, worker PID
**57058** (started `15:56:36.620236 UTC`), selected orders `[89]`, existing frozen validation `ok`.
Source frozen at `15:55:41.638717 UTC`:
`d8a382cbc8e3e23a58a7af158fecd7308b4422d8cdd48bfffa7b53daf6f2619f`
(532 files / 81,314,011 bytes). Config SHA-256:
`0fb7474fd2956ffd2bf32b8bd171caf2d9f8a7f3eeca95834601a3636c66551e`.
Original worker-05 Holo1 pairing uses direct `http://192.168.0.224:8002/v1`, both thinking/T0.8 roles,
top_k7, existing 100/50 steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests
remain frozen through supervisor exit. Original mainT0 and currentT0.8, serving and cumulative source
differences remain separately recorded; tool visibility does not establish a task PASS.

Only **Order 89** is retesting/running. Counts: **25 isolated PASS, 18 skips, 69 Agent attempts,
43/94 processed and 50 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control, new gate or further full run.

## 2026-09-13 15:49 UTC Order 88 bounded unresolved skip after delivered guidance; next Order 89

Attempt **68** finalized `2026-09-13T15:46:40.216961+00:00` as **interrupted / unscored**, reward null,
18 steps / 502.883 seconds, zero completion rejections. Developer SIGINT ended supervisor **21665** /
session **1787** with **130**; worker **21704** exited **0**, both PIDs are gone. Worker final integrity
is `ok` with unchanged source/config through all exits; supervisor final integrity remains **null**.
No evaluator loaded. Results SHA-256:
`5b2920c9518ca79b0abec0075704adda56e579f3a2bf64b891c2cc7ae06f6185`.

New guidance at **8/12** is fully serialized with native argv/error/returncode. The model chooses
`find -name` but keeps literal `~/Desktop` paths. Conversion calls **6/7/10/11/14/15/16** return process
code 0 while complete stderr explicitly says the source could not be loaded; the model repeats them,
with no output artifact established. Neither missing-executable nor GUI-timeout feedback triggers in
this attempt. This does not demonstrate hidden stderr, Java/environment failure or a new transport bug.

At the two-affected-attempt checkpoint, **skip Order 88 unresolved**. Preserve attempt **67 failed / 0**
separately from **68 interrupted / null**; retain the truthful generic feedback without a PASS claim,
and add no third replay or semantic fix. See the
[Order 88 report](archive/all-holo-order88-command-usage-feedback-retest-20260913.md).

Counts: **25 isolated PASS, 18 skips, 68 Agent attempts and 43/94 processed**. Actual next queue
position **44 / Order 89**, multi-app task `937087b6-f668-4ba6-9110-60682ee33441`, is current/diagnosing,
with **50 pending** behind it. Its [preserved triage](../experiments/work/all-holo-order89-triage-20260912.md)
shows a deadline after GUI loops and guessed command usage despite available errors; original reward
is null. No new episode has launched. Original **95/189** and baseline pointer remain unchanged.

## 2026-09-13 15:38 UTC Order 88 error-local argument and timeout-mode replay running

The existing nonzero command error now adds literal-argument guidance only when native stderr names
the exact supplied argument containing attached redirection or wildcard syntax. Native argv/error/
returncode stay intact; program-owned pattern handling remains allowed. Direct-mode timeout feedback
now reports requested argv/cwd, `terminal_launch:false`, waiting for process exit, possible partial
effects and conditional GUI terminal advice. No argument rewriting, retry, rejection, execution change
or gate is added. **65 focused checks**, Ruff and scoped diff checks passed, including real subprocess
arguments and forwarded model-request timeout evidence. See the
[Order 88 report](archive/all-holo-order88-command-usage-feedback-retest-20260913.md).

Agent attempt **68**, condition `holo31-all-roles-order88-error-local-guidance-retest-20260913-v1`,
started `2026-09-13T15:38:05.763081+00:00`, supervisor PID **21665** / session **1787**, worker PID
**21704** (started `15:38:14.069527 UTC`), selected orders `[88]`, existing frozen validation `ok`.
Source frozen at `15:37:09.570408 UTC`:
`8872d86e09373b4ae42966a10a07bb8ce7c60638a75849d532568da49fd0ea79`
(531 files / 81,313,057 bytes). Config SHA-256:
`774d68ae3760a871ba51fb3a957b1d5f61df51f97400fbee417cff10fc658105`.
Same paired Holo1 direct `http://192.168.0.224:8002/v1`, thinking/T0.8, top_k 7 and existing
100/50 steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests stay frozen
through supervisor exit. No extra operator, schema probe or regression/control episode runs.

Only **Order 88** is retesting/running, at its second affected attempt. Counts: **25 isolated PASS,
17 skips, 68 Agent attempts, 42/94 processed and 51 pending**. Original **95/189** and baseline
pointer remain unchanged; CSV output semantics remain a model choice, not an injected repair.

## 2026-09-13 15:33 UTC Order 88 scores 0 with improved row count but wrong columns and terminal mode

Attempt **67** finalized `2026-09-13T15:31:55.416096+00:00` as original-evaluator **failed / reward 0**,
18 steps / 624.359 seconds, `agent_done`, zero completion rejections. Supervisor **52069** / session
**68338** and worker **52140** exited **0**, both PIDs are gone; both final integrity records are `ok`
with unchanged source/config. The evaluator loaded only after the episode. Results SHA-256:
`bbaecaba9ad77d2ac8841c4809f2afd6d9c6844e3e06c2e31a1c3a71ce21bcf9`.

The saved CSV now has **5001 rows × 2 columns**, versus original **1 × 10002**, but all three accepted
reference variants are **5001 × 1**. Step **16** again omits explicit terminal mode and times out
waiting for GUI exit; GUI **17** accepts the import and done **18** falsely claims completion. No
missing-executable error occurs, so the new mapping is not exercised by this Agent attempt and receives
no task-level benefit claim. See the
[Order 88 report](archive/all-holo-order88-command-usage-feedback-retest-20260913.md).

**Order 88 stays current/repairing.** The bounded second-attempt hypothesis is limited to error-local
literal-argument guidance and timeout execution-mode feedback, with no semantic argument rewriting or
gate change. Focused checks and a new current-only seal precede any replay; no next attempt is launched.
Counts remain **25 isolated PASS, 17 skips, 67 Agent attempts, 42/94 processed and 51 pending**.
Original **95/189** and baseline pointer stay unchanged.

## 2026-09-13 15:22 UTC Order 88 command-start errors and terminal usage replay running

Actual process-start `FileNotFoundError` now yields a precise missing-cwd or executable/interpreter
error, preserving exact caller argv/cwd and native diagnostic fields. The mapping uses the native
filename to distinguish cwd; it neither splits a shell string nor executes an implicit shell. Existing
descriptions clarify that `active_terminal` supplies a directory and `shell_history` records provenance;
neither selects a terminal process. The model still chooses `terminal:true` and writes the data
transformation. **21 application/error checks + 38 shell/capture checks (59 total)** and Ruff passed.
See the [Order 88 report](archive/all-holo-order88-command-usage-feedback-retest-20260913.md).

Agent attempt **67**, condition `holo31-all-roles-order88-command-usage-feedback-retest-20260913-v1`,
started `2026-09-13T15:21:15.341744+00:00`, supervisor PID **52069** / session **68338**, worker PID
**52140** (started `15:21:23.321003 UTC`), selected orders `[88]`, existing frozen validation `ok`.
Source frozen at `15:20:20.724538 UTC`:
`29e3e75b0ee0acca6eb7afc323789492554f529a2692e814edd7fbc3f9dd2315`
(529 files / 81,304,516 bytes). Config SHA-256:
`10b11fbe0cebed70365da5a08af0aec4d841ca347e4169ff6e6e6943ee9d1d2b`.
Original worker-04 Holo1 pairing uses direct `http://192.168.0.224:8002/v1`, both thinking/T0.8 roles,
top_k 7, existing 100/50 steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests
remain frozen through supervisor exit. The independent row-flattening mistake still needs correct
model-authored logic; error clarity alone does not establish task recovery.

Only **Order 88** is retesting/running. Counts: **25 isolated PASS, 17 skips, 67 Agent attempts,
42/94 processed and 51 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control, new gate or extra episode.

## 2026-09-13 15:17 UTC Order 87 offline reference-mismatch skip; next Order 88

Order **87** is skipped offline without source changes or a new Agent attempt. The preserved scorer
reproduces **0.8438601849044152** by comparing only the first grayscale frame after resizing. Actual
conversion follows the requested interval with approximately **5 seconds / 75 frames**, while the
reference has **0.3 seconds / 3 frames** and a different canvas. That mismatch does not establish a
reusable native conversion bug. Omitted requested GIMP use remains a real instruction residual but is
not directly tested by this scorer. Preserve the original non-unit score; do not tune timestamps/canvas/
palette to the reference, change thresholds or repeat an unchanged run. See the
[Order 87 skip report](archive/all-holo-order87-reference-mismatch-skip-20260913.md).

Counts: **25 isolated PASS, 17 skips, 66 Agent attempts and 42/94 processed**. Actual next queue position
**43 / Order 88**, multi-app task `3680a5ee-6870-426a-a997-eba929a0d25c`, is current/diagnosing, with
**51 pending** behind it. Its [preserved triage](../experiments/work/all-holo-order88-triage-20260912.md)
separates model-authored CSV row flattening from omitted explicit terminal mode; command/error contracts
will be inspected before a repair or replay. No Order 88 episode has launched. Original **95/189** and
baseline pointer remain unchanged; no regression/control or new gate.

## 2026-09-13 15:15 UTC Order 82 completes all 21 ranges and recovers PASS; next Order 87

Attempt **66** finalized `2026-09-13T15:13:24.055152+00:00` as original-evaluator **passed / reward 1**,
53 steps / 1151.909 seconds, `agent_done`, two completion rejections. Supervisor **61444** / session
**46620** and worker **61456** exited **0**, both PIDs are gone, and both final integrity records are
`ok` with unchanged source/config. The evaluator loaded only after the episode. Results SHA-256:
`eaf1f6fb8c2cc8cb2e7ff8448e55344604365734c1323c4c1a1bbb9f69b8692f`.

The model adopted combined current-format filtering from step **15** and completed **21 distinct
successful range edits**. Step **50** found zero remaining old-size italic matches, **51** saved,
**52** read back all italic text, and done **53** was accepted. Earlier completion proposals **18/32**
were rejected by the existing readback rule and work resumed. The report also records the prelaunch
five filter checks, synthetic remaining-filter example, 67 native-reference tests and Ruff passing.
This is one observed isolated recovery; serving/sampling and cumulative source differences prevent
a wording-only causality claim. See the
[Order 82 report](archive/all-holo-order82-current-format-filter-retest-20260913.md).

Counts now **25 isolated PASS, 16 skips, 66 Agent attempts and 41/94 processed**. Actual next queue
position **42 / Order 87**, multi-app task `2fe4b718-3bd7-46ec-bdce-b184f5653624`, is current/diagnosing,
with **52 pending** behind it. Its [preserved triage](../experiments/work/all-holo-order87-triage-20260912.md)
records non-unit reward **0.8438601849044152**, reference/output first-frame differences and separate
omitted GIMP use; it does not demonstrate a reusable transcoding defect. No new condition or episode
has launched. Original **95/189** and baseline pointer remain unchanged; no regression/control or new gate.

## 2026-09-13 14:54 UTC Order 82 current-format filter usage replay running

The existing `text.find` description now shows a generic combined current-format example and copying
one complete returned paragraph index, start/end offsets and `matched_text` into `text.set_format`.
This lets the model search an observed old property alongside style so completed ranges can stop
matching. The model still chooses every property, value, range and action; native/schema/validation/
context/gates are unchanged. No operator or schema-health probe accompanies this description-only
change. See the [Order 82 report](archive/all-holo-order82-current-format-filter-retest-20260913.md).

Agent attempt **66**, condition `holo31-all-roles-order82-current-format-filter-retest-20260913-v1`,
started `2026-09-13T14:53:58.925441+00:00`, supervisor PID **61444** / session **46620**, worker PID
**61456** (started `14:54:06.996971 UTC`), selected orders `[82]`, existing frozen validation `ok`.
Source frozen at `14:49:30.197923 UTC`:
`02c7f038e366f2192ea891584321632275c1f0f6a79c2bb79b3b07911fe77229`
(528 files / 81,299,590 bytes). Config SHA-256:
`87ce98c103a69b73337d9efdda23c369bb8516b577f703aea551c88451add989`.
Original worker-12 Holo2 pairing runs directly at `http://192.168.0.138:8001/v1`, both thinking/T0.8
roles, top_k 7, existing 100/50 steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor.
Source/tests remain frozen through supervisor exit. Original main temperature was 0; current sampling,
direct/serial serving and cumulative source differences prevent a pure wording-ablation claim.

Only **Order 82** is retesting/running. Counts: **24 isolated PASS, 16 skips, 66 Agent attempts,
40/94 processed and 53 pending**. Original **95/189** and baseline pointer remain unchanged;
no regression/control, new gate or further full run.

## 2026-09-13 14:46 UTC Order 79 bounded unresolved skip; next Order 82

Attempt **65** finalized `2026-09-13T14:44:50.111342+00:00` as **interrupted / unscored**, reward null,
14 steps / 324.127 seconds, zero completion rejections. Supervisor **33208** / session **13270** exited
**130**, worker **33236** exited **0**, both PIDs are gone. Worker final integrity is `ok`, with
unchanged config `15e22d29…` and source `c050f123…`; supervisor final integrity remains **null**.
No evaluator loaded. Results SHA-256:
`e661b7b766c664b6cd966ade771d6cb27521ab214a18af2f06dee9a851cb6372`.

Actual request **1** includes all new descriptions and request **9** includes the exact new native
source guidance. Bookmark **4** still targets the destination; precheck **8** preserves the marker.
Numbering **11/14** uses paragraph 10 as both source and target; step 14's restart/start-1 arguments
remain invalid. No citation append or successful native reference occurs before the developer stop.
At the **two-affected-attempt checkpoint**, skip Order 79 unresolved. Retain the native preservation
repair, operator evidence and truthful usage/errors without a PASS-gain claim. Original scored-zero
and both interrupted/unscored retests remain distinct; this is not a deadline or impossibility claim.
See the [Order 79 report](archive/all-holo-order79-reference-source-repair-20260913.md).

Counts: **24 isolated PASS, 16 skips, 65 Agent attempts and 40/94 processed**. Actual next queue
position **41 / Order 82**, Writer task `e246f6d8-78d7-44ac-b668-fcf47946cb50`, is current/diagnosing,
with **53 pending** behind it. Its [preserved triage](../experiments/work/all-holo-order82-triage-20260912.md)
shows successful partial formatting with mixed range identities and repeated completed-target reads;
latest matches/errors were available. Inspect existing combined-format filtering and exact range-copy
usage before any replay. No Order 82 episode has launched. Original **95/189** and baseline pointer
remain unchanged; no regression/control or new gate.

## 2026-09-13 14:40 UTC Order 79 source/target usage and range feedback replay running

Existing descriptions and native-error guidance now distinguish the cited source from the display
destination: source bookmark/numbering belongs to the cited content; the destination need not be
numbered. Existing range-length errors now include supplied offsets, range/text lengths and existing
`text.find` coordinate-copy guidance. The same validation predicates decide rejection for
`bookmark.create`, `cross_reference.insert` and `text.set_format`; no range is rewritten, and zero-length
bookmark/insertion ranges remain valid. **5 range-feedback + 67 native-reference tests**, **9 discovery
checks**, updated public-description checks and Ruff passed. Native behavior, schema shape, observation
priority/budget and gates are unchanged. No extra operator or endpoint probe was issued. See the
[Order 79 report](archive/all-holo-order79-reference-source-repair-20260913.md).

Agent attempt **65**, condition `holo31-all-roles-order79-reference-usage-feedback-retest-20260913-v1`,
started `2026-09-13T14:39:15.200174+00:00`, supervisor PID **33208** / session **13270**, worker PID
**33236** (started `14:39:22.907942 UTC`), selected orders `[79]`, existing frozen validation `ok`.
Freeze time `14:38:28.251907 UTC`; source SHA-256:
`c050f123ec846cb81fdb9126d3798d78819f1aa80d961ebc724d9a62d8623322`
(528 files / 81,299,258 bytes). Config SHA-256:
`15e22d29fbda73bb2e02b3d62b3354acd8e3ae0fcd2863072dd39551c8a7f309`.
The direct Holo2 origin `http://192.168.0.138:8001/v1`, both thinking/T0.8 roles, top_k 7 and existing
100/50 steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor match attempt 64. Source/tests
remain frozen through supervisor exit.

Additional preserved attempt-64 evidence: two `StructuredToolProtocolError` events before step 13
reported omitted `text.find.case_sensitive`; both recovered. They are not terminal protocol failures
and are outside this source/target-guidance hypothesis. Only **Order 79** is retesting/running, on its
second affected Agent attempt. Counts: **24 isolated PASS, 15 skips, 65 Agent attempts, 39/94 processed
and 54 pending**. Original **95/189** and baseline pointer remain unchanged.

## 2026-09-13 14:35 UTC Order 79 attempt 64 interrupted; source/target usage and range errors remain confusing

Attempt **64** finalized `2026-09-13T14:34:33.834566+00:00` as **interrupted / unscored**, reward null,
24 steps / 584.98 seconds, zero completion rejections. Developer stop followed repeated source/target
confusion and opaque offset errors; it was not a new user stop, scored failure or deadline. Supervisor
**2036** / session **48551** exited **130**, worker **2048** exited **0**, both PIDs are gone. Worker
final integrity is `ok` with unchanged source `b2544175…`; supervisor final integrity remains **null**.
No evaluator loaded. Results SHA-256:
`27ab85480081895ac757d2ff5d33af9fcba9a3e610b3ae952afc625c2fbfe4c9`.

Citation append **10** succeeds, but bookmarks **3/20** target the destination. Native
`SOURCE_NOT_NUMBERED` at **5/23** preserves the marker and delivers error feedback. Invalid numbering
**7/12** and guessed bookmark ranges **18/21** recur; no reference completes. Some actual requests
lose paragraph 20/21 numbering fields, but retain valid source **22**, which model reasoning **15**
recognizes. Missing numbering fields alone therefore do not explain the repeated source/target error.
See the [Order 79 report](archive/all-holo-order79-reference-source-repair-20260913.md).

**Order 79 stays current/repairing, not skipped.** The next small change clarifies existing source/target
and numbering usage and adds observed bounds/details to the existing range error, retaining its validation
decision. Focused checks precede a new current-only condition; no second operator run, new gate or
automatic source/offset selection. Counts remain **24 isolated PASS, 15 skips, 64 Agent attempts,
39/94 processed and 54 pending**. Original **95/189** and baseline pointer stay unchanged.

## 2026-09-13 14:25 UTC Order 79 reference source verification completes; Agent attempt 64 running

Operator `all-holo-order79-reference-source-operator-20260913-v1` completed at
`2026-09-13T14:23:41.122781+00:00`, 389.006 reported seconds. Session **89724** exited **0** and PID
**52137** is gone. **9 API calls** yielded **8 successes plus 1 expected `SOURCE_NOT_NUMBERED`**.
Independent inspection confirmed the marker remained intact after that error. Applying observed native
numbering to the synthetic source then let **identical reference arguments** create a native
`GetReference` field. Final readback matched original prefix + native presentation + original suffix,
with source text unchanged. The ordinary UndoManager success path was exercised; forced rollback after
a later insertion failure is covered by fake-native tests, not a deliberately forced live failure.

The operator's original scorer **0** is expected for synthetic-only targets and adds no Agent attempt or
PASS. Source `b2544175…` remained unchanged after exit. Results SHA-256:
`cb2500a482e3533dbeb07d75379d26ee2122d8c42dc8e40095f436b8b0c2c6c5`;
metadata SHA-256: `170a28f475d803d27360ddc3e5d2261d8acbf2e75de526b8127421a2e429766b`.
Separate schema health returned **HTTP 200**, expected `finish_reason: length` with one output token;
request SHA-256 `99345e22981017fe130e5ec66370ba17f96a4e42393da5ad80253f5ed4e8d4c4`, response SHA-256
`e5d87d69de040544d5d128c33fc2954c3144560f792d5ae5e89351ef411be8e2`. This confirms schema acceptance,
not completed tool generation, and issued no VM/tool actions. See the
[Order 79 report](archive/all-holo-order79-reference-source-repair-20260913.md).

Agent attempt **64**, condition `holo31-all-roles-order79-reference-source-retest-20260913-v1`, started
`2026-09-13T14:24:37.492372+00:00`, supervisor PID **2036** / session **48551**, worker PID **2048**
(started `14:24:45.695793 UTC`), selected orders `[79]`, existing frozen validation `ok`. Config SHA-256:
`122642598d01f527104a9f09323f8fc8955f55105822239bd76e0115d2489918`.
Same source `b25441756b8edb9fc93bdcbc2f976e6e54672dc548e249227522579ac7ad8d7c`
(527 files / 81,296,210 bytes), frozen `14:16:23.499622 UTC`, remains frozen through supervisor exit.
Original worker-09 Holo2 pairing uses direct `http://192.168.0.138:8001/v1`, both thinking/T0.8 roles,
top_k 7 and existing 100/50 steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor.

Only **Order 79** is retesting/running. Counts are **24 isolated PASS, 15 skips, 64 Agent attempts,
39/94 processed and 54 pending**. Original **95/189** and baseline pointer are unchanged; no
regression/control, new gate or further full run.

## 2026-09-13 14:18 UTC Order 79 selected-source reference repair enters operator-only verification

The owning reference Adapter now checks its explicitly selected bookmark's native numbering before
numeric insertion. If later refresh/verification fails, a native UndoManager context restores only this
insertion's edit, preserving formatting and prior work, or reports the actual remaining state. Generic
catalog tags improve discovery of existing numbering/bookmark source tools; they select no source or
arguments. **173 focused tests** and Ruff for five changed Python files passed. See the
[Order 79 repair report](archive/all-holo-order79-reference-source-repair-20260913.md).

Operator experiment `all-holo-order79-reference-source-operator-20260913-v1` started at
`2026-09-13T14:17:05.713182+00:00`, session **89724** / PID **52137**. Its fresh guest is initializing
with the first inspect queued. Source frozen at `14:16:23.499622 UTC` is
`b25441756b8edb9fc93bdcbc2f976e6e54672dc548e249227522579ac7ad8d7c`
(527 files / 81,296,210 bytes). Source/tests remain frozen through process exit. Bound: **10 public
API calls / 600 seconds / 30 GiB floor**, stop on first unexpected result. The deliberately unnumbered
synthetic source should produce `SOURCE_NOT_NUMBERED` without consuming its marker; after applying
observed native numbering, the same explicit insertion should resolve. The harness makes **zero model
requests** and any post-finish evaluator output is non-Agent evidence.

A separate harmless one-token request checks the complete actual top-7 reference schemas during setup;
it issues no VM/tool actions, is not an operator run or Agent attempt, and has no result recorded yet.
**No Agent attempt 64 has launched.** Order 79 is current/operator_validation; counts remain **24 isolated
PASS, 15 skips, 63 Agent attempts, 39/94 processed and 54 pending**. Original **95/189** and baseline
pointer are unchanged; no regression/control, new gate or further full evaluation.

## 2026-09-13 14:08 UTC Order 78 native conversion and paragraph delivery recover PASS; next Order 79

Agent attempt **63** finalized at `2026-09-13T14:07:05.192669+00:00` as original-evaluator **passed /
reward 1**, 7 steps / 229.024 seconds, `agent_done`, one completion rejection. Supervisor **24854** /
session **46598** and worker **24917** exited **0**, both PIDs are gone, and final/worker integrity are
`ok`. Config `704adf63…` and source `15e75d3d…` remain unchanged through exit. The evaluator loaded only
after the episode. Results SHA-256:
`5e7cfd77d41f664afd0dcfe5777a4c0c6363ef9cc3f2336b36347e9a5818fb6c`.

Actual requests **3 and 4** preserve all **5 source paragraphs, 293 characters and 40 NBSPs** exactly.
Raw model call arguments, parsed arguments and executed payload agree on the observed range **4–8**
and comma delimiter. Step **4** performs native **5 × 4** conversion; done **5** receives a truthful
missing-readback rejection, inspect **6** supplies fresh state and done **7** is accepted. This verifies
one Agent recovery from the native capability and paragraph-delivery repairs. Original scored-zero,
interrupted attempt 62 and both non-Agent operator outcomes remain preserved separately. See the
[Order 78 report](archive/all-holo-order78-native-text-to-table-repair-20260913.md).

Counts now **24 isolated PASS, 15 skips, 63 Agent attempts and 39/94 processed**. Actual next queue
position **40 / Order 79**, Writer task `adf5e2c3-64c7-4644-b7b6-d2f0167927e7`, is current/diagnosing;
**54 pending** remain behind it. Start with its
[preserved reference-insertion triage](../experiments/work/all-holo-order79-triage-20260912.md): validate
the selected native source and preserve the destination on this insertion's own failure, keeping model
selection intact. No Order 79 episode is launched. Original **95/189** and baseline pointer remain
unchanged; no regression/control, new gate or additional full run.

## 2026-09-13 14:04 UTC Order 78 paragraph-text observation repair launched as Agent attempt 63

The existing Writer observation path now prioritizes exact paragraph index, `text_length` and `text`
before optional formatting. The **5000-character budget**, sanitization, raw trace, native conversion,
public schema and gates are unchanged; long text remains explicitly partial. Offline recreation of
actual requests **3, 4 and 7** now retains all **5 short source paragraphs and 40 NBSP characters**.
**9 new actual-message tests** plus **161 existing relevant checks** and Ruff passed. These cover
ordinary/recovery direct and forwarded requests, Unicode/spacing, explicit long-text truncation and
observed nulls. No extra operator run or endpoint/schema probe was needed. See the
[Order 78 report](archive/all-holo-order78-native-text-to-table-repair-20260913.md).

Agent attempt **63**, condition `holo31-all-roles-order78-paragraph-text-observation-retest-20260913-v1`,
started `2026-09-13T14:03:00.158433+00:00`, supervisor PID **24854** / session **46598**, worker PID
**24917** (started `14:03:08.120175 UTC`), selected orders `[78]`, existing frozen validation `ok`.
Freeze time is `14:02:22.550371 UTC`; source SHA-256:
`15e75d3dd78bc75cf33b444a1441dfabeb28e4371fda1741836219d9fcfa1579`
(526 files / 81,278,748 bytes). Config SHA-256:
`704adf63a85cb4176cf5c10120ac42bbe7faf14b8a48047b60bd91f7e306bf21`.
The paired direct Holo2 origin `http://192.168.0.138:8001/v1`, both thinking/T0.8 roles, top_k 7,
100 global/50 local steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor match attempt 62.
Against the original full run, main temperature remains changed from 0 to 0.8, with direct/serial
serving and cumulative source differences.

Only **Order 78** is retesting/running, at its second affected Agent attempt. Source/tests remain frozen
through supervisor exit. Counts: **23 isolated PASS, 15 skips, 63 Agent attempts, 38/94 processed and
55 pending**. Original **95/189** and baseline pointer are unchanged; no regression/control or new gate.

## 2026-09-13 13:58 UTC Order 78 Agent attempt 62 interrupted after demonstrated paragraph-text delivery loss

Attempt **62** finalized at `2026-09-13T13:56:52.520552+00:00` as **interrupted / unscored**, reward
null, 14 steps / 382.631 seconds, zero completion rejections. The developer sent SIGINT to supervisor
PID **60638** / session **37151** after a concrete observation defect appeared; this was not a new user
stop request, scored failure or deadline. Supervisor exited **130**, worker **60675** exited **0**,
and both PIDs are gone. Worker final integrity is `ok` with unchanged source `e3f82d0e…`; supervisor
final integrity remains **null**, as no final record was emitted. No evaluator loaded before or after
the episode. Results SHA-256:
`c163c9870bce4a72c9409a439dfa9bb55515d589ec5a10afd5789e2390f2c35c`.

The new conversion API reached the model, but complete raw Adapter paragraph text lost its row-text
fields in actual model requests **3, 4 and 7**. The model made **13 inspections** and one invalid
conversion over paragraphs 4–14; unequal column counts correctly rejected that range. This establishes
a separate observation serialization defect, not native character loss. The next smallest repair gives
Writer paragraph text appropriate priority in the existing observation path, then uses focused checks
and a new current-task-only condition. See the
[Order 78 report](archive/all-holo-order78-native-text-to-table-repair-20260913.md).

**Order 78 stays current/repairing**, with no skip or next attempt registered. Source freeze is released
after process exit; finalized artifacts remain immutable. Counts stay **23 isolated PASS, 15 skips,
62 Agent attempts, 38/94 processed and 55 pending**. Original **95/189** and baseline pointer are
unchanged; no regression/control episode or new gate is added.

## 2026-09-13 13:50 UTC Order 78 terminal conversion verified; Agent attempt 62 running

The native compatibility fix accepts exactly one obligatory empty terminal paragraph only after actual
end-of-body conversion, with the new table and empty paragraph as the final body objects. Exact prior
outside content and cell comparison remain intact; no trimming or completion-gate change. **15 focused
native tests** and Ruff passed. Fresh operator experiment
`all-holo-order78-text-to-table-end-operator-20260913-v2` then completed all **4 API calls** successfully:
synthetic append, inspect, conversion of observed paragraphs 43–44 with `|`, and independent readback of
all **6 exact cells**. It started `13:45:53.547089 UTC`, completed `13:49:34.383165 UTC`, and reports
214.324 seconds. Session **46813** exited **0**; PID **51729** is gone. The expected operator scorer
**0** reflects a synthetic-only check that did not convert the real task source. Both operator runs are
non-Agent evidence and add no Agent attempt or PASS.

Operator v2 result SHA-256: `34065c81009250b00e6af7e275358fc2f9d68f6f8a14c05e92f28384ff845f9e`;
metadata SHA-256: `e8f28a203b87bc26097a271284e8e656c288cbff5c97fd7e63adacf8421b6143`.
Its source was revalidated unchanged after exit. See the
[Order 78 report](archive/all-holo-order78-native-text-to-table-repair-20260913.md).

Agent attempt **62**, condition `holo31-all-roles-order78-native-text-to-table-retest-20260913-v1`,
started at `2026-09-13T13:50:18.858555+00:00`, supervisor PID **60638** / session **37151**, worker
PID **60675**, selected orders `[78]`, existing frozen validation `ok`. Source was frozen at
`13:45:06.699437 UTC` and remains unchanged from operator v2:
`e3f82d0e36c0cdb6296440034e9dd965321112195403cd7f240ce107eefa7f0b`
(525 files / 81,271,703 bytes). Config SHA-256:
`638c1838c39b31bd370197ce65c94fa78145bbc9fb024a2364ec42a91cf57852`.
Original worker-08 Holo2 pairing is retained on direct `http://192.168.0.138:8001/v1`, both roles
thinking/T0.8, top_k 7, existing 100 global/50 local steps, one same-VM restart, 1800 Agent seconds and
30 GiB floor. Original main temperature was 0, GUI 0.8; current sampling, direct/serial serving and
cumulative source differ, so this is not a pure API ablation.

Only **Order 78** is retesting/running. Source/tests remain frozen through supervisor exit. Counts are
**23 isolated PASS, 15 skips, 62 Agent attempts, 38/94 processed and 55 pending**. Original **95/189**
and baseline pointer stay unchanged; no regression/control, new gate or additional full evaluation.

## 2026-09-13 13:43 UTC Order 78 operator conversion preserves characters; terminal-paragraph receipt needs compatibility

Operator-only experiment `all-holo-order78-text-to-table-operator-20260913-v1` completed at
`2026-09-13T13:42:05.637097+00:00`, after starting at `13:31:48.430600 UTC`; reported duration is
610.809 seconds. Tool session **42897** exited **0**, PID **24692** is gone. Six public API calls were
issued; five succeeded. Finish followed the first unexpected native result near the 600-second target,
with teardown ending afterwards. The source seal was recomputed unchanged as
`efe0ead6b78641a26844300a0b39d746637e454a65caf803e30d25cdcd08d427`
(525 files / 81,268,299 bytes), releasing the freeze only after process exit.

Command 2 converted observed paragraphs 4–8 natively into **Table14, 5 × 4**, preserving all **20 cells
and 40 NBSP characters**. Independent read 3 matched exactly. Synthetic append/inspect 4–5 succeeded;
terminal-range conversion 6 produced the exact **2 × 3** cells but returned `VERIFICATION_FAILED` for
`outside_text_unchanged: false`. Offline persisted DOCX contains all 38 expected outside paragraphs plus
one obligatory empty terminal paragraph. A small compatibility fix for that native document structure is
underway; no content reconstruction or new completion gate is warranted. See the
[Order 78 report](archive/all-holo-order78-native-text-to-table-repair-20260913.md).

The original evaluator ran only after finish and returned **failed / 0** with the extra synthetic table.
This is **non-Agent capability evidence**, with zero model requests; it adds neither an Agent attempt nor
a PASS. Results SHA-256: `620af0e7fabc919719e5190cd756970701da38580a3f410d9454b8cd03e60d8e`;
metadata SHA-256: `7eee2f608c6cce9625ad2fdd4f9cd9cee113db20bd160378bfcaedc481eba082`.

Order 78 remains current/repairing, Agent attempt not started. Counts stay **23 isolated PASS, 15 skips,
61 Agent attempts, 38/94 processed and 55 pending**. Original **95/189** and baseline pointer remain
unchanged. A later live attempt needs its own seal and fresh guest.

## 2026-09-13 13:32 UTC Order 78 native conversion implemented; operator-only validation running

Generic `table.convert_text` takes an explicitly observed paragraph range and delimiter, then performs
one native conversion preserving source characters. It does not retype cell contents or infer selection;
outside text/tables are checked and save/readback remain separate public calls. The delimiter's native
single-BMP-character constraint is part of this action contract, not a new evaluation gate. **156 focused
tests** and Ruff for seven Python files passed. See the
[Order 78 repair report](archive/all-holo-order78-native-text-to-table-repair-20260913.md).

A synthetic full-schema health request to direct Holo2 returned HTTP 200 with **max_output_tokens 1**
and expected `finish_reason: length`. This proves schema acceptance only, not valid tool generation,
native execution or an Agent result. It issued no Adapter/VM action.

The existing **operator_validation** harness is now running for current Order 78 on a fresh guest,
tool session **42897**, experiment `all-holo-order78-text-to-table-operator-20260913-v1`, registered/frozen
`2026-09-13T13:30:57.374498+00:00`. Source SHA-256:
`efe0ead6b78641a26844300a0b39d746637e454a65caf803e30d25cdcd08d427`
(525 files / 81,268,299 bytes). Scope is at most **8 public API calls / 600 seconds**, no model requests,
and a **30 GiB** floor. The native command runs inside the Adapter; host GUI-action count is zero.
Source/tests stay frozen through operator exit. Condition and metadata label this **non_agent** and
**non_promotable**; any later operator evaluator output cannot count as an Agent PASS.

Order 78 remains current in operator validation. **No Agent attempt 62 has launched**. Counters stay
**23 isolated PASS, 15 skips, 61 Agent attempts, 38/94 processed and 55 pending**. Original **95/189**
and baseline pointer remain unchanged; any future Agent replay needs its own condition and fresh guest.

## 2026-09-13 13:15 UTC Order 77 explicit scope usage delivered but scores 0; bounded skip to Order 78

Attempt **61** finalized at `2026-09-13T13:14:02.888949+00:00` as original-evaluator **failed**, reward
**0**, 13 steps / 591.086 seconds, `agent_done`, one completion rejection. Supervisor PID 33485 /
tool session 14417 and worker PID 33520 exited **0**, both gone; final and worker integrity are `ok`.
The evaluator loaded only after the episode and source freeze is released. Results SHA-256:
`19e47497e74f08e8f52cc2aba5abaa990be09611a8a8d900ff47e7ec173c93cc`.

The actual first request includes all new scope guidance. Error 6's stale index is corrected by split 9
on index 4; save 10 then done 11 gets a truthful missing-readback rejection. Inspect 12 reads ten paragraphs,
including the remaining right text at index 6, but done 13 accepts unfinished work with no more edits.
One **APIConnectionError at step 2 recovered**; it is not a terminal transport failure. See the
[second Order 77 report](archive/all-holo-order77-split-source-scope-retest-20260913.md).

**Order 77 is skipped unresolved** at the two-affected-attempt checkpoint, preserving original and both
retest scored-zero outcomes. Retain accurate usage without a PASS-benefit claim; no further demonstrated
framework defect justifies another variant. Actual next queue entry **39 / Order 78**, Writer task
`936321ce-5236-426a-9a20-e0e3c5dc536f`, is current/diagnosing from its
[preserved triage](../experiments/work/all-holo-order78-triage-20260912.md), with no new episode. Counts:
**23 isolated PASS, 15 skips, 61 attempts, 38/94 processed and 55 pending**. Original **95/189** and
baseline pointer stay unchanged; no new gate, regression/control or full evaluation is added.

## 2026-09-13 13:04 UTC Order 77 split-source scope usage clarification launched

Only `writer_adapter/tool_manifest.py` split usage changed: after a split the old index names the left
part, while original selected text spans the returned parts; inspecting only the old index omits remaining
right text. Native API/schema/projection/defaults/completion are unchanged, with no scope tracker, target
injection or new gate. The existing bounded Writer module passed **41 tests**, plus Ruff and diff checks;
no new tests were added. Actual attempt-60 requests already delivered the full 253-character remainder,
right index 6 and unchanged-text evidence, so this is not lost-feedback repair. See the
[second Order 77 report](archive/all-holo-order77-split-source-scope-retest-20260913.md).

Attempt **61**, condition `holo31-all-roles-order77-split-source-scope-retest-20260913-v1`, started at
`2026-09-13T13:03:57.821782+00:00`, supervisor PID **33485** / tool session **14417**, worker PID **33520**,
selected orders `[77]`, existing frozen validation `ok`. Freeze time **13:02:36.365503 UTC**; config SHA-256:
`4bb5bafbadd391d1b355694520148a4dd878698e51a95954c159b56fd92bc558`.
Source SHA-256:
`ef411b18a8d0686166dc75f401d6db5d4543e878544a6394ed5c0261a4940ac7`
(523 files / 81,249,359 bytes). Both thinking Holo roles remain direct/serial on original Holo1 at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8, top_k 7, with existing 100 global/50 local
steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through supervisor exit.

Only **Order 77 is retesting/running**, at its second affected attempt. The model still chooses all
boundaries and current indices; use the two-attempt checkpoint if full guidance leaves the same scope
error without a new defect. Counts: **23 isolated PASS, 14 skips, 61 attempts, 37/94 processed and
56 pending**. Original **95/189** and baseline pointer remain unchanged; no regression/control, new gate
or full evaluation is added.

## 2026-09-13 13:01 UTC Order 77 follows current split indices but leaves scope unfinished

Attempt **60** finalized at `2026-09-13T13:00:03.907767+00:00` as original-evaluator **failed**, reward
**0**, 11 steps / 328.651 seconds, `agent_done`, zero completion rejections. Supervisor PID 12346 /
tool session 38721 and worker PID 12421 exited **0**, both gone; final and worker integrity are `ok`.
The evaluator loaded only after the episode and source freeze is released. Results SHA-256:
`ad522cb7eabd3692d0f82709020af4365de1d8690f96ffad4388867ff909139a`.

Splits **2/3/4 correctly follow indices 0/2/4**, preserving partial progress over the original stale-index
behavior. Four remaining sentences nevertheless stay together. Premature done 9 makes terminal review
continue with inspect 10 of only paragraphs 0/1, then done 11 is accepted. This review continuation is not
a completion-gate rejection. See the [Order 77 report](archive/all-holo-order77-current-setting-retest-20260913.md).

**Order 77 remains current/repairing**. Root plans only a small split-usage clarification: after a split,
the original selected text spans returned parts and the old index names just the left part. The model
still chooses each boundary; no native API/gate change or automatic segmentation is planned. Focused
checks and a new seal precede a second bounded episode; no attempt 61 or skip is registered. Counts remain
**23 isolated PASS, 14 skips, 60 attempts, 37/94 processed and 56 pending**. Original **95/189** and
baseline pointer stay unchanged.

## 2026-09-13 12:55 UTC Order 77 current-setting sentence-split replay launched

Original actual requests already delivered the complete 577-character paragraph, new right-paragraph
indices and ordered-list split usage. The model nevertheless reused stale indices, repeated completed
boundaries and guessed nonmatching literals. No new native/API/feedback defect is established, so this
attempt carries existing source without an Order 77 code/test change. Main temperature is **0.8 versus
original 0**, while GUI remains 0.8; direct/serial serving and cumulative source also differ. See the
[Order 77 report](archive/all-holo-order77-current-setting-retest-20260913.md).

Attempt **60**, condition `holo31-all-roles-order77-current-setting-retest-20260913-v1`, started at
`2026-09-13T12:54:23.866172+00:00`, supervisor PID **12346** / tool session **38721**, worker PID **12421**,
selected orders `[77]`, existing frozen validation `ok`. Freeze time **12:53:10.565729 UTC**; config SHA-256:
`cfd621db1a010fa20d66a51654f08d056a0ae771d9087d25ad2c4d209b13165f`.
Unchanged source SHA-256:
`eb71ffee4c2af69144e22a969a457d8ffbc342d7670fad548cb1054603b57d46`
(523 files / 81,249,107 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, top_k 7, with existing 100 global/50 local steps, one same-VM restart,
1800 Agent seconds and 30 GiB floor. Prior focused checks remain relevant; no repeated test campaign.
Source/tests remain frozen through supervisor exit.

Only **Order 77 is retesting/running**. Model-selected anchors, current indices and saved readback determine
the outcome; persistent fully observed errors without a new defect lead to bounded skip. Counts:
**23 isolated PASS, 14 skips, 60 attempts, 37/94 processed and 56 pending**. Original **95/189** and baseline
pointer remain unchanged; no new gate, regression/control or full evaluation is added.

## 2026-09-13 12:52 UTC Order 76 compact delivery verified, bounded unscored skip; Order 77 selected

Attempt **59** ended at `2026-09-13T12:50:53.676069+00:00` as **interrupted/unscored**, 12 steps /
459.288 seconds, no completion rejection, evaluator or reward. Supervisor PID 54525 / tool session
92132 exited **130**, verified by root; worker PID 54619 exited **0**, revalidation `ok`. Both are gone
and source freeze is released. Supervisor `metadata.final_integrity` is **null**, not a scored seal.
Results SHA-256:
`c104d0684da22ac9c3bd9a92e9abf450d93f380c87348c201a424cbc27e401df`.

Actual requests 4/5 each retain the full **2542-byte** projected hint, all 55 exact native rows and complete
legend; reconstruction matches the **5220-byte** native result. Byte reduction is established, while
the model still uses internal letters, selects more cells than its reasoning identifies and overwrites
colors. Late step 11 repeats a red row and step 12 scrolls. No new projection/native/feedback defect is
demonstrated. See the [second Order 76 report](archive/all-holo-order76-compact-table-observation-retest-20260913.md).

**Order 76 is skipped unresolved** at the two-attempt checkpoint. Preserve original transport failure,
attempt 58 scored 0 and attempt 59 unscored interruption. Keep the small generic compression for its
verified byte reduction without a PASS/classification-benefit claim. This developer stop before the
1800-second limit is not deadline exhaustion, evaluator 0 or proof of impossibility. The original main
temperature 0 versus current 0.8 provenance correction remains recorded; 59 versus 58 changes only hint shape.
Actual next queue entry **38 / Order 77**, Writer task `88fe4b2d-3040-4c70-9a70-546a47764b48`, is
current/diagnosing from its [preserved triage](../experiments/work/all-holo-order77-triage-20260912.md), with
no new episode. Counts: **23 isolated PASS, 14 skips, 59 attempts, 37/94 processed and 56 pending**.
Original **95/189** and baseline pointer remain unchanged; no new gate or full evaluation is added.

## 2026-09-13 12:50 UTC Order 76 comparison-provenance correction

The original full-189 condition has **main temperature 0**, confirmed by `protocol.temperature` and
worker-06 `metadata.temperature: 0.0`; original `protocol.gui_model.temperature` is **0.8**. Attempts
58 and 59 use **0.8 for both roles**. Any earlier implication that original main/GUI both used 0.8 is
incorrect: attempt 58 changes main sampling **0→0.8**, direct/serial serving and cumulative source, so
it is **not a pure transport ablation**. Attempt 59 relative to 58 changes only model-hint shape.

Immutable configs/results remain untouched, including attempt 58's ambiguous expected wording about
retaining thinking/T0.8. This correction is recorded in the host-only ledger and linked task reports.
Order 76 attempt 59 remains running; no terminal outcome or new episode is inferred. Counts remain
**23 isolated PASS, 13 skips, 59 attempts, 36 processed and 57 pending**; original **95/189** is unchanged.

## 2026-09-13 12:43 UTC Order 76 compact native table observation launched

Only the existing Writer `table.read` model-context projection changed: one `cell_fields` legend and
rows of exact native values preserve names/text/colors/order/coordinates; absent coordinates remain null.
Raw/native results, tool schemas, context budgets/algorithm and completion are unchanged. The two existing
focused modules passed **138 tests**, covering direct/forwarded/recovery delivery and bounded truncation;
Ruff for three Python files and scoped diff checks pass. A synthetic 60-cell payload shrank **5805→2352
characters** with values intact, which is not a model score. See the
[second Order 76 report](archive/all-holo-order76-compact-table-observation-retest-20260913.md).

Attempt **59**, condition `holo31-all-roles-order76-compact-table-observation-retest-20260913-v1`, started at
`2026-09-13T12:43:03.217985+00:00`, supervisor PID **54525** / tool session **92132**, worker PID **54619**,
selected orders `[76]`, existing frozen validation `ok`. Freeze time **12:42:02.464423 UTC**; config SHA-256:
`ff96793b0987a79a4c98a77f6901915f9a94f58ed66878de24772972d5160bda`.
Source SHA-256:
`eb71ffee4c2af69144e22a969a457d8ffbc342d7670fad548cb1054603b57d46`
(523 files / 81,249,107 bytes). Both thinking Holo roles remain direct/serial on original Holo1 at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8, top_k 7, with existing 100 global/50 local
steps, one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests freeze lasts through supervisor exit.

Only **Order 76 is retesting/running**, at its second affected attempt. Earlier delivery already included
all 55 cells, and compact positional rows have a readability tradeoff; model benefit is unproven. Use the
two-attempt checkpoint if complete delivery still leaves semantic errors. Counts: **23 isolated PASS,
13 skips, 59 attempts, 36/94 processed and 57 pending**. Original **95/189** and baseline pointer remain
unchanged; no regression/control, new gate or full evaluation is added.

## 2026-09-13 12:39 UTC Order 76 completes transport but scores 0; compact observation hypothesis remains current

Attempt **58** finalized at `2026-09-13T12:38:31.860182+00:00` as original-evaluator **failed**, reward
**0**, 16 steps / 946.78 seconds, `agent_done`, no completion rejections. Supervisor PID 13649 /
tool session 80596 and worker PID 13715 exited **0**, both gone; worker and supervisor final integrity
are `ok`. The evaluator loaded only after the episode; source freeze is released. Results SHA-256:
`8094c60f2abee3764a25591777ca1ffdb4593b062970e9225039b46ca5634ead`.

Actual requests 3–6 retain all 55 native cell identities/text/positions and complete guidance. Duplicate
action feedback reaches the model unchanged and raw color arguments match payload, but semantic color
mistakes and later overwrites persist. There is no terminal transport failure. **One zero-tool
`StructuredToolProtocolError` at step 8 recovered** to a GUI action; it is neither omitted from the record
nor counted as terminal protocol failure. See the
[Order 76 report](archive/all-holo-order76-direct-transport-retest-20260913.md).

**Order 76 remains current/repairing**. Root is changing only table-observation projection toward compact
field rows. Synthetic size reduction does not establish better classification, and positional fields have
a readability tradeoff. Focused projection checks and a new seal must precede any second episode; no
attempt 59, skip, native classifier, target correction or new gate is registered. Counts stay **23 isolated
PASS, 13 skips, 58 attempts, 36/94 processed and 57 pending**. Original **95/189** and baseline pointer
remain unchanged.

## 2026-09-13 12:23 UTC Order 76 direct-Holo1 transport recheck launched with normal seven-tool setting

Original worker 06 exhausted three proxy HTTP 524 attempts after 11 events; no scorer ran. Actual model
requests retain all **55 native table cells**, exact names/text/positions and complete first-character
guidance, with native read/color tools exposed. Model color submissions and viewport-relative cell
confusion are independent errors; no context loss or missing capability is demonstrated. No new source,
test, API, prompt or gate edit is introduced. See the
[Order 76 report](archive/all-holo-order76-direct-transport-retest-20260913.md) and
[host-only triage](../experiments/work/all-holo-order76-triage-20260913.md).

Attempt **58**, condition `holo31-all-roles-order76-direct-transport-retest-20260913-v1`, started at
`2026-09-13T12:22:31.753466+00:00`, supervisor PID **13649** / tool session **80596**, worker PID **13715**,
selected orders `[76]`, existing frozen validation `ok`. Freeze time **12:20:26.145839 UTC**; config SHA-256:
`e1710974f5037062bf9f02070252c025eb0b21f81c66c35f0c9605a1d38af2e7`.
Unchanged source SHA-256:
`15bd730bd250f56ab313358a243b2de558e243a58c578bd530a2726f1d8b1ec1`
(523 files / 81,246,478 bytes). Both thinking Holo roles use original Holo1 directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8. Normal **top_k 7** is restored;
Order 74's isolated top_k 12 is not propagated. Existing 100 global/50 local steps, one same-VM restart,
1800 Agent seconds and 30 GiB floor remain. Source/tests stay frozen through supervisor exit.

Only **Order 76 is retesting/running**. Transport completion and semantic task correctness will be
recorded separately; no launch PASS is claimed. Counts: **23 isolated PASS, 13 skips, 58 attempts,
36/94 processed and 57 pending**. Original **95/189** and baseline pointer remain unchanged; no other
episode, regression/control, new gate or full evaluation is added.

## 2026-09-13 12:19 UTC Order 74 actual exposure verified, interrupted unscored and bounded skip; Order 76 selected

Attempt **57** ended at `2026-09-13T12:18:51.295760+00:00` as **interrupted/unscored**, 26 steps /
946.765 seconds, four completion rejections, no evaluator or reward. Supervisor PID 38105 / tool session
99970 exited **130**, explicitly verified by root; worker PID 38154 exited **0**, revalidation `ok`.
Both processes are gone and source freeze is released. Supervisor `metadata.final_integrity` remains
**null**, not a scored seal. Results SHA-256:
`e9289f8a36fb9cdcf285b1f8889501309d31a08da37a3cca9b86516025f33a7b`.

Actual model requests now expose the complete clear-tool schema and truthful completion errors, correcting
attempt 56's exposure miss. The model still makes no document edit and repeatedly proposes count-only
completion, including rejected step 25. **Exposure is verified; live clear execution and task recovery
are not established.** See the [exposure report](archive/all-holo-order74-clear-tool-exposure-retest-20260913.md).

**Order 74 is skipped unresolved** after three distinct attempts and the explicitly justified third
exposure correction. This developer stop at about 15.8 minutes is before 1800 seconds, not evaluator 0,
deadline exhaustion or proof of impossibility. Preserve the original deadline and all three unscored
interruptions. Actual next queue entry **37 / Order 76**, Writer task
`8472fece-c7dd-4241-8d65-9b3cd1a0b568`, is current/diagnosing from its original transport failure, with
no new episode. Counts: **23 isolated PASS, 13 skips, 57 attempts, 36/94 processed and 57 pending**.
Original **95/189** and baseline pointer remain unchanged; no regression/control, new gate or full run
is added.

## 2026-09-13 12:03 UTC Order 74 configuration-only clear-tool exposure launched

Attempt **57** changes only existing `top_k` from **7 to 12** on identical source. Actual
`LiteAgent.selected_actions` plus `build_tools` offline verification includes the clear tool's complete
schema; actual request exposure and execution still require their own evidence. Additional ordinary
tools, including saved-file reading, may help or distract the model. No source/test/tag/ranking/gate or
target-selection changes occurred after attempt 56. See the
[exposure report](archive/all-holo-order74-clear-tool-exposure-retest-20260913.md).

Condition `holo31-all-roles-order74-clear-tool-exposure-retest-20260913-v1` started at
`2026-09-13T12:02:53.447744+00:00`, supervisor PID **38105** / tool session **99970**, worker PID **38154**,
selected orders `[74]`, existing frozen validation `ok`. Freeze time **12:02:11.368760 UTC**; config SHA-256:
`b34769b6cee7162864cb309fc683dc7900da800ae823258c6e6c05b49b0d9c45`.
Unchanged source SHA-256:
`15bd730bd250f56ab313358a243b2de558e243a58c578bd530a2726f1d8b1ec1`
(523 files / 81,246,478 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8, with existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through supervisor exit.

This third affected attempt is explicitly justified by the demonstrated tool-exposure miss at the
two-attempt checkpoint. Attempts 55/56 remain interrupted/unscored; no live clear execution is attributed
to them. If actual exposure leaves only model errors without a new demonstrated defect, record bounded
skip instead of further variants. Only **Order 74 is retesting/running**. Counts: **23 isolated PASS,
12 skips, 57 attempts, 35/94 processed and 58 pending**; original **95/189** and baseline pointer remain
unchanged. No other episode, regression/control, new gate or full evaluation is added.

## 2026-09-13 12:02 UTC Order 74 clear-tool exposure miss; explicit third-attempt extension prepared

Attempt **56** ended at `2026-09-13T11:59:25.748655+00:00` as **interrupted/unscored**, 24 steps /
654.359 seconds, three completion rejections, no evaluator or reward. Supervisor PID 6863 / tool session
73598 exited **130**, verified by root; worker PID 6893 exited **0**, revalidation `ok`. Both are gone and
source freeze is released. Supervisor `metadata.final_integrity` is **null**, not a scored seal.
Results SHA-256:
`711ab5da3ed6cc5aca9552c3d77884047fff52ea7ce82d804b1f303e1048dac5`.

**The new clear tool was not exposed to this model run.** Actual requests 14/15 include only the original
seven actions; current ranking places `paragraph.clear_text` at 12 and the model never searches. Earlier
commentary saying it was visible was inaccurate. Registration and native tests do not establish live
execution. Count-only completion attempts 18/20/22 are truthfully rejected for no task-changing action;
save 23 does not remove content. See the
[second Order 74 report](archive/all-holo-order74-explicit-paragraph-clear-retest-20260913.md).

**Order 74 remains current/preparing**. The two-attempt checkpoint is explicitly extended once for this
exposure miss: a new condition will change only existing `top_k` from 7 to 12 on unchanged source. Actual
`LiteAgent.selected_actions` plus `build_tools` offline verification confirms the complete clear schema
at 12; saved-file reading also returns to the initial selection. Extra tool choice may distract the model,
and no action or selector is forced. See the
[prospective exposure report](archive/all-holo-order74-clear-tool-exposure-retest-20260913.md).
No source/test/tag/ranking/gate change, new episode or attempt 57 is registered. Preserve both interrupted
attempts and original deadline. Counts stay **23 isolated PASS, 12 skips, 56 attempts, 35/94 processed and
58 pending**; original **95/189** and baseline pointer remain unchanged.

## 2026-09-13 11:49 UTC Order 74 explicit homogeneous paragraph clearing launched

Public `paragraph.clear_text` requires explicit raw indices and applies one clear operation to those
selected paragraphs. All targets resolve before mutation; native readback checks each selected text is
empty and paragraph count unchanged, then uses existing auto-save/file verification. It preserves
boundaries and model-chosen targets, with no predicates, ID lookup, deduplication rule, default-all
selection, new gate or scorer change. **11 native/public**, **93 context** and **41 bounded Writer**
tests passed, plus Ruff for seven Python files and scoped diff checks. See the
[second Order 74 report](archive/all-holo-order74-explicit-paragraph-clear-retest-20260913.md).

Attempt **56**, condition `holo31-all-roles-order74-explicit-paragraph-clear-retest-20260913-v1`, started at
`2026-09-13T11:48:20.167789+00:00`, supervisor PID **6863** / tool session **73598**, worker PID **6893**,
selected orders `[74]`, existing frozen validation `ok`. Freeze time **11:47:21.724508 UTC**; config SHA-256:
`baa8a711c8e5fa4b1f8828e85c5e25deb5ea85ca59318329c75a4177eab252f0`.
Source SHA-256:
`15bd730bd250f56ab313358a243b2de558e243a58c578bd530a2726f1d8b1ec1`
(523 files / 81,246,478 bytes). Both thinking Holo roles remain direct/serial on original Holo1 at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8, with existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests stay frozen through supervisor exit.

Final review corrects attempt 55's last actions: **steps 23–25 were `text.find`**, not inspection; no content
edit occurred across all 25 steps. The interrupted/unscored evidence remains preserved. Only **Order 74
is retesting/running**, at its second affected attempt. Tool availability does not establish correct
selection or recovery; GUI remains an alternative to the costly single-paragraph path. Counts:
**23 isolated PASS, 12 skips, 56 attempts, 35/94 processed and 58 pending**. Original **95/189** and baseline
pointer remain unchanged; no other episode, regression/control, new gate or full evaluation is added.

## 2026-09-13 11:43 UTC Order 74 interrupted unscored for a bounded explicit-selection capability change

Attempt **55** ended at `2026-09-13T11:42:29.145477+00:00` as **interrupted/unscored**, 25 steps /
714.202 seconds, zero completion rejections, no evaluator or reward. Supervisor PID 35842 / tool session
43691 exited **130**, verified by root; worker PID 35921 exited **0**, revalidation `ok`. Both are gone
and source freeze is released. Supervisor `metadata.final_integrity` remains **null**, not a scored seal.
Results SHA-256:
`a135a27288cb8148be9539f25aaaeedd08089d5caf237bc384063d0eb5ac48f1`.

Actual requests 11–13 expose `paragraph.replace_text` and retain every previously read paragraph 0–49;
request 16 also retains 90–99. The model's ten-line-memory claim is not a context overwrite. A separate
100-match search is compacted to 12 with a truthful marker; full visibility of all match texts is not
claimed. Final review confirms no edit in all 25 steps; the last steps 23–25 are `text.find`, not inspection.
Direct serving avoids original proxy stalls, but discovery/transport evidence is not recovery. See the
[Order 74 report](archive/all-holo-order74-deletion-discovery-retest-20260913.md).

**Order 74 remains current/repairing**. Root stopped at about 12 minutes to prepare a public homogeneous
`paragraph.clear_text` operation requiring explicit raw indices and retaining paragraph boundaries.
One-call-per-paragraph clearing can consume the 100-step budget after reads; GUI remains an alternative,
so no impossibility claim is made. No predicates, ID lookup, retained-record choice or default-all target
set is planned. Focused owning checks and a new seal must precede a second attempt; no attempt 56,
skip or new gate is registered. Counts stay **23 isolated PASS, 12 skips, 55 attempts, 35/94 processed
and 58 pending**. Original **95/189** and baseline pointer remain unchanged.

## 2026-09-13 11:31 UTC Order 74 generic text-deletion discovery launched

Existing Writer replacement actions now have generic `clear/delete/remove` discovery tags. Owning docs
explain deleting a literal with empty replacement and clearing selected paragraph text with `[""]` while
retaining its boundary. Native matching and every semantic selection remain model-owned; no record/ID/
deduplication keyword, new API, algorithm or gate is added. Offline initial seven tools now include
`paragraph.replace_text` at rank 5, displacing `document.read_file`, which remains searchable; ordinary
removal search finds both existing edit primitives. Existing bounded Writer module: **41 passed**, plus
Ruff for three Python files and scoped diff checks. See the
[Order 74 report](archive/all-holo-order74-deletion-discovery-retest-20260913.md).

Attempt **55**, condition `holo31-all-roles-order74-deletion-discovery-retest-20260913-v1`, started at
`2026-09-13T11:30:23.473310+00:00`, supervisor PID **35842** / tool session **43691**, worker PID **35921**,
selected orders `[74]`, existing frozen validation `ok`. Freeze time **11:29:22.446474 UTC**; config SHA-256:
`0b33dc6d29833fba1679188e6d3b0fffac0395dd8e6f5a075ec484890bdefa16`.
Source SHA-256:
`6739a74bea0011314a182d55f851d33291dcbb36fbad24b5b5b8ca6cd9acd291`
(522 files / 81,236,818 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8, with existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through supervisor exit.

The original episode only read complete input and suffered proxy latency; it never searched or edited.
Improved discovery does not establish correct selection or task recovery, and the initial read-tool change
is a recorded tradeoff. Only **Order 74 is retesting/running**. Counts: **23 isolated PASS, 12 skips,
55 attempts, 35/94 processed and 58 pending**. Original **95/189** and baseline pointer remain unchanged;
no other task episode, regression/control, new gate or additional full evaluation is added.

## 2026-09-13 11:24 UTC Order 65 interrupted unscored and bounded skip; Order 74 selected

Attempt **54** ended at `2026-09-13T11:23:12.826315+00:00` as **interrupted/unscored**, 23 steps /
870.528 seconds, zero completion rejections, no evaluator or reward. Supervisor PID 56274 / tool session
86850 exited **130**, verified by root; worker PID 56328 exited **0**, revalidation `ok`. Both are gone
and source freeze is released. Supervisor `metadata.final_integrity` is **null**, not a scored final seal.
Results SHA-256:
`bd2072ff67e6df12d16cca2c903ec04c39329b3d4f4cef1fc755954b968e900d`.

Actual requests 4/7/10 retain complete focused text, empty actual-Tab offsets, literal escape count 1,
no-Tab status and native body width 165.1; request 8 retains full no-Tab guidance. The model still chooses
width 12.7, repeats literal/overescaped sequences and stale searches, receiving truthful feedback. Last
save 17 precedes write 18; final readback 23 still has no real Tab. The new observations are delivered
but do not establish behavioral recovery. See the
[second Order 65 report](archive/all-holo-order65-tab-position-observation-retest-20260913.md).

**Order 65 is skipped unresolved** at the two-distinct-attempt checkpoint. The developer stopped this
episode at about 14.5 minutes, before 1800 seconds; it is not deadline exhaustion, evaluator 0 or proof
that more time could never succeed. Preserve Order 65's original scored failure, attempt 53 scored 0
and attempt 54 unscored interruption. The actual next queue entry **36 / Order 74**, Writer task
`6f81754e-285d-4ce0-b59e-af7edb02d108`, is current/diagnosing from its original deadline trajectory and
[offline triage](../experiments/work/all-holo-order74-triage-20260912.md), with no new episode.
Counts: **23 isolated PASS, 12 skips, 54 attempts, 35/94 processed and 58 pending**. Original **95/189**
and baseline pointer stay unchanged; no new gate, regression/control or full evaluation is added.

## 2026-09-13 11:09 UTC Order 65 actual Tab position observation launched

Native paragraph details now expose actual Tab zero-based code-point offsets and counts of literal
backslash-t sequences, computed from full native strings even when text previews are truncated. Existing
Writer projection retains these observations, and public inspect usage explains them. Execution, model
arguments, target selection and text remain unchanged; there is no new gate, required action or global
fitter. Existing native Tab module: **27 passed**; context module: **91 passed**, including Unicode and
offsets beyond the 500-character preview. Ruff for five Python files and scoped diff checks pass. See the
[second Order 65 report](archive/all-holo-order65-tab-position-observation-retest-20260913.md).

Attempt **54**, condition `holo31-all-roles-order65-tab-position-observation-retest-20260913-v1`, started at
`2026-09-13T11:08:31.187584+00:00`, supervisor PID **56274** / tool session **86850**, worker PID **56328**,
selected orders `[65]`, existing frozen validation `ok`. Freeze time **11:07:30.633825 UTC**; config SHA-256:
`f4d66214df8320007c16e1aeb33383ad1525078c36688dc078fcb5216886fc2c`.
Source SHA-256:
`8e1298ad8c0ad762f7e00a376eb000f3438c6770dcd977f29e7eab2068180352`
(522 files / 81,232,991 bytes). Both thinking Holo roles remain direct/serial on original Holo2 at
`http://192.168.0.138:8001/v1`, main/grounding temperature 0.8, with existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests stay frozen through supervisor exit.

Only **Order 65 is retesting/running**, at its second affected attempt. Complete coverage and geometry
remain separate model responsibilities. Review the two-attempt checkpoint if full observations leave
model errors without another demonstrated shared defect. Counts: **23 isolated PASS, 11 skips,
54 attempts, 34/94 processed and 59 pending**; original **95/189** and baseline pointer remain unchanged.
No other task episode, regression/control, new gate or additional full evaluation is added.

## 2026-09-13 11:06 UTC Order 65 feedback delivered and local Tab progress; task still fails

Attempt **53** finalized at `2026-09-13T11:05:21.319872+00:00` as original-evaluator **failed**, reward
**0**, 21 steps / 622.766 seconds, `agent_done`, one completion rejection. Supervisor PID 29692 /
tool session 39562 and worker PID 29721 exited **0**, both gone; final and worker integrity are `ok`.
The evaluator loaded only after the episode and source freeze is released. Results SHA-256:
`77ce93d8e71060a48d136bdbf3f393ac14f9de560d836232e58fb39239c59a29`.

The new note/counts are present in actual model requests **6–10**, and the model acknowledges missing
Tabs. Step 16 inserts a proper actual Tab in one local paragraph. Preserve that partial progress, while
step 7 placed a Tab at paragraph end, step 8 wrote literal backslash-t text, other paragraphs were omitted
and selected width 155 remained wrong. Raw model arguments match payload: no protocol conversion defect
is demonstrated. Final readback 20 and completion 21 still deliver a false completion claim. See the
[Order 65 report](archive/all-holo-order65-tab-effect-feedback-retest-20260913.md).

**Order 65 stays current/diagnosing**. Root plans minimal truthful observations of actual Tab offsets and
literal-tab-escape counts for a possible second bounded attempt, with focused checks and a new seal before
launch. No attempt 54, skip, automatic target edit or new gate is registered. Counts stay **23 isolated
PASS, 11 skips, 53 attempts, 34/94 processed and 59 pending**; original **95/189** and baseline pointer
remain unchanged.

## 2026-09-13 10:55 UTC Order 65 tab-stop effect feedback launched

Writer native formatting now reports informational `tab_stop_observation` counts of selected paragraphs
with/without actual Tab characters, plus effect guidance. Formatting without Tabs and clearing stops
remain valid successful operations; no text or model arguments are injected. The existing Writer context
mapping retains these small fields before large previews with the regular fitter, with no global
priority change or new gate. **24 native tests** and **89 context tests** passed, including mixed/no-Tab,
clearing/unrelated formatting and direct/forwarded retention in 1500 characters. Ruff for four Python
files and scoped diff checks pass. See the
[Order 65 report](archive/all-holo-order65-tab-effect-feedback-retest-20260913.md).

Attempt **53**, condition `holo31-all-roles-order65-tab-effect-feedback-retest-20260913-v1`, started at
`2026-09-13T10:54:46.249884+00:00`, supervisor PID **29692** / tool session **39562**, worker PID **29721**,
selected orders `[65]`, existing frozen validation `ok`. Freeze time **10:53:44.067791 UTC**; config SHA-256:
`cf25d74d392ed45f7096a45700ff5c22ef2419c40f6e8692a3959ef4b50b3dab`.
Source SHA-256:
`ff941674ecf1bacea7be8485f93f6e1106f93d3d9d38b0dc8ee950b63ff00f83`
(522 files / 81,230,315 bytes). Original Holo2 serves both thinking roles directly/serially at
`http://192.168.0.138:8001/v1`, main/grounding temperature 0.8, with existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests freeze lasts through supervisor exit.

The original final focused read already showed missing Tabs, so compact feedback alone does not explain
false completion. The model still owns correct text edits and stop geometry; no recovery is established
at launch. Only **Order 65 is retesting/running**. Counts: **23 isolated PASS, 11 skips, 53 attempts,
34/94 processed and 59 pending**. Original **95/189** and the promoted pointer remain unchanged; no other
task episode, regression/control, new gate or full evaluation is added.

## 2026-09-13 10:50 UTC Order 64 second scored failure and bounded skip; Order 65 selected

Attempt **52** finalized at `2026-09-13T10:49:19.922794+00:00` as original-evaluator **failed**, reward
**0**, five steps / 148.453 seconds, `agent_done`, one completion rejection. Supervisor PID 9015 /
tool session 78557 and worker PID 9126 exited **0**, both gone; final and worker integrity are `ok`.
The evaluator loaded only after the episode. Source freeze is released. Results SHA-256:
`bf9f9bad2833cd9ce1e5c64192f194ee3afb0092f83f6099d6410b7bb32de8eb`.

The actual step-2 schema contains the new blank/nonempty clarification. The model nevertheless repeats
raw `[0,1]`, counting the empty paragraph as the second body paragraph; inspect/format/readback/done and
terminal-audit behavior matches attempt 51. No transport or protocol error occurred, but no behavioral
improvement or isolated PASS is established. See the
[second Order 64 report](archive/all-holo-order64-paragraph-selector-usage-retest-20260913.md).

At the two-affected-attempt checkpoint, **Order 64 is skipped unresolved**. Complete feedback and explicit
usage leave no further demonstrated framework defect to justify another variant now. Preserve the
accurate generic documentation, original transport failure and both scored-zero rechecks; this bounded
skip does not establish intrinsic impossibility. The actual next queue entry **35 / Order 65**, Writer task
`0a0faba3-5580-44df-965d-f562a99b291c`, is current/diagnosing from its
[preserved offline triage](../experiments/work/all-holo-order65-triage-20260912.md), with no new episode.
Counts: **23 isolated PASS, 11 skips, 52 attempts, 34/94 processed and 59 pending**. Original **95/189**
and the promoted pointer stay unchanged; no new gate, regression/control or full evaluation is added.

## 2026-09-13 10:47 UTC Order 64 paragraph-selector usage clarification launched

Only `writer_adapter/tool_manifest.py` descriptions changed: raw paragraph indices and inspection limits
explicitly count blank separators; existing `nonempty_ordinals` counts paragraphs containing text. Schema
shape, defaults, native formatting, completion policy and argument conversion are unchanged. The existing
bounded Writer module has **35 passing tests**; Ruff for one Python file and scoped diff checks pass.
No new test or gate was added. Host-only artifact comparison confirms the omitted second body paragraph
is the sole spacing difference against one accepted alternative; reference content/selectors never enter
runtime. See the [second Order 64 report](archive/all-holo-order64-paragraph-selector-usage-retest-20260913.md).

Attempt **52**, condition `holo31-all-roles-order64-paragraph-selector-usage-retest-20260913-v1`, started at
`2026-09-13T10:46:39.903011+00:00`, supervisor PID **9015** / tool session **78557**, worker PID **9126**,
selected orders `[64]`, existing frozen validation `ok`. Freeze time **10:45:41.596331 UTC**; config SHA-256:
`d87690a72018d4d6465a11e64b475d2f483ec9bb853a0031ccb645f69f736561`.
Source SHA-256:
`1d5442844b49f506cf7a939729d125792fb7670c8c74c4bf9e64207bee982f58`
(522 files / 81,224,901 bytes). Both thinking Holo roles remain direct/serial on original Holo2 at
`http://192.168.0.138:8001/v1`, main/grounding temperature 0.8, with existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through supervisor exit.

Only **Order 64 is retesting/running**, now at its second affected attempt. The clarification is a usability
hypothesis; prior feedback already exposed the correct distinction. If it is still ignored without another
demonstrated defect, review the two-attempt checkpoint. Counts are **23 isolated PASS, 10 skips,
52 attempts, 33/94 processed and 60 pending**; original **95/189** and the promoted pointer remain unchanged.
No other task, regression/control, probe, new gate or additional full evaluation was run.

## 2026-09-13 10:44 UTC Order 64 transport completes; paragraph-selection failure remains current

Attempt **51** finalized at `2026-09-13T10:43:08.405209+00:00` as original-evaluator **failed**, reward
**0**, five steps / 147.281 seconds, `agent_done`, one completion rejection. The evaluator loaded only
after the episode. Supervisor PID 61713 / tool session 42279 and worker PID 61733 exited **0**; worker
and supervisor final integrity are `ok`. Source freeze is released. Results SHA-256:
`570696dde4920925330f805d39e5ac8eb9f31a55170b85dc63c19882b2c6532e`.

Direct transport worked in this attempt, but inspect 1 read only two raw paragraphs and format 2 applied
double spacing to raw `[0,1]`, including empty paragraph 1. After rejection 3 required readback, inspect 4,
completion 5 and terminal audit 6 accepted the incomplete selection. The second nonempty body paragraph
remains unformatted. This is a task failure with successful transport, not a new environment or protocol
failure. See the [Order 64 report](archive/all-holo-order64-direct-transport-retest-20260913.md).

**Order 64 remains current/diagnosing**. Root is investigating offline evaluator evidence and a minimal
generic clarification of existing paragraph-selection usage; no new gate, skip or attempt 52 is registered.
Counts remain **23 isolated PASS, 10 skips, 51 attempts, 33/94 processed and 60 pending**. Original
**95/189** and the promoted pointer stay unchanged.

## 2026-09-13 10:41 UTC Order 64 direct-Holo2 transport recheck launched

Original request 4 ended after three Cloudflare **HTTP 524** origin timeouts at 120 seconds, not tool
argument/protocol rejection. Before that, native formatting/readback/auto-save worked, but raw paragraph 1
was empty and the model omitted the second nonempty body paragraph. Current public schemas already
explain raw indices, `nonempty_ordinals` and `line_spacing: 2` for double spacing. No new production or
test edit is introduced; source remains unchanged from attempt 50. See the
[Order 64 report](archive/all-holo-order64-direct-transport-retest-20260913.md).

Attempt **51**, condition `holo31-all-roles-order64-direct-transport-retest-20260913-v1`, started at
`2026-09-13T10:40:28.384807+00:00`, supervisor PID **61713** / tool session **42279**, worker PID **61733**,
selected orders `[64]`, existing frozen validation `ok`. Freeze time **10:39:38.163531 UTC**; config SHA-256:
`09fc8577a1c172f97018f2ed1c6f369b3f338ae0ceb126b7a453595b0505d1d2`.
Source SHA-256:
`cff959fdf0c431766b2d114e1c91fdb4ae5038d0c8310d1c57394860a3454385`
(522 files / 81,224,245 bytes). Original Holo2 serves both thinking roles directly/serially at
`http://192.168.0.138:8001/v1`, main/grounding temperature 0.8. Existing 100 global/50 local steps,
one same-VM restart, 1800 Agent seconds and 30 GiB floor remain. Source/tests freeze lasts through
supervisor exit; prior focused checks are not repeated.

Transport completion and correct paragraph selection will be assessed separately; direct/serial serving,
sampling and cumulative source differ from the original condition. Only **Order 64 is retesting/running**.
Counts are **23 isolated PASS, 10 skips, 51 attempts, 33/94 processed and 60 pending**. Launch adds no PASS;
original **95/189** and the promoted pointer remain unchanged. No regression/control, new gate, probe or
additional full evaluation is added.

## 2026-09-13 10:32 UTC Order 61 bounded unresolved skip; Order 64 selected

Attempt **50** ended at `2026-09-13T10:30:45.812126+00:00` as **interrupted/unscored**, 35 steps /
1024.45 seconds, five completion rejections, no evaluator or reward. Supervisor PID 7361 / tool session
15990 exited **130**, verified by root; worker PID 7415 exited **0**, revalidation `ok`. Both processes
are gone and source freeze is released. Supervisor `metadata.final_integrity` remains **null**; this is
not a finalized scored seal. Results SHA-256:
`cd3b30c2eb507d2bb12e8c8b9ace92e22377212a25214b332c2b6f1f1d6914db`.

Save discovery is live-verified at search 3 and save 13. The page labels reach actual model requests,
but the model still confuses page indices despite available target fields, styles, tools and errors.
Late correct formatting at step 32 means **2/4 requested textboxes** are complete, not the earlier 1/4.
Completion 34 truthfully asks for target 3/4 plus save/readback, and inspection 35 shows both actual
page-1 textboxes still unformatted. Wrong-page formatting 22–30 and geometry 5/6 remain, as do writes
after the last save at 13. No new host-side hidden-tool or feedback-loss defect is demonstrated.
See the [third Order 61 report](archive/all-holo-order61-save-search-page-label-retest-20260913.md).

Order 61 is **skipped unresolved** at the approximately 60-minute review checkpoint after three distinct
affected attempts. This developer stop occurred before the 1800-second episode limit; it is not deadline
exhaustion, an evaluator failure or proof that a longer run could never succeed. Preserve late progress
and all interrupted evidence. The actual next queue entry **34 / Order 64**, Writer task
`0810415c-bde4-4443-9047-d5f70165a697`, is current/diagnosing from its original transport failure;
no new episode is registered. Counts: **23 isolated PASS, 10 skips, 50 attempts, 33/94 processed and
60 pending**. Original **95/189** and the promoted pointer remain unchanged; no regression/control,
new gate or additional full evaluation was added.

## 2026-09-13 10:16 UTC Order 61 save-search and page-label repairs launched

Public `.save` candidates now survive semantic-search scope filtering before ranking without adding
a mandatory action or changing model arguments, ranking, unrelated writes or export eligibility.
Three synthetic searches exercise the actual next-model tool surface; the existing recovery module
has **43 passing tests**. Model-facing page summaries now use `slide_index` beside preserved
`display_slide_number`, with canonical/raw receipts and `tool_target.slide` unchanged. The normal,
bounded and forwarded projection modules have **123 passing tests**; shortened guidance retains the
same large-deck objects within existing budgets. Ruff for six Python files and scoped diff checks pass.
See the [third Order 61 report](archive/all-holo-order61-save-search-page-label-retest-20260913.md).

Attempt **50**, condition `holo31-all-roles-order61-save-search-page-label-retest-20260913-v1`, started at
`2026-09-13T10:13:29.821439+00:00`, supervisor PID **7361** / tool session **15990**, worker PID **7415**,
selected orders `[61]`, existing frozen validation `ok`. Freeze time **10:12:21.105842 UTC**; config SHA-256:
`4dc97a4bef4c132927226442f2aa94024034ebd86bf21dc6a27541b770973c2f`.
Source SHA-256:
`cff959fdf0c431766b2d114e1c91fdb4ae5038d0c8310d1c57394860a3454385`
(522 files / 81,224,245 bytes). Both thinking Holo roles remain on original Holo1 directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8, 100 global/50 local steps, one same-VM
restart, 1800 Agent seconds and 30 GiB floor. Source/tests remain frozen through supervisor exit.

This **third affected attempt** extends the checkpoint for the newly demonstrated save-search defect;
both prior interrupted/unscored attempts remain preserved, including null supervisor final integrity.
Correct page targets were already visible, so the label change does not guarantee recovery. If fully
observed model confusion persists without another demonstrated defect, record and skip instead of an
unchanged replay. Only **Order 61 is retesting/running**. Counts are **23 isolated PASS, 9 skips,
50 episode attempts, 32 processed and 61 pending**. Original **95/189** and the promoted pointer remain
unchanged. No regression/control, new gate, endpoint probe or additional full run was added.

## 2026-09-13 10:07 UTC Order 61 second attempt interrupted for confirmed save-search exclusion

Attempt **49** finalized at `2026-09-13T10:06:17.837916+00:00` as **interrupted/unscored**, 38 steps /
1129.292 seconds, one completion rejection, no evaluator or reward. Supervisor PID 22028 / tool session
19078 exited **130**, verified by root; worker PID 22037 exited **0** with revalidation `ok`. Supervisor
`metadata.final_integrity` is **null**; no final supervisor seal is claimed. Both processes are gone and
source freeze is released. Results SHA-256:
`cc82a86ed3c0538a7dbdd785d0b4fabbed02096f3ef7be7471cc55e7190f1533`.

Global role-format equivalence is now exercised online: completion 22 no longer demanded duplicate
`shape.format_text`. Real page/readback/save/geometry requirements remained. No listener recovery happened,
so the passive repair is not live-verified by this attempt. At steps 25/27 the model searched for save, but
`semantic_search_scope` removed `presentation.save` before ranking—even an exact query fails—and the
actual next schemas lacked the tool. This is a newly reproduced framework defect. Observation labels also
use ambiguous `slide` beside display numbers; a model-only `slide_index` label is planned without changing
backend state or tool arguments. See the [second Order 61 report](archive/all-holo-order61-role-equivalence-listener-retest-20260913.md).

**Order 61 remains repairing**. A third affected attempt will require the new search/label changes,
focused evidence and a new seal; it is not an unchanged replay or parameter sweep. Both interrupted
attempts remain preserved. Counts stay **23 isolated PASS, 9 skips, 49 episode attempts, 32 processed and
61 pending**; no skip, advance or new score is recorded. Original **95/189** and the promoted pointer remain
unchanged, and no new gate or regression/control episode is added.

## 2026-09-13 09:47 UTC Order 61 role-format equivalence and passive-listener repairs launched

Global and per-target underline evidence now recognizes the model's successful native role-format
receipts on the same observed page/path, retaining later overrides, target coverage and save/readback.
**47 focused tests** passed. Separately, passive listener startup preserves live Office/documents/profile
locks and executes the selected action once under the existing lock/timeout, without document reopen or
write replay; **22 focused tests** passed. Ruff for seven changed Python files and diff checks passed.
The first UNO bridge-disposal cause remains unknown, and a task PASS alone cannot establish that the
listener branch ran. See the [second Order 61 report](archive/all-holo-order61-role-equivalence-listener-retest-20260913.md).

Attempt **49**, condition `holo31-all-roles-order61-role-equivalence-listener-retest-20260913-v1`, started at
`2026-09-13T09:47:17.235530+00:00`, supervisor PID **22028** / tool session **19078**, worker PID **22037**,
selected orders `[61]`, existing frozen validation `ok`. Freeze time **09:45:43.126547 UTC**; config SHA-256:
`9a9403b8a660d23a150c8f01a845bc48bb26adede29e70aeb92d64becc7c4e4c`.
New source SHA-256:
`8241022cf1cffc14f5868a3b172e7e1fbc3a617193b61bf247ff1538a8830352`
(522 files / 81,221,753 bytes). Both thinking Holo roles remain on original Holo1 directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8 and unchanged episode/resource limits.
Source/tests remain frozen through supervisor exit; interrupted attempt 48 remains separate.

Only **Order 61 is retesting/running** at its second affected attempt. Counts are **23 isolated PASS,
9 skips, 49 episode attempts, 32 processed and 61 pending**. No new PASS is established by launch;
original **95/189** and the promoted pointer remain unchanged. No regression/control, new gate or full run
was added.

## 2026-09-13 09:39 UTC Order 61 interrupted unscored for role-format alias and native-listener recovery defects

Attempt **48** finalized at `2026-09-13T09:38:37.753122+00:00` as **interrupted/unscored**, 23 steps /
630.224 seconds, one completion rejection, no evaluator or reward. Supervisor PID 45972 / tool session
93493 exited **130**, verified by root; worker PID 45985 exited **0** with revalidation `ok`. Supervisor
`metadata.final_integrity` is **null** after interruption; no final supervisor seal is claimed. Both processes
are gone and the source freeze is released. Results SHA-256:
`b32a51fc4068d0fc08c8d662b70eccb9fdf6a1fc84ca91f9ed931d60da210f7d`.

Picture placement 7 and role-format actions 8/10 succeeded, then save 11. Completion's extra mandatory
`shape.format_text` restriction omitted this successful equivalent action in both matching paths, while
its missing initial page-0/post-save inspection remained real. The whole rejection is not false. Inspect
13 then lost the UNO bridge; after GUI reopen 15, calls 16/19/20/21 returned `LIBREOFFICE_NOT_READY` and
directed the model to inaccessible host-only prepare. The developer stopped to repair those demonstrated
issues. The runner's generic “by user” label does not attribute this stop to a new user request.

**Order 61 stays current/repairing** for equivalent-action recognition and passive-listener recovery.
Focused checks and a new source/config seal are required before any second episode; no next task or
unchanged replay is started. See the [Order 61 report](archive/all-holo-order61-direct-sampling-retest-20260913.md).
Counters remain **23 isolated PASS, 9 skips, 48 episode attempts, 32 processed and 61 pending**. Original
**95/189** and the promoted pointer remain unchanged; this interruption adds no scored failure or PASS.

## 2026-09-13 09:28 UTC Order 61 current-setting exploration launched; post-58 observation followup completed separately

After Order 58's scored run, owning inspection now exposes `text_style.bold` beside unchanged raw
`bold_weight`, retaining weight 0 as unknown/null. Usage explains 100 normal / 150 bold. Existing projections
already retain the style, so no new branch or gate is needed. **19 grouped-text module tests** passed with
normal/bold/unknown cases, plus Ruff for three changed Python files and diff checks. This followup is
**not part of Order 58's PASS**, does not rerun it and does not resolve its recorded instruction residual
retroactively. See the [Order 58 report](archive/all-holo-order58-completion-evidence-retest-20260913.md).

Attempt **48** explores current sampling on Order 61's observed page/shape confusion; no native geometry
or target-selection fix is claimed. Condition `holo31-all-roles-order61-direct-sampling-retest-20260913-v1`
started at `2026-09-13T09:27:56.107324+00:00`, supervisor PID **45972** / tool session **93493**, worker
PID **45985**, selected orders `[61]`, existing frozen validation `ok`. Freeze time **09:26:44.817076 UTC**;
config SHA-256:
`4a9791b39c9b7ea1cfd245ab5a54db68f515dbdc2f1a636dcad7dd5b92fd4897`.
New source SHA-256:
`f1898e8e9d770af21ba623e3458fdad8ccf5f9d7bd35957cdf5e7b11cf9fc080`
(520 files / 81,206,130 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8 and existing episode/resource limits.
Source/tests remain frozen through supervisor exit. See the
[Order 61 report](archive/all-holo-order61-direct-sampling-retest-20260913.md).

Only **Order 61 is retesting/running**. Counts remain **23 isolated PASS, 9 skips, 48 episode attempts,
32 processed and 61 pending**. No outcome is established at launch; original **95/189** and the promoted
pointer remain unchanged. No control/regression, new gate or additional full evaluation was added.

## 2026-09-13 09:24 UTC Order 58 scores PASS with grouped-text instruction residual; Order 61 selected

Attempt **47** finalized at `2026-09-13T09:23:16.567108+00:00` as original-evaluator **PASS**, reward
**1.0**, six event steps / 173.003 seconds, `agent_done`, with one completion rejection. Supervisor PID
29896 / tool session 43867 and worker PID 29904 exited **0**; both final integrity checks are `ok`. Results
SHA-256:
`e77bf4bb3e5a247838c8cc5361a269731d06468468edfa05b010bd327e8a9fa9`.

**The scorer PASS and full-instruction completion differ here.** The model formatted only the title and,
as in the original episode, misread `bold_weight 100` as already bold. Grouped text remained unchanged,
so the full-page bold instruction still has a recorded residual despite reward 1. Completion used **array
evidence**; the four original string calls have offline compatibility evidence, not new online string-path
coverage. Preserve both limitations. Root is preparing a minimal generic boolean-observation usability
followup after supervisor exit; it is not part of this sealed PASS and does not rerun the passed task.
See the [Order 58 report](archive/all-holo-order58-completion-evidence-retest-20260913.md).

The ledger records **23 isolated evaluator PASS, 9 skips, 47 episode attempts, 32/94 processed and
61 pending**. Actual next queue entry **33 / Order 61**, Impress task
`ed43c15f-00cb-4054-9c95-62c880865d68`, is current/diagnosing from its original deadline trajectory and
[preserved triage](../experiments/work/all-holo-order61-triage-20260912.md); no new episode has launched.
Original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 09:20 UTC Order 58 existing evidence compatibility replay launched; full text scope remains model-owned

All four original completion calls rejected for string evidence pass the current shared contract with raw
outer arguments preserved. They were complete calls; evidence lengths are **364 / 3465 / 3140 / 3114**
characters. Separate native observations show that the original title was formatted but grouped text
remained unbold. Removing a protocol rejection therefore does not establish the requested full-page result.
No new source/test change or automatic scope correction is introduced. See the
[Order 58 report](archive/all-holo-order58-completion-evidence-retest-20260913.md).

Attempt **47**, condition `holo31-all-roles-order58-completion-evidence-retest-20260913-v1`, started at
`2026-09-13T09:20:11.542960+00:00` (the `started_at` value, distinct from metadata's later update time),
supervisor PID **29896** / tool session **43867**, worker PID **29904**, selected orders `[58]`, existing
frozen validation `ok`. Freeze time **09:18:56.543189 UTC**; config SHA-256:
`d695eb80849a7fe5cdd412e4e48b0ba71614fa19b3d200db41a5a555edf0131d`.
Unchanged source SHA-256:
`1d2eaf316d871a3766c6672a125852289c326f112dbfd5ddceb6c80fdf4cdaec`
(520 files / 81,204,789 bytes). Both thinking Holo roles use original Holo1 directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8 and existing episode/resource limits.
Source/tests remain frozen through supervisor exit; no task result is established by launch.

Only **Order 58 is retesting/running**. Counts are **22 isolated PASS, 9 skips, 47 episode attempts,
31 processed and 62 pending**. Original **95/189** and the promoted pointer remain unchanged; no
regression/control, new gate or additional full evaluation was added.

## 2026-09-13 09:14 UTC Order 57 recovered PASS after correcting page/selector pairs; Order 58 selected

Attempt **46** finalized at `2026-09-13T09:12:28.992502+00:00` as original-evaluator **PASS**, reward
**1.0**, 24 event steps / 558.144 seconds, `agent_done`, with one completion rejection. Supervisor PID
58063 / tool session 9402 and worker PID 58130 exited **0**; both final integrity checks are `ok`. Results
SHA-256:
`66b97f489395ef961023d27fdc3bd1d74bd1c93b712fa9805a89385bac73eb70`.

After early cross-page errors, the model used correct API page/selector pairs at steps **12, 17 and 20**;
native receipts report the requested right/center/left alignments. It saved at step 22, inspected the last
target page at 23 and completed at 24, confirmed by terminal model audit 25 and original scoring. Post-save
inspection covered only that last page; do not claim a broader final readback. No new code was added for
this task, and one success does not isolate temperature causality or measure variance. See the
[Order 57 report](archive/all-holo-order57-direct-sampling-retest-20260913.md).

The ledger now records **22 isolated PASS, 9 skips, 46 episode attempts, 31/94 processed and 62 pending**.
Actual next queue entry **32 / Order 58**, Impress task `5c1a6c3d-c1b3-47cb-9b01-8d1b7544ffa1`, is current/
diagnosing, starting from original `model_protocol_failure`; no new episode has launched. Original
**95/189** and the promoted pointer remain unchanged, with no regression/control or additional full run.

## 2026-09-13 09:04 UTC Order 57 direct sampling exploration launched with unchanged source

Original evidence exposes complete paired page/object targets. Five API attempts combined a page with
another page's path and correctly returned `SHAPE_NOT_FOUND`; one correctly targeted alignment succeeded.
No alignment API or hidden-feedback defect is demonstrated. Attempt **46** is one explicit **main
temperature 0.8 sampling exploration**, versus original 0, with no new source/test change. If the same
fully observed target confusion or omission persists, record it and skip without unchanged replay or a
parameter sweep. See the [Order 57 report](archive/all-holo-order57-direct-sampling-retest-20260913.md).

Condition `holo31-all-roles-order57-direct-sampling-retest-20260913-v1` started at
`2026-09-13T09:02:58.926582+00:00`, supervisor PID **58063** / tool session **9402**, worker PID **58130**,
selected orders `[57]`, existing frozen validation `ok`. Freeze time **09:01:38.064441 UTC**; config SHA-256:
`b7016ec3f72babbc640e1f39415a10370662cb1e667bc82385ced3aa7f5d3748`.
Unchanged source SHA-256:
`1d2eaf316d871a3766c6672a125852289c326f112dbfd5ddceb6c80fdf4cdaec`
(520 files / 81,204,789 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8 and the existing episode/resource limits.
Source/tests remain frozen through supervisor exit; this is not a single-factor API-fix comparison.

Only **Order 57 is retesting/running**. Counts are **21 isolated PASS, 9 skips, 46 episode attempts,
30 processed and 63 pending**. No task PASS is established at launch. Original **95/189** and the promoted
pointer remain unchanged; no control/regression, new gate or additional full evaluation was added.

## 2026-09-13 08:59 UTC Order 54 receipt is verified but cleanup remains incomplete; skip and select Order 57

Attempt **45** finalized at `2026-09-13T08:57:21.146459+00:00` as original-evaluator **failed**, reward
**0.0**, 12 steps / 429.098 seconds, `agent_done`, with one completion rejection. Supervisor PID 32505 /
tool session 46466 and worker PID 32514 exited **0**; both final integrity checks are `ok`. Results SHA-256:
`e2f57f5f4169de0947667a4c89dd7c154fd23e72e1a8610cc9c1b8e6295a2a18`.

The complete actual deleted-object result reached request 8 unchanged, directly verifying the receipt and
existing projection. The model still removed only the address, unnecessarily formatted the contact-page
title and ignored visible phone/email/website/social text plus five icons. It saved at step 11 and claimed
completion at step 12, accepted by terminal audit 13. Saved page counts are `[10,12,15,14,7]` versus the
alternate reference's `[10,12,15,5,7]`; other pages have no object loss. This offline evidence remains host-only.
No new hidden-tool, lost-observation, argument-rewrite or ineffective-deletion defect is established.

**Skip Order 54** at the negative checkpoint, keeping the truthful generic receipt and all evidence without
an unchanged replay, cleanup classifier or new gate. See the
[Order 54 report](archive/all-holo-order54-deletion-receipt-retest-20260913.md). The ledger now records
**21 isolated PASS, 9 skips, 45 episode attempts, 30/94 processed and 63 pending**. Actual next queue entry
**31 / Order 57**, Impress task `05dd4c1d-c489-4c85-8389-a7836c4f0567`, is current/diagnosing with no new
episode. Its [preserved triage](../experiments/work/all-holo-order57-triage-20260912.md) concerns original
`agent_deadline_exhausted`. Original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:50 UTC Order 54 actual-deleted-object receipt repair launched

Native `shape.delete` feedback now records the object's actual identity before removal, owning slide,
unchanged requested selector and index-shift guidance while retaining the existing remaining count.
Owning usage advises keeping slide/selector observations aligned. Native removal and model target choices
are unchanged; this adds no selector prerequisite or deletion sequence. **Six focused tests** and Ruff/diff
checks for three changed Python files passed. A normal **703-character receipt** survives existing context
projection intact, so no new projection branch was added. The original seven deletes all executed; prior
duplicate-delete exemption is not credited with fixing this original failure. See the
[Order 54 report](archive/all-holo-order54-deletion-receipt-retest-20260913.md).

Attempt **45**, condition `holo31-all-roles-order54-deletion-receipt-retest-20260913-v1`, started at
`2026-09-13T08:49:56.095342+00:00`, supervisor PID **32505** / tool session **46466**, worker PID **32514**,
selected orders `[54]`, existing frozen validation `ok`. Freeze time **08:48:41.641828 UTC**; config SHA-256:
`d853159b15d3c014b3261876a00f49d8a22febe8d61be1d8229c920ff277e0d5`.
New source SHA-256:
`1d2eaf316d871a3766c6672a125852289c326f112dbfd5ddceb6c80fdf4cdaec`
(520 files / 81,204,789 bytes). Original metadata confirms Holo2; both thinking roles use its established
direct backend `http://192.168.0.138:8001/v1`, serially with main/grounding temperature 0.8 and unchanged
episode/resource limits. Source/tests remain frozen through supervisor exit.

Only **Order 54 is retesting/running**. Counts are **21 isolated PASS, 8 skips, 45 episode attempts,
29 processed and 64 pending**. No PASS is established at launch; original **95/189** and the promoted
pointer remain unchanged. No regression/control, new gate or additional full evaluation was added.

## 2026-09-13 08:44 UTC Order 46 recovered PASS; Order 54 selected

Attempt **44** finalized at `2026-09-13T08:42:52.431306+00:00` as original-evaluator **PASS**, reward
**1.0**, six event steps / 168.024 seconds, `agent_done`, with one completion rejection. Supervisor PID
8424 / tool session 28057 and worker PID 8457 exited **0**; both final integrity checks are `ok`. Results
SHA-256:
`44e008856185cd5b2c09dc940999c5d9855aa0ccaf564a63de624d43c91e19e1`.

The model changed the background at step 2, then used save at step 4 and inspection at step 5 after the
existing save/readback feedback. Completion at event 6 and terminal model audit 7 reached original scoring.
This online episode used **array evidence**; compatibility of the three original **string evidence** calls
has direct offline validation, not new online string-path coverage from this PASS. No new source was needed.
See the [Order 46 report](archive/all-holo-order46-completion-evidence-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **21 isolated PASS,
8 skips, 44 episode attempts, 29/94 processed and 64 pending**. Actual next queue entry **30 / Order 54**,
Impress task `a53f80cd-4a90-4490-8310-097b011433f6`, is current/diagnosing with no new episode. Its
[preserved triage](../experiments/work/all-holo-order54-triage-20260912.md) concerns original
`failed / agent_loop_time_budget_exhausted`. No regression/control or additional full evaluation was added;
original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:40 UTC Order 46 existing completion-evidence compatibility replay launched

The original task reached saved green-background readback but failed protocol validation on three complete
`propose_done` calls with string evidence. Existing Order 5 compatibility accepts those three original outer
argument objects unchanged; evidence remains opaque text of **3446 / 3067 / 3067 characters**. Every original
finish reason is `tool_calls`, so this was not truncation. Current schema, claim-contract and contradiction
checks accept them. This offline argument check is not a full completion-ledger replay, model probe or task
PASS, and no new source/test change is introduced. See the
[Order 46 report](archive/all-holo-order46-completion-evidence-retest-20260913.md).

Attempt **44**, condition `holo31-all-roles-order46-completion-evidence-retest-20260913-v1`, started at
`2026-09-13T08:39:52.408278+00:00`, supervisor PID **8424** / tool session **28057**, worker PID **8457**,
selected orders `[46]`, existing frozen validation `ok`. Freeze time **08:37:19.385351 UTC**; config SHA-256:
`04304f19917c1f5abd4dccbbd1cb19bcc8562415ad6611e617b523fedac176b2`.
Unchanged source SHA-256:
`580dd602a18b26b5618de29e09c1aac04f5c3a72bf54ae8b414c4e08cd532f1b`
(519 files / 81,199,374 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8 and unchanged episode/resource limits.
Source/tests remain frozen through supervisor exit. The original public/greedy condition also differs
in cumulative source, so this is not an isolated test of the evidence fix.

Only **Order 46 is retesting/running**. Counts are **20 isolated PASS, 8 skips, 44 episode attempts,
28 processed and 65 pending**. No task PASS is established by launch, and no regression/control, new gate,
promotion or full evaluation was added. Original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:34 UTC Order 43 recovered PASS with persisted bold text; Order 46 selected

Attempt **43** finalized at `2026-09-13T08:33:23.050917+00:00` as original-evaluator **PASS**, reward
**1.0**, 12 event steps / 294.938 seconds, `agent_done`, with one completion rejection. Supervisor PID
49517 / tool session 31834 and worker PID 49571 exited **0**; both final integrity checks are `ok`.
Results SHA-256:
`91648e623d15bcc454b818b9ebf59dee82c584affbfd1dd4fcafe48b5971694e`.

Step 6's native formatting receipt reported **CharWeight 150** for the model-selected title. The model
wrote the note at step 8, saved at step 10 and read persisted **bold_weight 150** at step 11; event 12
completed and terminal model audit 13 confirmed it. This verifies successful delivery and truthful native
receipts under this condition. The selector was path-only and no final-format mismatch occurred, so
composite-selector compatibility and mismatch recovery remain locally tested fixes, not paths exercised
by this PASS. The original edit-buffer explanation remains unproven. See the
[Order 43 report](archive/all-holo-order43-format-recovery-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **20 isolated PASS,
8 skips, 43 episode attempts, 28/94 processed and 65 pending**. Actual next queue entry **29 / Order 46**,
Impress task `9cf05d24-6bd9-4dae-8967-f67d88f5d38a`, is current/diagnosing, starting from its original
`model_protocol_failure`; no new episode has launched. No regression/control or additional full run was
added. Original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:29 UTC Order 43 selector, native-format receipt and recovery repairs launched

All three repairs are integrated: compatible composite-selector checking/usage based on complete native
observations; direct formatting receipts that read the selected span and report actual mismatches; and a
shared recovery predicate that retains repair/search tools after wrong state has already been observed.
Native selection/arguments, completion thresholds and existing duplicate policy remain unchanged. The
original saved-format persistence cause remains unproven; no speculative GUI action was added.

Focused checks passed in groups of **42 recovery/schema/save, 26 native-format, 30 selector/grouped-
observation and 28 post-integration tests**. These groups overlap and are not summed into independent
tests or episodes. Ruff and diff checks passed for eight changed Python files. See the
[Order 43 report](archive/all-holo-order43-format-recovery-retest-20260913.md).

Attempt **43**, condition `holo31-all-roles-order43-format-recovery-retest-20260913-v1`, started at
`2026-09-13T08:28:13.012803+00:00`, supervisor PID **49517** / tool session **31834**, worker PID **49571**,
selected orders `[43]`, existing frozen validation `ok`. Freeze time **08:27:07.195093 UTC**; config SHA-256:
`07a7f2a1c22238ea20f1e9ae8eacf12395bc72906be87dfa3907a0c6cb202fac`.
New source SHA-256:
`580dd602a18b26b5618de29e09c1aac04f5c3a72bf54ae8b414c4e08cd532f1b`
(519 files / 81,199,374 bytes). Original Holo1 serves both thinking roles directly/serially at
`http://192.168.0.224:8002/v1`, main/grounding temperature 0.8 and unchanged episode/resource limits.
Source/tests remain frozen through supervisor exit; launch establishes no task outcome.

Only **Order 43 is retesting/running**. Counts are **19 isolated PASS, 8 skips, 43 episode attempts,
27 processed and 66 pending**. No control/regression, new gate, promotion or additional full evaluation
was added; original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:22 UTC Order 43 source repair in progress; no new episode

The preserved failure exposes valid composite-selector rejection, requested rather than observed format
receipts, and recovery that mistakes an already completed but incorrect readback for a request to read
again. Root's shared read-action predicate now covers both recovery classifiers, keeping repair/search
tools available for wrong observed state. **42 focused recovery/schema/save tests passed**, including a
synthetic save/readback mismatch corrected by the unchanged model-selected call. Existing duplicate
protection already releases after the intervening save; no additional exception or gate is added.

Selector-contract and truthful native-format work remain in progress. The possible GUI edit-buffer cause
of the write mismatch remains unproven and is not used to justify speculative actions. See the new
[Order 43 report](archive/all-holo-order43-format-recovery-retest-20260913.md). **No Order 43 episode has
launched**, and these local checks add no task PASS or attempt. Counters stay **19 isolated PASS, 8 skips,
42 attempts, 27 processed and 66 pending**; original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:17 UTC Order 35 fails on omitted placeholder cleanup and is skipped; Order 43 selected

Attempt **42** finalized at `2026-09-13T08:13:45.092646+00:00` as original-evaluator **failed**, reward
**0.0**, 21 steps / 446.284 seconds, `agent_done`, with one completion rejection. Supervisor PID 1424 /
tool session 22688 and worker PID 1432 exited **0**; both final integrity checks are `ok`. Results SHA-256:
`1a70c1f120e201ba80f9b8aa68829d3eeded3ca3fbef576dd4e94be39bb98d99`.

The false mandatory deletion pair is gone; the only rejection correctly requested final readback. Output
contains six pages and the six correct image payloads in order, but page object counts are
`[3, 1, 1, 1, 1, 1]`: the initial Title and Subtitle remain beside the first image. Those objects were fully
visible in request 21 with no omitted text shapes, and the model had recognized cleanup earlier but omitted
it. The unchanged evaluator compares object counts even with geometric comparison disabled, explaining
reward zero. This offline artifact evidence stays host-only. No deletion executed in either attempt, so
the positional-delete exemption remains covered by focused tests but not live-verified by this task.

**Skip Order 35 at the two-attempt checkpoint** for remaining model cleanup/planning and review omission.
Preserve the first interrupted attempt, this scored failure and the demonstrated generic fixes. No new
validator, task-specific cleanup sequence or unchanged replay is added. See the
[Order 35 report](archive/all-holo-order35-positional-delete-layout-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **19 isolated PASS,
8 skips, 42 episode attempts, 27/94 processed and 66 pending**. Actual next queue entry **28 / Order 43**,
Impress task `7dbc52a6-11e0-4c9a-a2cb-1e36cfda80d8`, is current/diagnosing with no episode launched by this
update. Its [preserved triage](../experiments/work/all-holo-order43-triage-20260912.md) concerns original
`failed / stalled_no_progress`. Original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 08:06 UTC Order 35 optional-cleanup correction launched as attempt 42

Strict ordered-image requirements now omit both deletion strategies while retaining creation/insertion;
advisory action-selection hints keep both cleanup tools discoverable. Owning inspection usage explains
that empty placeholders remain objects. Generic completion, native observations, model review and
save/readback are unchanged. **No legacy ordered-image plan or blankness method is enabled**, and no new
strict blankness checker is added; correct page content still depends on the model and original evaluator.

The strict-Impress completion and bounded-Impress decomposition suites passed **23 tests**, including
clean synthetic decks requiring no deletion, object cleanup only or page replacement only. Ruff passed for
four changed Python files and diff checks passed. A local synthetic check found no premature tool hiding
after first insertion/save/readback; existing recovery already releases normally. The earlier 25 deletion
tests remain separate completed checks. See the [Order 35 report](archive/all-holo-order35-positional-delete-layout-retest-20260913.md).

Attempt **42**, condition `holo31-all-roles-order35-optional-cleanup-retest-20260913-v2`, started at
`2026-09-13T08:06:05.035830+00:00`, supervisor PID **1424** / tool session **22688**, worker PID **1432**,
selected orders `[35]`, existing frozen validation `ok`. Freeze time **08:04:57 UTC**; config SHA-256:
`2f1d2f4e404b7294dece6dd418271b2728b99210c98b80bba9a3b48a727544da`.
New source SHA-256:
`441d865763794e3b6ce79a901b6439e766e84422e7cb8196b96f22d798434573`
(517 files / 81,181,540 bytes). Prior delete/layout fixes remain, with original Holo1 directly/serially,
both roles thinking, main/grounding temperature 0.8 and unchanged episode/resource limits. Source/tests
remain frozen until supervisor exit. Preserve interrupted attempt 41 and review actual residuals at the
two-attempt checkpoint; no other task or regression/control episode is run.

Only **Order 35 is retesting/running**. Counts are **19 isolated PASS, 7 skips, 42 episode attempts,
26 processed and 67 pending**. No new task PASS is established at launch; original **95/189** and the
promoted pointer remain unchanged.

## 2026-09-13 07:59 UTC Order 35 stopped unscored for a confirmed false completion prerequisite

Attempt **41** finalized at `2026-09-13T07:57:58.565437+00:00` as **interrupted/unscored**, 27 steps /
536.933 seconds, ten completion rejections, no evaluator execution or reward. Supervisor PID 33516 /
tool session 86248 exited **130**, verified by root, and worker PID 33543 exited **0** with final revalidation
`ok`; the supervisor final integrity record is absent. Both processes are gone. Results SHA-256:
`bf37e2e692f3bb61ac5a6a4684e51dfc1ebf406635e0c58389336848b8138204`.

Native layout **20 worked**: five new blank pages were created, all six images inserted and the presentation
saved. The initial page still retained two visible placeholders, so real cleanup remained. **No deletion
executed**; the positional-delete exception is therefore not yet live-verified. Starting at step 15,
completion wrongly required both `shape.delete` and `slide.delete` to succeed, even though the page count
was already correct and these are alternative cleanup strategies. This is a newly confirmed completion
contract defect, distinct from the model's unfinished work.

The developer stopped to repair that false prerequisite. The latest stop check included successful
`tools_search` at step 27 after repeated completion claims; do not describe this as proof of persistent
stall/no progress or as a finished task. The raw “by user” interrupt text is the runner's generic label,
not a new user stop request. Root and the assigned agent are addressing the mandatory pair while retaining
tool discovery, real-state/save review and generic placeholder usage; no new gate or legacy task plan is
introduced. These pending changes do not alter the preserved attempt. See the
[Order 35 report](archive/all-holo-order35-positional-delete-layout-retest-20260913.md).

**Order 35 remains diagnosing**. Counters stay **19 isolated PASS, 7 skips, 41 episode attempts,
26 processed and 67 pending**; this interruption adds no scored failure or PASS. No new episode has
launched. Original **95/189** and the promoted pointer remain unchanged.

## 2026-09-13 07:49 UTC Order 35 positional-delete and native-layout repairs launched

The preserved failure demonstrates a false duplicate-success rejection: deleting one object moves another
into the same positional path, so the next model-selected `shape.delete` can legitimately repeat its
arguments. The execution fix exempts only canonical Impress `shape.delete` from that rejection for direct
and forwarded calls. Native missing-object errors, repeated-error handling and other mutation protection
remain intact. **25 focused tests**, Ruff and diff checks passed, including two distinct synthetic objects
deleted at the same index with unchanged model arguments and native feedback after the collection is empty.

The owning `slide.create` description now explains insertion rather than navigation, and native **layout
20 = blank / 0 = title and subtitle**, independently checked against LibreOffice source. Direct, search and
forwarded structural checks plus Ruff passed; integer constraints, defaults and native behavior are unchanged.
The original task was still unfinished, with one valid save/readback completion rejection; it was not trapped
by repeated completion review. See the [Order 35 report](archive/all-holo-order35-positional-delete-layout-retest-20260913.md).

Attempt **41**, condition `holo31-all-roles-order35-positional-delete-layout-retest-20260913-v1`, started at
`2026-09-13T07:48:50.064741+00:00`, supervisor PID **33516** / tool session **86248**, worker PID **33543**,
selected orders `[35]`, frozen validation `ok`. Freeze time **07:47:26 UTC**; config SHA-256:
`65dc81eec37002667c224917cd1720ccb16a1cf1e653792d369c03b463a0655d`.
New source SHA-256:
`5a5ff22bc84394253b0b51a54c3b009d48afaf74ba64833b4535a6ef79de043d`
(517 files / 81,178,865 bytes). Both Holo roles are thinking on original Holo1 directly/serially at
`http://192.168.0.224:8002/v1`, with carried main temperature 0.8 and existing episode/resource limits.
Source/tests remain frozen until supervisor exit; no task PASS is established at launch.

The ledger remains **19 isolated PASS, 7 skips, 41 episode attempts, 26 processed and 67 pending**, with
only **Order 35 retesting/running**. Route, concurrency, sampling and cumulative source differ from the full
run; original **95/189** and the promoted pointer remain unchanged. No other episode, regression/control,
new gate, task macro, promotion or additional full evaluation was added.

## 2026-09-13 07:39 UTC Order 29 repeats wrong-picture failure and is skipped; Order 35 selected

Attempt **40** finalized at `2026-09-13T07:38:36.018729+00:00` as original-evaluator **failed**, reward
**0.0**, seven steps / 240.822 seconds, `agent_done`, with zero completion rejections. Supervisor PID 2939 /
tool session 77609 and worker PID 2947 exited **0**; both final integrity records are `ok`, and both processes
are gone. Results SHA-256:
`7594235a97124cccce42b15e4c5003f644ecec77c94d09a8951c32cac94d38b7`.

The sampled model again chose the portrait emblem's selector `[5]`. Existing feedback rejected contain and
stretch, after which the Adapter correctly applied cover to that exact model-selected object. The final
screenshot confirms the enlarged emblem; review still claimed the requested city image was complete.
This is the same **model visual-selection and completion-review failure**, without a demonstrated API,
feedback, transport or environment defect. Follow the prospective stop condition and **skip Order 29**;
retain both failures and add no unchanged replay, selector gate or offline-known target. See the
[Order 29 report](archive/all-holo-order29-visual-selection-sampling-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **19 isolated PASS,
7 skips, 40 episode attempts, 26/94 processed and 67 pending**. The actual next pending entry is queue
position 27 / **Order 35**, Impress task `bf4e9888-f10f-47af-8dba-76413038b73c`, now diagnosing with no
new episode or source change. Its original outcome was `agent_deadline_exhausted`; preserved
[triage](../experiments/work/all-holo-order35-triage-20260912.md) and
[duplicate-review evidence](../experiments/work/all-holo-order35-duplicate-review-20260912.md) are available.
Original **95/189** and the promoted pointer remain unchanged; no regression/control, new gate, promotion
or additional full evaluation was added.

## 2026-09-13 07:35 UTC Order 29 bounded sampling exploration launched after separate Calc save cleanup

After Order 28's PASS and supervisor exit, the existing strict Impress save overlay was extended to Calc,
removing redundant expert `filter_name` from the strict model schema. Shared usage explains `{}` for
in-place save and an explicit `.ods`/`.xlsx` URL for Save As; legacy expert filters remain available outside
that surface. Root verified **79 focused tests**, Ruff for both changed Python files, and direct/Multi-Apps
search structural checks. This later usability change is **not part of Order 28's PASS**, does not rerun it,
and is irrelevant to Order 29's Impress image-selection hypothesis. Adapter execution, gates and defaults
are unchanged. Details remain in the [Order 28 report](archive/all-holo-order28-direct-sampling-retest-20260913.md).

Read-only comparison confirms the relevant current picture descriptions were already present in Order 29's
original request. No code-fix or description-transfer claim is made. Attempt **40** is one explicit **main
temperature 0.8 sampling exploration**, versus original 0, using original Holo1 directly/serially; grounding
stays 0.8. If the same wrong-picture failure recurs, record the negative and skip without unchanged repeats.
Condition `holo31-all-roles-order29-visual-selection-sampling-20260913-v1` started at
`2026-09-13T07:34:20.982699+00:00`, supervisor PID **2939** / tool session **77609**, worker PID **2947**,
selected orders `[29]`, frozen validation `ok`. Freeze time **07:32:59 UTC**; config SHA-256:
`8e58cb2ba770c03d280eaf6d97e31ec83b51d6718cf4cdaa6d57ecea93e9d043`.
New cumulative source SHA-256:
`9d96171819a8e217701d773162bdba124199647c74bd80548468feb4eba1448a`
(517 files / 81,175,650 bytes). Both roles are thinking at `http://192.168.0.224:8002/v1`, with the existing
episode/resource limits. Source/tests remain frozen until the supervisor exits. See the
[Order 29 report](archive/all-holo-order29-visual-selection-sampling-20260913.md).

**Order 29 retesting/running** is the only current task; the ledger has **19 isolated PASS, 6 skips,
40 episode attempts, 25 processed and 68 pending**. The new condition does not isolate route, concurrency,
source and sampling effects. No control/regression, additional probe, new gate, promotion or full evaluation
was added; original **95/189** and the baseline pointer remain unchanged.

## 2026-09-13 07:26 UTC Order 28 recovered PASS; Order 29 selected from the remaining queue

Attempt **39** finalized at `2026-09-13T07:25:45.860465+00:00` as original-evaluator **PASS**, reward
**1.0**, 12 steps / 901.641 seconds, `agent_done`, with one completion rejection. Supervisor PID 21523 /
tool session 96299 and worker PID 21702 exited **0**; both final integrity records are **ok** and both
processes are gone. Results SHA-256:
`3a28f7cd4a9eaf57c79ff535a8c5813b04ef68f180315ce4be9da3dc60d9cd29`.

The same-settings replacement completed the task without adopting the negative presence-penalty probe or
changing the frozen source. Preserve attempt 38's operator-error interruption and the separate probe;
neither is an evaluator failure or a PASS. This result belongs to its original frozen inputs; any later
post-pass save-schema usability fix is separate and does not trigger a rerun of passed Order 28. See the
[Order 28 report](archive/all-holo-order28-direct-sampling-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **19 isolated PASS,
6 skips, 39 episode attempts, 25/94 processed and 68 pending**. Its actual next pending entry was queue
position 26 / **Order 29**, now current/diagnosing with **no episode launched**. The existing
[offline triage](../experiments/work/all-holo-order29-triage-20260912.md) attributes the original failure to
choosing the wrong picture despite available selectors, geometry, screenshot and actionable feedback;
selection of this queue item does not establish a new Adapter defect or authorize an unchanged replay.
Original full-run **95/189** and the promoted pointer remain unchanged. No regression/control, new gate,
promotion or additional full evaluation was added.

## 2026-09-13 07:10 UTC Order 28 same-settings replacement launched; presence probe negative

The one host-only presence-penalty probe finished at `2026-09-13T07:08:54.261667+00:00`, tool session
99363 exit **0**: HTTP 200, 202.626 seconds, 4096 completion tokens, `finish_reason=length`, and the same
parsed `workbook.inspect({})`. Source remained unchanged. This is **no improvement** in the observed
generation overhead/action; parsed schema validity does not establish complete native closing tags.
Presence penalty is **not adopted**, and the probe is excluded from episode/PASS counters.

Attempt **39** is one bounded replacement with the preceding settings because attempt 38 was mistakenly
interrupted after progress resumed. Preserve that operator-error interruption and the negative probe;
no preceding evaluator outcome exists to select against. Condition
`holo31-all-roles-order28-completion-retest-20260913-v1` started at `2026-09-13T07:10:30.753643+00:00`,
supervisor PID **21523** / tool session **96299**, worker PID **21702**, selected orders `[28]`, frozen
validation `ok`. Freeze time **07:09:49 UTC**; config SHA-256:
`553e69eb5a6daa05762726ff9d0aa0e8ca760404a5c3242275e2735a16098099`.
Unchanged source SHA-256:
`d8ba5bbceb6df264d77b943a54bf88f1aca046e83560551a9a40eab986e56644`
(517 files / 81,173,891 bytes). Both roles remain thinking on original Holo2 directly/serially, main and
grounding temperature **0.8**, with no presence override and unchanged existing episode/resource limits.
Let existing stall/restart handling and the original evaluator run; manual decisions must use the latest
action. See the [Order 28 report](archive/all-holo-order28-direct-sampling-retest-20260913.md).

**Order 28 retesting/running** remains the only current task. The ledger has **18 isolated PASS, 6 skips,
39 episode attempts, 24 processed and 69 pending**. No new source, tests, probes, other task, regression,
control, gate or full evaluation was added; original 95/189 and the baseline pointer remain unchanged.

## 2026-09-13 07:06 UTC Order 28 interrupted after progress had resumed; operator stop corrected

Attempt 38 finalized at `2026-09-13T07:04:12.688522+00:00` as **interrupted/unscored**, six steps /
571.663 seconds, without evaluator execution or reward. Supervisor PID 52594 / tool session 25559 exited
**130**, verified by root, and worker PID 52633 exited **0** with final revalidation `ok`; the supervisor
final integrity record is absent. Results SHA-256:
`0f1a808564fde0aad16a27fde1f4197f1d58860c5a3bf52ee0b69df5f45fbb97`.

The developer stopped using a stale step-3 snapshot. The finalized trace shows that **progress had already
resumed before SIGINT**: step 4 read the cells, step 5 wrote a header and step 6 wrote 24 model-selected
formulas, all successfully. This is an **operator decision error**, not evidence of a persistent model stall
or task failure. Two costly 4096-token generations preceded spontaneous recovery; the task's evaluator
outcome remains unknown. The runner's generic “by user” error text does not attribute this stop to the user.
Future manual stops must first refresh the latest action; no new runtime gate is introduced. See the
[Order 28 report](archive/all-holo-order28-direct-sampling-retest-20260913.md).

One separate host-only probe has started in tool session **99363**, frozen at 07:05:30.838434 UTC under
`experiments/work/all-holo-order28-presence-probe-20260913-v1`. It uses the unchanged existing driver and
captured step-2 request, retaining temperature 0.8 and changing only presence penalty to 1.0. The narrower
question is whether this reduces the measured generation overhead, not whether it repairs a proven terminal
failure. One request, zero retries, 240 seconds; no tool, VM or evaluator execution. It is excluded from
episode/PASS counters. **Order 28 remains diagnosing** with unchanged **18 isolated PASS, 6 skips,
38 episode attempts, 24 processed and 69 pending**. Original 95/189 and the baseline pointer remain unchanged.

## 2026-09-13 06:54 UTC Order 28 direct-Holo2 replay launched with explicit carried sampling

Original Order 28's first inspection-only request failed three times with Cloudflare HTTP 524 before any
Agent/Adapter action. There is no exercised calculation/formatting defect requiring a new source patch.
This direct original-Holo2 serial condition explicitly carries main temperature **0.8** from Order 27 after
its demonstrated whitespace-loop diagnosis, compared with original full-run **0**; grounding remains 0.8.
The setting belongs to this frozen condition, without changing a global runtime default.

Condition `holo31-all-roles-order28-direct-sampling-retest-20260913-v1` started at
`2026-09-13T06:54:29.835774+00:00`, supervisor PID 52594 / tool session 25559, worker PID 52633,
selected orders `[28]`, `frozen_condition.status=ok`. Frozen at 06:53:12 UTC; unchanged source SHA-256:
`d8ba5bbceb6df264d77b943a54bf88f1aca046e83560551a9a40eab986e56644`
(517 files / 81,173,891 bytes). Config SHA-256:
`0573219174a076df4620ed163ad7d9ded362569e7356a5701bdd064ae0dcdee2`.
Both roles remain thinking at `http://192.168.0.138:8001/v1`, one fresh guest, with existing limits. Direct
serving, serial concurrency, source and main sampling differ from the original full run; causal effects are
not isolated. See the [Order 28 report](archive/all-holo-order28-direct-sampling-retest-20260913.md).

Isolated episode attempt **38** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **18 isolated PASS, 6 skips, 24 processed and 69 pending**, with only Order 28 current. No
source/test change, probe, regression/control, new gate, promotion or full evaluation was added. Original
full-run 95/189 remains immutable.

## 2026-09-13 06:51 UTC Order 27 recovered PASS with sampled main generation; Order 28 selected

Attempt 37 finalized at `2026-09-13T06:47:39.753753+00:00` as original-evaluator **PASS**, reward **1.0**,
16 steps / 758.243 seconds, `agent_done`, with one completion rejection. Supervisor PID 13522 / tool session
89781 and worker PID 13587 exited **0**; both source integrity records are `ok`. Results SHA-256:
`6ffa5820af56cd2c076b849f422b7ae50d47238f08484838e276c9c8b1e62da1`.

The second real episode changed only main temperature to 0.8 and reached successful original scoring.
Order 27 is recovered. Preserve its first interrupted episode and both host-only token probes separately;
the probes executed no tools and are not scored episodes or passes. This isolated result does not establish
a general rate increase or silently change a global runtime default. See the
[Order 27 report](archive/all-holo-order27-chart-category-transfer-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **18 isolated PASS,
6 skips, 37 attempts, 24 processed and 69 pending**. Current **Order 28 diagnosing** originally ended in
`model_transport_failure` after three requests / 696.754 seconds on public Holo2, without evaluator execution;
raw step count is absent. No Order 28 episode has launched. Original full-run **95/189** and the promoted
pointer remain unchanged; no regression/control, new gate, promotion or full evaluation was added.

## 2026-09-13 06:35 UTC Order 27 main-temperature comparison launched after two host-only token probes

Both separate token probes completed without tool, VM or evaluator execution and with unchanged source.
At temperature 0, the preserved request emitted 4096 tokens in 202.353 seconds, including 4009 consecutive
tabs inside an unclosed function; no native closing boundary existed for the stop to match, although provider
parsing returned an inspect call. At 0.8, it emitted 286 tokens in 15.448 seconds, zero tabs and one real closed
call matching the stop. The sampled call changed to `chart.create` and omitted required `source_sheet`, so it
was schema-invalid and never executed. This is a decoding improvement, not a valid-tool or task PASS. Both
probe results are recorded under Order 27 and excluded from episode-attempt counters.

The second real episode changes only main temperature from 0 to 0.8; grounding was already 0.8. Condition
`holo31-all-roles-order27-sampling-retest-20260913-v1` started at
`2026-09-13T06:34:49.674763+00:00`, supervisor PID 13522 / tool session 89781, worker PID 13587,
selected orders `[27]`, `frozen_condition.status=ok`. Frozen at 06:34:19 UTC; unchanged source SHA-256:
`d8ba5bbceb6df264d77b943a54bf88f1aca046e83560551a9a40eab986e56644`
(517 files / 81,173,891 bytes). Config SHA-256:
`ebbc7720b638cc7ee8092cb02a24cb15858d47c510b027cebbfd7c6e5b1e6095`.
Source, prompts, schemas, thinking, native stop and limits remain unchanged. Existing schema/native feedback
must support the model's own corrections; no Runner argument repair or global default change is introduced.
See the [Order 27 report](archive/all-holo-order27-chart-category-transfer-retest-20260913.md).

Isolated episode attempt **37** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **17 isolated PASS, 6 skips, 23 processed and 70 pending**, with only Order 27 current. No unchanged
probe, parameter sweep, regression/control, new gate, promotion or full evaluation was added; full-run 95/189 remains immutable.

## 2026-09-13 06:22 UTC Order 27 generation loop interrupted; host-only token diagnosis planned

Attempt 36 finalized at `2026-09-13T06:22:10.169187+00:00` as **interrupted/unscored**, 5 steps and
896.225 seconds, with no evaluator/reward. Worker PID 23655 exited **0** and revalidation is `ok`;
supervisor PID 23562 exited **130 / KeyboardInterrupt**, verified by root from tool session 31716, and is
gone, with no final integrity record after interruption. Results SHA-256:
`d4fc41e3c018057945517bd14c7e17786a90848bc27a24677c40b52c03922423`.
The raw error says “by user,” but this was a developer diagnostic stop, not an environment block or user stop.

After successful sorting, steps 3–5 repeated the same inspection, each reporting 4096 completion tokens,
`finish_reason=length` and roughly 202 seconds. Parsed step 3 was short and Adapter execution took 0.420
seconds; chart creation was never reached despite its current category guidance being present. Neither
long hidden reasoning nor stop mismatch is established by the parsed message. **Order 27 remains diagnosing**.
After exit, one host-only probe launched in tool session **78680**, using the unchanged existing driver and
preserved step-3 request with unchanged generation inputs and only token/logprob instrumentation, zero retries
and a 240-second cap. Its independent condition records source/request/driver hashes in
`experiments/work/all-holo-order27-generation-tokens-probe-20260913-v1`. It executes no tool, VM or evaluator
and does not count as a scored attempt/PASS. See the
[Order 27 report](archive/all-holo-order27-chart-category-transfer-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) remains **17 isolated PASS,
6 skips, 36 attempts, 23 processed and 70 pending**. No source change, new gate, regression/control, promotion
or full evaluation was added; original full-run 95/189 remains immutable.

## 2026-09-13 06:07 UTC Order 27 existing chart-category contract transfer launched

Independent offline comparison confirms original Order 27 sorted and saved the sheet correctly. Its model-
selected `row_headers=false` instead plotted dates and quantities as two value series without categories.
Actual requests retained the full series count, ranges, empty categories and review guidance. Existing
cumulative chart descriptions now explain that categories can be dates/numbers and describe both flag choices,
so this replay transfers that unchanged contract without a new source patch or repeated test campaign.

Condition `holo31-all-roles-order27-chart-category-transfer-retest-20260913-v1` started at
`2026-09-13T06:07:02.882130+00:00`, supervisor PID 23562 / tool session 31716, worker PID 23655,
selected orders `[27]`, `frozen_condition.status=ok`. Frozen at 06:06:05 UTC; unchanged source SHA-256:
`d8ba5bbceb6df264d77b943a54bf88f1aca046e83560551a9a40eab986e56644`
(517 files / 81,173,891 bytes). Config SHA-256:
`c2fb9f18014237bb99f150e60e69dac30822ae19e4d1511382c315702914e51d`.
Both roles remain thinking on original Holo2 directly/serially with existing limits. The model owns category
flags and every semantic argument; only original evaluator PASS counts. See the
[Order 27 report](archive/all-holo-order27-chart-category-transfer-retest-20260913.md).

Isolated attempt **36** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **17 isolated PASS, 6 skips, 23 processed and 70 pending**, with only Order 27 current. No
regression/control, unchanged flag replay, new gate, promotion or full evaluation was added. Original full-run
95/189 remains immutable.

## 2026-09-13 06:03 UTC Order 26 recovered PASS; Order 27 selected for diagnosis

Attempt 35 finalized at `2026-09-13T06:02:31.349778+00:00` as original-evaluator **PASS**, reward **1.0**,
12 steps / 433.774 seconds, `agent_done`, with one completion rejection. Supervisor PID 62282 / tool session
56137 and worker PID 62320 exited **0**; both source integrity records are `ok`. Results SHA-256:
`1218c1ce3d015ede7cc808f74d3d82612340b3e08f3f6f6ac0498086c07d67d5`.

Initial inspection and model-selected zoom calls succeeded; the original first-request HTTP 524 did not
recur. A save-filter error reached the model with the selected/required names, and its next call corrected
the filter. Original scoring confirms recovery. No new Order 26 source patch was required; direct transport,
serial concurrency and cumulative source prevent unique attribution to the endpoint route. See the
[Order 26 report](archive/all-holo-order26-direct-transport-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **17 isolated PASS,
6 skips, 35 attempts, 23 processed and 70 pending**. Current **Order 27 diagnosing** originally completed
`agent_done` after 10 steps / 1079.474 seconds on public Holo2 but received evaluator reward 0. Existing offline
triage is preserved; no Order 27 episode has launched. Original full-run 95/189 and the promoted pointer remain
unchanged; no regression/control, repeated passed task, new gate, promotion or full evaluation was added.

## 2026-09-13 05:55 UTC Order 25 post-pass fixes completed; Order 26 direct-transport attempt launched

Both demonstrated Order 25 follow-ups are complete without rerunning that passed task. The inferred date-column
`fill_down` requirement is removed while explicit fill requests and optional catalog discovery remain; 30
focused tests and Ruff passed. Full-range formatting remains unchanged, but immediate readback is bounded to
32×16 with returned bounds/truncation retained in context; 20 focused tests and Ruff passed. The earlier
120-second timeout and unbounded readback were demonstrated, though exact native-assignment versus readback
timing was not measured. These later fixes do not explain or alter the already-frozen Order 25 PASS.

Original Order 26 stopped before its first action because all three initial inspection requests hit the public
Holo2 proxy's HTTP 524. A direct serial replay needs no new task-specific source change. Condition
`holo31-all-roles-order26-direct-transport-retest-20260913-v1` started at
`2026-09-13T05:55:01.294470+00:00`, supervisor PID 62282 / tool session 56137, worker PID 62320,
selected orders `[26]`, `frozen_condition.status=ok`. Frozen at 05:54:28 UTC; source SHA-256:
`d8ba5bbceb6df264d77b943a54bf88f1aca046e83560551a9a40eab986e56644`
(517 files / 81,173,891 bytes). Config SHA-256:
`e8b99bb1272ff6ed01ba603626c81f2e14d9a08cc5e15e1c78a9081fcf3ba6d4`.
Both roles remain thinking on original Holo2 directly/serially with existing limits. See the
[Order 26 report](archive/all-holo-order26-direct-transport-retest-20260913.md).

Isolated attempt **35** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **16 isolated PASS, 6 skips, 22 processed and 71 pending**, with only Order 26 current. No
regression/control, unchanged replay, new gate, promotion or full evaluation was added. Original full-run
95/189 remains immutable.

## 2026-09-13 05:46 UTC Order 25 recovered PASS; two demonstrated generic follow-ups and Order 26 selected

Attempt 34 finalized at `2026-09-13T05:45:40.390763+00:00` as original-evaluator **PASS**, reward **1.0**,
31 steps / 1351.211 seconds, `agent_done`, with five completion rejections. Supervisor PID 63514 / tool
session 58620 and worker PID 63543 exited **0** and are gone; both source integrity checks are `ok`.
Results SHA-256: `e6ebe10def3b1d4881eb2b2508be626b1a58a19b1cda0e2a1b22af5a1b0e179c`.

The original header succeeded, followed by model-authored date formulas, recovery from literal-text/native-
separator mistakes and date-format correction. Original scoring confirms recovery. This successful trajectory
also demonstrated two generic issues: mandatory `range.fill_down` despite explicit formulas for every date
cell, and unbounded whole-column `range.format` readback causing a 120-second timeout. These will receive
focused post-pass fixes after process exit; no replacement gate or repeat of the already-passed Order 25 is
planned. The finalized result remains tied to its existing source seal. See the
[Order 25 report](archive/all-holo-order25-literal-cell-transfer-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **16 isolated PASS,
6 skips, 34 attempts, 22 processed and 71 pending**. Current **Order 26 diagnosing** originally ended in
`model_transport_failure` after three requests / 801.902 seconds on public Holo2, without evaluator execution;
raw step count is absent. No Order 26 episode has launched. Original full-run 95/189 and the promoted pointer
remain unchanged; no regression/control, promotion or full evaluation was added.

## 2026-09-13 05:23 UTC Order 25 transferred literal-cell compatibility attempt launched

Original Order 25 inspected the workbook, then repeated the same plain-string header call three times against
the old typed-only schema. Exact errors and full typed-cell usage reached retries; no HTTP or feedback-loss
failure was found. Existing generic literal-cell support now accepts every original call unchanged through
generated public schema and Adapter validation, with one-string-cell native orientation. This current-task
replay adds no new source patch or test campaign; the unexecuted later formula/save plan still requires scoring.

Condition `holo31-all-roles-order25-literal-cell-transfer-retest-20260913-v1` actually started at
`2026-09-13T05:22:55.247729+00:00`, supervisor PID 63514 / tool session 58620, worker PID 63543,
selected orders `[25]`, `frozen_condition.status=ok`. Frozen at 05:22:12 UTC; unchanged source SHA-256:
`10addfe8da9b9abfb3b148be5d13865d85e7be8bd57fd031a263e98bc72d47ee`
(517 files / 81,160,371 bytes). Config SHA-256:
`88695cb5d0effaef33b12f8eee92d2e8459e8f3680148d1668530e5facd295da`.
Both roles use thinking on original Holo2 directly at `http://192.168.0.138:8001/v1`, serially with existing
limits. Source, route and concurrency differ from the full run; no isolated causality is claimed. See the
[Order 25 report](archive/all-holo-order25-literal-cell-transfer-retest-20260913.md).

Isolated attempt **34** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **15 isolated PASS, 6 skips, 21 processed and 72 pending**, with only Order 25 current. No
regression/control, unchanged replay, new gate, promotion or full evaluation was added. Original full-run
95/189 remains immutable.

## 2026-09-13 05:19 UTC Order 24 failed despite intact native feedback; documented skip and Order 25 selected

Attempt 33 finalized at `2026-09-13T05:18:17.486306+00:00` as original-evaluator **failed**, reward **0.0**,
14 steps / 771.372 seconds, `agent_done`, with no completion rejection. Supervisor PID 28956 / tool session
17832 and worker PID 28985 exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`91e5f7c572033d732d558232e283910f7c239ed881ede751ce3cb5fd9564af8f`.

The merged-title anchor hint corrected the write. Actual requests 9–12 retained the native 100% pivot values
and complete denominator descriptions. Step 13 fully read the output sheet, still showing 100%, title overlap
and output extending to column F; the model then claimed completion at step 14. No further implementation or
feedback gap was demonstrated. **Skip Order 24 after two affected attempts**, retaining the generic native
readback/error-hint fixes without claiming task recovery. Preserve both scored failures; add no third unchanged
replay, gate or reference-layout injection. See the
[Order 24 report](archive/all-holo-order24-pivot-percentage-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **15 isolated PASS,
6 skips, 33 attempts, 21 processed and 72 pending**. Current **Order 25 diagnosing** originally ended in
`model_protocol_failure` after three structured-protocol attempts / 147.232 seconds on public Holo2, without
evaluator execution; raw step count is absent. No isolated Order 25 episode has launched. Original full-run
95/189 and the promoted pointer remain unchanged; no regression/control, promotion or full evaluation was added.

## 2026-09-13 05:05 UTC Order 24 native pivot-output feedback attempt launched

The second current-Order-24 hypothesis returns actual pivot display strings immediately after creation,
using the existing native reader with a 32×16 preview, returned range and truncation flags. Readback errors
remain visible without invalidating successful creation; complete output bounds and model arguments stay
unchanged. Context projection retains the new feedback. The existing matrix-size error also receives the
merged top-left-anchor hint already present for flat arrays; validation is unchanged. This addresses missing
immediate pivot values and the prior hidden duplicate-title mistake without new gates or reference-placement
hints. All **98 distinct focused tests** and Ruff passed; runtime/source changes occurred after attempt 32 exited.

Condition `holo31-all-roles-order24-pivot-readback-retest-20260913-v1` actually started at
`2026-09-13T05:05:12.392342+00:00`, supervisor PID 28956 / tool session 17832, worker PID 28985,
selected orders `[24]`, `frozen_condition.status=ok`. Frozen at 05:04:33 UTC; source SHA-256:
`10addfe8da9b9abfb3b148be5d13865d85e7be8bd57fd031a263e98bc72d47ee`
(517 files / 81,160,371 bytes). Config SHA-256:
`fce4f6a6848433e10a249b488f0266090be3d6d18cc28a1c04c7445da6516164`.
Both roles remain thinking on original Holo2 directly/serially with the existing limits. Review both affected
attempts after the terminal outcome before any extension. See the
[Order 24 report](archive/all-holo-order24-pivot-percentage-retest-20260913.md).

Isolated attempt **33** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **15 isolated PASS, 5 skips, 20 processed and 73 pending**. No regression/control, unchanged replay,
new gate, promotion or full evaluation was added. Original full-run 95/189 remains immutable.

## 2026-09-13 04:56 UTC Order 24 scored failed; native pivot-output feedback diagnosis continues

Attempt 32 finalized at `2026-09-13T04:55:37.304058+00:00` as original-evaluator **failed**, reward **0.0**,
15 steps / 635.228 seconds, `agent_done`, with no completion rejection. Supervisor PID 50438 / tool session
20781 and worker PID 50476 exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`615528969662fe3039e30b882f347d7afeb191ed79ea06dbfe85531be34f8a54`.

The model corrected source bounds and count fields but retained `row_percentage`. Its raw pivot-create
responses contained output rectangles without values; screenshots stayed on the source page until all pivots
were created. **Order 24 remains current, diagnosing** for a minimal bounded native pivot-output readback
repair, so actual created values can inform the next model decision. Model-selected denominator, range and
placement remain unchanged; no new gate is planned. No second episode has launched. See the
[Order 24 report](archive/all-holo-order24-pivot-percentage-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) remains **15 isolated PASS,
5 skips, 32 attempts, 20 processed and 73 pending**. No regression/control, unchanged replay, promotion or
full evaluation was added. Original full-run 95/189 and the promoted pointer remain unchanged.

## 2026-09-13 04:45 UTC Order 24 pivot-percentage/source-range guidance attempt launched

Original Order 24's title/merge/formatting and table spacing succeeded, but its raw calls selected row
percentages for category shares and omitted the final source record without reading the cells. Existing public
field descriptions now explain competing percentage denominators and complete header/data source bounds.
Only text in `calc_adapter/tool_manifest.py` and `integrations/lite_agent/tool_catalog.py` changed; field
types/enums, execution and validation remain unchanged. All 11 existing pivot-display-schema tests and Ruff
passed. Reference-only layout differences stay host-side; no exact anchor hint, new API or gate is introduced.

Condition `holo31-all-roles-order24-pivot-percentage-retest-20260913-v1` actually started at
`2026-09-13T04:44:47.224424+00:00`, supervisor PID 50438 / tool session 20781, worker PID 50476,
selected orders `[24]`, `frozen_condition.status=ok`. Frozen at 04:44:17 UTC; source SHA-256:
`95ac27978b8e4876f3ca5ecefe118158c8bbc854cf9b697cc6d6aa6aad1a5002`
(517 files / 81,152,305 bytes). Config SHA-256:
`a4e07ee540ca6fea811a818a2db034d677a9458fd5da154576cc085314f5f438`.
Both roles use thinking on original Holo2 directly at `http://192.168.0.138:8001/v1`, serially with the same
100 global / 50 local steps, one soft restart, 1800 Agent seconds and 30 GiB disk stop. Source, route and
concurrency differ from the full run; only original evaluator PASS counts. See the
[Order 24 report](archive/all-holo-order24-pivot-percentage-retest-20260913.md).

Isolated attempt **32** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **15 isolated PASS, 5 skips, 20 processed and 73 pending**, with only Order 24 current. No
regression/control, unchanged replay, new gate, promotion or full evaluation was added. Original full-run
95/189 remains immutable.

## 2026-09-13 04:39 UTC Order 23 recovered PASS after fixed-decimal-text guidance; Order 24 selected

Attempt 31 finalized at `2026-09-13T04:38:03.488743+00:00` as original-evaluator **PASS**, reward **1.0**,
17 steps / 990.534 seconds, `agent_done`, with one completion rejection. Supervisor PID 3240 / tool session
2602 and worker PID 3279 exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`ebfd62cc997068086bf0af7383437d7d2c66674eb1dd6b0998adf6d6927b9b73`.

The model filled both source formulas and wrote the header, then authored a native `TEXT` formula with the
instructed two-decimal representation at step 12. Its first formula submission succeeded, followed by fill,
save at step 15 and readback at step 16. Required tools and full source cells were present during earlier
repeated inspections; no retrieval omission or developer workbook intervention was found. Order 23 is
recovered, with all three attempts preserved separately. See the
[Order 23 report](archive/all-holo-order23-literal-cell-transfer-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **15 new isolated PASS,
5 skips, 31 attempts, 20 processed tasks and 73 pending tasks**. Current **Order 24 diagnosing** originally
completed `agent_done` after 17 steps / 994.583 seconds on public Holo2 but received evaluator reward 0. No
isolated Order 24 episode has launched. Original full-run **95/189** and the promoted baseline pointer remain
unchanged; isolated recovery does not establish an integrated success-rate increase. No control/regression,
new gate, promotion or full evaluation was added.

## 2026-09-13 04:21 UTC Order 23 fixed-decimal-text attempt launched after documented checkpoint extension

Offline comparison of all 150 cells from attempt 30 isolated score-relevant differences to 10 combined-data
cells containing 19 number fragments missing trailing zeros. Numeric values, labels, order and punctuation
match; A–D match at evaluator precision and B/D formulas match exactly. Three tiny pre-existing A-cell
floating-point differences are not score-relevant. This complete saved output supports one distinct hypothesis
after the two-attempt checkpoint: teach numeric rounding versus fixed-width text, with a synthetic three-decimal
example and an explicit trailing-zero description for existing `formatted_text`. Artifact differences stay
host-side. Only manifest descriptions changed; Ruff and schema structural validation passed, without repeating
the prior 18 tests or adding tests, APIs, gates, automatic rewrites or task-specific values.

Condition `holo31-all-roles-order23-fixed-decimal-text-retest-20260913-v1` started at
`2026-09-13T04:21:18.372430+00:00`, supervisor PID 3240 / tool session 2602, worker PID 3279,
selected orders `[23]`, `frozen_condition.status=ok`. Frozen at 04:20:49 UTC; source SHA-256:
`3d5278e7a0486b7be41ee3866877db3a6b67073dc7cce1e0473aacf927bc2cb3`
(517 files / 81,151,578 bytes). Config SHA-256:
`72a7f393290fcceb222f5d9840c317656d78f22e84e420d8237ffb3407f65dc5`.
Both roles remain thinking on original Holo2 directly/serially with the same limits. This is the third distinct
current-task hypothesis; if the same misunderstanding persists without a new concrete contract defect, document
and skip instead of an unchanged fourth replay. See the
[Order 23 report](archive/all-holo-order23-literal-cell-transfer-retest-20260913.md).

Isolated attempt **31** is running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **14 isolated PASS, 5 skips, 19 processed and 74 pending**. No regression/control, new gate, promotion
or full evaluation was added. Original full-run 95/189 remains immutable.

## 2026-09-13 04:17 UTC Order 23 formula-usage attempt scored failed; offline artifact diagnosis pending

Attempt 30 finalized at `2026-09-13T04:16:35.031704+00:00` as original-evaluator **failed**, reward **0.0**,
19 steps / 773.837 seconds, `agent_done`, after one completion rejection. Supervisor PID 33992 / tool session
6793 and worker PID 34046 exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`c16e8c0679be39e2338c25a7eaaf924ffe31de83c8f7f19d4af80eba62109aac`.

This episode completed naturally and was scored. Attempt 29 remains separately preserved as developer-
interrupted and unscored. **Order 23 stays current, diagnosing**, while offline comparison of the persisted
artifact identifies the remaining output mismatch. No further attempt has launched; reaching `agent_done`
does not count as task success. See the [Order 23 report](archive/all-holo-order23-literal-cell-transfer-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) remains **14 isolated PASS,
5 skips, 30 attempts, 19 processed and 74 pending**. No new gate, regression/control, unchanged replay,
promotion or full evaluation was added. Original full-run 95/189 and the promoted pointer remain unchanged.

## 2026-09-13 04:03 UTC Order 23 formula-usage clarification attempt launched

The second current-Order-23 attempt changes only public formula/action descriptions and existing error
recovery text in `calc_adapter/tool_manifest.py` and `calc_adapter/uno_worker.py`. A synthetic native-function
example distinguishes semicolon arguments from punctuation inside quoted literal output; existing
`formatted_text` is mentioned as an alternative. Model arguments, native execution/errors, rollback and gates
are unchanged. All 18 existing focused formula-error tests and Ruff passed; independent review found no
task-specific content or execution change. Source changes occurred only after attempt 29 fully exited.

Condition `holo31-all-roles-order23-formula-usage-retest-20260913-v1` started at
`2026-09-13T04:03:29.947647+00:00`, supervisor PID 33992 / tool session 6793, worker PID 34046,
selected orders `[23]`, `frozen_condition.status=ok`. Frozen at 04:02:55 UTC; source SHA-256:
`e95dab7c36667e116defc4e92ac4496fba3439613aab67a8a6319e363070e8ea`
(517 files / 81,150,983 bytes). Config SHA-256:
`20809c883508bfd4fdb743e469d370b87c1e1c01c84503cbd1843a25c8e8ae3c`.
Both roles remain thinking on original Holo2 at `http://192.168.0.138:8001/v1`, one fresh guest, with existing
100 global / 50 local steps, one soft restart, 1800 Agent seconds and 30 GiB disk stop. Review this second
affected attempt on terminal evidence; preserve any documented diagnostic stop. See the
[Order 23 report](archive/all-holo-order23-literal-cell-transfer-retest-20260913.md).

This is isolated attempt **30**, running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **14 isolated PASS, 5 skips, 19 processed and 74 pending**. No regression/control, unchanged replay,
new gate, promotion or full evaluation was added. Original full-run 95/189 remains immutable.

## 2026-09-13 04:01 UTC Order 23 literal support confirmed; diagnostic interrupted for formula-usage repair

Attempt 29 finalized at `2026-09-13T04:00:26.701097+00:00` as **interrupted/unscored**, 12 steps and
943.495 seconds, with no evaluator/reward. Supervisor PID 59977 / tool session 76659 exited **130**;
worker PID 60002 exited **0** and both are gone. Worker revalidation is `ok`; supervisor final integrity is
absent. The generic raw error says “by user,” but this was a developer diagnostic stop. Results SHA-256:
`084aae8e4ea8be77c804af769db711c8d75704184e9711d93a9c69e3b3140921`.

The existing literal-cell repair transferred: the original header succeeded at step 7, after step 6 filled
56 formula cells. Three subsequent concatenation formulas raised native error 508 and rolled back. Exact
recovery reached the model, but it kept commas as function separators and changed quoted output punctuation
instead. It then repeated a completed fill and inspected, with step 12 saturating 4096 output tokens. No
concatenation formula succeeded. This bounded stop does not establish evaluator failure or complete-task recovery.

**Order 23 remains current, diagnosing.** The next small repair will place native function-argument syntax
beside the formula field and distinguish quoted literal punctuation in existing error feedback, using a
synthetic example and preserving every model formula unchanged. A new freeze and current-task attempt follow
focused verification; no second episode has launched, and no new gate, regression/control or unchanged replay
is added. See the [Order 23 report](archive/all-holo-order23-literal-cell-transfer-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) remains **14 isolated PASS,
5 skips, 29 attempts, 19 processed and 74 pending**. Original full-run 95/189 and the promoted pointer remain unchanged.

## 2026-09-13 03:45 UTC Order 23 transferred literal-cell repair attempt launched

Original Order 23 completed eight actions, then a plain-string header hit the old typed-cell-only schema.
The terminal sequence was one protocol error followed by two public-Holo2 HTTP 524s; exact schema feedback
and typed-cell usage remained available. Current Order 6 generic literal-cell support accepts the original
rejected arguments unchanged in both public schema and Adapter validation. This replay tests that existing
repair plus original Holo2 directly/serially, with no new Order 23 source patch.

Condition `holo31-all-roles-order23-literal-cell-transfer-retest-20260913-v1` actually started at
`2026-09-13T03:44:31.664646+00:00`, supervisor PID 59977 / tool session 76659, worker PID 60002,
selected orders `[23]`, `frozen_condition.status=ok`. Frozen at 03:40:52 UTC; source SHA-256:
`9ff5e0204adef6cbf80f0a8585d589fe1805e3944d9dadb3002be5abba99836c`
(517 files / 81,149,996 bytes). Config SHA-256:
`1ee5f53338a5ec8834e66100ce1d9f97c097980605dd7ad6c2dc56c1c8ebad49`.
Both roles use thinking on original Holo2 at `http://192.168.0.138:8001/v1`; 100 global / 50 local steps,
one soft restart, 1800 Agent seconds and 30 GiB disk stop remain. Removing one schema obstacle does not prove
the remaining concatenation/save task will succeed. Source, route and concurrency differ from the full run;
no isolated source/transport-causality claim is made. See the
[Order 23 report](archive/all-holo-order23-literal-cell-transfer-retest-20260913.md).

This is isolated attempt **29**, running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains at **14 new isolated PASS, 5 skips, 19 processed and 74 pending**, with only Order 23 current. No
source/test change, new gate, regression/control episode, promotion or full evaluation was added. Original
full-run 95/189 remains immutable.

## 2026-09-13 03:35 UTC Order 22 recovered PASS; Order 23 selected

Order 22 finalized at `2026-09-13T03:34:02.860607+00:00` as original-evaluator **PASS**, reward **1.0**,
6 steps / 177.111 seconds, `agent_done`, with no completion rejection. Supervisor PID 34106 / tool session
44580 and worker PID 34164 exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`546abedc52657d79cf57aeed0b26947afa2a6d2e7b366294890c3f4c0b15e6a2`.

The model read the workbook, selected column reordering, saved, inspected and completed. Direct original
Holo2 requests enabled these actions; no new Order 22 source patch or gate was required. Route, concurrency
and cumulative source differ from the full run, so isolated transport causality is not claimed. See the
[Order 22 report](archive/all-holo-order22-direct-transport-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **14 new isolated PASS,
5 skips, 28 attempts, 19 processed tasks and 74 pending tasks**. Current **Order 23 diagnosing** originally
ended in `model_protocol_failure` after three structured-protocol attempts / 817.957 total seconds on public
Holo2, without evaluator execution; raw step count is absent. No isolated Order 23 episode has launched.
Original full-run **95/189** and the promoted baseline pointer remain unchanged; no control/regression episode,
new gate, promotion or full evaluation was added.

## 2026-09-13 03:31 UTC Order 22 direct-Holo2 single-task attempt launched

Original Order 22's first inspection-only request exhausted three public-Holo2 HTTP 524 attempts before any
Agent action. Its manifest records zero steps and Adapter calls, with no tool feedback demonstrating an API
defect. This replay uses original Holo2 directly and serially on cumulative source, without an Order 22 patch.

Condition `holo31-all-roles-order22-direct-transport-retest-20260913-v1` started at
`2026-09-13T03:30:52.836363+00:00`, supervisor PID 34106 / tool session 44580, worker PID 34164,
selected orders `[22]`, `frozen_condition.status=ok`. Freeze time 03:30:33 UTC; source SHA-256:
`9ff5e0204adef6cbf80f0a8585d589fe1805e3944d9dadb3002be5abba99836c`
(517 files / 81,149,996 bytes). Config SHA-256:
`a9156db700a8bdac39daf4dad6e378a254aec203bc5d15f9317fc5cb4c0fe476`.
Both roles use thinking on **original Holo2** at `http://192.168.0.138:8001/v1`, one fresh guest.
Existing 100 global / 50 local steps, one soft restart, 1800 Agent seconds and 30 GiB disk stop remain.
Route, concurrency and source differ from the full run, so isolated transport causality is not claimed.
See the [Order 22 report](archive/all-holo-order22-direct-transport-retest-20260913.md).

This is isolated attempt **28**, running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains at **13 new isolated PASS, 5 skips, 18 processed and 75 pending**, with only Order 22 current. No
source/test change, new gate, regression/control episode, promotion or full evaluation was added. Original
full-run 95/189 remains immutable.

## 2026-09-13 03:28 UTC Order 21 recovered PASS; Order 22 selected

Order 21 finalized at `2026-09-13T03:27:15.813992+00:00` as original-evaluator **PASS**, reward **1.0**,
6 steps / 578.727 seconds, `agent_done`. Supervisor PID 4959 / tool session 59112 and worker PID 5011
exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`edaa7c6b133a6a89c90d319c8c3266a94308d8845e7bed700fabec4d0981d43c`.

The model finished formatting, saving and readback after one existing completion rejection. No new Order 21
source patch or gate was required. This direct serial result includes cumulative source differences from
the full run and does not isolate transport causality. See the
[Order 21 report](archive/all-holo-order21-direct-transport-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **13 new isolated PASS,
5 skips, 27 attempts, 18 processed tasks and 75 pending tasks**. Current **Order 22 diagnosing** originally
ended in `model_transport_failure` after three requests / 887.852 total seconds, without evaluator execution.
Original worker-08 metadata identifies public **Holo2**. No isolated Order 22 episode has launched. Original
full-run **95/189** and the promoted baseline pointer remain unchanged; no control/regression episode, new gate,
promotion or full evaluation was added.

## 2026-09-13 03:17 UTC Order 21 direct-transport single-task attempt launched

Original Order 21 formatted its model-selected range and saved after an existing completion rejection, but
request 5 exhausted three public-Holo1 HTTP 524 attempts. Successful save feedback and usable read/inspect
schemas remained in the request; no new schema/protocol or feedback defect was demonstrated. The replay uses
original Holo1 directly and serially on cumulative source, with no new Order 21 patch.

Condition `holo31-all-roles-order21-direct-transport-retest-20260913-v1` started at
`2026-09-13T03:17:25.749024+00:00`, supervisor PID 4959 / tool session 59112, worker PID 5011,
selected orders `[21]`, `frozen_condition.status=ok`. Freeze time 03:17:02 UTC; source SHA-256:
`9ff5e0204adef6cbf80f0a8585d589fe1805e3944d9dadb3002be5abba99836c`
(517 files / 81,149,996 bytes). Config SHA-256:
`1d5ce2bcffda680e0971a319d206591298585620b3ea912eb980ebbc56b13089`.
Both roles retain thinking on `http://192.168.0.224:8002/v1`; 100 global / 50 local steps, one soft restart,
1800 Agent seconds and 30 GiB disk stop remain. Route, concurrency and source differ from the full run, so
isolated transport causality is not claimed. See the [Order 21 report](archive/all-holo-order21-direct-transport-retest-20260913.md).

This is isolated attempt **27**, running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains at **12 new isolated PASS, 5 skips, 17 processed and 76 pending**, with only Order 21 current. No
source/test change, new gate, regression/control episode, promotion or full evaluation was added. Original
full-run 95/189 remains immutable.

## 2026-09-13 03:15 UTC Order 20 recovered PASS; Order 21 selected

Order 20 finalized at `2026-09-13T03:14:34.822289+00:00` as original-evaluator **PASS**, reward **1.0**,
8 steps / 388.942 seconds, `agent_done`. Supervisor PID 51990 / tool session 92107 and worker PID 52025
exited **0**; supervisor and worker source integrity are `ok`. Results SHA-256:
`00a551882af03bb790a4185d38dfc5e769a0292e17b73652e290d13e44bd806b`.

The model correctly transformed 28 cells and saved. An existing completion rejection requested missing
readback; the model inspected the workbook and then completed. This recovered task needed no Order 20 source
patch or new gate. Direct transport, serial concurrency and cumulative source differ from the full run, so no
isolated transport-causality claim is made. See the [Order 20 report](archive/all-holo-order20-direct-transport-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **12 new isolated PASS,
5 skips, 26 attempts, 17 processed tasks and 76 pending tasks**. Current **Order 21 diagnosing** originally
ended in `model_transport_failure` after three requests / 835.984 total seconds on public Holo1, without
evaluator execution. No isolated Order 21 episode has launched. Original full-run **95/189** and the promoted
baseline pointer remain unchanged; no regression/control episode, new gate, promotion or full evaluation was added.

## 2026-09-13 03:08 UTC Order 20 direct-transport single-task attempt launched

Original Order 20 completed a model-selected 28-cell text transformation and recovered from explicit
save-filter errors, but request 8 then exhausted three public-Holo1 HTTP 524 attempts before another proposal.
The preserved trace demonstrates no new execution/error-delivery defect. This current-task replay adds no
Order 20 source patch; cumulative repairs and direct serial transport may permit readback/review and scoring.

Condition `holo31-all-roles-order20-direct-transport-retest-20260913-v1` started at
`2026-09-13T03:07:54.776871+00:00`, supervisor PID 51990 / tool session 92107, worker PID 52025,
selected orders `[20]`, `frozen_condition.status=ok`. Freeze time 03:06:51 UTC; source SHA-256:
`9ff5e0204adef6cbf80f0a8585d589fe1805e3944d9dadb3002be5abba99836c`
(517 files / 81,149,996 bytes). Config SHA-256:
`e7bf6d239be9b8779b08d97fd4e3f38f0d09cb38a1e3f1f7bb5d3b2a6cd6326e`.
Both Holo roles use thinking on original Holo1 directly at `http://192.168.0.224:8002/v1`, serially.
Order 19's non-thinking diagnostic is not adopted globally. Existing 100 global / 50 local steps, one soft
restart, 1800 Agent seconds and 30 GiB disk stop remain. Route, concurrency and cumulative source differ
from the full run; no isolated transport-causality claim is made.

This is isolated attempt **26**, running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains at **11 new isolated PASS, 5 skips, 16 processed and 77 pending**, with Order 20 current. No control/
regression episode, new source/test change, gate, promotion or full evaluation was added. Original full-run
95/189 remains immutable. See the [Order 20 report](archive/all-holo-order20-direct-transport-retest-20260913.md).

## 2026-09-13 03:02 UTC Order 19 scored failure and documented skip; Order 20 selected

Attempt 25 finalized at `2026-09-13T02:59:50.891539+00:00` as original-evaluator **failed**, reward **0.0**,
26 steps / 336.425 seconds, `stalled_no_progress`. Supervisor PID 25686 and worker PID 25696 both exited
**0**, with supervisor and worker source integrity `ok`. This episode ended naturally and was scored;
attempt 24 remains a distinct developer-interrupted, unscored result. Attempt 25 results SHA-256:
`00e33fb1884a05f08a6b5355d46b0b2c9ce7cee79e779e965c3a6016e8916146`.

All 27 main non-thinking responses finished with `tool_calls`, without thinking or output-cap hits: maximum
346 completion tokens, median 6.33 seconds, mean 7.02 seconds and maximum 20.64 seconds. The model repeatedly
selected invalid matrix dimensions despite complete shape usage and the 7×1 versus 7×2 native error retained
in the latest request. No numeric/formula write succeeded; step 13 did format a blank range successfully.
The episode reached existing stalled-progress termination. Thinking had already ignored complete scaling guidance/readback and
produced two output-cap stalls. At the two-attempt checkpoint, **skip Order 19**: no further evidence-backed
reusable runtime repair is justified. Keep the generic scaling contract fixes without claiming task recovery;
do not adopt non-thinking globally or add automatic reshaping, a formula interpreter, a new gate or an unchanged
third replay. Both attempts and the [Order 19 report](archive/all-holo-order19-scaled-display-retest-20260913.md)
remain preserved.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **11 new isolated PASS,
5 skips, 25 attempts, 16 processed tasks and 77 pending tasks**. Current **Order 20 diagnosing** originally
ended in `model_transport_failure` on public Holo1 after three requests / 1011.421 total seconds, with no
evaluator execution. No isolated Order 20 episode has launched. Original full-run 95/189 and the promoted
baseline pointer remain unchanged; no control/regression episode or further full evaluation is added.

## 2026-09-13 02:54 UTC Order 19 main non-thinking comparison launched

The second current-Order-19 attempt, `holo31-all-roles-order19-nonthinking-generation-retest-20260913-v1`,
started at `2026-09-13T02:54:00.835906+00:00`, supervisor PID 25686 / tool session 15648, worker PID 25696,
selected orders `[19]`, `frozen_condition.status=ok`. Frozen at 02:53:28 UTC, config SHA-256:
`9f36bcf9ad5cee990b441932ce8c720fa31ca932b39ce6d2766b464cedbe3733`.
Source remains `9ff5e0204adef6cbf80f0a8585d589fe1805e3944d9dadb3002be5abba99836c`
(517 files / 81,149,996 bytes).

Compared with the preceding interrupted attempt, only the main Holo binary mode changes to `non_thinking`
with `protocol.thinking=false`. Config comparison confirms unchanged source, VM, grounding `thinking` and
other protocol inputs: same direct Holo1 backend, serial fresh guest, tools, token budget, 100 global / 50 local
steps, one soft restart, 1800 Agent seconds and 30 GiB disk stop. The new hypothesis tests response saturation/
latency and adherence to native values. It adds no source/test change, new gate or regression/control episode.
Review the terminal evidence at the two-attempt checkpoint; preserve both attempts and skip if no further
evidence-backed reusable repair is justified. A single mode comparison does not establish broader score gains.

This is isolated attempt **25**, running and unscored. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
still records **11 isolated PASS, 4 skips, 15 processed and 78 pending**; Order 19 remains current, and the
original full-run 95/189 is immutable. See the [Order 19 report](archive/all-holo-order19-scaled-display-retest-20260913.md).

## 2026-09-13 02:53 UTC Order 19 interrupted; current-task mode comparison planned

Attempt 24 finalized at `2026-09-13T02:52:23.599727+00:00` as **interrupted/unscored**, 9 steps and
906.047 seconds, with no evaluator/reward. Supervisor PID 55902 / tool session 22673 exited **130**;
worker PID 55960 exited **0**, and both processes are gone. Worker revalidation is `ok`; final supervisor
integrity is absent. The raw interruption says “by user,” but the early diagnostic stop was developer-initiated.
Results SHA-256: `a1cc8303a06d9b694fda4dc93f7d7d8646895ffe07cc75e973f9917cf1575c57`.

The model repeated double-scaling despite complete current-value/divisor-1 guidance, prior formula values
and native displayed rows in actual requests. Raw model arguments matched execution; no further observation
or Adapter defect was demonstrated. Two simple inspection responses each reached 4096 output tokens with
`finish_reason=length`, taking 205.44 and 205.18 seconds; Adapter calls took 0.317–0.574 seconds, and no model
HTTP/timeout failure occurred in the audited snapshot. The artifacts do not distinguish hidden overgeneration
from server parser/stop behavior. Neither evaluator failure nor source-fix success is claimed.

**Order 19 remains current, not skipped.** The next planned current-task condition changes only the main
Holo binary mode to `non_thinking`, retaining model/backend/source/tools/grounding mode/token budget/steps/
deadline/reset. It will test response saturation/latency and adherence to observed values. No next episode
has launched; review the evidence at the two-attempt checkpoint. No unchanged replay, regression/control,
new gate, promotion or full evaluation is added. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json)
remains **11 isolated PASS, 4 skips, 24 attempts, 15 processed and 78 pending**; original full-run 95/189
is immutable. See the [Order 19 report](archive/all-holo-order19-scaled-display-retest-20260913.md).

## 2026-09-13 02:37 UTC Order 19 scaled-display contract repair attempt launched

The preserved Order 19 trajectory applied arithmetic conversion and display scaling twice, then ignored
native all-zero feedback. Existing completion additionally prescribed copying and a divisor inferred from
the instruction even when current cell values were already converted. The owning tool explanation now
describes scaling current values/formula results and divisor 1; existing completion drops only mandatory
copying and inferred divisor equality, retaining column/unit/decimal/spacing and schema checks. Every value
and operation remains model-selected. The two relevant modules passed 49 focused tests and Ruff passed.

Condition `holo31-all-roles-order19-scaled-display-retest-20260913-v1` launched at
`2026-09-13T02:37:06.177517+00:00`, supervisor PID 55902 / tool session 22673, worker PID 55960,
selected orders `[19]`, `frozen_condition.status=ok`. Freeze time: 02:36:31 UTC. Source SHA-256:
`9ff5e0204adef6cbf80f0a8585d589fe1805e3944d9dadb3002be5abba99836c`
(517 files / 81,149,996 bytes). Config SHA-256:
`7d1a3385a004990cb760332b6721646e2a63fad1253ee18839d860e735529274`.
Both model roles use original Holo1 directly at `http://192.168.0.224:8002/v1`, serially on one fresh guest.
Route, concurrency and cumulative source also differ from the full run, so no isolated causal claim is made.

This is isolated attempt **24**, still running and unscored. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) remains at **11 new isolated PASS,
4 skips, 15 processed tasks and 78 pending tasks**. No control/regression episode, new gate, promotion or
another full run was added; original full-run 95/189 remains immutable. Existing 100 global / 50 local steps,
one soft restart, 1800 Agent seconds and 30 GiB disk stop remain. See the
[Order 19 report](archive/all-holo-order19-scaled-display-retest-20260913.md).

## 2026-09-13 02:30 UTC Order 17 interrupted for repeated missing action; documented skip and Order 19 selected

Order 17 finalized at `2026-09-13T02:29:40.131379+00:00` as **interrupted/unscored**, 21 steps and
901.798 seconds, with eight completion rejections and no evaluator/reward. Supervisor PID 9520 / tool session
53956 exited **130**; worker PID 9574 exited **0**. Worker revalidation is `ok`; final supervisor integrity
is absent. The raw interruption says “by user,” but the stop was developer-initiated. Results SHA-256:
`c371ac11c3eabfde71cd371aa0b21b868b54389d65172a441da05c99b372144e`.

Direct transport enabled actions and recovery from an initial merged-cell write error. The model nevertheless
formatted one requested region instead of merging it, then repeatedly claimed completion. Actual requests
12/13 retained the specific missing-merge feedback and usable merge/save/read schemas. After saving and
reading back, only that unexecuted merge remained, and the model still ignored it through step 21. Existing
completion checks correctly rejected unfinished work; no additional implementation/feedback flaw was found.
The developer stopped this unproductive diagnostic and **skipped Order 17**, preserving its unscored result
without an unchanged replay or added gate. See the
[Order 17 report](archive/all-holo-order17-direct-transport-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **11 new isolated PASS,
4 skips, 23 isolated attempts, 15 processed tasks and 78 pending tasks**. Current Order **19 diagnosing**
originally exhausted its Agent deadline after 2166.955 total seconds on public Holo1, without evaluator
execution. No isolated episode has launched. The immutable full-run result remains 95/189.

## 2026-09-13 02:14 UTC Order 17 direct-transport single-task attempt launched

Original Order 17's first model request exhausted three identical public-Holo1 HTTP 524 origin-timeout
requests before any valid proposal or Agent action. No current-task implementation defect was demonstrated.
The direct-same-backend serial replay adds no source change; actual task behavior remains to be observed.

Condition `holo31-all-roles-order17-direct-transport-retest-20260913-v1` launched at
`2026-09-13T02:14:26.997753+00:00`, supervisor PID 9520 / tool session 53956, worker PID 9574,
selected orders `[17]`, `frozen_condition.status=ok`. Freeze time: 02:13:25 UTC. Source SHA-256:
`d572b6fbbe97703fd1dcdcb038aa842560cb0fdf8ecbbfe7482cefd70046daf5` (517 files, 81,147,702 bytes).
Config SHA-256: `e5038a8b2b04d4b90c2457ed81bfb21a566aa40845b76f4f703caf55aba199d0`.
Both roles use original Holo1 directly at `http://192.168.0.224:8002/v1`, one worker and unchanged limits.
Route, concurrency and cumulative source differ from the full run, so this does not isolate transport
causality. Existing structural checks passed; source/tests/config remain frozen through supervisor exit.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **17 running**,
**23 isolated attempts, 11 new PASS, 3 skips, 14 processed tasks and 79 pending tasks**. No regression/control
episode runs or new evaluator outcome is claimed; the full-run result remains 95/189. See the
[Order 17 report](archive/all-holo-order17-direct-transport-retest-20260913.md).

## 2026-09-13 02:11 UTC Order 16 recovered PASS; Order 17 selected

Order 16's first isolated attempt finalized at `2026-09-13T02:11:56.796555+00:00` with original-evaluator
**reward 1.0 / passed**, `agent_done`, 8 steps and 415.071 seconds. Supervisor PID 56211 / tool session
64376 and worker PID 56251 exited **0**. Supervisor final integrity and worker revalidation are `ok`, with
unchanged source/config seals. Results SHA-256:
`148edc90bdad482d134d9aa8c854f8f5905d4decfc228c48fa98f388e89dea09`.

The direct-Holo1 serial replay completed task work, save/readback and delivery after one existing completion
rejection. No new Order 16 source patch was added; accumulated source and runtime differences remain a limit
on transport-only causal attribution. See the
[Order 16 report](archive/all-holo-order16-direct-transport-retest-20260913.md). No regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **11 new isolated PASS,
3 skips, 22 isolated attempts, 14 processed tasks and 79 pending tasks**. Current Order **17 diagnosing**
originally ended in public-Holo1 transport failure after 473.755 seconds and three requests, without an
evaluator. No isolated episode has launched. The immutable full-run result remains 95/189.

## 2026-09-13 02:04 UTC Order 16 direct-transport single-task attempt launched

Original Order 16 completed sheet operations and corrected a save-filter error from returned feedback,
then request 8 exhausted three public-Holo1 HTTP 524 timeouts. The successful save result and structural
readback tools were retained in the request. No additional protocol, execution or feedback defect was found;
this direct-same-backend serial recheck adds no source patch. Saving alone does not establish PASS.

Condition `holo31-all-roles-order16-direct-transport-retest-20260913-v1` launched at
`2026-09-13T02:04:46.735543+00:00`, supervisor PID 56211 / tool session 64376, worker PID 56251,
selected orders `[16]`, `frozen_condition.status=ok`. Freeze time: 02:03:57 UTC. Source SHA-256:
`d572b6fbbe97703fd1dcdcb038aa842560cb0fdf8ecbbfe7482cefd70046daf5` (517 files, 81,147,702 bytes).
Config SHA-256: `1060bbb94f92eddfbecac556595c71b8a30dd526f28e5a35ae3758bae572475d`.
Both roles use original Holo1 directly at `http://192.168.0.224:8002/v1`, one worker and unchanged limits.
Direct route, concurrency and cumulative source also differ from the full run; no transport-only causal
effect is claimed. Existing structural revalidation passed; source/tests/config stay frozen through exit.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **16 running**,
**22 isolated attempts, 10 new PASS, 3 skips, 13 processed tasks and 80 pending tasks**. No regression/control
episode runs or evaluator outcome is yet claimed; the full-run result remains 95/189. See the
[Order 16 report](archive/all-holo-order16-direct-transport-retest-20260913.md).

## 2026-09-13 02:01 UTC Order 15 second attempt interrupted; documented skip and Order 16 selected

Order 15's second attempt finalized at `2026-09-13T01:57:25.160532+00:00` as **interrupted/unscored**,
20 steps and 1137.045 seconds, with one completion rejection and no evaluator or reward. Supervisor PID
3398 / tool session 39073 exited **130**; worker PID 3483 exited **0**. Worker integrity revalidation is
`ok`; final supervisor integrity is absent. The raw error says “by user,” but the stop was developer-initiated.
Results SHA-256: `a590cafbc440154d7eabe65718c16559d73078ef5bd77a420c3bc4f846fa1fdc`.

Actual model requests retained complete native header flags, ranges, series/categories and usage guidance,
with raw/model/HTTP arguments agreeing and no getter errors. The model still repeatedly recreated an
incomplete second chart through its own header/range choices. At the two-attempt checkpoint no further
reusable runtime, projection or protocol defect was found, so the developer stopped this unproductive attempt.
Order **15 is skipped**; its first evaluator failure and second unscored interruption remain distinct.
Retain the generic coverage explanations and native observations, without automatic header selection,
mandatory fields, another gate or a third unchanged replay. See the
[Order 15 report](archive/all-holo-order15-chart-coverage-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **10 new isolated PASS,
3 skips, 21 isolated attempts, 13 processed tasks and 80 pending tasks**. Current Order **16 diagnosing**
is the next original transport failure; no isolated episode has launched. The full-run result remains 95/189.

## 2026-09-13 01:38 UTC Order 15 immediate native-header feedback frozen; second attempt launched

Existing `chart.create` now reports native `getHas*Headers` values immediately, retaining independent getter
errors in `header_inspect_error`. Existing result projection preserves these observations and explains their
label role. The model still selects every range, flag and replacement; prior complete category feedback was
already available, so this is not a claim of recovered lost feedback. **19 focused checks** and Ruff passed.
The preserved native fixture already exercised these getters; no extra native diagnostic was needed.

Condition `holo31-all-roles-order15-native-header-feedback-retest-20260913-v1` launched at
`2026-09-13T01:38:16.956614+00:00`, supervisor PID 3398 / tool session 39073, worker PID 3483,
selected orders `[15]`, `frozen_condition.status=ok`. Freeze time: 01:37:51 UTC. Source SHA-256:
`d572b6fbbe97703fd1dcdcb038aa842560cb0fdf8ecbbfe7482cefd70046daf5` (517 files, 81,147,702 bytes).
Config SHA-256: `7a0545933ea1827ce4015879415ba3c5d7aa0550f0c465e8283a02ae1d2440cc`.
Both roles retain direct Holo1 at `http://192.168.0.224:8002/v1`, one worker and unchanged limits.
Source/tests/config remain frozen through supervisor exit; review this second affected attempt's native
observations and terminal outcome before deciding any extension.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves failed attempt 1 and
records current Order **15 running**, **21 isolated attempts, 10 new PASS, 2 skips, 12 processed tasks
and 81 pending tasks**. No regression/control episode runs or new evaluator outcome is claimed; the full-run
result remains 95/189. See the [Order 15 report](archive/all-holo-order15-chart-coverage-retest-20260913.md).

## 2026-09-13 01:31 UTC Order 15 first retest failed; immediate native-header observation next

Order 15's first isolated attempt finalized at `2026-09-13T01:31:32.286599+00:00` with original-evaluator
**reward 0 / failed**, `agent_done`, 8 steps and 397.08 seconds. There were zero completion rejections;
terminal audit at review step 9 confirmed delivery. Supervisor PID 42279 / tool session 2397 and worker
PID 42327 exited **0**, with supervisor final integrity and worker revalidation `ok`. Results SHA-256:
`b751ffbebd00966da863cc0bf36f2bf5e9eebc3fca44030ba8f565bc2b1744d4`.

The model now selected actual monthly data and excluded the annual total, but omitted `column_headers`.
Its declared true default consumed January, leaving both charts with 11 February–December categories.
Native execution followed those arguments. Existing `chart.create` readback omits actual native header flags
until a later inspection; the next minimal hypothesis exposes those flags and their roles immediately.
The model still chooses all arguments, with no forced schema, automatic correction or added gate.

Current Order **15 fixing** remains in progress, without a skip or new PASS. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **20 isolated attempts,
10 new PASS, 2 skips, 12 processed tasks and 81 pending tasks**. No regression/control episode ran;
the full-run result remains 95/189. See the
[Order 15 report](archive/all-holo-order15-chart-coverage-retest-20260913.md).

## 2026-09-13 01:24 UTC Order 15 chart-coverage guidance frozen; isolated attempt launched

Original Order 15's sole scored mismatch was its second chart omitting January while including an annual
total. All 288 values/formulas/formats and the first chart matched. Native execution and complete feedback
were correct for the model-selected range/default headers; the model mistook a count of 12 for coverage.
Two generic chart explanations now ask the model to read each source table's headers/boundaries and compare
actual first/last/blank category labels. No target inference, native behavior change, new API or gate is added.
**33 focused checks** and Ruff passed; no extra native diagnostic was needed for wording-only changes.

Condition `holo31-all-roles-order15-chart-coverage-retest-20260913-v1` launched at
`2026-09-13T01:24:42.239086+00:00`, supervisor PID 42279 / tool session 2397, worker PID 42327,
selected orders `[15]`, `frozen_condition.status=ok`. Freeze time: 01:24:08 UTC. Source SHA-256:
`454666199d4c146a96ecc5bd6d11f68fe83f3149a4272e41705962d6c05fa9e4` (517 files, 81,144,846 bytes).
Config SHA-256: `f232ae07d4dd55cb86ba4267abfab23cf7f5ac24158d0e9d3c2a618fad67e67d`.
Both roles use original Holo1 directly at `http://192.168.0.224:8002/v1`, one worker and unchanged limits.
Route, concurrency and cumulative source also differ from the full run; no prompt-only causal conclusion is
yet justified. Source/tests/config remain frozen through supervisor exit.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **15 running**,
**20 isolated attempts, 10 new PASS, 2 skips, 12 processed tasks and 81 pending tasks**. No regression/control
episode runs or new evaluator outcome is claimed; the full-run result remains 95/189. See the
[Order 15 report](archive/all-holo-order15-chart-coverage-retest-20260913.md).

## 2026-09-13 01:17 UTC Order 14 recovered PASS; Order 15 selected

Order 14's first isolated attempt finalized at `2026-09-13T01:17:57.441996+00:00` with original-evaluator
**reward 1.0 / passed**, `agent_done`, 6 steps and 354.037 seconds. Supervisor PID 17299 / tool session
77890 and worker PID 17311 exited **0**. Supervisor final integrity and worker revalidation are `ok`,
with unchanged source/config seals. Results SHA-256:
`1dd0eabedf9585d6e04cf3346b3ec0f22a61ab3cc8bef2df2f86a61004b1577e`.

The direct-Holo2 single-worker episode executed its task and completed after one existing completion
rejection; terminal audit at review step 7 confirmed delivery. No new Order 14 source patch was needed.
Accumulated source and runtime differences remain a limit on transport-only causal attribution. See the
[Order 14 report](archive/all-holo-order14-direct-transport-retest-20260913.md). No regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **10 new isolated PASS,
2 skips, 19 isolated attempts, 12 processed tasks and 81 pending tasks**. Current Order **15 diagnosing**
originally completed in 11 steps and 1512.936 seconds but received evaluator reward 0, using public Holo1.
No Order 15 episode has launched. The immutable full-run result remains 95/189.

## 2026-09-13 01:11 UTC Order 14 direct-transport single-task attempt launched

The first model request in original Order 14 exhausted three public-Holo2 HTTP 524 responses. No Agent
action or evaluator ran, so the original episode provides no application-behavior result. This recheck uses
the same backend directly over LAN with one worker and adds no source patch. Accumulated source, route
and concurrency differ from the full run, preventing a transport-only causal comparison.

Condition `holo31-all-roles-order14-direct-transport-retest-20260913-v1` launched at
`2026-09-13T01:11:47.394482+00:00`, supervisor PID 17299 / tool session 77890, worker PID 17311,
selected orders `[14]`, `frozen_condition.status=ok`. Freeze time: 01:11:06 UTC. Source SHA-256:
`d89e8f9231f0af4f3fceeb1a448df5eb4e0fa58f60645bfff35ed02a04d1fd41` (517 files, 81,144,337 bytes).
Config SHA-256: `5af206496a8c47e8b34dd4ab15c1c54ad9e9c6ca558acbaadc58ce73e6cc4e4f`.
Both roles use direct Holo2 at `http://192.168.0.138:8001/v1`, with one worker and unchanged model/episode
budgets. Source/tests/config stay frozen until supervisor exit; existing configuration/frozen-input checks pass.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **14 running**,
**19 isolated attempts, 9 new PASS, 2 skips, 11 processed tasks and 82 pending tasks**. No regression/control
episode runs or new evaluator outcome is claimed; the full-run result remains 95/189. See the
[Order 14 report](archive/all-holo-order14-direct-transport-retest-20260913.md).

## 2026-09-13 01:10 UTC Order 13 second attempt failed; documented skip and Order 14 selected

Order 13's second attempt finalized at `2026-09-13T01:06:02.318983+00:00` with original-evaluator
**reward 0 / failed**, `agent_done`, 30 steps and 1330.487 seconds. Two completion claims were rejected;
terminal audit at review step 31 confirmed the eventual result. Supervisor PID 27657 / tool session 90504
and worker PID 27692 exited **0**, with supervisor final integrity and worker revalidation `ok`.
Results SHA-256: `d395f5f84517f40dda98233dada03e47f4fe7b31ac97b26bff4e0edce070b955`.

Offline comparison found five wrong Growth cells, C13:G13, whose formulas used row 2 instead of the Total
row 12. The other 86 of 91 cell values and all General formatting matched. Chart types/titles were correct,
but the model-selected ranges with default true/true header flags omitted January from Total and February
from Growth. Native source/category readback and saved state matched the declared contract; no new API or
save defect was demonstrated. Order **13 is skipped** for remaining model selection and review failure.
Preserve the reusable native-header and replacement guidance repairs; no third unchanged replay or new gate.
See the [Order 13 report](archive/all-holo-order13-direct-transport-retest-20260913.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **9 new isolated PASS,
2 skips, 18 isolated attempts, 11 processed tasks and 82 pending tasks**. Current Order **14 diagnosing**
originally ended in a public-Holo2 transport failure after 1008.348 seconds and three requests, without an
evaluator. No Order 14 episode has launched. The immutable full-run result remains 95/189.

## 2026-09-13 00:43 UTC Order 13 native chart-header repair frozen; second isolated attempt launched

The owning chart creator now reapplies the original physical header flags after `setDiagram` establishes
orientation. Existing replacement descriptions and conflict feedback explain explicit `replace=true` with
the observed chart name; no automatic replacement or model-range change is introduced. **16 runtime/chart
checks** and **37 schema/feedback checks** passed; Ruff passed. Synthetic native v1 verified row binding but
partially failed on reused fixture chart names across sheets. Preserved v2 changed only synthetic names and
fully passed in 48.316 seconds: both orientations retain correct physical flags, three labels and three values,
with unchanged source and arguments. These diagnostics used no model, evaluator or benchmark data.

Condition `holo31-all-roles-order13-chart-header-binding-retest-20260913-v1` launched at
`2026-09-13T00:43:37.094051+00:00`, supervisor PID 27657 / tool session 90504, worker PID 27692,
selected orders `[13]`, `frozen_condition.status=ok`. Freeze time: 00:43:11 UTC. Source SHA-256:
`d89e8f9231f0af4f3fceeb1a448df5eb4e0fa58f60645bfff35ed02a04d1fd41` (517 files, 81,144,337 bytes).
Config SHA-256: `c2ca8bd52087a823966871703eb45c47b077ec76caea692f106ccf1c2de47508`.
Both Holo roles, direct Holo2 route, one worker and limits match attempt 1. The model still chooses its
Growth range and all chart arguments. Source/tests/config stay frozen until supervisor exit; review the
second affected attempt's actual terminal result before deciding further work.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves interrupted attempt 1
and records current Order **13 running**, **18 isolated attempts, 9 new PASS, 1 skip, 10 processed tasks
and 83 pending tasks**. No regression/control episode runs or new evaluator outcome is claimed; the full-run
result remains 95/189. See the [Order 13 report](archive/all-holo-order13-direct-transport-retest-20260913.md).

## 2026-09-13 00:31 UTC Order 13 interrupted for reproduced chart-header binding defect

Order 13's direct replay passed its original transport interruption, then reproduced a shared chart-header
binding defect at steps 6/9: row-oriented calls selected physical first-row/first-column flags, but native
readback consumed a different header boundary and omitted categories. The model also selected a Growth chart
range different from its written formula range; raw/API arguments and next-request readback matched, so that
mistake is not data loss. Existing-chart replacement conflicted while its `replace` usage lacked guidance.
The developer documented this checkpoint and interrupted before repairing native binding and replacement
descriptions. The existing API is retained and the model continues to select ranges and replacement intent.

Supervisor PID 43464 / tool session 94184 exited **130**; worker PID 43672 exited **0**. Final metadata at
`2026-09-13T00:31:31.064466+00:00` records `interrupted`, reward **null**, 18 steps, 649.165 seconds and
zero completion rejections. No evaluator ran. Worker revalidation is `ok`; final supervisor integrity is
absent. The raw error says “by user,” but the actual stop was developer-initiated. Results SHA-256:
`48b335c1376b948672a9b20311ea8dea30ef19158ea5744900a5ac8d8653a21d`.

Current Order **13 fixing** remains in progress; the interruption is neither a new failed evaluator result
nor a skip. The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **17 isolated
attempts, 9 new PASS, 1 skip, 10 processed tasks and 83 pending tasks**. No regression/control episode ran;
the full-run result remains 95/189. See the
[Order 13 report](archive/all-holo-order13-direct-transport-retest-20260913.md).

## 2026-09-13 00:20 UTC Order 13 direct-transport single-task attempt launched

Original Order 13 corrected a range-size error, wrote totals and produced an incomplete category chart
before request 8 exhausted three public-Holo2 HTTP 524 responses. Chart correction, growth work and saving
remained undone; readback and corrective guidance were available. The direct-same-backend single-worker
recheck adds no new source patch and tests continuation through that remaining model-selected work.

Condition `holo31-all-roles-order13-direct-transport-retest-20260913-v1` launched at
`2026-09-13T00:20:30.408588+00:00`, supervisor PID 43464 / tool session 94184, worker PID 43672,
selected orders `[13]`, `frozen_condition.status=ok`. Freeze time: 00:19:18 UTC. Source SHA-256:
`c1f7548a68052dc26796fb93af0a032fa1962846e93db04963aafb3960bd58f0` (516 files, 81,135,464 bytes).
Config SHA-256: `df6f2141b54708db78a047b94b0baa94a920d39b417dbf84cf5038d53d798f64`.
Both roles use direct Holo2 at `http://192.168.0.138:8001/v1`, one worker and unchanged model/episode
budgets. Accumulated source and concurrency also differ from the full run, so this is not a transport-only
causal comparison. Source/tests/config stay frozen through supervisor exit; existing structural checks suffice.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **13 running**,
**17 isolated attempts, 9 new PASS, 1 skip, 10 processed tasks and 83 pending tasks**. No regression/control
episode runs or new evaluator outcome is claimed; the immutable full-run result remains 95/189. See the
[Order 13 report](archive/all-holo-order13-direct-transport-retest-20260913.md).

## 2026-09-13 00:17 UTC Order 12 recovered PASS; Order 13 selected

Order 12's first isolated attempt finalized at `2026-09-13T00:17:14.992541+00:00` with original-evaluator
**reward 1.0 / passed**, `agent_done`, 6 steps and 366.018 seconds. Supervisor PID 25075 / tool session
54941 and worker PID 25163 exited **0**. Supervisor final integrity and worker revalidation are `ok`,
with unchanged frozen source/config. Results SHA-256:
`b89c44b08c79f3bc832d71e673a8220f9ce09ce123823c48016ccd7e08e660b4`.

The direct-Holo2 single-worker episode completed formatting, save/readback and delivery, with one existing
completion rejection. Terminal audit at review step 7 confirmed completion. No new Order 12 source patch
was needed, but cumulative source and runtime differences prevent a transport-only causal claim. See the
[Order 12 report](archive/all-holo-order12-direct-transport-retest-20260913.md). No regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **9 new isolated PASS,
1 skip, 16 isolated attempts, 10 processed tasks and 83 pending tasks**. Current Order **13 diagnosing**
originally ended in a public-Holo2 transport failure after 1245.715 seconds and three request attempts,
without evaluator execution. No Order 13 episode has launched. The immutable full-run result remains 95/189.

## 2026-09-13 00:10 UTC Order 12 direct-transport single-task attempt launched

Original Order 12 changed the selected range's decimal separator and saved successfully, then exhausted
three public-Holo2 Cloudflare HTTP 524 responses at the 120-second proxy timeout before final readback.
Earlier structured-call errors recovered and were not the terminal cause. No new Order 12 source patch is
needed before this direct-same-backend single-worker recheck. Cumulative source and concurrency differ from
the full run alongside route, so it is not a transport-only causal comparison.

Condition `holo31-all-roles-order12-direct-transport-retest-20260913-v1` launched at
`2026-09-13T00:10:54.947638+00:00`, supervisor PID 25075 / tool session 54941, worker PID 25163,
selected orders `[12]`, `frozen_condition.status=ok`. Freeze time: 00:07:32 UTC. Source SHA-256:
`c1f7548a68052dc26796fb93af0a032fa1962846e93db04963aafb3960bd58f0` (516 files, 81,135,464 bytes).
Config SHA-256: `222e65c0fc85778608a4fdc124f99f3f484568205efb51cb3d7e2bedb2b1f321`.
Both roles use direct Holo2 at `http://192.168.0.138:8001/v1`, with one worker and existing model/episode
budgets. Source, tests and config remain frozen through supervisor exit. Only configuration/frozen-input
structural checks were needed; no extra test campaign or regression/control episode runs.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **12 running**,
**16 isolated attempts, 8 new PASS, 1 skip, 9 processed tasks and 84 pending tasks**. No evaluator outcome
is yet claimed; the immutable full-run result remains 95/189. See the
[Order 12 report](archive/all-holo-order12-direct-transport-retest-20260913.md).

## 2026-09-13 00:06 UTC Order 11 third attempt failed; documented skip and Order 12 selected

Order 11's third attempt finalized at `2026-09-12T23:58:41.670540+00:00` with original-evaluator
**reward 0 / failed**, `agent_done`, 8 steps and 494.989 seconds. Supervisor PID 47303 / tool session
17302 and worker PID 47375 exited **0**; supervisor final integrity and worker revalidation are `ok`.
Results SHA-256: `908e4fab1bc73f91927f23e6eb156d2d048c32a61958f5ce013c2808660887d6`.

The native explicit-area contract executed all 36 selected targets with exact argument and readback agreement.
Offline comparison found all 198 values identical and only eight missing background changes: 36 correct red
cells versus 44 required. Seven omitted dates remained visible in selection and terminal-review requests;
C33 was missed because the model did not read the last row. Terminal review accepted the incomplete result.
No additional API, environment or saved-document defect was demonstrated. After three distinct preserved
attempts, Order **11 is skipped** for remaining model selection/review failure; no isolated PASS is counted.
The reusable repairs and complete evidence remain. No task-specific target oracle or new gate is introduced.
See the [Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **8 new isolated PASS,
1 skip, 15 isolated attempts, 9 processed tasks and 84 pending tasks**. Current Order **12 diagnosing**
originally ended in a public-Holo2 transport failure after 1227.572 seconds and three requests, without an
evaluator. The next condition is being prepared on direct Holo2 with one worker and the unchanged current
source seal; no episode has launched. The immutable full-run result remains 95/189.

## 2026-09-12 23:50 UTC Order 11 explicit-area formatting frozen; third isolated attempt launched

Existing `range.format` now supports model-explicit comma-separated A1 areas sharing one format, with
independent native date/color readback and actionable partial-application feedback. Exact-member completion
matching adds no new obligation. The model selects every target; there is no date/task classifier, inferred
target expansion, new API, gate or context-budget increase. Relevant context invocation passed **107 tests**,
retrieval/retired-macro invocation passed **29**, and the final collection/context invocation passed **13**.
These invocations overlap and are not a unique-test total. Ruff and frozen-condition validation passed.

Condition `holo31-all-roles-order11-explicit-format-areas-retest-20260912-v1` launched at
`2026-09-12T23:50:11.603257+00:00`, supervisor PID 47303 / tool session 17302, worker PID 47375,
selected orders `[11]`, `frozen_condition.status=ok`. Freeze time: 23:49:39 UTC. Source SHA-256:
`c1f7548a68052dc26796fb93af0a032fa1962846e93db04963aafb3960bd58f0` (516 files, 81,135,464 bytes).
Config SHA-256: `c364c3bb5f5c6b14274e7ddcd1b293be5db09659898fa57a2ce7f872e1081383`.
Both roles retain direct Holo2, one worker and unchanged limits. Source, tests and config remain frozen
through supervisor exit. This episode must verify the native collection path and stops at a terminal
outcome or existing limits before another review.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves both prior attempts
and records current Order **11 running**, **15 isolated attempts, 8 new PASS, 0 skips, 8 processed tasks
and 85 pending tasks**. No regression/control episode runs or evaluator outcome is yet claimed; the full-run
result remains 95/189. See the [Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

## 2026-09-12 23:39 UTC Order 11 second attempt reached deadline; third hypothesis justified

Order 11's second isolated attempt finalized at `2026-09-12T23:39:01.284549+00:00` with task status
**`agent_deadline_exhausted`**, reward **null**, 1855.589 seconds and no evaluator execution. Supervisor
metadata says `completed`, meaning the run finished; it does not mean task success. The finalized task's
`steps` remains **null**, while the preserved trace separately contains **35 events**. Supervisor PID 30919 /
tool session 82862 and worker PID 30954 exited **0**. Supervisor final integrity and worker revalidation
are `ok`. Results SHA-256:
`bdfea450bcb9c30a6b2c5d7f4e502805f34fe6c36de00398e59163281c5c8038`.

Native date observations supported correct early choices. At step 3, the model explicitly selected eight
June weekend cells in one comma-separated formatting call, which failed natively. Repeated individual-area
calls plus later date/address misuse and truncation consumed the episode. At the two-attempt checkpoint,
this concrete evidence justifies one distinct third hypothesis: extend existing `range.format` to accept
model-explicit comma-separated A1 areas sharing one format, with owning post-format date/color readback.
The model still selects every target; no date classifier, new API, gate or control episode is introduced.
One newly frozen third attempt will stop at its terminal outcome for review.

Current Order **11 fixing** remains in progress, with no skipped task or new PASS claimed. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **14 isolated attempts,
8 new PASS, 0 skips, 8 processed tasks and 85 pending tasks**. The full-run result remains 95/189; see the
[Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

## 2026-09-12 23:07 UTC Order 11 native-date/background readback frozen; second isolated attempt launched

The owning Calc reader adds A1-keyed ISO date/weekday for native numeric DATE cells using the document's
actual NullDate. Existing context projection retains these `date_cells` and native `background_cells`, and
the existing read description explains them. **103 projection/context, 57 native/formatted-text/write and
3 retrieval checks** passed; Ruff passed. Native tests simulate UNO, so live field access still needs proof
from this episode's actual responses. No context budget increase, target selection, arbitrary date-string
inference, new API or gate is added.

Condition `holo31-all-roles-order11-native-date-readback-retest-20260912-v1` launched at
`2026-09-12T23:07:51.083250+00:00`, supervisor PID 30919 / tool session 82862, worker PID 30954,
selected orders `[11]`, `frozen_condition.status=ok`. Freeze time: 23:07:18 UTC. Source SHA-256:
`b30a164d57f361bdb917c9804ff658095e737ee8d3cb055957d0e5cdead51d87` (514 files, 81,115,645 bytes).
Config SHA-256: `04f06610989ab8f172d5ca5a54f6ead01be1d477111f303fed0d8352c3ca0863`.
Both roles retain direct Holo2, one worker and the same episode/resource budgets. Source, tests and config
stay frozen through supervisor exit. The second affected episode's outcome and native observations will
be reviewed before deciding further work.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves interrupted attempt 1
and records current Order **11 running**, **14 isolated attempts, 8 new PASS, 0 skips, 8 processed tasks
and 85 pending tasks**. No regression/control episode runs or evaluator outcome is yet claimed; the full-run
result remains 95/189. See the [Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

## 2026-09-12 23:01 UTC Order 11 discovery verified online; interrupted for native readback repair

Order 11 selected and executed `range.format` three times at steps 4–6, confirming the discovery improvement
online. The model still made two date/address errors despite observed dates and A1 positions. A separate
confirmed feedback loss drops native `background_cells` from the `range.read` context hint, hiding already
observed coloring from text feedback. The developer interrupted at this reproduced failure before repairing
the observation contract. The next hypothesis adds A1-keyed ISO date/weekday observations from native numeric
DATE cells and the actual document NullDate, and preserves native background readback. No arbitrary date-string
inference, target selection, new gate or API is introduced.

Supervisor PID 62350 / tool session 12271 exited **130**; worker PID 62407 exited **0**. Final metadata at
`2026-09-12T23:01:08.548879+00:00` records `interrupted`, reward **null**, 7 steps, 506.963 seconds and zero
completion rejections. No evaluator ran. Worker integrity revalidation is `ok`; final supervisor integrity is
absent. The raw error says “by user,” but the actual stop was developer-initiated. Results SHA-256:
`c4db8cee2d69116e186bca62895a0694880ca908a3b0aa0b81fc8b2632e79920`.

Current Order **11 fixing** remains in progress. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **13 isolated attempts,
8 new PASS, 0 skips, 8 processed tasks and 85 pending tasks**. No regression/control episode ran; the
immutable full-run result remains 95/189. See the
[Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

## 2026-09-12 22:52 UTC Order 11 formatting-discovery repair frozen; isolated attempt launched

Three synthetic retrieval/tool-exposure checks and Ruff passed for the generic formatting vocabulary
repair. Existing `range.format` selection improved from rank 14 to 4; its parameters and execution remain
unchanged, and the model still selects cells/colors. Retrieval success is not yet an evaluator result.

Condition `holo31-all-roles-order11-format-recall-retest-20260912-v1` launched at
`2026-09-12T22:52:30.237130+00:00`, supervisor PID 62350 / tool session 12271, worker PID 62407,
selected orders `[11]`, `frozen_condition.status=ok`. Freeze time: 22:52:04 UTC. Source SHA-256:
`3002e92534835f7670ddbac5775b78cb779badde9216b0ba706e00eb98a0ea7c` (512 files, 81,104,988 bytes).
Config SHA-256: `d883c283b8e15b2bd4558d026bdaaa43a22c8c8a872f86db8b03c5d370d772ad`.
Both roles use original Holo2 directly at `http://192.168.0.138:8001/v1`, serial worker, with existing model
settings and episode/resource budgets. Cumulative source, direct route and concurrency differ from the
full run. Source, tests and config stay frozen through supervisor exit.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **11 running**,
**13 isolated attempts, 8 new PASS, 0 skips, 8 processed tasks and 85 pending tasks**. No regression/control
episode, new gate or evaluator change is introduced; the immutable full-run result remains 95/189.
See the [Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

## 2026-09-12 22:51 UTC Order 11 formatting-discovery metadata repair in verification

Original Order 11 exhausted its deadline after 30 events. `range.format` was absent from all 34 saved model
requests; tool search was available 33 times but never selected. The model repeatedly asserted that no exact
RGB formatting API existed and wandered through GUI dialogs, alongside independent date/address errors.

General `highlight`, `highlighting` and `background` vocabulary in the existing tool synonyms and owning
`range.format` description now raises its automatic selection rank from **14 to 4**, within Top7. The
public parameters and execution remain unchanged; the model still selects all cells and colors. Focused
synthetic retrieval and tool-exposure checks are completing. No new API, gate, calendar parser or semantic
argument injection is added, and retrieval alone does not establish task success.

Current Order **11 fixing** has not launched an isolated episode. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **8 new isolated PASS,
0 skips, 12 isolated attempts, 8 processed tasks and 85 pending tasks**. The immutable full-run result
remains 95/189. See the [Order 11 report](archive/all-holo-order11-format-recall-repair-20260912.md).

## 2026-09-12 22:43 UTC Order 8 recovered PASS; Order 11 selected

Order 8's first isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
17 steps and 1269.545 seconds, finalized at `2026-09-12T22:43:29.590363+00:00`. Supervisor PID 2703 /
tool session 33525 and worker PID 2711 exited **0**. Supervisor final integrity and worker revalidation are
`ok`, with unchanged source/config seals. Results SHA-256:
`ac5fb36a4371e6b6df772ab6968e494b9b1db64026d7f151ef55aab5dd9e84be`.

The existing scalar-cell path wrote literal headers at step 4. After initially choosing incorrect month
references and sums, the model inspected the result, activated Sheet2 with Holo GUI, wrote literal month
labels, read the source and corrected the sums at step 13. Raw API arguments and executed values matched,
with schemas/tools available; no additional Adapter bug was demonstrated. Step 14 string evidence correctly
received missing-save/read-back rejection, followed by save, inspection and completion at steps 15–17.
This records actual model correction without attributing it to an untested new prompt. See the
[Order 8 report](archive/all-holo-order8-literal-cells-retest-20260912.md). No regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **8 new isolated PASS
(42, 1, 2, 4, 5, 6, 7, 8), 0 skips, 8 processed tasks, 12 isolated attempts and 85 pending tasks**.
The next original non-passing task is Order **11 diagnosing**, whose original episode exhausted its Agent
deadline without evaluator execution. Its recorded 2772.021-second duration includes lifecycle. No Order 11
episode has launched. The immutable full-run result remains 95/189 and the promoted baseline is unchanged.

## 2026-09-12 22:22 UTC Order 8 existing literal-cell repair retest launched

All three original Order 8 literal-cell calls now pass the existing schema, native parsing and orientation
offline with their raw parameters retained. No new source change is added; the condition reuses the literal-cell
repair and source seal from recovered Orders 6/7. Only current-condition structural checks were needed,
without an extra test campaign or regression/control episode.

Condition `holo31-all-roles-order8-literal-cells-retest-20260912-v1` launched at
`2026-09-12T22:22:04.444567+00:00`, supervisor PID 2703 / tool session 33525, worker PID 2711,
selected orders `[8]`, `frozen_condition.status=ok`. Freeze time: 22:21:25 UTC. Source SHA-256:
`a084243ab70e623c627e9351233313d79304ba029427093d678f5fa721a8637b` (511 files, 81,102,048 bytes).
Config SHA-256: `c0b9b48d2285211d8c093402c6d8e395fd624399a661e5efc4a5fb87a5da1a3e`.
Both roles use the original worker-08 Holo2 backend directly at `http://192.168.0.138:8001/v1` with
one worker. Public-to-LAN transport, 14-to-1 concurrency and cumulative source changes from the full run
are explicit comparison limitations. Model settings and episode/resource budgets remain; source, tests and
config stay frozen through supervisor exit.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **8 running**,
**12 isolated attempts, 7 new PASS (42, 1, 2, 4, 5, 6, 7), 0 skips, 7 processed tasks and 86 pending tasks**.
No evaluator outcome is yet claimed; the immutable full-run result remains 95/189. See the
[Order 8 report](archive/all-holo-order8-literal-cells-retest-20260912.md).

## 2026-09-12 22:19 UTC Order 7 recovered PASS; Order 8 selected

Order 7's first isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
7 steps and 352.254 seconds, finalized at `2026-09-12T22:19:12.502587+00:00`. Supervisor PID 50922 /
tool session 19229 and worker PID 50984 exited **0**. Supervisor final integrity and worker revalidation
are `ok`, with unchanged source/config seals. Results SHA-256:
`83ace745c860483eb9958faa7b40a0166b3101b1d106c658a4b31410c4bf8bd9`.

Step 3 `rows.hidden` succeeded. Step 4 string evidence was correctly rejected by the existing save/read-back
requirements, followed by step 5 save, step 6 inspection and step 7 completion. The episode used the same
Holo1 backend directly with one worker and no new Order 7 source repair; cumulative source and runtime
differences prevent attributing success solely to transport. See the
[Order 7 report](archive/all-holo-order7-direct-transport-retest-20260912.md). No regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **7 new isolated PASS
(42, 1, 2, 4, 5, 6, 7), 0 skips, 7 processed tasks, 11 isolated attempts and 86 pending tasks**. Current
Order **8 diagnosing** originally ended in `model_protocol_failure` after 823.169 seconds and three structured
protocol attempts, without evaluator execution; original worker-08 used public Holo2. Its preserved calls
are being checked against the existing literal-cell repair before a new current-task-only condition. No
Order 8 episode has launched. The immutable full-run result remains 95/189.

## 2026-09-12 22:13 UTC Order 7 direct-transport single-task attempt launched

All three original Order 7 requests returned Cloudflare **HTTP 524**, reporting a 120-second origin timeout.
There were no proposals, Agent steps, API executions or evaluator result. No new Order 7 source repair is
added. The bounded recheck uses the original Holo1 backend directly with one worker and retains the source
sealed for Order 6. The public-to-LAN route, 14-to-1 concurrency and cumulative source differences from the
full run are explicit; this condition cannot establish a pure transport causal effect.

Condition `holo31-all-roles-order7-direct-transport-retest-20260912-v1` launched at
`2026-09-12T22:13:07.458189+00:00`, supervisor PID 50922 / tool session 19229, worker PID 50984,
selected orders `[7]`, `frozen_condition.status=ok`. Freeze time: 22:12:38 UTC. Source SHA-256:
`a084243ab70e623c627e9351233313d79304ba029427093d678f5fa721a8637b` (511 files, 81,102,048 bytes).
Config SHA-256: `84eb69a9a865c7cf203e77613c0ad93c7037ae079742d471a7e94eab2fb8b79f`.
Both model roles use `http://192.168.0.224:8002/v1`; model settings and episode/resource budgets remain.
Only structural configuration checks are needed for this runtime change, with no extra test campaign.
Source, tests and config remain frozen through supervisor exit.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records current Order **7 running**,
**11 isolated attempts, 6 new PASS (42, 1, 2, 4, 5, 6), 0 skips, 6 processed tasks and 87 pending tasks**.
No regression/control episode or new gate is introduced, no evaluator outcome is claimed, and the immutable
full-run numerator remains 95/189. See the
[Order 7 report](archive/all-holo-order7-direct-transport-retest-20260912.md).

## 2026-09-12 22:08 UTC Order 6 recovered PASS; Order 7 selected

Order 6's second isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
12 steps and 517.21 seconds, finalized at `2026-09-12T22:08:55.786415+00:00`. Supervisor PID 26040 /
tool session 37119 and worker PID 26117 exited **0**. Supervisor final integrity and worker revalidation
are `ok`, with unchanged source/config seals. Results SHA-256:
`f4ad5800848387e94e3a5c4b52eac3936482a7c6f9ef66080864c60e20c1513a`.

The model read the source at step 3 and wrote 15 correct formulas at step 5. Literal headers and year strings
exercised scalar compatibility online. **Error 522 did not occur**, so this PASS does not establish that the
new 522 explanation caused improvement. Step 9 completion was rejected for missing read-back; inspection at
step 10 and a read at step 11 preceded successful completion at step 12. The first interrupted attempt stays
preserved. The second-attempt review checkpoint is resolved by original-evaluator PASS; no further Order 6
episode or regression/control task is needed. See the
[Order 6 report](archive/all-holo-order6-literal-cells-repair-20260912.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **6 new isolated PASS
(42, 1, 2, 4, 5, 6), 0 skips, 6 processed tasks, 10 isolated attempts and 87 pending tasks**. Current Order
**7 diagnosing** originally ended in `model_transport_failure` after 1387.125 seconds and three request
attempts, without evaluator execution; original worker-07 used public Holo1. No Order 7 episode has launched.
The immutable full-run result remains 95/189 and the promoted baseline is unchanged.

## 2026-09-12 22:00 UTC Order 6 circular-reference explanation frozen; second isolated attempt launched

The only added production change is an owning-Calc helper explaining error 522 for the two existing
formula-writing paths. Other error fallbacks, selected formula arguments and rollback remain unchanged.
**18 focused checks** and Ruff passed. Offline reconstruction from seven original events showed that a
longer explanation was truncated by the existing context budget. The final 96-character explanation is
fully retained: “522: circular reference. Unqualified cells use the destination sheet; qualify source references.”
No context budget or evaluation gate changed.

Condition `holo31-all-roles-order6-circular-reference-retest-20260912-v1` launched at
`2026-09-12T22:00:05.727415+00:00`, supervisor PID 26040 / tool session 37119, worker PID 26117,
selected orders `[6]`, `frozen_condition.status=ok`. Freeze time: 21:59:39 UTC. Source SHA-256:
`a084243ab70e623c627e9351233313d79304ba029427093d678f5fa721a8637b` (511 files, 81,102,048 bytes).
Config SHA-256: `ed4db943e04a0efa0e4fef1881555e77c69d77aab67e643bd858eae77afc246d`.
Both Holo roles, direct Holo1 endpoint, one-worker concurrency and budgets match attempt 1.
Runtime source, tests and config remain frozen through supervisor exit. The second affected attempt's
actual terminal result will be reviewed before deciding any extension.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves interrupted attempt 1
and records current Order **6 running**, **10 isolated attempts, 5 new PASS (42, 1, 2, 4, 5), 0 skips,
5 processed tasks and 88 pending tasks**. No regression/control episode runs, no new evaluator outcome is
claimed, and the full-run numerator remains 95/189. See the
[Order 6 report](archive/all-holo-order6-literal-cells-repair-20260912.md).

## 2026-09-12 21:53 UTC Order 6 literal writing verified online; interrupted for misleading Calc 522 recovery

Step 4 of Order 6's first isolated episode successfully wrote literal cells, with matching raw arguments,
Adapter payload and host conversion record. Steps 6/7 then submitted self-referencing formulas and received
native Calc error 522. The recovery text emphasized separators rather than explaining a circular reference.
After reading the source at step 9, the model repeated the formulas at step 10 and hit the existing repeated-error
block. The developer interrupted this demonstrated failure to correct the error explanation before another
newly frozen Order 6-only condition. Formula values, rollback and existing error handling remain unchanged.

Supervisor PID 60241 / tool session 37000 exited **130**; worker PID 60301 exited **0**. Final metadata at
`2026-09-12T21:53:37.646983+00:00` records `interrupted`, reward **null**, 10 steps, 458.208 seconds and
zero completion rejections. No evaluator ran. Worker integrity revalidation is `ok`; final supervisor integrity
is absent. The raw error says “by user,” but the actual interrupt was developer-initiated. Results SHA-256:
`5451985b6b38ff8d8437914e6ae7282a8c28438adbe944c3e0b19744b0f69208`.

Current Order **6 fixing** remains in progress, with no skip or evaluator outcome claimed. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves **9 isolated attempts,
5 new PASS (42, 1, 2, 4, 5), 0 skips, 5 processed tasks and 88 pending tasks**. No regression/control
episode ran; the immutable full-run result remains 95/189. See the
[Order 6 report](archive/all-holo-order6-literal-cells-repair-20260912.md).

## 2026-09-12 21:45 UTC Order 6 literal-cell compatibility frozen; isolated attempt launched

The Calc schema, manifest and UNO writer now accept exact JSON string, finite number, boolean and null
cells alongside existing typed cells. The existing Adapter executor preserves raw parameters and records a
bounded host conversion summary. Dimension checks and formula rollback remain; strings never imply
formulas or dates. **85 focused local checks**, Ruff and diff checks passed. Offline replay accepts the
schemas of all three original calls, while call 1 still returns `RANGE_INVALID` for its 10-target/6-value
row mismatch and calls 2/3 retain their valid model-selected headers. Correct source/formula planning
remains the model's responsibility and is unproven by these local compatibility checks.

Condition `holo31-all-roles-order6-literal-cells-retest-20260912-v1` launched at
`2026-09-12T21:45:48.516696+00:00`, supervisor PID 60241 / tool session 37000, worker PID 60301,
selected orders `[6]`, `frozen_condition.status=ok`. Freeze time: 21:45:29 UTC. Source SHA-256:
`cb2ce412e037f4783223bf963622e284b02ab8044e920d81391ff5bf3b450b48` (511 files, 81,098,851 bytes).
Config SHA-256: `1ce3819b094b012b17bc8aeafb7c7b654cb5d1907fafc587053738dc08483b35`.
Both roles use the original worker-06 Holo1 backend directly at `http://192.168.0.224:8002/v1`.
Public-proxy to LAN transport and 14-to-1 concurrency are recorded runtime differences from the full run;
model settings and episode/resource budgets remain. Runtime, tests and config stay frozen through exit.

Only current Order **6 running** is retested. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **9 isolated attempts,
5 new PASS (42, 1, 2, 4, 5), 0 skips, 5 processed tasks and 88 pending tasks**. No regression/control
episodes, new gates or evaluator changes are introduced; the immutable full-run result remains 95/189.
See the [Order 6 report](archive/all-holo-order6-literal-cells-repair-20260912.md).

## 2026-09-12 21:36 UTC Order 5 recovered PASS with string evidence; Order 6 selected

Order 5's first isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
9 steps and 611.492 seconds, finalized at `2026-09-12T21:36:46.591261+00:00`. Supervisor PID 23151 /
tool session 41609 and worker PID 23188 exited **0**. Supervisor final integrity and worker revalidation
are `ok`, with unchanged frozen source/config seals. Results SHA-256:
`a78e64623163d00e69f526196207328d7d47b44c98916dea07e5db835e735f97`.

Step 6 used array evidence and was correctly rejected for missing save/read-back. The model then saved at
step 7 and inspected at step 8. Step 9 submitted JSON-looking **string** evidence, which remained a raw
string and executed successfully. This episode exercised the repaired compatibility path online while
retaining the existing completion requirements. See the
[Order 5 report](archive/all-holo-order5-completion-evidence-repair-20260912.md). No regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **5 new isolated PASS
(42, 1, 2, 4, 5), 0 skips, 5 processed tasks, 8 isolated attempts and 88 pending tasks**. Current Order
**6 diagnosing** originally ended in `model_protocol_failure` after 1431.344 seconds and three structured
protocol attempts, with no evaluator execution; original worker-06 used Holo1. Its preserved trajectory is
the next diagnosis source, and no Order 6 episode has launched. The immutable full-run result remains 95/189.

## 2026-09-12 21:26 UTC Order 5 completion-evidence repair frozen; isolated attempt launched

Offline replay of both preserved evidence strings (215 and 318 characters) now passes representation
validation while still receiving the original ledger's missing-save and structural-readback feedback.
The 67 focused tests and Ruff passed; no new gate or evaluator change is introduced.

Condition `holo31-all-roles-order5-completion-evidence-retest-20260912-v1` launched at
`2026-09-12T21:26:21.518119+00:00`, supervisor PID 23151 / tool session 41609, worker PID 23188,
selected orders `[5]`, `frozen_condition.status=ok`. Freeze time: 21:25:52 UTC. Source SHA-256:
`acfb7bdd5051c2f5ffca0ce08380a538d54808dae757b1c5c58d41ae5b3a3e87` (510 files, 81,082,210 bytes).
Config SHA-256: `987b01e92fcaa798b2f59a898f7cf7cbcad09bff14ede375d403f4d8ecf2632a`.
Both roles use the original worker-05 Holo1 backend directly at `http://192.168.0.224:8002/v1`.
Public-proxy to LAN transport and 14-to-1 concurrency are recorded runtime differences from the full run;
model settings and episode/resource budgets remain. Source and tests stay frozen through supervisor exit.

Only current Order **5 running** is retested. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **8 isolated attempts,
4 new PASS (42, 1, 2, 4), 0 skips, 4 processed tasks and 89 pending tasks**. No regression/control
episodes run, no new evaluator outcome is claimed, and the immutable full-run score remains 95/189.
See the [Order 5 report](archive/all-holo-order5-completion-evidence-repair-20260912.md).

## 2026-09-12 21:25 UTC Order 5 completion-evidence compatibility locally verified

Order 5's preserved failure followed a corrected formula: the next model turn encountered a public-proxy
HTTP 502, then two valid-JSON `propose_done` calls were rejected because `evidence` was a string. The
compatibility repair accepts a nonempty string as one opaque evidence statement alongside the existing array
representation, retaining raw arguments and the existing state, save/read-back and contradiction checks.
No new gate or application action is added. **67 focused tests** passed across schema, new compatibility,
hybrid GUI completion and generic save recovery; Ruff passed. The main Agent is checking the original
failed claims offline and preparing a new frozen Order 5-only condition.

Current Order **5 locally verified** has **not launched** an isolated episode. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) still records **4 new isolated PASS
(42, 1, 2, 4), 0 skips, 4 processed tasks, 7 isolated attempts and 89 pending tasks**. Local checks do not
increase PASS or attempt counts. The immutable full-run result remains 95/189. See the
[Order 5 report](archive/all-holo-order5-completion-evidence-repair-20260912.md).

## 2026-09-12 21:15 UTC Order 4 original-evaluator PASS; Order 5 selected

Order 4's second isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
12 steps and 650.537 seconds, finalized at `2026-09-12T21:15:07.406624+00:00`. Supervisor PID 43255 /
tool session 82209 and worker PID 43282 exited **0**. Supervisor final integrity and worker revalidation
are `ok`, with unchanged config/source seals. Results SHA-256:
`1b796d77d18030503bf3e93ee37fcdc46adc34b110de2671839cec9503e6191a`.

The new native pivot inventory reached the model and it recognized overlap. Its step-7 move omitted
`replace` and returned `CONFLICT`; it ultimately saved the original overlapping pivots. The PASS records
the original evaluator's outcome; **it does not establish that the pivot layout was corrected**. That
quality limitation remains explicit in the [Order 4 report](archive/all-holo-order4-serial-startup-retest-20260912.md).
The first interrupted attempt remains preserved; no regression/control episode ran.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **4 new isolated PASS
(42, 1, 2, 4), 0 skips, 4 processed tasks, 7 isolated attempts and 89 pending tasks**. Current Order **5**
is diagnosing: its original episode ended in `model_protocol_failure` after 1159.183 seconds and three
structured protocol attempts, without evaluator execution. Original worker-05 used Holo1. Offline diagnosis
is examining completion-evidence string compatibility; no new episode has launched. The immutable full-run
result remains 95/189 and the promoted baseline is unchanged.

## 2026-09-12 21:04 UTC Order 4 pivot readback repair frozen; second isolated attempt launched

`workbook.inspect` now returns native pivot names and ranges from the Calc Adapter, retained in bounded
Agent context alongside structured errors. Existing tool descriptions clarify pivot shared-cell placement
and signed wheel units. No application action, default, validator or evaluation gate changes. **42 focused
checks** passed (23 pivot contract, 3 projection, 7 Holo and 9 chart), and Ruff passed.

Condition `holo31-all-roles-order4-pivot-readback-retest-20260912-v1` launched at
`2026-09-12T21:04:02.326468+00:00`, supervisor PID 43255 / tool session 82209, worker PID 43282,
selected orders `[4]`, `frozen_condition.status=ok`. Freeze time: 21:03:22 UTC. Source SHA-256:
`79c4fef879ef0487d4af3978feaa0caef0b28149c6e25a4fd2551130ce16bb12` (509 files, 81,075,664 bytes).
Config SHA-256: `72130a2c2f2c75acf4fef828bdec2f18e501adc1c87e546382a818b3fe2541e8`.
Both Holo roles, direct Holo1 endpoint, one-worker concurrency and episode/resource budgets match attempt 1.
Source remains frozen through supervisor exit; only Order 4 runs, without regression/control episodes.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves interrupted attempt 1
and records **7 isolated attempts, 3 new PASS (42, 1, 2), 0 skips, 3 processed tasks and 90 pending tasks**,
current Order **4 running**. No new evaluator outcome is claimed, and the integrated result remains 95/189.
See the [Order 4 report](archive/all-holo-order4-serial-startup-retest-20260912.md).

## 2026-09-12 20:57 UTC Order 4 interrupted for missing pivot inventory readback

The first isolated Order 4 episode reached the Agent after serial startup, so the original readiness failure
did not recur in this attempt. Repeated `workbook.inspect` calls exposed missing pivot-table inventory.
The developer interrupted to repair that existing-object readback and clarify pivot shared-cell placement
and signed wheel units. Startup success alone does not count as a recovered task.

Supervisor PID 1288 / tool session 18550 exited **130**; worker PID 1323 exited **0**. Final result metadata
at `2026-09-12T20:57:56.870187+00:00` records `interrupted`, reward **null**, 15 steps, 855.047 seconds,
and zero completion rejections. No evaluator ran. Worker integrity revalidation is `ok`; no final supervisor
integrity record was emitted. The raw KeyboardInterrupt text says “by user,” but the actual stop was
developer-initiated. Results SHA-256:
`4f471fac06cafa1d19641c7b5b35a79774cf6e147561a478a3fb0de3f0da7edf`.
The frozen config and raw results remain preserved.

Current Order **4 fixing** remains in progress. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **6 isolated attempts,
3 new PASS (42, 1, 2), 0 skips, 3 processed tasks and 90 pending tasks**. No regression/control episode
ran, no new gate is authorized, and the immutable full-run result remains 95/189. See the
[Order 4 report](archive/all-holo-order4-serial-startup-retest-20260912.md).

## 2026-09-12 20:43 UTC Order 4 serial startup recheck launched

Order 4's first isolated condition, `holo31-all-roles-order4-serial-startup-retest-20260912-v1`, started at
`2026-09-12T20:43:30.691207+00:00`, supervisor PID 1288 / tool session 18550, worker PID 1323,
selected orders `[4]`, `frozen_condition.status=ok`. Freeze time: 20:43:08 UTC. The unchanged source seal is
`143b8dda6b7ea01d1c062c8abdffeb38b24df20bdbece598dec4c67e14cbbba0` (508 files, 81,067,020 bytes).
Config SHA-256: `efd089a1b2e38954b9dddc3ac377fb38dbe239efd2da23fae6d9daba12f8b0b5`.
Both roles use direct Holo1 at `http://192.168.0.224:8002/v1`; original worker-04 metadata confirms its
Holo1 assignment. One-worker concurrency and direct transport are recorded changes from the full run.
No additional source or gate change is made; source remains frozen through exit.

Only Order 4 runs, without regression/control episodes. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **6 isolated attempts,
3 new PASS (42, 1, 2), 0 skips, 3 processed tasks and 90 pending tasks**, current Order **4 running**.
No Order 4 outcome is yet claimed. The immutable full-run numerator stays 95/189; see the
[Order 4 report](archive/all-holo-order4-serial-startup-retest-20260912.md).

## 2026-09-12 20:40 UTC Order 2 recovered PASS; endpoint provenance corrected; Order 4 selected

Order 2's second isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
10 steps and 411.928 seconds. Metadata finalized at `2026-09-12T20:40:32.223918+00:00`.
Supervisor PID 47232 / tool session 92032 and worker PID 47292 exited 0. Supervisor final integrity and
worker revalidation are `ok`, with source/config unchanged. Results SHA-256:
`19c97802f4c45ac8375fdcf1269d0d1af69c36d46c580374a0478bf98a0c2684`.
The chart call omitted header flags and used the documented true defaults, producing two value series and
ten categories. The model corrected two save-argument errors and completed. No regression/control episode ran.

Endpoint correction: earlier Order 2 prose describing “the same original Holo2 backend” was inaccurate.
The preserved full-run `workers/worker-02/metadata.json` assigns **Holo1** at
`https://holo1.jinmaoapi.cc.cd/v1`; both isolated Order 2 configs and actual workers used **direct Holo2**
at `http://192.168.0.138:8001/v1`. The original episode never reached inference, but the assigned endpoints
still differ. This additive correction supersedes those earlier descriptions without changing frozen configs,
results or scores. See the [corrected Order 2 report](archive/all-holo-order2-serial-startup-retest-20260912.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **3 new isolated PASS
(42, 1, 2), 0 skips, 3 processed tasks, 5 isolated attempts and 90 pending tasks**. Current Order **4** is
in diagnosis after its original 664.208-second VM timeout before any episode. Its original worker 04 also
used Holo1; the proposed serial recheck uses that backend directly at `http://192.168.0.224:8002/v1`.
See the [Order 4 report](archive/all-holo-order4-serial-startup-retest-20260912.md).
The immutable full-run numerator remains 95/189 and the promoted baseline is unchanged.

## 2026-09-12 20:33 UTC Order 2 chart category wording repair frozen; second isolated attempt launched

Two existing `chart.create` description strings now explain the role of `row_headers` for column-oriented
data and retain row-oriented series-label semantics. Nine existing chart tests and Ruff pass. Rendered
schemas excluding descriptions match the first attempt's actual request 9; native behavior, defaults,
validators and semantic arguments are unchanged. No new gate is added.

Condition `holo31-all-roles-order2-category-flag-retest-20260912-v1` launched at
`2026-09-12T20:33:27.172347+00:00`, supervisor PID 47232 / tool session 92032, worker PID 47292,
selected orders `[2]`, `frozen_condition.status=ok`. Freeze time: 20:32:56 UTC. Source SHA-256:
`143b8dda6b7ea01d1c062c8abdffeb38b24df20bdbece598dec4c67e14cbbba0` (508 files, 81,067,020 bytes).
Config SHA-256: `e5a5edde84f50e4177dee952c0159857e42205b0ec1de48913e4795961cf4c00`.
Models, direct Holo2 route, concurrency and budgets match the first isolated attempt. Source remains frozen
through exit; no regression/control episodes run.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves the first interrupted
attempt and records Order 2 attempt 2 running: **5 isolated attempts overall, 2 new PASS (42, 1), 0 skips,
2 processed tasks and 91 pending tasks**. No new evaluator outcome is claimed; integrated 95/189 remains
unchanged. See the [Order 2 report](archive/all-holo-order2-serial-startup-retest-20260912.md).

## 2026-09-12 20:30 UTC Order 2 interrupted for a demonstrated chart-description contradiction

The serial Order 2 episode booted and created Sheet2 and a chart. Steps 5 and 9 explicitly identify Week
as the category column in reasoning but select `row_headers=false`; the Adapter correctly returns three
value series (Week, Sales, COGS) and no category axis. Actual next requests retain those observations and
correction guidance. There is no demonstrated feedback loss. The top-level chart description nevertheless
unconditionally promises that the category range is not an additional series, contradicting the false flag.
The exact cause of the model's repeated parameter choice remains unproven.

The developer deliberately interrupted after that contradiction was established. Supervisor PID 20902 /
tool session 13210 exited **130**, worker PID 20930 exited **0**. Final metadata at
`2026-09-12T20:30:50.415030+00:00` records `interrupted`, reward **null**, 10 steps, 672.315 seconds,
and zero completion rejections. No evaluator ran. Worker integrity revalidation is `ok`; no final supervisor
integrity record exists. The raw runner labels the KeyboardInterrupt “by user”; the actual stop was
developer-initiated. Results SHA-256:
`92759a3be866e859da39e53f734a52f1eb081240496f8991daef2d648b9e36fa`.

Current Order 2 remains in progress, fixing the existing `chart.create` description to distinguish category
labels from plotted values for column-oriented data while retaining row-oriented series-label semantics.
Focused checks are underway; no retest outcome is claimed. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **4 isolated attempts,
2 new PASS (42, 1), 0 skips, 2 processed tasks and 91 pending tasks**. No regression/control episode ran;
the full-run 95/189 remains unchanged. See the
[Order 2 report](archive/all-holo-order2-serial-startup-retest-20260912.md).

## 2026-09-12 20:19 UTC Order 2 serial startup recheck launched

Order 2's first isolated attempt, `holo31-all-roles-order2-serial-startup-retest-20260912-v1`, started at
`2026-09-12T20:19:27.125187+00:00`, supervisor PID 20902 / tool session 13210, worker PID 20930,
selected orders `[2]`, `frozen_condition.status=ok`. Freeze time is 20:19:10 UTC; source remains
`d8071c6c4f5bf933a27581f8981b3f5200d22f11ed081bd249e87a9f0eb61bbe` (508 files, 81,066,494 bytes).
Config SHA-256: `2be174e13981791620c609d336de6668a2a43e186861e742dbf63fa825e5dbbe`.
One worker uses the original Holo2 backend directly for both roles at `http://192.168.0.138:8001/v1`.
There is no new source or gate change; existing episode/resource limits remain and source stays frozen through exit.

Only Order 2 runs; no regression/control episodes. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **4 isolated attempts,
2 new PASS (42, 1), 0 skips, 2 processed tasks and 91 pending tasks**, current Order **2 running**.
No Order 2 outcome is yet claimed. Full-run 95/189 and the promoted baseline remain unchanged; see the
[Order 2 report](archive/all-holo-order2-serial-startup-retest-20260912.md).

## 2026-09-12 20:17 UTC Order 1 recovered PASS; Order 2 selected next

Order 1's second isolated attempt completed with original-evaluator **reward 1.0 / passed**, `agent_done`,
5 steps and 335.777 seconds including lifecycle. Metadata finalized at `2026-09-12T20:17:26.199097+00:00`.
Supervisor PID 2476 / tool session 27280 and worker PID 2516 exited 0. Final supervisor integrity and worker
revalidation are `ok`; source/config seals match the launch. Results SHA-256:
`c10689a35488e4f9eacf557067ad0af19f01396d785b4e5a85a1597b2abcf7a0`.

The actual sequence is inspect, export, completion rejected only for read-back, inspect, accepted completion.
The original evaluator loads after the episode and returns PASS. The first interrupted attempt remains
preserved. No regression/control episode ran; see the
[Order 1 report](archive/all-holo-order1-serial-startup-retest-20260912.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **2 new isolated PASS
(42, 1), 0 skips, 2 processed tasks, 3 isolated attempts and 91 pending tasks**. Current Order **2** is in
diagnosis: its original VM readiness timeout lasted 662.701 seconds with no Agent steps or evaluator.
The next single-guest hypothesis reduces cold-start contention and uses the original Holo2 backend directly;
no additional source or gate change is proposed. Its launch remains to be recorded. See the
[Order 2 report](archive/all-holo-order2-serial-startup-retest-20260912.md).
The immutable full-run 95/189 and promoted baseline remain unchanged.

## 2026-09-12 20:11 UTC Order 1 export completion repair frozen; second isolated attempt launched

The existing `completion_policy.py` collector now counts successful instruction-relevant `.export` actions
as mutations while preserving export persistence and the existing read-back behavior. Synthetic direct,
forwarded, unexecuted and save-only cases use the existing save-recovery test module; **76 relevant tests
and Ruff pass**. Offline replay of the first attempt now requires only read-back at step 3 and accepts
step 11. These checks are not an evaluator PASS; no new gate is added.

The new `holo31-all-roles-order1-export-evidence-retest-20260912-v1` condition started at
`2026-09-12T20:11:36.154045+00:00`, supervisor PID 2476 / tool session 27280, worker PID 2516,
selected orders `[1]`, `frozen_condition.status=ok`. Source seal:
`d8071c6c4f5bf933a27581f8981b3f5200d22f11ed081bd249e87a9f0eb61bbe` (508 files, 81,066,494 bytes).
Config SHA-256: `834d7ef9f072870093e035c6658fe0b6f8c2eff4eb00beb9dbec454179931c7e`.
Both Holo models, direct Holo1 endpoint, one-worker concurrency and budgets match the prior isolated attempt.
Source stays frozen through exit; only Order 1 runs, with no regression/control episodes.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) preserves the interrupted first
attempt and records Order 1 attempt 2 running: **3 isolated attempts overall, 1 new PASS (42), 0 skips,
1 processed task and 92 pending tasks**. Its original-evaluator outcome is pending. The integrated full-run
result remains 95/189. See the [Order 1 report](archive/all-holo-order1-serial-startup-retest-20260912.md).

## 2026-09-12 20:09 UTC Order 1 startup recovered; attempt interrupted for proven completion defect

The serial Order 1 attempt booted, deployed and reached Agent execution. Step 2 successfully exported the
requested CSV (128 bytes); step 7 read it back. Nevertheless, completion repeatedly claimed that
`workbook.export` had not succeeded. The existing collector categorizes `.export` as a persistence action
and excludes it from task-changing evidence. This is a demonstrated framework defect; successful startup
alone is not an evaluator PASS and does not prove the original cold-start failure's exact cause.

The developer deliberately interrupted the episode after this rejection repeated, preserving 18 steps and
5 completion rejections. Supervisor PID 41567 / tool session 15144 exited **130**; worker PID 41577 exited.
Final metadata at `2026-09-12T20:09:03.146352+00:00` records `interrupted`, reward **null**, duration
647.348 seconds. The evaluator never loaded. The raw runner's generic message says “interrupted by user”;
the actual initiator was the developer responding to the demonstrated bug, not a new user stop request.
Worker final integrity revalidation is `ok`, including unchanged source/config; no final supervisor integrity
record was emitted, so none is claimed. Results SHA-256:
`896bd8e1b0f414912cc1a33fcc0c6450e0e80d35f2264554da8fc9cb83dd2a7b`.

Order 1 remains in progress, now fixing the existing export classification before another separately sealed
episode. This interrupted attempt is neither an evaluator failure nor a skip. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) retains **2 isolated attempts,
1 new PASS (42), 0 skips, 1 processed task and 92 pending tasks**. No regression/control episode was run.
The full-run 95/189 and promoted baseline stay unchanged. See the
[Order 1 report](archive/all-holo-order1-serial-startup-retest-20260912.md).

## 2026-09-12 19:58 UTC Order 1 serial startup recheck launched

Order 1's first isolated attempt started at `2026-09-12T19:58:05.184283+00:00`, supervisor PID 41567 /
tool session 15144, worker PID 41577, selected orders `[1]`, `frozen_condition.status=ok`.
The condition is `holo31-all-roles-order1-serial-startup-retest-20260912-v1`; one worker replaces the original
14-worker cold-start wave. Both roles use the same original Holo1 backend directly at
`http://192.168.0.224:8002/v1`. These changed runtime inputs are recorded separately from the frozen full run.
The source seal remains `6b0a1d4bf5a387a88b7785a23efd16b58c117b168fb3b7309f72c6859886d140`;
there is no additional source or gate change. Source stays frozen through supervisor exit.

This one-task episode tests whether VM startup can complete under reduced contention; only original-evaluator
PASS counts as recovery. No regression/control episodes run. The
[ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records **2 isolated attempts,
1 new PASS (42), 0 skips, 1 processed task**, current Order **1 running**, and 92 pending tasks.
No Order 1 retest outcome is claimed yet. The full-run numerator remains 95/189; see the
[Order 1 report](archive/all-holo-order1-serial-startup-retest-20260912.md).

## 2026-09-12 19:54 UTC Order 42 recovered PASS; Order 1 selected next

Order 42's first isolated all-Holo repair attempt completed with original-evaluator **reward 1.0 / passed**,
`agent_done`, 399.891 seconds including lifecycle. The final metadata time is
`2026-09-12T19:54:54.916161+00:00`; supervisor PID 22367 / tool session 18541 and worker PID 22414 exited 0.
Worker integrity revalidation and final integrity are `ok`, with the frozen source seal unchanged.
Results SHA-256: `f5d6e30acba12c888df4e04f5c10308fe5c590f2b6d361cba460b1dfcfe64fa6`.

Actual step 12 executes `slides.format_text_roles`. The next completion rejection requests only final
save/read-back; the erroneous singular-action requirement is gone. Model-selected save at 14, inspect at 15
and completion at 16 lead to the original evaluator PASS. Both the source repair and direct Holo2 transport
change remain recorded, so this is not a source-only comparison. No regression/control episode ran.
See the [completed repair report](archive/all-holo-order42-role-format-repair-20260912.md).

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) now records **1 new isolated PASS
(42), 0 skips, 1 processed task**, and Order **1** as the current diagnosis. Order 1's preserved full-run
failure was a 690.986-second VM readiness timeout before model or evaluator execution. The next hypothesis
is that using one worker instead of the 14-worker cold-start wave reduces resource contention; no new runtime
repair or gate is presumed necessary. Its separate condition and prospective episode remain to be recorded.
The immutable full-run result stays **95/189** and the promoted baseline pointer is unchanged.

## 2026-09-12 19:47 UTC Order 42 compatibility repair frozen; affected-only retest launched

The existing completion path now recognizes the declared successful plural role-format action alongside its
singular form. Focused verification passes 24 tests and Ruff; offline replay of the preserved trajectory
leaves only save/read-back requirements at step 9 and accepts the saved/read-back state at step 45.
This is implementation evidence, not an evaluator PASS. No new API or gate is added.

The new `holo31-all-roles-order42-role-format-retest-20260912-v1` condition seals 508 source files,
81,064,092 bytes, SHA-256 `6b0a1d4bf5a387a88b7785a23efd16b58c117b168fb3b7309f72c6859886d140`.
Both Holo roles now use `http://192.168.0.138:8001/v1`, the same Holo2 backend/snapshot through a direct
route. Both source and transport changes are registered; this is not a source-only comparison.
The one-task supervisor started at `2026-09-12T19:47:49.866409+00:00` (PID 22367, tool session 18541,
worker PID 22414), with selected orders `[42]` and `frozen_condition.status=ok`. Source remains frozen
through exit. Only Order 42 runs; no regression/control episodes.

The [ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) records one running isolated
attempt, **0 new PASS and 0 skips**. No retest outcome is available yet. The immutable integrated result
remains 95/189; the promoted baseline remains unchanged. See the
[Order 42 repair report](archive/all-holo-order42-role-format-repair-20260912.md).

## 2026-09-12 19:41 UTC All-Holo fixed-189 completed; 94-task repair queue initialized

The authorized `holo31-all-roles-fixed189-20260912-v1-run1` completed all 189 scheduled outcomes:
**95 passed / 42 evaluator failed / 22 agent deadline / 10 model protocol / 16 model transport /
4 environment failure**. The measured full-denominator result is **95/189 = 50.264550%**. Legacy metadata
`success_rate=0.6934306569343066` instead uses `95/(95+42)` and excludes 52 abnormal terminal outcomes;
it must not be reported as this run's full-189 success rate.

Supervisor PID 64309 / tool session 53302 exited 0. Final metadata updated at
`2026-09-12T19:41:03.619965+00:00` records `status=completed`, `final_integrity.status=ok`, and unchanged
source/config seals. Results SHA-256 is
`4c1c466066e0f8d9d4805daa423c587e626fa08d1b7ff8c3a5adf958989ea76a`.
This is non-promotable exploration; the promoted v337 pointer and all historical scores remain unchanged.

The [94-task host-only ledger](../experiments/work/all-holo-failed-task-ledger-20260912.json) derives directly
from every non-passing result. Order 42 is the first current repair because its preserved trajectory proves a
valid plural role-format operation is missed by the singular completion requirement. All other tasks remain
pending in original order; read-only triage does not count as a skip. At initialization, isolated all-Holo
PASS is **0**, skips **0**, and isolated attempts **0**. Subsequent attempts are recorded separately.
Repair only this current task under a new frozen condition; the user explicitly excludes regression/control
episodes, another full run, new gates and baseline promotion. See the
[final report](archive/all-holo-fixed189-20260912.md) and [current reference](current-repair-reference.md).

## 2026-09-12 All-Holo GOAL enabled; authorized fixed-189 evaluation launched

The user replaced the blocked Qwen-service objective with Holo 3.1 4B throughout planning, tool selection,
result review and GUI grounding, authorized one complete fixed-189 run, and asked to enable GOAL without
further questions. Root GOAL and the active goal mechanism are enabled. The earlier service blocker is
superseded by this model choice; the Qwen-Holo +8 isolated PASS and 22 skips remain historical counters.

The new frozen condition is `holo31-all-roles-fixed189-20260912-v1`, source SHA-256
`b5a82e1119db7488b3169abe71d5408dcf9af822b03267b692dd7febbf39877d` (508 files).
The supervisor launched at approximately 15:56 UTC with 14 workers, seven assigned to each user-provided
Holo endpoint. Each worker's two roles use its same endpoint sequentially. Existing 100/50 step, one restart,
1800 Agent-second and 30 GiB disk limits remain. No runtime edits are permitted through supervisor exit.
Focused checks passed (115 endpoint/runner checks and 37 delegation/completion checks); both endpoints passed
synthetic main-tool and visual-grounding requests, with one Holo2 engine crash and successful recovery retained
as probe evidence. The full-run numerator is pending; isolated all-Holo repairs have not begun.

After completion, derive the queue from this run and retest only the current failure, without regression/control
episodes, new gates, another full run or baseline promotion. See the
[all-Holo report](archive/all-holo-fixed189-20260912.md) and [current reference](current-repair-reference.md).

At 16:13:50 UTC the first original-evaluator PASS is recorded (Order 10). Partial terminal counts are
1 PASS, 3 environment failures (VM readiness timeouts on 1,2,4), and 1 protocol failure (8). The latter is a
main-Holo typed-cell argument error with preserved feedback, not truncation or a grounding failure.
The full run continues with unchanged source. New isolated all-Holo PASS remains 0; repair has not begun.

## 2026-09-12 Order 108 file-read repair complete; retest awaits Qwen service

The latest preserved episode received all 8583 source characters from the
Adapter but exposed only 3228 to the model. Repeatedly increasing the API
limit could not repair the downstream 4200-character context cap. The repair
reuses the existing typed-text observation and adds an explicit character
window to `file.read_text`, including its default snapshot verification.
Focused message-chain, owning-Adapter and projection checks pass. Two broader
search-ranking checks still fail under the previous schema and are recorded
as pre-existing. Same-source offline reconstruction confirms all 8583
characters reach the actual normal model message. V1 was frozen at
08:32:56 UTC and launched for Order 108 only, but the existing model
preflight terminated it as `invalid_configuration`: the Qwen endpoint now
serves only Holo. Both processes exited, supervisor exit 2, final integrity
`ok` and source seal unchanged. No Agent episode or scorer ran. Read-only
checks confirm dgx2's Qwen container was stopped and both machines now run
Holo. No model service was changed here. A usable Qwen endpoint or service
restoration decision is required before another episode; no run is active.
After three consecutive confirmations of this same external blocker, the
goal is marked blocked pending that service decision. Its objective and
repair queue remain unchanged; Order 108 is not skipped.
Recent isolated PASS remains +8, skips 22 and current task is 108. The
integrated reference and promoted pointer remain unchanged. See the
[Order 108 report](archive/hybrid-order108-text-window-20260912.md).

## 2026-09-12 Order 107 native PDF and listener repairs retained; task skipped

Two prior header-projection probes were negative. A new offline check now
shows that default native PDF detection preserves complete rows, columns
and merged header spans that the text extractor does not represent.
Implement a single-file, single-page table read and focused synthetic
verification before one separately sealed affected-only episode. The model
still chooses every file, arithmetic operation and spreadsheet write.
Focused native, surface, deployment and projection checks passed. Source
was frozen at 06:56:07 UTC. V1 was stopped at 22 steps after Holo closed Calc
and forwarded reads repeatedly failed with an unavailable UNO listener.
Worker/supervisor exited with source unchanged; status `interrupted`, reward
null. No native table read or spreadsheet write occurred. Repair passive
Calc startup in the owning Adapter; targeted checks passed. V2 then exposed
GUI reopening of a live Office without its UNO listener. It was stopped at
34 steps, reward null, with both processes exited and source unchanged.
It read batch PDF text and issued one GUI cell-entry action, but never selected
the new table API. Official LibreOffice source confirms existing-process IPC
listener registration; the passive path is implemented and 31 related checks
pass. V3 finalized at 08:15 UTC with `agent_deadline_exhausted`, 22 events,
reward null, 1951.920 seconds including lifecycle and final integrity `ok`.
Supervisor exited 0; both processes exited and the source seal still matched.
The model repeatedly read flat PDF text, never selected the exposed native
table API, and made no spreadsheet write. Its first Calc read used a
misspelled path; the true error and observed correct workbook path survived
into model requests, and its second Calc read succeeded with the target
cells still empty. No listener failure occurred, so live IPC recovery was
not exercised. No new defect warrants a further episode; skip 107.
Recent isolated passes remain **+8 (2,24,30,49,57,143,144,175)**; skips become
**22 (65,77,87,93,95,97,98,100,101,102,104,106,107,109,116,117,118,130,132,141,163,189)**.
No experiment is running. Order 108 is selected for preserved-trace diagnosis.
The integrated reference and promoted pointer stay
unchanged. See the [Order 107 report](archive/hybrid-order107-native-pdf-table-20260912.md).

## 2026-09-12 Order 106 source-debugging failed; false repeat block repaired; task skipped

Order 103 has a completed hybrid evaluator PASS with final integrity and
Order 105 already has an isolated reward-1 result; neither is rerun or added
to the new-pass counter. Select original hybrid failure 106. Its latest
completed episode opened/scrolled/copied source but never read source text
or edited it. Current shared read/edit retrieval and observation/feedback
repairs justified one separately frozen affected-only recheck. It finalized
at 55 steps with `agent_deadline_exhausted`, reward null, 1939.603 seconds,
final integrity `ok`, and worker/supervisor exit 0. The evaluator did not run.
The model read source, installed a dependency and launched the game, but
made eight incorrect edits to the wrong rotation abstraction. Its final
file is syntactically invalid; the collision-handling method is unchanged.

V1 also demonstrated a shared defect: different forwarded errors
`COMMAND_FAILED` and `OPERATION_TIMEOUT` collapsed to one generic signature,
causing a false repeat block. After final exit, six production lines now
unwrap the existing downstream error before comparison; existing thresholds
and feedback are unchanged. One focused regression fails before and passes
after; 81 related tests, Ruff and a replay of the preserved failure sequence
pass. No gate or second Agent episode was added. The signature repair is
verified separately from the unresolved model source-editing failure.

Skip 106 without V2. This adds **0 PASS**; recent isolated passes remain
**+8 (2,24,30,49,57,143,144,175)**; skips become
**21 (65,77,87,93,95,97,98,100,101,102,104,106,109,116,117,118,130,132,141,163,189)**.
No experiment remains running, the next task is not selected, and the goal
remains active. The integrated 119/189 reference and promoted baseline are
unchanged. See the
[Order 106 report](archive/hybrid-order106-source-recheck-20260912.md).

## 2026-09-12 Order 102 filename loss repaired; classification still failed; task skipped

Order 102's existing exact-path move API lacked ordinary catalog synonyms;
the small metadata repair passes 34 discovery/rename-contract checks.
V1 completed with 39 steps,
`agent_deadline_exhausted`, reward null, 1960.392 seconds including lifecycle,
final integrity `ok`, and worker/supervisor exit 0. The evaluator did not run
after the abnormal termination. It copied 11 distinct files, misclassified
six, and never handled the project directories. Copying alone is not a
scoring failure: the evaluator compares target directory listings.

Actual requests also prove an unrelated UUID in an ordinary spreadsheet
filename was wrongly replaced with the internal-metadata marker; the model
then searched for that marker. V1 source remained frozen through exit.
The narrow projection fix passes 175 focused projection/boundary tests and
Ruff. V2 finalized with evaluator reward 0.0, 29 steps, 1212.148 seconds,
`agent_done`, integrity `ok`, and worker/supervisor exit 0. Actual requests
25–27 now preserve the full ordinary UUID filename/path while excluding
real task identity. Source remained frozen through final exit.

The model correctly placed both project directories, but the paper directory
still contains five miscellaneous files. Later API listings exposed these
contents; the model accepted completion without correcting the categories.
Keep the generic repairs and skip this task without a third attempt or new
gate. This adds **0 PASS**. Recent isolated passes remain
**+8 (2,24,30,49,57,143,144,175)**; skips become
**20 (65,77,87,93,95,97,98,100,101,102,104,109,116,117,118,130,132,141,163,189)**.
No experiment remains running and the next task is not selected. The
integrated reference stays 119/189; the promoted baseline is unchanged. See the
[Order 102 report](archive/hybrid-order102-move-discovery-20260912.md).

## 2026-09-12 Order 101 capability repaired; context loss fixed; task still failed

Order 101 V2 finalized with reward 0.0, 14 action steps, 900.456 seconds,
final integrity `ok`, and worker/supervisor exit 0. It created all seven
PDFs with 26 fields each; the first two actual fill requests preserved all
109 field choices and the complete source table. However, the model chose
SATISFACTORY for all 119 ratings and added an unrequested filename suffix.
The first four outputs have correct basic information but 59 of 68 ratings
wrong. Raw model calls and saved values agree. There were no action errors
or model retries; the terminal audit accepted the incorrect completion.

Keep the generic PDF APIs and reproduced context repairs, but close this
task without a third attempt or extra gate. This adds **0 PASS**; recent
isolated passes remain **+8 (2,24,30,49,57,143,144,175)**. Skips become
**19 (65,77,87,93,95,97,98,100,101,104,109,116,117,118,130,132,141,163,189)**.
No experiment remains running. The next task is not selected, integrated
reference stays 119/189, and the promoted baseline is unchanged. See the
[Order 101 report](archive/hybrid-order101-pdf-form-capability-20260912.md).

## 2026-09-12 Order 101 implementation and first-attempt diagnosis

Rechecked 87's preserved GIF/reference metadata: the documented mismatch
persists, with no demonstrated media defect. Order 93's native-find and
timeout hypotheses already have code verification and negative task/usage
outcomes. Do not replay either task. These offline dispositions add no PASS.
Recent isolated passes remain +8; skips become
**18 (65,77,87,93,95,97,98,100,104,109,116,117,118,130,132,141,163,189)**.

Current task 101 has a missing public capability: the source PDF has named
AcroForm fields but active APIs cannot inspect/fill them. Add two ordinary
operations for reading actual field metadata and writing explicit values
into one selected output. The model owns every mapping and filename; no
batch workflow or evaluation gate is added. Implementation now passes 52
focused tests and changed-file Ruff. Host-only synthetic filling of the
actual blank template saved and visibly rendered all 102 selected fields;
this is capability evidence, not an Agent PASS. Both non-executing Qwen
schema preflights returned HTTP 200 and valid synthetic calls. Source is
frozen and V1 completed with reward 0.0, 23 action steps and worker exit 0.
It created five partial PDFs with unrequested filename suffixes. Actual
messages prove the 9K retry lost most fields and two spreadsheet rows; even
the ordinary 13K per-hint budget reduced 109 fields to 12. Repair this
observed information loss before a separately frozen second attempt of 101.
V2 now removes redundant PDF metadata and retains 24K for form recovery;
156 focused tests pass. Actual-message rebuilding preserves 109 fields and
all 208 source cells. The separate V2 source was frozen and run on the same
task; its final negative result and disposition are recorded above.
See the
[Order 101 report](archive/hybrid-order101-pdf-form-capability-20260912.md).

## 2026-09-12 Order 100 archive layout correct; photo selection failed; task skipped

Order 99 already passed in September 6 evidence and is not rerun. Order 100
has no recovered hybrid PASS: its latest episode guessed photo identities
from thumbnails, then produced an archive with unwanted parent directories
after a rejected `cd`/`&&` direct-exec call. Repair only the existing shell
error's overescaped example and missing explicit-cwd usage guidance; do not
change parameters, execution, APIs or gates. The new synthetic case fails
before the change; 55 focused cases and changed-file Ruff pass after it.
The affected-only current-model validation completed with reward 0.0,
47 steps, 1529.683 seconds including lifecycle, integrity `ok`, and worker
exit 0. The existing archive API created the correct relative directory
layout, but the model omitted two required photos and included an unwanted
one. It had recognized the two omitted photos; it lost their pending copy
operations and even misremembered closing a viewer as copying a file.
There were no command calls, so the changed shell error was not
exercised by the live episode. No terminal environment or transport failure,
same-VM restart, or completion rejection occurred. Stop without V2.
See the [Order 100 report](archive/hybrid-order100-command-directory-feedback-20260912.md).
This adds 0 PASS. Recent isolated passes remain
**+8 (2,24,30,49,57,143,144,175)**; skips become
**16 (65,77,95,97,98,100,104,109,116,117,118,130,132,141,163,189)**.
No experiment remains running and no next live task is registered. The
immutable integrated reference and promoted baseline pointer are unchanged.

## 2026-09-12 Order 118 visibility improved; evaluator still failed; task skipped

The first recheck completed with evaluator reward 0.0 after 6 steps and
399.079 seconds, final integrity `ok`, worker exit 0. It ran the command in
a background process and captured an empty terminal. The existing handoff
policy is `os`-only and did not apply to this forwarded `multi_apps` episode;
do not broaden it. Added only truthful visibility feedback to the existing
background command result: stdout/stderr were not displayed in an already
open terminal. Direct/forwarded feedback and related command/projection
tests pass 99 cases; Ruff and scoped diff checks pass.

V2 completed with evaluator reward `0.0`, `agent_done`, 10 steps, and
461.338 seconds; final integrity was `ok`, worker exit 0. It received the
new feedback and then selected `terminal.show_output` followed by a capture
of that exact window. Unlike V1, the PNG contains command output. However,
the model chose `ls -la`, whose long listing scrolled the command line out
of the captured viewport; the unchanged evaluator still rejected it. This
is an observed behavior improvement, not isolated causal proof or a PASS.
See the [Order 118 report](archive/hybrid-order118-terminal-capture-recheck-20260912.md)
for immutable results and verified config/source/results hashes.

Stop Order 118 with no V3 or further wording variant. This task adds **0
PASS**. Recent isolated passes remain **+8 (2,24,30,49,57,143,144,175)**;
skips become **15 (65,77,95,97,98,104,109,116,117,118,130,132,141,163,189)**.
The integrated reference stays 119/189 and the promoted v337 pointer is
unchanged. No experiment is running at closure; no next task has launched.

## 2026-09-12 Order 117 archive grammar repair recheck failed; task skipped

Order 110 already has isolated PASS evidence and was not rerun. The final
September 8 episode's incomplete archive arguments were traced to a serving
grammar that rejected valid complete calls. The existing owning schema repair
passes 10 direct/forwarded tests and the earlier non-executing model snapshot.
The current-source episode did not call the archive API: it used `zip` via
`terminal.launch`, so the schema mechanism was unexercised. The model
exported the supporting reminder document instead of the
essay. Evaluator reward was `0.0`, status `failed`, `agent_done` after 10 steps
and 367.242 seconds; integrity was `ok`, with no transport, environment,
deadline, or completion-rejection issue. The earlier snapshot supports the
grammar repair, but this episode does not verify it and did not recover
source-document activation or staged workflow planning. See the
[Order 117 report](archive/hybrid-order117-archive-schema-recheck-20260912.md).

This task adds **0 PASS**. Recent isolated passes remain +8; recorded skips
become **14 (65,77,95,97,98,104,109,116,117,130,132,141,163,189)**. The
integrated reference remains 119/189 and both baseline references are
unchanged. Next selected task: Order 118, a separate current-source check of
the existing terminal screenshot handoff repair. The registration is recorded
in the [Order 118 report](archive/hybrid-order118-terminal-capture-recheck-20260912.md).

## 2026-09-12 Order 109 closed; unsuccessful ranking change withdrawn

Both current-source Order 109 attempts finalized with evaluator reward 0.0,
integrity `ok`, and worker exit 0. V1 stopped on repeated-read stall after 22
steps; V2 ended normally on the 1800-second Agent budget after 58 steps and
51 Adapter calls, without creating the output document. V2 was not manually
interrupted. The new Writer composition boost also displaced relevant tools
for JSON-reading searches because it matched the whole instruction; withdraw
that predicate, score block, and its added test only. Earlier repairs and raw
evidence remain intact. The affected file passes 18 local tests; Ruff and
scoped diff checks pass. No post-withdrawal live attempt is planned. See the
[Order 109 report](archive/hybrid-order109-current-recheck-20260912.md).

This task adds **0 PASS**. Formally close 97, 98, and 109 as skipped; 98 is an
offline disposition of exhausted historical hypotheses, not a new hybrid run.
Recent isolated passes remain **+8 (2,24,30,49,57,143,144,175)**; skips are
**13 (65,77,95,97,98,104,109,116,130,132,141,163,189)**. The integrated
reference stays 119/189 and the promoted v337 pointer is unchanged. No
experiment remains running at closure. Review the next original failure's
preserved trajectory and existing PASS evidence before selecting a live run.

## 2026-09-12 Order 97 atomic-route retest remained unsuccessful

The affected-only condition
`qwen35-holo31-hybrid-order97-notes-routing-retest-20260912-v2` ended
`agent_deadline_exhausted` after 25 steps, 11 Adapter calls, 26 LLM calls,
and about 1945 seconds including lifecycle. Final integrity was `ok`, with
zero environment or transport failures. Qwen selected `presentation.inspect`
and repeated `slide.set_notes`, but never selected `document.read_file` or
`presentation.save`; Holo returned one malformed numeric `y` during repeated
GUI checks. No evaluator PASS was obtained. The atomic catalog route is
available, so this is a model-planning/convergence failure rather than a
missing gate or transport defect. See the [Order 97 hybrid retest report]
(archive/hybrid-order97-notes-routing-retest-20260912.md).

The prior v73-v76 generic-only Order 97 hypotheses remain exhausted. Order 98
is next for queue review; its independent v76-v79 generic-only hypotheses are
already task-blocked and should not be repeated without a materially different
shared model/framework change. No full-run numerator, baseline pointer, or
promotion state changed.

## 2026-09-11 Order 2 current-source recheck passed

The affected-only Order 2 recheck under current source condition
`qwen35-holo31-hybrid-order2-current-recheck-20260911-v3` passed the original
evaluator with reward `1.0`, `agent_done`, 9 action steps, and 621.839 seconds
including lifecycle. Final integrity was `ok`; there were no transport,
environment, or deadline failures. The model first selected inconsistent
category/value row spans and received the existing truthful empty-chart
`INVALID_REQUEST`; it then corrected the model-owned ranges and header flag,
created the two-series `Sales & COGS` chart on `Sheet2`, saved, inspected it,
and completed. No runtime source, API, gate, scorer, or baseline pointer
changed. See the [Order 2 report](archive/hybrid-order2-current-recheck-20260911.md).

Recent isolated passes are now **+8 (2, 24, 30, 49, 57, 143, 144, 175)**;
skips remain **+10 (65, 77, 95, 104, 116, 130, 132, 141, 163, 189)**.
The immutable hybrid `119/189` reference and promoted v337 pointer remain
unchanged. No experiment is running. Next selected task: **Order 97,
read-only diagnosis**. Its original trajectory used the retired notes-transfer
macro and then repeated GUI Notes-view checks until timeout; no retired macro
will be restored. Do not repeat Order 2 unchanged.

## 2026-09-11 Order 95 stopped after shared sanitizer repair

Final v5 reached `agent_deadline_exhausted` after 36 actions / 1933.567
seconds including setup, with final integrity `ok`, worker exit 0, and no
evaluator result. The first four-file and later long PDF windows were visible
without sanitizer placeholders, but Qwen repeated pagination and GUI/header
setup and never produced a final workbook. V3's earlier reward-0 workbook
was structurally correct; its only evaluator mismatches were two source email
values, not the accepted `Email` header. Preserve all five conditions and
skip Order 95 rather than adding task-specific handling. Recent isolated
passes remain +7; skips become +10 `(65,77,95,104,116,130,132,141,163,189)`.
No full-run numerator, gate, baseline or promotion changed.

## 2026-09-11 Order 95 shared sanitizer repair ready for final verification

V4 was intentionally interrupted after 23 actions / 947.49 seconds, reward
null, with no evaluator or final integrity result. The context projection
layer no longer hid the first read, but the separate `safety.py` result
sanitizer still hid a later 20000-character PDF window. Finish the same
generic fix by sharing punctuation-delimited prose route matching between
both layers; structured/error fields and exact tool routes remain strict.
Cross-layer and real-PDF checks: 182 passed; Ruff passed. Freeze one final
new-seal affected-only v5 attempt, then stop this task if it does not pass.
See the [Order 95 report](archive/hybrid-order95-pdf-reader-retest-20260911.md).

## 2026-09-11 Order 95 context repair reached evaluator, then found sanitizer false positive

V3 completed normally with integrity `ok` and reward 0.0 after 54 steps /
1885.055 seconds. It created the correct four-row sorted workbook. The
evaluator accepts the `Email` header via its includes rule; two source emails
were incorrect.
The trace also showed an entire 16000-character PDF window replaced by
`<internal-benchmark-metadata>` because ordinary prose `task, execute
subtasks` normalized to forbidden route `task.execute`. Preserve V3 as an
immutable scored failure. Scope the generic sanitizer's normalized-route
check to punctuation-delimited prose clauses while retaining fail-closed
structured/error checks; 82 focused checks pass. Register one final new-seal
affected-only attempt for this demonstrated generic defect. See the
[Order 95 report](archive/hybrid-order95-pdf-reader-retest-20260911.md).
No baseline, full run, gate, commit or promotion change.

## 2026-09-11 Order 95 inherited-window metadata correction

V2 saw the previously missing email, then lost it on the next context rebuild.
Stop and preserve the run as interrupted, reward null, 507.059 seconds;
both processes exited before edits, with no evaluator or final integrity
result. Recovery failed to inherit file-level length metadata after slimming
removed its per-chunk duplicate. Repair that existing contract only. All
80 focused checks pass; rebuilding actual history now retains the missing
middle detail after 5, 9 and 11 events. Register one justified new-seal v3
attempt at the two-attempt checkpoint. See the
[Order 95 report](archive/hybrid-order95-pdf-reader-retest-20260911.md).
Recent isolated passes +7, skips +9, current task 95; no new task PASS,
regression episode, gate, full run, commit or promotion.

## 2026-09-11 Order 95 complete-window context repair

The first affected attempt found and executed the PDF reader, but actual
model requests lost the middle of an 8000-character single-file read. Stop
and preserve v1 as interrupted, reward null, 661.001 seconds; both processes
exited before edits, with no evaluator result or final integrity assertion.
Normal projection now uses the existing per-file allowance, and recovery
preserves a complete requested window even when the source continues. Total
context budget is unchanged. Focused checks: 78 passed; Ruff passed. Actual
trace reconstruction confirms the previously missing middle text reaches
the model. Register one new-seal affected-only attempt for this confirmed
defect; see the [Order 95 report](archive/hybrid-order95-pdf-reader-retest-20260911.md).
Recent isolated passes +7, skips +9, current task 95; no new task PASS yet,
gate, regression episode, full run or change to either baseline reference.

## 2026-09-11 Order 95 PDF reader usage repair

Select original failed Order 95 after reconciling existing PASS evidence and
earlier closed investigations. Its preserved September 6 trace reads only
20 lines per paper, then writes incomplete author data and fails the original
evaluator. The current generic PDF reader already supports page/text windows.
Add plural-article recall and correct the existing cursor usage description;
no extraction algorithm, dedicated author API, gate or scorer change. Register
one fresh-guest affected-only check after focused tests and a new seal. See the
[Order 95 report](archive/hybrid-order95-pdf-reader-retest-20260911.md).
Recent isolated passes +7, skips +9; current task 95. No old PASS is counted
again and no integrated numerator is changed.

## 2026-09-11 Order 77 ordered-boundary retest timed out; task skipped

V2 finished `agent_deadline_exhausted`, reward null, 37 action events /
1855.992 seconds including setup. The step-38 request exhausted the deadline;
no original evaluator score was obtained. Both processes exited 0 and final
source/config integrity was `ok`. The model chose a boundary list immediately
but did not correct an apostrophe mismatch after truthful error feedback.
It switched to literal backslash-r replacement and then repeated completion
claims: 16 rejected/blocked submissions, unchanged paragraph count, 14 visible
backslash-r sequences and one altered source apostrophe. Native ordered
insertion had no successful live execution in this attempt. See the
[Order 77 outcome](archive/hybrid-order77-native-paragraph-split-20260911.md).

No new PASS and no third attempt. Recent isolated passes **+7
(24, 30, 49, 57, 143, 144, 175)**; skips **+9
(65, 77, 104, 116, 130, 132, 141, 163, 189)**. The existing completion gate's
misleading missing-mutation feedback is recorded separately from the malformed
document; no gate was changed. No experiment is running. Next: review the next
preserved original hybrid failure, without another unchanged Order 77 attempt.
The immutable 119/189 reference and older promoted v337 pointer are unchanged.

## 2026-09-11 Order 77 deadline outcome and ordered-boundary repair

Native-split v1 reached `agent_deadline_exhausted`, reward null, 29 action
events / 1862.013 seconds including setup; final integrity `ok`, processes
exited. Six splits preserved characters, but stale paragraph indices caused
retries and two redundant end-of-paragraph insertions. No evaluator score
was obtained. Extend the same primitive to an explicit ordered literal list
with successive first-match semantics and reverse-order native insertion.
One further affected-only attempt is the recorded review-checkpoint decision;
no gate, regression, full run or baseline update. See the
[Order 77 report](archive/hybrid-order77-native-paragraph-split-20260911.md).
The v2 condition is frozen with 112 focused checks and Ruff passed; model
identity endpoints responded, and the independent affected-only run is ready.
Recent isolated passes +7, skips +8; current task 77.

## 2026-09-11 Order 77 explicit source-preserving paragraph split

The preserved full-read failure still rewrites Unicode punctuation and
source spaces; earlier wording/local-replacement probes were negative.
Add one native `paragraph.split` primitive with a model-selected paragraph,
unique literal boundary and gap count. It inserts only paragraph breaks and
returns the observed parts/new index, without detecting sentences or
re-authoring text. Focused checks: 101 passed; Ruff passed. Production tool
reconstruction confirms the action is exposed. Register one affected-only
fresh-guest run; see the [Order 77 report](archive/hybrid-order77-native-paragraph-split-20260911.md).
Recent isolated passes +7, skips +8; current task 77. No gate, regression
episode, full run or change to the immutable integrated score is added.

## 2026-09-11 Order 65 preserved text but still failed; task skipped

The affected-only run finished `failed`, reward 0.0, `agent_done`, 57 action
events / 58 model turns, 1713.046 seconds including setup. Final integrity
was `ok`; both processes exited 0. Saved DOCX parsing confirms unchanged
text across all 12 paragraphs and zero tab characters. All 10 nonempty
paragraphs received tab formatting, but the only executed literal edit
replaced an anchor with itself. The terminal review accepted an unsupported
completion claim. See the [Order 65 outcome](archive/hybrid-order65-local-tab-insertion-20260911.md).

Recent isolated passes **+7 (24, 30, 49, 57, 143, 144, 175)**; skips **+8
(65, 104, 116, 130, 132, 141, 163, 189)**. No second attempt, gate, scorer
change, regression cohort or full run is added. No experiment is running;
the goal stays active. Next queue review: Order 77, starting with its
preserved negative probes, not an unchanged replay. The immutable 119/189
reference and older promoted v337 pointer remain unchanged.

## 2026-09-11 Order 65 local tab insertion and native layout observation

Current task 65 retains its failed full-text/coverage trajectory. Its tab usage
pointed to destructive whole-paragraph replacement and its inspection omitted
page width/margins. Clarify existing local literal insertion and expose native
in-use page layouts without selecting a position or paragraph. Focused checks:
71 passed; Ruff passed. Register one affected-only new-seal attempt, with no
new API, restored macro, gate or scorer change. See the
[Order 65 report](archive/hybrid-order65-local-tab-insertion-20260911.md).
Recent isolated passes +7, skips +7; no integrated score update. Existing
31/34/41/45 PASS evidence was read, not rerun or counted again.

## 2026-09-11 Order 30 recovered after post-GUI inspection guidance

The second prompt-only affected attempt completed `passed`, reward 1.0,
`agent_done`, 8 action events / 295.064 seconds including setup. The model
invoked the native feature, inspected its generated page and completed without
rewriting it. One Holo coordinate-type error recovered through existing
feedback. The original evaluator confirmed matching files. Final integrity
was `ok`; supervisor and worker exited 0. No retired API, gate or scorer change
was introduced. See the [Order 30 outcome](archive/hybrid-order30-native-feature-retest-20260911.md).

This repair turn recovered Orders 24 and 30. Recent isolated passes **+7
(24, 30, 49, 57, 143, 144, 175)**; skips **+7 (104, 116, 130, 132, 141,
163, 189)**. The goal remains active, with no experiment running and the next
original failed task not yet selected. These isolated results do not change
the immutable 119/189 reference or the older promoted v337 pointer. No third
Order 30 attempt, regression cohort, full run or promotion is launched.

## 2026-09-11 Order 30 native-feature diagnosis and prompt-only repair

The original failure generated the native summary but was rejected on
unchanged body-text run segmentation. The Sep6 failure instead substituted
hand-written text and overwrote an existing slide without invoking the named
feature. Add only generic hybrid prompt guidance to use an explicitly named
built-in feature, leaving the exact GUI requests and inputs model-selected.
Keep the retired macro absent and scoring/serialization unchanged. Register
one affected-only new-seal attempt after focused verification; see the
[Order 30 report](archive/hybrid-order30-native-feature-retest-20260911.md).
Recent isolated passes +6, skips +7, current task 30; no integrated score change.

The first affected run finished failed, reward 0, 11 events / 343.0 seconds,
final integrity ok; both processes exited 0. Native menu selection now worked,
but Qwen misread the populated output as blank and overwrote it. Add only
generic post-GUI fresh-inspection guidance for one reviewed second attempt;
no new gate or forced action. The report preserves the unmet behavior target.

## 2026-09-11 Order 24 recovered with model-selected relative placement

The second affected-only run completed `passed`, reward 1.0, `agent_done`,
16 action events / 641.409 seconds including setup. The model selected both
relative anchors and their one-row gaps; the owning Adapter converted them
to A7 and A13, preserving the original arguments and native output ranges.
The original evaluator confirmed PASS. Final integrity was `ok`; supervisor
and worker exited 0. Preserve the first reward-0 attempt and the remaining
long-generation/redundant-inspection evidence. See the
[Order 24 outcome](archive/hybrid-order24-pivot-row-feedback-20260911.md).

Recent isolated passes **+6 (24, 49, 57, 143, 144, 175)**; skips **+7 (104,
116, 130, 132, 141, 163, 189)**. Next task 30 is at read-only diagnosis.
No new gate, regression cohort, full run, score aggregation or promotion.
These isolated checks leave the immutable 119/189 repair reference unchanged.

## 2026-09-11 Order 24 native row feedback repair

Resume the original failed Order 24 with a new hypothesis from its preserved
Sep9 grouping-v2 trajectory: the model guessed a table height despite reading
the correct occupied range. The singular pivot return now also exposes the
native row count and one-based last row; usage explains blank-row arithmetic
without choosing any destination. Register one current-source affected-only
attempt after focused verification. No new API, macro, gate or scorer change.
See the [Order 24 report](archive/hybrid-order24-pivot-row-feedback-20260911.md).
Recent isolated passes +5, skips +7, current task 24; no integrated score change.

The first run completed `failed`, reward 0, 14 events / 602.148 seconds,
final integrity `ok`; both processes exited 0. Native row fields reached the
model, but its placement arithmetic still left two blank rows between tables.
After exit, extend only the singular pivot destination representation with
explicit `below_range` and `blank_rows`, preserving the model's request and
the Adapter's resolved A1 coordinate. One second affected-only new-seal run
is reviewed in the report; no batch, automatic next action or new gate.

## 2026-09-11 Order 189 feedback verified, task skipped

The second affected attempt reached `agent_deadline_exhausted`, reward null
(no evaluator score), 53 recorded action events / 1853.472 seconds including
setup. Final integrity was `ok`; supervisor and worker exited 0. The actual
model requests prove that started-then-ended guidance and structured paused
variable context survived projection. Source reading/discovery and execution
sequencing still failed; four Holo calls supplied coordinate arrays instead
of scalar integers. See the [complete evidence and disposition](archive/hybrid-order189-debug-picker-feedback-20260911.md).

No new PASS from either Order 189 attempt. **Recent isolated passes +5
(49, 57, 143, 144, 175); skips +7 (104, 116, 130, 132, 141, 163, 189).**
No experiment is running and no third attempt is launched. Keep the goal
active and select the next original hybrid failure without isolated PASS
evidence. No new gate, evaluator change, full run, integrated score or
promotion; the immutable reference remains unchanged.

## 2026-09-11 Order 189 picker resolved; remaining feedback repaired

The first Sep11 Agent attempt finished `failed`, reward 0, 48 steps /
1569.572 seconds, final integrity `ok`; both processes exited 0. It resolved
the actual debugger/configuration selectors and reached paused variable
inspection, but reread an unchanged list and claimed completion too early.
After exit, correct the observed started-then-ended error feedback and
preserve structured variable context before body truncation. Keep the
existing verifier verdict and all gates unchanged. Focused tests: 44 passed;
Ruff passed. One new-seal affected-only retest is reviewed in the
[Order 189 report](archive/hybrid-order189-debug-picker-feedback-20260911.md).
Recent isolated passes remain +5, skips +6, current task 189. No integrated
score or baseline-pointer update.

## 2026-09-11 Order 189 native debugger-picker feedback

The preserved repeated-debug-start failure omitted an open native selector.
One model-free public-API diagnosis confirmed that its prompt is an input
placeholder and its choices are live list-box items. The operator result is
reward 0 and zero model requests, not an Agent score. After its clean exit,
the owning VS Code Adapter now returns these observations and existing GUI
recovery guidance promptly. It does not choose a debugger or repair source.
Focused checks: 44 passed; Ruff passed. Register one affected-only frozen
Agent attempt; see the [Order 189 report](archive/hybrid-order189-debug-picker-feedback-20260911.md).

Recent ledger: **new isolated passes +5 (49, 57, 143, 144, 175); skipped +6
(104, 116, 130, 132, 141, 163); current task 189**. No new gate, evaluator
change, control, regression cohort, integrated score or promotion.

## 2026-09-11 Order 175 recovered under the original evaluator

The corrected-identity affected run finished `passed`, reward 1.0,
`agent_done`, 2 steps / 107.936 seconds including setup. One model-selected
`workspace.open` opened the full nested path directly; the native observation
found only the requested workspace. The original evaluator confirmed it.
Final integrity was `ok`; supervisor and worker exited 0. No new runtime
source, API, gate, evaluator change, or regression task was added. See the
[Order 175 outcome](archive/hybrid-order175-workspace-open-retest-20260911.md).

Recent ledger: **new isolated passes +5 (49, 57, 143, 144, 175); skipped +6
(104, 116, 130, 132, 141, 163); current task 189, read-only diagnosis**.
The immutable hybrid full-run numerator remains 119/189 and the promoted
v337 pointer is unchanged. These isolated checks do not establish a new
integrated success rate or five first historical passes.

## 2026-09-11 Order 175 setup diagnosis corrected

The two Sep8 setup failures were caused by a mistyped host-config task ID and
wrong source_order, not intermittent example-file availability. Both preserved
tracebacks name the incorrect path. The canonical row from the original repair
config loads successfully through the existing isolated projection helper.
Preserve old configs/results; register one affected-only condition using the
structurally extracted canonical record and current direct-path usage. Its
existing focused description test passes; no runtime code or new gate is added.
See the [Order 175 report](archive/hybrid-order175-workspace-open-retest-20260911.md).

Recent ledger: **new isolated passes +4 (49, 57, 143, 144); skipped +6 (104,
116, 130, 132, 141, 163); current task 175**. No regression task, evaluator
change, integrated numerator update or promotion is part of this check.

## 2026-09-11 Order 163 skipped after evidence recheck

The preserved Sep8 affected result remains reward 0.9897855178912893 with
final integrity ok: a valid MP3 export and normal completion, but not original
evaluator PASS. The historical model-free native VLC alternative was worse
at 0.9816658425864843, and current FFmpeg reproduction was byte-identical.
No new reusable fidelity hypothesis is established; do not tune against the
reference artifact, change the scoring threshold, or repeat the same episode.
The [audio report](archive/hybrid-vlc-audio-export-retest-20260908.md) records
this dated queue disposition. No model/VM experiment or source edit was added.

Recent ledger: **new isolated passes +4 (49, 57, 143, 144); skipped +6 (104,
116, 130, 132, 141, 163); next task 175, not launched**. Orders 145/146/147/149
retain their earlier isolated PASS evidence and are not counted as skips or
new passes. The immutable hybrid full-run numerator remains 119/189.

## 2026-09-11 Order 144 recovered without another source change

The affected-only condition completed `passed`, reward 1.0, `agent_done`,
2 steps / 152.104 seconds including setup. The model-selected relative output
path was accepted, its file contents were verified, and structured completion
evidence reached the unchanged evaluator. The original evaluator confirmed
success. Final integrity was `ok`; both worker and supervisor exited 0.
See the [Order 144 evidence](archive/hybrid-order144-relative-output-retest-20260911.md).

No new runtime code, API, gate, regression cohort or evaluator modification
was required. Recent ledger: **new isolated passes +4 (49, 57, 143, 144);
skipped +5 (104, 116, 130, 132, 141)**. The immutable hybrid numerator remains
119/189 and the promoted pointer is unchanged. Orders 145/146/147/149 have
existing isolated PASS records and are not rerun. Next unrecovered task is
163, whose retained audio-fidelity diagnosis is being checked before any run.

## 2026-09-11 Order 144 relative-output verification

Select Order 144 for one affected-only current-source attempt. The preserved
Sep4 trace rejected the same relative output filename three times before
execution. The current owning Adapter already accepts that filename and
resolves it from the live terminal directory; the existing focused native
test passes. No runtime code, API, evaluator, or gate is added. See the
[Order 144 report](archive/hybrid-order144-relative-output-retest-20260911.md).

Recent ledger: **new isolated passes +3 (49, 57, 143); skipped +5 (104, 116,
130, 132, 141); current task 144**. No control or regression task is launched,
and no integrated numerator or baseline-pointer change is made.

## 2026-09-11 Order 143 recovered under the original evaluator

The v3 affected-only attempt completed `passed`, reward 1.0, `agent_done`,
9 steps / 282.221 seconds including setup. The original evaluator confirmed
the directory structure and all matching files. The route was generic API
only; final integrity was `ok`, and the supervisor and worker exited 0.
All 10 model calls ended `tool_calls` with 3,256 total output tokens and no
protocol recovery. Captured requests confirm the existing complete-call stop
was enabled. See the [complete Order 143 evidence](archive/hybrid-order143-copy-retest-20260911.md).

Preserve v1/v2 failures, redundant copies, and repeated existing-file errors.
The successful calls used the existing directory-copy API; the opt-in parent
creation branch is focused-test verified but is not proven to have caused
the PASS. No fourth attempt, new gate, evaluator modification, regression
cohort, full run, or promotion is added.

Recent ledger: **new isolated passes +3 (49, 57, 143); skipped +5 (104, 116,
130, 132, 141); next task 144, not launched**. The original hybrid full-run
numerator remains 119/189 and the promoted baseline pointer is unchanged.

## 2026-09-11 Order 143 existing copy repair verification

The Sep8 copy attempt exposed a native directory-target conflict; its owning
Adapter correction was focused-tested after exit but not replayed. Register
one current-source affected-only attempt with no new runtime code or gate.
The focused copy file passes 7 tests. See the [Order 143 report](archive/hybrid-order143-copy-retest-20260911.md).
Preserve the older Sep2 different-source integrated PASS and later failures;
this attempt measures current isolated recovery, not a first historical PASS.

v1 finished `failed`, reward 0, 6 steps / 593.300 seconds, final integrity
`ok`; both processes exited 0. It selected the correct root but copied one
source to three directories and missed the other two sources. A file supplied
as a destination directory also raised an unhandled FileExistsError. After
exit, convert that demonstrated conflict to the existing explicit path-error
contract before copying, and clarify one-source fanout in the public usage.
The focused file passes 9 tests and Ruff. Register one changed-source v2
attempt; no new API, gate, regression cohort, or third attempt is added.

v2 finished `failed`, reward 0, 18 steps / 1266.732 seconds, final integrity
`ok`; both processes exited. It copied all sources but failed to place two
at the required nested paths. A correct exact-file path was rejected because
its parent was missing. At the two-attempt review, extend the existing copy
API with explicit optional `create_parents`, preserving the default false
and separate replacement policy. Copy-focused checks pass 21 tests and Ruff.
Register one third changed-source attempt for that capability and the already
implemented opt-in complete-call stop, omitted from v1/v2. The detailed report
records the extension reason; no fourth attempt or new gate is registered.

Recent ledger: **new isolated passes +2 (49, 57); skipped +5 (104, 116, 130,
132, 141); current task 143**. No regression or full-run evaluation is started.

## 2026-09-11 Order 141 closed without a recovered pass

The second affected-only attempt finished `failed`, reward 0, `agent_done`,
5 steps / 169.330 seconds including setup. Both native preference writes and
read-backs succeeded, but the model did not open a new terminal to verify
startup behavior. The completion gate and separate terminal audit accepted.
The supervisor and worker exited 0, and final integrity was `ok` with the
registered source unchanged. See the [Order 141 report](archive/hybrid-order141-terminal-profile-retest-20260911.md).

Preserve both failed Agent attempts and the model-free diagnostic. No third
same-task attempt, automatic launch, new gate, or evaluator change is added.
Recent ledger: **new isolated passes +2 (49, 57); skipped +5 (104, 116, 130,
132, 141); current task 143, read-only diagnosis**. Order 142 already has an
isolated PASS and is not rerun. The full-run numerator and promoted pointer
remain unchanged.

## 2026-09-11 Order 141 native default-profile capability

Select Order 141 next. Orders 136, 138, and 142 already have isolated PASS
records and are not rerun. The preserved 141 traces show the former size
macro failing during a bundled terminal launch, then repeated CLI schema
discovery failures after that macro was removed. Four earlier prompt/usage
attempts are preserved; this attempt adds a native owning-Adapter capability.

`terminal.default_profile.inspect` lists keys or reads one typed preference;
`terminal.default_profile.set_setting` persists one model-selected key/value.
Native GSettings resolves the current default profile inside the OS Adapter.
The existing GSettings verifier checks persisted values. No window restart,
inferred key/value, revived size macro, evaluator change, or new gate is added.
Register one fresh-VM affected-only attempt after focused checks/source seal;
see the [Order 141 report](archive/hybrid-order141-terminal-profile-retest-20260911.md).

v1 finished with reward 0 after five steps / 157.619 seconds, integrity `ok`.
The requested values were saved and verified, but the evaluator obtained
`null`; recording shows its command reaching a desktop search dialog before
a terminal was ready. A separate model-free, non-promotable diagnosis found
the correct shortcut, opened a terminal through the existing public launch
API in 1.05 seconds, and let the unchanged evaluator read the untouched
`24 80` defaults. No diagnostic result is counted as an Agent score.
Add only startup-verification usage to the owning setting description, then
register one changed-source affected-only v2 attempt. Window launch remains
a separate model-selected action; no scorer delay or completion gate changes.

Recent ledger: **new isolated passes +2 (49, 57); skipped +4 (104, 116, 130,
132); current task 141**. No integrated score or baseline-pointer update.

## 2026-09-11 Order 132 closed; error-path feedback corrected

Order 132 completed with `agent_deadline_exhausted`, no evaluator reward,
34 recorded events / 2163.294 wall seconds including setup, and final
integrity `ok`. The 1800-second Agent limit was unchanged. Both processes
exited. Startup had a Java-install HTTP 500 recovered by the existing deploy
retry; no in-run source or guest repair was applied.

The live filename fix succeeded: all ten submission paths remained visible,
and the model read them plus the reference document. The normal step-26
request retained all eleven complete document bodies. However, four
4096-token generations ended without a call, recovery projections dropped
prior body text, and repeated searches/reads never reached a spreadsheet
write or save. These are remaining convergence/context limitations, not PASS.

After exit, repair another demonstrated error-path false positive: the two
existing sensitive-word matchers must treat underscores as identifier
characters. The native missing-file path now survives direct and forwarded
error feedback into model messages. The new synthetic cases failed before
the correction; afterward 49 focused tests passed, with Ruff/diff checks
clean. Offline replay of the actual raw error also preserved its native
message/code/path. This post-run patch has no new Agent-score claim and is
not included in the completed condition's source seal. No new API, gate,
evaluator change, or second live attempt was added. See the
[Order 132 report](archive/hybrid-order132-filename-feedback-retest-20260911.md).

Recent ledger: **new isolated passes +2 (Orders 49, 57); skipped +4 (Orders
104, 116, 130, 132); current task closed, next unrecovered reference failure
not yet selected**. The immutable hybrid `119/189` numerator and promoted
baseline pointer remain unchanged.

## 2026-09-11 Order 130 closed; Order 132 filename feedback repair

Order 130 v3 completed with `agent_deadline_exhausted`, no evaluator reward,
61 recorded events / 1966.918 seconds including setup, final integrity `ok`.
Opening/launch tools appeared in the search, but repeated GUI navigation and
source reads did not converge on a saved document. All three attempts remain
preserved; no fourth attempt is planned. See the
[Order 130 report](archive/hybrid-order130-text-composition-retest-20260910.md).

The next preserved failure, Order 132, exposes a deterministic feedback bug:
ten real student DOCX paths returned by `filesystem.find` were replaced with
`<internal-benchmark-metadata>` because their filenames contained
`answer_sheet`. Move that ambiguous identifier from the substring blacklist
to the existing metadata-key filter. Ordinary filenames remain visible;
structured answer metadata and the other benchmark/forbidden-route checks
remain hidden. See the [Order 132 report](archive/hybrid-order132-filename-feedback-retest-20260911.md).

Recent ledger: **new isolated passes +2 (Orders 49, 57); skipped +3 (Orders
104, 116, 130); current task: Order 132**. No full-run numerator or promoted
baseline pointer changes.

## 2026-09-10 Order 130 current-source affected-only validation

One fresh-VM attempt is registered for Order 130, which has no independent
hybrid PASS. The reference trace found five workspace files but returned an
empty-check `VERIFICATION_FAILED`; the current workspace discovery contract
already fixes that false failure. The later integrated attempt instead spent
most of its budget in GUI/path recovery and saved an incomplete document.
Current discovery/read recall, formatting usage, and complete-text projection
repairs justify one changed-source check, not an unchanged retry.

v1 failed with reward `0.0`, 17 steps / 511.394 seconds, final integrity
`ok`. Its preserved request proves errors were visible, but compound and
recovery searches omitted workspace discovery because their relevance rule
missed ordinary `VS Code project` wording. After v1 exited, reuse the existing
project-file intent helper in cross-application search; no API, gate, or
evaluator changed. The focused workspace/search file passes 48 tests and Ruff.
v2 successfully discovered and read all five source files, then exhausted
the deadline without an evaluator reward: later Writer-creation searches
were still overridden by instruction-level file-composition priorities.
Restrict those priorities to relevant current queries and add ordinary
Writer keywords to the existing launch action. No new API is needed.
The expanded focused checks pass 56 tests, with Ruff/diff checks clean.
One final changed-source v3 attempt is registered; no further same-task
resampling is planned after that outcome.
See the
[Order 130 report](archive/hybrid-order130-text-composition-retest-20260910.md)
and conditions `qwen35-holo31-hybrid-order130-text-composition-retest-20260910-v1`
through `qwen35-holo31-hybrid-order130-text-composition-retest-20260910-v3`.
Repair ledger before this attempt: **new isolated passes +2 (Orders 49, 57);
skipped +2 (Orders 104, 116); current task: Order 130**. The immutable hybrid
`119/189` reference and promoted v337 pointer remain unchanged.

## 2026-09-10 Order 122 completed results recorded

This entry reconciles already-completed evidence; it is not a new experiment.
Order 122 v1 failed with reward `0.0` after 64 steps: a successful
`workbook.read_file` observation was not recognized by the existing open-file
contract. The minimal repair recognizes a verified read with matching document
identity/path. In v2 that rejection disappeared, but the model selected
`workbook.create_new` for an existing workbook and later exhausted the Agent
deadline; there was no evaluator reward. Both conditions finished with final
integrity `ok`. The earlier focused checks passed 114 tests.

See the [Calc read-file report](archive/hybrid-calc-read-file-observation-repair-20260910.md).
No PASS is added, no unchanged Order 122 retry is planned, and the recent
Orders 49/57/104/116 ledger is not retroactively changed.

## 2026-09-10 Order 116 skipped after model-planning failure

The affected-only Order 116 condition completed with evaluator reward `0.0`.
The attempt was infrastructure-healthy: final integrity was `ok`, with zero
protocol, transport, environment, or deadline failures. The existing
no-progress stop ended the episode after 47 steps / 1142.534 seconds. The
preserved trace shows repeated model-selected `vs_code.file.replace_literal`
calls with short anchors that appended duplicate code after an incomplete
script run. Adapter responses reported the real successful replacements; no
error was hidden or intercepted.

No runtime source or gate changed. This is a model-planning failure, so Order
116 is recorded as **skipped +1**, not as an infrastructure regression and not
as a reason to add a gate. See the [Order 116 report](archive/hybrid-order116-retest-20260910.md)
and condition `qwen35-holo31-hybrid-order116-retest-20260910-v1`.

Repair ledger: **new isolated passes +2 (Orders 49, 57); skipped +1 (Order
116); current task completed: Order 116**. These isolated results do not
change the immutable hybrid `119/189` reference or promoted v337 baseline.
Continue with exactly one fresh evaluator attempt for the next candidate.

## 2026-09-10 Order 104 skipped after answer-format failure

The affected-only Order 104 condition completed with evaluator reward `0.0`.
The attempt was infrastructure-healthy: final integrity was `ok`, with zero
protocol, transport, environment, and deadline failures. It ended as
`agent_done` after 55 steps / 2016.890 seconds. The model read the source
documents and executed two successful `table.insert_after_text` mutations,
but saved tables instead of the expected plain-text answer layout, then
declared completion. The Adapter returned actual successful operation results;
no error was hidden or intercepted. Repeated reads also show that the current
projection repair did not yield a recovered task under this model context.

No runtime source or gate changed. This is a task/model answer-format failure,
so Order 104 is recorded as **skipped +1**, not as an infrastructure
regression and not as a reason to add a gate. See the [Order 104 report](archive/hybrid-order104-text-window-retest-20260910.md)
and condition `qwen35-holo31-hybrid-order104-text-window-retest-20260910-v1`.

Repair ledger: **new isolated passes +2 (Orders 49, 57); skipped +2 (Orders
104, 116)**. These isolated results do not change the immutable hybrid
`119/189` reference or promoted v337 baseline. Continue with exactly one fresh
evaluator attempt for the next candidate.

## 2026-09-10 Complete typed-chunk projection repair verified offline

Order 104's trace exposed a reusable projection defect after the live Adapter
response: a complete 2,424-character Writer observation had already become a
typed chunk, but recovery compaction unconditionally reduced it to 320-character
head/tail windows. The fit-before-compaction repair handled raw `text` but not
this typed-chunk shape. The minimal generic fix preserves only chunks whose
source and context flags are both complete and whose offsets cover the full
`0..total_chars` range; partial windows keep the existing cap.

The focused context projection suite passes **72 tests**, with Ruff and
`git diff --check` clean. The new active-v2 source seal is 489 files,
80,846,067 bytes, `02794c3b1f484ff038014a7b3c6caea4b35bd06627da9bc5d51ce367f00c2055`.
This is offline repair evidence only: no Agent run or score update was made,
and no new gate was added. See the [complete-chunk repair report](archive/hybrid-text-window-complete-chunk-repair-20260910.md).

## 2026-09-10 Impress Order 49 recovered

The affected-only Order 49 condition completed with evaluator reward `1.0`.
Qwen inspected the live Impress deck, selected the `Features` slide and target
object, created the requested 5-by-2 table, saved, and terminated in 6 steps /
192.264 seconds. The evaluator comparison confirmed the table dimensions and
slide structure. The route was `generic_api_only`; final integrity was `ok`,
with no protocol, transport, environment, or deadline failure. No runtime
source or gate changed for this retest. See the [Order 49 report](archive/hybrid-impress-order49-retest-20260910.md)
and condition `qwen35-holo31-hybrid-impress-order49-retest-20260910-v1`.

Repair ledger: **new isolated passes +2 (Orders 57, 49); skipped +0; current
task completed: Order 49**. These isolated results do not change the immutable
hybrid `119/189` reference or promoted v337 baseline. Continue with exactly one
unrecovered task and one fresh evaluator attempt.

## 2026-09-10 Impress Order 57 recovered

The affected-only Order 57 condition completed with evaluator reward `1.0`.
The model applied the requested right, center, and left alignments to the
three live text targets through the existing atomic `shape.format_text`
contract, saved, read back the result, and terminated normally in 17 steps /
1295.339 seconds. The route was `generic_api_only`; final integrity was `ok`,
with 18 Qwen calls, 15 Adapter calls, no environment recovery, and no
protocol/transport/environment/deadline failure. No runtime source or gate
changed for this retest. See the [Order 57 report](archive/hybrid-impress-order57-retest-20260910.md)
and condition `qwen35-holo31-hybrid-impress-order57-retest-20260909-v1`.

Repair ledger: **new isolated passes +1 (Order 57); skipped +0; current task
completed: Order 57**. This isolated result does not change the immutable
hybrid `119/189` reference or promoted v337 baseline. Continue with exactly
one unrecovered task and one fresh evaluator attempt.

## 2026-09-09 Editor read recall repaired offline

The catalog query `edit file command line` previously returned the existing
literal-replacement action but omitted `vs_code.file.read_text` from Top-6. Add
the generic `edit` term to the existing read action metadata; no API, schema,
gate, prompt, or execution behavior changed. A second deterministic check found
that an explicit path query (`read /tmp/report.txt`) tied with
`debug.variables.read`; a narrow path/extension-aware retrieval weight restores
`file.read_text` precedence while paused-debug variable queries still prefer
`debug.variables.read`.

The focused workspace/search contract suite passes `46/46`; Ruff and
`git diff --check` pass. This is offline repair evidence only: no model, VM,
evaluator, or full-189 run was started, and the immutable hybrid 119/189
reference plus promoted v337 baseline remain unchanged. See the
[editor read recall report](archive/hybrid-editor-read-recall-repair-20260909.md).

## 2026-09-09 Holo scroll bound retest completed; text projection issue isolated

The changed-contract 104/110 pair completed 1/2. Control 110 passed in 6
events / 279.177 seconds with final integrity ok. Affected 104 ended
`agent_deadline_exhausted` after 1943.476 seconds including setup, with no
environment, transport or protocol failure and no evaluator reward. The
model-selected Holo scroll amount `-500` reached the executor unchanged, so
the former Holo-only range rejection is removed in live execution. The model
then read both test documents and the answer document, but did not save the
requested answers before the existing Agent deadline.

Offline replay of the preserved requests found a separate reusable cause: a
complete 2,424-character Writer read is projected to two 320-character chunks
even when the per-hint budget is sufficient. An in-memory fit-before-compaction
prototype preserves 2,000/2,400-character windows without changing events or
arguments. This is recorded as a new diagnosis, not applied during the frozen
pair and not counted as a task pass. Stop unchanged 104 retries; next candidate
is task 116 under a new condition. See the [scroll report](archive/hybrid-holo-scroll-units-repair-20260909.md)
and [text-window diagnosis](archive/hybrid-small-text-window-preservation-20260909.md).

After the pair exited, the minimal fit-before-compaction fix was applied to
the generic text projection. It preserves a complete raw text batch when the
existing per-hint budget fits, including the forwarded Multi-Apps wrapper,
while retaining the established cap for already-chunked or oversized results.
Direct/forwarded regressions plus Writer/command/context suites pass (104
tests); Ruff and diff checks pass. This has no Agent score yet and requires a
new sealed condition for live validation.

## 2026-09-09 DOCX retest completed; Holo-only scroll bound removed

The frozen 104/110 pair completed 1/2 with both workers and the supervisor
exiting 0 and unchanged source/final integrity ok. Control 110 passes in 6 events
/ 295.257 seconds. Affected 104 exhausts its unchanged 1800-second Agent budget
after 57 events (1945.559 seconds including setup), with no evaluator reward.
It discovers the actual DOCX paths but never selects document.read_file, instead
cycling through document windows and navigation controls without writing answers.
Two Qwen 4096-token no-call responses recover on the third attempt. Holo returns
24 responses: 19 dispatches, two scroll-range rejections and three coordinate-type
errors. Refreshed screenshots retain the previous public error as intended.

The existing read-only checks find no request-hash or executed-argument mismatch.
They still flag the deadline's missing model identity and three deliberate
pre-Holo duplicate blocks; retain those audit flags, not an all-audits-passed claim.
See the [DOCX pair report](archive/hybrid-docx-reading-retest-20260909.md).

Two independent Holo-only description probes are both negative semantically:
they return valid +10/+15 scroll amounts for a down intent. Preserve both and
do not adopt the wording changes. Ownership inspection instead identifies the
Holo-only [-20, 20] limit: the native and existing GUI signed-integer contracts
accept the original -30. After all processes exit, remove only those two schema
constraints. Two new regression cases fail before the change; all 41 Holo tests
and Ruff then pass. Offline real-grounder/gateway replay preserves both original
-30 calls at a capture-only executor, with zero network or GUI actions. No new
gate or semantic argument rewriting is added. The task effect is not live-tested;
the next run requires a new frozen condition. See the
[scroll contract report](archive/hybrid-holo-scroll-units-repair-20260909.md).
The immutable 119/189 reference and promoted v337 pointer are unchanged.

## 2026-09-09 Holo error feedback survives screenshot refresh

The completed Writer trace proves that Holo requests at steps 12 and 14 differ
only in their screenshots. The previous amount=-30 schema failure was omitted
because feedback was keyed to the full image digest. After all workers exited,
exclude only image parts from feedback matching, not from the actual request or
evidence. Keep changed-intent/contract invalidation, one-shot clearing, schema
validation and model-selected coordinates unchanged. The refreshed-image test
failed before repair; all 221 Holo/Writer tests plus Ruff/diff checks now pass.
Offline replay of both actual requests/responses/PNGs confirms that only the
second system message gains the public error; no network or GUI action executes.
This is an offline-verified feedback fix, not a new Agent pass. A later live run
needs a new condition. See the
[Holo refreshed-screen report](archive/hybrid-holo-refreshed-screen-feedback-20260909.md).

## 2026-09-09 Writer reference usage and locator retrieval

The reference-usage pair preserved a 66 pass (9 events / 286.826 seconds) and
an engineering-interrupted, unscored 79 (24 read-only events / 981.231 seconds).
The model repeatedly omitted or guessed paragraph indices, never searched the
catalog, and explicitly wanted text.find while it was absent from Top-K. Original
calls and pagination feedback prove no Runner rewriting or hidden Adapter error.
The supervisor labels the interrupted worker invalid_configuration under its
existing reportability rules; worker/supervisor source/config checks were ok.
All processes exited before edits. The interrupted request remains incomplete;
do not count that pair as a full scored comparison.

Add only generic locator keywords and one owning-description sentence, with no
new API, gate, forced plan or execution change. All 182 focused tests and Ruff /
diff checks pass. The complete parameter schema is unchanged, 79 now sees the
existing locator, and 66 retains the same initial action list/order. The new frozen
pair completed: 66 passed in 6 events / 195.766 seconds; 79 exhausted its unchanged
1800-second Agent budget after 37 recorded events. It locates the exact marker,
appends the citation, discovers bookmark.create and creates the source bookmark,
but never applies native numbering and cannot resolve the numeric reference.
Later stale ranges and partial effects of failed field insertion impede recovery.
Both workers/supervisor exit 0 and final source/config checks pass. Captured hashes
and Holo boundaries pass; the existing Qwen audit flags the final timeout's absent
model identity, not a returned different model. Stop consecutive 79 replay after
this second affected attempt; no unchanged repeat is registered. See the
[Writer reference and locator report](archive/hybrid-writer-reference-usage-repair-20260909.md).
The immutable 119/189 reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Focused font pass and split-page completion repair

Order 62 now passes the original evaluator in 7 events / 244.527 seconds after
reusing the existing focused inspection and exact text-target repairs. No new
runtime code was needed for that pass. The 61 control exposed an independent
false rejection: all mutations were saved and both pages separately read back,
but completion kept only the last page. The coding agent stopped that repeated
loop at 19 events; 61 is interrupted, not scored. Both worker source checks passed.

The existing post-save observation helper now combines compatible page reads
without changing raw events or adding a gate. Missing-page evidence requests a
read-back rather than another underline/picture move. All 239 related tests,
Ruff and diff checks pass; offline step-15 replay removes the false rejection.
The new frozen 61 affected / 62 control pair completed 2/2 with unchanged limits:
61 passes in 10 events / 427.085 seconds and 62 in 7 events / 261.466 seconds.
61 uses one combined final read, so the split-read mechanism is directly proved
by preserved replay/tests rather than this live trajectory. Both workers and
supervisor exited 0 with unchanged source and final integrity ok. All 20 Qwen
request/boundary checks and captured artifact/inventory hashes pass. Neither task
uses Holo; one evidence-array schema error recovers and terminal failure counts
are zero. No unchanged repeat is planned.
See the [focused-font and split-read report](archive/hybrid-impress-focused-font-retest-20260909.md).
This does not change the immutable 119/189 reference or the promoted v337 pointer.

## 2026-09-09 Pivot grouping/counting usage clarified

The follow-up v2 is now complete, also 1/2: control Order 4 passes in 13 events
/ 366.504 seconds; affected Order 24 fails in 12 events / 362.545 seconds.
Same-field grouping/counting now produces all correct nonempty rows and
headings. The title uses a literal string and recovers from one merged-range
shape error immediately after the new hint. Remaining failure is excessive
blank rows from model-selected destinations, not count semantics or a native
error. All 27 Qwen responses end normally below 529 tokens; one Holo action
succeeds. Final integrity, source seals and existing read-only boundary/hash
checks pass. Stop consecutive Order 24 replay at this checkpoint and retain
all negative attempts; no recovered pass or new aggregate rate is claimed.

The completed layout pair exposed category/count field reversal in Order 24.
Clarify only public parameter descriptions, with no schema constraints or
argument changes. Direct/forwarded frequency and numeric-sum checks pass, and
the real prior schema is unchanged after descriptions are removed. All 195
related tests plus Ruff/diff checks pass. The new pair completes 1/2: Order 4
passes in 9 events / 284 seconds; Order 24 still fails in 25 events / 580 seconds.
All three category groupings, numerical values and layout now match; only the
three counted-field headings differ. All 36 Qwen calls end normally with at
most 818 tokens after opting into the existing complete-call stop. One Holo
delegation succeeds. Existing boundary/hash checks pass with frozen source.

At the two-attempt review, preserve that evidence and refine the description
to include the already-supported same-field grouping/counting capability.
Also clarify literal-text and merged-range feedback after eleven title-write
errors in the preserved episode. All 214 focused tests pass; one changed v2
affected/control pair is registered with unchanged budgets. No heading, source
field, value or coordinate is injected. See the
[grouping report](archive/hybrid-calc-pivot-grouping-retest-20260909.md).
No new API, gate, full-189 authorization or aggregate-score claim is implied.

## 2026-09-09 Pivot occupied range and missing merge tool repaired

Order 24's preserved trace exposed two reusable defects: native pivot results
omitted their output rectangle, and Top-K truncation before state filtering
kept the required merge tool invisible. The singular native API now returns
its observed `output_range` and destination sheet; selection filters before
the unchanged Top-K. No argument, next position, macro or gate is injected.
All 218 related tests and Ruff/diff checks passed. Original steps 3, 9 and 10
now expose the merge tool in the production model surface. The newly frozen
Order 24 plus Order 4 pair completed 1/2: control passed in 11 events, affected
failed in 15 events after normal save/readback and completion. The latter now
merges and formats the title, uses supported percentage display, and places
all three pivots with a blank row between native output ranges. Its remaining
error is grouping by individual record identifiers instead of categories.
Saved XLSX evidence confirms these observations. Both workers and supervisor
exited 0 with unchanged source and valid final integrity; the 29 captured Qwen
requests also pass existing read-only hash/boundary checks. See the
[pivot layout report](archive/hybrid-calc-pivot-layout-retest-20260909.md).
No affected task pass or aggregate-rate improvement is claimed. Next clarify
generic grouping/counting usage and consider the existing complete-call stop
option in a new frozen condition, not an unchanged replay or another gate.

## 2026-09-09 Pivot display schema restored and positive single-call result

Order 24's preserved September 6 replay exposed a missing enum in LiteAgent's
duplicate pivot-field schema. The model sent unsupported `percentage`, then
misread the native error as an unsupported field and omitted display semantics.
The model tools now reuse the owning Calc `PIVOT_DATA_FIELD`; native errors name
the unsupported value and existing choices. Five focused cases failed before
repair; the relevant suite then passed 180 tests plus Ruff/diff checks. Native
accepted values, arguments, APIs and evaluation gates did not change.

One newly frozen step-11 snapshot restored independently captured tool ordering
and changed only the data-field schema. On the current split endpoint, Qwen
returned a valid percentage-pivot call in 23.591 seconds / 469 output tokens,
selecting `total_percentage` instead of the invalid mode. Source stayed frozen,
no application action executed and the driver exited 0. This is a positive
single-call result, not an Agent pass or a whole-condition causal ablation.
See the [pivot schema report](archive/hybrid-calc-pivot-display-schema-20260909.md).

Next inspect native pivot output-range feedback before a whole-task replay:
the preserved results provide only anchors, and later placements overlap
earlier output. Do not restore the retired stacked macros or choose positions
for the model. Title merging remains unverified. Both baseline pointers and
the measured full-run numerator remain unchanged.

## 2026-09-09 Multirow PDF headers retained; second snapshot still negative

The PDF projection now prioritizes the first observed multilevel tabular label
block within its existing two-window allowance, and table offsets use the
actual source representation. A year-bearing tabbed title no longer prevents
header detection. Direct, normal and recovery synthetic checks cover grouped
labels, summary rows and nonzero offsets; all 175 related tests plus Ruff pass.
The real request retains nine full header/total pairs without raising budgets.

One new frozen snapshot returned HTTP 200 in 208.107 seconds, but again used
4096 output tokens and produced no call. It still misgrouped counts/amounts
and repeatedly enumerated the entire table. Source remained frozen; no tool
or task executed. Both changed-context snapshots are negative behavioral
evidence. Retain the proven observation fixes and stop Order 107 replay work
at this checkpoint; next triage the separately preserved Order 24 protocol
failure. See the [PDF context report](archive/hybrid-pdf-context-projection-20260909.md).
No API or gate was added; the immutable hybrid reference and v337 pointer
remain unchanged, and the greater-than-80-percent goal is not yet verified.

## 2026-09-09 PDF body starvation repair and remaining multirow-header loss

Order 107's normal context projection shrank nine complete PDF extractions
to eight files and 16 body characters. Normal projection now reuses existing
metadata slimming and actual-size fitting, preserving canonical handles,
offsets, source/context flags and the unchanged 18000-character budget.
Full production message assembly retains all nine files, 3694 body characters
and 3143 table-row characters; other request fields remain unchanged.
The focused suite passed 172 tests plus Ruff/diff checks. No API or gate changed.

One independently frozen Qwen snapshot returned HTTP 200 in 208.675 seconds
but exhausted 4096 output tokens with zero calls. Its reasoning repeatedly
confused numeric column roles; complete multirow count/amount headings remain
outside the approximately 205-character head windows. Source stayed frozen
through exit, and no application action executed. This is a negative behavioral
result, not service unavailability or a new task pass. Preserve the proven
projection fix, do not repeat unchanged, and inspect generic multirow-header
retention offline before any further model replay. See the
[PDF context report](archive/hybrid-pdf-context-projection-20260909.md).
The immutable hybrid reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Object encoding feedback and repeated-protocol recovery

Order 113's preserved malformed payload exposed incomplete object-encoding
guidance and identical recovery requests whenever no required field was
missing. Existing schema hints now explain native JSON objects and escaping
tabs/newlines; the repeated-response cue uses the existing ordinal for type
errors and zero-call responses too. Three counterfactual cases failed before
the change; 123 related tests then passed plus Ruff/diff checks. No validation
rule, retry budget, semantic argument, API or gate changed.

One independently frozen request-only replay returned HTTP 200 in 14.094
seconds with 260 output tokens and a valid public tool search. It stopped
repeating the string payload but did not execute any action, establish correct
clipboard encoding, preserve formatting or pass a task. Source stayed frozen
through exit. Retain the feedback correction and move to the preserved PDF
projection loss; no unchanged replay is queued. See the
[object feedback report](archive/hybrid-object-protocol-feedback-20260909.md).
The immutable hybrid reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Active-workbook feedback and remaining protocol/context failures

The existing Calc inspection now matches ordinary active-workbook searches;
missing-file errors include bounded live document identities without choosing
or reading a substitute. Relevant checks passed 176 tests plus Ruff. The
frozen Order 107/113 pair completed 0/2 with final integrity ok: 107 exhausted
the Agent deadline (19 events, 1959.956 seconds including lifecycle), and 113
failed protocol (four events, 331.700 seconds). No terminal environment or
transport failure occurred. Source remained frozen; 18 manifest and 33 request
hashes matched, all ten Adapter forwards preserved arguments, and every
process exited. See the [workbook report](archive/hybrid-active-workbook-recovery-20260909.md).

Order 113 used the new live-path error to correct its guessed file, then
corrected its sheet name; later string-payload errors still prevented any
clipboard call. Order 107 read the correct file directly, but repeated reads
and PDF extraction without writing. Its normal batch projection discarded
body headers, retaining only 16 body-chunk characters across eight visible
files, plus selected table rows, from nine fully extracted PDFs. Keep this
as the next text-projection diagnosis rather than launching an unchanged run.
Neither isolated result changes the immutable hybrid reference or promoted
v337 pointer. The object-feedback follow-up has focused checks and a separately
completed positive request-only probe, not a new whole-task pass.

## 2026-09-09 Impress native failure feedback and recovered picture-height task

Order 55 exposed an actual native-result contradiction: a failed size
readback returned `verification_passed=false`, while the empty outer checks
and HTTP status reported success. The owning Impress worker now propagates
that existing failure through `VERIFICATION_FAILED` with observed partial
state. Geometry readback also preserves explicit path selectors instead of
returning `[-1]`. No API, semantic rewrite or evaluation gate was added.
Focused tests first reproduced the defects; the related suite then passed
259 tests plus Ruff/diff checks.

The new frozen affected/control pair passed 2/2 with final integrity `ok`:
Order 55 recovered reward 1.0 in 334.349 seconds (10 events plus audit), and
Order 48 retained reward 1.0 in 350.367 seconds (4 events plus audit). Order
55 selected all three real pictures and corrected one missing-readback
completion rejection; it did not need the new native error branch. Control
48 recovered one malformed completion-evidence request. No terminal protocol,
transport, environment or deadline failure occurred; neither case used Holo
or a soft restart. The result proves an isolated recovered task under this
version, not sole causality from the feedback repair or an aggregate rate.

Source stayed frozen, 20 manifest and 17 request artifact hashes matched,
all 11 Adapter forwards preserved model arguments, and every process exited.
See the [native verification report](archive/hybrid-impress-native-verification-20260909.md).
The immutable hybrid reference and promoted v337 pointer are unchanged.

## 2026-09-09 Explicit Adapter timeout budget

Repaired a deterministic cross-layer contract defect: a model-selected
300000 ms Multi-Apps payload previously kept a 120000 ms outer envelope.
Long explicit budgets now propagate; omitted budgets keep the 120000 ms
default. The Runner binds the existing episode deadline once, and the
executor/proxy cap operational budgets to remaining time while preserving
raw model arguments and native errors. Invalid nested values still use the
existing Adapter validation feedback. No API or evaluation gate was added.
Final focused checks passed 295 tests plus Ruff and diff checks.

One description-only probe reused Order 93's preserved post-timeout request.
Qwen returned HTTP 200 in 12.559 seconds with one valid call, but still omitted
the longer budget and selected a script with the same literal-variable quoting
error. No tool or whole-task replay executed. Source remained frozen during
the probe; a subsequent invalid-value handling correction was tested offline
and has a separately recorded source hash. Retain the proven contract fix,
record the negative usage result, and move to another preserved failure.
Details: [timeout report](archive/hybrid-adapter-timeout-budget-20260909.md).
No new task pass or aggregate improvement is claimed; the immutable hybrid
reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Native find terminator and GIF triage

Order 87's preserved GIF is 75 frames / 4.99 seconds, begins at the requested
source time, and matches the source first frame at SSIM 0.997. Its reference
has three frames / 0.3 seconds and different geometry; the scorer compares
only the first frame. Preserve the original failed result and do not alter
runtime semantics to match the reference. See the
[offline GIF diagnosis](archive/hybrid-gif-reference-diagnosis-20260909.md).

Order 93 exposed a real false rejection of native `find -exec ... ;`.
The shared Adapter check now accepts find's own terminator, preserves exact
argv/native errors, and leaves other shell-operator checks intact. Usage
descriptions clarify literal globs. Final related checks passed 93 tests;
Ruff and diff checks passed. The frozen pair completed with integrity ok:
control 146 passed (129.579 seconds), while affected 93 failed after 29 steps
and one restart (1165.891 seconds, stalled_no_progress). Its model-selected
semicolon command genuinely executed, with raw arguments preserved, but two
119-second command timeouts and repeated quoting/read mistakes remained.
It produced all twelve PDFs without satisfying the command-history scorer;
offline PDF text similarity is 0.99764, with all words preserved and three
wrapping differences. One zero-call response recovered; no terminal
protocol/transport/environment/deadline failure occurred. Retain the native
fix without claiming task recovery or scheduling an unchanged repeat. Source
remained frozen, all processes exited, and both run-owned guests were removed.
See the [find repair report](archive/hybrid-find-exec-terminator-20260909.md).
This does not change the immutable hybrid reference or promoted v337 pointer.

## 2026-09-09 Writer native CR literal replacement

Found and repaired a real mode inconsistency in existing text.find_replace:
single-match CR replacement created paragraphs, but all-match replacement
embedded CR literally and lost it on save. Only the CR-bearing bulk branch
now assigns unchanged text to native match ranges in reverse order. Plain
bulk replacement is unchanged; no new API, argument rewriting or gate was
added. Public parameter descriptions now state CR paragraph semantics and
the whole-document scope of replace_all=true. The focused suite passed 166
tests and Ruff/diff checks.

Two preserved native probes located the defect. The new frozen native v3
check completed seven calls in 462.822 seconds, exit 0 and source unchanged:
one single match plus two bulk matches produced three real empty paragraphs,
with every synthetic source character and the original document tail retained
in the saved DOCX. These operator checks do not count as Agent scores.

Two independent request-only snapshots remained negative: the description-only
request re-authored the paragraph incorrectly; rebuilding the real current tool
list exposed local replacement directly but still produced a whole-paragraph
call with the existing spacing conflict. No tool or retry executed. Withdraw
only the unproven cross-API guidance, retain the native fix, and move to another
preserved failure without an unchanged Order 77 replay. Details are in the
[local newline report](archive/hybrid-writer-local-newline-20260909.md).
Final retained-code verification passed 391 related tests plus Ruff/diff
checks. There is no new Agent pass or change to the immutable hybrid reference
or promoted v337 pointer; all experiment processes exited.

## 2026-09-09 Writer focused paragraph text

Repaired two fixed preview caps that made even a selected paragraph unreadable
in full: native inspection stopped at 500 characters and model hints at 180.
Existing explicit paragraph pages now expose selected live text and native
text_length, while overview previews and bounded context limits stay intact.
The related suite passed 384 tests; Ruff and diff checks passed. A fresh
affected/control pair completed 0/2 with final integrity ok: control 64
failed (176.147 seconds) by formatting an empty raw paragraph as the second
text paragraph; affected 77 failed (241.168 seconds) after correctly reading
all 577 characters and splitting seven sentences but normalizing two
apostrophes and dropping six source spaces. No terminal environment,
transport, protocol or deadline failure occurred. The capability works, but
there is no recovered task or no-control-regression claim.

A one-request character-fidelity wording probe returned another same-paragraph
read, not the registered exact replacement: HTTP 200, 11.501 seconds, 210
tokens, source unchanged and no tool execution. Withdraw that unproven wording,
retain the complete-read fix and synthetic Unicode round-trip coverage, and
do not repeat unchanged. The follow-up focused suite passed 50 tests; final
retained-code verification passed 386 related tests plus Ruff/diff checks.
Twenty manifest artifacts and thirteen Agent requests passed hash checks,
and all experiment processes exited. See the
[focused paragraph report](archive/hybrid-writer-full-paragraph-read-20260909.md).
The immutable 119/189 hybrid reference and promoted v337 pointer are unchanged.

## 2026-09-09 Calc native empty-chart error

The selected-header pair exposed an actual application error: a zero-series
chart was reported as successfully created, then saved alongside a later
valid chart. Its empty plot reproduces the evaluator's openpyxl IndexError.
The owning Adapter now removes a confirmed empty new chart and returns an
actionable INVALID_REQUEST without rewriting arguments or adding an evaluation
gate. The existing explicit replacement's partial state is reported honestly.
Focused tests passed 56; Ruff and diff checks passed. The newly sealed
affected-only Order 2 replay passed with reward 1.0 in 830.701 seconds,
eight event steps plus terminal audit, and final integrity ok. Two
completion-evidence schema errors recovered on retry; there was no terminal protocol,
transport, environment, or deadline failure. Its first chart selection was
already correct, so the pass does not prove that the new error path caused
recovery. The saved workbook loads and has one two-series, ten-category chart.
A model-free synthetic v1 check did not reproduce the empty chart with two
ranges. The changed-input v2 using three separate ranges verified the real
HTTP 422 error, empty-chart cleanup, preservation of the valid chart and
synthetic cells, and a saved XLSX that loads successfully. Both operator
attempts remain preserved and neither is an Agent score. Source remained
unchanged through all exits; ten manifest artifacts and eleven Agent requests
passed hash checks. No further replay was launched. See the
[empty-chart report](archive/hybrid-calc-empty-chart-error-20260909.md).

## 2026-09-09 Calc selected-range header meaning

The failed Order 15 reasoning confused a worksheet header above its selected
ranges with a header inside them. Only the chart action and parameter usage
descriptions now explain which row true consumes; defaults, validation, and
execution are unchanged. Focused tests passed 29 and Ruff passed. One
request-only snapshot returned a valid false-header chart call with correct
reasoning in 202.416 seconds, HTTP 200, and unchanged source. It reached the
4096-token cap with a complete call; no tool executed and no task pass is
claimed. The independent Order 15 affected / Order 2 control pair completed
0/2 with both tasks failed and final integrity ok. Order 15 omitted the flags
and still lost January; two reasoning-only errors recovered on the third
attempt. Order 2 saved an empty chart alongside a correct replacement under
a new name, causing an artifact-read error. There was no terminal protocol,
transport, environment, or deadline failure. Close the description-only
hypothesis without an unchanged replay. Details and
evidence are in the [selected-header report](archive/hybrid-calc-selected-header-usage-20260909.md).
The immutable 119/189 reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Native Calc chart series observation

The next Order 2 diagnosis separates native value-series identities from
source-range syntax. Existing `workbook.inspect` now reads Chart2 data series
and primary category labels; the ordinary direct/forwarded projection keeps
them with explicit preview omissions. Failed series reads retain the other
chart fields and report the error. No API, mutation, completion rule or gate
was added. Focused tests passed 166; Ruff and diff checks passed.
The native column-oriented operator check passed; row-oriented native
coverage remains inconclusive. The corrected request-only snapshot selected
`workbook.save`, but the first Agent pair still ended with Order 2 protocol
failure and Order 15 passed. After exposing the native observation immediately
after chart creation and clarifying non-active worksheet evidence, the
affected-only v2 replay passed Order 2: reward 1.0, eight event steps plus
terminal audit, 621.167 seconds, and final integrity `ok`. One initial
zero-call response recovered on retry; the terminal completion loop did not
recur. The continuation's 25 focused tests and Ruff passed.

The same-source Order 15 control then failed (reward 0, 814.760 seconds);
both charts exposed eight series and eleven categories, but the model saved,
inspected, and completed without correcting the selection. The success
feedback's unconditional "keep this chart" advice is now conditional on
matching the requested data; execution alone is explicitly not task success.
Only that guidance and three existing-test assertions changed; 25 focused
tests and Ruff passed. The new two-worker pair completed: Order 2 passed
(421.764 seconds), Order 15 failed (629.781 seconds), final integrity `ok`.
All 19 model calls were protocol-valid without retries; no transport,
environment, or Holo execution failure occurred. Order 15 read both source
tables and selected total-only values, but kept `column_headers=true` for
data-only ranges. Saved chart XML confirms eleven observations starting with
February in each chart. The new feedback did not recover the affected task;
retain truthful execution feedback and close this unchanged-replay path.
All attempts and limitations are in the
[chart-series report](archive/hybrid-calc-native-chart-series-20260909.md).
This is per-task evidence, not a new aggregate score; the immutable 119/189
reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Successful parameterless inspection availability

The chart-inspection replay completed with Order 15 passed (685.203 seconds)
and Order 2 `model_protocol_failure` (900.279 seconds), final integrity `ok`.
Offline reconstruction exposed obsolete selection and search filters hiding
a successful `workbook.inspect`, despite the existing repeated-read execution
contract. Those filters are removed; no API or gate is added. Focused tests
passed 179, including Calc/VLC selection and search, real-error preservation,
and unchanged duplicate-write/stall behavior. Ruff and diff checks passed.
The evidence is recorded in the
[read-availability report](archive/hybrid-parameterless-read-availability-20260909.md).
One request-only snapshot returned a valid `workbook.inspect` in 21.074 seconds
with 413 output tokens, no execution, and unchanged source. The newly sealed
Order 2/15 pair finished at 08:28:24Z with worker/supervisor integrity `ok`:
Order 15 retained reward 1.0 (653.659 seconds); Order 2 still failed protocol
(911.793 seconds). Its three zero-call, 4096-token responses had the inspection
tool and usage available, but repeatedly confused categories with numeric
series. All 18 request and 18 manifest artifact hashes checked successfully;
no terminal environment/transport error occurred. No new affected pass or
changed full-run numerator is claimed. Retain the correctness repair, close
this unchanged-replay hypothesis, and examine native chart series readback
as a separate candidate before further inference.

## 2026-09-09 Calc chart-versus-cell inspection guidance

The Order 2 protocol failure from the preceding v4 pair exposed ambiguous
inspection descriptions. The two existing tools now explicitly distinguish
cell reads from embedded chart settings and explain equivalent native range
coalescing. No parameter, observation, execution, or gate changed. Focused
tests passed 35; Ruff and diff checks passed.

One preserved proposal-12 snapshot returned a valid `workbook.inspect` call
in 23.925 seconds with 456 output tokens, rather than the preserved three
4096-token zero-call responses. No tool executed and source stayed unchanged.
This supports one newly sealed Order 2/15 affected/control replay, not a
recovered task claim. That replay has since completed with Order 15 passed
and Order 2 still failing protocol. See the [inspection-usage report](archive/hybrid-calc-chart-inspection-usage-20260909.md).
The 119/189 reference and promoted v337 pointer remain unchanged.

## 2026-09-09 Calc chart range/header clarification follow-up

Order 15 passed its corrected v4 replay with reward 1.0; the same-API
Order 2 control ended in `model_protocol_failure`. The range-syntax v2
attempt was rejected before worker launch due to a 0-versus-5-second
worker-delay mismatch. v3 reached
the evaluator with reward 0, but its model-facing range example copied task
coordinates; it is explicitly `invalid_leakage`, regardless of the automated
integrity result. Raw artifacts remain unchanged, with a separate host-only
disposition linked in the [Order 15 report](archive/hybrid-calc-order15-total-selection-retest-20260909.md).
Saved chart XML confirms that both charts lost their first observation after
the model selected `column_headers=true` for data-only ranges.

The minimal follow-up replaces the example with synthetic coordinates,
preserves the destination-sheet description in strict tools, and explains
field-name versus data rows using unrelated synthetic values. Focused tests
pass `22`; Ruff and `git diff --check` pass. The v4 pair completed at
07:09:57Z with unchanged source and final integrity `ok`. Order 15 took
647.437 seconds and 10 event steps plus terminal audit; saved XML confirms
one total series and all 12 observations in each chart. Control Order 2 took
1690.673 seconds, repeatedly read empty chart-sheet cells, misinterpreted
native range coalescing, and ultimately produced three zero-call,
4096-token responses at proposal 12. Inspection/save tools and chart
guidance were visible; no Adapter error was intercepted.

This is one isolated task recovery, not a stable affected/control condition
or an aggregate improvement claim. There were no terminal environment,
transport, or deadline failures and no Holo delegation. The 100-step,
1800-second, and 30-GiB limits remain unchanged. No API or gate was added;
the immutable 119/189 numerator and promoted v337 pointer are unchanged.
Do not rerun this pair unchanged; the remaining diagnosis is chart
read-back/completion comprehension.

## 2026-09-09 Calc total-formula direction repair

The affected Calc Order 3 repair now exposes both blank detail-row `Total`
cells and blank summary-row period/final-total cells from the live read. The
model-visible guidance distinguishes horizontal detail totals from vertical
summary-period totals and the horizontal summary final total, without
choosing arguments or adding a gate. Focused projection/formula checks pass
`34`; Ruff and `git diff --check` pass.

The replay sequence v6/v7/v9 was useful negative evidence: the model first
missed one of the two target sets, then used detail ranges for summary final
totals. Two v8 attempts were invalid configuration (stale seal and source
drift) and are retained without score. The fresh v10 replay passed `1/1`
with evaluator reward `1.0`; all expected detail and summary formulas were
written, saved, and read back. The isolated pass is non-promotable and does
not change the immutable `119/189` repair reference or the v337 baseline.
See [Calc total-formula direction repair](archive/hybrid-calc-total-formula-direction-repair-20260909.md).

## 2026-09-09 Calc contiguous-range error feedback

Preserved Calc Orders 3 and 15 both showed a reusable contract gap: the model
passed comma-separated disjoint areas to a single `range.read` or chart source
entry. The descriptions warned against this, but the Adapter accepted the
string and UNO could surface only an opaque internal error. The owning Calc
schema now rejects non-contiguous A1 ranges with a model-visible
`INVALID_REQUEST` explaining that separate calls are required; chart source
entries use the same check. Focused Calc/formula/protocol checks passed `89`,
Ruff and `git diff --check` passed. No live replay, gate, endpoint, or score
change was made; the repair reference remains `119/189` and Order 15's
total-only selection issue remains unresolved. See [Calc contiguous-range
error repair](archive/hybrid-calc-contiguous-range-error-repair-20260909.md).

The fresh affected/control replay completed `1/2`: stable Impress Order 63
passed; Calc Order 3 failed at the evaluator after the model left the period
cells of each `Total` row blank. Its first formula batch also produced
`Err:508`, which the Adapter incorrectly reported as successful. The minimal
follow-up now detects formula errors in `cells.set_formulas`, rolls back the
batch, and returns the existing `FORMULA_ERROR` feedback. Focused formula/Calc
checks pass `35`.

Two new source-sealed Order 3 replays reached the model-visible formula-error
path but ended as `model_protocol_failure`: one repeated a misread `F6:F20`
readback until three length-truncated requests, and the other wrote outside the
six-column used range (`F:J`) before stalling on `J6:J20`. Neither had
environment or transport failure; no gate or full-189 score was changed. The
immutable result directories are
`experiments/qwen35-holo31-hybrid-calc-formula-error-retest-20260909-v1-run1`
and `experiments/qwen35-holo31-hybrid-calc-formula-error-retest-20260909-v2-run1`.

## 2026-09-08 VS Code debug.variables.read post-fix retests v8–v10

[The combined diagnostic report](archive/hybrid-vscode-debug-variables-retest-20260908.md)
now records v8–v10 after the timeout/error-surface repair. v8 was stopped
mid-worker and is `invalid_configuration` at the supervisor level, with its
14-step Order 189 trace retained but no reportable score. v9 and v10 each ran
stable control Order 177 (passed) alongside affected Order 189, which was
stopped after 10 steps when the model repeatedly retried `debug.start` despite
the native `VSCODE_NOT_READY` response and recovery guidance; v10 also repeated
`extension.install`. The reduced wait (about 21–23 seconds) and structured
`last_observation` are present, so the remaining issue is a model/planning loop
around an unavailable debug session, not an intercepted error or a new gate.
These are interrupted, non-promotable diagnostics; the immutable `119/189`
repair reference and promoted v337 pointer are unchanged. No full-189 run or
new gate was started.

## 2026-09-08 VS Code section-name normalization follow-up

[The combined Order 189 diagnostic report](archive/hybrid-vscode-debug-variables-retest-20260908.md)
now includes v2–v7. The minimal v7 repair makes `ui.expand_section` compare
accessible names case-insensitively after collapsing surrounding or repeated
whitespace, with an ambiguity regression test and matching catalog/schema
usage text. Focused tests (21) and Ruff pass; the current source seal is
`07335929a0e5be91ed57d63cae55958d98235df79e13d00e46e35ff3d9bad0a6`.
The canonical v2 suite then passed all `1667` tests; changed-file Ruff also
passed.

The fresh-VM v7 Order 189 attempt was stopped after 24 steps/677.145 seconds
once the same GUI loop was established: the live accessibility tree exposed
no expandable section, Holo produced one recoverable non-integer-coordinate
schema error, and the model kept trying to dismiss the Python-extension
prompt without reaching `debug.start`. It is interrupted non-promotable
evidence with no evaluator score. The immutable `119/189` repair reference,
all prior attempts, and the promoted v337 pointer are unchanged; no gate was
added.

## 2026-09-08 Recovery Error Diagnostics

[The focused repair report](archive/hybrid-recovery-error-hint-repair-20260908.md)
records the minimal recovery-surface fix: concrete nested command diagnostics
such as `BadWindow` now survive the model-facing summary, and the failed
action's existing schema usage is repeated on the recovery turn. No new gate
or argument injection was added; the immutable hybrid reference and promoted
v337 baseline are unchanged. The same pass also fixed token-boundary matching
for task-identity redaction so short identifiers cannot corrupt ordinary error
words.

## 2026-09-08 VS Code debug.variables.read Retest

[The isolated retest report](archive/hybrid-vscode-debug-variables-retest-20260908.md)
shows that the minimal generic search-term repair works at the discovery
boundary: Qwen saw `adapter__debug_variables_read` in its tool surface and
selected it during Order 189. The task remained unsuccessful because the VM
was stuck in the Python-extension/Run-and-Debug GUI setup loop; its model-
selected `debug.variables.read` call returned the native invalid-window error.
The same trace exposed a reusable Adapter bug where timeout partial output was
`bytes` and caused a second JSON serialization failure. VS Code and VLC
command timeout handling now decode those bytes, with worker-level regression
coverage. The controlled v1 run is preserved as `interrupted` evidence (68
steps, one soft restart), not a score; the immutable `119/189` reference and
v337 pointer remain unchanged.

## 2026-09-08 VS Code Workspace-Open Retest

[The retest report](archive/hybrid-vscode-workspace-open-retest-20260908.md)
records two new conditions for affected Order 175 and stable Order 187 after
the minimal direct-path description repair. Both conditions hit the same
pre-episode `workspace.open` task-file read failure and are
`invalid_configuration`; no Agent episode or evaluator score is claimed. The
example file is readable in a direct host check afterward, so this is setup
evidence rather than a model/Adapter result. The 45 focused tests and Ruff
passed; source seal `b6936fd9…`. Historical numerators and v337 remain
unchanged.

## 2026-09-08 VLC Audio Export Retest

[The isolated retest](archive/hybrid-vlc-audio-export-retest-20260908.md)
replayed affected Order 163 with stable Order 170. Order 163 now performs only
the requested MP3 export and no longer opens playback for future-use wording,
but the unchanged evaluator audio-similarity reward remains `0.9897855`; Order
170 passed. Final integrity is `ok`, with zero protocol, transport, environment
or deadline failures. This confirms the semantic repair and leaves a fidelity
residual; it does not change the immutable `119/189` repair reference or v337.

## 2026-09-08 OS Exact Rename Retest

[The isolated retest](archive/hybrid-os-rename-retest-20260908.md) replayed
affected Order 138 with stable Order 148. Both passed (`2/2`) under source
seal `c56627388b2a1192caa9427fa66df22b6648fc1850b7a1ff4110f37e34022155`.
Order 138 selected the concrete Desktop source and destination on its first
call, and the Adapter verified the rename; Order 148 retained its normal copy
control. Final integrity is `ok`, with zero protocol, transport, environment,
deadline, leakage, rewrite, injection, mismatch, or evaluator-boundary
findings. This isolated pass does not change the immutable `119/189` repair
reference or the promoted v337 pointer. No source or gate change was made.

## 2026-09-08 OS Recursive JPG Copy Retest

[The isolated retest](archive/hybrid-os-file-copy-retest-20260908.md) replayed
affected Order 142 with stable Order 148. Both passed (`2/2`) under source seal
`c56627388b2a1192caa9427fa66df22b6648fc1850b7a1ff4110f37e34022155`, with final
integrity `ok` and zero protocol, transport, environment or deadline failures.
Order 142 recovered from an initial `~/photos` path error, used the exact
observed `/home/user/Desktop/photos` path, found all four JPG files and copied
each to `cpjpg`; the evaluator and structural read-back passed. This isolated
pass is not added to the immutable 119/189 numerator or v337 pointer.

## 2026-09-08 OS Desktop-Setting Schema Recovery Retest

[The isolated retest](archive/hybrid-os-desktop-setting-retest-20260908.md)
replayed affected Order 141 (persistent GNOME Terminal size) with Order 148 as a
stable copy control. The repeated-read fix is effective: identical
`gsettings list-schemas`/`list-keys` calls execute and native errors reach Qwen.
The additional generic GSettings, shell-syntax, truncated-output and catalog
usage guidance passed 80 focused tests and Ruff. Order 141 still fails because
Qwen chooses the wrong fixed schema and repeats catalog/read calls instead of
using `list-relocatable-schemas` and a concrete profile path. Order 148 passed in
the first two attempts; v3/v4 were stopped once the same no-progress loop was
confirmed. No transport or environment failure occurred, and no isolated pass
changes the immutable 119/189 numerator or v337 pointer.

## 2026-09-08 Impress Completion Evidence Protocol Retest

[The isolated Impress retest](archive/hybrid-impress-completion-evidence-retest-20260908.md)
replayed affected Order 34 and stable Impress control 48 after the native
structured `propose_done.evidence` repair. Order 34 passed in 5 steps/158.772
seconds and Order 48 passed in 7 steps/402.342 seconds. Both used the
`generic_api_only` path; there were no protocol, transport, environment,
deadline, leakage, rewrite, injection or evaluator-boundary findings, and
final integrity is `ok`. Together with the Writer 67/73/84 replay immediately
below, the same protocol repair has now passed affected/control checks across
both Writer and Impress. These are isolated results only: the119/189 repair
reference and v337 pointer remain unchanged.

## 2026-09-08 Completion Evidence Protocol Retest

[The isolated retest](archive/hybrid-completion-evidence-retest-20260908.md)
replayed affected Writer Orders 67 and 84 with stable control 73 after the
native structured `propose_done.evidence` repair. Two earlier launches were
configuration-only failures caused by short frozen model roots; they started
no task and remain separate immutable `invalid_configuration` evidence. The
v3 condition froze the actual Qwen `192.168.0.138:8001` and Holo
`192.168.0.224:8002` snapshot roots and completed all three tasks:67 passed in
4 steps/161.635 seconds,73 passed in4 steps/176.017 seconds, and84 passed in2
steps/96.247 seconds. All paths were `generic_api_only`; no protocol,
transport, environment, deadline, leakage, rewrite, injection or
evaluator-boundary finding occurred, and final integrity is `ok`. This is
isolated evidence only: the119/189 repair reference and v337 pointer are
unchanged.

## 2026-09-08 Completion Evidence Protocol Repair

[The completion evidence repair](archive/hybrid-completion-evidence-contract-20260908.md)
addresses preserved protocol failures in Orders34,67 and84 (and the same
shape in143). Their successful Adapter actions were followed by native JSON
evidence objects, but `propose_done` only allowed string items and rejected the
request before the existing completion ledger could run. The shared schema now
accepts concise strings or compact structured evidence objects; the object is
informational and does not weaken executed-action, save/read-back or terminal
audit requirements. Serialized JSON strings remain invalid. Focused checks pass
`87`, Ruff and diff checks pass, and offline replay of all four preserved object
claims returns zero schema errors. The affected/control Writer and Impress
retests are recorded immediately above and both completed without protocol,
transport or environment failures. No aggregate-score change is claimed; the
119/189 repair reference and v337 pointer remain unchanged.

## 2026-09-08 OS Transport-Bound Failure Retest Result

The v2 usage-repair retest now recovers all three selected tasks:145,146 and
148 pass.145 executes explicit old-file compression and creates a ZIP for the
newer files;146 executes a model-authored `bash -c` pipeline and displays54;
148 remains a stable copy pass. All terminal audits complete with zero
protocol, transport, environment or deadline failures. Results hash
`fd90302b383076bb46eb7d431acecf4dd88e2f8e2cde5fad6094c29e7b452436`.
The isolated result is not added to the immutable119/189 numerator.
145 retains the requested new files but creates an extra unrequested ZIP;
the scorer passes it while the final explanation/audit misses that distinction.
No gunzip search occurs in this successful trace, so its pass does not prove
the retrieval fix caused recovery.146 directly uses the documented shell
representation. Both conditions' final integrity checks are ok; the v2 run
completed at08:53:55Z and all workers have exited.

[The completed condition](archive/hybrid-os-transport-retest-20260908.md)
shows148 passing while145/146 remain model protocol failures, not environment
or endpoint failures.145 executed discovery and three gzip calls before its
recovery model emitted no structured call;146 received the exact shell-token
error but emitted no recovery call across three attempts. The existing public
`command.run` is now recalled for generic `gunzip/decompress` queries, and its
and `terminal.show_output` descriptions explain model-authored `bash -c`
scripts for pipelines.49 focused tests and Ruff pass. Source seal
`de63cf7051a3dbb00e606620b87f12579cf07cebe7430aba4590380d7b0845bd` is new;
the completed run remains immutable and the full-189 numerator is unchanged.

## 2026-09-08 OS Transport-Bound Failure Retest

[The registered small condition](archive/hybrid-os-transport-retest-20260908.md)
selects145/146 from preserved Sep6 initial/recovery request timeouts, plus
stable148 copy control. One attempt each uses current generic source0811c3fd
and the split Qwen/Holo endpoints with unchanged100-step/1800-second/30-GiB
limits. No new runtime edit, evaluation gate, full189 run or promotion is
registered. Inspect semantic outcomes as well as transport recovery; the
completed pair before this condition remains immutable evidence.

## 2026-09-08 File-Copy Layout Usage Retest

[The owning copy description](archive/hybrid-file-copy-layout-20260908.md)
now distinguishes basename copying from preserving a source hierarchy. The
implementation and every model-selected path remain unchanged.143's older
initial surface omitted file discovery; current retrieval already retains it.
Two description tests fail before repair;132 related checks and Ruff pass.
The new143/148 affected/control pair finishes at07:33:42Z:148 passed in3
events/168.564 seconds;143 ends model_protocol_failure after27 events and
1477.673 seconds. It now discovers the files first, but still confuses output
directories and filenames, selects a wrong output base, and enters repeated
conflicts. At step28 three HTTP200 responses consume4096 tokens each with
zero calls. Source5e2beb9b stays unchanged and all final integrity checks are
ok. No transport/environment/deadline failure or recovered143 pass is claimed.

After all runners exit, two synthetic tests reproduce a real native defect:
copy2 descends into a directory-valued output while the Adapter reports its
parent path. The small owning copy fix now returns DESTINATION_CONFLICT
before writing any member for that conflict. Existing file-copy semantics
remain unchanged; all135 related tests and Ruff pass. Source0811c3fd is a
post-run fix, not part of the completed pair; no new Agent episode is run
with it. All runners have exited. No Agent gate, full189 launch, retry-budget
change, promotion or integrated numerator change is added.

## 2026-09-08 Negative Active-Document Prompt Snapshot

[The request-only probe](archive/hybrid-active-document-guidance-20260908.md)
finishes at06:53:20Z.117 still mistakes the supporting document for the source
and chooses File-menu export,10.073 seconds/181 output tokens.148 retains
its copy call,18.103 seconds/177 tokens. Both calls are schema-valid but do
not execute. Source41036e29 remains unchanged. Do not apply the ineffective
prompt, repeat117 unchanged or claim a recovered pass. The independently
verified archive-schema fix is retained.

## 2026-09-08 Archive Required-Field Generation Repair

[The archive schema repair](archive/hybrid-archive-branch-schema-20260908.md)
reproduces a serving grammar defect: partial oneOf branches allow only mode
and reject complete create/extract arguments. The field descriptions and
error feedback were already present. Only the owning OS manifest is changed
to make the two branches self-contained; no API, runtime validator or gate
is added. Four new cases fail before repair; all159 related tests and Ruff
pass afterward.

The frozen affected117/control148 request-only pair completes at06:38:38Z.
117 now emits a complete schema-valid archive call in24.062 seconds/295
output tokens;148 retains its copy call in8.428 seconds/152 tokens. Neither
call executes. Source41036e29 remains unchanged. The prior wrong-document
PDF remains wrong, so this is not a recovered117 pass. Six other branch APIs
accept complete synthetic calls; an extra native CPU cross-check is
inconclusive after two SSH disconnects. All Agent runners and snapshot drivers have exited,
and no new full episode, full189 or baseline promotion is registered.

## 2026-09-08 Local File Discovery And Split Serving

[The local-file retrieval repair](archive/hybrid-local-file-search-terms-20260908.md)
adds ordinary search/opening terms to two existing OS catalog entries. Six
synthetic cases failed before repair; all258 related tests plus a separate60
filesystem checks pass afterward. No API, argument, prompt or gate changes.
The preserved-state dgx2 snapshot completed in15.850 seconds/266 output tokens
with one schema-valid filesystem.find call. No application action executed;
source1a878f67 stayed unchanged and this is not an Agent pass.

The user resumed with Qwen on dgx2:8001 and Holo on spark224:8002. Their
reported12-way HTTP200 tests are not repeated or treated as Agent results.
A new split-local-files-retest-20260908-v1 condition registers117/147/148,
one attempt each, three workers and unchanged100-step/1800-second/30-GiB
limits.117 is an explicit changed-source extension after a positive snapshot;
147 previously failed on screenshots/transport;148 is a stable control.
Both serving and source differ, so this is not a ranking-only ablation.
No full189 run or baseline promotion is registered.

The three-task run completed at06:22:10Z:147 passed5 steps/173.638 seconds,
148 passed3 steps/136.677 seconds;117 ended model_protocol_failure after13
events/478.113 seconds. All final integrity checks are ok; source1a878f67
stayed unchanged. No terminal transport/environment/deadline failure occurred.
147 is a new individual recovery.117's search improves, but it still exports
the supporting document and then hits an independently reproduced
[archive branch grammar defect](archive/hybrid-archive-branch-schema-20260908.md).
The serving grammar accepts only mode and rejects complete create/extract
calls. An owning-schema representation repair is next; no new gate or full run.

## 2026-09-08 Reproduced Native Tool Generation Loop

[The token-level diagnosis](archive/hybrid-filesystem-generation-overhead-20260908.md)
restored117's independently captured tool ordering and reproduced4096 output
tokens in204.023 seconds:37 complete native calls were generated, but the
serving parallel-call filter returned only the first. Canonically sorted old
request artifacts change prompt tokens; the archive writer now preserves
original dictionary order without changing its canonical hash or old evidence.
Its focused regression and247 related tests pass.

One parameter-only snapshot retained the full native closing marker and
stopped at the first complete call:273 tokens,14.886 seconds, identical raw
token prefix and first-call arguments. Empty-argument control73 remained
valid at133 tokens/7.205 seconds. No desktop action executed and neither is
a task pass. Opt-in protocol.tool_call_stop_sequence now forwards this setting
through the existing request path, with defaults, Holo and gates unchanged.
All170 related tests and Ruff pass. A new affected117/control148 pair is
registered under complete-tool-stop-retest-20260908-v1; no full189 authorization
or baseline promotion is implied.

The pair completed1/2: affected117 failed after42 steps/1275.615 seconds
(stalled_no_progress); control148 passed in3 steps/122.220 seconds. Both final
integrity checks are ok and source73f99b69 stayed unchanged. All42 successful
affected proposals end normally with at most675 output tokens; one separate
reasoning-only4096-token attempt recovered on the existing retry. All14 Holo
responses are schema-valid. The remaining failure is semantic discovery and
document activation, not a recovered task. The next bounded change repairs
missing OS file-search/opening catalog keywords; no unchanged full episode.

## 2026-09-08 Durable Context And Holo Self-Error Feedback

[The context identity repair](archive/hybrid-durable-observation-identity-20260908.md)
stops forwarded file reads/searches from replacing one another under the same
adapter.call history key. Actual117 request23/33 offline replays now retain
both source observations and search within the existing budgets, with raw
events and model calls unchanged. There is no new API, gate or memory framework.

[The Holo feedback repair](archive/hybrid-holo-self-error-feedback-20260908.md)
returns a prior bounded schema error to Holo only when the parent next selects
the identical grounding input. New input and success clear it; no automatic
retry, coordinate rewriting or block-rule change occurs. All 316 related tests
and Ruff pass. One changed-feedback snapshot returns a valid on-target click
in 6.450 seconds/127 tokens, compared with the preserved invalid 1024-token
responses. Nothing executes on a desktop; this is not an Agent pass. Source
85076ab5 stays unchanged through the probe. All processes have exited, no
unchanged repeat is scheduled, and full189 authorization is still pending.

## 2026-09-08 Writer Offline PDF Dependency And Source Usage

[The PDF repair](archive/hybrid-writer-offline-pdf-dependency-20260908.md)
bundles pinned PyMuPDF for private, offline Writer installation without apt
mirrors or new health gates. After one stopped host-caller error, three
native PDF exports succeeded in the second 372.858-second session. Source
51b9fd19 stayed unchanged. The final fixture failed its positive-patch
expectation: this source needed zero patches. Earlier assertions verified
private dependency provenance, unchanged DOCX bytes, and equal normalized/raw
text, page geometry and pixels. Positive-patch coverage and the later short
text assertion remain unverified; both diagnostic attempts are preserved.

The subsequent owning read/export descriptions explicitly distinguish saved
file reading from active Writer document selection. All 351 related tests
and Ruff pass. The affected-only 117 Agent replay exited at 03:38:54Z with
agent_deadline_exhausted: 30 recorded events, 31 Qwen requests, 1928.006 seconds
including lifecycle overhead. It found/read files but repeatedly exported the
wrong active document through GUI, never exercising the PDF API repair.
Five valid Qwen file-search calls exhausted 4096 tokens each; Holo had three
schema failures among 15 requests. Both final integrity checks are ok and
source 56abcc80 is unchanged. There is no new pass, unchanged third 117 attempt,
unstable 113 repeat or authorization to expand to full189.

## 2026-09-08 Small Text-Batch Recovery Budget

[The batch-budget repair](archive/hybrid-small-batch-budget-repair-20260908.md)
charges the actual fitted source size instead of reserving 90% even for a
short read. It changes only shared observation allocation, not gates, model
arguments or context limits. Both new regressions fail before the fix; all
205 related tests and Ruff pass afterward. Preserved Order117 request15
replay restores all five actual tool routes in each of three search results:
4768 -> 8243 characters within the original 16000 limit. The 3234-character
batch/history object, events and proposals remain exactly unchanged. Source
806b404c is unchanged during this offline replay; no model, VM or evaluator
runs, and no new task pass is claimed. The preceding 113/117 pair remains 0/2.
Next review its independent dependency and active-document failures before
registering any new affected attempt. No full-189 launch or promotion.

## 2026-09-08 Writer Supporting-File Reading

[The Writer reader repair](archive/hybrid-writer-file-reading-repair-20260908.md)
adds one owning-Adapter document.read_file for explicit saved DOCX/ODT body
and table text, with model-selected character pages. It does not restore a
retired Multi-Apps macro or add a completion gate. 338 focused tests, Ruff,
and a 317.565-second fresh-guest synthetic API diagnostic passed. Native
reads preserve source bytes and every open Writer document's unsaved state.
The frozen pair completed at 02:33:54Z with source c73f383d unchanged and
final integrity ok. 113 failed at 50 steps/2031.057 seconds, with underlying
Agent time exhaustion; 117 failed at 60 steps/1402.292 seconds, stalled.
Each used one restart. The reader worked on both supporting and essay files,
but missing PDF dependencies and wrong-document GUI loops blocked 117;
clipboard backend absence and invalid conversion choices also affected 113.
No terminal protocol/transport/environment failures or new task pass. Both
processes exited; no unchanged pair retry is registered. The subsequent
context-budget fix above is offline-only and not part of this pair's source.
The active repair reference and promoted baseline pointer remain unchanged.

## 2026-09-08 Audio Volume Usage Repair

[The audio usage repair](archive/hybrid-audio-volume-usage-repair-20260908.md)
clarifies normal 100% volume versus optional over-amplification. Preserved
136 explicitly misread the accepted 150% bound as the normal maximum; the
Adapter executed its arguments correctly. Only the owning field description
changes; no clamp, default, API, gate or completion rule is added. The new
regression failed before repair; all 38 related tests and Ruff pass. A frozen
133-control/136-affected pair completed at 01:04:19Z with the original models
and 100-step/1800-second limits. Both passed in two recorded steps each:
133 took 109.673 seconds, 136 took 101.560 seconds. Qwen selected percent=100
itself and native read-back confirmed both channels at 100%/0.00 dB. No
repeated writes, completion rejections, restarts or terminal protocol,
transport, environment or deadline failures occurred. Both processes exited
0, final integrity is ok, and source dc6e3c59 remained unchanged (475 files).
No runner remains. This recovers one Aug31 non-pass/Sep6 failure, not an
integrated score. No unchanged pair replay or new full-189 is registered;
the pending full-run authorization and greater-than-80% goal remain open.

## 2026-09-08 Terminal Timeout Request Diagnostics

[Two preserved initial requests](archive/hybrid-transport-generation-diagnostic-20260908.md)
that each timed out three times in the Sep6 integrated run returned normally:
179 took 12.468 seconds/241 output tokens; 147 took 13.467 seconds/243 tokens.
Both emitted one schema-valid call with normal token termination. The only
request additions were response-debug metadata. No tool, VM or evaluator ran,
source 34ce5c90 stayed unchanged, and both processes exited 0. This does not
reproduce or explain the historical timeout and is not recovered task evidence.
No production retry, timeout, decoding setting or gate changed. Stop unchanged
probes and continue concrete failure diagnosis. A new full-189 authorization
request remains unanswered; no new aggregate score or promotion is claimed.

## 2026-09-08 Impress Edit-Stage Inspection Availability

[The text-target pair](archive/hybrid-impress-text-target-observation-repair-20260907.md)
completed by 00:04:17Z with source 84a74f25 unchanged and final integrity ok:
57 exhausted the Agent deadline (28 recorded steps, 1856.663 seconds including
setup); 61 passed (25 recorded steps, 26 model requests, 754.498 seconds).
61 is slower than its earlier 16-step/484.712-second pass. Five recovered
reasoning-only responses remain in 57, and one recovered schema error remains
in 61. There is no new affected pass or integrated success-rate improvement.

[The independent budget snapshot](archive/hybrid-impress-thinking-budget-20260907.md)
returned one valid call in 18.638 seconds/324 output tokens, but chose the
wrong page/alignment relationship. No tool executed and source stayed frozen.
This is a negative semantic result, not proof of a forced thinking cutoff.
The forwarding tests passed (12 cases). Do not run a scored 57 budget retry;
end this 57 attempt series without changing model defaults or denominators.

[The edit-stage repair](archive/hybrid-impress-staged-inspection-repair-20260908.md)
addresses a separate omission: pending Impress mutations hid the inspection
tool even while Qwen asked to read. The actual 61 requests 10/11 reproduce
that surface exactly. Retaining the already-selected inspection in the owning
stage/filter adds only that tool; existing tools, schemas, events and missing
requirements remain unchanged. Two new regressions failed before the fix;
all 188 related tests and Ruff pass. A new 33-control/61-affected pair is
registered with original models and limits, no budget override or new gate.
It completed at 00:35:01Z, both processes exit 0, source 34ce5c90 unchanged
(475 files), final integrity ok. Both passed with normal terminal audit:
33 took 20 steps/707.845 seconds; 61 took 20 steps/606.933 seconds.
61's five unique geometry/text mutations each executed once, removing the
parent's six repeated successful writes and reducing its time by about 19.6%.
Inspection stayed available in actual requests, but two early claims and two
Holo save operations remain. 33 had a same-VM restart and one recovered
reasoning-only protocol error, and was slower than its earlier passing control.
There are no terminal protocol/transport/environment/deadline failures.

This verifies one affected behavior improvement, not an integrated success-rate
increase: both tasks already had passing evidence and older 61 was faster still.
No runner remains and no unchanged 33/61 or 57 rerun is registered. Next focus
on shared request-generation/timeout costs: offline classification confirms
23 Sep6 transport failures with 69 APITimeoutError entries, including eight
episodes with no completed action. Network, queueing and generation causes
remain to be separated; do not infer them from the terminal label alone.
The 119/189 repair reference, historical numerator and promoted pointer remain
unchanged. At least 152 passes in one frozen full-189 condition are still needed
to establish the user's greater-than-80-percent objective.

## 2026-09-07 Impress Observed Text Targets And Geometric Order

[The text-target observation repair](archive/hybrid-impress-text-target-observation-repair-20260907.md)
addresses 57's preserved cross-page path mixing and native-order object choice.
Text observations now expose complete observed page/selector pairs, like pictures.
The model-facing list uses the existing geometric sorter, moved into the owning
geometry module to avoid a circular import; raw objects and identifiers remain
unchanged. Unknown geometry keeps native order, explicitly labeled. No gate,
mutation rule, task-specific target or model setting changed. All 216 related
tests and Ruff pass. The full replay retains six text targets; its 9000-character
projection truthfully reports one omitted textbox instead of fabricating coverage.
One non-executing 32.973-second snapshot probe returned a valid additional read,
so it is inconclusive, not a pass. One affected 57/passing-control 61 pair
started at 23:20:31Z under source 84a74f25 (475 files); the completed negative
affected result and slower passing control are recorded in the Sep8 entry above.
No integrated numerator or promoted baseline change is claimed.

## 2026-09-07 Impress Slide And Visual Selector Guidance

[The selector-guidance repair](archive/hybrid-impress-selector-guidance-repair-20260907.md)
clarifies human numbering versus zero-based slide arguments and native stacking
indices versus visual reading order. The model still chooses every observed
target; no sorting, API, automatic arguments, gate or completion change was added.
An overlong draft initially dropped one real text shape under the existing
9000-character budget. Shortened final wording preserves all six, including
paragraphs and alignment, in 8960 characters; no live run used the long draft.
All 194 related tests and Ruff pass. One affected 57/control 33 pair started
at 22:39:37Z under source e2204cd9 (475 files), preserving all model and episode
limits. It was engineering-interrupted at 22:45:18Z: 33 stopped after 14 steps
and 332.459 seconds; 57 never started. The current missing-scope message was
used to restrict tools but never sent to the model, which repeated partial
reads. Both processes exited before further edits; this is not a scored pass.

[The current-feedback repair](archive/hybrid-current-completion-feedback-repair-20260907.md)
adds the already-computed latest missing requirements to those recovery tools'
descriptions, without changing tools, arguments, checks or completion rules.
Both new regressions reproduce the old defect; all 247 related tests and Ruff
pass. Preserved request 10 differs only by the new requirements suffix and now
exposes the existing whole-scope read instruction. The fresh 33/57 pair completed
at 23:05:38Z under unchanged source 382f7dd1 (475 files), both processes exit 0
and final integrity ok. 33 passed in 10 steps/317.300 seconds but repeated one
mutation and made two premature claims. Its full-scope reads did not exercise
the exact partial-scope feedback; that remains independently replay-tested.
57 failed in 13 steps/627.202 seconds after choosing the wrong textboxes on two
pages. One invalid cross-page path was corrected after native SHAPE_NOT_FOUND;
one connection error and one 4096-token length response recovered, with zero
terminal protocol/transport/environment/deadline failures. No runner remains.

Retain current-feedback delivery, but do not count a new recovered task or an
80% score. Stop unchanged wording retries. Next consider an observed page/path
tool_target for text (already present for pictures) and the existing geometric
ordering helper, with no task-specific macro or new gate. No additional change
to that observation contract has yet been implemented. Neither an integrated
numerator nor the promoted pointer changes.

## 2026-09-07 Persistence Recovery Inspection Availability

[The recovery-surface repair](archive/hybrid-persist-inspection-availability-repair-20260907.md)
addresses61's preserved post-save loop: the framework advertised only save/fail
while Qwen asked in reasoning to inspect. Persistence recovery now retains
existing owning inspections and discovered owning Multi-Apps reads; completion
requirements and model arguments are unchanged. Three regressions reproduced
the defect; all250 related tests and Ruff pass. Offline replay restores the
inspection tool without clearing missing read-back or modifying raw evidence.
The new33/61 pair completed at22:22:09Z under unchanged source2b6ae67a (475 files):
33 passed in6 steps/179.030 seconds;61 passed in16 steps/484.712 seconds.61 saved
at14, retained inspect in request15, inspected both pages, and completed the
normal terminal audit. It still made two premature claims, three Holo GUI calls
and a repeated picture move; the report preserves those limitations and all
prior interruptions. Terminal protocol/transport/environment/deadline failures
are zero. Both processes exited0, final integrity is ok, and no worker remains.

This recovers an Aug31 failed task without changing a frozen numerator or the
promoted pointer.80% remains unverified; next address57's preserved wrong-object
selection without new gates or task-specific targets, not an unchanged61 rerun.

## 2026-09-07 Impress Partial Observation State

[The grouped-text trio](archive/hybrid-impress-grouped-text-observation-repair-20260907.md)
ended with33 passed,57 failed and61 engineering-interrupted/unscored.57 still
selected the wrong visual textbox on two pages despite successful native
alignment mutation.61 corrected omitted underlines but the initial-state
accessor ignored every page outside the first partial inspection, creating
an impossible completion rejection. Both processes exited before source edits.

[The partial-state repair](archive/hybrid-impress-partial-observation-state-repair-20260907.md)
accumulates each page's first observation without replacing its original
formatting/geometry or adding a gate. Two focused regressions reproduced the
defect. Offline replay still rejects unfinished work at3/7 and clears the
erroneous rejection after saved read-back at16. The first pair (source88a273b0)
was then interrupted on33: a matching but partial background read was reported
as a color mismatch, provoking repeated mutations.61 had not started.

The follow-up changes only that existing error's explanation, retaining all
acceptance criteria. All205 related tests and Ruff pass; offline33 replay now
requests a complete read instead of an unnecessary background mutation. A new
33/61 pair ran under sourceb6e3fd6a (475 files), unchanged100-step/1800-second
limits and original models.33 passed in6 steps/182.626 seconds after a full
read; the new partial-scope message was not exercised in that successful trace.
61 was interrupted at27 steps/697.812 seconds after a separate save-only tool
surface defect, not a scored failure or pass. Both processes exited before
the next repair. No integrated numerator or promoted pointer changed.

## 2026-09-07 Writer Native Font-Family Observation

[The font-observation repair](archive/hybrid-writer-font-observation-repair-20260907.md)
adds truthful native font-family read-back over the existing body/table-cell
scope, including explicit mixed/unknown counts. Mutation input echoes remain
separate from observation. All322 related tests and Ruff pass, including12
new regressions. No mutation semantics, completion rule or gate was added.

The affected68/control83 pair completed at20:46:58Z under unchanged source
43c0e481 (474 files):68 passed in4 steps/132.288 seconds and83 passed in
3 steps/116.198 seconds. All terminal protocol/transport/environment/deadline
counts are zero;68 recovered one premature completion rejection. Native
read-back preserved one mixed text object, which Qwen overgeneralized in its
claim. Offline final-DOCX inspection confirmed all42 nonempty runs, including
table text, used the requested font; old paragraph-marker fonts remain and
are consistent with the mixed observation. The report records this limit.

Worker/supervisor exited0 and final integrity was ok. This recovers a Sep6
regression and preserves a newly passing Aug31 failure, not an integrated80%
result or an increment to a frozen numerator. No runner or new full-189 run
remains active. Next verify multi-slide failure candidates57/61 rather than
adding a new completion gate or rerunning the passing font task unchanged.

## 2026-09-07 Writer Case-Transform Recovery Retest

[The unchanged-source recovery pair](archive/hybrid-writer-case-recovery-retest-20260907.md)
completed at20:35:33Z: affected83 passed in4 steps/129.740 seconds and
control73 in4 steps/176.600 seconds.83 selected one case transformation,
corrected a premature claim with actual text read-back, and completed the
ordinary terminal audit. No new runtime rule or gate was added. There were
no protocol/transport/environment/deadline failures; one completion claim
was rejected and recovered. Both processes exited0 and final integrity was
ok under unchanged source6d957a0c. This is an isolated recovered Aug31
non-pass, not a changed full-run numerator or an80% result. Next investigate
the separately observed missing native font-family evidence on68.

## 2026-09-07 Writer Native Strikethrough Observation

[The strikeout-observation repair](archive/hybrid-writer-strikethrough-observation-repair-20260907.md)
adds truthful whole-paragraph native strikeout state to existing inspection
and mutation feedback. Request echoes remain separate from observation;
mixed and unknown values do not become false uniform-success evidence.
All203 related tests and Ruff pass, including13 new counterfactual and
direct/forwarded projection checks. No mutation or completion/gate code changed.

The control73/affected75 pair completed at20:22:42Z with original Qwen/Holo
settings,100 steps,1800 seconds,one worker and30-GiB stop.73 passed in4 steps/
176.293 seconds;75 passed in7 steps/269.442 seconds. Native read-back confirmed
strikeout only on the model-selected final paragraph.75 recovered one missing
query-parameter error and made two repeated successful searches; terminal
protocol/transport/environment/deadline counts are zero, not all incidents.

Worker/supervisor exited0, final integrity was ok and source stayed6d957a0c
(473 files). No process remains active. This is an isolated recovered Aug31
non-pass, not an integrated numerator change or80% claim. Next verify existing
recovery on another preserved failure before adding speculative code; the
report records83's read-only triage. No extra operator or full-189 launched.

## 2026-09-07 Writer Native Footer Observation

[The footer-observation repair](archive/hybrid-writer-footer-observation-repair-20260907.md)
adds actual native page-number fields, alignment and independent footer
variants to existing Writer inspection and its model projection. Five initial
regressions reproduced the missing capability; all190 related tests and Ruff
pass. No API, mutation, completion policy or evaluation gate changed.

One native three-call session completed at19:57:51Z and exited0 under unchanged
sourceb747f23a (472 files). The synthetic center-aligned field read back
correctly and the bounded observed body remained unchanged. Its non-Agent
scorer reward1 does not prove the requested left alignment; preserve that
limitation and check the actual Agent arguments/native result in the next pair.
The affected67/control73 pair completed at20:06:54Z with original models and
100-step/1800-second limits.67 passed in4 steps/138.537 seconds;73 passed in
4 steps/177.800 seconds.67's raw model argument is bottom_left and the native
read-back confirms left alignment before its accepted claim and terminal
audit. Both processes exited0, final integrity was ok, source stayed unchanged
and terminal protocol/transport/environment/deadline counts are zero.

This is one recovered Aug31 non-pass, not an increment to a frozen numerator
or verified80% aggregate. No runner remains active. The report records75's
missing native strikeout observation as the next read-only candidate, without
registering a new episode or treating requested formatting as observed state.

## 2026-09-07 Writer Native Preference Evidence

[The preference-evidence repair](archive/hybrid-writer-preference-evidence-repair-20260907.md)
corrects a preserved84 failure: a successfully persisted default-font setting
was followed by an unrelated document read-back requirement and three model
request timeouts. The existing default_font verifier now reads native
configuration instead of echoing caller input. Settings-only Office work may
use scoped native preference evidence without saving an unrelated document;
document editing and mixed work keep their normal requirements and terminal
audit. No new API, evaluation gate or model argument injection was added.

All235 related tests and Ruff passed, including the real service/executor/model
projection boundary. The control73/affected84 pair completed at19:42:13Z under
unchanged source0136cc7e (471 files), unchanged models,100 steps/1800 seconds
and30-GiB stop.73 passed in4 steps/171.846 seconds;84 passed in2 steps/91.229
seconds with no irrelevant document read-back. Both used the original evaluator
and ordinary terminal audit. Terminal protocol/transport/environment/deadline
counts are all zero, final integrity is ok, and worker/supervisor exited0.

This recovers an Aug31 non-pass and Sep6 transport failure in an isolated pair,
not an integrated80% result. Do not add it to a historical numerator. No runner
remains active. Move to another preserved failure; the report records a
read-only67 footer-observation gap without authorizing an unchanged retry or
weakening document-content evidence requirements.

## 2026-09-07 Preserve Pre-Claim Correction Tools

[The Impress feedback investigation](archive/hybrid-impress-paragraph-feedback-repair-20260907.md)
found a shared recovery defect: before Qwen ever claimed completion, a
successful mutation caused the framework to remove editing/search tools and
leave only save/fail. The recovery wrapper now waits for an explicit rejected
completion claim before narrowing the surface. A later content mutation
reopens ordinary work; existing save/read-back and terminal checks remain.
The owning formatting description also clarifies whole-shape versus explicit
line/literal scope without changing defaults or mutation semantics.

Five new tests reproduced the old defects; all282 related tests and Ruff
now pass. Offline replay of the preserved38 states restores corrective
editing/search while completion remains false for missing save. Source:
aafe42b382bcbc4fc9822888e485c77f3c0107734d5d24eafd374c6ca2ee4bfb.
No new gate, API macro, automatic target, or argument rewrite was added.

Two separately registered non-executing snapshots did not recover task
quality. Step4 produced a premature propose_done in69.817 seconds; step2,
with only the new description, still omitted the range in21.459 seconds.
Both source checks passed and no returned tool executed. End the38 attempt
series, retain these negative results and the demonstrated availability fix,
and move to another preserved failure rather than adding task-shaped checks.
All processes have exited. There is no new integrated score or80% claim.

## 2026-09-07 Integrated Worker Reconciliation

Read-only reconciliation found all six Sep6 integrated workers completed under
one source seal a7f056c5, with each final integrity check ok. Their189 unique
tasks exactly match the frozen selection:93 passed,46 failed,19 deadlines,
8 protocol failures and23 transport failures. Worker-derived success is49.21%.
The supervisor aggregate is stale (running,52 not_run,57 passed); no parent
process exists. No raw record was resumed, overwritten or marked complete.
Hashes and checks are in
`experiments/work/hybrid-integrated-worker-reconciliation-20260907.json`.

This is diagnostic evidence, not promotion or a replacement of the Aug31
119/189 repair reference. Later local fixes have not had a new integrated
full-denominator run. The80% objective requires at least152/189 in one frozen
version,59 above this integrated condition, not accumulated isolated passes.
Of its96 non-passing tasks,50 are transport/protocol/deadline outcomes; verify
shared recovery there alongside application fixes before any new full campaign.

## 2026-09-07 Impress Focused Paragraph Feedback

[The paragraph-feedback repair](archive/hybrid-impress-paragraph-feedback-repair-20260907.md)
adds optional explicit page selection to the existing inspection API and
retains native paragraph formatting in model feedback. No macro, automatic
target selection, context-budget increase, mutation change or new gate was
added. All174 related tests and Ruff passed. Offline counterfactual focused
reading preserves all6 target paragraphs in9000 characters; whole-deck
reconstruction still loses them. This is not an Agent pass claim.

The affected38/control33 pair under source a97f4d97 (470 files) completed
at19:03Z with unchanged models and limits.33 passed in5 steps/177.013 seconds;
38 ended model_protocol_failure in931.489 seconds after three executed
actions, with no scorer result. Worker and supervisor exited0, final integrity
ok and source unchanged.38 used focused reading but formatted the whole
shape; subsequent requests lost corrective tools before any completion claim.
The follow-up above repairs that availability defect but records negative
decision probes.38 is a Sep6 regression, not an extra pass for the Aug31
reference. No full-189 run, numerator change or promotion was started.

## 2026-09-07 Impress Explicit Page Size

[The page-size repair](archive/hybrid-impress-page-size-repair-20260907.md)
adds a native presentation-wide canvas primitive with explicit model-selected
width/height. It does not alter shapes, infer values or save automatically.
Inspection preserves native orientation through existing compact projections;
no new gate, task route or retired orientation macro is introduced.
All 163 related tests and Ruff pass.

One native operator validation exited 0 at 18:22:06Z. All six API calls
succeeded, the arbitrary portrait dimensions read back correctly, content and
shape geometry were unchanged, and the observed original size was restored
and saved. Its post-finish reward 0 is expected from restoring landscape and
is not an Agent result. Source stayed frozen at c3c00594 (469 files).

The separately frozen affected32/control33 Agent pair completed at18:32:37Z:
32 passed in6 steps/373.401 seconds and33 in5 steps/158.459 seconds. Qwen
selected the dimensions itself and corrected a premature submission after
existing feedback requested save/read-back. Both final integrity checks passed,
source was unchanged, and worker/supervisor exited0. No terminal protocol,
transport, environment or deadline failures occurred. No runner remains active.

This recovers a Sep6 integrated regression;32 had passed the Aug31 reference.
No extra pass has been added to the119/189 numerator, and no full-189 run or
promotion has started. Next is the report's read-only Order38 diagnosis:
native paragraph editing worked, but model context lost text/indentation fields
before wrong repeated edits. A flat receipt alone did not fix the replay;
investigate focused inspection and paragraph feedback without a new gate.

## 2026-09-07 Writer Format Search And Feedback

[The Writer format-search repair](archive/hybrid-writer-format-search-repair-20260907.md)
adds explicit current-format predicates to the existing read-only text.find;
native range mutation remains one model-selected text.set_format call per
range. Native read/edit/read/restore validation passed without model calls.
The first Agent pair retained66 (six steps/197.941 seconds), but82 edited
only12/21 targets and falsely submitted (18 steps/697.453 seconds, reward0).

Observed-format counts then prompted corrective reading in one non-executing
request probe. The second66/82 pair completed at17:55:50Z with source8ec653b2
unchanged, final integrity ok and both processes exit0.66 passed in six steps/
179.785 seconds.82 reached20/21 targets but exhausted the1800-second Agent
allowance; reward is null and the evaluator never loaded. Total task duration
including setup is1852.725 seconds. Three reasoning-only protocol errors were
recovered, but repeated edits and range mistakes consumed time. This is
improved target coverage, not a recovered pass or an80-percent result.

After exit, fixed a demonstrated recovery projection loss: the new setter now
has a compact native business hint, and unused ordinary history allocations
are shared without increasing any budget. The existing range validator now
reports both numeric lengths; no arguments, validation rules or gates change.
Four regressions reproduced the old defects, and all281 related tests plus
Ruff now pass. A production offline replay preserves all21 matches, all format
counts and every successful model call in8459 rather than8973 characters.
No model/application/evaluator ran in that replay. New source:
711b502daf7d7320fdc418edf42feb3f79971ff1e802bd412348b4607df8fbae.

This final feedback source has no new Agent replay. Stop the current82 attempt
series and move to the [diagnosed Impress page-size gap](archive/hybrid-impress-page-size-repair-20260907.md).
That item is read-only diagnosis so far, not a new API or pass. No worker is
active; no full-189 run, repair-reference numerator or promoted pointer changed.

## 2026-09-07 Writer Explicit Character Formatting

[The owning Writer repair](archive/hybrid-writer-character-format-repair-20260907.md)
adds one explicit-range `text.set_format` primitive with exact-text precondition,
native script presets and ordinary save/read-back. It restores no matching
macro, task-specific answer or new gate. All 210 related tests and Ruff pass.
Native operator validation passed five API calls in 277.054 seconds with zero
model requests; it deliberately restored normal formatting, so its task reward
0 is not an Agent score. Source stayed frozen at
ad6e33f0521062030a78b70ae170a5ba9a55be592763cb01a98c8b23c89575ee.

The separately frozen affected66/control73 Agent pair uses the same source and
unchanged generation/episode limits. Order 66 has passed the original scorer
in 6 steps and 187.306 seconds, compared with integrated-parent deadline
exhaustion. Qwen first chose an off-by-one range, received TEXT_MISMATCH with
the actual selected text, corrected its own arguments, formatted the title
character, read back and submitted. No host argument replacement occurred.
Order 73 also passed in 3 steps and 157.943 seconds. The pair completed at
16:35:58Z with 2/2 passed, final integrity ok and unchanged source. The
supervisor exited 0 and no worker remains. There were no terminal environment,
protocol, transport or deadline failures. This is one recovered integrated
regression, not a changed full-189 numerator or an 80% claim. Next inspect
Order 82's missing character-format read/search capability; the current
setter alone does not expose italic runs. Keep its old negative trace and
avoid restoring the removed italic-resize macro.

## 2026-09-07 GUI Edit Plus API Save Completion

[The shared completion repair](archive/hybrid-gui-save-completion-repair-20260907.md)
addresses preserved integrated 32/66/82 claims rejected after audited GUI work
and a successful API save. Save-only persistence now preserves the existing
GUI evidence; exports and later content writes still use normal API checks.
No new gate, auditor, API, argument injection or automatic completion is added.
All 181 relevant tests and Ruff pass. Offline replay changes the three original
claims to pending terminal review, with done=false and raw/parsed arguments
unchanged; API-only 170 remains accepted. No model or evaluator ran, and these
are not three recovered task passes. New source:
dfdc8c1657078772ff67a9ac2137af65f99efce913eca66b9d56fc67e879ef51.
No live worker remains. Next select the strongest remaining GUI/save case
after reviewing its separate application mistakes, then freeze affected/control.

## 2026-09-07 VLC Current Source Feedback Repair

Preserved integrated Order 164 used the playback display filename as a media
input and received PATH_NOT_FOUND. The [owning Adapter repair](archive/hybrid-vlc-source-readback-20260907.md)
reads the native current playlist item's URI, exposes its exact source and
retains a truthful source_error on lookup failure. No task plan, directory
search, argument injection, new API or gate is added. The usage contract
distinguishes display labels from paths. Seven old-behavior failures were
reproduced in an isolated copy while the Writer source stayed frozen.

After both Writer processes exited, the patch was applied to the active
tree; all 156 related tests, Ruff and diff checks passed. A fresh model-free
native read/extract check completed at 15:21:34Z under
vlc-source-readback-operator-validation-20260907-v1, source
2b21247b9af964b1a2431c42a3016b2a88d5ad43c9a98a1d5dd6cc78b34602e2.
Both public calls passed verification: real local source/URI returned, then
a 1920x1080 PNG extracted from that observed source. The actual native source
and URI survive normal bounded model projection without another compactor
change. Source stayed frozen; the harness exited 0. Its post-finish task
reward is 0 because only a synthetic /tmp image was written, not the task
deliverable. This is capability validation only, not a recovered Agent task
or an 80-percent claim. No runner remains active. Next is a separately frozen
164/170 Agent pair; the active repair reference and promoted pointer stay fixed.

That pair is now registered as qwen35-holo31-hybrid-vlc-source-retest-20260907-v1,
one attempt per task under the same 2b21247b seal. It retains the integrated
parent's generation parameters and omits both optional thinking-token and
presence-penalty overrides. Expected evidence is a real 164 Agent pass with
170 still passing, not another operator-only capability result. No new gate
or default is introduced; existing 100-step/1800-second/30-GiB limits remain.

The pair completed at 15:38:11Z, both processes exit 0, final integrity ok and
source unchanged. 164 produced the requested PNG but scored
0.859163639863998/status failed (9 steps, 515.545 seconds); 170 passed
(2 steps, 130.222 seconds). The trace also exposed a missing frame-extraction
keyword entry that falsely rejected a verified mutation. After exit, eight
ordinary snapshot-related keywords were added to the existing catalog, with
no new API, gate or completion rule. All 153 related tests and Ruff pass;
offline replay of the original first completion now succeeds. This later
6380e8125f14905620bfcda6b9a8f301db6bcaa4a095d7a281cdc38c60dbf422 seal
has no Agent replay yet. Whole-second playback time is the next frame-fidelity
diagnostic; no fixed offset, recovered pass or aggregate improvement is claimed.

The unscored native read finished in 48.469 seconds with source unchanged:
HTTP time was 121, same-source MPRIS position was 121091096 microseconds, and
one public extraction at the exact converted native time succeeded. No model
or evaluator ran. The owning Adapter now exposes that precision as time_seconds
and reports time_error when it cannot bind one native player to the same URI;
whole-second time remains intact. No offset, new API, gate or automatic action
is added. All 159 related tests and Ruff pass. One further 164/170 pair is
registered as qwen35-holo31-hybrid-vlc-position-completion-retest-20260907-v1,
frozen at cd60826db8dcc5071e2b2bd182cbb4ff3916820e36667e0da6c445f22bdf4d38.
Measure model use of native precision and clean submission separately from
the unchanged scorer; stop this candidate if frame fidelity still fails.

That pair completed at 15:58:14Z with both processes exit 0, final integrity
ok and cd60826d source unchanged. 164 still scored 0.859163639863998/status
failed, but its first claim was accepted: 4 steps and 152.598 seconds versus
9 steps and 515.545 seconds previously. Actual request inspection confirms
time_seconds=121.101128 reached Qwen; it selected integer 121 anyway. 170
passed in 2 steps and 119.266 seconds. There were no terminal environment,
protocol, transport or deadline failures. No further 164 replay is scheduled;
retain the precision capability and live-verified completion improvement,
without adding a pass or changing any full-189 numerator/baseline pointer.

## 2026-09-07 Writer Thinking Budget Expansion

The [preserved Writer 74 request](archive/hybrid-writer-thinking-budget-retest-20260907.md)
returned the correct next page with only thinking_token_budget=1024 added:
HTTP 200, 56.929 seconds, 1102 output tokens, one schema-valid call, source
unchanged and no tool execution. This follows the earlier Calc pass but does
not establish cross-task success by itself. A new frozen pair registers
affected 74 and passing Writer control 73, one attempt each, under
qwen35-holo31-hybrid-writer-thinking-budget-retest-20260907-v1. Source seal:
a3fa0277be61a2605e9468ea9cf0b339bc74252e46e382a935d9372d71b0b307.
The pair was stopped at 15:11:20Z after 74 repeatedly inspected the already-read
document: 35 read calls, zero mutations, 1285.232 seconds, interrupted with
no evaluator loading and null reward. Control 73 passed in 159.649 seconds.
The worker exited 0 and supervisor 130; source remained frozen, but the final
supervisor integrity publication did not run after interruption. This is an
early-stopped exploration, not a completed passing pair. One connection error
recovered through existing retries. The opt-in budget improved call generation
but did not recover 74; do not enable it by default or replay the pair unchanged.
No gates, configured 100-step/1800-second limits, 30-GiB stop or baseline
pointers changed. The following VLC source fix is outside this sealed run.

## 2026-09-07 Bounded Thinking Affected/Control Retest

Read-only serving inspection found the existing per-request thinking-token
budget. A [single preserved Order 18 probe](archive/hybrid-thinking-token-budget-20260907.md)
changed only thinking_token_budget=1024, keeping thinking enabled and the
4096-token overall cap. It returned one valid range.read in 53.416 seconds
and 1073 tokens instead of the preserved reasoning-only failure. No tool
executed, and source stayed unchanged.

The optional budget now passes unchanged from frozen protocol config to
parent model extra_body. Missing values preserve the old request; Holo,
defaults, retries, gates and task arguments are unchanged. The related suite
passed 331 tests; Ruff and diff checks passed. Independent condition
qwen35-holo31-hybrid-thinking-budget-retest-20260907-v1 completed control 14
and affected 18, one attempt each, source frozen at
0c20f43fc095e2cbbbe5a786012c465660afadf340dcdb173af56417ff0d2938.
It includes current description deduplication and omits the negative
presence-penalty override. Both processes exited 0 by 14:33:38Z, final
integrity ok, source unchanged: **2 passed, original rewards 1/1**. Control
14 took 330.703 seconds; affected 18 recovered from protocol failure to pass
in 878.152 seconds. No terminal protocol, transport, environment or deadline
failure occurred. Keep 100 steps, 1800 seconds and the 30-GiB stop.

The remaining behavior matters: 18 still visually misread populated cells,
repeated fills and saves, used one soft restart and ended under the existing
stall rule at step 21, not model-confirmed completion. Its saved artifact then
passed the unchanged scorer. Control 14 used all 4096 output tokens for one
valid empty-argument read with only 648 reasoning characters and was slower
than its parent. The budget remains opt-in; this is one recovered failed task,
not a clean self-review fix or proof of an integrated 80-percent success rate.

After both processes exited, [one missing fill-count field](archive/hybrid-calc-fill-count-feedback-20260907.md)
was restored in the existing response compactor. Zero and positive values now
survive bounded model projection; absent values are not invented. All 174
related checks and Ruff pass, with no extra priority, budget or gate. This
later source, a3fa0277be61a2605e9468ea9cf0b339bc74252e46e382a935d9372d71b0b307,
has not had a new model-backed or scored replay and is not the two-pass seal.
No runner remains active. No full-189 aggregate or baseline pointer changed.

## 2026-09-07 Native Tool Description Deduplication

The [description-only change](archive/hybrid-tool-description-deduplication-20260907.md)
removes the second Python-repr copy of directly typed tool schemas. Unique
usage guidance, native parameters, strict overlays, untyped tool signatures
and catalog search/ranking are preserved. Three tests reproduced the old
duplication; all 325 related tests, Ruff and diff checks now pass.

A single preserved Order 64 decision probe completed at 14:02:19Z, HTTP 200,
9.194 seconds, source unchanged. Function descriptions fell from 8657 to
2855 characters; actual prompt tokens fell from 7553 to 6165 (18.4 percent).
The model still selected the blank separator, so this is input-efficiency
evidence only, not a recovered task. No tool executed or full-task retry was
launched. Source seal: 39075052fc89389a11b27cdd2d2f1a1827b42e3b9e4174482ad3b9a15052c799.
The repeated-generation failures remain the next shared diagnosis target.

## 2026-09-07 Writer Pagination Affected Retest

The [pagination repair](archive/hybrid-writer-inspect-pagination-20260907.md)
adds two optional read-range fields to existing document.inspect. It addresses
Order 74's unreachable middle paragraphs without a new route, hidden plan,
mutation, or gate. The default overview is unchanged. The related suite passed
315 tests and Ruff; a single non-executing preserved request selected a valid
paged read in 8.453 seconds. Frozen source:
e8ac1ae6eb9f82d6f888135e3fa0d6f10edbf5e6c0896f4b2e5fc245b7ef62f2.
Condition: qwen35-holo31-hybrid-writer-pagination-retest-20260907-v1.

The first affected/control run completed at 13:32Z with final integrity ok.
Control 64 passed with original reward 1; affected 74 read previously omitted
paragraphs but ended in model_protocol_failure. At step 5, three 4096-token
responses endlessly repeated record identifiers and produced no tool call.
No terminal environment, transport or deadline failure occurred.

After both processes exited, the real native-format fixture reproduced missing
page cursors. Three priorities in the existing projector fixed that loss with
all paragraph text retained within 5000 characters. No budget or gate changed.
The related suite remained at 315 passed. A separate parameter-only snapshot
with presence_penalty=1.0 then produced the correct next page in 23.997 seconds
and 440 tokens instead of exhausting 4096 tokens. No tool executed in the probe.

Optional per-condition presence_penalty now passes unchanged from the hashed
protocol config to parent Qwen requests; None preserves the old omitted field,
and Holo is unchanged. The related suite passed 418 tests and Ruff. The second
two-task condition, qwen35-holo31-hybrid-presence-penalty-retest-20260907-v1,
completed at 13:59:15Z with source seal
15e6d6360af6835016cb4e122cc98ce28d104f8b74fb0ca17e849553100211b0.
This combines the cursor fix and sampling override, not a mode-only ablation.
Both processes exited 0; final integrity was ok and source stayed frozen.
Control 64 failed (161.602 seconds), selecting raw indices 0 and 1 despite
the observed blank separator. Affected 74 read pages through start 60 but
ended in model_protocol_failure (783.295 seconds): three further 4096-token
reasoning loops, zero calls. No affected-task pass or new integrated rate
was recovered. Do not enable the penalty by default or repeat 74 unchanged.
The [next input-overhead experiment](archive/hybrid-tool-description-deduplication-20260907.md)
removes duplicate schema prose while preserving native contracts and search.

Two earlier diagnostics are closed: the [token probe](archive/hybrid-generation-overhead-20260907.md)
did not reproduce the 4096-token overhead (134 tokens, 7.248 seconds), and
restoring the latest paragraph observation in a preserved Order 65 completion
snapshot still produced an incorrect propose_done (577 tokens, 30.404 seconds).
Neither justifies another unchanged repeat. The 80-percent goal, hybrid models,
100 global steps, 1800 seconds, 30-GiB stop, and baseline pointers stay unchanged.

## 2026-09-07 Paragraph Observation Repair Recovered One Task

The [bounded-observation repair](archive/hybrid-writer-paragraph-selector-20260907.md)
recovered Order 64 from failed to passed, with original evaluator reward 1;
passing Writer image-insertion control 73 remained passed. The independent
frozen two-task run completed at 12:43:56Z, durations 169.388 and 352.335 seconds.
Both processes exited 0; final integrity is ok, source stayed frozen, and
terminal environment/protocol/transport/deadline failures are all zero.
Source seal: f9707744b5591976ee51aa663bfa4982b07ed562f31f504459fd53dbfd98b459.
Condition: qwen35-holo31-hybrid-writer-observation-retest-20260907-v1.
The existing 100 global steps, 1800 seconds, and 30-GiB stop are unchanged.

The actual defect was lost input evidence: paragraph text was discarded
behind verbose formatting and an observed null ordinal was treated as an
omission. Three field priorities and one null-retention correction restore
the distinction between raw blank objects and paragraph positions in text.
The model selected the corrected indices itself; no API, parameter default,
gate, validator, task-specific route, or argument rewrite was introduced.
The related suite passed 148 tests, Ruff and diff checks passed. A broader
allocation experiment was removed when an existing batch test caught a
regression; batch-continuation checks now pass unchanged.

Both [terminal-review variants](archive/hybrid-terminal-evidence-review-20260907.md)
and a selector-description-only probe were negative. Their runtime changes
were withdrawn, with raw requests and results preserved. No changes from
those abandoned prompt variants remain in the runtime. The two passes above
are individual evidence, not a new 189-task rate or a claim of reaching 80%.
The Aug-31 repair reference and promoted v337 pointer remain unchanged.

Next evidence targets are other lost paragraph observations (65/74) and
unexplained generation overhead. The passing control used 4096 output tokens
on one empty-argument read, with only 538 visible reasoning characters; one
request was running and none queued. Do not infer a general concurrency fix
or silently raise timeouts from that observation. About 425 GiB is available,
and no runner remains active at this checkpoint.

## 2026-09-06 File-Edit Search Recall Repair

The preceding 112 replay was progress through new negative evidence, not a
reason for another unchanged attempt. Preserved 94 v24 instead exposed a
[catalog recall gap](archive/hybrid-file-edit-search-repair-20260906.md): editing/files
word forms omitted the existing literal-edit tool from six results. Five
ordinary keywords repair the original query and independent source-editing
queries without altering command priority, APIs, arguments, or gates.
Three tests failed before repair; the related suite now passes 179 tests,
with Ruff and diff checks passing. One non-executing preserved-request probe
is registered with source seal
7febd7f8db6e744e5f14129e241975e834a5af5ccd18d96f6d85aa1c4fae9e04.
No task pass, new episode, or promotion is claimed; 30 GiB remains unchanged.

The one-request probe completed at 09:03:41Z, HTTP 200, 12.599 seconds and
219 output tokens. The model selected the newly discoverable existing
file.replace_literal tool with schema-valid model-authored arguments instead
of sed. Nothing executed and the source stayed unchanged. This is positive
next-tool evidence, not a recovered pass. Do not repeat the probe; next is an
independently sealed affected 94 episode. About 31.2 GiB remains, less than
the preceding fresh-VM allocation plus the 30 GiB reserve. No new episode,
cleanup, or unrelated container stop is started. The verified 11.43 GiB
already-extracted VM ZIP is a potential cleanup candidate only with user
authorization; redownload availability has not been verified.

## 2026-09-06 Stall Recovery Affected Retest

Registered [one fresh Order 112 attempt](archive/hybrid-stall-recovery-retest-20260906.md)
using source seal d6d0ac3089da3f0951db9c616e3eea85090a21a2b4433a8032816a59c598d889.
It checks the corrected within-retry window and forwarded command identity
against the preserved v24 failure. This includes intervening source changes,
not an isolated ablation or a contemporaneous control claim. No pass is
claimed at registration. One worker, runs=1, 100 global steps, 1800 seconds,
and the user-authorized 30 GiB disk stop remain unchanged. About 32.8 GiB is
available; retain any disk stop without cleanup or an unchanged retry.
Keep source frozen through final process exit; no new gate or promotion.

Completed at 08:50:17Z: failed, reward 0, 18 global steps, 631.479 seconds,
one soft restart. The corrected window allowed all eight new local steps
instead of stopping after one. The model nevertheless repeated a command
without stdout_path, briefly attempted unsupported shell redirection, then
returned to the same blocked call. Actual model requests retain the parameter
description, no-file-saved guidance, duplicate errors, and shell recovery
instructions. The missing report returned 404 during scoring; terminal
environment, transport, protocol, and deadline failures are all zero.
Both processes exited 0 and final integrity checks are ok with unchanged
source. Disk stayed above 30 GiB and is about 32 GiB after normal teardown.
No active runner, cleanup, unchanged retry, new pass, or promotion is claimed.
Results SHA-256: 342b7a3f7f4e7b7f502148dd92546f277cc7c42a19e5ab967cfe910ed704f285.

## 2026-09-06 Forwarded Command Stall Identity Repair

Read-only Order 94 v24 replay confirmed that the existing stall detector
collapsed different forwarded sed/cat/python3 commands to an empty argument
identity. It read argv/stdout_path from adapter.call's outer envelope instead
of payload.params. The [minimal parser-reuse repair](archive/hybrid-command-stall-identity-repair-20260906.md)
now retains the actual command arguments and output destinations. Six synthetic
direct/forwarded cases preserve distinct operations, detect terminal-mode-only
cycles, and leave proposals unchanged. The two affected cases failed before
repair; the related suite passed 123 tests, with Ruff and diff checks passing.
The preserved step-36 false stall no longer triggers in offline reconstruction;
no model action executed and no task pass is claimed. Source seal is
d6d0ac3089da3f0951db9c616e3eea85090a21a2b4433a8032816a59c598d889
(463 files, 54,752,346 bytes). No new gate, limit, or live run was added.
The 30 GiB default and explicit override were reconfirmed by two focused
tests; about 32.8 GiB is available and no runner/supervisor is active at this
checkpoint. No source, evidence, or unrelated container was removed.

## 2026-09-06 Soft-Restart Window Repair

The single literal-scope probe returned HTTP 200 and a valid call in 32.429
seconds but still supplied only a method declaration as old. Source stayed
frozen; no tool was executed. Preserve this negative result and do not rerun
the same description hypothesis.

A separate [controller defect](archive/hybrid-soft-restart-stall-window-repair-20260906.md)
was reproduced from four completed traces across Orders 94/105/112. The first
post-restart observation immediately triggered another stall because seven
pre-restart events remained in its eight-event window. The existing detector
now uses event.retry to keep the window within one retry while preserving
prior evidence, error blocks, all budgets, and the one-restart limit. Two
synthetic regressions failed before the repair and now pass, including the
unchanged stop after eight fresh no-progress events. All four real replays
retain the first stall but no longer terminate after one recovery event.
The related suite passed 103 tests; Ruff and diff checks passed. Current
source seal is 6b777beb76a385d739d3ef88dc03dd97df1b6953bc92ecd2eefb82de1769c950.
No live run used that seal, and no task pass is claimed. About 33.5 GiB is
available, close to the 30 GiB stop after a fresh-VM allocation; no runner,
supervisor, cleanup, new gate, or promotion is active. A new affected 94/112
condition is the next live verification, not an unchanged wording retry.

## 2026-09-06 Literal Replacement Retest And Usage Diagnosis

Registered [one fresh Order 105 replay](archive/hybrid-literal-replacement-retest-20260906.md)
after the demonstrated zero-match false-success repair. The parent received
reward 1 but left a removed method and broken call path; this run checks
functional edits separately from the original evaluator reward. Source seal
5b838e4da43e30bd3ea407be1455c44e6f9bf77f41579b3fb4908f803c55e1bd
includes current bounded recovery and ordinary-error-language fixes. The
relevant suite passed 64 tests before launch.

Keep one worker, runs=1, thinking, temperature 0, 100 steps, 1800 seconds,
and 30 GiB. No source edits until final process exit, unchanged retry, full
run, new gate, or baseline promotion. Offline 29/163 inspection established
no new execution defect and did not justify a selector or codec change.

The retest completed at 08:00:34Z, both process exits 0 and final integrity
checks ok: failed, reward 0, 37 steps, 1532.617 seconds, stalled_no_progress,
one soft restart. Two no-call truncations recovered; terminal environment,
transport, protocol, and deadline failures are zero. No zero-match native
replacement occurred, so that earlier error fix was not exercised. The model
repeatedly replaced only a method declaration while intending to replace its
whole body, and active file-read feedback named nonexistent file.write_text.
After finalization, two runtime text surfaces were clarified: only old is
replaced, a whole block requires its complete current text, and read feedback
names the supported file.replace_literal action. Six usage assertions failed
before repair; the final relevant suite passed 161 tests, including actual
model-message retention and both existing disk-stop cases. Ruff and diff
checks passed. No implementation, argument, budget, or gate changed.
The 30 GiB stop line remains confirmed in the default, config, and launch
arguments, with about 34.2 GiB remaining and no active runner or supervisor.
No model-backed run used the later source; a new sealed condition is required.
No new live attempt, gate, promotion, or aggregate pass is claimed.

## 2026-09-06 Native Error Feedback And Disk Stop Confirmation

The [application-error language repair](archive/hybrid-application-error-language-repair-20260906.md)
removes a confirmed false positive in the two existing metadata sanitizers:
ordinary Calc, OS, and VS Code errors containing standalone `reference` or
`expected` were hidden in full. All six direct/forwarded reproductions now
retain the exact native error in actual model messages. Explicit internal
metadata remains filtered, with no new API, gate, or argument rewrite.
The relevant offline suite passed 240 tests, including the two existing
disk-stop cases; Ruff and diff checks passed.

The supervisor already uses the authorized 30 GiB stop line; no further
threshold edit was needed, with about 37 GiB available. No model-backed run
was launched. A new sealed condition is required before replay, and no
additional task pass is claimed. The previous Calc label-selection failure,
100-step/1800-second limits, active repair goal, full-run numerator, and
promoted v337 pointer are unchanged.

## 2026-09-06 Observation Retests And Recovery Feedback Repair

The [Order 105 source-priority retest](archive/hybrid-file-content-priority-retest-20260906.md)
completed at 06:36:32Z, supervisor exit 0: reward 1, 25 steps, 924.719 seconds,
with worker/supervisor final integrity ok. One no-call truncation recovered;
terminal protocol/transport/environment failures were zero. It stopped for
no progress, not model-declared completion. Its final code corrected initial
positioning but wrongly removed a method, which the narrow evaluator did not
exercise. Preserve the scored pass but do not claim full functional recovery.

After all run processes exited, two concrete generic defects were repaired:
the [Writer hint budget](archive/hybrid-writer-table-budget-repair-20260906.md)
now preserves coordinate-bearing tables (synthetic 12/60 became exact 60/60
through both actual request paths), and [literal replacement](archive/hybrid-literal-replacement-feedback-repair-20260906.md)
now reports an existing no-match error instead of falsely inferring an earlier
write from unrelated replacement text. The relevant suite passed 238 tests,
Ruff and diff checks passed. No API, argument rewrite, or gate was added.

The [affected-only Order 76 retest](archive/hybrid-writer-table-budget-retest-20260906.md)
completed at 07:03:24Z with v33's temperature 1.0 and frozen source seal
0797c6742ded1310d4e6cefdc43a3a477d0d0f4d6121f00aceb0ea1b98a95fe8:
passed, reward 1, 11 steps, 1134.056 seconds, normal model completion, no
completion rejections or soft restart, and final integrity ok. All 52 words
were correctly colored and saved. One no-call truncation recovered; terminal
protocol/transport/environment failures were zero.

That run exposed a separate [ordinary recovery allocation defect](archive/hybrid-recovery-latest-observation-repair-20260906.md):
a summary only 88 characters over its 9000-character budget lost 43 cells.
After both run processes exited, existing fitting was adjusted to budget
newer entries first while retaining small audit markers and chronological
output. The captured request now keeps all 55 cells in 8997 characters.
The updated relevant suite passed 242 tests, the two existing disk-stop tests
passed, and Ruff/diff checks passed. No gate or global budget was added.

Post-repair source is 462 files / 54,742,360 bytes, seal
8ebf647e62ac90898e745da9d3edb8d083e106c9a3e7de7e46a33e0c4fcdb1c7.
No model run used this later seal; do not attribute the preceding pass to it
or reuse the completed condition. The 30 GiB stop and 100-step/1800-second
limits remain unchanged, with about 38 GiB free at handoff and no active test
process. Isolated results do not update the original ten-task rate, integrated
repair numerator, or promoted v337 pointer. The next work must use new
preserved-failure evidence or a separately frozen condition, not an unchanged
repeat of these completed runs.

## 2026-09-06 Chart Retest Passed And Source Content Retained

The [frozen chart read-back retest](archive/hybrid-calc-chart-readback-retest-20260906.md)
completed at 06:11:01Z: Order 2 passed in 7 steps / 396.100 seconds, and the
stable Order 63 control passed in 11 steps / 405.725 seconds. Both final
integrity checks were ok and source remained unchanged through exit. Calc
stopped after saving without the parent's eleven post-save reads. It did not
inspect populated charts after creation, so the result proves the overall
condition pass, not causal use of the newly retained chart fields.

Continued offline review found that Order 105's compact recovery kept usage
guidance while discarding most of two small source files. The [one-entry
priority repair](archive/hybrid-file-content-priority-repair-20260906.md), made
after the chart run exited, changes no budget or gate. The 900/606-character
observations improve from 65/68 visible characters to 655/606. Two new
regressions and the related suites passed 145 tests; Ruff passed. A model-backed
Order 105 replay remains pending a new condition. Current source seal is
263410e4dfc21befd20b91caa820cf874b53a4e458f84220cc4870052df9151e.
No further runtime change was justified by the 94/112 command-trajectory checks.
The 30 GiB stop, 100-step/1800-second limits, full-run numerator, and promoted
v337 pointer remain unchanged. The original ten-sample queue is not re-scored
by combining these isolated runs.

## 2026-09-06 Calc Chart Headers And Read-Back Repair

The [chart repair](archive/hybrid-calc-chart-headers-repair-20260906.md)
completed v1 with Order 15 failed / Order 63 passed. In v2, Order 15 retained
all twelve months after the header-description fix but still failed because
the model selected eight numeric series instead of total-only values. Order 2
created and saved its chart, then repeatedly read empty chart-sheet cells.
The coding operator interrupted that diagnostic after 17 steps; the run has
no control reward or final-integrity attestation and is not a completed pair.
All attempts, including two separately marked invalid-leakage probes, remain
preserved. No new pass or no-regression claim is made.

After process exit, the existing workbook projection was fixed to retain
native chart settings and inspection errors, with bounded omission counts.
Direct/forwarded request tests and related suites passed 142 cases; the two
disk-stop checks and Ruff passed. Preserved observations now retain all three
charts in roughly 1.2k characters per workbook. No post-fix model rerun occurred.
The next replay needs a new sealed condition; current seal is
efee53aae8400431c78299a310ca01f79005726d3af372761c3592967f075e9b.
The 30 GiB stop, 100-step/1800-second limits, repair numerator, and promoted
v337 pointer remain unchanged. No API, gate, or argument rewrite was added.

## 2026-09-06 Calc Chart Title Affected-Control Retest

The [frozen retest](archive/hybrid-calc-chart-title-retest-20260906.md) passed
the affected Calc Order 2 and stable Impress Order 63 control (`2/2`, reward
`1.0` each). The existing chart contract clarification separated the internal
chart-object `name` from the displayed `title`; no route, default, argument
rewrite, or gate was added. The run used one fresh VM per task, 100 steps,
1800 seconds, and the authorized 30 GiB disk stop. Its final integrity and
source seal matched throughout. This is isolated repair evidence only: the
hybrid repair numerator and promoted v337 baseline remain unchanged.

## 2026-09-06 Writer Table Coordinate And Color Usage Repair

Preserved Order 76 showed a model-understanding defect rather than an Adapter
failure: it treated `A1/A2/A3` as one row and later emitted `black` while its
reasoning specified `#FF0000`. The [repair](archive/hybrid-writer-table-coordinate-repair-20260906.md)
adds generic `row_index`/`column_index` metadata to existing `table.read`
observations, explains first-character semantics for starts-with rules, and
documents standard red/blue color mappings. It does not classify words, choose
targets, rewrite colors, add a route, or add a gate.

The focused Writer/context/public-contract suite passed 178 tests, Ruff and
diff checks passed. Three bounded non-executing diagnostics produced evidence:
coordinates improved grouping; first-character wording selected all 11 vowel
cells but emitted `black`; color mapping then produced `color="red"` while
generating only a partial first batch. No complete task pass is claimed. Source
stayed frozen at seal 3a401fc17e78f0aa91d228d0282bc8c020a9bed25fba62854992a81304245d0a.
The disk stop remains 30 GiB with about 51 GiB free; 100-step/1800-second
episode limits, repair numerator, and baseline pointer are unchanged. Do not
repeat these probes; a future Order 76 replay requires a new sealed condition.

## 2026-09-06 Settings Discovery Usage Repair Verified

Offline reconstruction of preserved Order 141 confirms that the raw
`command.run` response contained the 246-character GSettings key listing, but
the next historical model request retained only `stdout_chars=246`. The shared
command-context repair already restores bounded stdout/stderr to model context;
no duplicate feedback change was added. The [settings repair](archive/hybrid-settings-usage-repair-20260906.md)
clarifies the existing `desktop.set_setting` contract for schema/key discovery,
relocatable `SCHEMA:/instance/path/` identifiers, and `gsettings get/range`.
It adds no API, profile lookup, task route, value, gate, or argument rewrite.

The focused direct/forwarded, execution, context, protocol, decomposition, and
recovery checks passed: 161 tests, plus Ruff. One preserved-request,
non-executing diagnostic completed at 02:51:02Z in 14.111 seconds. With the
complete observed listing and current usage descriptions, Qwen selected the
schema-valid discovery call `gsettings list-schemas` instead of guessing another
missing size key. Source stayed frozen at seal
0afb1cca5970d7a8ffd329c363bbfa3865872644ba7da3773bb19db3e87dcaad. This is
model-visible feedback evidence only, not a task pass. The 30 GiB disk stop,
100-step/1800-second episode limits, repair numerator, and baseline pointer are
unchanged. Do not repeat this probe or start a whole-task replay without a new
sealed condition.

## 2026-09-06 Terminal Overview Repair Verified Natively

The [native comparison](archive/hybrid-terminal-overview-repair-20260906.md)
completed at 02:26:40Z with unchanged source and clean process/guest exit.
The identical terminal call passed with overview closed (5.820 seconds),
failed with overview open (119.222 seconds), then passed after native close
(6.075 seconds). The failure kept actual output and exit status, verifying
the preceding deadline repair. Add one bounded native close after observing
the launched terminal, before existing activation. No command arguments,
schemas, verification standards, retries, or gates changed. The new focused
reproduction failed before the repair; all 211 related tests and Ruff now pass.
Recovery condition operator-terminal-overview-native-20260906-v2 is registered
with source seal bd16d982ec187226740abbf96fb69123276dfc83a5bc7c9946a9ca099da72246.
It opens overview and leaves closing to the Adapter, then checks a closed-state
control. No model runs, requested task setting changes, or Agent pass claims.
Keep source frozen, preserve both attempts, and retain the 30 GiB disk stop.

Recovery v2 completed at 02:36:46Z, exit 0, all six API actions successful.
The affected call changed observed overview=true to false without an operator
close and passed in 7.426 seconds; the closed-state control passed in 6.762
seconds with identical command arguments. Source stayed frozen and the guest
and processes exited. This verifies the native focus repair, not the whole
task: no model ran and no terminal-size setting was changed, so the synthetic
post-finish reward 0 cannot enter any Agent score. Next evidence-backed issue
is generic discovery/usage of profile-scoped settings, since the original
model repeatedly selected nonexistent keys. Do not restore the retired size
macro or repeat the native condition. Baseline pointers/numerators and the
100-step/1800-second limits are unchanged.

## 2026-09-06 Writer Model Probe And Terminal Focus Evidence

The [Writer tab-stop probe](archive/hybrid-writer-tab-stop-repair-20260906.md)
recognized the new field but exhausted 4096 tokens without a call while
conflating paragraph and per-tab alignment. Clarified only the owning public
usage descriptions; 44 focused tests and Ruff passed. A separately recorded
second probe exited 143 without a response artifact; its cause is unknown,
source was unchanged, and it remains inconclusive rather than a model failure.
No third request or Writer episode is scheduled at this review checkpoint.
Neither diagnostic adds a task pass. Retain the generic capability and usage
clarification without changing defaults, execution, or gates.

Offline review of preserved Order 141 screenshots exposed GNOME Activities
overview before and after the terminal read-back failure, despite visible
completed output. A [fresh native comparison](archive/hybrid-terminal-overview-repair-20260906.md)
is registered to compare closed/open/closed overview with the same public
read-only command. No model or task setting is involved. The current source
seal is 311bcd4ee12442fa9d54bb148d1a3af92ba19d2ec11b031c0f210365cc9fe9b2;
keep it frozen during the diagnostic. The 30 GiB stop line and repair goal
remain active. No full-run numerator or baseline pointer changed.

## 2026-09-06 Writer Explicit Tab Stops And Native Validation

Preserved cohort30 Order 65 exposed a generic capability gap after macro
decomposition: paragraph.set_format had no explicit tab stops, and the Agent
projection dropped the native tab observations. The [repair](archive/hybrid-writer-tab-stop-repair-20260906.md)
adds measured mm/cm/in positions and alignment to that existing action,
retains observed tabs, and improves lexical retrieval. It does not split text,
choose positions, restore the retired macro, or add a gate. All 298 related
tests and Ruff passed. The model-free fresh-guest diagnostic completed at
01:58:40Z, exit 0, with five successful API actions. Native read-back confirmed
0/38.1/67.5 mm, decimal/leader characters, and clearing; all 12 paragraph texts
and unselected paragraph observations stayed unchanged. Source remained at
1706628d13ef67485e161a1949e4e9f13dc550b979d0304fa24c8bfceacc1466
(461 files, 54,715,768 bytes), and its processes/guest exited.
The synthetic check did not solve the task: post-finish reward 0 is non-Agent
evidence, not a recovered pass. Next is a bounded preserved-request diagnostic
of model use, not an unchanged episode replay. The full-run numerator and
baseline pointer are unchanged. The 30 GiB stop default/override tests passed;
the repair goal and 100-step/1800-second episode limits remain active.

## 2026-09-06 Terminal Read-Back Deadline And Partial Results

The preceding checkpoint verified the 30 GiB stop line without advancing the
failure queue. Continued offline review found no new missing-output defect
in 94/112 or selector omission in 29; 119's GUI-only choice remains separate
from its prior image.adjust pass. An adjacent cohort30 141 failure exposed a
shared [terminal read-back issue](archive/hybrid-terminal-readback-deadline-repair-20260906.md):
a completed command's visibility failure was hidden by the outer timeout,
and its captured output was dropped. One existing deadline now covers launch
and polling, and the error retains actual exit status/output without claiming
visible success. Protocol wording no longer says every executed=false implies
an unchanged VM. No event flag, argument, completion rule, or gate changed.
The 8-second synthetic reproduction previously took 18.1 seconds; it now
finishes within 8. All 209 related tests, Ruff, and diff checks passed.
Source seal: 0fcd94f55923d265f6b1dd95f6dedc27d69d2328afcbc4593ea17bf5ea8d0781
(460 files, 54,703,214 bytes). No model/guest/evaluator ran, no new pass is
claimed, and a real affected retest remains pending a new condition. Next
offline candidate is 65's missing explicit Writer tab-stop formatting after
macro decomposition; do not restore a task-shaped split helper. The repair
goal, 30 GiB disk stop, and 100-step/1800-second limits remain active.

## 2026-09-06 Next-Action Observation Wording

The previous turn made progress by finalizing v33, verifying live repeated
reads, and recording its negative affected result and passing comparison.
Its preserved Writer request still ends a complete structured observation
with a screenshot-only next-action instruction. Two focused tests reproduce
that wording. The [small repair](archive/hybrid-observation-priority-repair-20260906.md)
changes only the sentence to include the instruction, latest tool results,
and screenshot together; data, schemas, arguments, and gates are unchanged.
After verification, one preserved-request diagnostic is planned with the
source v33 sampling settings, no retry, and no tool execution. This is not
another Writer episode, a default temperature change, or a task-pass claim.
The 30 GiB disk stop and repair goal remain active.
Completed verification: 111 related tests, Ruff, and diff checks passed.
The single diagnostic completed at 01:11:48Z, HTTP 200, 509 tokens in
26.794 seconds, with the source seal unchanged at
982e0973c580b0c1211e74c8f70d5d6d0b22b3a32f75c6117ef6416eb9c0947e.
It returned a valid color call but still selected an incorrect cell after
correctly recognizing the word's initial letter in reasoning. No tool or
evaluator executed. This negative target-selection evidence does not justify
a third Writer episode. Retain the generic wording correction and move to
another evidence-backed candidate, without another speculative hint or gate.

## 2026-09-06 Read Recovery And Temperature v33 Results

[v33](archive/hybrid-read-temperature-retest-v33-20260905.md) completed at
00:57:28Z with supervisor exit 0 and both final integrity checks ok. Source
stayed at 01cdef69ba42fdd838f98cd1811e80d7b8e2422d22fb9607df39e4fe8e33291d.
Writer 76 exhausted its 1800-second Agent deadline without a reward; all
18 recorded events executed, including nine full 55-cell reads, four color
batches, three GUI scrolls, and save. No duplicate-read rejection occurred.
Four 4096-token no-call generations recovered, but 17 of 52 nonempty words
remained incorrectly colored in the last read. This verifies read recovery,
not task recovery. Comparison 63 passed in 20 events and 1562.422 seconds,
after one recovered truncation and model-corrected textbox ordering errors.
No terminal environment or protocol failure occurred. Writer's last request
timeout was bounded by its episode deadline, not a separate transport outage.
The temperature probe did not translate into a new affected pass or reliably
short generation. Retain the read fix and default temperature 0.0; do not
append another unchanged Writer attempt or promote this condition. The repair
goal remains active; next work starts with offline diagnosis, not new gates.
The user-authorized 30 GiB default/override tests both passed. About 60 GiB
remained after teardown; no process from this condition remains running.
Results SHA-256: 46eef9239d7966f1a3094550e0de014d6c0f4235fac10bbe08a29b86440f93f1.
The integrated full-run numerator and promoted baseline pointer are unchanged.

## 2026-09-05 Read Recovery And Temperature Retest v33

Registered [v33](archive/hybrid-read-temperature-retest-v33-20260905.md)
for affected Writer 76 followed by stable comparison 63, one attempt each.
Source seal: 01cdef69ba42fdd838f98cd1811e80d7b8e2422d22fb9607df39e4fe8e33291d.
The condition alone uses Qwen temperature 1.0; thinking mode, Holo settings,
100-step/1800-second limits, one worker, and 30 GiB remain unchanged. This
combines the verified read-recovery repair with the positive temperature
probe; it is not a temperature-only ablation or a default/score promotion.
No result or task pass is claimed at registration. Keep source frozen and
review after the two scheduled episodes before any further affected attempt.

## 2026-09-05 Writer Temperature Diagnostic

Registered a [one-request diagnostic](archive/hybrid-writer-temperature-probe-20260905.md)
against v32 step 7 attempt 1, which exhausted 4096 tokens without a tool call.
Only temperature changes from 0 to 1.0. Thinking mode, original messages and
schemas, endpoint, and output/time budgets remain unchanged. No tool will
execute, no retry or fresh VM is scheduled, and no default or task pass is
claimed. Source seal stays 29e951669340d96d1f96a1b855506f02929d5adf5fcc32f5af3312beff993c64.
The previous turn made progress by completing the repeated-read repair and
offline verification. Disk stop remains 30 GiB.
Completed at 23:52:27Z: HTTP 200, 12.618 seconds, 218 output tokens, one valid
table.read call, and unchanged source. No tool executed. This supports a
bounded-generation hypothesis, not correct classification or a task pass.
After completion, added the supervisor's missing --temperature forwarding
to the already-supported worker option; default stays 0.0. All 139 related
tests and Ruff passed. Next is an independently sealed affected/control
76/63 combined read-recovery and temperature check, not a default switch.

## 2026-09-05 Repeated-Read Recovery Repair

After v32 finalized, the [read-recovery repair](archive/hybrid-repeated-read-repair-20260905.md)
removes only the success-only duplicate restriction for canonical read-only
actions. Three focused failures reproduced the direct/forwarded obstruction;
188 relevant tests now pass, with Ruff and diff checks clean. Actual read
failures and duplicate mutation handling remain unchanged, and the existing
equivalent-read stall detector still terminates loops. No new gate or retry
mechanism was added. The original v32 step 8 call now executes unchanged in
a host-only recording-executor replay, and the next model context retains
all 55 recorded cells. No model, application, or evaluator call occurred.
Replay SHA-256: 953bd3f22fa12142e738a42fb2d7890898c3d49a417dfe9e1a16a3dea21b10d6.
New source seal: 29e951669340d96d1f96a1b855506f02929d5adf5fcc32f5af3312beff993c64.
No new Agent run or pass is claimed. Model repetition/classification remains
unresolved; a separately registered one-request sampling diagnostic is the
next bounded option. No test process remains active. The repair goal and
30 GiB disk stop line remain unchanged; available space is about 64 GiB.

## 2026-09-05 Writer Repeated-Target Affected Retest v32

Registered [v32](archive/hybrid-writer-repeated-target-retest-v32-20260905.md)
for one affected Order 76 thinking-mode attempt, using seal
d4a0f37156e6687fdca8fc7832113223874dd956450e49e2f373b914497f09b4.
The idempotent same-color contract no longer rejects duplicate target names.
Classification and prior output exhaustion remain open; no result or pass is
claimed at registration. One worker, 100 steps, 1800 seconds/task, and 30 GiB
remain unchanged. v31's passing unrelated API control is not repeated. This
is not a mode ablation, full run, integrated score, or promotion.
Completed at 23:38:55Z with exit 0 and both final integrity checks ok. Order 76
ended in model_protocol_failure without a reward: three color batches executed
without duplicates, but one word remained misclassified, two repeated reads
were rejected, and step 10 exhausted three 4096-token generations without a
tool call. Steps 7 and 8 each recovered one earlier truncation. The old
duplicate-target defect is verified offline, not exercised by this live run.
No environment/transport/deadline failure occurred. Do not rerun unchanged;
the next evidence-backed repair addresses the repeated-read obstruction.

## 2026-09-05 Writer Idempotent Repeated Targets

The [Writer repair](archive/hybrid-writer-repeated-target-repair-20260905.md)
removes only the unnecessary unique-name restriction from one-color table
formatting. Original arguments, execution order, and response targets remain
unchanged; the existing count now reports distinct cells. All 135 focused
checks and Ruff pass. All three preserved v27 76 calls now pass public and
owning-Adapter validation byte-for-byte, with zero network or application
calls in the replay. Incorrect classification remains a separate failure.
Source seal: d4a0f37156e6687fdca8fc7832113223874dd956450e49e2f373b914497f09b4.
Next is a single thinking-mode affected 76 check, not another Calc retry,
full-189 run, promotion, or new aggregate score. Disk stop remains 30 GiB.

## 2026-09-05 Calc Formula-Error Usage Feedback

After v31 exited with both final integrity checks ok, repaired the preserved
v27 23 error that recommended formatted_text after formatted_text itself had
failed. The [report](archive/hybrid-calc-formula-error-feedback-20260905.md)
records two initially failing synthetic cases, 89 final passing tests, Ruff,
and a zero-model/application/evaluator replay retaining the new guidance in
the actual recovery context. Draft wording hit an existing sanitizer false
positive; cell-address wording plus a visibility assertion resolves this
message without changing security rules. No argument, formula conversion,
rollback, validator, or gate changed. Current source seal:
1c92d841d93a1237bb0c7b73588157b66f84a3e43af222a50d945e10deaaf61e.
No new Calc task pass is claimed and no run remains active. A bounded
next-action diagnostic, not another unchanged long episode, is the next
verification option. The repair goal remains active and disk stop is 30 GiB.
The subsequent single-request diagnostic completed at 23:03:46Z with unchanged
source, HTTP 200, and no execution. It repeated the wrong 30-to-29 row write
and text-cell decimal formatting. This is negative next-action evidence, not
a task pass; do not add an unchanged Calc episode. The next concrete repair
is Writer's unnecessary uniqueness restriction on a same-color cell batch.

## 2026-09-05 Audited-GUI Completion Affected-Control Retest v31

Registered [v31](archive/hybrid-gui-completion-retest-v31-20260905.md) for
affected 119 and prior passing API-only control 63, one attempt each, using
seal 259e8385510863e5608710f3276c2a9674a45f262b968069ad5e466ae6c3a5ea.
Qwen/Holo thinking, one worker, 100 global steps, 1800 seconds/task, and the
user-authorized 30 GiB disk stop line remain unchanged. The source includes
both path-prefix compatibility and audited-GUI completion, not a regex-only
ablation. No task pass, integrated score, or promotion is claimed at launch.
Completed at 22:48:06Z, exit 0 and both final integrity checks ok: 119 failed
at reward 0 in 19 GUI-only events, while 63 passed in 11 API-only events.
119's completion was accepted and separately confirmed without any Adapter
write or completion rejection. Its retained PNG is a whole-slide export with
the picture washed out at 100% brightness. The completion mechanism improved,
but image selection/export remains wrong. No terminal protocol, transport,
environment, or deadline failure occurred. Preserve all results and do not
repeat 119 unchanged; the next small repair addresses Calc error feedback.

## 2026-09-05 Audited-GUI Completion Repair

The [completion repair](archive/hybrid-gui-completion-repair-20260905.md)
allows explicit audited-GUI claims through the existing terminal confirmation
without forcing an additional Adapter write. Read-only verification is allowed;
later Adapter writes and API-only episodes retain their ordinary checks. The
157 relevant tests and Ruff passed. Offline replay of all five rejected v30
119 claims now reaches pending terminal with unchanged arguments; the v29 63
API-only control remains accepted. No model, application, or evaluator ran in
that replay. Source seal: 259e8385510863e5608710f3276c2a9674a45f262b968069ad5e466ae6c3a5ea.
Next is one affected/control 119/63 run, not an integrated score or promotion.
The user's 30 GiB disk stop line and 100-step/1800-second limits remain in place.

## 2026-09-05 Path-Prefix Grammar Compatibility

The [path-prefix repair](archive/hybrid-path-prefix-grammar-repair-20260905.md)
fixes 24 existing schema literals after deployed xgrammar 0.2.4 proved unable
to generate complete paths under prefix-only patterns. No new gate, API,
argument conversion, or validator was added. All 170 focused tests and Ruff
passed. A single host-only replay returned a schema-valid workspace discovery
search in 9.128 seconds; no tool was executed and no task pass is claimed.
Source seal: 1168c55a939e48a6bf18bbe8080b7308c4108123f524c15b7919741afcd10549.
The source was changed only after v30's final checks and exit. Next: isolate
the GUI-completion mismatch recorded in v30, preserving API-only evidence
checks and Qwen's terminal audit. Disk stop line remains 30 GiB.

## 2026-09-05 Editor Discovery Affected-Control Retest v30

Registered [v30](archive/hybrid-editor-discovery-retest-v30-20260905.md) for
105 followed by previously passing Multi-Apps comparison 119. The source seal
is `45b2437001d899ca5879c8e2010574d26021bc56054bf447fdcf567f6ff995aa`.
One worker, one attempt each, Qwen/Holo thinking, 100 steps, 1800 seconds,
and 30 GiB remain unchanged. No pass is claimed at registration. This follows
a positive bounded next-action diagnostic, not an unchanged retry of v29.
Completed at 21:55:18Z with exit 0 and both final integrity checks ok: 105
failed at reward 0 in 42 events, and 119 failed at reward 0 in 37 events.
There were no terminal environment/transport/protocol/deadline failures;
119 had two recovered protocol errors. 105 found the workspace, read source,
wrote an equivalent comparison, and launched the program without fixing the
actual defect. 119's GUI completion was rejected five times for lacking an
Adapter mutation, followed by an API export that overwrote the earlier PNG.
The comparison is not stable and no integrated score or promotion is claimed.
The subsequent path-prefix repair is a distinct source condition.

## 2026-09-05 Editor-File Search Recall

The [feedback-only probe](archive/hybrid-repeated-error-feedback-repair-20260905.md)
returned the same bad path after correctly identifying workspace discovery in
its reasoning. Its preserved catalog query omitted that API. Adding one generic
editor keyword to workspace.find_files fixed six synthetic direct/forwarded
recall cases; all 131 related tests and Ruff passed. A separate one-request
[route-surface probe](archive/hybrid-editor-discovery-repair-20260905.md)
then returned a valid workspace.find_files call with all messages and other
tools unchanged. Neither probe executed its returned call or counted as an
Agent pass. Their complete negative/positive evidence and distinct source
seals are retained. No ranker, schema, gate, or application execution changed.

## 2026-09-05 Repeated-Request Original Error Retention

Completed v29 exposed loss of the original Adapter cause after an existing
request block. After process exit and final integrity ok, two field assignments
preserve previous_error through active-block state and later rejected events.
The [repair report](archive/hybrid-repeated-error-feedback-repair-20260905.md)
records two initially failing synthetic cases, 126 canonical plus two scratch
passing checks, Ruff/diff checks, and zero-network original-proposal replay.
No gate, retry, argument, or application behavior changed. This is not a new
Agent pass; a bounded next-action diagnostic should precede another long 105
attempt. The repair goal remains active and the disk stop line remains 30 GiB.

## 2026-09-05 Corrected Holo Feedback Launch v29

Registered [v29](archive/hybrid-holo-schema-feedback-retest-v29-20260905.md)
with v28's identical source seal, 105/63 selection, and thinking-mode settings.
The launch explicitly includes --thinking as well as --reasoning-mode thinking.
v28's startup-only invalid result remains immutable; no VM or model request
ran in that attempt. This corrects the launch command, not the validator.
Completed at 20:46:15Z, exit 0 and both final integrity checks ok: 105 failed
at reward 0 in 17 steps; 63 passed in 11 steps. All eight 105 Holo delegations
executed valid GUI actions, but repeated file/path choices prevented source
repair. Later request rejections dropped the original path error, repaired
only after this run finalized. No terminal environment/transport/protocol/
deadline failure, new affected pass, integrated score, or baseline promotion.

## 2026-09-05 Holo Feedback Affected-Control Retest v28

Registered [v28](archive/hybrid-holo-schema-feedback-retest-v28-20260905.md)
for affected 105 and prior passing control 63, runs=1 and one worker. Source
seal: `52ce088d85da5dc3d1f1c931ff7f6ed25985b77bb875ec9dee7f5bf32f3f0702`.
The newly demonstrated Holo rejection/feedback issue warrants one affected
replay; this is not another unchanged file-search retry. Qwen returns to the
established thinking mode after negative v27, Holo remains thinking, and
100 steps/1800 seconds/30 GiB are unchanged. No pass is claimed at registration.
The initial command omitted --thinking, so the supervisor rejected it at
20:28:55Z before worker/VM/model startup. Its two invalid_configuration entries
are not failed Agent episodes. Preserve v28 and use the explicitly corrected
v29 launch without any source or gate change.

## 2026-09-05 Holo And Nested-Schema Error Feedback

After v27 fully exited with final integrity `ok`, repaired two demonstrated
feedback losses: Holo's coordinate field/type error was reduced to an exception
class, and Calc's nested part error was reported as an outer kind/value choice.
The existing schema-hint helper now follows unambiguous type/enum/const branches
and gives plain-language duplicate-item feedback, also exposed by Writer v27.
The [Holo report](archive/hybrid-holo-error-feedback-repair-20260905.md) and
[nested-schema report](archive/hybrid-nested-schema-feedback-repair-20260905.md)
record initial failing cases, five retained regressions, 234 focused passing
tests, Ruff/diff checks, and original-response reconstruction without network
requests or execution. No gate, retry layer, argument rewrite, or task pass
was added. Next is a new sealed thinking-mode 105/63 affected/control check;
do not replay the negative Calc/Writer condition unchanged.

## 2026-09-05 Calc And Writer Combined Retest v27

Registered [v27](archive/hybrid-calc-writer-nonthinking-retest-v27-20260905.md)
for 23/76 and passing control 63, using source seal
`22256a554ecee7e597a40786abb7eb11b87e0263c9fdf6c533b5ddefc6f78532`.
This combines the two Calc feedback fixes with condition-local Qwen
non_thinking, motivated by the Writer offline probe and Calc output loops.
Holo remains thinking; the default condition is not changed. One worker,
runs=1, 100 steps, 1800 seconds, and 30 GiB are unchanged. This is neither a
mode-only comparison nor an integrated ten-task score; no pass is claimed yet.
Completed at 20:18:13Z, supervisor exit 0 and both final integrity checks `ok`.
23 failed at reward 0 after 56 steps and the time limit, retaining literal
Header in its combined values. 76 ended in model_protocol_failure after three
identical 309-token calls containing duplicate cells. 63 failed at reward 0 in
21 steps after selecting the wrong textbox/color mapping. No terminal transport
or environment failure occurred. This negative result and control regression
do not support a default non_thinking switch. Raw evidence and baseline pointers
remain unchanged; shared feedback defects were repaired only after finalization.

## 2026-09-05 Calc Recovery Surface And Matrix Positions

The completed v26 trajectory exposed an exclusive fill-down surface without
read/search and a protocol-recovery matrix sampled from both ends without
row identities. After final integrity passed, removed that exclusive branch,
made matrix compaction retain complete leading rows, and corrected partial-data
guidance. Existing completion checks, budgets, and execution are unchanged.
The [repair report](archive/hybrid-calc-fill-surface-repair-20260905.md) records
260 passing tests, Ruff, and original-trace reconstruction: 12 leading rows,
four intact columns, 5621 characters. No task pass is inferred. Next is a
separately sealed combined 23/76/63 non_thinking check, not a default switch.

## 2026-09-05 Calc Schema And Selection Retest v26

Reproduced Order 23's malformed formatted-text shape as two failing tests,
then added only the owning value/parts schema; execution and validation are
unchanged. The [repair report](archive/hybrid-calc-formatted-schema-repair-20260905.md)
records 90 focused passing tests and two serving-compiler checks. Synthetic
proposals still made reference/literal mistakes, so no task pass is inferred.
Registered [v26](archive/hybrid-calc-selection-retest-v26-20260905.md) for
23/29 plus passing control 63, with source seal
`6cbf8d166d9e9ee4d05ee2e8b7ce8f668f6d445cdb61dd47343efadeeafa7381`.
One worker, runs=1, thinking mode, 100 steps, 1800 seconds, and 30 GiB remain
unchanged. No pass is claimed at registration; existing results are immutable.
Completed with supervisor exit 0 and final worker/supervisor integrity `ok`:
63 passed in 13 steps; 29 failed at reward 0 after selecting the wrong portrait
image; 23 ended in model_protocol_failure after three length-truncated replies
at step 11. No terminal environment/transport failure and no new affected pass.
The Calc feedback defects found during this run are repaired under a new
source seal; v26's raw result and full-run numerator are unchanged.

## 2026-09-05 Offline Reasoning-Mode Probe

After v25 terminated, replayed its preserved Writer step 6 request exactly once
with only Qwen's binary thinking switch disabled. The response selected save
in 3.069 seconds with 18 completion tokens, instead of changing correct colors.
The [probe report](archive/hybrid-reasoning-mode-probe-20260905.md) retains the
request/response hashes and limits: host-only, no tool execution, no task pass.
A separate sealed affected/control trial is warranted, not a default-mode change.

## 2026-09-05 Image And Writer Feedback Retest v25

Registered an affected-only replay of 76/119 against preserved v22 failures,
using source seal `b27300eddf38323f9dae1a81ae944eb6c3159fb8bd91d0bf2ec06127ba427575`.
The [v25 report](archive/hybrid-image-feedback-retest-v25-20260905.md) records
the hypotheses before launch. Runs=1, one worker, 100 steps, 1800 seconds,
and 30 GiB are unchanged. Existing v22/v24 evidence remains immutable, and
no new pass is claimed at registration.
Completed with both final integrity checks `ok` and supervisor exit 0: 119
passed with reward 1 in 16 steps; 76 ended in model_protocol_failure after
three 4096-token length-truncated responses without a tool call. Writer's full
latest table result was retained; contradictory model classification is now
the remaining observed cause. The 119 pass is individual recovery evidence,
not a revised full-189 numerator or integrated ten-sample rate.

## 2026-09-05 Image Adjustment Repair

While v24 was frozen and running, traced Order 119's v22 image-brightness
searches to missing retrieval metadata and terse usage for existing GIMP
`image.adjust`. A separate synthetic test also reproduced deletion of an
in-place input before GIMP loads it. The [repair report](archive/hybrid-image-adjust-repair-20260905.md)
distinguishes the observed trajectory cause from the newly found file-handling
bug. After v24 terminated with final integrity `ok`, added existing-action
keywords, faithful typed usage, and one pre-cleanup source-collision check.
47 related tests, Ruff, and diff checks passed. The later sealed v25 replay
recovered Order 119, including model correction of the protected input/output
collision. Its separate Writer failure remains unresolved. The disk stop line
remains 30 GiB, and previous raw results were not changed.

## 2026-09-05 Search And Usage Retest v24

Registered affected-only replay of 105/112/94 with source seal
`3406706b1d88efc11eeb0ae3f66fd37a2d213049d1183a17a50abe28d7ab0f23`.
The [v24 report](archive/hybrid-search-usage-retest-v24-20260905.md) records
hypotheses and stop signals before launch. The planned 142 control was dropped
after the authoritative task list showed it is OS, not Multi-Apps; its original
score/domain remain unchanged. Runs=1, one worker, 100 steps, 1800 seconds,
and 30 GiB remain unchanged. No new pass is claimed at registration.
Completed with supervisor exit 0 and final worker/supervisor integrity `ok`:
105/112/94 all failed, at 11/11/37 steps respectively. No terminal environment,
protocol, or deadline failures occurred, although a truncated Qwen response
and rejected Holo calls were recovered during the episodes. This negative
result is preserved; move to 76/119 after the v23/v24 review checkpoint.

## 2026-09-05 Search Recall And Tool Usage Repair

After v23 completed with final worker/supervisor integrity `ok`, added generic
workspace-discovery keywords and clarified tool-search recovery, stdout saving,
literal argv paths, and launch-only status. No API, execution behavior, required
parameter, or gate changed. The [follow-up report](archive/hybrid-search-usage-repair-20260905.md)
records 134 focused passing tests, Ruff, and remaining Agent retest requirements.
The subsequent v24 affected replay recovered no new task pass; its report
distinguishes 94's execution-search improvement from its failed application result.

## 2026-09-05 Pending-Feedback Retest v23

Registered a new sealed condition for 105/112/94 and previously passing
comparison 63, using the latest-result, command-feedback, discovery, and usage
description repairs. Source seal:
`1f8294f8c7d54c56b664e6843668131df5e32152eeabd590984141b0c48d6154`.
The [v23 report](archive/hybrid-feedback-retest-v23-20260905.md) records the
hypotheses and stop signals before launch. One worker, runs=1, 100 steps,
1800 seconds, and a 30 GiB disk stop line remain unchanged. No pass is claimed
at registration; v20/v22 evidence and the full-run numerator are preserved.
Completed at 16:55:30Z with both final integrity checks `ok`: 63 passed,
105/112/94 failed, and no terminal protocol, environment, or deadline failures.
Latest errors and command output now survive, but no new task pass was recovered.
The final binary output in 112 and the missing execution search in 94 are
documented separately from the fixed feedback defects. Raw evidence is unchanged.

## 2026-09-05 Latest-Result Feedback Repair

During frozen v22, Order 76's saved recovery request omitted its latest color
read-back and subsequent rejected-call error. An audit marker plus prefix
truncation in `RuntimeStateCoreMixin.context_summary` removed the newest two
events; a synthetic seven-event example reproduced the loss without a model.
The [context-tail report](archive/hybrid-context-tail-repair-20260905.md) records
this, dropped results from unprojected forwarded APIs, and description
mismatches. After v22 completed, the repair retained the latest event tail,
reused bounded sanitized downstream results, and corrected command, wrapper,
and source-bitmap export descriptions. No gate or application behavior changed.
Checks: 339 related tests, Ruff lint, and real-trace reconstruction passed. The
new working source has not yet been model-retested and must not reuse v22's seal.

## 2026-09-05 Observation Repair Retest v22

Registered a new sealed affected-only condition for Orders 76/119/163 and
previously passing comparison 63, in that order. The source seal is
`0752d8180f3109835ea2f94ea3229141182b90840502ddc9f40fbae07b9cd64e`.
The run retains one worker, runs=1, Qwen/Holo thinking, 100 steps, and 1800 seconds;
the authorized disk stop line is 30 GiB. No existing result directory is resumed.
The [v22 report](archive/hybrid-observation-retest-v22-20260905.md) records the
per-task hypotheses, expected observations, and stop signal before launch.
The run completed at 15:58:03Z with final worker/supervisor integrity `ok`:
63 passed; 119 failed with reward 0; 163 failed with unchanged reward
0.9897855178912893; 76 exhausted the Agent deadline without a reward. No terminal
protocol or environment failures occurred. Actual Writer color read-back and
removal of the unrequested VLC playback obligation were observed, but there was
no new recovered task pass. Raw evidence and the full-run numerator are unchanged.

## 2026-09-05 User-Authorized Disk Stop Line

The user requested lowering the disk stop line to 30 GiB. Changed only the
supervisor's `--min-free-gib` default from 100 to 30; the existing comparison,
worker-stop behavior, and CLI override remain unchanged. This supersedes the
earlier same-day storage hold for future runs, not the historical reports.
Verification covers default parsing and an explicit override. No experiment
was started, no storage was deleted, and a scored rerun still needs a new seal.

## 2026-09-05 Remaining-Sample Observation Repair

Continued with Orders 76/119/163/29/23/142 using preserved v20/v21 evidence.
Writer now returns observed whole-cell font colors; Impress preserves early
picture and text selectors together and advertises a zero-based `tool_target`
accepted by its image-export API. VLC no longer mistakes future media use for
an immediate playback requirement. The OS relative-path error explains that
home is not the current folder. Calc text-reference and Impress selection/export
usage were clarified without supplying formulas, selectors, or destinations.
Multi-Apps now retains the owning API's top-level usage description, previously
lost when constructing the forwarded parameter schema.

The original Order 119 context lost all three second-slide graphics; offline
reconstruction now retains all three in 11698 characters, and also in a
5979-character direct view. Order 29 selected the wrong square picture, and
Order 23 used literal placeholders after an invalid call was correctly rejected.
Order 163 scored 0.9897855178912893, not zero; no evaluator or encoder was tuned.

Checks: 304 focused tests, Ruff lint, and `git diff --check` passed. No new gates,
live experiments, or task passes. Available disk space fell to about 97 GiB,
below the existing 100 GiB stop line; no storage was deleted. See the
[remaining-failure report](archive/hybrid-remaining-failures-repair-20260905.md)
for per-task causes, changed files, limitations, and pending affected-only replay.
The frozen full-189 numerator and promoted baseline pointer remain unchanged.

## 2026-09-05 Failed-Task Feedback Repair

Continued the ten-task repair queue with preserved v20/v21 evidence. Order 112's
failed command returned usage text, but the next model request discarded its
inner `COMMAND_FAILED`, return code, and stderr. The existing 1200-character
error projection now prioritizes those diagnostics over wrapper metadata.
Both failure summaries recognize the Multi-Apps error envelope, and ordinary
`unexpected` wording is no longer filtered as benchmark metadata. Successful
`command.run` observations now retain bounded stdout/stderr as well as their
lengths and truncation flags. VS Code missing-file errors and read schemas
explain model-selected `workspace.find_files` discovery without guessing roots.

Focused checks: 144 tests passed; Ruff and `git diff --check` passed. Offline
reconstruction of Order 112's actual next request retained its complete usage
text in 1189 error characters. Reconstructions of Orders 94/112 retained the
previously omitted successful command output. These are deterministic repair
checks, not new task passes. No gates, completion requirements, or model-selected
arguments were added or changed.

v20 remains `2 passed / 5 failed / 1 deadline / 2 protocol failures`. v21 remains
stopped with `2 failed / 1 interrupted / 2 not_run`, without final integrity
attestation. No new live condition was launched: the filesystem had about
101 GiB available against the existing 100 GiB supervisor stop line. The
[repair report](archive/hybrid-feedback-repair-20260905.md) records evidence,
remaining issues, and the next affected-only verification. The fixed-189
numerator and promoted v337 pointer remain unchanged.

## 2026-09-04 Post-Fix Environment Retest

After commit `e429808` (protocol, transport, and VM readiness repair), the
independent live retests covered all four historical environment failures.
The concurrent one-step smoke for Orders 6/149 and the deployment smoke for
Orders 105/129 all reached fresh-VM readiness, setup, model entry, and cleanup
with `environment_failure=0`. The full-budget follow-up used a new frozen
condition and result directory:

`experiments/qwen35-holo31-hybrid-environment-full-retest-e429808-20260904-run1`

It ran Orders 6, 105, 129, and 149 once with one worker, 100 steps, and a
1800-second Agent budget. Results were Order 129 passed, Order 149 passed,
Order 105 stalled with a guest path/verification mismatch, and Order 6 hit
the Agent deadline after recoverable protocol and application-layer timeout
events. The final worker counters were `2 passed / 1 failed / 1 deadline`,
`0 environment_failure`, `0 model_protocol_failure`, `0 model_transport_failure`,
`0 agent_failure`, and `0 invalid_configuration`. This is repair evidence only;
it is non-promotable and does not change the fixed-189 numerator or v337
baseline pointer.

## 2026-09-03 Hybrid Failure Repair: Protocol, Transport, And Environment

The fixed-189 hybrid run was stopped cleanly after the worker snapshot reached
`102/189` tasks: `44` passed, `20` evaluator failures, `14` agent deadlines,
`10` model protocol failures, `13` model transport failures, and `1` environment
failure. The top-level aggregate was stale; the counts above come from the six
preserved worker result files. No old result, baseline pointer, or frozen
condition was resumed or rewritten. The complete repair note is in the
[hybrid failure repair report](archive/hybrid-failure-repair-20260903.md).

The protocol failures were mostly zero-call `finish_reason=length` responses at
the 4096-token limit, plus a below-minimum Calc zoom and a missing geometry
branch in `shape.set_geometry`. Recovery now keeps its compact projection across
an intervening transport timeout, raises the output budget only for an explicit
truncation recovery (minimum 8192, never for ordinary turns), and renders
schema-authored numeric and undiscriminated-union constraints directly.

Transport diagnosis found 94 timeout attempts at the frozen 240-second limit,
one HTTP 500 caused by a negative-lookahead path pattern, and one local safety
false positive caused by joining adjacent serialized fields. The two maintained
path schemas now use a guided-schema-compatible pattern; runtime canonical root
checks remain in place; and strict surface checks inspect structured string
leaves. The next frozen condition must restore both healthy Qwen endpoints with
six workers (three workers per endpoint); the stopped one-endpoint condition is
not reusable.

The sole environment failure occurred before any model or Adapter call when VM
screenshot readiness exceeded 300 seconds during concurrent cold starts. The
Docker provider now retries only that `TimeoutError` with one fresh-container
rebuild, cleaning container and port state between attempts; other exceptions
remain fail-fast.

Focused checks and the complete active suite passed: `1110` tests under
`tests/`, `ruff check`, `compileall`, and `git diff --check`. A bare repository
root `pytest -q` still collects historical evaluator/cache and vendored OSWorld
tests that require unavailable optional SDKs or a display; those files are
outside the active suite and were not modified.

## 2026-09-03 Oversized Public Action Decomposition

The active v2 surface now composes previously oversized application workflows from
model-selected actions owned by the relevant Adapter. Calc's compound range and
table helpers, Writer's document-generation and paragraph macros, Impress's
semantic cleanup and slide-creation helpers, OS's recursive/batch filesystem,
conversion, desktop, terminal, and PDF helpers, and the GIMP/VLC compound actions
were removed from public schemas, manifests, dispatch maps, and search catalogs.
Multi-Apps now exposes only the provenance-bound `adapter.call` transport; it no
longer republishes flat downstream facades. Replacements include explicit
`range.copy`/`range.set_scaled_display`, per-document or per-file operations,
`filesystem.set_permissions`, `document.convert`, read-only desktop/PDF
inspection, and one-range `pdf.pages.extract`. Historical implementation helpers
remain isolated and unreachable where incremental migration permits.

Focused decomposition checks passed `116` tests. The full active suite completed
with `1024 passed, 67 failed` (`1091` collected). All 67 failures are historical
tests in `test_batch_table_stage.py`, `test_clipboard_path_semantics.py`,
`test_composition_viability.py`, `test_contact_spreadsheet_semantics.py`,
`test_generic_completion_save_recovery.py`, and `test_spreadsheet_open_semantics.py`
that still expect retired Multi-Apps flat actions; restoring those actions would
violate the current generic-only surface. Excluding those legacy assertions, the
remaining suite passed `865` tests. Compileall, Ruff, and `git diff --check` also
passed. This is a source/refactor verification only; baseline pointers and frozen
experiment evidence are unchanged.

## 2026-09-02 Calc Open-Inspect-Save Contract A/B

The generic Multi-Apps spreadsheet handoff now requires a verified
`spreadsheet.inspect_current` bound to the same opened workbook before Calc
mutation or save. Offline parser, identity, Save-As, and flattened-route
checks passed, and the active v2 suite passed `896` tests.

In the frozen non-promotable run, control Order 91 passed with reward `1.0`
through `generic_api_only`. Affected Order 103 did perform the intended
GUI-open -> same-identity verified inspect -> model-selected `D5` write
sequence, so the pre-mutation gate held. It then repeated the write, used GUI
save attempts, and continued to create new save obligations; duplicate actions
and completion claims were rejected. The final model request timed out, leaving
Order 103 `agent_deadline_exhausted` with no evaluator reward. The condition
therefore passed `1/2` scheduled and converted `0/1` affected; metadata
`success_rate=1.0` is only the evaluator-terminal `1/1` denominator. This is
not a new pass, score, or baseline change, and the condition will not be
replayed unchanged. A post-run read-only queue rescan classified the 70
non-passing episodes as 41 with historical `clean_pass`, 28
`task_blocked`, and one remaining Order 136 that already has a recent
independent A/B pass. There is no uncovered, unexhausted generic contract
gap to run without a new condition or explicit scope. See the
[Calc open-inspect-save report](archive/calc-open-inspect-save-ab103-91-20260902.md).

## 2026-09-01 Hybrid Repair Queue Stop Review

The final hybrid non-pass review stopped without a new condition or live run. Order 65 provided credible offline
evidence of continued surface replay after `paragraph.apply_split_tabstop` had already produced the evaluator-relevant
state; later `paragraph.set_format` calls did not corrupt that state. A dedicated post-success module was fully
reverted because adversarial compound instructions repeatedly showed that it could take over the surface while
unrelated requested work remained. Post-revert verification passed `158` related tests and all `803` tracked active
tests; Ruff, compilation, and diff checks were clean.

Order 121 received the complete spreadsheet, including Stella's visible `Payment = No` row, but Qwen selected only
Fox, Iron, and Nancy. Because the read request carried no model-declared payment predicate, host-side derivation of the
missing recipient would replace a semantic model decision rather than perform declared representation conversion.
That candidate is no-go. In the final low-ranked set, removing Order 65 from `28` non-passes left `27`: `25` already
have historical `clean_pass` evidence, and Orders 87 and 93 are `task_blocked`. The higher-ranked remainder exposed no
unexhausted generic contract gap; Orders 3 and 63 already have dedicated A/B and successful capability evidence.

This repair slice is closed. It does not change the hybrid `119/189` full-run numerator or the promoted baseline
pointer. Reopen it only for new cross-task evidence, a new model condition, or an explicitly authorized newly scoped
experiment. See the [queue-stop report](archive/hybrid-repair-queue-stop-20260901.md).

## 2026-09-01 Hybrid Repair Reference And Source Recovery

The active failed-task repair goal now uses the Qwen-Holo hybrid full-189 condition rather than v337 as its task
queue. The preserved run completed 119/189 scheduled tasks (62.96%): 119 passed, 33 evaluator failures, 21 agent
deadlines, 12 model protocol failures, three environment failures, and one agent failure. Its metadata
`success_rate=78.29%` excludes the 37 abnormal terminal episodes and is not the full-denominator result. v337
remains the promoted older-architecture comparison; historical v210 is unrelated despite also recording 119/189.

The exact dirty source scope was recovered from Git tree `d37296fa4cfca83621240489012d43f2f1f8a9b9`, verified
against seal `a1dfe6a2bc6335bc09ef0fbc23349e9f8b1952145748735abea4943a8c422d12`, and made durable as commit
`88484bcea3238c53fec993eb312f7d9269ccda79` with tag
`archive/qwen35-holo31-hybrid-20260831-a1dfe6`. The current dirty worktree was not reset. As of this update,
isolated later runs contain per-task evidence for selected members of that queue. Those results use different source
seals and remain per-task evidence; they do not change the full-run numerator or define an aggregate score. See the
[current repair reference](current-repair-reference.md) for canonical links, hashes, and maintenance rules.
The Git tag does not carry the three LFS payloads; they are currently present only in the local `.git/lfs` store,
and this checkout has no configured remote. Run `git lfs fsck` and make an independent LFS backup before treating
the recovered source as portable.

## 2026-09-01 Terminal Show-Output Shell-Syntax A/B

The OS Adapter now rejects standalone shell operators in
`terminal.show_output.argv` at the same pre-execution boundary used by
`command.run`. The two actions share the exact-token validation but expose
action-specific recovery guidance, so `terminal.show_output` never advertises
redirection fields that its public schema does not accept. The model still
selects the complete argv and any replacement action. Offline verification
passed `9` focused tests, `32` related tests, and all `803` tracked active
tests; Ruff, compilation, formatting of the new files, and diff checks were
clean.

In the frozen live condition, affected order 146's first pipe-bearing call was
rejected in 1.277 seconds with HTTP 422 `SHELL_SYNTAX_UNSUPPORTED`,
`executed=false`, no logs, and byte-identical before/after screenshots. This
removed the preserved trajectory's approximately 57.9-second side-effecting
timeout. Qwen then returned three full-length HTTP-200 responses without any
structured tool call, so the affected task ended `model_protocol_failure`,
reward `null`, without GUI, terminal execution, or evaluator. The repeated
protocol failure fired the stop signal; this condition will not be replayed
unchanged.

Control order 118 recovered from two blocked duplicate captures, successfully
used `terminal.show_output`, captured the confirmed visible terminal after the
result, and remained `passed`, reward `1.0`, `generic_api_only`. The condition
therefore passed `1/2` scheduled and `0/1` affected. Metadata
`success_rate=1.0` is only the evaluator-terminal `1/1` denominator, not a new
affected pass or score improvement. The pre-side-effect rejection is retained
as generic integrity evidence; it does not change the hybrid `119/189`
reference or the v337 baseline pointer. See the
[shell-syntax report](archive/terminal-show-shell-syntax-ab118-146-20260901.md),
[condition](../experiments/configs/qwen35-terminal-show-shell-syntax-ab118-146-20260901.json),
and [immutable result](../experiments/qwen35-terminal-show-shell-syntax-ab118-146-20260901-run1/).

## 2026-09-01 Writer Paragraph-Spacing Representation A/B

Writer's shared `paragraph.replace_text` and `document.append_paragraphs`
contracts now reject a positive automatic paragraph gap combined with any
empty or whitespace-only paragraph string. The model-visible structured schema
and defensive Adapter validation describe the two legal representations; no
sentence macro, text injection, Writer UNO change, or Runner change was added.
Offline verification included `41` focused tests in the implementation check,
`25` focused tests plus all `794` tracked active tests in main verification,
and a separate independent `25`-test run with schema/runtime/parser parity and
invalid-case matrices. Ruff, formatting, compilation, and diff checks were
clean.

In the frozen live condition, affected order 77 still ended
`model_protocol_failure`, reward `null`, on the `generic_api_only` route. At
step 2 Qwen repeated the same invalid `paragraph.replace_text` three times:
`13` items containing six explicit blank strings plus
`blank_paragraphs_between=1`. Each attempt failed model-visible validation
with `StructuredToolProtocolError` at `paragraphs.1/3/5/7/9/11` against
pattern `\S`. None was parsed, forwarded to the Adapter, or mutated; beyond
the initial inspect there was no save or final read-back, GUI call, evaluator,
or restart. The repeated conflict fired the stop signal, so this pair will not
be replayed unchanged.

Control order 80 remained `passed`, reward `1.0`, and `generic_api_only` in
nine events plus terminal audit at review step 10. It had no GUI, restart,
rejection, or completion rejection; read-back showed three 12 pt paragraphs
with line spacing `1`, `2`, and `1.5`, followed by save and evaluator reward
`1.0`. Its additional Times New Roman setting was non-blocking. The condition
passed `1/2` scheduled and `0/1` affected. Metadata `success_rate=1.0` describes
only the evaluator-terminal denominator (`1/1`), not a two-task result or a new
affected pass. Exact text-fidelity risks around `our`/`your`, quotation marks,
and `If...! So...` remain untested because order 77 never mutated the document.

This stopped, non-promotable condition does not change the hybrid `119/189`
repair reference or the v337 baseline pointer. See the
[paragraph-spacing report](archive/writer-paragraph-spacing-ab77-80-20260901.md),
[condition](../experiments/configs/qwen35-writer-paragraph-spacing-ab77-80-20260901.json),
and [immutable result](../experiments/qwen35-writer-paragraph-spacing-ab77-80-20260901-run1/).

## 2026-09-01 Calc Range-Write Formula-Error Rollback A/B

The Calc Adapter now treats a nonzero UNO error from a model-submitted
`formula` or `formatted_text` cell in `range.write` as `FORMULA_ERROR`. Before
such a write it snapshots the complete target range; on a formula error or
later write/read-back exception it strictly restores content and style and
recalculates. Formula-like literal strings are identified by their UNO cell
type rather than their leading `=`, so rollback does not turn them into
formulas. The model still owns every value and any replacement representation.

Offline validation passed `31` related tests and all `776` tracked active
tests; Ruff, formatting, compilation, and diff checks were clean. In the
frozen live condition, order 5's step 15 invalid formula produced UNO error
`509`, returned `FORMULA_ERROR` with `executed=false`, and the step 17 and 22
reads both proved that `D1` remained the prior literal string with a blank
formula field. The model nevertheless repeated the same bad formula at step
20, then submitted two invalid `formatted_text` shapes at steps 21 and 23. It
also used two read-only GUI clicks and finally exhausted the agent deadline.
The affected result is therefore still `agent_deadline_exhausted`, reward
`null`, and `api_plus_gui`; it is not a new pass and will not be replayed
unchanged.

Control order 25 remained `passed` with reward `1.0` and
`generic_api_only`, despite 22 episode steps, terminal audit, one same-VM soft
restart, and six completion rejections. The result metadata's
`success_rate=1.0` uses only the evaluator-terminal denominator (`1/1`); by
the two scheduled tasks the condition is `1/2`, and the affected metric is
`0/1`. The rollback mechanism is retained as integrity evidence, while
`cells.set_formulas` and purely non-formula writes remain separate residual
scopes. The malformed recovery attempts also expose a distinct model-facing
schema gap: `formatted_text.value` describes `{parts: [...]}` only in prose,
so structurally wrong arrays passed model-call validation and failed only
inside the Adapter.

This stopped condition does not change the hybrid `119/189` reference or the
v337 baseline pointer. See the
[formula-error rollback report](archive/calc-range-write-formula-error-ab5-25-20260901.md),
[condition](../experiments/configs/qwen35-calc-range-write-formula-error-ab5-25-20260901.json),
and [immutable result](../experiments/qwen35-calc-range-write-formula-error-ab5-25-20260901-run1/).

## 2026-09-01 Calc Stacked-Pivot Destination Conflict A/B

The preserved hybrid order 24 trace correctly created a merged, formatted
title at `Sheet2!A1:C1`, then selected an explicit `A1` destination for its
first pivot. The Calc Adapter avoided only existing DataPilot outputs, so it
overwrote the ordinary title and completion still accepted the historical
title action. A generic Adapter-level safety contract now rejects an actual
stacked-pivot destination occupied by ordinary content or a merged range. It
checks every final destination after gap adjustment, preserves existing
pivot-owned append semantics, rolls back a partially created batch on a later
conflict, and never supplies a replacement destination.

Offline validation passed `34` related tests and all `766` tracked active
tests; Ruff, formatting, compilation, diff checks, and independent review were
clean. In the frozen one-run condition, affected order 24 selected
`placement="below_existing_content"` for all three pivots and changed from
reward `0` to evaluator `passed` (`1.0`). The evaluated workbook retained the
merged blue title with bold white text, placed the percentage pivots at
`A2:B5`, `A7:B11`, and `A13:B17`, and preserved the required blank rows.
Same-contract Calc control order 4 retained reward `1.0` through the sibling
stacked-aggregate action. Neither task used GUI or incurred a completion
rejection, and all model arguments matched Adapter payloads.

This is one isolated per-task pass, not an aggregate recomputation. The hybrid
reference remains `119/189` and the v337 baseline pointer is unchanged. See
the [pivot destination report](archive/calc-pivot-destination-conflict-ab24-4-20260901.md),
[condition](../experiments/configs/qwen35-calc-pivot-destination-conflict-ab24-4-20260901.json),
and [immutable result](../experiments/qwen35-calc-pivot-destination-conflict-ab24-4-20260901-run1/).

## 2026-09-01 VS Code Workspace-Open Target A/B

The preserved hybrid order 175 trace first opened `~/`, then opened
`/home/user/project` while retaining both the old `user` window and the new
`project` window. Completion passed, but the evaluator later activated the old
window and returned reward `0`. A new conservative VS Code semantic contract
binds an explicit folder/project/workspace target and its named ancestor
hierarchy to the model-selected path and the verified Adapter-observed path.
It rejects mismatched paths before execution without injecting or rewriting
arguments, and it fails closed on ambiguous, file/UI, negated, or multi-target
instructions.

Offline validation passed `72` focused tests and `755` tracked active tests;
Ruff, formatting, compilation, and diff checks were clean. The first live
invocation was preserved as `invalid_configuration` because the CLI omitted
the frozen thinking flag before any model request. The bounded retry corrected
only that invocation. Affected order 175 then passed (`1.0`) in two steps:
the first model call selected `/home/user/project`, the exact payload reached
the Adapter, verification reported one `project` window, terminal audit
passed, and the evaluator artifact contained `project`. Stable same-domain
control 187 also passed (`1.0`), recovering from one transport timeout through
the configured model retry. Neither task used GUI or incurred a completion
rejection.

This is a new isolated per-task pass, not a recomputed aggregate. The hybrid
reference remains `119/189` and the v337 baseline pointer is unchanged. See
the [workspace-open target report](archive/vscode-workspace-open-target-ab175-187-20260901.md),
[retry condition](../experiments/configs/qwen35-vscode-workspace-open-target-ab175-187-20260901-retry1.json),
and [immutable retry result](../experiments/qwen35-vscode-workspace-open-target-ab175-187-20260901-retry1-run1/).

## 2026-09-01 Clipboard Path Final-State A/B

The preserved hybrid order 110 trace found
`/home/user/Data3/List3/secret.docx` and successfully wrote that observed path
to the clipboard, then overwrote it with the document contents. Completion
incorrectly accepted the historical correct write and the evaluator returned
reward `0`. A generic `multi_apps`/`os` workflow now stages explicit
find-path-to-clipboard requests as discovery, exact model-selected clipboard
write, and terminal audit. The argument and completion contracts require a
successful prior observed path and verify that the latest clipboard write
still contains it; no path or action is injected.

Offline validation covered parser counterexamples, other domains, event
ordering, direct and wrapped calls, wrong values, destructive overwrite,
recovery, terminal audit, and argument immutability. The new test file passed
`33` tests, the related set passed `152`, and the tracked active suite passed
`683`; Ruff, compilation, formatting, and diff checks were clean.

In the frozen one-run condition, affected order 110 changed from reward `0`
to evaluator `passed` (`1.0`) in three events: `filesystem.find`,
`clipboard.set` with the exact returned path, and `propose_done`. Its four
model requests saw only the staged tool for that phase, followed by terminal
controls; there was no search, GUI use, retry, completion rejection, or later
overwrite. Stable same-domain control order 94 remained passed (`1.0`). This
is a new isolated per-task pass, not a recomputed aggregate: the hybrid
reference remains `119/189` and the v337 baseline pointer is unchanged. See
the [clipboard final-state report](archive/clipboard-path-final-state-ab94-110-20260901.md),
[condition](../experiments/configs/qwen35-clipboard-path-final-state-ab94-110-20260901.json),
and [immutable result](../experiments/qwen35-clipboard-path-final-state-ab94-110-20260901-run1/).

## 2026-09-01 Impress Audio Routing A/B

The preserved hybrid order 31 trace lacked the public `audio.insert` action in
its initial strict route, used Holo GUI delegation, and exhausted its deadline.
The strict Impress route now recognizes an instruction that names one Desktop
audio file and explicitly asks to insert it into a presentation. Route,
completion, and stateful validation share that generic predicate; the model
still owns the slide, geometry, and path representation, and GUI mutation does
not satisfy the Adapter-backed completion gate.

Offline validation passed (`108` focused tests plus Ruff, compilation, and diff
checks). In the frozen one-run condition, affected order 31 and stable control
33 both received evaluator reward `1.0`. Order 31 is therefore a new isolated
pass relative to the hybrid non-pass queue, but the pre-registered direct-route
metric failed: it ran 30 steps, was not terminated by the Agent, and used GUI
fallback after every `audio.insert` API attempt returned `FILE_NOT_FOUND`.
The public schema accepted a basename and a valid local file URL, while the
worker mishandled the file URL as `file:/home/...`. This condition is stopped
and will not be replayed unchanged; the audio path contract is a separate
candidate. The hybrid reference remains `119/189`, and the v337 baseline
pointer is unchanged. See the
[Impress audio routing report](archive/impress-audio-routing-ab31-33-20260901.md),
[condition](../experiments/configs/qwen35-impress-audio-routing-ab31-33-20260901.json),
and [immutable result](../experiments/qwen35-impress-audio-routing-ab31-33-20260901-run1/).

## 2026-09-01 Filesystem Copy Completeness A/B

The preserved hybrid order 142 trace found four JPG files, copied three, and
then passed completion. A generic strict completion check now compares the
successful model-selected copy sources with the complete successful
`filesystem.find` collection and fails closed for a missing source. It does
not inject paths or rewrite arguments; direct and `adapter.call` forms are
covered by focused tests.

In the one-run exploratory condition, affected order 142 changed from the
hybrid failure (reward `0`) to evaluator `passed` (reward `1.0`), while stable
same-domain control order 148 remained passed (`1.0`). The affected model
found all four files and selected four copy calls, so the new rejection branch
was not reached live; the causal contract evidence is the offline replay of
the preserved three-of-four event set. Focused validation passed (`148` tests)
with Ruff, formatting, compilation, and diff checks clean. This is one
positive per-task result, not a new aggregate score: keep the hybrid reference
at `119/189` and leave the v337 baseline pointer unchanged. See the
[filesystem copy completeness report](archive/filesystem-copy-completeness-ab142-148-20260901.md),
[condition](../experiments/configs/qwen35-filesystem-copy-completeness-ab142-148-20260901.json),
and [immutable result](../experiments/qwen35-filesystem-copy-completeness-ab142-148-20260901-run1/).

## 2026-09-01 Impress Background Readback A/B

An unnumbered Impress background instruction could select
`slide.set_background(all_slides=true)`, but the completion checker treated
the missing instruction slide number as a single `None` target. It therefore
reported a false read-back mismatch after a verified all-slide mutation. The
generic checker now recognizes the model-selected all-slide scope and
requires a complete inspected slide inventory (including a matching
`slide_count` when supplied); numbered instructions remain fail-closed.

Focused Impress, boundary, projection, and composition validation passed
(`176` tests), with Ruff, compilation, and diff checks clean. In the frozen
one-run exploratory condition, affected order 42 and control order 33 both
passed (`2/2`); order 42 completed the background mutation, save, and final
inspection without a repeated background action. Model arguments matched
Adapter payloads exactly, and no task identity or evaluator data entered
model requests. This is positive non-promotable evidence; v337 and its
baseline pointer remain unchanged. See the
[A/B report](archive/impress-background-readback-ab33-42-2026-09-01.md),
[condition](../experiments/configs/qwen35-impress-background-readback-ab33-42-20260901.json),
and [raw results](../experiments/qwen35-impress-background-readback-ab33-42-20260901-run1/).

## 2026-08-31 Contact Export Verb Routing A/B

The generic contact-to-CSV detector recognized only the bare verbs `export`
and `save`. Instructions using ordinary inflections such as `exporting` were
therefore routed without `contacts.export_csv`, even though the requested
workflow was otherwise explicit. The detector now accepts bounded export/save
inflections while retaining the contact-and-CSV requirements; no arguments or
task data are synthesized. The change is committed as `48ed105`.

In the corrected one-run affected/control condition, order 90 changed from
the preserved `stalled_no_progress` failure to evaluator `passed` (`1.0`),
and same-domain control order 91 remained `passed` (`1.0`). The first model
call selected `contacts.export_csv`, followed by
`spreadsheet.convert_file`; both calls reached the Adapter with exact model
arguments and verified outputs. Focused and related checks passed (`169`
tests), with no leakage or argument-rewrite findings. This is strong but
still exploratory evidence; v337 and the baseline pointer are unchanged.
See the [A/B report](archive/contact-export-verb-ab90-91-2026-08-31.md),
[condition](../experiments/configs/qwen35-contact-export-verb-ab90-91-20260831-retry1.json),
and [raw results](../experiments/qwen35-contact-export-verb-ab90-91-20260831-retry1-run1/).

## 2026-09-01 Impress Selector Equivalence A/B

The Impress selector matcher now accepts exactly one model-selected `index` or
`path` when both identify the same shape in the preceding inspection. Wrong,
extra, and conflicting selector fields remain rejected, and the original model
arguments are preserved. Focused Impress validation passed (`39` tests).

The exploratory affected/control run for orders 61/42 produced `0/2` passes:
both episodes exhausted the agent deadline, and the previously passing control
42 regressed in this condition. Order 61 nevertheless exercised verified
`index`/`path` alias calls and reached the Adapter without argument rewriting.
This is a behavior signal only; the condition is stopped and is not promotable
or eligible for an unchanged replay. See the
[A/B report](archive/impress-selector-equivalence-ab42-61-2026-09-01.md),
[condition](../experiments/configs/qwen35-impress-selector-equivalence-ab42-61-20260901.json),
and [raw results](../experiments/qwen35-impress-selector-equivalence-ab42-61-20260901-run1/).

## 2026-08-31 Chmod Tree Convergence A/B

Order 147 exposed a dynamic-directory race in `filesystem.chmod_tree`: a file
could disappear between enumeration, chmod, and verification, producing HTTP
500 and an unbounded retry response. The OS Adapter now uses at most three
regular-file convergence passes, tolerates only `FileNotFoundError` races,
strictly verifies every surviving file, leaves directories and symbolic links
unchanged, and bounds result samples while preserving full counts.

In the one-run affected/control condition, order 147 changed from `agent_failure`
to `passed` (`1.0`) in two steps. Its exact model-selected call verified three
files at `0644` with no HTTP 500. The live tree did not lose an entry, so dynamic
race behavior remains counterfactual-test evidence. Control order 148 regressed
to `model_protocol_failure` after three token-limit `propose_done` calls encoded
`evidence` as a string instead of the required string array, despite both
filesystem actions succeeding. The source-path improvement added one pass, but
the control regression rejects this condition for promotion and it will not be
replayed unchanged. See the
[A/B report](archive/chmod-tree-convergence-ab147-148-2026-08-31.md),
[condition](../experiments/configs/qwen35-chmod-tree-convergence-ab147-148-20260831.json),
and [raw results](../experiments/qwen35-chmod-tree-convergence-ab147-148-20260831-run1/).

## 2026-08-31 Terminal Capture Handoff A/B

Order 118 exposed a generic completion dependency defect: the policy could
combine an old `window.capture` result with a later `terminal.show_output`, so
the episode could finish even when the saved PNG showed a different terminal
window. Completion now requires an ordered, verified handoff from
`terminal.show_output` to a later capture of the same Adapter-confirmed window,
while preserving the model-selected title and destination unchanged.

In the one-run affected/control condition, order 118 changed from evaluator
failure to `passed` (`1.0`), and stable order 94 remained `passed` (`1.0`). The
existing missing-action gate rejected completion before `terminal.show_output`;
after that action succeeded, the model proactively captured its exact returned
window before retrying completion. The two changed calls matched their Adapter
payloads exactly, all model audits completed, and the condition finished `2/2`.
The new reversed-order and wrong-window rejection branches are covered by
focused counterfactual tests. Focused and related validation passed (`43
passed`). This is positive non-promotable evidence and leaves v337 unchanged.
See the [A/B report](archive/terminal-capture-handoff-ab94-118-2026-08-31.md),
[condition](../experiments/configs/qwen35-terminal-capture-handoff-ab94-118-20260831.json),
and [raw results](../experiments/qwen35-terminal-capture-handoff-ab94-118-20260831-run1/).

## 2026-08-31 Command Output Conflict A/B

Order 116 exposed a destructive generic cross-field defect:
`command.capture_output` could redirect stdout onto an existing input file in
`argv`, truncating the source before the command began. The OS Adapter now
rejects exact, normalized relative, symbolic-link, and hard-link aliases before
spawn; the public OS and Multi-Apps schemas explain the rule, and legacy
self-overwrite events no longer satisfy source-execution completion evidence.

In the one-run affected/control condition, order 116 changed from the preserved
evaluator failure to `passed` (`1.0`), while stable order 94 remained `passed`
(`1.0`). The affected model selected `bubbleSort.py -> res.txt` directly,
captured and read back 35 output bytes, and retained a non-empty 741-character
source. Because live execution did not attempt the forbidden alias, the runtime
`OUTPUT_CONFLICT` branch is established by focused same-path, relative,
symbolic-link, and hard-link tests rather than claimed as live evidence. The
condition finished `2/2`; focused and related validation passed (`17 passed`).
The one-time relevant module and boundary suite then passed (`146 passed`). This
is positive non-promotable evidence and leaves v337 unchanged. See the
[A/B report](archive/command-output-conflict-ab94-116-2026-08-31.md),
[condition](../experiments/configs/qwen35-command-output-conflict-ab94-116-20260831.json),
and [raw results](../experiments/qwen35-command-output-conflict-ab94-116-20260831-run1/).

## 2026-08-31 Save As Completion Contract A/B

Order 34 exposed a narrow generic completion gap: the policy excluded every
save action from task-changing evidence, so even a model-selected Save As with
an Adapter-confirmed new URL could never complete. The policy now recognizes a
Save As only when the immutable ledger proves an explicit model destination, a
successful exact-URL Adapter result with positive size, and an earlier
inspection with a different document URL. Same-URL saves remain persistence
only, and post-save structural read-back is still mandatory.

In the one-run affected/control condition, order 34 changed from the preserved
failure to evaluator `passed` (`1.0`), and same-domain control order 42 remained
`passed` (`1.0`). The affected task's first completion claim was correctly
rejected until the model performed a structural read-back of the new URL. Both
terminal audits completed, no argument rewrite or injection occurred, and the
condition finished `2/2`. Focused completion tests passed (`54 passed`). This
supports the narrow hypothesis but remains non-promotable; v337 and the
string-only completion evidence schema are unchanged. See the
[A/B report](archive/save-as-completion-ab34-42-2026-08-31.md),
[condition](../experiments/configs/qwen35-save-as-completion-ab34-42-20260831.json),
and [raw results](../experiments/qwen35-save-as-completion-ab34-42-20260831-run1/).

## 2026-08-31 Completion Event Evidence A/B

Four preserved failures submitted successful Adapter events as objects in
`propose_done.evidence`, while the public completion schema accepted only
strings. A bounded object contract removed that exact protocol blocker on
affected order 34: its model-selected object passed unchanged and reached the
existing completion gate. The task still ended `agent_deadline_exhausted`
because save-as was not classified as a task-changing action.

The stable order 42 control regressed to `model_protocol_failure` after Qwen
emitted a different object layout, with `executed=true` nested inside `result`.
The condition added no pass (`0/2`), so the object-evidence hypothesis is
rejected and the candidate schema was removed rather than broadened. See the
[negative A/B report](archive/completion-event-evidence-ab34-42-2026-08-31.md),
[condition](../experiments/configs/qwen35-completion-event-evidence-ab34-42-20260831.json),
and [raw results](../experiments/qwen35-completion-event-evidence-ab34-42-20260831-run1/).

## 2026-08-31 Nested Union Schema Hints A/B

Order 117 exposed a generic recovery-diagnostic gap: after the model selected
`mode=create`, the top-level schema error reported `archive_path` but omitted
the selected `oneOf` branch's required `input_paths`. Recovery now descends
only through a uniquely selected public-schema `const` branch; ambiguous unions
remain fail closed, and the Runner never supplies values or rewrites arguments.
Focused recovery/transport tests passed (`63 passed`), and the real exposed
archive schema now reports exactly `archive_path` plus `input_paths` for the
preserved incomplete call.

The first affected/control live check was blocked before any model request:
both order 91 and order 117 ended `environment_failure`. The root cause was a
guest packaging defect: the Multi-Apps service imported an OS Adapter helper
that its isolated systemd package did not install. A package-local runtime
guard plus an isolated `/health` import test restored guest self-containment
(`115` focused tests passed).

In a new-seal v2 replay, control order 91 reached evaluator `passed` (`1.0`),
confirming the deployment fix. Order 117 then received `archive_path` and
`input_paths` diagnostics on all three retries but still returned the identical
`{"mode":"create"}` call, ending `model_protocol_failure`. Thus the deployment
fix added a real pass relative to the blocked v1, while the nested-union hint
hypothesis added no affected-task pass and is rejected without further replay.
See the [A/B report](archive/nested-union-hints-ab117-91-2026-08-31.md),
[v2 condition](../experiments/configs/qwen35-nested-union-hints-ab117-91-20260831-v2.json),
and [v2 raw results](../experiments/qwen35-nested-union-hints-ab117-91-20260831-v2-run1/).

## 2026-08-31 Holo Non-Thinking A/B

The full-189 Holo trace showed long grounding failures clustered near the
`1024`-token output limit. A bounded affected/control condition therefore
changed only Holo from thinking to non-thinking; the main Qwen model remained
in thinking mode and all output and episode budgets stayed fixed.

Order 62 still failed (`0.0`), so this condition added no pass and stops without
promotion. Its Holo behavior did improve: four rejected calls fell from the
historical `84-108s` range to about `48s`, and a fifth call returned and
executed a legal scroll in `6.875s`; the episode later stalled on selector and
repeat-save errors. Control order 156 remained passed (`1.0`) but completed by
the generic API path without invoking Holo, so it is not evidence of Holo-path
equivalence. See the [A/B report](archive/holo-nonthinking-ab062-156-2026-08-31.md),
[condition](../experiments/configs/qwen35-holo-nonthinking-ab062-156-20260831.json),
and [raw results](../experiments/qwen35-holo-nonthinking-ab062-156-20260831-run1/).

## 2026-08-31 Mail Selector Contract A/B

Order 122 exposed a generic selector representation mismatch: a Thunderbird
message with no `Message-ID` was returned as `message_id: ""`, although the
same query row had a valid `mailbox_index` and the attachment contract rightly
rejects empty IDs. Query/result projections now omit absent IDs, preserve the
index-only path, and keep non-empty ID validation strict. Focused selector and
boundary tests passed (`104` plus `45`).

The first one-run affected/control replay was inconclusive because order 122
failed during Multi-Apps deployment before any model call; stable order 148
remained `passed` (`1.0`). After restoring isolated guest packaging, a new-seal
v2 replay exercised the changed path. The query row exposed only
`mailbox_index:0`; the model eventually selected that exact index without a
`message_id`, and the unchanged call saved and verified the attachment. This
removed the preserved selector protocol blocker and met the pre-registered
behavior metric.

Order 122 still ended `agent_deadline_exhausted` before completing the workbook
update, so the change added no evaluator pass. Control order 148 again remained
`passed` (`1.0`). The selector hypothesis therefore stops with a clear behavior
improvement but no promotion claim or further replay. See the
[A/B report](archive/mail-selector-ab122-148-2026-08-31.md),
[v2 condition](../experiments/configs/qwen35-mail-selector-ab122-148-20260831-v2.json),
and [v2 raw results](../experiments/qwen35-mail-selector-ab122-148-20260831-v2-run1/).

## 2026-08-31 LiteAgent SDK Retry Bound A/B

Full-189 deadline traces showed hidden OpenAI SDK retries continuing after the
Runner's 900-second episode budget. The LiteAgent model client now sets
`max_retries=0`, leaving bounded retries to the Runner and restoring a
one-logical-request/one-SDK-attempt boundary.

In a new affected/control replay, prior-deadline order 2 changed from
`agent_deadline_exhausted` at `1016.845s` to evaluator `passed` (`1.0`) at
`456.532s`; stable order 148 remained `passed` (`1.0`). The affected trace had
zero SDK retry log lines, while outer Runner retries remained auditable.
Focused transport and protocol validation passed (`23 passed`). This supports
the Qwen LiteAgent transport hypothesis but is non-promotable; the Holo client
and v337 baseline are unchanged. See the [A/B report](archive/sdk-retry-bound-ab002-148-2026-08-31.md),
[condition](../experiments/configs/qwen35-sdk-retry-bound-ab002-148-20260831-thinking-mode.json),
and [raw results](../experiments/qwen35-sdk-retry-bound-ab002-148-20260831-thinking-mode-run1/).

## 2026-08-31 GUI Repeat Normalization A/B

The numeric-string A/B removed a direct GUI type blocker but exposed a second
generic issue: quoted and numeric coordinates could evade duplicate-action
comparison. Internal repeat detection now uses the same bounded representation
normalization as command construction, while raw model arguments remain
unchanged and delegated Holo requests retain their coordinate-free path.

In the affected/control replay, order 124 produced four normalized
`RepeatedActionBlocked` events and switched to search/other-image actions, a
clear recovery-path improvement, but still ended `stalled_no_progress` after
issuing no-op `filesystem_move` calls; evaluator reward remained `0`. Stable
order 148 remained `passed` (`1.0`). This is non-promotable exploration
evidence; v337 and prior result directories remain unchanged. See the
[A/B report](archive/gui-repeat-normalization-ab124-148-2026-08-31.md),
[condition](../experiments/configs/qwen35-gui-repeat-normalization-ab124-148-20260831-thinking-mode.json),
and [raw results](../experiments/qwen35-gui-repeat-normalization-ab124-148-20260831-thinking-mode-run1/).

## 2026-08-31 GUI Numeric String Contract A/B

Preserved direct-GUI failures showed a generic representation mismatch: Qwen
returned bounded `x/y/seconds` values as JSON strings while the public schema
required JSON numbers. The active GUI boundary now accepts only finite decimal
string representations for existing numeric fields, converts them to canonical
numbers for command construction, and preserves the raw model arguments in the
event ledger. The Holo coordinate-free request surface is unchanged.

In the affected/control replay, order 124's quoted-coordinate action executed
without a GUI schema rejection, but the model then repeated the same close-
window click and ended `stalled_no_progress` with evaluator reward `0`.
Stable order 148 remained `passed` (`1.0`). The representation blocker was
removed, but no affected-task pass was added; repeated-action convergence is a
separate hypothesis. Focused validation passed (`122 passed`). This is
non-promotable exploration evidence; v337 and all prior result directories
remain unchanged. See the [A/B report](archive/gui-numeric-string-ab124-148-2026-08-31.md),
[condition](../experiments/configs/qwen35-gui-numeric-string-ab124-148-20260831-thinking-mode-v2.json),
and [raw results](../experiments/qwen35-gui-numeric-string-ab124-148-20260831-thinking-mode-v2-run1/).

## 2026-08-31 Batch Cardinality Detector A/B

Full-189 order 108 exposed a generic detector false positive: nearby language
about reports and years was converted into an exact one-row-per-input
constraint, so a valid aggregate table was rejected before the Adapter. The
detector now requires a local, explicit one-record-per-input instruction and
keeps exact cardinality for genuine row-mapping requests.

In a new affected/control exploration, order 108 no longer received the
inferred `minItems=maxItems=10` schema and reached PDF extraction and later
planning, but still ended `agent_deadline_exhausted` during subsequent
convergence/grounding. Stable control order 91 remained `passed` (`1.0`).
Thus the protocol blocker was removed, but the task-level pass hypothesis was
not confirmed. Focused tests passed (`66 passed`). This is non-promotable
exploration evidence; v337 and all prior result directories remain unchanged.
See the [A/B report](archive/batch-cardinality-ab108-91-2026-08-31.md),
[condition](../experiments/configs/qwen35-batch-cardinality-ab108-91-20260831.json),
and [raw results](../experiments/qwen35-batch-cardinality-ab108-91-20260831-run1/).

## 2026-08-31 Impress Color Schema Contract A/B

Full-189 order 41 exposed a generic manifest/runtime mismatch: Impress runtime
color normalization accepted case- and whitespace-variant named colors, but the
model-facing `RGB_COLOR` schema accepted only lowercase spellings. The
Adapter-owned schema now shares the runtime's normalized named-color contract,
and the LiteAgent legacy color schema reuses that same definition.

In a new affected/control exploration, order 41 moved from
`model_protocol_failure` to evaluator `passed` (`1.0`) with the model-selected
`color: "Dark Red 2"` reaching the Adapter unchanged. Stable Impress control
order 42 remained `passed` (`1.0`). Both tasks were `generic_api_only`; no
argument rewrite or injection was observed. Focused contract and regression
tests passed (`39 passed`). This is non-promotable exploration evidence; v337,
the full-189 run, and all prior result directories remain unchanged. See the
[A/B report](archive/impress-color-schema-ab41-42-2026-08-31.md),
[condition](../experiments/configs/qwen35-impress-color-schema-ab41-42-20260831.json),
and [raw results](../experiments/qwen35-impress-color-schema-ab41-42-20260831-run1/).

## 2026-08-31 Audio Volume Schema Contract A/B

Full-189 order 136 exposed a generic source-of-truth defect: the OS Adapter
implemented and validated `audio.set_volume`, but its public manifest omitted the
action. LiteAgent consequently exposed only an opaque `params` wrapper, and the
model's valid intent could not reach the Adapter. The action is now declared in
the Adapter-owned manifest with top-level `percent` and optional `sink`; runtime
unknown-parameter validation and the model-facing catalog are kept in parity.

In a new affected/control exploration, order 136 moved from
`model_protocol_failure` to evaluator `passed` (`1.0`), while stable OS control
order 148 remained `passed` (`1.0`). The model selected `percent=100`, the Adapter
verified both default sink channels at 100%, and no argument rewrite or injection
was observed. Focused contract and regression tests passed (`69 passed`). This is
non-promotable exploration evidence; v337 and all prior result directories remain
unchanged. See the [A/B report](archive/audio-volume-schema-ab136-148-2026-08-31.md),
[condition](../experiments/configs/qwen35-audio-volume-schema-ab136-148-20260831.json),
and [raw results](../experiments/qwen35-audio-volume-schema-ab136-148-20260831-run1/).

## 2026-08-31 Desktop Setting Schema Contract A/B

The full-189 order 141 protocol failure exposed a generic contract bug: the public
`desktop.set_setting.value` schema used overlapping `integer` and `number` branches,
so a valid integer was rejected before the Adapter. The contract is now owned by the
OS Adapter manifest, uses a scalar `anyOf` with one numeric branch, and is checked
against the runtime validator and built LiteAgent surface.

In a new affected/control exploration, order 141 changed from
`model_protocol_failure` to evaluator `passed` (`1.0`), while stable control order
148 remained `passed` (`1.0`). The model's `value=132` reached the Adapter unchanged,
and the terminal-size operation was verified. The affected episode still spent time
on unavailable GSettings keys and ended `stalled_no_progress`, so this result removes
one schema blocker but is not a general convergence fix. Focused tests passed
(`163 passed`); v337 and all prior result directories remain unchanged.

See the [A/B report](archive/desktop-setting-schema-ab141-148-2026-08-31.md),
[condition](../experiments/configs/qwen35-desktop-setting-schema-ab141-148-20260831.json),
and [raw results](../experiments/qwen35-desktop-setting-schema-ab141-148-20260831-run1/).

## 2026-08-30 Qwen--Holo Hybrid Episode Architecture

The active v2 tree now implements the target episode flow: Qwen 3.5 4B remains the text reasoning and
orchestration model, while an optional Holo 3.1 grounding gateway handles coordinate-bearing GUI actions after
Qwen selects the coordinate-free `gui_request` Tool. API actions, GUI delegation, catalog search, completion,
and failure all use the same one-Tool event path. Every result is marked for the next Qwen audit; accepted
terminal controls are deferred until that audit confirms them. A bounded no-progress recovery rebuilds only the
model-facing context and keeps the same VM, goal, event ledger, and usable observations.

The implementation is validated by the focused Holo, episode-control, recovery, protocol, boundary, and stage
suites (`250 passed`) and the full active v2 test suite (`390 passed`), together with compile, scoped Ruff, and diff
checks. A fresh exploratory
20-task run then exercised the live path: `14 passed / 4 failed / 2 agent_deadline_exhausted` with two workers and
one fresh guest per task. The coordinate-free `gui_request -> Holo -> shared GUI gateway` path was exercised three
times; all model requests used `reasoning_mode=thinking` and `enable_thinking=true`. This result is explicitly
non-promotable and does not change v337. Existing Qwen diagnostic runs below use older effort-labelled condition
schemas and must be treated as non-scoring evidence. A new condition records
the native binary `reasoning_mode` and explicit `enable_thinking` request for
each model endpoint; response reasoning fields are observations, not numeric
provider-maximum evidence.

The exploratory run is preserved in the [condition](../experiments/configs/qwen35-holo31-hybrid-random20-20260830-thinking-mode.json)
and [raw result directory](../experiments/qwen35-holo31-hybrid-random20-20260830-thinking-mode-run1/). The four
normal failures were evaluator failures after an episode, while two tasks exhausted the bounded Agent deadline;
there were no preflight or VM-start failures. It is a runtime viability measurement, not a new baseline or a claim
that all twenty tasks pass.

## 2026-08-29 Bounded Recovery And Context Projection Candidate

Offline trace analysis identified a cross-application recovery loop in which
repeated structured errors led to search-only turns and repeated the same bad
action, while oversized observations lost exact paths and selectors. The
candidate adds bounded alternative recovery (including first-error soft
recovery), consistent schema constraints,
public-route filtering, durable structured context projection, normalized
model-boundary redaction, and catalog-first multi-app route binding. Relevant
module and boundary tests pass at `99 passed`; scoped Ruff, format, compilation,
and diff checks pass. The initial 16k-thinking diagnostic was interrupted by
model-response latency; its evidence is archived separately. A practical
4096-token response budget was then frozen for small diagnostic runs with
`thinking=true`; the historical configs used a generic effort label that is
not a Qwen3.5 capability, so these runs are diagnostic and non-scoring under
the binary-mode gate.
This candidate is not a baseline.
The trusted v337 pointer remains `157/189` (`83.07%`). See the [archived
architecture report](archive/recovery-context-architecture-fix-2026-08-29.md).

## 2026-08-29 Relative-Path Resolution A/B

The OS Adapter now resolves relative `filesystem.copy_matching_tree` paths
against the observed active terminal working directory; absolute and `~/` paths
remain unchanged. Focused OS tests pass (`10 passed`). Under a new frozen
condition using Qwen3.5-4B with thinking enabled and a bounded 4096-token
budget, the affected v337-failed Order 143 and stable control Order
187 both passed (`2/2`, `generic_api_only`). Order 143 copied three matching
files into the live `fails` tree; this is one recovered task relative to v337,
not a new 189-task score. The condition was selected from prior outcomes and is
non-promotable; its config predates the canonical binary-mode schema, so it is
non-scoring under the current gate. Its config, raw results, and detailed
report are immutable.
See [the A/B report](archive/qwen35-pathcwd-ab143-187-2026-08-29.md),
[config](../experiments/configs/qwen35-recovery-pathcwd-ab143-187-thinking4k-dgx1-concurrency2.json),
and [results](../experiments/qwen35-recovery-pathcwd-ab143-187-thinking4k-dgx1-concurrency2-run1/).

## 2026-08-29 Recovery A/B: Orders 184 and 187

In that dated source condition, a two-worker Qwen3.5-4B run passed both a prior
v337 failure (Order 184) and a stable same-domain control (Order 187), with
`2/2` rewards and no environment failures. Thinking was explicitly enabled
(`thinking=true`, `enable_thinking=true`) with a bounded 4096-token output
budget. The historical effort label is not a Qwen3.5 capability, so this result
is non-scoring under the binary-mode gate. Order 184 used the public `file.indent_lines` API and
recovered from one rejected completion payload; Order 187 used
`explorer.set_exclusion`. This is `+1` affected-task pass relative to v337, but
the selection was informed by prior outcomes, so it is candidate evidence only,
not a baseline or an 189-task estimate. See the [archived A/B report](archive/qwen35-latest-recovery-ab184-187-2026-08-29.md),
[config](../experiments/configs/qwen35-recovery-latest-ab184-187-thinking4k-dgx1-concurrency2.json),
and [raw results](../experiments/qwen35-recovery-latest-ab184-187-thinking4k-dgx1-concurrency2-run1/).

## 2026-08-29 Qwen3.5-4B Fine-Grained API Composition Diagnostic

The first six-worker Agent run over the 17-task fine-grained API representative set completed with `3 pass / 14
fail / 0 environment failure` (`17.65%`). It used DGX1 `Qwen/Qwen3.5-4B` through LiteAgent, one fresh guest per
task, and no proxy. Passed orders were 43, 64, and 86. Across 266 model turns, the model made 71 tool searches,
145 Adapter proposals, and 47 GUI proposals; 81 Adapter calls returned successfully, while all GUI proposals
were rejected by the strict schema. The trace shows model-side action recall, argument typing, and incomplete
multi-stage composition as the dominant failures. This outcome-informed diagnostic is not an Agent baseline and
does not change v337 (`157/189`, `83.07%`). See the [archived run report](archive/qwen35-fine-grained-api-representative17-2026-08-29.md),
[config](../experiments/configs/qwen35-fine-grained-api-representative17-a485e12-dgx1-concurrency6.json), and
[raw results](../experiments/qwen35-fine-grained-api-representative17-a485e12-dgx1-concurrency6-run1).

## 2026-08-29 Holo3.1-4B Local OSWorld Sample

The frozen GUI-only random-10 condition completed `5 pass / 5 fail / 0 environment failure` on an unchanged,
outcome-independent sample from the fixed-189 OSWorld-Verified non-OAuth pool. It used the local BF16 Holo3.1-4B
service, H Company's public Agent Loop conventions, fresh Docker/KVM guests, one run, 30 steps, 300 Agent
seconds, and three workers. Across 124 serialized requests and 121 Agent events, the post-run check found zero
task-ID/evaluator URL/forbidden-route hits, zero argument or command mismatches, and zero false success
acknowledgements.

This is a local estimate, not an official Holo score or a promoted baseline. H Company publishes 80.0% only for
Holo3.1-35B-A3B and says that result uses an internal implementation; it does not publish a 4B OSWorld value or
the complete internal harness. The v337 pointer remains unchanged. See the
[archived Holo evaluation](archive/holo31-4b-osworld-local-evaluation-2026-08-29.md).

## 2026-08-29 Consolidated Dual-DGX Model Deployment

The active inference topology was consolidated without running OSWorld or changing the trusted
v337 baseline:

| Host | Endpoint | Model | Runtime condition | Measured KV capacity |
|---|---|---|---|---:|
| DGX1 | `http://192.168.0.224:8001/v1` | `Qwen/Qwen3.5-4B` | BF16, 65,536 context, `max_num_seqs=6`, utilization 0.21 | 417,792 tokens / 6.38 full sequences |
| DGX1 | `http://192.168.0.224:8002/v1` | `Hcompany/Holo-3.1-4B` | BF16, 65,536 context, `max_num_seqs=6`, utilization 0.21 | 416,768 tokens / 6.36 full sequences |
| DGX2 | `http://192.168.0.138:8001/v1` | `Qwen/Qwen3.8-27B` | BF16, 262,144 context, `max_num_seqs=6`, utilization 0.75 | 555,172 tokens / 2.12 full sequences |

Qwen3.8-27B is pinned to revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.
All 18 weight shards were checked against their Hugging Face LFS SHA-256 identifiers before
startup. Its six-way native function-call smoke returned `6/6` exact tool names and arguments in
7.939 seconds. DGX1 Qwen also returned `6/6` exact native function calls. DGX1 Holo completed a
six-way real-screenshot click test with `6/6` valid coordinate-bearing tool calls in 3.113 seconds.
All three services reported HTTP 200 and zero restarts after warmup.

The former DGX2 services were stopped and retained as `qwen35-4b-pre38-20260829` and
`holo31-4b-pre38-20260829`; no container was deleted. Qwen3.8 remains a deployment candidate. Holo was later
evaluated through a separate native GUI Runner, as recorded above. The Qwen--Holo delegation was integrated in the
active LiteAgent tree at the time of this snapshot, but that snapshot had not yet been live-validated as a new
sealed condition. The later hybrid full-189 reference is recorded at the top of this document and in
[Current Qwen-Holo Repair Reference](current-repair-reference.md).
Reproducible entries are under `deployment/qwen35-vllm/`, `deployment/holo31-vllm/`, and
`deployment/qwen38-vllm/`.

## 2026-08-28 Model-Free Direct API Composition Validation

The bounded validation queue is complete: all 17 evidence tasks for the 16 decomposed actions were exercised
through 26 immutable attempts. There were 25 scored attempts and one Order 79 exploration stopped before any
mutation or evaluator call when a result-projection defect was observed. Every scored attempt used a fresh guest,
operator-authored public API calls, Adapter read-back, zero model requests, zero direct Runner GUI actions, and
exactly one original evaluator call after the API sequence ended. A public semantic Adapter may still use a
generic keyboard shortcut behind its contract; no operator-authored coordinate or raw GUI command was issued.
Final results were `17/17 api_composition_pass`:

| Classification | Orders |
|---|---|
| `api_composition_pass` | 3, 15, 25, 43, 57, 62, 63, 64, 76, 77, 79, 86, 118, 142, 145, 161, 189 |

The Writer sequences used the actual public contracts, including `document.inspect`, `text.find`,
`paragraph.replace_text`, `document.append_paragraphs`, `paragraph.apply_numbering`, `bookmark.create`, and
`cross_reference.insert`. Order 79 derived the placeholder offsets and reference-list indices from current-state
read-back, created a native `[14]` list entry and GetReference field, and passed. The OS sequences used
single-file `filesystem.copy`, `filesystem.rename`, and `archive.compress_file` calls after explicit
`filesystem.find` observations; no removed batch macro was restored. Orders 57, 77, and 142 passed after fixing
visual ordering, significant trailing-space preservation, and flat destination mapping respectively.

Order 118 first exposed a reusable terminal visibility race: a valid terminal could appear after the verifier's
initial empty `wmctrl` read. Commit `3a1d879` added a bounded generic probe retry with counterfactual coverage.
The fresh-guest retry then passed through separate `terminal.show_output` and `window.capture` calls. Commit
`674c43c` supplied the reusable Writer capabilities that moved Order 79 from gap to pass. Order 189 removed the
task-shaped `osworld.array-variables` extension and added window-scoped accessibility verification in commit
`13a3e4e`. Commit `a485e12` added hash-pinned official offline Python/Debugpy acquisition, exact checked source
breakpoints, real debug-session state controls, and standard paused VARIABLES-tree read-back. Its fresh attempt
derived the source repairs, breakpoint line, and window ID from public live state, reached a native paused debug
session, and passed. No task ID, evaluator state, expected variable list, or synthetic task extension entered the
runtime contracts. A same-commit stable VS Code control, Order 187, also passed through one
`explorer.set_exclusion` call, so the direct affected/control gate is `2/2`.

Raw evidence is preserved under `experiments/direct-api-composition-order*/`; the final Writer-native retry is
`direct-api-composition-order079-writer-native-projection-attempt3`, the final Order 189 evidence is
`direct-api-composition-order189-controller-readback-a485e12-attempt4`, and the control is
`direct-api-control-order187-a485e12-attempt1`. See the
[machine-readable ledger](../experiments/analysis-v337-bounded-granularity/direct-api-composition-ledger.json)
and [archived report](archive/direct-api-composition-validation-2026-08-28.md). The `17/17` result measures
developer-operated API composability only. It is not a LiteAgent/Qwen evaluation, is not promotable as an Agent
baseline, and does not change the immutable v337 result of `157/189` (`83.07%`).

## 2026-08-28 Bounded Task-Shaped API Decomposition

The source-only decomposition pass is complete on the active clean-hardened-v2-derived tree. All 24 reviewed
actions now have a disposition: 16 task-shaped, hidden-discovery, policy-solving, or heterogeneous workflow
actions were removed, while eight native or explicit homogeneous transactions were retained. The strict public
inventory now contains 289 actions. The authoritative action list, classifications, replacements, and inventory
hash are in `experiments/analysis-v337-bounded-granularity/macro-ledger.json`.

The 16 removals were completed in five coherent batches: Calc 3, Writer 4, OS/VLC 3, Multi-Apps/VS Code 3, and
Impress 3. Their replacements expose read-only inspection followed by one explicit mutation per independently
meaningful target. The Impress batch also removed seven task-shaped modules and seven dead Runtime planning or
completion methods; title-to-notes is now composed from `presentation.inspect` and `slide.set_notes`, while
heterogeneous textbox changes use repeated model-selected `shape.format_text` calls.

The five focused counterfactual contract files passed together at `36 passed`; scoped Ruff, compileall, JSON
validation, and diff checks passed at the source gate. No model endpoint, GUI fallback, broad suite, or fixed-189
run was started during that source-only phase. The later model-free direct validation is recorded above and
remains separate from Agent success; v337 is still the trusted baseline.

## 2026-08-28 Selector And Context-Budget Diagnostics

Two prospectively frozen three-task pairs completed under the same sealed source, thinking/4096-token model
condition, concurrency 2, and fresh-VM protocol. The observed-selector control and candidate both passed `2/3`.
On affected Order 122, the candidate exposed a complete selector derived only from successful live query output;
Qwen selected it unchanged and saved the attachment on the first attempt. This reduced attachment-save attempts
from four to one and GUI calls from nine to five, but later PDF/workbook work still failed, so the mechanism adds
no binary pass.

The context-budget candidate also passed `2/3`; all 63 real decisions were below the budget, with a maximum input
of 18,152 tokens and zero projections. Its separate live synthetic preflight reduced a 238,494-token request to
35,806 tokens with exact agreement from the serving tokenizer and unchanged protected hashes. The control's
Order 108 received three HTTP-200 responses with zero structured tool calls and became an environment failure,
so that pair is not a causal success comparison. Candidate audits are valid and admissible with zero leakage,
argument rewrite/injection, action mismatch, or trace mismatch. The next gate targets tool-call transport repair
and workflow convergence rather than further selector or context-threshold tuning. See the
[archived report](archive/architecture-recall-selector-context-budget-ab.md).

## 2026-08-28 Tool Router Paired Diagnostic

The prospectively frozen six-task pair compared the default lexical `tools_search` with the experimental
`llm_full_catalog_rerank_v1` backend under the same source, task order, model, thinking/4096-token policy, VM,
budgets, and evaluator. Both conditions passed `2/6` with reward sum `2.998820`. The lexical control had three
normal failures and one context-overflow environment failure; the candidate had four normal failures and no
environment failure. The candidate used 12 additional Router calls with mean input 33,227 tokens, increased
steps from 129 to 136, and increased aggregate duration from 5,046.782 to 6,094.348 seconds.

Both candidate worker audit-v5 reports are valid, evidence-valid, and admissible. Router request/call/catalog
mismatches, task identity leakage, Runner argument rewrites/injections, model/action mismatches, Adapter trace
mismatches, and GUI command mismatches are all zero. The backend therefore remains default-off as a valid negative
result. The traces identify observed resource binding, context projection, and completion rejection as the next
independent architecture variables. See the
[archived paired diagnostic](archive/architecture-recall-tool-router-ab.md).

## 2026-08-27 Git Source-Control Migration

The original root Git metadata has been restored and the canonical source tree is now versioned by commit rather
than by copied v-numbered directories. Raw experiment evidence remains in place and outside normal Git objects;
configs and compact baseline records remain tracked. Repeated offline deployment wheels use Git LFS. The import
is tagged `source-import-20260827`; it does not claim to reconstruct v386, whose preserved evidence contains a
source-tree hash but no complete source archive. See [Version Control](archive/version-control.md).

## 2026-08-27 Complete v422 Remaining-27 Classification

The sealed v422 condition completed the immutable 27-task recovery cohort at `5 pass / 22 fail / 0 environment
failure` (`18.52%`). Passed orders were 55, 61, 90, 119, and 129. All six audit-v5 workers are valid,
evidence-valid, and baseline-admissible, so the 22 failures are behavior, capability, fidelity, or dataset-reference
failures rather than environment or evidence failures.

The trace-level classification assigns one primary cause per failed task: six observed-result/path/selector
binding failures, five multi-step composition or premature-completion failures, one missing reusable PDF-form
capability, one deterministic-tool routing/GUI fallback failure, three model semantic or visual reasoning
failures, three output-fidelity failures, and three dataset/reference inconsistencies. Ten tasks have high
generic engineering leverage; five should not be tuned against a single Golden artifact. See the
[archived classification](archive/generic-only-v422-remaining27-failure-classification.md) and machine record at
`experiments/analysis-v422-literal-control-consistency/remaining27-failure-classification.json`. This is
prior-outcome-selected development evidence and does not replace v337.

## 2026-08-27 Complete v421 Remaining-27 Diagnostic

The sealed v421 condition ran every task in the immutable 27-task recovery cohort once with six workers and a
fresh VM per task. It completed `4 pass / 23 fail / 0 environment failure` (`14.81%`). Passed orders were 55,
61, 90, and 119. Compared with v415, there were no new passes and Orders 129 and 132 did not reproduce. All six
audit-v5 reports are valid, evidence-valid, and baseline-admissible across 253 captured requests, with every
leakage, forbidden-route, Runner rewrite/injection, action mismatch, and Adapter trace mismatch count at zero.

The observed-result path constraint did improve Order 105's execution depth: Qwen read multiple verified source
files and applied a patch, but still localized the defect incorrectly. Offline taxonomy attributes 19 of 23
failures primarily to incomplete workflow/completion and four to residual model capability. v421 is rejected as
an improvement and does not replace v337. See the
[archived v421 report](archive/generic-only-v421-remaining27-result.md) and machine summary at
`experiments/analysis-v421-observed-path-batch-reliability/remaining27-result-summary.json`.

## 2026-08-27 Complete v413 Remaining-27 Diagnostic

The sealed v413 condition ran all 27 tasks in the immutable v404 remaining-failure cohort once, with six
workers, a fresh VM per task, no resume, and no best-of selection. It completed `5 pass / 22 fail / 0
environment failure` (`18.52%`). Passed orders were 55, 61, 90, 103, and 132. Compared with v409's two passes,
v413 adds Orders 55, 61, and 103. Order 129 passed the preceding affected/control gate but failed this complete
run, so it is explicitly recorded as an unstable gate-only recovery rather than a stable pass.

All six audit-v5 reports are valid, evidence-valid, and baseline-admissible across 367 captured requests and 27
guest inventories. Task/golden leakage, forbidden routes, Runner argument rewrite or injection, model/action
mismatch, and Adapter trace mismatch are all zero. Orders 87, 120, 126, and 163 retained non-binary partial
rewards of `0.84386`, `0.92585`, `0.80429`, and `0.98979`; none counts as a pass. The authoritative machine
summary is `experiments/analysis-v413-generic-recovery-contracts/remaining27-result-summary.json`. v413 is a
prior-outcome-selected diagnostic, not a promoted baseline; v337 remains the trusted baseline.

## 2026-08-26 Complete v410 v409-Failures-25 Diagnostic

The sealed v410 condition ran all and only the 25 failed episodes from the immutable v409 remaining-27 result.
It completed `0 pass / 25 fail / 0 environment failure` with six workers, one fresh VM per task, no resume, and
no best-of selection. The complete 25-element reward vector is identical to v409. Orders 87, 120, and 163
retained partial rewards `0.84386`, `0.92585`, and `0.98979`; none is a binary pass. The prior four-task check's
Order 126 partial `0.80429` did not reproduce in the expanded run, which returned `0.0`.

All six audit-v5 reports are valid, evidence-valid, and baseline-admissible across 297 captured requests and 25
guest inventories. Every leakage, forbidden-route, request-mismatch, Runner rewrite/injection, action mismatch,
Adapter/GUI trace mismatch, forbidden guest path, cache-hash match, and pre-model boundary count is zero. v410
is retained as valid negative evidence, not a success improvement; v337 remains the trusted baseline. See the
[archived v410 report](archive/generic-only-v410-v409-failures25-result.md) and machine summary at
`experiments/analysis-v410-path-recovery/v409-failures25-result-summary.json`.

## 2026-08-26 Complete v409 Remaining-27 Diagnostic

The frozen v409 condition ran all 27 preceding failures once with six workers and fresh VM reset per task. It
completed `2 pass / 25 fail / 0 environment failure`; Orders 90 and 132 were the two new binary passes, both in
two `generic_api_only` steps. All six audit-v5 reports are valid, evidence-valid, and baseline-admissible across
308 captured model requests, with zero leakage, forbidden-route use, Runner argument rewrite/injection, action
mismatch, or Adapter trace mismatch.

Offline trace analysis attributes 19 failures primarily to incomplete workflow/completion behavior, five to
parameter or contract use, and one to residual planning capability. The next bounded work targets two shared
causes: model-selected `filesystem.find` recovery after structured missing-path errors, and completion evidence
for each independently requested final result. The detailed report is
[archived here](archive/generic-only-v409-remaining27-result.md), with the authoritative machine summary at
`experiments/analysis-v409-workflow-archive-contract/remaining27-result-summary.json`.

## 2026-08-26 Grounded Completion Negative Result

v406 tested all and only the 27 tasks still failed by the complete v404 prior-failure diagnostic. The fixed
condition used six workers, `runs=1`, fresh VM reset per task, no proxy, no resume, and no best-of selection.
It produced `0 pass / 26 fail / 1 Runner-labeled environment failure`; Order 119 is effectively a model failure
because the model saved an ODP presentation under the requested `background.png` name and the image evaluator
could not decode it. No environment retry is authorized.

The candidate generated 151 completion rejections across 13 tasks and no binary recovery. Its surface clause
splitter treated preambles and politeness as state-changing outcomes, consuming steps without repairing task
state. The grounded completion candidate is therefore rejected and must be disabled in the next condition.
All six worker audits are valid across 450 model requests with zero leakage, action mismatch, argument rewrite
or injection, and Adapter trace mismatch. The detailed evidence is in the
[archived v406 report](archive/generic-only-v406-remaining27-negative-result.md) and its machine-readable summary
at `experiments/analysis-v406-grounded-completion/remaining27-result-summary.json`.

## 2026-08-26 Adapter-Declared Auxiliary Observation Lease

v404 removes the last tool-name special case from the image-preview lifecycle. An Adapter may now return a
sanitized `observation_surface` declaration with a version, kind, readiness, and two blocking properties. The
LiteAgent policy starts a lease only from an executed successful Adapter result whose declaration says the
auxiliary visual surface is ready, does not block Adapter actions, and requires no GUI dismissal. It keeps the
normal API surface available while the visual observation remains useful, then releases GUI conservatively on
an explicit empty search, a conflicting declaration, or another boundary that cannot prove the lease remains
valid. Rejected calls and action names without the declaration cannot start the lease.

The contract is application-neutral. `image.preview_batch` is only its first producer; the Runner neither checks
that action name nor assumes an image-preview route. A counterfactual synthetic Adapter/action with the same
typed declaration receives identical policy behavior. Unknown result fields are stripped from the model-visible
projection, and the model still chooses every subsequent action and argument unchanged.

The source tree is frozen at SHA-256
`f46138e0809024bcc3300741580c9450145d42c47839f558da6fdaf9242cf6e9` (`826` files). Verification produced
`125 passed` in the focused contract/policy suites and `4288 passed / 110 preserved historical failures` in the
complete unit suite. Full Ruff, compileall, source seal, strict action contracts, tool-granularity quarantine,
deployment/leakage/layout checks, and frozen-v1 hashes passed.

The prospectively frozen clean-VM smoke completed `2/2`. The fixed outcome-independent 16-task validation then
completed `16 pass / 0 fail / 0 environment failure` in one run with six workers. It used 91 model requests,
forwarded 52 Adapter calls and 12 GUI calls, and produced 11 `generic_api_only` plus 5 `api_plus_gui` routes.
All eight audit-v5 worker reports across smoke and validation are `valid=true`, `evidence_valid=true`, and
`baseline_admissible=true` with zero leakage, argument rewrite/injection, action mismatch, Adapter trace
mismatch, GUI command mismatch, or guest-policy failure.

Order 100 is the mechanism check. v403 had found the correct images but let GUI controls compete with the next
API call after the preview, so the model never created the ZIP. In v404, the model itself selected
`filesystem.find`, `image.preview_batch`, the then-public `filesystem.copy_files` batch action, another
`filesystem.find`, and `archive.create_zip`; no GUI call executed in that episode and the original evaluator
returned `1.0`. That action is historical and is not the active single-file `filesystem.copy` contract. The same
16-task set had previously peaked at `15/16`, so v404 adds one observed pass on this small gate. Because this is
one run and includes source changes after the earlier controls, it is not a causal full-benchmark claim and does
not replace v337.

Raw evidence, configs, audits, and the bounded interpretation are indexed in
[the archived v399-v404 report](archive/generic-only-v399-v404-observation-lease.md).

### v337 Prior-Failure Diagnostic

The user requested a direct check of every error from the previous baseline. The immutable v337 fixed-189
result contains exactly 32 failed episodes. A machine-readable selection record extracts all and only those
failures in fixed-pool order: 2 Impress, 27 Multi-Apps, 1 OS, 1 VLC, and 1 VS Code task. Because task selection
uses known v337 outcomes, the frozen condition explicitly records `selection_uses_prior_outcome=true` and
`baseline_candidate=false`.

The unchanged v404 source completed the 32 tasks once with six workers and fresh VM reset per task:
`5 pass / 27 fail / 0 environment failure`. Recovered tasks were Orders 100, 112, 123, 143, and 184; all five
were `generic_api_only`. Their v337-to-v404 step counts were respectively `19→11`, `21→2`, `19→5`, `30→9`, and
`9→3`. The remaining failures ended as 13 no-progress stalls, 10 model-declared completions rejected by the
original evaluator, 2 max-step exits, and 2 agent-time exits. All eight `api_plus_gui` routes failed.

Six audit-v5 reports are valid, evidence-valid, and baseline-admissible across 381 captured requests. They found
zero task/golden leakage, Runner rewrite or injection, model/action mismatch, Adapter trace mismatch, GUI command
mismatch, or guest-policy failure. `baseline_admissible` here means the episode evidence is internally valid; it
does not override the prior-outcome selection or make this diagnostic promotable.

If all 157 v337 passes were retained, adding the five recoveries would project to `162/189` (`85.71%`). That is
an explicitly unverified upper projection, not a score: the 157 previous passes were not run under v404. The
trusted baseline therefore remains v337 at `157/189` (`83.07%`). Full selection, task-level comparison, hashes,
and evidence paths are recorded in
[the archived prior-failure report](archive/generic-only-v404-prior-failures32.md).

## 2026-08-25 Innovation Prototype

The **Contract-Compiled Causal Affordance Graph (CCAG)** was an opt-in prototype in the 2026-08-25 snapshot. Its
former implementation path (`integrations/lite_agent/causal_affordance_graph.py`) is archived and absent from the active tree;
the prototype compiled public action-contract metadata and sanitized executed events into bounded observation
edges. The archived experiment and its constraints remain available for provenance, but the current hybrid path
uses the active recovery/context modules described in [Architecture](architecture.md).

The default remained disabled, so v337 evidence and the promotion-controlled baseline pointer were unchanged in
that snapshot. Focused tests,
the model-authored-state regression suite, Ruff, and compilation passed. The detailed literature boundary,
equations, counterfactual requirements, and
small A/B gate are recorded in the [archived innovation plan](archive/innovation-plan-20260825.md) and
[`archive/innovation-ccag-20260825.md`](archive/innovation-ccag-20260825.md).
The v395-v398 fresh-VM experiments are diagnostic only and do not alter the baseline pointer.

### Evidence hardening after v393

The generic state-evidence reader now traverses only the public response envelopes (`context_hint`,
`downstream_context`, `adapter_response`, `response`, and `result`) to a bounded depth. An explicit
`state_changed=false` dominates duplicate or conflicting declarations, so a delegated no-op cannot fall through to
the old non-read-only action heuristic and become mutation evidence. Missing declarations retain the legacy
fallback for older Adapters. CCAG uses the same reader, preventing the graph and completion policy from disagreeing.

The focused evidence, request-block, completion, model-state, and CCAG suites pass (`223 passed`), with Ruff and
compile checks clean. A read-only scan of v393 found two events whose false declaration was nested below the old
reader's depth; both now resolve to `False`. This changes the active source and therefore requires a new frozen
condition. v337, v393, and all raw evidence remain immutable.

### CCAG and Progressive Disclosure A/B (v395-v398)

All conditions use the same outcome-independent 16-task validation template, Qwen/Qwen3.5-4B, LiteAgent, six
workers, fresh VM per task, and runs=1. Every raw result and worker audit is immutable; all listed worker audits
are `valid=true` and `baseline_admissible=true`.

| Condition | Result | Input/request | Model-visible images | GUI executions |
|---|---:|---:|---:|---:|
| v395 control | 15/16 | 7,458 | 104/104 | 13 |
| v395 naive CCAG | 14/16 | 7,244 | 70/119 | 25 |
| v396 control | 14/16 | 7,593 | 103/103 | 16 |
| v396 visual-debt CCAG | 14/16 | 7,713 | 82/104 | 10 |
| v397 control | 13/16 | 7,666 | 119/119 | 25 |
| v397 CCAG-memory | 13/16 | 7,804 | 100/128 | 15 |
| v398 control | 14/16 | 7,816 | 118/118 | 27 |
| v398 progressive GUI | 14/16 | 6,860 | 86/110 | 13 |

In v398, progressive GUI disclosure reduced total prompt tokens by 18.2%, requests by 6.8%, GUI executions by
51.9%, and summed wall time by 30.8% relative to its same-condition control. Binary success stayed at `14/16`,
with failed orders changing from `[19, 100]` to `[100, 143]`. This is an efficiency candidate, not a success-rate
gain; it remains opt-in and is not promoted into v337. The condition is frozen at
`experiments/configs/generic-only-validation16-v398-progressive-gui-concurrency6.json`.

[Back to project index](index.md)

## Historical v337 Baseline

v337 is the trusted promoted generic-only baseline for `Qwen/Qwen3.5-4B` through LiteAgent. It completed the
fixed 189 non-OAuth tasks once with six workers, a fresh VM per task, no proxy, no resume, and no best-of selection. The
result is `157 pass / 32 fail / 0 environment failure`, or `83.07%` binary success.

All six strict audit-v5 reports are `valid=true`, `evidence_valid=true`, and `baseline_admissible=true`. They
checked 1606 serialized model requests and 189 guest inventories. Task identity/golden exposure, forbidden
routes, Runner argument rewrite or injection, model/action mismatch, Adapter trace mismatch, GUI command
mismatch, forbidden guest paths, OSWorld-cache hash matches, unexpected guest source, and initial/pre-model
process boundary failures are all zero.

The promoted runtime/test tree seal is `2b62a116...aa26aad`. The same source passed a prospective 2-task smoke
(`2/2`) and frozen 16-task validation (`15/16`) before the fixed run was authorized. The current complete unit
suite reports `4234 passed / 111 preserved historical failures`; the remaining gap is
dominated by Multi-Apps: 21/48 pass and 27/48 fail. The tool-granularity Goal is complete; none of its post-v337
source conditions has been promoted or benchmarked as a replacement baseline.

## Tool-Granularity Goal

The machine-readable ledger is
`experiments/analysis-generic-tool-granularity/one-task-macro-ledger.json`. It starts from 24 actions observed as
the only successful principal mutation in at least one v337 pass and classifies each as a whole-task macro,
heterogeneous batch, cross-application workflow, misplaced facade, or defensible native atomic operation.

The queue is complete at v386: all 24 candidates have an implementation-level classification. Twenty-three
whole-task, heterogeneous-batch, implicit-discovery, cross-application, or misplaced-facade actions were
decomposed; `slide.create_summary` was retained as one native atomic application command. No candidate remains
blocked or in progress. The ledger is the authoritative per-item record.

The v386 inventory contains 292 public actions: 154 atomic, 21 read-only, 6 save, 71 quarantined composite,
3 legacy-forbidden, and 37 not yet part of this evidence-backed queue. Strict mode allows 181 and blocks 111;
zero composite or forbidden action is strict-exposed. The v386 source tree contains 774 files with SHA-256
`a38dcd0d03eb1e9065f04d86499c5faceb95ae07d620ef763a95ed8a8326730f`.

The final two candidates make the boundary concrete. `desktop.set_default_application` was replaced by bounded
read-only `desktop.applications.inspect` and exact `desktop.mime_associations.set`; the model owns pagination,
Desktop Entry ID, and every MIME value. `pdf.split_by_outline` was replaced by read-only
`pdf.outline.inspect` and one-output `pdf.pages.extract`; the model owns every output path, inclusive page range,
backend, and overwrite choice. The Runner exposes reusable companions but never transfers results or executes
the next action.

The first v385 PDF check exposed a contract gap: the model omitted `output_backend` and the Adapter selected a
default. That 0/1 run remains immutable superseded evidence. v386 made `outline_level`, `overwrite`, and
`output_backend` mandatory, then froze a new one-task check. It completed `0 pass / 1 fail / 0 environment
failure` in three steps. The model explicitly selected the outline depth and a Cairo extraction with unchanged
arguments, but proposed completion after creating only one of eight required outputs. Audit-v5 is valid across
all three requests and reports zero task/golden leakage, argument rewrite or injection, action mismatch, trace
mismatch, or guest-policy failure. This proves the explicit primitive boundary, not stable multi-output
planning. The raw failure is preserved in
`experiments/generic-only-pdf-explicit-policy-validation-v386-concurrency1-run1/` and the concise record is
`experiments/analysis-generic-tool-granularity/v386-pdf-primitives-explicit-policy-validation.json`.

Verification for v386 produced 743 related passes and `3855 passed / 112 preserved historical failures` in the
complete unit suite. Ruff, touched-file formatting, compileall, strict action contracts, granularity quarantine,
and guest deployment policy passed. The granularity Goal itself did not authorize a fixed-189 run, and the
baseline pointer was not changed.

After the Goal completed, the user explicitly authorized one fresh full diagnostic despite the negative PDF
completion gate. The frozen config is
`experiments/configs/generic-only-fixed189-v386-diagnostic-concurrency6.json` (SHA-256
`39719c480643f0f996b72860b9c526076062985a241bff5e1c8e30ab50880cca`). It runs all 189 tasks once from Order 1
with six workers, no resume or best-of selection, and preserves every attempt under
`experiments/generic-only-fixed189-v386-diagnostic-concurrency6-run1/`. The condition records
`baseline_candidate=false`, `promotion_pre_authorized=false`, and the unsuccessful preceding validation.

The diagnostic completed all 189 tasks in about 2 hours 14 minutes: `97 pass / 92 fail / 0 environment failure`,
or `51.32%`. Domain passes were Calc 15/28, Impress 15/35, Writer 16/21, Multi-Apps 5/48, OS 11/16,
Thunderbird 11/12, VLC 12/13, and VS Code 12/16. Six audit-v5 reports are valid and evidence-valid across 1967
captured model requests and 189 guest inventories; task/golden leakage, forbidden routes, request mismatch,
Runner rewrite/injection, action/trace/GUI mismatch, forbidden guest paths, and OSWorld-cache hash matches are
all zero. The machine-readable record is
`experiments/analysis-v386-fixed189-diagnostic/manifest.json`.

This is 60 fewer passes than v337. Multi-Apps alone lost 16 passes, but the regression is broad across Calc,
Impress, Writer, OS, Thunderbird, and VS Code as well. The result shows that the 4B model does not reliably
compose the decomposed primitives or preserve multi-step completion state. It cannot replace v337 without a
separate prospective promotion sequence; v337 remains the trusted baseline.

Offline trace classification assigns the 92 failures to workflow/completion (40), tool routing (38), parameter
usage (10), and unresolved model capability (4). Forty-nine episodes submitted an accepted completion claim
that the evaluator rejected; 31 stalled, 6 exhausted the time budget, 5 hit the step limit, and 1 explicitly
failed. Seventy-seven failures had already executed at least one successful mutation, while repeated-action
blocking appeared in 61 and truncated model responses in 43. Of the 25 tasks directly evidencing the 24 reviewed
macros, only Orders 25, 43, 64, 77, and 161 passed after decomposition. The preserved routing analysis, failure
taxonomy, and historical comparison live under `experiments/analysis-v386-fixed189-diagnostic/` and remain
offline diagnostics only.

## Historical Routing Recovery (v389-v393)

The post-v386 work at that time recovered generic primitive routing and truthful stateful execution through small,
prospectively frozen affected/control conditions. It did not reopen the 24-item granularity queue. The current
hybrid repair queue and authorization state are defined at the top of this document and in the current reference.

v389y added bounded `editor.inspect_active_file` inspection and completed its frozen three-task run at `3/3`.
The target nevertheless never called the new action, so the predeclared mechanism gate failed. The result is
preserved under `experiments/analysis-v389y-active-editor-resource3/`; no larger gate or promotion followed.

v389z isolated an Impress persistence defect. Saving to the current document URL had been treated as Save As,
allowing an unrelated paragraph to be reserialized differently before the official evaluator's later save.
The historical `impress_adapter/persistence_contract.py` logic now lives in `impress_adapter/uno_worker.py`, which
selects native current-document save only for a canonically equal local URL with no explicit filter, and retains Save
As for every distinct or explicitly filtered destination.
The frozen target passed with unchanged model arguments and truthful `save_mode=current_document` evidence.
The control failed because the model selected exact `shape.fit_to_slide` on the wrong observed portrait image
instead of semantic `picture.fit_to_slide`; it was not a persistence regression.

The formal v389z result is `1 pass / 1 fail / 0 environment failure`, both `generic_api_only`, across 16 captured
requests. Audit-v5 is valid and reports zero leakage, forbidden routes, rewrite, injection, action mismatch,
trace mismatch, GUI mismatch, or transport mismatch. Because the frozen condition required both tasks to pass,
v389z did not advance to the 30-task gate, confirmation, fixed-189, or promotion. Its source seal is
`2bd235f2...b9d1`; the detailed machine-readable record is
`experiments/analysis-v389z-impress-current-save2/summary.json`.

v390 tested that residual routing hypothesis without changing Adapter execution or model arguments.
`impress_cover_semantics.py` and `impress_tool_routing.py` now withhold the overlapping exact-selector
`shape.fit_to_slide` action only when
the instruction asks for semantic picture fitting and contains no explicit observed identity. Exact action names,
paths, indices, selectors, and observed names keep the lower-level action searchable. The frozen target selected
`picture.fit_to_slide` with its own semantic arguments; the persistence control again used current-document save.

The formal v390 result is `2 pass / 0 fail / 0 environment failure`, both `generic_api_only`, across 18 captured
requests and no GUI calls. Audit-v5 is valid with zero identity or golden leakage, forbidden routes, Runner
rewrite or injection, action mismatch, Adapter mismatch, transport mismatch, GUI mismatch, or model-authored
state mismatch. Its source seal is `a0cf1fcf...2c55`; the detailed record is
`experiments/analysis-v390-impress-fit-route-overlap2/summary.json`. The predeclared two-task criteria are met, so
the work advances to the existing deterministic 30-task gate, not to confirmation or fixed-189.

v391 then ran that frozen 30-task gate once and completed `15 pass / 15 fail / 0 environment failure`. It retained
all 6 stable controls but recovered only 9 of the required 12 failed targets, and its long-loop stratum recorded
11 repeated-action blocks against a maximum of 8. All six strict audits passed, but the performance gate failed;
therefore v391 did not authorize a 60-task confirmation or fixed-189 run. The immutable summary is
`experiments/analysis-v391-development-gate30/summary.json`.

v392 added one generic bounded Impress `shape.query` capability and routing disambiguation. Its source seal covers
815 files, 64,036,826 bytes, SHA-256 `85509ac...57130e`; the full unit suite produced `4216 passed / 111 preserved
historical failures`, and static integrity checks passed. The frozen three-task check was interrupted by the user
before any task completed, so it supplied no stability evidence.

The user then explicitly requested one full diagnostic despite the failed/interrupted smaller gates. v393 froze
the unchanged v392 source as a non-candidate condition and completed all 189 tasks in 2 hours 31 minutes:
`92 pass / 92 fail / 5 environment failure`. This is `50.00%` over 184 scored episodes and `48.68%` over all
scheduled tasks. Domain passes were Calc 9/28, Impress 13/35, Writer 16/21, Multi-Apps 6/48, OS 12/16,
Thunderbird 12/12, VLC 12/13, and VS Code 12/16.

Five of six v393 audit-v5 workers passed. All six found zero task/golden leakage, forbidden-route use, Runner
argument rewrite or injection, Adapter trace mismatch, transport mismatch, and GUI mismatch. Worker 3 failed on
one Order 111 work-state transition: a model-selected idempotent `filesystem.create_directory` result explicitly
reported `state_changed=false`, but Runtime exposed and accepted it as primary mutation evidence. The live reader
did not traverse delegated `context_hint.downstream_context`, while the independent auditor did. This is a
generic evidence-validation defect, not argument transfer, but it makes v393 evidence-invalid. The raw score is
descriptive only and the v337 baseline pointer remains unchanged. See the
[v393 diagnostic report](archive/generic-only-fixed189-v393-diagnostic.md) and
`experiments/analysis-v393-fixed189-diagnostic/summary.json`.

## Promoted Baseline Record

The promoted baseline is tracked by the [promotion-controlled current pointer](../experiments/baselines/current.json), which
resolves to the [immutable v337 promotion record](../experiments/baselines/v337.json). v337 was pre-authorized
before its full result existed and was promoted only after smoke, validation, fixed-189, source, process,
trajectory, and all audit-v5 gates passed.

The promotion record is the short operational index; the detailed seal remains
`experiments/analysis-v337-trusted-fixed189-baseline/manifest.json`. The seal, aggregate results, worker results,
trajectory manifests, and report are immutable evidence. The active runtime is identified by its recorded tree
hash (`2b62a116...aa26aad`), so any source, schema, prompt, model, VM, or protocol change must create a new
condition and a new result directory. No source files are copied into the active baseline directory.

Before using the baseline, verify the pointer record hash and the referenced seal/config/results hashes against
the values in `experiments/baselines/v337.json`. This prevents a later experiment from silently changing what
the headline score refers to.

## v247 Correction

v247 completed one fixed run of 189 non-OAuth tasks with six workers. The immutable result is `135/189`, reward
137.63793466034602, with no recorded environment failures. It remains a historical observation only.

The original audit schema v3 reported all six workers admissible. Independent follow-up exposed blind spots, so
audit schema v4 was run read-only into a separate correction directory. Aggregate results are:

| Check | Corrected result |
|---|---:|
| Tasks / actual model requests checked | 189 / 1911 |
| Model request artifact mismatches | 0 |
| Task identity or evaluator URL leaks in model/Adapter data | 0 |
| Adapter Runner rewrites / injections | 0 / 0 |
| Multi-Apps tasks containing a golden asset | 48 |
| Forbidden guest paths / OSWorld-cache hash matches | 96 / 96 |
| Pre-model evaluator-boundary failures | 189 |
| GUI calls missing an independent handoff trace | 123 |
| Confirmed invalid GUI calls | 3 |
| Corrected worker audits admissible | 0/6 |

The three confirmed GUI defects were one VLC episode in which the model supplied
`{"action":"hotkey","key":"F"}` three times. The old schema accepted `key`, but execution read only `keys`,
so the actual command was `pyautogui.hotkey()`.

Evidence paths:

- immutable source results: `experiments/generic-only-fixed189-v247-concurrency6-run1/`;
- corrected audit JSON and seal: `experiments/analysis-v247-baseline-audit-correction/`;
- report: [v247 audit correction](archive/generic-only-fixed189-v247-audit-correction.md).

## Implemented Cleanup

### Strict deployment

`scripts/strict_deployment.py` is the central strict-package policy. Every host deployer accepts an explicit
`strict_generic` mode. It excludes task modules, GIMP/VLC golden assets, reference profiles, task manifests,
and package README files. Strict Multi-Apps uploads its generic action/schema overlay and creates an empty task
manifest. Guest sanitization remains a second fail-closed boundary rather than the primary removal mechanism.

### Evaluator boundary

`scripts/evaluation_boundary.py` loads the task JSON in a short-lived child process and returns only `id`,
`instruction`, `config`, and `proxy`. VM reset receives a non-answer placeholder evaluator. The parent process
loads evaluator configuration and evaluator-only cache resources only after the Agent loop and final screenshot,
then attaches them immediately before the original evaluator runs.

### GUI contract

`integrations/lite_agent/gui_actions.py` owns both the action-specific schema and deterministic command
conversion. Model-selected arguments are validated without defaults or alias repair. Every GUI attempt now has a
`gui_calls.jsonl` record containing the original arguments and exact OSWorld command.

### Historical Audit v4

The historical audit process used all task IDs from the frozen config, not each worker shard alone. It audited failed
as well as successful Adapter forwards, GUI argument/command equality, evaluator-boundary evidence, forbidden paths,
and guest hashes matching any OSWorld cache file. The corresponding standalone helper is not present in the current
checkout; preserved worker audit records remain the authoritative evidence for that dated condition. Any missing
required evidence failed closed.

## Verification

| Check | Result |
|---|---:|
| Focused cleanup/auditor tests | 62 passed |
| Complete project unit suite | 3291 passed for v306; no cross-project source outside LiteAgent changed in v307 |
| Complete LiteAgent unit suite | 1473 passed for v307 |
| Offline v252 failure-taxonomy tests | 7 passed, included in the complete suite |
| Ruff | passed for active source and tests |
| Changed-file formatting | all v307 changed Python files passed; unchanged historical files remain outside the format assertion |
| compileall | passed |
| Frozen v1 SHA-256 validation | passed |
| OSWorld checkout | pinned commit, tracked tree clean |
| Project layout gate | passed |
| v249 clean-VM smoke | 2/2 evaluator pass; 2/2 audit-v4 valid |
| v252 promotion record | pointer, record, seal, config, results, and 189 trajectory hashes rechecked |
| v319/v320 project unit suite | 3437 passed |
| v319/v320 strict deployment/schema/Runner suite | 698 passed |
| v320 Phase-1 consolidated cohort | 11/11 evaluator pass; six repair items Agent-terminated |
| v320 strict audits | 6/6 valid and admissible; 98 requests; all leakage/integrity counters zero |
| v326 complete project unit suite | 3513 passed |
| v326 targeted A/B | 4/4 pass and Agent-terminate; four audits admissible across 28 requests |
| v326 Phase-2 consolidated cohort | all 10 repair gates, 4 clean controls, and Order 128 passed; only non-gating blocked Order 131 failed |
| v326 strict audits | 6/6 valid and admissible; 117 requests; all leakage/integrity counters zero |
| v326 Phase-3 disposition | 5/5 items bounded as reference-specific; no source change, model run, or new binary pass |
| v335 complete project unit suite | 3620 passed on the final sealed source |
| v335 fixed-189 historical observation | 158 pass / 31 fail / 0 environment failure; 83.60% |
| v335 audit-v5 correction | 0/6 admissible; missing prospective condition and 189 pre-model process boundaries; dynamic leak/mismatch counters zero |
| v337 complete project unit suite | 3625 passed on the final sealed source |
| v337 smoke / validation | 2/2 and 15/16; all eight audit-v5 reports valid/admissible |
| v337 fixed-189 | 157 pass / 32 fail / 0 environment failure; 83.07% |
| v337 strict audits | 6/6 valid and admissible; 1606 requests and 189 guest inventories; all leakage/integrity counters zero |
| v337 baseline registry | prospective config, seal, promotion record, report, and promotion-controlled current pointer verified |

Three standalone guest integration tests are not part of the unit count and require a persistent local guest
Adapter endpoint. The v249 fresh-VM smoke supplied the required deployed-runtime verification instead.

## v249 Clean-VM Smoke

The final smoke used one worker on each DGX and one fresh VM per task. Order 85 exercised strict deployment of
the full Multi-Apps Adapter stack; Order 165 exercised the historical VLC fullscreen/GUI-contract surface.

| Metric | Result |
|---|---:|
| Original evaluator | 2/2 |
| Route | 2 `generic_api_only` |
| Requests / steps | 27 / 27 |
| Valid audit-v4 workers | 2/2 |
| Request, identity, evaluator-URL leaks | 0 |
| Forbidden guest paths/cache-hash matches | 0 / 0 |
| Pre-model evaluator-boundary failures | 0 |
| Rewrite/injection/transport mismatches | 0 / 0 / 0 |
| Rejected invalid GUI proposals | 2, neither forwarded |

The frozen config SHA-256 is
`e0e597712ca8f098c1fba8f0461087337cea5e730efefc7bd78d213b3f050bd5`; the result SHA-256 is
`61eb6c1863c78824a8dfb178a254dbf81ea093cbcda339e49af6d295197ec650`. The machine-readable candidate seal is
`experiments/analysis-v249-clean-code-baseline/manifest.json`.

## v250 And v251 Gates

The v250 validation selected two source-order quantiles per domain without using prior outcomes. It completed
`15/16`, with all 16 routes `generic_api_only`, 194 model requests, no environment failures, and six of six
audit-v4 reports valid and baseline-admissible. The one normal model failure repeatedly inspected candidate
photos but never copied and archived them. See [the archived validation report](archive/generic-only-validation16-v250.md).

The v251 fixed-189 run was stopped by the user at `10 passed / 3 failed / 6 interrupted / 170 not run`.
Partial audit v4 found zero integrity violations across 13 completed tasks and 93 model requests, but the run and
all six partial audits are correctly baseline-inadmissible. Preserve the directory without resume or overwrite;
details are in [the interrupted-run report](archive/generic-only-fixed189-v251-interrupted.md).

## v337 Trusted Baseline

v337 used one source seal for the prospective smoke, validation, and fixed-189 gates. The fixed config was
created before any full-run result existed with `baseline_candidate=true`, `promotion_pre_authorized=true`,
`runs=1`, `resume=false`, and `best_of=false`.

| Metric | Result |
|---|---:|
| Pass / fail / environment failure | 157 / 32 / 0 |
| Binary success | 157/189, 83.07% |
| Reward sum / mean | 161.55996 / 0.85481 |
| Route | 189 `generic_api_only` |
| Captured requests | 1606 |
| Strict audits valid and admissible | 6/6 |
| Task identity, forbidden route, or evaluator URL leaks | 0 |
| Runner rewrite / injection / action mismatch | 0 / 0 / 0 |
| Process, guest-source, or request-integrity failures | 0 / 0 / 0 |

The source-tree SHA-256 is `2b62a1169272bee8d5c4a5dd25373a5d498b57af40a3af6a8910f5a31aa26aad`.
Evidence is sealed in `experiments/analysis-v337-trusted-fixed189-baseline/manifest.json`; see the
[v337 trusted baseline report](archive/generic-only-fixed189-v337-trusted.md) and immutable
[`experiments/baselines/v337.json`](../experiments/baselines/v337.json) promotion record.

## v335 Historical Result

v335 ran all fixed 189 non-OAuth tasks from Order 1 with six workers, three per DGX, `runs=1`, no proxy, no
resume, and a fresh VM per task. It completed in 2h 14m 42s and produced 1595 captured model requests and 1595
steps.

| Metric | Result |
|---|---:|
| Pass / fail / environment failure | 158 / 31 / 0 |
| Binary success | 158/189, 83.60% |
| Reward sum / mean | 162.5600 / 0.8601 |
| Strict audits valid and admissible | 6/6 |
| Task identity, forbidden route, or evaluator URL leaks | 0 |
| Runner rewrite / injection / action mismatch | 0 / 0 / 0 |
| Forbidden guest paths / cache-hash matches | 0 / 0 |

Evidence is sealed in `experiments/analysis-v335-clean-fixed189-baseline/manifest.json`; the detailed historical
report is [v335 result](archive/generic-only-fixed189-v335.md). The immutable old promotion record is
[`experiments/baselines/v335.json`](../experiments/baselines/v335.json). Do not edit it.

Under audit-v5, all six workers are invalid and baseline-inadmissible. The read-only recheck still found zero
dynamic task-identity leaks, forbidden-route calls, Runner argument changes, or execution mismatches across
1595 requests, but all 189 episodes lack the required pre-model process boundary and the old config lacks a
prospective condition. Static review also found the legacy answer-bearing Runner module reachable in the old
Agent process. The additive correction is
`experiments/analysis-v335-trust-boundary-adjudication/manifest.json`.

## v252 Clean Baseline

v252 ran all fixed 189 non-OAuth tasks from Order 1 with six workers, three per DGX, `runs=1`, no proxy, no
resume, and a fresh VM per task. It completed in 2h 16m 2s and produced 1911 captured model requests and 1882
steps.

| Metric | Result |
|---|---:|
| Pass / fail / environment failure | 132 / 56 / 1 |
| Binary success, valid scored episodes | 132/188, 70.21% |
| Pass rate over all scheduled tasks | 132/189, 69.84% |
| Reward sum / mean | 134.6379 / 0.7162 |
| Strict audits valid and admissible | 6/6 |
| Task identity, forbidden route, or evaluator URL leaks | 0 |
| Runner rewrite / injection / action mismatch | 0 / 0 / 0 |
| Forbidden guest paths / cache-hash matches | 0 / 0 |

The sole `environment_failure` was not a machine outage. The model selected `presentation.export` with PNG
format and a `.pptx` destination; the Adapter accepted the inconsistent pair and wrote PNG bytes over the
presentation path. This exposes a reusable format/extension contract gap.

Evidence is sealed in `experiments/analysis-v252-clean-fixed189-baseline/manifest.json`; the detailed report is
[v252 clean baseline](archive/generic-only-fixed189-v252.md).

## Post-Baseline Development

The durable ledger is `experiments/analysis-v252-failure-optimization/ledger.json`. Every candidate uses a new
config and run directory; no v252 artifact is resumed or rewritten.

| Candidate | Generic change | Strict A/B outcome |
|---|---|---:|
| v257 | Atomic native table completion semantics | 4/4 |
| v258 | Adapter-owned semantic slide-edge geometry | primary 4/4; secondary 3/4 |
| v259-v260 | All-textbox recovery and Adapter-confirmed completion equivalence | retained through later candidates |
| v261 | Separate single/multi role schemas and conservative live visual-title resolution | 3/4; core fix retained |
| v262 | Uniform-role versus ordinal-textbox action disambiguation | 4/4 |
| v263 | Current-media to active-presentation action staging and strict audio-path schema | 1/4 binary; staging core retained, complete candidate rejected |
| v264 | Exact post-search Adapter/action pairs and downstream parameter schemas | 3/5; all controls passed, route core retained, complete candidate rejected |
| v265 | Semantic VLC recording location resolved against active guest home | 3/3; affected task and both controls passed |
| v266 | Semantic stacked-pivot placement resolved from live Calc state | 3/3; affected task and both controls passed |
| v267-v271 | Physical units, grouped-picture observation, bound targets, and semantic picture roles | target converged; v271 exposed a clean-control navigation regression |
| v272 | Read-only slide navigation versus explicit deck-reorder routing | 3/3; affected task and both controls passed |
| v273 | Unresolved single-local-input discovery before consuming actions | 3/3; affected task and both controls passed |
| v274-v276 | Local-source discovery and persistent-output completion hypotheses | rejected; evidence preserved and source rolled back |
| v277 | Verified source/reference/edit/capture/read-back phase arbitration | 6/6; both affected tasks and all controls passed |
| v278 | Semantic VS Code configuration contracts and instruction-only action staging | 6/6; both affected tasks and four clean controls passed |
| v279-v280 | Semantic role-text update and UNO paragraph-alignment read-back normalization | role/update controls passed; Order 57 workflow remained |
| v281 | Atomic model-owned multi-slide textbox batch | 3/4; controls passed, document-order target semantics rejected |
| v282 | Deterministic live visual-order textbox ordinals | 4/4; affected Order 57 and all controls passed |
| v283 | Bitmap-filled and dominant live picture-container recognition | 1/3; reusable Adapter behavior retained, complete candidate rejected |
| v284 | Model-owned atomic multi-picture sizing and exact completion coverage | 2/3; controls passed, affected Order 55 failed, source restored to v283 |
| v285 | Model-owned Calc date-plus-duration derived column | 3/3; affected Order 25 and controls 23/28 passed |
| v286-v287 | Live Impress title-to-notes conflict semantics | v286 1/3; v287 3/3 with affected Order 43 and controls 42/44 passed |
| v288-v289 | Physical image insertion and consistent redundant slide references | v288 2/3; v289 3/3 with affected Order 48 and controls 31/46 passed |
| v290 | Live personal-information cleanup and clause-scoped title slide binding | 4/4; affected Order 54 and controls 51/53/58 passed |
| v291-v292 | Finite visible-terminal command plus semantic eligibility boundary | v291 3/4 and rejected; v292 4/4 with affected Order 146 and controls 141/143/144 passed |
| v293-v294 | Isolated command-line spreadsheet conversion plus active VS Code workspace discovery | v293 4/5 and rejected for Order 130 regression; v294 7/7 with affected Order 92 and six controls passed |
| v296-v297 | Rowwise single-column spreadsheet combination plus verified terminal launch | v296 4/4 reward but rejected for a failed action contract; v297 4/4 with affected Order 88 and controls 90/92/109 passed |
| v298-v300 | Active-workspace folder addition, named current-project workspace save, and verified completion context | v298 rejected after control 182 regressed; v299 4/4 but rejected its literal trailing-slash gate; unchanged-source v300 4/4 with affected Order 183 and controls 174/182/185 passed |
| v301-v303 | Header-first batch tables, standard-directory recovery, observed cardinality, explicit sorting, and true XLSX/ODS persistence | v301 1/3; v302 2/3; v303 2/3 with both controls passing and workflow corrected, but affected Order 95 remained content-inexact and is blocked after budget |
| v305-v306 | Semantic Thunderbird filtering and explicit conditionality | v305 2/3 after an omitted condition produced an unconditional rule; v306 3/3 with affected Order 154 and controls 155/160 passed |
| v307 | Verified prior-artifact path handoff | 1/4; no new binary pass, generic behavior retained, Order 127 reference inconsistency recorded |

The v262 run passed affected Order 61, retained Order 59, and controls 41/53. Both audit-v4 reports are
`valid=true`, `evidence_valid=true`, and `baseline_admissible=true` across 26 captured requests. All four routes
were `generic_api_only`; action mismatch, Runner rewrite/injection, Adapter trace mismatch, forbidden guest
artifact, task identity/golden exposure, and OSWorld tracked changes were all zero. The detailed chronology is
[v253-v262 Impress optimization](archive/generic-only-v252-optimization-v253-v262.md).

The v263 A/B reduced affected Orders 125 and 126 to three model-owned steps, with rewards `0.9961747823` and
`0.8042889576`. Both strict audits were admissible and all leakage, rewrite, injection, and mismatch counters
were zero. Binary acceptance failed because neither affected artifact was exact and clean control Order 128 had
an unrelated tool-search recall miss. See [v263 media-to-presentation staging](archive/generic-only-v263-media-presentation-staging.md).

The v264 A/B passed clean controls 111, 121, and 128. Both audit-v4 workers were admissible across 73 requests,
with every mismatch, rewrite, injection, forbidden-artifact, and leakage counter at zero. The exact route and
parameter contracts executed successfully on affected Orders 119/120, but Order 119 stalled after image export
and Order 120 reached only `0.9258519747` due segmentation fidelity. See
[v264 post-search route contracts](archive/generic-only-v264-search-route-contracts.md).

The v265 A/B passed affected Order 162 and controls 161/168 in two or three model-owned steps. For the affected
task, the raw model call, validated call, and Adapter payload all retained
`{"recording_location":"desktop"}`; only the VLC Adapter converted that public semantic value to
`/home/user/Desktop`. Both audit-v4 workers were admissible across seven requests with all mismatch, rewrite,
injection, forbidden-artifact, and leakage counters at zero. See
[v265 VLC semantic recording location](archive/generic-only-v265-vlc-recording-location.md).

The v266 A/B passed affected Order 24 and controls 23/27. On the affected task, all three raw model calls,
validated calls, and Adapter payloads retained `placement="below_existing_content"` and `gap_rows=1`; only the
Calc Adapter derived A2, A7, and A13 from live values, formulas, and pivot output. Both audit-v4 workers were
admissible across 22 requests with every mismatch, rewrite, injection, forbidden-artifact, and leakage counter
at zero. See [v266 Calc semantic pivot placement](archive/generic-only-v266-calc-pivot-placement.md).

The v267-v272 sequence converted an ambiguous selector-heavy picture operation into semantic
`picture.set_size` resolved from live document roles. v271 passed the affected task but exposed that a read-only
navigation search could retrieve destructive `slide.move`. v272 filtered that action unless the query or
instruction contains explicit whole-slide reorder semantics. Orders 58, 60, and 62 all passed; both audit-v4
workers were admissible across 33 requests with zero mismatch, rewrite, injection, forbidden artifact, or
leakage finding. See [v267-v272 Impress picture and navigation](archive/generic-only-v267-v272-impress-picture-routing.md).

The v273 A/B passed affected Order 115 and controls 113/114. Order 115 exposed only `filesystem.find` on its
first turn; Qwen selected the XCF glob, then passed the exact returned Desktop path unchanged to
`document.create_from_image`, structurally read the saved DOCX, and received reward `1.0`. Both controls stayed
outside the new stage and passed. The two audit-v4 workers were admissible across 11 requests with zero action
mismatch, Runner rewrite/injection, Adapter mismatch, GUI use, forbidden artifact, or leakage finding. See
[v273 Multi-Apps local input discovery](archive/generic-only-v273-multiapps-local-input-discovery.md).

The v277 A/B passed affected Orders 94/116, clean controls 90/91/109, and retained-fix control 115. Both affected
tasks completed in nine model turns: the model selected the observed source edit, `command.capture_output`, exact
output read-back, and `propose_done`. Both audit-v4 workers were admissible across 41 captured requests and six
guest inventories, with zero identity/golden leak, rewrite, injection, action mismatch, Adapter/GUI mismatch, or
forbidden guest artifact. The frozen pre-A/B ledger snapshot contained a bookkeeping-only Order 4/116 status
misassignment; the snapshot remains immutable, a correction record documents it, and the runtime config and run
always selected Orders 94/116. See
[v277 source execution phases](archive/generic-only-v277-source-execution-phases.md).

The v278 A/B passed affected Orders 177/181 and clean controls 176/180/185/187. The model selected
`debugging.configure` and `editor.configure` for the two affected tasks without a raw setting-key guess; all
model-facing arguments reached the Adapter unchanged. The run completed `6/6` through `generic_api_only` with
27 requests, 27 steps, seven Adapter calls, and no GUI action. Both audit-v4 workers were admissible, and every
task/golden, rewrite, injection, action mismatch, Adapter mismatch, guest-residue, and evaluator-boundary count
was zero. See
[v278 VS Code semantic configuration](archive/generic-only-v278-vscode-semantic-configuration.md).

The v279-v282 sequence resolved the remaining Impress alignment workflow without a task route. v281 reduced
Order 57 to one complete unchanged `slides.format_textboxes` call, but its internal document-order ordinal
selected lower text objects and failed the evaluator. v282 retained the same public model call and resolved
`position=1` by live top-to-bottom order, producing paths `[6]`, `[8,0]`, and `[3,1]`. Order 57 and
controls 47/52/53 passed `4/4`; both audit-v4 workers were admissible across 22 requests with zero identity or
golden leak, rewrite, injection, action/Adapter mismatch, forbidden guest artifact, or GUI action. See
[v279-v282 Impress textbox semantics](archive/generic-only-v279-v282-impress-textbox-semantics.md).

The v283-v284 sequence exhausted three materially different hypotheses for Order 55. v284's two workers were
strict-audit-v4 admissible across 44 requests with zero leakage, rewrite, injection, action mismatch, Adapter
mismatch, guest residue, or evaluator-boundary failure. The model's complete first batch used
`foreground_content`; live preflight reported a `slide_cover` candidate, and the model corrected the roles.
LiteAgent then rejected that corrected call because it had inferred and locked roles absent from the public
instruction. Since the affected task still failed, v284 was rejected and every v284 source change was removed.
The restored tree matches v283's exact source seal and passes 2980 unit tests. See
[v283-v284 picture-size hypotheses](archive/generic-only-v283-v284-impress-picture-sizes.md).

The v285 A/B passed affected Order 25 and clean controls 23/28. Qwen selected
`table.add_date_offset_column` with the live sheet, range, two headers, `duration_unit="days"`, and output
header; those raw arguments reached the Calc Adapter unchanged. The Adapter verified nine formulas, Qwen saved
and read back `C1:C10`, and the original evaluator returned `1.0` in five turns. Both audit-v4 workers were
admissible across 18 requests with zero identity/golden leak, rewrite, injection, action/Adapter mismatch, GUI
call, forbidden guest artifact, or evaluator-boundary failure. See
[v285 Calc date offset](archive/generic-only-v285-calc-date-offset.md).

The v286-v287 sequence added `slide.copy_title_to_notes`. In v286 the model selected the correct action, slide,
conflict policy, and title formatting, but LiteAgent rejected `replace` from instruction wording before the
Adapter could use the observed empty notes. v287 preserves that model-selected policy and lets the Adapter
apply it against live state. Order 43 then passed in five turns; controls 42/44 also passed. Both audit-v4
workers were admissible across 17 requests with zero leakage, rewrite, injection, action/Adapter/GUI mismatch,
guest residue, or evaluator-boundary failure. See
[v286-v287 Impress title notes](archive/generic-only-v286-v287-impress-title-notes.md).

The v288-v289 sequence replaced brittle raw image geometry with a reusable local-path/file-URL and physical
measurement contract. v288 proved Qwen selected the correct path and two 1 cm values, but rejected its redundant
yet consistent `slide=1` and `slide_number=2` pair. v289 accepts that pair only when the two public
representations identify the same slide, preserves both fields unchanged, and rejects conflicts. Order 48 then
passed in six turns; controls 31/46 also passed. Both audit-v4 workers were admissible across 20 requests with all
leakage, rewrite, injection, action/Adapter/GUI mismatch, guest-residue, and evaluator-boundary counters at zero.
See [v288-v289 Impress image insertion](archive/generic-only-v288-v289-impress-image-insertion.md).

v290 added `slide.remove_personal_information`, a reusable Adapter-owned live-content operation. Qwen selected
`slide=3` and `include_adjacent_icons=true` unchanged; the Adapter found five contact records across address,
email, phone, social, and URL categories, removed those plus five geometrically adjacent icons, and verified
zero matching records remained. The independent title-format call targeted only slides `[1,2]`; the cleanup
slide was excluded by clause-scoped parsing. Order 54 passed in seven turns and all controls retained reward 1.
Both audit-v4 workers were admissible across 25 requests with zero leak, rewrite, injection, mismatch, GUI,
guest-residue, or evaluator-boundary finding. See
[v290 Impress personal-information cleanup](archive/generic-only-v290-impress-personal-information.md).

v291 introduced `terminal.show_output`, which accepts an exact finite model-selected argv and resolves the live
working directory from the focused terminal or Files window inside the OS Adapter. Order 146 passed in two turns,
but the broad catalog exposure regressed clean file-copy control Order 143, so the complete candidate was
rejected. v292 added an instruction-semantic eligibility boundary: terminal-output instructions retain the
action, while unrelated copy, text mutation, and permission workflows cannot retrieve it even after catalog
expansion. Orders 141/143/144/146 then passed `4/4`; both audit-v4 workers were admissible across 21 requests,
with zero task/golden leak, rewrite, injection, action/Adapter/GUI mismatch, guest residue, or evaluator-boundary
failure. See [v291-v292 visible terminal output](archive/generic-only-v291-v292-visible-terminal-output.md).

v293 routed explicit command-line spreadsheet conversion to the isolated-profile
`document.convert_batch` contract and made `filesystem.find` roots explicitly model-selected. Order 92 passed,
but clean Order 130 regressed after the model guessed project paths, so v293 was rejected. v294 added
`workspace.find_files`: the VS Code Adapter resolves the live active workspace and searches only model-selected
globs, failing closed on absent or ambiguous state. Order 130 then used five exact returned paths for
`document.create_from_text_files`, while project-open control 175 stayed on `workspace.open`. All seven tasks
passed `generic_api_only`; both audit-v4 workers were admissible across 85 requests, with zero task/golden leak,
rewrite, injection, action/Adapter/GUI-command mismatch, executed GUI call, guest residue, or evaluator-boundary
failure. Twelve invalid GUI proposals were rejected before execution and remain recorded as an efficiency
residual, not successful GUI actions.

v296 added `spreadsheet.concatenate_single_columns` and `spreadsheet.open_in_terminal`. Qwen selected both input
paths, the output path, `separator_style="single_space"`, overwrite policy, and terminal-open path unchanged;
the first action verified a 5,001-row one-column CSV. The evaluator and all controls passed, but v296 was
rejected because the OS worker supplied no default verification specs for `terminal.launch`, so the visible
launch was recorded `executed=false` and the model looped through 30 steps. v297 added a generic verifier for
exact argv, launch status, visible window, child status, and requested history. The same affected workflow then
completed in four turns, both actions were `executed=true`, and controls 90/92/109 passed. Both audit-v4 workers
were admissible across 15 requests with every leak, rewrite, injection, action/Adapter/GUI mismatch, guest
residue, and evaluator-boundary counter at zero. See
[v296-v297 spreadsheet column workflow](archive/generic-only-v296-v297-spreadsheet-column-workflow.md).

v298 added a reusable active-workspace folder operation. Its affected Order 183 passed, but clean control Order
182 exposed a separate semantic gap: the model used the lower-level `workspace.write` contract and guessed the
wrong workspace filename. v299 added `workspace.save_current_project`, whose model-selected `directory` and
`workspace_name` are resolved against the observable active project only inside the VS Code Adapter. All four
episodes passed and strict audit-v4 was clean, but the candidate was rejected because its frozen acceptance
gate required a byte-identical trailing slash. v300 changed only that offline gate to predeclared filesystem
path equivalence and independently repeated the same four-task condition; affected Order 183 and controls
174/182/185 passed `generic_api_only`, with exact model-call-to-Adapter arguments and no forwarded GUI. See
[v298-v300 VS Code workspace semantics](archive/generic-only-v298-v300-vscode-workspace-semantics.md).

v301-v303 addressed a PDF-to-spreadsheet workflow through three bounded hypotheses. In v303 the affected
episode consumed all four publicly observed inputs, wrote four model-supplied rows, executed a model-selected
sort, saved genuine OOXML, read back the complete table, and finished in eight steps. The evaluator still
returned zero because the model changed the full-name representation, shortened one affiliation, and selected
a header synonym outside the evaluator rule. Both controls passed; all 15 captured requests passed strict
audit-v4 with zero leak, rewrite, injection, mismatch, GUI execution, guest residue, or evaluator-boundary
failure. The generic contracts remain, but Order 95 exhausted its three-hypothesis budget. See
[v301-v303 spreadsheet batch lifecycle](archive/generic-only-v301-v303-spreadsheet-batch-lifecycle.md).

v305 replaced strict exposure of raw Thunderbird filter storage with `filters.configure`. Its affected episode
still failed because the model omitted conditions and the valid semantic default produced an unconditional
rule. v306 made that choice explicit: `criteria` requires at least one complete model-selected condition, while
`all_messages` requires an explicit empty array. Order 154 then supplied the intended condition and destination
unchanged, the Adapter compiled and verified the native rule, and controls 155/160 also passed. Both audits were
admissible with all leakage, rewrite, injection, mismatch, GUI, guest-residue, and evaluator-boundary counters
at zero. See [v305-v306 Thunderbird filter contract](archive/generic-only-v305-v306-thunderbird-filter-contract.md).

v307 constrained a downstream typed path only to compatible local files observed in a preceding successful and
verified Adapter result. Orders 125/126/127 all used the exact model-selected observed path, and both audit-v4
workers were admissible across 17 requests with every integrity counter at zero. The A/B added no binary pass:
Order 125 retained a media-fidelity residual, while offline post-evaluator analysis proved Order 127's golden
image is absent from its attached DOCX. The behavior remains as reusable grounding; Order 125 is blocked after
budget and Order 127 is `data_reference_inconsistent`. See
[v307 verified artifact handoff](archive/generic-only-v307-verified-artifact-handoff.md).

Phase 3 re-audited the five partial-reward items against immutable v307 traces and prior bounded work. Orders
87/126 conflict with the requested media timestamps, Order 120 requires one author's exact foreground mask,
and Orders 125/163 require waveform or codec boundaries that no standards-compliant generic backend reproduced.
All five instruction-relevant operations were already model-selected and verified. A disposable Ubuntu 22.04
codec matrix for Order 163 confirmed that current FFmpeg remained the best generic result; default FFmpeg and
standalone LAME scored lower. No runtime source changed and no expected artifact entered deployment. The
machine-readable phase record is
`experiments/analysis-v307-residual-optimization/phase3-completed-v326.json`.

On 2026-09-08, the preserved VS Code debug-variables retest exposed one remaining recovery-surface weakness:
when a command wrapper contained a useful nested `details.stderr` diagnostic, the model-facing failure summary
could collapse it to the generic `command failed` message. The recovery surface now keeps a bounded, sanitized
stderr/recovery hint (preferring concrete diagnostics over generic wrappers) and repeats the failed action's
parameter-placement guidance on its recovery turn without changing model arguments or schemas. Focused recovery
checks passed 110/110, canonical v2 tests passed 1,661/1,661, and Ruff passed. This isolated repair does not
change the immutable 119/189 hybrid reference or the promoted v337 baseline.

On 2026-09-09, Order 20 Calc text transformation was recovered. The preserved
failure had the model select a header-inclusive `B1:B29` to `C1:C29` transform,
which correctly executed but replaced the destination header. The Calc action
and parameter descriptions now explicitly say that every selected cell is
transformed, headers are not auto-detected, data-only cleaning starts below the
observed header, and the destination is one top-left cell. Focused checks passed
17/17 and Ruff passed. The first affected/control replay remained
Order 20 failed and Order 63 passed; a reviewed, non-comparable draft attempt
was interrupted before scoring. The corrected affected-only v3 replay then
selected `B2:B29` to `C2` and passed Order 20 with reward 1.0 and final
integrity `ok`. See [Hybrid Calc text-transform header retest](archive/hybrid-calc-text-transform-header-retest-20260909.md).

This isolated repair does not change the immutable 119/189 hybrid reference or
the promoted v337 baseline.

On 2026-09-09, Order 15 received a minimal generic chart-source description
clarifying that a requested total/value series must be passed separately from
its component columns. Focused checks passed 17/17 and Ruff passed. The
affected-only replay was stopped after two repeated invalid calls: the model
guessed `Sheet2` and supplied a comma-joined range string, received the native
`SHEET_NOT_FOUND` error, then repeated the invalid range on `Sheet1`. No chart
was created and no scored result was produced; the partial evidence is
preserved in the dated archive report. Order 15 was unresolved at that early
checkpoint; its subsequent v4 pass and the Order 2 follow-up are recorded in
the dated entries above.

## Current Failure Analysis

The active queue is the 70 non-passing episodes from the preserved Qwen-Holo hybrid full-189 condition, not the
32 failures from the older v337 baseline and not the v393 diagnostic queue. Its immutable terminal breakdown is
119 passed, 33 evaluator failures, 21 Agent deadline exits, 12 model protocol failures, 3 environment failures,
and 1 Agent failure. Use the preserved trajectory for each selected task and keep isolated reruns as per-task
evidence; passes from different source seals do not define a new aggregate score.

Historical v393, v395-v398, v337, v335, v307, v252, and v247 analyses above remain useful only for their stated
conditions. They do not override the current repair source in
[Current Qwen-Holo Repair Reference](current-repair-reference.md).

## Next Gate

1. Select one of the 70 hybrid non-passing tasks and diagnose its preserved trajectory before changing runtime
   behavior.
2. Prefer a focused deterministic test, then run the affected task; add a stable control when the change is shared
   or a meaningful control exists. Preserve every attempted result and stop an unchanged negative replay.
3. Keep the Qwen orchestration, Holo grounding, unified event ledger, Qwen result audit, and same-VM soft restart
   architecture intact. Do not inject model arguments or use evaluator data during an episode.
4. Record isolated outcomes here and in a dated repair report. Do not change the 119/189 numerator without one
   integrated frozen rerun of the selected scope.
5. Keep v337 as the only promoted baseline. A new fixed-189 run requires explicit user authorization and a new
   frozen condition; never modify or resume prior evidence.
