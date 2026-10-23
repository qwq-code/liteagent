# Active v2 Scope

Updated: 2026-09-01

The repository-level rules in `../../AGENTS.md` are the canonical policy for this directory. This file is a
pointer, not a second copy of those rules; when wording differs, the root policy and the user's latest request
take precedence.

Active implementation belongs here. Keep the frozen v1 tree, the pinned OSWorld evaluator, and finalized raw
experiment evidence unchanged. Use this directory for reusable Adapter, LiteAgent, test, deployment, and
experiment-source changes. Temporary prototypes may live in the documented scratch locations and must not be
packaged as runtime source.

Failure repair follows the root `GOAL.md`: work from preserved failures, test the smallest reusable change, and
record the result per task. The current condition and score semantics are centralized in
`docs/current-repair-reference.md`; promotion procedures and other changing runtime facts are documented under
`docs/` rather than duplicated here.
