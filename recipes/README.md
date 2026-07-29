# Validation recipes

Copy exactly one recipe to `.codex/agent-check.json`, then adapt it to the repository.

- `vitest-pnpm.json` uses Vitest's documented `related --run` mode. It follows static imports; dynamic loaders need an explicit sentinel check.
- `jest-pnpm.json` uses Jest's documented `--findRelatedTests` mode.
- `pytest-changed-tests.json` runs only changed test files. Pytest has no generic source-to-test dependency graph, so source changes need a project-specific command or CI coverage.
- `custom.example.json` is the schema starting point for another stack.

Commands are arrays and run without a shell. `{files}` must be its own array element and expands to matching changed files as separate arguments.

A check should remain bounded. Do not put the full repository suite in this file; that would recreate the problem this project is designed to prevent.
