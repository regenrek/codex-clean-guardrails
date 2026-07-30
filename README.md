# codex-lean-guardrails

![A small coding robot balancing lightly while oversized test and build blocks stay behind](assets/codex-lean-guardrails-banner.png)

Keep Codex focused. Make small changes. Write useful tests. Avoid long validation loops.

## Why I built this

A small coding task can grow into a much larger one:

- Codex runs the full test suite or build several times.
- A small fix gets many new tests, fixtures, snapshots, or E2E flows.
- More time goes into extra work than into the requested change.

A prompt can ask Codex to stay focused. But prompts are easy to forget as a task grows.

This project puts the rules inside the repository. Hooks enforce the basic limits. One small validation command checks only the relevant changes.

The goal is not to avoid tests. The goal is to write the smallest useful test at the right level. Larger test work still remains possible when a human approves it.

## What it does

```text
Codex starts a task
        │
        ├─ project rules keep the task focused
        ├─ hooks stop large test and build commands
        ├─ a diff check tracks all test changes
        └─ agent-check validates only changed files
```

The guardrails:

- give Codex clear rules for scope and tests;
- stop full test suites and other broad checks during normal agent work;
- use `./scripts/agent-check changed` for small local checks;
- detect when test changes become too large;
- protect the guardrail files from normal Codex edits;
- check the same test limits again in pull-request CI;
- offer broader profiles when a task truly needs them.

Hooks guide the workflow. They are not a security boundary and do not replace review or CI.

## Quick start

You need Git, Python 3.10+, and a current Codex version with hook support.

```bash
git clone https://github.com/regenrek/codex-lean-guardrails.git
cd codex-lean-guardrails

./scripts/install /path/to/your-project --recipe vitest-pnpm

cd /path/to/your-project
./scripts/doctor
codex
```

Open `/hooks` once inside Codex. Review and trust the project hooks.

During normal work, Codex can use this local validation command:

```bash
./scripts/agent-check changed
```

Included recipes:

```text
vitest-pnpm
jest-pnpm
pytest-changed-tests
```

The installer keeps your existing project instructions and hooks. It does not create or change `.codex/config.toml`. Your personal `~/.codex/config.toml` stays active.

See [usage and installation](docs/usage.md) for custom checks, profiles, CI setup, and overrides.

## What is included

| Part | What it does |
| --- | --- |
| `AGENTS.md` | Gives Codex rules for scope, tests, and validation |
| `.codex/hooks/` | Stops broad commands and checks edits |
| `.codex/test-policy.json` | Defines the test-change limits |
| `.codex/agent-check.json` | Defines checks for changed files |
| `scripts/agent-check` | Runs small checks with a time limit and cache |
| `scripts/test-policy` | Shows whether test changes fit the policy |
| GitHub workflow | Checks the policy on pull requests |
| CODEOWNERS example | Sends sensitive changes to human reviewers |

The target app gets no new runtime dependency.

## Dogfood benchmark

**Shiftline** is the only clean A/B run so far. Both variants used the same starter and prompt. Neither run needed manual input. Both passed hidden acceptance, the full test suite, the build, and E2E.

| Result | Default Codex | Lean guardrails |
| --- | ---: | ---: |
| Completion time | 512 s | 519 s |
| Production lines added | 689 | 608 |
| Test lines added | 92 | **37** |
| Added test cases | 6 | **4** |
| Direct full test/build/E2E calls | 15 | **0** |
| Hidden acceptance | 20/20 | 20/20 |
| Final test, build, and E2E | passed | passed |

Lean produced the same measured result with 60% fewer test lines. It used small checks instead of repeated full checks. This is one local experiment. It does not prove that guardrails always improve Codex.

Read the [full benchmark notes](docs/benchmarks.md) for the earlier failed runs, methods, trade-offs, and limits.

## Documentation

- [Usage and installation](docs/usage.md) — setup, profiles, overrides, and CI
- [Test policy](docs/test-policy.md) — limits, hooks, and tuning
- [Benchmarks](docs/benchmarks.md) — results and failed runs
- [Evidence and rationale](docs/evidence.md) — sources and design choices

## License

MIT
