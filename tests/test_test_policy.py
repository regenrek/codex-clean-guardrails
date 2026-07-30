from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_MODULE = ROOT / ".codex/hooks/test_policy.py"
POLICY_CONFIG = ROOT / ".codex/test-policy.json"
DIFF_HOOK = ROOT / ".codex/hooks/test_guard.py"

spec = importlib.util.spec_from_file_location("test_policy_module", POLICY_MODULE)
assert spec and spec.loader
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


@contextmanager
def clean_policy_env(**values: str):
    keys = {
        "CODEX_TEST_PROFILE",
        "CODEX_ALLOW_BROAD_TEST_EDITS",
        "CODEX_TEST_BASE",
    }
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class PolicyRepo(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / ".codex").mkdir()
        (self.root / ".codex/test-policy.json").write_bytes(POLICY_CONFIG.read_bytes())
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
        (self.root / "tests/__snapshots__").mkdir(parents=True)
        (self.root / "tests/test_existing.py").write_text(
            "def test_existing():\n    assert True\n",
            encoding="utf-8",
        )
        (self.root / "tests/__snapshots__/existing.snap").write_text(
            "existing\n",
            encoding="utf-8",
        )
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.initial = self.git("rev-parse", "HEAD").strip()

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(f"git {' '.join(args)} failed: {completed.stderr}")
        return completed.stdout

    def product_change(self) -> None:
        (self.root / "src/app.py").write_text("def value():\n    return 2\n", encoding="utf-8")

    def write_test(self, name: str = "test_app.py", cases: int = 1) -> Path:
        path = self.root / "tests" / name
        path.parent.mkdir(exist_ok=True)
        body = "\n\n".join(
            f"def test_case_{index}():\n    assert True" for index in range(cases)
        )
        path.write_text(body + "\n", encoding="utf-8")
        return path


class TestRepositoryPolicy(PolicyRepo):
    def test_focused_profile_allows_product_change_and_one_regression_test(self) -> None:
        self.product_change()
        self.write_test(cases=1)
        with clean_policy_env():
            report = policy.evaluate_repository(self.root)
        self.assertTrue(report.ok, report.concise())
        self.assertEqual(report.summary.new_test_files, 1)
        self.assertEqual(report.summary.added_test_cases, 1)

    def test_focused_profile_rejects_tests_only_diff(self) -> None:
        self.write_test()
        with clean_policy_env():
            report = policy.evaluate_repository(self.root)
        self.assertFalse(report.ok)
        self.assertIn("no product-code change", "\n".join(report.violations))

    def test_tests_only_profile_allows_intentional_test_work(self) -> None:
        self.write_test()
        with clean_policy_env(CODEX_TEST_PROFILE="tests-only"):
            report = policy.evaluate_repository(self.root)
        self.assertTrue(report.ok, report.concise())

    def test_focused_profile_rejects_large_case_matrix(self) -> None:
        self.product_change()
        self.write_test(cases=11)
        with clean_policy_env():
            report = policy.evaluate_repository(self.root)
        self.assertFalse(report.ok)
        self.assertIn("added test cases", "\n".join(report.violations))

    def test_focused_profile_rejects_new_test_infrastructure(self) -> None:
        self.product_change()
        (self.root / "vitest.config.ts").write_text(
            "export default { test: { globals: true } };\n",
            encoding="utf-8",
        )
        with clean_policy_env():
            focused = policy.evaluate_repository(self.root)
        self.assertFalse(focused.ok)
        self.assertIn("new test-infrastructure files", "\n".join(focused.violations))

        with clean_policy_env(CODEX_TEST_PROFILE="tests-only"):
            intentional = policy.evaluate_repository(self.root)
        self.assertTrue(intentional.ok, intentional.concise())

    def test_snapshot_budget_allows_existing_update_but_rejects_new_snapshot(self) -> None:
        self.product_change()
        snapshots = self.root / "tests/__snapshots__"
        (snapshots / "existing.snap").write_text("existing changed\n", encoding="utf-8")
        with clean_policy_env():
            allowed = policy.evaluate_repository(self.root)
        self.assertTrue(allowed.ok, allowed.concise())

        (snapshots / "new.snap").write_text("new\n", encoding="utf-8")
        with clean_policy_env():
            blocked = policy.evaluate_repository(self.root)
        self.assertFalse(blocked.ok)
        self.assertIn("snapshot files touched", "\n".join(blocked.violations))

    def test_deleting_a_test_file_requires_tests_only_profile(self) -> None:
        (self.root / "tests/test_existing.py").unlink()
        with clean_policy_env():
            focused = policy.evaluate_repository(self.root)
        self.assertFalse(focused.ok)
        self.assertIn("deleted test files", "\n".join(focused.violations))

        with clean_policy_env(CODEX_TEST_PROFILE="tests-only"):
            maintenance = policy.evaluate_repository(self.root)
        self.assertTrue(maintenance.ok, maintenance.concise())

    def test_base_ref_counts_a_committed_test_as_new(self) -> None:
        self.product_change()
        self.write_test()
        self.git("add", ".")
        self.git("commit", "-m", "feature")
        with clean_policy_env():
            report = policy.evaluate_repository(self.root, base=self.initial)
        self.assertTrue(report.ok, report.concise())
        self.assertEqual(report.summary.new_test_files, 1)

    def test_rust_sibling_tests_filename_is_classified(self) -> None:
        self.product_change()
        path = self.root / "src/parser_tests.rs"
        path.write_text("#[test]\nfn parses_value() {}\n", encoding="utf-8")
        with clean_policy_env():
            report = policy.evaluate_repository(self.root)
        self.assertTrue(report.ok, report.concise())
        self.assertEqual(report.summary.test_files[0].path, "src/parser_tests.rs")

    def test_support_templates_are_not_counted_as_product_tests(self) -> None:
        templates = self.root / "templates"
        templates.mkdir()
        (templates / "CODEOWNERS.tests.example").write_text(
            "/tests/ @test-owners\n",
            encoding="utf-8",
        )
        with clean_policy_env():
            report = policy.evaluate_repository(self.root)
        self.assertTrue(report.ok, report.concise())
        self.assertEqual(report.summary.test_files, ())

    def test_bootstrapping_a_first_test_suite_requires_an_explicit_profile(self) -> None:
        for path in (self.root / "tests").rglob("*"):
            if path.is_file():
                path.unlink()
        self.git("add", "-A")
        self.git("commit", "-m", "remove test suite")
        self.product_change()
        self.write_test()

        with clean_policy_env():
            focused = policy.evaluate_repository(self.root)
        self.assertFalse(focused.ok)
        self.assertIn("baseline has no test suite", "\n".join(focused.violations))

        with clean_policy_env(CODEX_TEST_PROFILE="tests-only"):
            tests_only = policy.evaluate_repository(self.root)
        self.assertTrue(tests_only.ok, tests_only.concise())


class TestPatchPolicy(PolicyRepo):
    def test_small_tdd_patch_is_allowed_before_product_edit(self) -> None:
        patch = """*** Begin Patch
*** Add File: tests/test_regression.py
+def test_regression():
+    assert True
*** End Patch
"""
        with clean_policy_env():
            report = policy.evaluate_patch(self.root, patch)
        self.assertTrue(report.ok, report.concise())

    def test_large_single_patch_is_rejected(self) -> None:
        lines = "\n".join(f"+def test_case_{index}(): assert True" for index in range(11))
        patch = f"*** Begin Patch\n*** Add File: tests/test_matrix.py\n{lines}\n*** End Patch\n"
        with clean_policy_env():
            report = policy.evaluate_patch(self.root, patch)
        self.assertFalse(report.ok)
        self.assertIn("added test cases", "\n".join(report.violations))

    def test_delete_then_add_same_test_path_counts_as_one_updated_file(self) -> None:
        patch = """*** Begin Patch
*** Delete File: tests/test_example.py
*** Add File: tests/test_example.py
+def test_replacement():
+    assert True
*** End Patch
"""
        with clean_policy_env():
            summary = policy.summarize_patch(self.root, patch)
        self.assertEqual(summary.changed_paths, ("tests/test_example.py",))
        self.assertEqual(summary.test_files_touched, 1)
        self.assertEqual(summary.new_test_files, 0)
        self.assertEqual(summary.deleted_test_files, 0)
        self.assertEqual(summary.added_test_cases, 1)

    def test_repeated_updates_to_same_test_path_count_as_one_file(self) -> None:
        patch = """*** Begin Patch
*** Update File: tests/test_example.py
@@
+def test_first():
+    assert True
*** Update File: tests/test_example.py
@@
+def test_second():
+    assert True
*** End Patch
"""
        with clean_policy_env():
            summary = policy.summarize_patch(self.root, patch)
        self.assertEqual(summary.changed_paths, ("tests/test_example.py",))
        self.assertEqual(summary.test_files_touched, 1)
        self.assertEqual(summary.added_test_cases, 2)

    def test_first_suite_patch_requires_explicit_profile(self) -> None:
        for path in (self.root / "tests").rglob("*"):
            if path.is_file():
                path.unlink()
        self.git("add", "-A")
        self.git("commit", "-m", "remove test suite")
        patch = """*** Begin Patch
*** Add File: tests/test_first.py
+def test_first():
+    assert True
*** End Patch
"""

        with clean_policy_env():
            focused = policy.evaluate_patch(self.root, patch)
        self.assertFalse(focused.ok)
        self.assertIn("baseline has no test suite", "\n".join(focused.violations))

        with clean_policy_env(CODEX_TEST_PROFILE="tests-only"):
            intentional = policy.evaluate_patch(self.root, patch)
        self.assertTrue(intentional.ok, intentional.concise())


class TestDiffHook(PolicyRepo):
    def run_hook(self, event: str, *, active: bool = False) -> dict:
        payload = {
            "session_id": "test",
            "turn_id": "test",
            "cwd": str(self.root),
            "hook_event_name": event,
            "permission_mode": "default",
            "stop_hook_active": active,
        }
        if event == "PostToolUse":
            payload.update(
                {
                    "tool_name": "apply_patch",
                    "tool_use_id": "test",
                    "tool_input": {"command": "patch"},
                }
            )
        with clean_policy_env():
            completed = subprocess.run(
                [sys.executable, str(DIFF_HOOK)],
                input=json.dumps(payload),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                env=os.environ.copy(),
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_post_and_stop_hooks_surface_cumulative_violation_without_looping(self) -> None:
        self.write_test()
        post = self.run_hook("PostToolUse")
        first_stop = self.run_hook("Stop")
        second_stop = self.run_hook("Stop", active=True)
        self.assertEqual(post["decision"], "block")
        self.assertEqual(first_stop["decision"], "block")
        self.assertFalse(second_stop["continue"])
        self.assertEqual(second_stop["stopReason"], "test-authoring-policy-remains-violated")


if __name__ == "__main__":
    unittest.main()
