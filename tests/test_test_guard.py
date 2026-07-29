from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / ".codex/hooks/test_guard.py"

spec = importlib.util.spec_from_file_location("test_guard", HOOK_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hook
spec.loader.exec_module(hook)


def inspect(command: str):
    last = hook.Inspection(False)
    for segment in hook.split_shell(command):
        result = hook.inspect_argv(segment.argv, segment.operator_after)
        if result.blocked or result.is_agent_check:
            return result
        last = result
    return last


class TestGuardClassification(unittest.TestCase):
    def test_allows_normal_search_that_mentions_test(self) -> None:
        self.assertFalse(inspect("rg test src").blocked)

    def test_allows_git_diff_for_test_path(self) -> None:
        self.assertFalse(inspect("git diff -- tests/example_test.py").blocked)

    def test_allows_normal_dev_script(self) -> None:
        self.assertFalse(inspect("pnpm run dev").blocked)

    def test_blocks_package_manager_test(self) -> None:
        self.assertTrue(inspect("pnpm test").blocked)
        self.assertTrue(inspect("npm run test:unit").blocked)
        self.assertTrue(inspect("pnpm exec vitest related --run src/a.ts").blocked)

    def test_blocks_direct_runners(self) -> None:
        self.assertTrue(inspect("pytest -q").blocked)
        self.assertTrue(inspect("eslint src").blocked)
        self.assertTrue(inspect("playwright test").blocked)

    def test_blocks_nested_shell_validation(self) -> None:
        self.assertTrue(inspect("bash -lc 'cd app && python3 -m pytest -q'").blocked)

    def test_blocks_build_system_validation(self) -> None:
        self.assertTrue(inspect("cargo test --workspace").blocked)
        self.assertTrue(inspect("go test ./...").blocked)
        self.assertTrue(inspect("nx affected -t test").blocked)
        self.assertTrue(inspect("make").blocked)

    def test_allows_agent_check_in_foreground(self) -> None:
        result = inspect("./scripts/agent-check changed")
        self.assertFalse(result.blocked)
        self.assertTrue(result.is_agent_check)

    def test_blocks_agent_check_in_background(self) -> None:
        result = inspect("./scripts/agent-check changed &")
        self.assertTrue(result.blocked)
        self.assertTrue(result.is_agent_check)

    def test_blocks_agent_check_options_that_could_swap_the_config(self) -> None:
        result = inspect("./scripts/agent-check changed --config /tmp/full-suite.json")
        self.assertTrue(result.blocked)
        self.assertTrue(result.is_agent_check)

    def test_blocks_indirect_agent_check_invocation(self) -> None:
        result = inspect("python3 ./scripts/agent-check changed --config /tmp/full-suite.json")
        self.assertTrue(result.blocked)
        self.assertTrue(result.is_agent_check)


class TestGuardHookProtocol(unittest.TestCase):
    @staticmethod
    def run_hook(
        command: str,
        override: bool = False,
        *,
        tool_name: str = "Bash",
        edit_override: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        payload = json.dumps(
            {
                "session_id": "test",
                "turn_id": "test",
                "cwd": str(ROOT),
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_use_id": "test",
                "tool_input": {"command": command},
            }
        )
        env = os.environ.copy()
        if override:
            env["CODEX_ALLOW_FULL_VALIDATION"] = "1"
        else:
            env.pop("CODEX_ALLOW_FULL_VALIDATION", None)
        if edit_override:
            env["CODEX_ALLOW_GUARDRAIL_EDITS"] = "1"
        else:
            env.pop("CODEX_ALLOW_GUARDRAIL_EDITS", None)
        return subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            check=False,
        )

    def test_denial_uses_current_codex_shape(self) -> None:
        completed = self.run_hook("npm test")
        self.assertEqual(completed.returncode, 0)
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("agent-check", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_safe_command_emits_no_output(self) -> None:
        completed = self.run_hook("git status --short")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_parent_override_allows_full_validation(self) -> None:
        completed = self.run_hook("npm test", override=True)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")


    def test_protected_guardrail_patch_is_denied(self) -> None:
        patch = """*** Begin Patch
*** Update File: .codex/agent-check.json
@@
-{}
+{"checks": []}
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(".codex/agent-check.json", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_normal_source_patch_is_allowed(self) -> None:
        patch = """*** Begin Patch
*** Update File: src/app.py
@@
-old
+new
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_parent_edit_override_allows_guardrail_maintenance(self) -> None:
        patch = """*** Begin Patch
*** Update File: scripts/agent-check
@@
-old
+new
*** End Patch
"""
        completed = self.run_hook(
            patch,
            tool_name="apply_patch",
            edit_override=True,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_malformed_payload_fails_closed(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input="{}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
