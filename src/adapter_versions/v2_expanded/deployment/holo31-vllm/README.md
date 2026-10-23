# Holo3.1-4B vLLM Service

This deployment exposes the pinned `Hcompany/Holo-3.1-4B` revision on port `8002`.
It is an independently deployed GUI-model candidate and does not replace the trusted
Qwen/LiteAgent baseline.

Defaults:

- served model: `holo3.1-4b`;
- context length: 65,536;
- maximum concurrent sequences per host: 6;
- GPU memory utilization per host: 0.21;
- native Qwen reasoning and tool-call parsers enabled.

Run `./run.sh` on DGX1. Override settings through the named environment variables in the script;
do not store Hugging Face credentials in this directory.

## Deployed Endpoints

| Host | OpenAI-compatible base URL | Configured concurrency |
|---|---|---:|
| DGX1 (`192.168.0.224`) | `http://192.168.0.224:8002/v1` | 6 |

On 2026-08-29, DGX1 reported a 416,768-token KV cache, sufficient for 6.36 full 65,536-token
sequences. Six simultaneous requests containing a real screenshot and an OpenAI-compatible
native click schema returned `6/6` valid coordinate-bearing `tool_calls` in 3.113 seconds. This
verifies service concurrency, visual input, and tool-call transport. It is not an OSWorld task
result or a new Agent baseline.

## Resource Note

DGX1 currently serves Qwen3.5-4B and Holo concurrently. The former DGX2 Holo service was stopped
and retained as `holo31-4b-pre38-20260829` when DGX2 was consolidated onto Qwen3.8-27B. Recheck
available memory before restarting another memory-heavy workload on DGX1.
