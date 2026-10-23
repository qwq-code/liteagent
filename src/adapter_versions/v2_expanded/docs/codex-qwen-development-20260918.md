# Codex source development experiment — 2026-09-18

User authorized a source-based Codex test version with automatic incremental
compilation through `cargo run`. This is a separate development experiment;
previous evaluation and repair queues remain paused.

## Issue and verification target

The available Codex source only speaks Responses. The Qwen3.5-4B endpoint speaks
Chat Completions. Add an opt-in protocol conversion to the existing Rust proxy,
retain the existing Codex loop, and expose atomic desktop operations through MCP.
Use a small model-specific catalog and prompt, with host shell/edit tools disabled.

Deterministic checks: compile/start CLI, exercise protocol translation, and run a
synthetic local round trip including screenshot, erroneous tool arguments, corrected
arguments and final response. Model-backed hypothesis: Qwen can complete a short
synthetic instruction through this same transport, with binary thinking recorded.
Stop the synthetic probe at an HTTP/protocol error or its 240-second timeout; do not
start OSWorld episodes or any evaluator. All such probes are non-promotable and
are not benchmark task passes.

## Source and environment

- Independent fork: `/home/liuhao/codex-qwen`, branch `codex/qwen-computer-use`.
- Base: `70b5cfc73b25458a7af225d24b16ef4794f8f380`.
- Rust 1.95.0 installed with rustup, including rustfmt/clippy/rust-src.
- The unmodified CLI built and printed help. The successful build invocation took
  5m 06s after earlier missing-library-discovery attempts.
- This host has OpenSSL headers/libraries, but no pkg-config executable. The
  development wrapper supplies `OPENSSL_LIB_DIR=/usr/lib/x86_64-linux-gnu` and
  `OPENSSL_INCLUDE_DIR=/usr/include`.
- Cargo's 13 GiB initial target directory was moved from the original inspection
  worktree into the independent fork for reuse. Source in the original worktree
  is unchanged. No installed Codex binary was replaced.

The development runner uses an independent configuration and empty workspace per
invocation. Its default budgets are 100 tool calls and 1800 seconds; build time is
outside the episode budget. It saves requests, responses, MCP calls and selected
configuration under a new run directory. No credentials are included in reports.

## Verification results

- Focused Rust proxy suite: 16 passed. Focused desktop MCP suite: 7 passed.
- Fork CLI rebuilt successfully in 4m 34s after changing the checkout path.
  An unchanged `run-dev.sh --version` invocation took 11.2s including Cargo's
  cached build check; the binary printed `codex-cli 0.0.0`.
- First full synthetic round trip exposed an SSE item lifecycle mismatch:
  `ReasoningRawContentDelta without active item`. Stopped the attempt after the
  first fake model request, before any desktop call. Preserved evidence:
  `/tmp/codex-qwen-roundtrip.K6YXv8/`. The next change buffers one model response
  and emits ordered item-added/item-done pairs after complete upstream output.
- That Rust correction rebuilt in 25.53s. The second attempt completed the four
  fake model rounds but its MCP calls were rejected by Codex's default tool
  approval setting under a read-only host sandbox. Evidence:
  `/tmp/codex-qwen-roundtrip.bntOSo/`. Set the existing
  `default_tools_approval_mode = "approve"` only for this explicitly configured
  desktop MCP server; retain the host sandbox and disabled local tools.
- Initial request inspection confirmed the short desktop prompt, the 9 desktop
  tools and 3 built-in MCP resource tools; no shell or source-edit tools.

- Corrected synthetic round trip completed in 18.125s, with four fake model
  requests, one screenshot, one rejected click missing `y`, and exactly one
  corrected click reaching the fake guest. Both the error/schema and successful
  result returned to the next model request. Evidence:
  `/tmp/codex-qwen-roundtrip.E4pEEq/`. The raw mock report's last assertion is false
  because its original checker did not parse Codex's `Wall time…Output…` text
  wrapper. After fixing that scratch checker, offline verification of the same
  preserved output passed all 8 assertions. The original report was not changed
  (SHA256 `b733167376b8c0ce67bcc1135229b2cf4e5ee765fb2e848defee012d4bf12cc8`).
- Real Qwen3.5-4B probe completed in 28.605s, using `thinking`, two upstream
  requests, and one MCP screenshot call. The prompt asked it to observe the
  synthetic image and identify the central rectangle's color without interacting.
  It correctly answered blue with a light-gray background. The fake desktop
  recorded one screenshot and zero execute requests. Evidence:
  `/tmp/codex-qwen-live.YmQimd/`, including `run/run.json`, `run/events.jsonl`,
  `run/wire/` and `desktop-report.json`. Its temporary timeout was 240 seconds;
  the runner's default remains 1800 seconds and 100 calls.
- Ruff and whitespace checks passed. Probe processes were stopped after the
  checks. All outcomes above are development checks, not scored task results.

The setup and synthetic checks above did not start OSWorld episodes. A later
user-authorized test of two previously failed tasks is recorded in the
[isolated trial report](archive/codex-qwen-failed-task-trial-20260918.md): both were
interrupted after repeated coordinate misses, and both post-stop evaluators returned
0. Existing experiment queues remain paused.

## Action observations and OCR — 2026-09-18

User requested borrowing useful computer-use behavior and adding OCR. The initial
MCP returned only an execution receipt after GUI actions, requiring another model
call to see the result. Verification target: return that receipt, a fresh PNG and
OCR of those exact pixels in the same result; preserve executed=true if the
additional observation fails, and keep every click and its arguments model-selected.

Successful GUI actions (including wait) now return a screenshot automatically.
Independent screenshot numbering prevents filename collisions across observations;
post-action observation trace fields do not overwrite the execution HTTP status.
The OCR helper uses the installed host Tesseract with sparse-text segmentation,
English by default, a five-second limit bounded by the remaining episode deadline,
and one OpenMP thread. It returns text lines with original-pixel boxes, centers and
confidence, limited to 100 lines and 6000 compact-JSON characters. Truncation is
explicit. It neither alters the PNG nor automatically selects a target or action.
Missing OCR dependencies, language data and timeouts leave the PNG usable and return
an observation error. If a post-action screenshot fails, the executed action remains
successful and the model is asked to observe the state before choosing its next step.

The same nine GUI tools remain exposed. Descriptions and the short model prompt now
explain the returned observation, OCR coordinate format and its limitations. The
runner passes `--ocr-language` / `--no-ocr` and records the configuration in run.json.
The current host has Tesseract 4.1.1 with eng/osd data; Chinese OCR requires an
additional language pack. There is no new Python dependency, evaluator gate or
benchmark-specific behavior.

Changed files: desktop_mcp.py, new screenshot_ocr.py, run_codex_qwen.py, the desktop
instructions and README, and the two focused test modules. MCP/OCR checks: **18
passed**, including real Tesseract recognition of a synthetic image, original-pixel
coordinates, updated images across actions, OCR failure, screenshot failure, disable
mode, unchanged call limits and correction of invalid tool arguments. Ruff and
format checks passed. These are development checks, not benchmark improvements.

One local synthetic round trip through the actual runner, Rust bridge and MCP also
passed **19/19 assertions**, with fake model and guest endpoints. Four Chat requests
contained the initial BEFORE image/OCR, a visible missing-y error, and the corrected
click's new AFTER image/OCR with pixel coordinates and matching image hashes. The
new image remained associated with the corrected click's tool result; exactly one
execute and two screenshot requests reached the guest. Runner and mock both exited
0; runtime was 3.591 seconds. OCR settings were present in run.json. Evidence:
`/tmp/codex-qwen-post-observation.2S4psX/summary.json`. No live-model accuracy or
benchmark gain is claimed from this synthetic transport check.

## OCR text clicks (follow-up)

After two interrupted failed-task trials exposed likely coordinate-convention
confusion, the user requested OCR-based clicks. Current click/double_click accept
literal `text` from the latest OCR list and `occurrence` when matches repeat;
raw pixel input and drag are removed. An intermediate ID-based contract exposed
model mistakes associating IDs with text and was replaced by this simpler form.
The eight-tool surface exposes text/confidence while preserving boxes and exact
text-to-center conversion in host traces. Keyboard tools cover non-text interactions
when feasible. The model still selects every target and action. No evaluator gate
was added. Actions wait 0.5 seconds before observation unless the model specifies
a different delay. Updated MCP tests: 17 passed; OCR tests: 6 passed; Ruff passed.
The final text-click trials reached actual account/signature and folder targets.
Order153 still failed due to missing newline and false completion; Order155 ended
with a model-transport failure after unsuccessful starring. Both post-episode
evaluators returned 0. The newly frozen affected-task retries and their outcomes belong in the
[trial report](archive/codex-qwen-failed-task-trial-20260918.md).

## Entry points

- Usage: `integrations/codex_agent/README.md`.
- Launch: `.venv-qwen-agent/bin/python scripts/run_codex_qwen.py --prompt 'Reply with READY.'`
  from the v2 directory. This automatically builds the independent Rust fork.
- Provide `--guest-url` for a selected, already-running OSWorld guest; provide
  `--adapter-urls-json` only when existing deployed Adapter actions are needed.
- The OSWorld integration consists entirely of new files; unrelated working-tree
  changes are preserved. Fork changes remain local and uncommitted.
