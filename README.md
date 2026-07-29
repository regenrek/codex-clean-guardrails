# codex-lean-guardrails

Codex guardrails for two related failure modes:

1. a small change triggers repeated full test, lint, typecheck, build, coverage, or CI runs;
2. the implementation grows into an unnecessary test project with broad matrices, new fixtures, snapshots, helpers, or E2E coverage that the task did not require.

This repository does not solve either problem with a longer prompt alone. It narrows the execution surface and checks the cumulative Git diff.

## Design principles

The policy deliberately does **not** use a universal test-to-production-code ratio. The right amount of testing depends on the behavior and risk of the change. The default rules instead enforce reviewability:

- write the smallest test that proves the changed behavior;
- prefer an existing test file and the cheapest deterministic layer;
- test public or user-observable behavior, not private implementation details;
- do not duplicate the same behavior at unit, integration, browser, and E2E layers;
- keep expensive tests at the narrowest useful scope;
- keep snapshots short and reviewable;
- require an explicit profile for test-only work, a first test suite, broad matrices, new E2E coverage, or large fixture changes;
- keep humans and CI authoritative for semantic correctness.

The numeric limits are configurable circuit breakers. They are not coverage targets and should never be filled merely because room remains.

## How it works

```text
AGENTS.md
  -> defines scope, test-selection, and stopping rules

PreToolUse
  -> blocks raw/full validation before it starts
  -> protects active guardrail files
  -> preflights test edits made through apply_patch
  -> blocks obvious direct shell writes to test paths

PostToolUse
  -> checks the complete Git diff after apply_patch and any Bash command not known to be read-only
  -> catches many small edits that exceed the policy cumulatively

Stop
  -> checks the complete diff before Codex finishes
  -> allows one correction pass, then stops instead of looping forever

scripts/test-policy
  -> exposes the same cumulative policy to humans

scripts/test-policy-ci
  -> evaluates pull requests with policy code and config loaded from the trusted base revision
  -> prevents policy code or config changes from self-approving while the workflow remains protected

scripts/agent-check
  -> runs the policy first
  -> executes only configured changed-file checks within a hard budget
  -> caches pass and failure results for an identical repository state

GitHub Actions + CODEOWNERS
  -> make the policy independent of the local agent session
  -> route exceptional test changes to explicit human review
```

## Quick start

Requirements:

- Git
- Python 3.10 or newer
- a current Codex CLI or desktop build with hooks

```bash
git clone https://github.com/regenrek/codex-lean-guardrails.git
cd codex-lean-guardrails

./scripts/install /path/to/project \
  --recipe vitest-pnpm

cd /path/to/project
./scripts/doctor
./scripts/test-policy explain
codex
```

Inside Codex, open `/hooks` once to review and trust the project hooks. Restart Codex after changing hook definitions.

Available recipes:

```bash
--recipe vitest-pnpm
--recipe jest-pnpm
--recipe pytest-changed-tests
```

For another stack, copy `recipes/custom.example.json` to `.codex/agent-check.json` and define one genuinely targeted command.

Use `--no-ci` only when the repository already has equivalent pull-request enforcement:

```bash
./scripts/install /path/to/project --recipe vitest-pnpm --no-ci
```

## Default focused test policy

The installed `.codex/test-policy.json` starts with this ordinary feature and bug-fix profile:

| Guard | Default |
| --- | ---: |
| Test files touched | 2 |
| New test files | 1 |
| Added test lines | 180 |
| Detected added test cases | 8 |
| Inline production files receiving tests | 1 |
| Existing test-infrastructure files touched | 1 |
| New test-infrastructure files | 0 |
| Added test-infrastructure lines | 80 |
| Existing integration/E2E/system files touched | 1 |
| New integration/E2E/system files | 0 |
| Added expensive-test lines | 120 |
| Snapshot files touched | 1 |
| New snapshot files | 1 |
| Added snapshot lines | 50 total and per file |
| Fixture/golden/test-data files touched | 1 |
| New fixture/golden/test-data files | 1 |
| Added fixture lines | 120 |
| Deleted test files | 0 |
| Binary test artifacts | blocked |
| Product-code change required when tests change | yes |
| First test suite may be created | no |

These defaults are intentionally conservative. A typical bug fix should usually add one regression case, not approach the limits.

### Profiles

```bash
# Ordinary implementation work. This is the default.
CODEX_TEST_PROFILE=focused codex

# Human-approved feature work that genuinely spans more test locations.
CODEX_TEST_PROFILE=expanded codex

# Intentional test maintenance, consolidation, or first-suite setup.
CODEX_TEST_PROFILE=tests-only codex

# Exceptional human-owned task. The diff is still reported and reviewed.
CODEX_ALLOW_BROAD_TEST_EDITS=1 codex
```

Set these variables on the **Codex parent process**. A variable placed inside a child command proposed by Codex does not alter the hook's environment.

The same profiles can be inspected and run without Codex:

```bash
./scripts/test-policy explain
./scripts/test-policy check
./scripts/test-policy check --base origin/main
./scripts/test-policy check --profile expanded
./scripts/test-policy check --json
```

Without `--base`, the policy compares the current worktree with `HEAD`. Existing uncommitted test changes therefore count toward the same budget. Start Codex from a clean worktree, or set `CODEX_TEST_BASE` when the task intentionally continues an existing branch diff.

## What the authoring policy detects

The cumulative checker covers tracked changes, staged changes, unstaged changes, renames, and untracked files. It measures:

- normal test files;
- common concrete test declarations across JavaScript/TypeScript, Python, Rust, Go, JVM, .NET, Ruby, PHP, Swift, C/C++, Dart, and Elixir;
- tests embedded in production files;
- test runner configuration, setup files, and helper/support subsystems;
- integration, E2E, system, and acceptance tests;
- snapshots;
- fixtures, golden files, and test data;
- binary or oversized test artifacts;
- test-only changes under the focused and expanded profiles;
- deletion of test files;
- creation of a first test suite.

It is intentionally conservative. It cannot prove that two tests are semantically redundant, that a parameter table represents the right equivalence classes, or that an expected-output update is correct. `AGENTS.md`, review, CODEOWNERS, and CI cover those judgments.

### TDD remains possible

A small test patch may be written before the implementation patch. `PreToolUse` evaluates that single patch without requiring product code in the same patch. `PostToolUse`, `Stop`, `scripts/agent-check`, and pull-request CI then enforce the relationship on the cumulative diff.

## Bounded validation

The only local validation command available to Codex is:

```bash
./scripts/agent-check changed
```

Direct commands such as these are denied unless a human starts Codex with `CODEX_ALLOW_FULL_VALIDATION=1`:

```text
pnpm test                    pytest
npm run lint                 cargo test
pnpm exec vitest             go test
npx jest                     nx affected -t test
eslint / tsc                 make test
playwright / cypress         gradle test / mvn verify
```

The wrapper:

- checks the authoring policy before launching any test runner;
- selects configured checks from changed files;
- uses argv arrays without a shell;
- applies a total wall-clock budget and per-check timeout;
- stops on the first failure;
- kills the child process group on timeout;
- fails closed when a configured related-test command cannot safely handle a deleted file;
- caches passes and failures by commit, configuration, runner implementation, changed paths, and changed contents.

Do not place a full repository suite in `.codex/agent-check.json`. Full validation belongs in CI or a deliberate human-run session.

## Pull-request enforcement

The installer adds `.github/workflows/codex-test-policy.yml` and compares the complete pull-request diff with full Git history. The first merge uses a visible bootstrap fallback because the target branch has no trusted runner yet. After that, the workflow extracts `scripts/test-policy-ci` from the target branch; that runner loads the policy implementation and limits from the same trusted revision before inspecting the pull-request checkout. Once the workflow file itself is protected, a pull request cannot make its own check pass by weakening the checker or limits it changes.

Maintainer-applied labels select an intentional exception. The workflow reruns when these labels are added or removed:

```text
test-policy-expanded
test-policy-tests-only
test-policy-exception
test-policy-maintenance
```

`test-policy-expanded` and `test-policy-tests-only` select bounded profiles. `test-policy-exception` bypasses mechanical authoring limits. `test-policy-maintenance` separately permits changes to active guardrail files. Keeping those exceptions separate prevents a broad test task from silently weakening enforcement.

Make the `test-policy` job a required status check in a GitHub ruleset or branch-protection rule. Protect the workflow itself with CODEOWNERS. For organization or enterprise deployments, the strongest option is a ruleset-required workflow stored on a protected branch or in a dedicated policy repository, because a pull request then cannot redefine the required workflow. Local hooks alone are not sufficient because hooks are workflow guardrails rather than a security boundary.

The installer also adds `.github/CODEOWNERS.tests.example`. Replace `@your-org/test-owners`, copy or merge it into `.github/CODEOWNERS`, and require code-owner review. The example owns:

- test paths and test filename patterns;
- test runner configuration, setup files, and shared helpers;
- snapshots, fixtures, and golden files;
- the test policy and hook implementation;
- the pull-request workflow;
- the CODEOWNERS file itself.

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

The installer never creates, copies, or changes `.codex/config.toml`; Codex uses the existing personal configuration at `~/.codex/config.toml` in the normal start path. Existing `AGENTS.md` and hook definitions are merged. Running the installer again does not duplicate the managed block or hooks.

`profiles/lean.config.toml` remains an optional reference profile for an explicit, manual opt-in. It is not installed and is not required for the normal workflow.

## Intentional maintenance overrides

```bash
# Allow raw/full validation for this Codex session.
CODEX_ALLOW_FULL_VALIDATION=1 codex

# Allow Codex to edit the protected policy and execution files.
CODEX_ALLOW_GUARDRAIL_EDITS=1 codex

# Bypass authoring limits for an exceptional human-owned task.
CODEX_ALLOW_BROAD_TEST_EDITS=1 codex
```

Protected files include `AGENTS.md`, the active runner, local and trusted CI policy runners, policy configuration, hook implementation, hook configuration, installed policy workflow, and CODEOWNERS review gate.

## Verify the installation

```bash
./scripts/doctor
./scripts/agent-check changed
```

`doctor` checks hook registration and protocol output, simulates allowed and denied Bash and `apply_patch` calls, validates the local policy and validation CLIs, checks the cumulative policy, and reports whether the CI and CODEOWNERS templates are installed.

## Limits

- OpenAI documents hooks as useful guardrails, not a complete security boundary.
- `PreToolUse` can prevent a supported tool call. `PostToolUse` runs after the side effect and cannot undo it, which is why the policy is also checked at stop and in CI.
- The shell-write detector blocks common direct writes but is not a complete shell parser. `PostToolUse` skips only a conservative allowlist of read-only inspection commands and rescans after unknown Bash commands; `Stop` and trusted-base CI catch the final cumulative state.
- Specialized tool paths may not pass through the standard hook path.
- Project hooks load only for trusted projects.
- `write_stdin` polling does not invoke `PreToolUse` again, so the original long command must be blocked before it starts.
- A path and line budget cannot determine semantic test quality. Human review is still required.
- Vitest `related` follows static imports and may miss dynamic loaders. Add one explicit sentinel check for those boundaries.
- Pytest has no generic source-to-test dependency graph. The included recipe runs changed test files only.
- This does not make a 30-minute suite faster. It prevents the agent from repeatedly launching it and prevents ordinary tasks from silently creating an oversized test surface.

See [docs/test-policy.md](docs/test-policy.md) for configuration details and [docs/evidence.md](docs/evidence.md) for the source-backed rationale.

## License

MIT
