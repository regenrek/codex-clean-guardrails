# codex-lean-guardrails

Hard guardrails for a specific Codex failure mode: a small implementation task grows into repeated full test, lint, typecheck, build, coverage, or CI runs while the user waits.

This repository does not ask the model to "please be minimal" and hope for the best. It changes the execution surface:

1. `AGENTS.md` defines a small scope and stopping contract.
2. A Codex `PreToolUse` hook blocks raw validation commands before they start.
3. The same hook prevents `apply_patch` from weakening the active guardrail files.
4. The agent gets one exact validation entry point: `./scripts/agent-check changed`.
5. That runner selects configured checks from changed files, has a hard wall-clock budget, stops on first failure, and caches both passes and failures for an identical repository state.
6. Full validation remains in CI or an explicit human-run session.

## What this prevents

```text
Codex edits one file
  -> runs the full suite
  -> waits/polls for 20 minutes
  -> changes another file
  -> reruns the full suite
  -> adds broad tests "for confidence"
  -> reruns lint + typecheck + build + suite
```

The guarded flow is:

```text
Codex makes one coherent edit batch
  -> ./scripts/agent-check changed
  -> related/bounded checks, max 120 seconds
  -> same repository state returns cached result
  -> full suite runs once in CI when appropriate
```

## Quick start

Requires Git, Python 3, and a current Codex CLI or desktop build with hooks.

```bash
git clone https://github.com/regenrek/codex-lean-guardrails.git
cd codex-lean-guardrails

# Install into an existing repository.
./scripts/install /path/to/project --recipe vitest-pnpm --install-profile

cd /path/to/project
./scripts/doctor
codex --profile lean
```

Inside Codex, open `/hooks` once to review and trust the project hook. Restart Codex after editing `hooks.json`; live hook edits have open reliability reports.

Available recipes:

```bash
--recipe vitest-pnpm
--recipe jest-pnpm
--recipe pytest-changed-tests
```

For another stack, copy `recipes/custom.example.json` to `.codex/agent-check.json` and define one genuinely targeted command.

## Files installed

```text
AGENTS.md
.codex/config.toml
.codex/hooks.json
.codex/hooks/test_guard.py
.codex/agent-check.json
scripts/agent-check
scripts/doctor
```

When a target already has `.codex/config.toml`, the installer does not silently rewrite it. It writes `.codex/config.guardrails.example.toml` for review. Existing `hooks.json` and `AGENTS.md` files are merged.

## The hard gate

The hook intercepts Codex Bash calls and denies direct validation through common runners and orchestrators, including:

```text
pnpm test                    pytest
npm run lint                 cargo test
pnpm exec vitest             go test
npx jest                     nx affected -t test
eslint / tsc                 make test
playwright / cypress         gradle test / mvn verify
```

Normal inspection is allowed:

```text
rg test src
git diff -- tests
cat tests/example.test.ts
```

The only agent validation path is the exact foreground command:

```bash
./scripts/agent-check changed
```

Alternate arguments such as `--config`, indirect execution through `python`, and background execution are denied. This prevents Codex from swapping in an unbounded validation plan or recreating the background polling loop.

### Guardrail integrity

The same `PreToolUse` hook observes `apply_patch` and denies edits to the active execution surface:

```text
.codex/agent-check.json
.codex/config.toml
.codex/hooks.json
.codex/hooks/test_guard.py
scripts/agent-check
```

Normal source patches remain allowed. This makes accidental self-weakening substantially harder; it is still a workflow guardrail rather than a security sandbox.

### Intentional overrides

Start the **Codex parent process** with an override when a human deliberately wants broader behavior:

```bash
# Deliberately allow raw/full validation inside this Codex session.
CODEX_ALLOW_FULL_VALIDATION=1 codex

# Deliberately maintain the protected guardrail files through apply_patch.
CODEX_ALLOW_GUARDRAIL_EDITS=1 codex
```

Putting either variable inside a command proposed by Codex does not bypass the hook because the hook runs before that child command starts.

## Configure the bounded runner

`.codex/agent-check.json` is deliberately small:

```json
{
  "version": 1,
  "budget_seconds": 120,
  "max_changed_files": 200,
  "cache": true,
  "cache_failures": true,
  "checks": [
    {
      "name": "Vitest related tests",
      "include": ["**/*.ts", "**/*.tsx"],
      "exclude": ["node_modules/**", "dist/**"],
      "command": [
        "pnpm", "exec", "vitest", "related", "--run", "{files}"
      ],
      "timeout_seconds": 90,
      "max_files": 60
    }
  ]
}
```

Commands are argv arrays and run without a shell. `{files}` expands to matching changed files as separate arguments. Checks run sequentially and stop on the first failure. The global budget covers repository inspection, fingerprinting, and all selected checks; Git calls and child processes receive bounded timeouts.

`max_changed_files` stops very large worktrees before hashing or execution, while each check can set a smaller `max_files`. A deleted file that matches a related-test check fails closed by default because dependency selection may be incomplete; CI remains authoritative. Set `allow_deleted: true` only for a command that genuinely handles deleted paths.

A fingerprint includes the current commit, configured plan, runner implementation, changed filenames, and changed file contents. Running the same failed or passing state again returns the cached result instead of spending the same minutes twice.

Do not place the full repository suite in this config. The hook would still prevent Codex from launching it directly, but the wrapper would become an expensive loophole.

## Keep full coverage in CI

Comprehensive tests are still valuable; they are simply moved out of the agent's edit loop. A practical split is:

| Lane | Purpose |
| --- | --- |
| `agent-check changed` | related tests or one small smoke/sentinel check |
| pull-request CI | affected packages and affected dependents |
| merge/nightly/release | full suite, broad E2E, coverage, release validation |

Cancel obsolete GitHub Actions runs so commits do not queue redundant suites:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

This repository's own workflow uses that policy and runs only its small zero-dependency guardrail tests.

## Lean Codex defaults

The included project config and optional `~/.codex/lean.config.toml` use:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
model_reasoning_effort = "medium"

[agents]
enabled = false

[features]
hooks = true
goals = false
```

The repository does not pin a model. The point is to constrain execution, not claim that one model always behaves better.

## Verify it

```bash
./scripts/doctor
python3 -m unittest discover -s tests -p 'test_*.py' -v
./scripts/agent-check changed
```

`doctor` checks the hook registration, simulates allowed and denied Bash and `apply_patch` calls, checks the wrapper CLI, and warns about Git worktrees because project hook discovery currently has an open worktree-specific issue.

## Limits

- Hooks are documented by OpenAI as guardrails, not a complete security boundary.
- Protected-file enforcement covers normal `apply_patch` calls. Arbitrary shell-generated file writes or specialized tool paths can still bypass a project workflow guardrail.
- The shell detector covers normal Codex-generated commands, not every possible shell-obfuscation technique.
- Project hooks only load for trusted projects.
- `write_stdin` polling does not run `PreToolUse` again, which is why the original long command must be blocked before it starts.
- Vitest `related` follows static imports and can miss dynamic loaders. Add one explicit sentinel check for those boundaries.
- Pytest has no generic source-to-test dependency graph. The included recipe only runs changed test files.
- Cache keys describe repository state and the configured plan, not every external machine or service dependency. CI remains the source of truth.
- This does not make a 30-minute suite faster. It prevents an agent from launching that suite repeatedly in its inner loop.

See [docs/evidence.md](docs/evidence.md) for the source-backed rationale and the distinction between official documentation and community issue evidence.

## License

MIT
