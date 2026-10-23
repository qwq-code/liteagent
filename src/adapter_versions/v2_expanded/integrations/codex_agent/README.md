# Codex + Qwen development runner

This experiment keeps the Codex agent loop and connects Qwen3.5-4B through an
opt-in Responses-to-Chat-Completions bridge in the independent Codex checkout
at `/home/liuhao/codex-qwen`. Desktop operations use the MCP server in this
directory. The runner is for development; it does not invoke an OSWorld evaluator
or produce a benchmark score.

## Run

From `/home/liuhao/computer_use/adapter_versions/v2_expanded`:

```bash
.venv-qwen-agent/bin/python scripts/run_codex_qwen.py \
  --prompt 'Reply with READY.'
```

The runner automatically invokes `cargo run` to rebuild changed Rust code. Build
time is outside the task timeout. An unchanged build uses the Cargo cache. Use
`--skip-build` only when deliberately reusing the existing binary.

For an already-running desktop, provide its explicit OSWorld HTTP URL:

```bash
.venv-qwen-agent/bin/python scripts/run_codex_qwen.py \
  --guest-url http://GUEST_ADDRESS:5000 \
  --prompt 'Describe the current desktop screenshot without changing anything.'
```

Defaults are model `qwen3.5-4b`, endpoint
`https://qwen.jinmaoapi.cc.cd/v1`, `thinking`, 100 tool calls, and 1800 seconds.
`--reasoning-mode non_thinking` explicitly disables Qwen thinking. The per-request
limits are 4096 output tokens and 240 seconds. Set `QWEN_API_KEY` in the environment
if the endpoint requires authentication; the key is passed to the bridge over
stdin and is not saved to the run configuration.

The desktop server exposes screenshot, click, double_click, type, press, hotkey,
scroll and wait. Clicks select visible OCR text from the latest screenshot, for
example `click({"text":"Save"})`. Matching ignores case and repeated whitespace,
prefers exact text, then permits a literal substring. Multiple matches require an
explicit `occurrence` (1-based in OCR list order). The server resolves the selected
text's OCR box center. Raw-coordinate clicks and drag are not exposed. The
keyboard `type` action currently supports ASCII; Unicode entry needs an existing
Adapter capability. Add `--adapter-urls-json /absolute/path/adapters.json` to
expose the selected Adapters' existing public actions, with JSON such as
`{"vlc":"http://GUEST_ADDRESS:ADAPTER_PORT"}`.

Every successful GUI action returns a fresh screenshot in the same tool result.
Screenshots also include best-effort Tesseract OCR: visible text and confidence.
Choose text from the latest observation in click or double_click. Coordinates and
internal screenshot references remain host-side in the trace alongside the
model-selected text, any occurrence and the resolved box/center under the
`ocr_text_center.v1` conversion contract. OCR runs locally on
the exact PNG returned to the model, with a five-second maximum (within the
remaining episode deadline), one CPU thread, and bounded text output. It adds no
tool call. OCR or post-action screenshot failure preserves the successful action
receipt, so the model can inspect state without blindly repeating the action.
Actions wait 0.5 seconds by default before taking the next screenshot; an explicit
`seconds` argument overrides this. Actions invalidate old observations even if
their new screenshot fails. A label may
not be clickable; for icons and unlabeled fields, use keyboard navigation or an
application shortcut and inspect the resulting image. No target is automatically
selected from the instruction. OCR currently does not solve non-text grounding.

The default language is `eng`. This host already has Tesseract and English data;
another host needs the `tesseract-ocr` and `tesseract-ocr-eng` packages. Use
`--ocr-language eng+chi_sim` only after installing the additional language data,
or `--no-ocr` for image-only observations with keyboard tools (OCR clicks are then
unavailable). A missing executable or language pack
returns an OCR error alongside the usable PNG. OCR settings are recorded in
`run.json`; per-screenshot output and elapsed OCR time are in the desktop trace.

## Artifacts and isolation

Each invocation creates a private directory under
`experiments/work/codex-qwen/` containing `run.json`, isolated Codex configuration,
`events.jsonl`, stderr logs, protocol request/response dumps, tool calls and PNGs.
`completed` means the Codex turn finished; it is not evaluator-confirmed task
success. Errors include the tool's parameter schema and return to the model for
correction. Local shell/edit tools and the default coding prompt are disabled.
Codex's built-in MCP resource discovery tools remain available.

The installed system Codex and its login are not changed. To run the source CLI
directly (without this isolated Qwen configuration):

```bash
bash /home/liuhao/codex-qwen/run-dev.sh --help
```

See `../../docs/codex-qwen-development-20260918.md` for the implementation and
verification record. No full benchmark run is started by setup or these probes.
