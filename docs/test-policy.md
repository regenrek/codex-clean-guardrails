# Test-authoring policy

`./scripts/test-policy` checks the cumulative Git diff against `.codex/test-policy.json`.

It is intentionally a circuit breaker, not a coverage calculator. It does not use a test-to-production line ratio and does not claim that a fixed number of tests is universally correct. It blocks measurable forms of test sprawl while `AGENTS.md`, review, and CI handle semantic quality.

## Commands

```bash
# Compare the working tree with HEAD.
./scripts/test-policy check

# Print the selected profile and configured limits.
./scripts/test-policy explain

# Compare all branch changes with a merge base.
./scripts/test-policy check --base origin/main

# Machine-readable result.
./scripts/test-policy check --json
```

Without `--base`, the comparison target is `HEAD`. Pre-existing uncommitted test changes count toward the same cumulative budget. Use a clean worktree for a new Codex task, or set `CODEX_TEST_BASE` when intentionally continuing work on an existing branch diff.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Policy passed or an explicit bypass is active |
| `1` | Cumulative test diff violates the selected profile |
| `2` | Configuration, Git, or inspection error |

## Profiles

The selected profile is resolved in this order:

1. explicit API argument;
2. `CODEX_TEST_PROFILE` in the parent environment;
3. `default_profile` in `.codex/test-policy.json`.

### `focused`

Use for ordinary feature and bug-fix work.

- Requires a product-code change when tests change.
- Allows a small number of nearby tests.
- Allows at most one new test file.
- Allows an existing test setup file to be adjusted, but no new test infrastructure.
- Allows no new integration, E2E, system, or acceptance test.
- Limits snapshots, fixtures, golden files, inline tests, and test-file deletion.
- Does not allow bootstrapping a first test suite.

### `expanded`

Use when a human has agreed that one implementation task genuinely spans more behavior or test locations.

It increases the mechanical limits but still requires product-code changes and still does not bootstrap a first test suite.

### `tests-only`

Use for intentional test maintenance, fixture work, removing or consolidating tests, and bootstrapping a first test suite.

This profile does not require a product-code change. It is broader than `focused`, but still bounded. A fully exceptional task can use `CODEX_ALLOW_BROAD_TEST_EDITS=1`.

## What is measured

The policy evaluates:

- test files touched;
- new and deleted test files;
- added test lines;
- common concrete test-case declarations;
- tests added inline to production files;
- test runner configuration, setup files, and helper/support subsystems;
- integration, E2E, system, and acceptance test growth;
- snapshots;
- fixtures, golden files, and test data;
- binary or oversized artifacts;
- whether test changes are accompanied by product-code changes;
- whether the baseline already has a test suite.

It examines tracked changes and untracked files. With `--base`, it compares the pull-request branch with the merge base of the requested ref and `HEAD`.

## Path classification

Classification order is:

1. ignored paths;
2. support-only paths;
3. test infrastructure;
4. snapshots;
5. fixtures and golden files;
6. expensive tests;
7. normal tests;
8. product code.

Support-only paths are checked before test filename patterns. This prevents files such as `.codex/hooks/test_policy.py`, workflow templates, or `CODEOWNERS.tests.example` from being mistaken for product tests.

Configure these arrays:

```json
{
  "test_file_patterns": [],
  "test_infrastructure_patterns": [],
  "expensive_test_patterns": [],
  "snapshot_patterns": [],
  "fixture_patterns": [],
  "support_only_patterns": [],
  "ignore_patterns": []
}
```

Test infrastructure includes runner configuration, setup files, and shared test-helper directories. The default focused profile permits one existing infrastructure file to change but blocks creation of a new one. Framework setup and helper subsystems should be explicit `expanded` or `tests-only` work rather than a side effect of an ordinary implementation task.

Patterns are repository-relative globs. `**/` also matches zero directories, so `**/*.test.ts` matches both `app.test.ts` and `src/app.test.ts`.

### Framework-specific conventions

Add patterns that represent tests in the target repository. Examples:

```json
{
  "test_file_patterns": [
    "**/*.stories.tsx",
    "**/*.contract.ts",
    "**/src/test/**"
  ],
  "expensive_test_patterns": [
    "apps/web/playwright/**",
    "packages/*/system-tests/**"
  ]
}
```

Only classify Storybook stories as tests when the repository genuinely uses stories or play functions as its canonical behavioral test architecture.

## Concrete case counting

The detector recognizes common declarations, including:

- Python `def test_*`;
- JavaScript/TypeScript `test(...)`, `it(...)`, and `specify(...)`;
- Rust `#[test]`, async test attributes, and common parameterized attributes;
- Go `func Test*`;
- JUnit and xUnit attributes;
- Ruby specs;
- PHP `test*` methods;
- Swift test functions;
- C/C++ test macros;
- Dart and Elixir test declarations.

This is deliberately conservative. Parameter tables, generated cases, custom macros, Gherkin scenarios, and framework-specific DSLs may not map one-to-one to a detected case. File and line budgets still apply.

## Snapshot and fixture handling

Snapshots and fixtures are treated separately because they can add large review surfaces without adding an obvious test declaration.

A focused task may update or add only a small amount of established artifact data. The policy checks:

- files touched;
- new files;
- total added lines;
- added lines per snapshot file;
- binary artifacts;
- artifacts larger than `max_inspected_file_bytes`.

The focused profile's 50-line snapshot default follows the reviewability precedent used by `jest/no-large-snapshots`; it remains configurable and is not a universal correctness rule. The policy cannot determine whether an expected-output update is semantically correct. CODEOWNERS and pull-request review remain important for these files.

## New test-suite handling

The baseline is considered to have a test suite when at least one path at the base commit matches a normal or expensive test pattern. Snapshots and fixtures alone do not count.

- `focused`: blocks creating the first suite.
- `expanded`: blocks creating the first suite.
- `tests-only`: permits a bounded, explicit bootstrap.

This prevents a normal implementation request from silently turning into a framework-selection and test-infrastructure project.

## Hooks

### PreToolUse

`.codex/hooks/test_guard.py`:

- blocks direct broad validation;
- protects `AGENTS.md`, policy and runner files, the trusted CI runner, the installed policy workflow, and CODEOWNERS review gate;
- evaluates one `apply_patch` before it runs;
- blocks obvious shell writes to test paths and asks Codex to use `apply_patch`.

Patch preflight intentionally does not require product and test changes to appear in the same patch. This permits TDD ordering. The cumulative check enforces the product/test relationship afterward.

### PostToolUse

`.codex/hooks/test_guard.py` evaluates the entire repository diff after `apply_patch` and after any Bash command that is not on a conservative read-only inspection allowlist. Normal `rg`, `git`, `cat`, and similar inspection loops skip the repeated scan. Interpreter-based, custom, or otherwise unknown commands are rescanned after execution, and `Stop`, `scripts/agent-check`, and pull-request CI check the final cumulative state. A violation returns a block decision and remediation context.

### Stop

The same cumulative hook evaluates the diff before completion. On the first violation it asks Codex to reduce the change. When `stop_hook_active` is already true and the violation remains, it stops instead of recursively blocking forever.

## Agent-check integration

`scripts/agent-check` runs the policy before selecting or executing validation commands. The policy result is included in the cache fingerprint and in `AGENT_CHECK_RESULT`.

A policy failure returns before any test runner starts. This is important because validating an oversized test diff first would preserve the original waiting-time problem.

## GitHub pull-request check

`templates/github-actions/test-policy.yml` uses full Git history and invokes `scripts/test-policy-ci` from the pull request's trusted base revision. That runner also loads `.codex/hooks/test_policy.py` and `.codex/test-policy.json` from the base revision before evaluating the pull-request checkout. The proposed policy files are data, not executable enforcement code.

This prevents policy implementation or configuration changes from approving themselves by raising limits, changing the checker, or replacing the active runner. A first installation has a visible bootstrap fallback because those trusted files do not exist on the base branch yet. After the installation is merged, subsequent checks use only the base implementation and configuration. The workflow file itself must still be protected with CODEOWNERS or, preferably for organization-wide use, enforced as a ruleset-required workflow from a protected policy repository.

Maintainer-applied labels select explicit exceptions:

- `test-policy-expanded` selects the broader implementation profile;
- `test-policy-tests-only` selects intentional test maintenance;
- `test-policy-exception` bypasses mechanical authoring limits;
- `test-policy-maintenance` separately permits changes to active policy and execution files.

The workflow listens for `labeled` and `unlabeled` events so changing a label recalculates the required check. Require the `test-policy` status check in a ruleset or branch-protection rule.

## CODEOWNERS

`templates/CODEOWNERS.tests.example` routes test, artifact, workflow, and policy changes to a designated human owner. Edit the placeholder before use and require code-owner review.

Own the CODEOWNERS file itself so a change cannot remove the review requirement without review from the same owner.

## Tuning guidance

Tune the policy from observed review pain, not from a desire to maximize test counts.

Raise a limit when normal, cohesive changes repeatedly require a small amount more room. Lower a limit when reviews show recurring mechanical sprawl. Prefer adding a repository-specific path category over globally expanding every allowance.

Examples:

- A compiler conformance repository may need a higher new-fixture allowance.
- A UI repository with established visual snapshots may allow more snapshot files but keep a low per-file line limit.
- A monorepo may need more test files touched while still allowing only one new expensive test.
- A library with inline Rust tests may increase `max_inline_test_files_touched` while keeping new integration tests at zero.

Do not tune the focused profile to fit the largest task. Use `expanded` or `tests-only` for the exceptional task and keep the default useful for ordinary work.
