# Qwen3.8-27B vLLM Service

This deployment serves the pinned BF16 `Qwen/Qwen3.8-27B` checkpoint on DGX2. It replaces
the duplicate DGX2 Qwen3.5 and Holo services after their stopped containers are preserved.

The plain `run.sh` entry point retains a 65K default for rollback and isolated use. The active
deployment uses `run_shared_256k.sh` plus the queueing gateway described below.

Plain `run.sh` defaults:

- pinned revision: `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`;
- served model: `qwen3.8-27b`;
- context length: 65,536;
- maximum concurrent sequences: 6;
- GPU memory utilization: 0.75;
- maximum batched tokens: 16,384;
- native Qwen reasoning and tool-call parsers enabled.

The startup acceptance gate is a reported KV capacity of at least 393,216 tokens, equal to
six full 65,536-token sequences. Service startup alone does not constitute an OSWorld result
or modify the trusted v337 baseline.

## Active Deployment

| Host | OpenAI-compatible base URL | Configured concurrency |
|---|---|---:|
| DGX2 (`192.168.0.138`) | `http://192.168.0.138:8001/v1` (short queue) | 6 short requests |
| DGX2 (`192.168.0.138`) | `http://192.168.0.138:8003/v1` (long queue) | 1 long request |

The active backend is private at `127.0.0.1:8101` and runs one pinned BF16 model instance with
`max_model_len=262144`, `max_num_seqs=6`, and utilization `0.75`. On 2026-08-29, all 18 weight
shards matched their Hugging Face LFS SHA-256 identifiers. vLLM reported 34.9 GiB of KV memory,
`565,393` KV tokens, and capacity for `2.16x` full 262,144-token requests. Both gateway ports
and the backend returned HTTP 200 health/model metadata after warm-up; no generation request was
used for this deployment smoke.

The replaced DGX2 containers remain available as stopped rollback points:
`qwen35-4b-pre38-20260829` and `holo31-4b-pre38-20260829`.

## Shared 256K Context Mode

The model weights do not need to be loaded twice to serve short and long requests. The
`run_shared_256k.sh` entry point starts one vLLM backend with `max_model_len=262144` on a private
host port (`8101` by default). `run_context_gateway.sh` can then expose two logical endpoints:

- `8001`: regular test traffic (`short` class); multiple requests may run concurrently.
- `8003`: occasional long traffic (`long` class); only one long request is admitted at a time.

The gateway gives a waiting long request priority after active short requests drain. While a long
request is active, new short requests wait as well. This is intentional: the measured KV pool holds
about 565K tokens, enough for one full 256K request plus four full 65K requests, but not one 256K
plus six full 65K requests. The gateway avoids relying on an unverified mixed-load overcommit.

This mode is a new deployment condition for personal use and must not be reported as the 65K
baseline. Keep the previous container stopped as a rollback point before switching ports.

## Cloudflare Ingress

The current lab Connector route is:

```text
https://qwen27b.jinmaoapi.cc.cd  ->  http://192.168.0.138:8003
```

The public hostname is an API endpoint, not a web page. `/` and `/v1` intentionally return
404; use `/docs`, `/v1/models`, or an OpenAI-compatible client with this base URL:

```text
https://qwen27b.jinmaoapi.cc.cd/v1
```

Use model name `qwen3.8-27b`. Because the route targets port `8003`, every request uses the
long-request queue and long generations are admitted one at a time. A separate hostname mapped
to `http://192.168.0.138:8001` is needed for ordinary multi-request test traffic. The current
origin accepts the placeholder key `EMPTY`; before exposing the hostname outside the lab, add a
Cloudflare Access policy or another authentication layer.
