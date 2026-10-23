# Environment Handoff

> Historical environment snapshot from 2026-08-29. It is useful for provenance but is not the current repair
> reference or an authoritative endpoint inventory. Use the active condition config and
> [`current-repair-reference.md`](current-repair-reference.md) for current work.

Snapshot: `2026-08-29T11:52:00Z`

This is an operational handoff for another agent. It records the environments that
already exist and how to use them. It is not a benchmark result and must not be used
to replace the trusted v337 baseline.

## Read First

1. Read `/home/liuhao/computer_use/AGENTS.md`.
2. Use `adapter_versions/v2_expanded/` as the only active source tree.
3. Treat `adapter_versions/v1_baseline/`, v337 evidence, and the OSWorld checkout as immutable.
4. The worktree is intentionally dirty. Inspect `git status` and do not reset, clean, or
   overwrite unrelated changes.
5. The previous development experiment has been stopped and its evidence is immutable.
   Check the result directory before starting any new condition; do not reuse or overwrite it.

## Access

| Alias | Host | User | Purpose |
|---|---|---|---|
| `dgx1` | `192.168.0.224` (`spark-1152`) | `liuhao` | Qwen3.5-4B and Holo3.1-4B |
| `dgx2` | `192.168.0.138` (`spark-2271`) | `liuhao` | Qwen3.8-27B shared-context service |

The aliases are defined in the current host's `~/.ssh/config`. A new agent or host
needs its own authorized key and must verify access with `ssh dgx1` and `ssh dgx2`.
Passwords, API keys, HF tokens, VNC passwords, and cookies are deliberately not stored
in this file or in the repository; inject them through the agent's secret store or a
private shell environment.

## Local Development Host

- Path: `/home/liuhao/computer_use`
- Host: `v100-server`, Ubuntu 22.04.5, Python 3.13.9, Docker 29.1.3
- Git branch: `experiment/v337-bounded-decomposition`
- Verify the exact checkout with `git rev-parse HEAD` (this handoff file is versioned,
  so a later documentation commit will necessarily change HEAD).
- Active code: `/home/liuhao/computer_use/adapter_versions/v2_expanded`
- OpenAPA environment: `adapter_versions/v2_expanded/.venv-openapa`
- Optional Qwen-Agent environment: `adapter_versions/v2_expanded/.venv-qwen-agent`
- OSWorld checkout: `third_party/OSWorld`, commit
  `091f5ef1d5544bc74953c77875d5feb5bed30108`
- Base VM: `third_party/OSWorld/docker_vm_data/Ubuntu.qcow2` (read-only backing image)
- OSWorld cache: `third_party/OSWorld/cache`
- OpenAPA checkout: `third_party/OpenAPA`
- Trusted baseline pointer: `adapter_versions/v2_expanded/experiments/baselines/current.json`
  -> v337, `157/189` (`83.07%`), zero environment failures.

This handoff was written while the root `README.md` still contained historical wording about Git being disabled.
The workspace has a Git repository; use `git status` and `git log` as the source of truth. The root-level Adapter
directories are historical snapshots.

### Dated Local Experiment Snapshot (Not Latest)

At the time of this 2026-08-29 snapshot, the following non-promotable six-task diagnostic condition had been stopped
at its 60-minute time box after four model requests remained in long retries. It is not the current experiment:

```text
experiment: qwen35-recovery-architecture-cohort6-thinking16k-dgx1-concurrency6
result:     adapter_versions/v2_expanded/experiments/
            qwen35-recovery-architecture-cohort6-thinking16k-dgx1-concurrency6-run1
workers:    6
model URL:  http://192.168.0.224:8001/v1
status:     interrupted (1 pass, 1 scored failure, 4 unscored interruptions)
```

Its supervisor was `scripts/supervise_lite_agent_parallel.py`; the machine-readable
status is `...-run1/results.json`. The condition used `thinking=true` and a
16,384-token output ceiling. Qwen3.5's native control is the binary
`enable_thinking` switch; this older condition did not use a numeric provider
effort tier. Do not mix this result with v337 or call it a baseline.
The detailed outcome is archived in
`docs/archive/qwen35-recovery-cohort6-2026-08-29.md`.

## Model Services

At the time of this snapshot, all services were OpenAI-compatible vLLM HTTP endpoints and accepted a
placeholder API key (`EMPTY`); this is an internal-network deployment, not an
authentication boundary.

### DGX1

| Container | Base URL | Model | Context | Sequences | Image | Status |
|---|---|---|---:|---:|---|---|
| `qwen35-4b` | `http://192.168.0.224:8001/v1` | `Qwen/Qwen3.5-4B` | 65,536 | 6 | `local/vllm-qwen35:26.07-xgrammar-0.2.4` | running |
| `holo31-4b` | `http://192.168.0.224:8002/v1` | `Hcompany/Holo-3.1-4B` | 65,536 | 6 | `local/vllm-qwen35:26.07-xgrammar-0.2.4` | running |

Both services enabled the Qwen reasoning parser, automatic tool choice, and the
`qwen3_coder` tool-call parser. Holo was being exercised by a separate native GUI
runner in this snapshot; the later Qwen-Holo hybrid repair reference is documented
in [`current-repair-reference.md`](current-repair-reference.md) and is not part of
the LiteAgent v337 score.

Useful checks:

```bash
curl -fsS http://192.168.0.224:8001/v1/models
curl -fsS http://192.168.0.224:8002/v1/models
ssh dgx1 'docker ps --filter name=qwen35-4b --filter name=holo31-4b'
```

### DGX2: Shared 256K Backend With Queueing

One model process serves both ordinary and occasional long requests:

| Layer | Address | Role |
|---|---|---|
| Public short endpoint | `http://192.168.0.138:8001/v1` | concurrent short/test requests |
| Public long endpoint | `http://192.168.0.138:8003/v1` | one long request; others wait |
| Private vLLM backend | `127.0.0.1:8101` on DGX2 | `qwen38-27b-shared-256k` |

Backend configuration:

- Model: `Qwen/Qwen3.8-27B`
- Revision: `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`
- Image: `local/vllm-qwen38:26.07-transformers5.8.0`
- `max_model_len=262144`, `max_num_seqs=6`, `max_num_batched_tokens=16384`
- BF16, `gpu_memory_utilization=0.75`
- Measured KV pool: `565,393` tokens; vLLM reported `2.16x` full 256K requests
- Model cache: `/home/liuhao/models/qwen3.8-27b/hf-cache` (about 61G)

The gateway admits short requests concurrently until a long request is waiting. It
then drains short work, runs one long request exclusively, and resumes short work after
the long request finishes. The conservative policy avoids assuming that one 256K plus
six full 65K requests fit the measured KV pool.

Checks:

```bash
curl -fsS http://192.168.0.138:8001/v1/models
curl -fsS http://192.168.0.138:8003/v1/models
curl -fsS http://192.168.0.138:8001/queue/status
curl -fsS http://192.168.0.138:8003/queue/status
ssh dgx2 'docker ps --filter name=qwen38-27b-shared-256k'
```

The gateway is installed at `/home/liuhao/qwen38-context-gateway` on DGX2. Its PID and
log are `/home/liuhao/qwen38-context-gateway.pid` and
`/home/liuhao/qwen38-context-gateway.log`. The checked-in source and scripts are in
`deployment/qwen38-vllm/`.

The DGX2 gateway directory is a copied deployment snapshot, not a repository mount.
After changing the gateway, copy the files explicitly, compare hashes, and restart
only the gateway:

```bash
scp adapter_versions/v2_expanded/deployment/qwen38-vllm/{context_gateway.py,run_context_gateway.sh,stop_context_gateway.sh} \
  dgx2:/home/liuhao/qwen38-context-gateway/
ssh dgx2 'sha256sum /home/liuhao/qwen38-context-gateway/context_gateway.py'
```

The same rule applies to any manually copied model startup script. A source-tree change
does not change a running container or gateway until it is explicitly deployed.

Start or stop only the gateway with:

```bash
ssh dgx2 '/home/liuhao/qwen38-context-gateway/run_context_gateway.sh'
ssh dgx2 '/home/liuhao/qwen38-context-gateway/stop_context_gateway.sh'
```

The former 65K Qwen3.8 container is preserved as
`qwen38-27b-65k-rollback-20260829` (stopped). Do not delete it. The exact pre-switch
inspect record is `/home/liuhao/qwen38-context-gateway/rollback-65k-inspect.json`.
The shared 256K deployment is a new infrastructure condition, not v337 evidence.

## OSWorld Guest Runtime

The active Runner allocates `happysixd/osworld-docker` containers from the read-only
Ubuntu QCOW2. Adapter host ports are allocated dynamically to avoid collisions. At the
snapshot, the two development guests are:

| Guest | Owner label | Control | noVNC | Chrome CDP | Adapter range |
|---|---|---:|---:|---:|---|
| `lucid_shaw` | worker 01 of the active experiment | 5003 | 8006 | 9222 | 8765-8774 |
| `heuristic_joliot` | worker 02 of the active experiment | 5005 | 8007 | 9223 | 8775-8784 |

VLC is on 8080/8081. The VNC password is intentionally omitted; obtain it through a
private channel if interactive inspection is needed. Do not assume a fixed host port
for a newly allocated guest.

Relevant lifecycle code:

- `integrations/openapa_osworld/provider.py`: Docker allocation, KVM detection,
  dynamic ports, run-owner labels, and guest egress policy;
- `scripts/run_lite_agent_pilot.py`: one-tool-per-turn Runner and evidence capture;
- `scripts/supervise_lite_agent_parallel.py`: sharding, worker supervision, and cleanup;
- `scripts/strict_deployment.py`: generic-only package filtering.

Only remove a guest by its exact run-owner label after the corresponding worker has
finished. The local Docker host contains unrelated user services; never use a broad
`docker prune`, name wildcard, or volume deletion during handoff.

## Common Commands

```bash
cd /home/liuhao/computer_use/adapter_versions/v2_expanded
PYTHONPATH=. .venv-openapa/bin/python -m pytest -q tests/test_clean_boundaries.py tests/test_recovery_surface.py
ruff check integrations scripts tests
git diff --check
git status --short --branch
```

For an explicitly authorized model experiment at or after this snapshot, use a new result directory and record
the model reasoning mode (`thinking`/`non_thinking`), explicit
`enable_thinking` request, endpoint, source hash, VM condition, and concurrency.
For Qwen3.5, do not add a numeric `reasoning_effort`; reserve that field for a
provider with a documented tiered control. Do not reuse v337 evidence or overwrite
an existing result. The snapshot's instruction not to run a full fixed-189 campaign
was superseded only by later explicit authorization; consult the current reference
before scheduling one.
Model-free Adapter contract tests do not require a model endpoint.

## Handoff Acceptance Checklist

- [ ] `ssh dgx1` and `ssh dgx2` succeed with the receiving agent's authorized key.
- [ ] DGX1 ports 8001 and 8002 return the expected model IDs.
- [ ] DGX2 ports 8001 and 8003 return `qwen3.8-27b`; both queue snapshots are empty or
      reflect the work intentionally submitted by the receiving agent.
- [ ] The active local experiment is either left running or stopped explicitly with
      the owner's approval.
- [ ] No credentials, cookies, golden files, task manifests, or evaluator data are
      copied into the handoff or runtime package.
- [ ] The receiving agent has read `AGENTS.md` and understands that the shared 256K
      deployment is not a new benchmark baseline.
