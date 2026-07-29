from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "install"
START = "<!-- codex-lean-guardrails:start -->"


class InstallTests(unittest.TestCase):
    def test_installer_merges_existing_project_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "project"
            target.mkdir()
            subprocess.run(["git", "init", "-q", str(target)], check=True)

            (target / ".codex").mkdir()
            original_config = 'model = "project-specific"\n'
            (target / ".codex/config.toml").write_text(original_config, encoding="utf-8")
            (target / ".codex/hooks.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "matcher": "^Bash$",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "python3 .codex/hooks/existing.py",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (target / "AGENTS.md").write_text("# Existing project rules\n", encoding="utf-8")

            command = [
                sys.executable,
                str(INSTALL),
                str(target),
                "--recipe",
                "pytest-changed-tests",
            ]
            first = subprocess.run(command, text=True, capture_output=True, check=False)
            second = subprocess.run(command, text=True, capture_output=True, check=False)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(
                (target / ".codex/config.toml").read_text(encoding="utf-8"),
                original_config,
            )
            self.assertFalse((target / ".codex/config.guardrails.example.toml").exists())

            agents = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# Existing project rules", agents)
            self.assertEqual(agents.count(START), 1)

            hooks = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
            commands_by_event: dict[str, list[str]] = {}
            for event, groups in hooks["hooks"].items():
                commands_by_event[event] = [
                    handler["command"]
                    for group in groups
                    for handler in group.get("hooks", [])
                    if isinstance(handler, dict) and "command" in handler
                ]

            self.assertIn("python3 .codex/hooks/existing.py", commands_by_event["PreToolUse"])
            for event in ("PreToolUse", "PostToolUse", "Stop"):
                guard_commands = [
                    value for value in commands_by_event[event] if "test_guard.py" in value
                ]
                self.assertEqual(len(guard_commands), 1, event)

            expected = [
                ".codex/hooks/test_guard.py",
                ".codex/hooks/test_policy.py",
                ".codex/test-policy.json",
                ".codex/agent-check.json",
                "scripts/agent-check",
                "scripts/test-policy",
                "scripts/test-policy-ci",
                "scripts/doctor",
                ".github/workflows/codex-test-policy.yml",
                ".github/CODEOWNERS.tests.example",
            ]
            for relative in expected:
                self.assertTrue((target / relative).exists(), relative)

            self.assertIn(
                ".codex/cache/",
                (target / ".gitignore").read_text(encoding="utf-8").splitlines(),
            )


if __name__ == "__main__":
    unittest.main()
