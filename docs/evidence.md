# Evidence and boundaries

Verified on July 29, 2026.

## Official Codex behavior used by this repository

### Hooks can block Bash before execution

OpenAI documents `PreToolUse` for Bash, unified exec, and file edits performed through `apply_patch`. A hook may return `hookSpecificOutput.permissionDecision = "deny"` with a reason. Bash and `apply_patch` input is available as `tool_input.command`.

Source: https://developers.openai.com/codex/hooks

The same documentation states:

- shell commands and unified exec match as `Bash`;
- project hooks require a trusted project;
- `write_stdin` polling does not run `PreToolUse` again;
- hooks are useful guardrails, not a complete enforcement boundary;
- hook changes should be reviewed and trusted.

These facts justify blocking the original expensive command instead of trying to stop later polling. They also support the protected-file check that prevents normal `apply_patch` calls from weakening the active runner and hook configuration.

### The terminal polling setting is not a process timeout

`background_terminal_max_timeout` controls the maximum empty `write_stdin` polling window. It does not impose a wall-clock limit on the underlying command.

Source: https://developers.openai.com/codex/config-reference

This repository therefore enforces its own total deadline, bounded Git inspection, and child-process-tree timeout inside `scripts/agent-check`.

### Configuration precedence and lean settings

OpenAI documents project config, profile files at `$CODEX_HOME/<name>.config.toml`, and `--profile <name>`. Project config has higher precedence than the selected profile.

Source: https://developers.openai.com/codex/config-basic

The current configuration reference documents:

- `agents.enabled` defaults to `true`;
- `features.goals` enables persisted goals and automatic continuation and defaults to on;
- `features.hooks` is the canonical hook feature key;
- `approval_policy = "on-request"` and `sandbox_mode = "workspace-write"` are supported.

Source: https://developers.openai.com/codex/config-reference

### AGENTS.md is a supported instruction layer

OpenAI documents repository and nested `AGENTS.md` files as Codex instruction sources.

Source: https://developers.openai.com/codex/guides/agents-md

The policy in this repository is intentionally short because OpenAI's GPT-5.6 guidance recommends lean prompts, one statement per instruction, and explicit autonomy/stopping boundaries.

Source: https://developers.openai.com/api/docs/guides/latest-model

## Community issue evidence

Community issues are evidence of observed behavior, not official confirmation of every claimed root cause.

### Background command polling

Open issue #13733 reports that long builds/tests can produce repeated `write_stdin` polls and full model turns while no meaningful state changes. It includes source analysis and multiple confirmations, but remains a user-filed issue.

https://github.com/openai/codex/issues/13733

Recent issue #35259 reports similar model-mediated wait/status polling in Codex Desktop.

https://github.com/openai/codex/issues/35259

The repository's response is conservative: do not start long repository-wide validation from the agent loop at all.

### Read-only batching instruction

Issue #35050 presents controlled same-model comparisons where a concrete Code Mode batching instruction reduced model cycles and estimated weighted usage on two read-heavy repository investigations. The author reports 27–45% lower weighted usage in the repeated datasets and explicitly limits the claim to tested workloads.

https://github.com/openai/codex/issues/35050

The short batching instruction in `AGENTS.md` is included as an efficiency improvement for independent reads. It is not presented as a fix for expensive test execution.

### Hook reliability caveats

Open issues report project hook problems in Git worktrees and after live hook edits:

- https://github.com/openai/codex/issues/27133
- https://github.com/openai/codex/issues/21160

For that reason, `scripts/doctor` warns when `.git` is a file, and the README tells users to restart Codex and inspect `/hooks` after changes.

## Test selection primitives

Vitest documents `vitest related --run <files>` for tests related to source files and notes that it relies on static imports.

https://vitest.dev/guide/cli

Jest documents `--findRelatedTests` as a way to find and run tests related to supplied source files.

https://jestjs.io/docs/cli

These are used only in explicit recipes. The repository does not pretend that a universal affected-test algorithm exists for every language or build system.

## CI cancellation

GitHub documents workflow concurrency groups and `cancel-in-progress: true`, which prevents obsolete runs for the same group from continuing after a newer run starts.

https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

## What is deliberately not claimed

- No prompt can guarantee a model will remain minimal.
- No hook is a complete sandbox; the protected-file rule covers normal `apply_patch` calls, not arbitrary file writes through every possible tool path.
- Related-test selection is not equivalent to a full suite.
- Switching to Pi or another harness does not make the underlying tests faster.
- The reported issue benchmarks do not prove the same percentage improvement for all repositories.
