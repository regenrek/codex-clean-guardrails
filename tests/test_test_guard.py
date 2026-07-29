from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_allows_git_add_with_agent_check_path(self) -> None:
        self.assertFalse(inspect("git add -- scripts/agent-check").blocked)


class TestGuardHookProtocol(unittest.TestCase):
    @staticmethod
    def run_hook(
        command: str,
        override: bool = False,
        *,
        tool_name: str = "Bash",
        edit_override: bool = False,
        test_edit_override: bool = False,
        test_profile: str | None = None,
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
        if test_edit_override:
            env["CODEX_ALLOW_BROAD_TEST_EDITS"] = "1"
        else:
            env.pop("CODEX_ALLOW_BROAD_TEST_EDITS", None)
        if test_profile is not None:
            env["CODEX_TEST_PROFILE"] = test_profile
        else:
            env.pop("CODEX_TEST_PROFILE", None)
        env.pop("CODEX_TEST_BASE", None)
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

    def test_test_policy_file_is_protected(self) -> None:
        patch = """*** Begin Patch
*** Update File: .codex/test-policy.json
@@
-  "version": 1,
+  "version": 2,
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(".codex/test-policy.json", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_codeowners_file_is_protected(self) -> None:
        patch = """*** Begin Patch
*** Update File: .github/CODEOWNERS
@@
-/tests/ @test-owners
+/tests/ @anyone
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(".github/CODEOWNERS", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_agents_file_is_protected(self) -> None:
        patch = """*** Begin Patch
*** Update File: AGENTS.md
@@
-- Prefer the smallest coherent diff.
+- Write every possible test.
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("AGENTS.md", output["hookSpecificOutput"]["permissionDecisionReason"])

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

    def test_focused_test_patch_is_allowed(self) -> None:
        patch = """*** Begin Patch
*** Add File: tests/test_regression.py
+def test_regression():
+    assert True
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")

    def test_oversized_test_patch_is_denied(self) -> None:
        lines = "\n".join(f"+def test_case_{index}(): assert True" for index in range(11))
        patch = f"*** Begin Patch\n*** Add File: tests/test_matrix.py\n{lines}\n*** End Patch\n"
        completed = self.run_hook(patch, tool_name="apply_patch")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("added test cases", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_direct_shell_write_to_test_path_is_denied(self) -> None:
        completed = self.run_hook("cat > tests/generated_test.py <<'EOF'\nassert True\nEOF")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Direct shell write", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_new_test_infrastructure_patch_is_denied(self) -> None:
        patch = """*** Begin Patch
*** Add File: vitest.config.ts
+export default { test: { globals: true } };
*** End Patch
"""
        completed = self.run_hook(patch, tool_name="apply_patch")
        output = json.loads(completed.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "new test-infrastructure files",
            output["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_parent_test_edit_override_allows_broad_patch(self) -> None:
        lines = "\n".join(f"+def test_case_{index}(): assert True" for index in range(20))
        patch = f"*** Begin Patch\n*** Add File: tests/test_matrix.py\n{lines}\n*** End Patch\n"
        completed = self.run_hook(
            patch,
            tool_name="apply_patch",
            test_edit_override=True,
        )
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

    def test_read_only_post_tool_use_skips_cumulative_rescan(self) -> None:
        with patch.object(hook, "evaluate_repository", side_effect=AssertionError("unexpected scan")):
            hook.handle_post({"cwd": str(ROOT)}, "Bash", "rg test src")

    def test_unknown_post_tool_use_command_triggers_cumulative_rescan(self) -> None:
        report = type("Report", (), {"ok": True})()
        with patch.object(hook, "evaluate_repository", return_value=report) as evaluate:
            hook.handle_post(
                {"cwd": str(ROOT)},
                "Bash",
                'python3 -c "from pathlib import Path; Path(\'tests/x.py\').write_text(\'x\')"',
            )
        evaluate.assert_called_once()

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
