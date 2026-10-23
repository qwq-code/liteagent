# OSWorld API v2

Updated: 2026-09-01

This is the only active source tree for the project. The root-level Adapter directories are historical copies;
the v1 directory is frozen.

## Current Work

The active objective is to repair the 70 non-passing tasks from the Qwen-Holo hybrid full-189 condition while
preserving Qwen orchestration, Holo visual grounding, the unified event ledger, result audit, and same-VM soft
restart. The condition completed 119/189 scheduled tasks (62.96%) and is exploratory/non-promotable. Read the
[current repair reference](docs/current-repair-reference.md) before selecting a task or reporting a score.

This hybrid is a condition, not a numbered `v` release. Use the condition ID, source seal, and archive tag in the
current reference to identify it; v337 is retained only as the older promoted comparison.

The promoted baseline registry remains a separate older-architecture comparison and currently resolves to v337
at 157/189 (83.07%). Do not substitute it for the hybrid repair queue or add isolated task passes to either
aggregate.

The historical `125/189` result is not a valid baseline. See [docs/index.md](docs/index.md).

## Layout

```text
integrations/lite_agent/   Agent loop, tool catalog, safety, and runtime state
*_adapter/                 Application-specific reusable APIs
scripts/                   Deployment, evaluation, supervision, and audit entry points
tests/                     Focused behavior, protocol, boundary, and deployment tests
tests/holo_agent/          Holo delegation and grounding tests
deployment/                Model service deployment
docs/                      Concise current documentation
docs/archive/              Historical reports and specifications
experiments/configs/       Machine-readable experiment configurations
experiments/               Immutable raw results and traces
```

## Standard Commands

```bash
PYTHONPATH=. .venv-openapa/bin/python -m pytest -q tests/<focused-test>.py
.venv-openapa/bin/ruff check <changed-python-files>
git diff --check
```

Use `scripts/deploy_all_adapters.py` for Adapter deployment and
`scripts/supervise_lite_agent_parallel.py` for parallel evaluation only after the generic-only preflight passes.

## Data Boundaries

- `.venv-openapa/` and `.venv-qwen-agent/` are local environments, not source.
- `experiments/` contains immutable historical evidence, baseline records, and raw traces; do not rename or
  overwrite completed runs. Read `experiments/baselines/current.json` to resolve the current baseline.
- Existing task-aware Adapter routes and golden assets are legacy implementation details and are excluded from
  a valid generic-only runtime.
- Development may inspect evaluator/golden offline to design reusable APIs, but runtime code and Agent-visible
  data must not contain answers or task identity.
