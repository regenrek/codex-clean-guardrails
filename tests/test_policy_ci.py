from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUSTED_RUNNER = ROOT / "scripts/test-policy-ci"
POLICY_MODULE = ROOT / ".codex/hooks/test_policy.py"
POLICY_CONFIG = ROOT / ".codex/test-policy.json"


class TrustedPolicyRepo(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / ".codex/hooks").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / ".codex/hooks/test_policy.py").write_bytes(POLICY_MODULE.read_bytes())
        (self.root / ".codex/test-policy.json").write_bytes(POLICY_CONFIG.read_bytes())
        (self.root / "scripts/test-policy-ci").write_bytes(TRUSTED_RUNNER.read_bytes())
        (self.root / "src/app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
        (self.root / "tests/test_existing.py").write_text(
            "def test_existing():\n    assert True\n",
            encoding="utf-8",
        )
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout

    def run_policy(self, **extra_env: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        env = os.environ.copy()
        for key in (
            "CODEX_TEST_PROFILE",
            "CODEX_ALLOW_BROAD_TEST_EDITS",
            "CODEX_ALLOW_GUARDRAIL_EDITS",
            "CODEX_TEST_BASE",
        ):
            env.pop(key, None)
        env.update(extra_env)
        completed = subprocess.run(
            [
                sys.executable,
                str(TRUSTED_RUNNER),
                "--root",
                str(self.root),
                "--base",
                self.base,
                "--json",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,
        )
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        return completed, json.loads(completed.stdout)


class TestTrustedPolicyRunner(TrustedPolicyRepo):
    def test_uses_base_policy_even_when_pull_request_weakens_current_config(self) -> None:
        config = json.loads((self.root / ".codex/test-policy.json").read_text(encoding="utf-8"))
        config["profiles"]["focused"]["max_added_test_cases"] = 1000
        (self.root / ".codex/test-policy.json").write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "src/app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
        cases = "\n\n".join(
            f"def test_case_{index}():\n    assert True" for index in range(11)
        )
        (self.root / "tests/test_matrix.py").write_text(cases + "\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "weaken policy and add matrix")

        completed, result = self.run_policy(CODEX_ALLOW_GUARDRAIL_EDITS="1")

        self.assertEqual(completed.returncode, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["trusted_policy_ref"], self.base)
        self.assertTrue(
            any("added test cases" in value for value in result["violations"]),
            result,
        )

    def test_policy_files_require_separate_maintenance_approval(self) -> None:
        config_path = self.root / ".codex/test-policy.json"
        config_path.write_text(config_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "touch policy")

        blocked, blocked_result = self.run_policy()
        allowed, allowed_result = self.run_policy(CODEX_ALLOW_GUARDRAIL_EDITS="1")

        self.assertEqual(blocked.returncode, 1)
        self.assertIn(".codex/test-policy.json", blocked_result["protected_policy_changes"])
        self.assertFalse(blocked_result["maintenance_override"])
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertTrue(allowed_result["ok"])
        self.assertTrue(allowed_result["maintenance_override"])


if __name__ == "__main__":
    unittest.main()
