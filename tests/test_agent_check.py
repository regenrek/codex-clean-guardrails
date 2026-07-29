from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUNNER = SOURCE_ROOT / "scripts/agent-check"
SOURCE_TEST_POLICY = SOURCE_ROOT / ".codex/hooks/test_policy.py"
SOURCE_TEST_POLICY_CONFIG = SOURCE_ROOT / ".codex/test-policy.json"
SOURCE_TEST_POLICY_CLI = SOURCE_ROOT / "scripts/test-policy"


def load_runner_module():
    loader = importlib.machinery.SourceFileLoader("agent_check_runner", str(SOURCE_RUNNER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("could not load scripts/agent-check")
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


RUNNER = load_runner_module()


class TestSelectionLogic(unittest.TestCase):
    def test_double_star_matches_root_and_nested_files(self) -> None:
        self.assertTrue(RUNNER.glob_matches("app.py", "**/*.py"))
        self.assertTrue(RUNNER.glob_matches("src/app.py", "**/*.py"))
        self.assertFalse(RUNNER.glob_matches("README.md", "**/*.py"))

    def test_files_expand_as_individual_argv_elements(self) -> None:
        command = RUNNER.expand_command(
            ["tool", "related", "{files}"], ["src/a.py", "src/file with spaces.py"]
        )
        self.assertEqual(
            command,
            ["tool", "related", "src/a.py", "src/file with spaces.py"],
        )

    def test_unmatched_files_select_no_check(self) -> None:
        config = {
            "checks": [
                {
                    "name": "python only",
                    "include": ["**/*.py"],
                    "command": ["python3", "-m", "unittest"],
                }
            ]
        }
        self.assertEqual(RUNNER.select_checks(config, ["notes.md"]), [])

    def test_deleted_matching_file_fails_closed_by_default(self) -> None:
        config = {
            "checks": [
                {
                    "name": "related",
                    "include": ["**/*.py"],
                    "command": ["python3", "-m", "unittest"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            selected = RUNNER.select_checks(config, ["deleted.py"], Path(directory))
        self.assertEqual(len(selected), 1)
        self.assertIn("matched deleted files", selected[0]["selection_error"])

    def test_too_many_files_fails_closed_instead_of_broadening(self) -> None:
        config = {
            "checks": [
                {
                    "name": "bounded",
                    "include": ["**/*.py"],
                    "command": ["python3", "-m", "unittest"],
                    "max_files": 1,
                }
            ]
        }
        selected = RUNNER.select_checks(config, ["a.py", "b.py"])
        self.assertEqual(len(selected), 1)
        self.assertIn("leave broad validation to CI", selected[0]["selection_error"])


class AgentCheckFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.external_log = Path(self.temp.name) / "runs.log"

        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")

        (self.root / "scripts").mkdir()
        (self.root / ".codex/hooks").mkdir(parents=True)
        shutil.copy2(SOURCE_RUNNER, self.root / "scripts/agent-check")
        shutil.copy2(SOURCE_TEST_POLICY_CLI, self.root / "scripts/test-policy")
        shutil.copy2(SOURCE_TEST_POLICY, self.root / ".codex/hooks/test_policy.py")
        shutil.copy2(SOURCE_TEST_POLICY_CONFIG, self.root / ".codex/test-policy.json")
        os.chmod(self.root / "scripts/agent-check", 0o755)
        os.chmod(self.root / "scripts/test-policy", 0o755)
        (self.root / ".gitignore").write_text(".codex/cache/\n", encoding="utf-8")
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "initial")

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

    def write_config(self, checks: list[dict], **overrides) -> None:
        config = {
            "version": 1,
            "budget_seconds": 5,
            "cache": True,
            "cache_failures": True,
            "max_output_chars": 4000,
            "checks": checks,
            **overrides,
        }
        (self.root / ".codex/agent-check.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

    def run_check(self, *extra: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in (
            "CODEX_TEST_PROFILE",
            "CODEX_ALLOW_BROAD_TEST_EDITS",
            "CODEX_TEST_BASE",
        ):
            env.pop(key, None)
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/agent-check"), "changed", *extra],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            check=False,
        )


class TestAgentCheckIntegration(AgentCheckFixture):
    def test_matching_files_are_expanded_cached_and_invalidated_by_content(self) -> None:
        command = [
            sys.executable,
            "-c",
            (
                "import pathlib,sys; "
                f"pathlib.Path({str(self.external_log)!r}).open('a').write('|'.join(sys.argv[1:])+'\\n')"
            ),
            "{files}",
        ]
        self.write_config(
            [
                {
                    "name": "record files",
                    "include": ["src/**/*.py", "src/*.py"],
                    "command": command,
                    "timeout_seconds": 2,
                }
            ]
        )
        path = self.root / "src/app.py"
        path.parent.mkdir()
        path.write_text("print('one')\n", encoding="utf-8")

        first = self.run_check()
        cached = self.run_check()
        path.write_text("print('two')\n", encoding="utf-8")
        changed = self.run_check()

        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(cached.returncode, 0, cached.stderr + cached.stdout)
        self.assertEqual(changed.returncode, 0, changed.stderr + changed.stdout)
        self.assertIn("AGENT_CHECK_RESULT", first.stdout)
        self.assertIn("cached pass", cached.stdout)
        first_result = json.loads(first.stdout.rsplit("AGENT_CHECK_RESULT ", 1)[1])
        cached_result = json.loads(cached.stdout.rsplit("AGENT_CHECK_RESULT ", 1)[1])
        self.assertTrue(cached_result["cached"])
        self.assertEqual(
            cached_result["cached_result_duration_seconds"],
            first_result["duration_seconds"],
        )
        self.assertEqual(
            self.external_log.read_text(encoding="utf-8"),
            "src/app.py\nsrc/app.py\n",
        )
    def test_test_policy_failure_prevents_validation_command(self) -> None:
        command = [
            sys.executable,
            "-c",
            f"import pathlib; pathlib.Path({str(self.external_log)!r}).write_text('ran')",
        ]
        self.write_config(
            [
                {
                    "name": "must not run",
                    "include": ["**/*.py"],
                    "command": command,
                    "timeout_seconds": 2,
                }
            ]
        )
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "test_only.py").write_text(
            "def test_only():\n    assert True\n",
            encoding="utf-8",
        )

        completed = self.run_check()

        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        self.assertIn("test-authoring policy failed", completed.stdout)
        self.assertFalse(self.external_log.exists())

    def test_timeout_kills_command_and_caches_the_timeout(self) -> None:
        self.write_config(
            [
                {
                    "name": "sleep",
                    "include": ["**/*.py"],
                    "command": [sys.executable, "-c", "import time; time.sleep(5)"],
                    "timeout_seconds": 0.2,
                }
            ],
            budget_seconds=2,
        )
        (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")

        started = time.monotonic()
        first = self.run_check()
        first_duration = time.monotonic() - started
        started = time.monotonic()
        cached = self.run_check()
        cached_duration = time.monotonic() - started

        self.assertEqual(first.returncode, 124, first.stderr + first.stdout)
        self.assertEqual(cached.returncode, 124, cached.stderr + cached.stdout)
        self.assertLess(first_duration, 2)
        self.assertLess(cached_duration, first_duration)
        self.assertIn("cached timeout", cached.stdout)


if __name__ == "__main__":
    unittest.main()
