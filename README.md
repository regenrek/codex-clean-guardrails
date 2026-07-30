# codex-lean-guardrails

Keep Codex focused: small changes, relevant tests, bounded local validation.

## Why I built this

A small coding task can quietly turn into a much larger one:

- Codex repeatedly runs the full test suite, build, lint, or typecheck;
- a focused fix grows new test files, matrices, fixtures, snapshots, or E2E coverage;
- more time is spent validating speculative work than finishing the requested change.

Prompts help, but they are easy to drift away from. This project puts the working agreement in the repository and backs it with hooks, a cumulative Git-diff policy, and one bounded validation command.

The goal is not “fewer tests at any cost.” It is to keep the smallest useful proof at the cheapest appropriate layer—and require an explicit human decision when a task genuinely needs more.

## What it does

```text
Codex proposes a change
        │
        ├─ repository instructions keep scope and test selection focused
        ├─ hooks block broad validation and preflight test edits
        ├─ the cumulative diff catches test growth across many small edits
        └─ agent-check runs only configured changed-file checks within a budget
```

The installed guardrails:

- define concise scope, test-authoring, and stopping rules in `AGENTS.md`;
- block direct full-suite test, build, lint, typecheck, coverage, and E2E commands;
- allow only `./scripts/agent-check changed` for normal local agent validation;
- limit measurable test sprawl without using a universal test-to-code ratio;
- protect the active policy and hook files from routine agent edits;
- repeat the cumulative policy in pull-request CI using the trusted base revision;
- provide explicit profiles and human-owned escape hatches for legitimate broad work.

Hooks are workflow guardrails, not a security boundary. They do not replace review or CI.

## Quick start

Requirements: Git, Python 3.10+, and a current Codex CLI or desktop build with hooks.

```bash
git clone https://github.com/regenrek/codex-lean-guardrails.git
cd codex-lean-guardrails

./scripts/install /path/to/your-project --recipe vitest-pnpm

cd /path/to/your-project
./scripts/doctor
codex
```

Inside Codex, open `/hooks` once to review and trust the project hooks. During normal work, the only local validation command available to the agent is:

```bash
./scripts/agent-check changed
```

Included recipes:

```text
vitest-pnpm
jest-pnpm
pytest-changed-tests
```

The installer merges existing project instructions and hooks. It never creates or changes `.codex/config.toml`; your personal `~/.codex/config.toml` remains in use.

See [usage and installation](docs/usage.md) for custom checks, profiles, CI setup, overrides, and operational details.

## What is included

| Piece | Purpose |
| --- | --- |
| `AGENTS.md` | Scope, test-selection, and validation rules for Codex |
| `.codex/hooks/` | Blocks broad commands, protects guardrails, and checks edits |
| `.codex/test-policy.json` | Configurable focused, expanded, and tests-only limits |
| `.codex/agent-check.json` | Repository-specific changed-file validation commands |
| `scripts/agent-check` | Budgeted, cached validation for the current diff |
| `scripts/test-policy` | Human-readable cumulative test-diff checks |
| GitHub workflow | Trusted-base pull-request enforcement |
| CODEOWNERS example | Human review routing for tests and policy files |

No runtime dependency is added to the target application.

## Dogfood benchmarks

**Shiftline** is the only clean paired run so far: both variants used the same starter and prompt, required no manual follow-up, and passed hidden acceptance, the full suite, build, and E2E.

| Result | Default Codex | Lean guardrails |
| --- | ---: | ---: |
| Completion time | 512 s | 519 s |
| Production lines added | 689 | 608 |
| Test lines added | 92 | **37** |
| Added test cases | 6 | **4** |
| Direct full test/build/E2E calls | 15 | **0** |
| Hidden acceptance | 20/20 | 20/20 |
| Final test, build, and E2E | passed | passed |

In this run, Lean produced the same measured outcome with 60% fewer test lines and bounded validation instead of repeated full-suite commands. It is one local experiment, not proof of a universal improvement.

Read the [full benchmark notes](docs/benchmarks.md) for the earlier unsuccessful runs, methodology, trade-offs, and limitations.

## Documentation

- [Usage and installation](docs/usage.md) — setup, recipes, profiles, overrides, CI, and troubleshooting boundaries
- [Test-authoring policy](docs/test-policy.md) — measured limits, path classification, hooks, and tuning
- [Benchmarks](docs/benchmarks.md) — all three dogfood runs, including negative results
- [Evidence and rationale](docs/evidence.md) — source-backed design choices and known limits

## License

MIT
