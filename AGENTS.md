# Codex working agreement

## Scope

- Implement only the user's explicit request.
- Do not invent acceptance criteria, speculative abstractions, future-proofing, unrelated cleanup, or follow-up features.
- Report newly discovered unrelated issues instead of fixing them.
- Prefer the smallest coherent diff that satisfies the request.

## Tests and validation

- Do not add or expand tests unless the user explicitly asks, or a minimal regression test is necessary to prove a confirmed bug fix.
- Never add broad test matrices, duplicate coverage, snapshots, fixtures, or golden files "just in case."
- Do not modify tests, snapshots, fixtures, or golden files merely to make a check pass.
- The only local validation command available to the agent is `./scripts/agent-check changed`.
- Run it once after a coherent edit batch, in the foreground, and only rerun after a relevant code change.
- Do not run raw repository-wide test, lint, typecheck, build, coverage, E2E, benchmark, CI, or release commands.
- Full validation belongs to CI or an explicit human request.
- Do not edit `.codex/agent-check.json`, `.codex/config.toml`, `.codex/hooks.json`, `.codex/hooks/test_guard.py`, or `scripts/agent-check` from a normal Codex session.
- Stop after the requested change and bounded validation. State exactly what was not checked.

## Efficient inspection

- In Code Mode, batch independent read-only tool calls within one bounded stage. Use `Promise.allSettled` when partial results remain useful and `Promise.all` when any failure should abort.
- Keep dependent, adaptive, approval-sensitive, conflicting, waiting, and mutation steps sequential.
- Do not expand investigation scope merely because more calls can be batched.
