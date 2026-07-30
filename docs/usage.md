# Usage and installation

This guide covers day-to-day operation after the project overview in the [README](../README.md). For the mechanics and configuration of the cumulative test policy, see [test-policy.md](test-policy.md).

## Requirements

- Git
- Python 3.10 or newer
- a current Codex CLI or desktop build with hooks
- the test runner used by the selected recipe already installed in the target repository

The guardrails themselves have no third-party runtime dependency.

## Install into an existing repository

From this repository:

```bash
./scripts/install /path/to/project --recipe vitest-pnpm
```

Available recipes:

```bash
--recipe vitest-pnpm
--recipe jest-pnpm
--recipe pytest-changed-tests
```

Use `--no-ci` only when the target repository already has equivalent pull-request enforcement:

```bash
./scripts/install /path/to/project --recipe vitest-pnpm --no-ci
```

The installer merges existing `AGENTS.md` content and hook definitions and is safe to run again. It does not create, copy, or modify `.codex/config.toml`; Codex continues to use the personal configuration at `~/.codex/config.toml`.

After installation:

```bash
cd /path/to/project
./scripts/doctor
./scripts/test-policy explain
codex
```

Open `/hooks` once inside Codex to review and trust the project hooks. Restart Codex after changing hook definitions.

## Custom validation

For another stack, copy `recipes/custom.example.json` to the target repository as `.codex/agent-check.json` and define one genuinely targeted command.

Do not put a full repository suite in this file. A useful check should select work from changed paths, stay deterministic, and fit inside the configured deadline. Full validation belongs in CI or a deliberate human-run session.

The normal agent command is:

```bash
./scripts/agent-check changed
```

The wrapper:

- evaluates the test-authoring policy first;
- selects checks from changed paths;
- passes files as argv values without a shell;
- enforces total and per-command deadlines;
- stops on the first failure;
- terminates the child process group on timeout;
- caches passes and failures for an identical repository state;
- fails closed when a configured command cannot safely handle its input.

## Day-to-day policy commands

```bash
# Show the active profile and limits.
./scripts/test-policy explain

# Compare the working tree with HEAD.
./scripts/test-policy check

# Compare the branch with the merge base of origin/main.
./scripts/test-policy check --base origin/main

# Emit a machine-readable result.
./scripts/test-policy check --json
```

Without `--base`, existing uncommitted changes count toward the same cumulative budget. Start a new Codex task from a clean worktree, or set `CODEX_TEST_BASE` when intentionally continuing an existing branch diff.

## Profiles and explicit exceptions

Set profile variables on the Codex parent process, not inside a child command proposed by Codex.

```bash
# Ordinary feature and bug-fix work. This is the default.
CODEX_TEST_PROFILE=focused codex

# Human-approved work that genuinely spans more test locations.
CODEX_TEST_PROFILE=expanded codex

# Intentional test maintenance, consolidation, or first-suite setup.
CODEX_TEST_PROFILE=tests-only codex
```

Exceptional human-owned sessions can use:

```bash
# Permit direct full validation commands.
CODEX_ALLOW_FULL_VALIDATION=1 codex

# Permit edits to protected policy and execution files.
CODEX_ALLOW_GUARDRAIL_EDITS=1 codex

# Bypass mechanical test-authoring limits while still reporting the diff.
CODEX_ALLOW_BROAD_TEST_EDITS=1 codex
```

These are deliberate session-level decisions, not flags the agent should add to its own command.

## Pull-request enforcement

The installer adds `.github/workflows/codex-test-policy.yml`. The workflow evaluates the complete pull-request diff using the policy runner, implementation, and limits from the trusted base revision. A pull request therefore cannot approve itself by weakening the policy code it changes.

Maintainer-applied labels select explicit exceptions:

```text
test-policy-expanded
test-policy-tests-only
test-policy-exception
test-policy-maintenance
```

Make the `test-policy` job a required status check in a GitHub ruleset or branch-protection rule. Protect the workflow with CODEOWNERS. For stronger organization-wide enforcement, use a ruleset-required workflow stored on a protected branch or in a dedicated policy repository.

The installer also provides `.github/CODEOWNERS.tests.example`. Replace the placeholder owner, merge it into `.github/CODEOWNERS`, and require code-owner review for tests, snapshots, fixtures, test infrastructure, policy files, and the workflow itself.

## Files installed

```text
AGENTS.md
.codex/hooks.json
.codex/hooks/test_guard.py
.codex/hooks/test_policy.py
.codex/agent-check.json
.codex/test-policy.json
scripts/agent-check
scripts/test-policy
scripts/test-policy-ci
scripts/doctor
.github/workflows/codex-test-policy.yml
.github/CODEOWNERS.tests.example
```

`profiles/lean.config.toml` is an optional manual reference profile. It is not installed and is not required for the normal workflow.

## Verify an installation

```bash
./scripts/doctor
./scripts/agent-check changed
```

`doctor` checks hook registration and protocol output, simulates allowed and denied commands and patches, validates the local policy and validation CLIs, checks the cumulative policy, and reports whether CI and CODEOWNERS templates are installed.

## Operational limits

- Hooks are workflow guardrails, not a complete security boundary.
- `PostToolUse` runs after a side effect and cannot undo it; stop-time and CI checks cover the cumulative result.
- The shell-write detector covers common direct writes but is not a complete shell parser.
- Specialized tools may not pass through the standard hook path.
- Project hooks run only after the project is trusted.
- Polling an accepted process does not invoke `PreToolUse` again, so broad commands must be denied before launch.
- Mechanical budgets cannot judge whether a test is semantically useful.
- Vitest `related` follows static imports and may need an explicit sentinel for dynamic boundaries.
- Pytest has no generic source-to-test graph; the included recipe runs changed test files only.
- The guardrails do not make an inherently slow suite faster. They prevent routine agent work from repeatedly launching it.

See [evidence.md](evidence.md) for the source-backed rationale and [test-policy.md](test-policy.md) for detailed tuning guidance.
