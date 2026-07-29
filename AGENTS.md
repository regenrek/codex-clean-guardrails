# Codex working agreement

## Scope

- Implement only the user's explicit request.
- Do not invent acceptance criteria, speculative abstractions, future-proofing, unrelated cleanup, or follow-up features.
- Report newly discovered unrelated issues instead of fixing them.
- Prefer the smallest coherent diff that satisfies the request.

## Test authoring

- Tests are evidence for changed behavior, not a second implementation project.
- For a bug fix, add one minimal regression test when one case proves the bug. Use the smallest coherent set only when distinct changed branches genuinely need separate proof.
- For a feature or behavior change, extend the nearest existing test at the cheapest deterministic layer that proves the externally observable behavior.
- Do not duplicate the same behavior across unit, integration, browser, and E2E layers. Add a higher layer only for confidence the lower layer cannot provide.
- For refactors, documentation, formatting, comments, or other behavior-preserving changes, do not add tests unless an existing test must be adjusted for a real contract change.
- Follow the repository's existing test architecture, naming, helpers, and fixture style. Do not introduce a new test framework, runner configuration, setup subsystem, first test suite, helper abstraction, test-only production API, snapshot system, or fixture system during a normal coding task.
- Test public or user-observable behavior. Do not lock in private calls, internal ordering, incidental markup, or other implementation details.
- Do not test trivial constants, static mappings, removed behavior, framework behavior, or hypothetical edge cases unrelated to the requested change or reproduced failure.
- Avoid broad parameter matrices. Select representative equivalence classes and the boundaries changed by this task.
- Prefer an existing test file. Snapshots, fixtures, and golden files are allowed only when that artifact is the established contract and the change intentionally affects it.
- Never weaken assertions, rewrite expected output, or update snapshots merely to make the implementation pass.
- Keep test changes within `.codex/test-policy.json`. The default `focused` profile is a circuit breaker, not a coverage target. Do not fill its allowance unnecessarily.
- When a legitimate task exceeds the focused profile, stop and report why it needs `CODEX_TEST_PROFILE=expanded`, `CODEX_TEST_PROFILE=tests-only`, or explicit human ownership. Do not silently broaden scope.

## Validation

- The only local validation command available to the agent is `./scripts/agent-check changed`.
- Run it once after a coherent edit batch, in the foreground, and only rerun after a relevant code change.
- Do not run raw repository-wide test, lint, typecheck, build, coverage, E2E, benchmark, CI, or release commands.
- Full validation belongs to CI or an explicit human request.
- Stop after the requested change and bounded validation. State exactly what was not checked.

## Guardrail integrity

- Do not edit `.codex/agent-check.json`, `.codex/test-policy.json`, `.codex/hooks.json`, files under `.codex/hooks/`, `scripts/agent-check`, `scripts/test-policy`, `scripts/test-policy-ci`, `.github/workflows/codex-test-policy.yml`, or `.github/CODEOWNERS` from a normal Codex session.

## Efficient inspection

- In Code Mode, batch independent read-only tool calls within one bounded stage. Use `Promise.allSettled` when partial results remain useful and `Promise.all` when any failure should abort.
- Keep dependent, adaptive, approval-sensitive, conflicting, waiting, and mutation steps sequential.
- Do not expand investigation scope merely because more calls can be batched.
