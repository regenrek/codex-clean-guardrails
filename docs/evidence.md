# Evidence and design rationale

This repository separates two questions:

1. **What makes a useful test?** This requires repository context and human judgment.
2. **What forms of test expansion can be measured mechanically?** File creation, case counts, snapshots, fixtures, test infrastructure, expensive test layers, and validation commands can be bounded from the Git diff.

The semantic rules live in `AGENTS.md`. The deterministic limits live in `.codex/test-policy.json`, hooks, the local validation wrapper, and pull-request CI.

## Codex capabilities and limits

### Lifecycle hooks can enforce a workflow boundary

OpenAI documents `PreToolUse`, `PostToolUse`, and `Stop` hooks for Codex. Supported tool calls include Bash and `apply_patch`.

- `PreToolUse` can deny a supported command before it runs.
- `PostToolUse` can return corrective context after the side effect, but cannot undo the side effect.
- `Stop` can block completion and exposes `stop_hook_active`, which must be handled to avoid a continuation loop.
- later `write_stdin` polling of an already accepted process does not invoke `PreToolUse` again.
- hooks are workflow guardrails, not a complete security boundary.

Source:

- https://developers.openai.com/codex/hooks

These constraints lead to the repository's layered design:

1. preflight visible test edits and validation commands;
2. inspect the complete Git diff after `apply_patch` and commands not conservatively classified as read-only;
3. inspect it again before completion;
4. repeat the same check independently in pull-request CI.

### Project instructions belong in AGENTS.md

Codex loads layered `AGENTS.md` files, with more local instructions taking precedence for files in their scope.

Source:

- https://developers.openai.com/codex/guides/agents-md

This supports a short repository-owned test policy instead of a large intent-distillation prompt repeated for every task.

### A polling timeout is not a test-process deadline

Codex configuration includes a terminal polling timeout, but it is not a hard wall-clock limit for the child test process itself.

Source:

- https://developers.openai.com/codex/config-reference

`scripts/agent-check` therefore owns the total deadline, per-command timeout, changed-file cap, process-group termination, and unchanged-state cache.

## OpenAI repository guidance

The current `openai/codex` `AGENTS.md` uses repository-specific testing rules rather than “test everything”:

- run tests for the changed project before considering the complete suite;
- ask before running the full suite;
- avoid routine all-feature test matrices;
- do not test statically defined values;
- do not add negative tests for behavior that has been removed;
- reuse existing helpers;
- avoid adding implementation functions solely for tests;
- use snapshots when an intentional user-visible UI contract changes.

Source:

- https://github.com/openai/codex/blob/main/AGENTS.md

The OpenAI Agents Python sandbox prompt similarly says to keep changes minimal, start validation as specifically as possible, add a test only where the existing repository has a logical adjacent pattern, and not introduce tests into a codebase that has no test suite.

Source:

- https://github.com/openai/openai-agents-python/blob/main/src/agents/sandbox/instructions/prompt.md

This supports four defaults in this repository:

- prefer the nearest existing test file;
- block first-suite bootstrapping in an ordinary implementation profile;
- block new test infrastructure in that profile;
- require explicit scope for broader test work.

## Patterns from mature repositories

These examples are not universal standards. They demonstrate how established projects map changed behavior to their own test architecture.

### Storybook

Storybook's `AGENTS.md` sends React component behavior to stories with play functions and reserves ordinary unit tests for suitable utilities, hooks, and non-React modules. It also says to test real behavior rather than source syntax.

Source:

- https://github.com/storybookjs/storybook/blob/next/AGENTS.md

The relevant lesson is to follow the repository's existing contract and test layer rather than generating every plausible kind of test.

### Apache Airflow

Airflow documents single-test, test-file, package, and selective changed-file workflows. Its contributor guidance includes a command that determines relevant tests from changed files rather than defaulting every inner-loop change to the complete repository suite.

Source:

- https://github.com/apache/airflow/blob/main/AGENTS.md

### CBMC

CBMC documents a focused bug-fix sequence: create a regression reproducer, confirm it fails before the fix, fix the defect, then confirm the targeted regression passes. Normal source changes call for relevant tests.

Source:

- https://github.com/diffblue/cbmc/blob/develop/AGENTS.md

This supports the `AGENTS.md` rule that a bug fix usually needs one minimal regression proof, with more cases only when separate changed branches genuinely require them.

## General engineering guidance

### Tests must be useful and maintainable

Google's code-review guidance says tests should be correct, sensible, and useful; should actually fail when the code is broken; should make simple assertions; and should not receive complexity merely because they are test code. It also explicitly warns against speculative over-engineering.

Source:

- https://google.github.io/eng-practices/review/reviewer/looking-for.html

A mechanical budget cannot prove these properties. That is why the repository combines a tripwire with review rather than claiming that every test under a numeric limit is good.

### Keep the implementation and related proof conceptually small

Google's small-change guidance says a change should represent one self-contained idea and include related test code. Larger test-framework work, independent test refactoring, and unrelated test additions can be separate changes. It also states that there is no hard universal line-count rule.

Source:

- https://google.github.io/eng-practices/review/developer/small-cls.html

This supports separate profiles for ordinary implementation, broader approved work, and intentional test maintenance. It also supports treating new runner configuration or helper subsystems as test infrastructure instead of hiding them inside a normal feature task.

### Prefer fast, isolated, minimally sufficient unit tests

Microsoft's unit-testing guidance describes good unit tests as fast, isolated, repeatable, self-checking, and timely. It recommends avoiding infrastructure dependencies in unit tests and writing the minimally sufficient test input because unnecessary setup makes intent less clear and tests more brittle. It also warns that a high coverage number does not by itself establish quality and that over-ambitious percentage targets can be counterproductive.

Source:

- https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices

These principles support the rules against speculative matrices, infrastructure-heavy unit tests, and coverage-target-driven expansion.

### Use different test layers deliberately

Microsoft's testing architecture guidance distinguishes fast unit tests, slower integration tests, and the slowest end-to-end tests. It explicitly advises against putting every possible test into the initial build pipeline and recommends preserving a fast feedback loop as coverage grows.

Source:

- https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/testing

This supports tighter limits for integration, system, browser, and E2E additions, while leaving broad validation to CI and deliberate higher-risk workflows.

### Keep snapshots short enough to review

Jest's snapshot guidance says snapshots should be treated as code, kept focused and short, and reviewed rather than accepted blindly. The maintained `jest/no-large-snapshots` rule uses 50 lines as its default maximum for an individual stored snapshot.

Sources:

- https://jestjs.io/docs/snapshot-testing
- https://github.com/jest-community/eslint-plugin-jest/blob/main/docs/rules/no-large-snapshots.md

The focused profile therefore uses 50 added snapshot lines as a conservative starting tripwire. It is configurable and is not presented as a universal correctness threshold.

## GitHub enforcement

GitHub documents that CODEOWNERS can automatically request the relevant reviewers and that rulesets or branch protection can require code-owner approval before merge. GitHub also recommends assigning an owner to the CODEOWNERS file itself when it protects sensitive paths.

Sources:

- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets

The included template therefore owns tests, snapshots, fixtures, test infrastructure, policy code, the policy workflow, and CODEOWNERS itself. The pull-request workflow also loads its policy runner, implementation, and configuration from the trusted base revision. This prevents proposed policy code or configuration from defining the check evaluating that same pull request. The workflow file remains a sensitive control and should be protected by CODEOWNERS or enforced through an organization or enterprise ruleset-required workflow stored on a protected branch or policy repository.

The workflow templates use the current major versions published by the official action repositories as of July 29, 2026:

- `actions/checkout@v6`
- `actions/setup-python@v6`

Sources:

- https://github.com/actions/checkout
- https://github.com/actions/setup-python

## Community reports

Open Codex issues and community reports describe goal drift, invented acceptance criteria, repeated validation, and long-running test polling. These are useful reports of user pain, not controlled experiments and not proof of one model-level root cause.

Example:

- https://github.com/openai/codex/issues/35050

This repository addresses the deterministic parts of that problem:

- which validation command the agent may launch;
- how long that command may run;
- whether an unchanged state is tested again;
- whether a routine task may create a new test framework, helper subsystem, E2E suite, snapshot surface, or large matrix;
- whether cumulative test changes receive an independent status check and human ownership.

## Local design choices

The following values are configurable implementation choices, not externally proven universal optima:

- focused, expanded, and tests-only thresholds;
- exact file, line, case, infrastructure, snapshot, and fixture limits;
- path and test-declaration patterns;
- the default local validation deadline;
- stopping on the first failed local check;
- caching both passes and failures by repository fingerprint;
- loading pull-request enforcement code and configuration from the trusted base revision.

They are conservative reviewability tripwires. A project should tune them from its architecture, historical review pain, CI duration, and risk profile. The focused profile should remain representative of ordinary work; exceptional work should select an explicit broader profile rather than permanently weakening the default.

## What this repository cannot prove

- It cannot prove that every test inside the budget is useful.
- It cannot prove that a blocked test would be useless.
- It cannot detect all semantic duplication or every generated parameter case.
- It cannot establish that an expected-output or snapshot update is correct.
- It cannot make an inherently expensive test suite faster.
- It does not replace CI, review, sandboxing, or security controls.
- It does not prove that one model or coding-agent harness is always better.

It provides enforceable workflow boundaries so useful tests can still be written without letting ordinary tasks silently become large test-authoring and validation projects.
