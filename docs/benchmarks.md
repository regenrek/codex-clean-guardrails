# Dogfood benchmarks

These benchmarks ask the same practical question: can repository-owned guardrails reduce speculative test growth and repeated validation without lowering the quality of the delivered app?

The short answer so far is **sometimes**. The first run was incomplete, the second reduced tests but also missed real defects, and the third delivered the strongest result: equivalent measured quality with substantially less test code. Three local runs are useful engineering feedback, not scientific proof.

## How the comparison works

Each benchmark starts from two repositories with the same tracked application surface:

- **Default** uses the normal Codex setup.
- **Lean** adds this repository's `AGENTS.md`, hooks, cumulative test policy, and bounded `agent-check` workflow.

The same product prompt is submitted manually in a fresh Codex session. The harness then measures the Git diff, authored tests, validation behavior, hidden acceptance checks, the full test suite, production build, and E2E suite. Later runs also recover model, timing, approval, and follow-up data from the Codex session log.

The product prompts describe acceptance criteria rather than asking for a particular number or kind of tests. That leaves test selection to Codex and the repository workflow.

## Benchmark 1: Signal Path

Signal Path was a responsive 4×4 browser puzzle with deterministic daily challenges, persistence, keyboard access, and a strict parser contract.

| Result | Default |
| --- | ---: |
| Completion time | 352 s |
| Production lines added | 754 |
| Test lines added | 82 |
| Test/production ratio | 10.9% |
| Full suite | passed |
| Production build | passed |
| Hidden acceptance | **failed** |

There is no Lean result: the Lean run was accidentally never started. This benchmark therefore cannot say anything about Default versus Lean. It did reveal that the initial task and harness were too weak to support a trustworthy comparison, especially when a polished app could still miss the hidden contract.

## Benchmark 2: Relay Control

Relay Control was an offline incident-response dashboard with a forward-only workflow, timeline events, SLA state, filters, history, persistence, and import/export.

| Result | Default | Lean |
| --- | ---: | ---: |
| Production lines added | 724 | 606 |
| Test lines added | 98 | 60 |
| Added runtime test cases | 5 | 1 |
| Added E2E cases | 1 | 0 |
| Hidden acceptance | 12/12 | 12/12 |
| Full suite | passed | passed |
| Production build | passed | **failed** |
| E2E suite | passed | **failed** |

Lean authored 39% fewer test lines, but this was not a win. Its build failed on an unsafe `unknown` access, and its unchanged E2E test still expected the starter heading after the UI had been replaced. Default added more coverage and shipped cleanly.

The timing data from this run is not suitable for a headline comparison. The original harness failed to associate sessions reliably, and the Default session included a manual continuation after an approval pause. Benchmark 2 led to three concrete changes:

- recover session context using Markdown-normalized prompt matching;
- separate approval and manual-follow-up time and mark such runs invalid;
- strengthen hidden acceptance and require build and E2E success in the interpretation.

## Benchmark 3: Shiftline

Shiftline was a larger offline workforce scheduler with a weekly board, staffing conflicts, filters, undo/redo, publication rules, persistence, import/export, and a separate mobile layout. This was the first clean paired run: both sessions used GPT-5.6 at medium effort, required no follow-up, and passed the same preflight.

| Result | Default | Lean |
| --- | ---: | ---: |
| Completion time | 512.4 s | 518.9 s |
| Changed files | 5 | 5 |
| Production lines added | 689 | 608 |
| Test lines added | 92 | 37 |
| Test/production ratio | 13.4% | 6.1% |
| Added runtime test cases | 6 | 4 |
| Added E2E cases | 2 | 0 |
| Hidden acceptance | 20/20 | 20/20 |
| Full suite | passed | passed |
| Production build | passed | passed |
| E2E suite | passed | passed |
| Manual follow-ups | 0 | 0 |
| Hook rejections | 0 | 0 |

Lean added about 60% fewer test lines and 12% less production code while finishing only 1.3% slower. Both implementations were polished, responsive, and functionally complete under the measured checks. Lean used four bounded `agent-check` calls; Default directly invoked the full test suite five times, the build six times, and E2E four times.

There is still a real trade-off. Default's two additional E2E cases covered creating and undoing a shift and rejecting an ineligible assignment. Those are useful user flows, not obvious test spam. Lean passed the existing E2E smoke test and all hidden checks, but it left less direct UI regression coverage behind.

## What we take from this

The results support the current conservative direction, not a stronger claim:

- bounded validation clearly changes agent behavior and can avoid repeated full-suite work;
- fewer tests are valuable only when build, E2E, and hidden acceptance remain green;
- zero hook rejections in Benchmark 3 suggests the instructions shaped behavior without creating a correction loop;
- the current limits should not be tightened based on one successful pair, especially because Default's extra E2E coverage had value.

## Limitations

- There is only one valid paired run with complete modern instrumentation.
- Coding agents are nondeterministic; one run per variant does not estimate variance.
- Runs were local and sequential, so caches, machine load, and run order may affect timing.
- Added lines and test counts measure quantity, not maintainability or defect-detection power.
- Hidden acceptance covers selected contracts, not every accessibility, persistence, or interaction edge case.
- The apps and harness were designed by the same evaluator, so task and metric selection can carry bias.

The honest conclusion is narrow: Benchmark 3 shows that these guardrails *can* preserve measured quality while cutting test growth and validation churn. Benchmark 2 shows they can also accompany an under-validated result. More paired runs across different stacks and task types are needed before generalizing further.
