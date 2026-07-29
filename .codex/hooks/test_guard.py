#!/usr/bin/env python3
"""Codex PreToolUse guard that blocks raw validation commands.

The guard intentionally allows exactly one validation entry point:
`./scripts/agent-check changed`. Expensive test, lint, typecheck, build,
coverage, E2E, and CI commands must go through that bounded wrapper or be run
by a human/CI process outside the Codex session.

This is a workflow guardrail, not a security boundary.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

VALIDATION_OVERRIDE_ENV = "CODEX_ALLOW_FULL_VALIDATION"
EDIT_OVERRIDE_ENV = "CODEX_ALLOW_GUARDRAIL_EDITS"
ALLOWED_WRAPPER_SUFFIX = "scripts/agent-check"
PROTECTED_PATHS = {
    ".codex/agent-check.json",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/hooks/test_guard.py",
    "scripts/agent-check",
}
PATCH_FILE_HEADER = re.compile(
    r"^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+?)\s*$",
    re.MULTILINE,
)

# Direct executables whose primary purpose is validation.
DIRECT_VALIDATION_RUNNERS = {
    "ava",
    "cargo-nextest",
    "clippy-driver",
    "compileall",
    "cypress",
    "detox",
    "eslint",
    "golangci-lint",
    "jest",
    "junit",
    "mocha",
    "mypy",
    "nextest",
    "nose",
    "nose2",
    "phpunit",
    "playwright",
    "pytest",
    "rspec",
    "ruff",
    "shellcheck",
    "swiftlint",
    "tox",
    "tsc",
    "unittest",
    "vitest",
}

PACKAGE_MANAGERS = {"npm", "pnpm", "yarn", "bun", "npx", "bunx"}
PYTHON_LAUNCHERS = {"python", "python3", "py", "uv", "poetry", "pipenv"}
SHELLS = {"bash", "dash", "fish", "sh", "zsh"}

# Script/task names. Suffixes such as test:unit or lint-fix are matched.
TASK_NAME = re.compile(
    r"^(?:pre|post)?(?:"
    r"test|tests|lint|typecheck|type-check|check|build|verify|validation|"
    r"e2e|integration|coverage|ci|bench|benchmark|format|fmt"
    r")(?:[:_.-].*)?$",
    re.IGNORECASE,
)

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.DOTALL)
SHELL_OPERATOR_CHARS = frozenset(";&|()")


@dataclass(frozen=True)
class Segment:
    argv: tuple[str, ...]
    operator_after: str | None = None


@dataclass(frozen=True)
class Inspection:
    blocked: bool
    reason: str = ""
    is_agent_check: bool = False


def _basename(value: str) -> str:
    name = Path(value).name.lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _is_operator(token: str) -> bool:
    return bool(token) and all(char in SHELL_OPERATOR_CHARS for char in token)


def split_shell(command: str) -> list[Segment]:
    """Split a shell command into simple argv segments and joining operators."""

    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""

    segments: list[Segment] = []
    current: list[str] = []

    for token in lexer:
        if _is_operator(token):
            if current:
                segments.append(Segment(tuple(current), token))
                current = []
            elif segments:
                previous = segments[-1]
                segments[-1] = Segment(previous.argv, (previous.operator_after or "") + token)
        else:
            current.append(token)

    if current:
        segments.append(Segment(tuple(current), None))

    return segments


def _strip_leading_options(argv: list[str]) -> list[str]:
    while argv and argv[0].startswith("-") and argv[0] != "-":
        argv.pop(0)
    if argv and argv[0] == "--":
        argv.pop(0)
    return argv


def normalize_argv(argv: Sequence[str]) -> tuple[list[str], bool]:
    """Remove common launch wrappers while preserving the actual command."""

    items = list(argv)
    backgroundish = False

    while items and ASSIGNMENT.match(items[0]):
        items.pop(0)

    while items:
        executable = _basename(items[0])

        if executable == "env":
            items.pop(0)
            while items and (items[0].startswith("-") or ASSIGNMENT.match(items[0])):
                items.pop(0)
            continue

        if executable in {"command", "builtin", "exec"}:
            items.pop(0)
            items = _strip_leading_options(items)
            continue

        if executable in {"nohup", "setsid"}:
            backgroundish = True
            items.pop(0)
            items = _strip_leading_options(items)
            continue

        if executable == "sudo":
            items.pop(0)
            # Good-enough parsing for common sudo options. The hook is a guardrail,
            # not a shell parser or security boundary.
            while items and items[0].startswith("-"):
                option = items.pop(0)
                if option in {"-u", "-g", "-h", "-p", "-C", "-T", "-R", "-D"} and items:
                    items.pop(0)
            continue

        if executable in {"time", "nice"}:
            items.pop(0)
            items = _strip_leading_options(items)
            continue

        if executable in {"timeout", "gtimeout"}:
            items.pop(0)
            while items and items[0].startswith("-"):
                option = items.pop(0)
                if option in {"-k", "--kill-after", "-s", "--signal"} and items:
                    items.pop(0)
            if items:
                items.pop(0)  # duration
            continue

        break

    return items, backgroundish


def _task_name(value: str) -> bool:
    normalized = value.strip().lower().lstrip("-")
    if "=" in normalized:
        normalized = normalized.split("=", 1)[-1]
    normalized = Path(normalized).name
    return bool(TASK_NAME.match(normalized))


def _contains_validation_runner(values: Iterable[str]) -> bool:
    return any(_basename(value) in DIRECT_VALIDATION_RUNNERS for value in values)


def _is_allowed_wrapper(executable: str) -> bool:
    normalized = executable.replace("\\", "/").lstrip("./")
    return normalized == ALLOWED_WRAPPER_SUFFIX or normalized.endswith("/" + ALLOWED_WRAPPER_SUFFIX)


def _nested_shell_command(argv: Sequence[str]) -> str | None:
    for index, value in enumerate(argv[1:], start=1):
        if value.startswith("-") and "c" in value[1:]:
            return argv[index + 1] if index + 1 < len(argv) else ""
    return None


def inspect_argv(argv: Sequence[str], operator_after: str | None = None) -> Inspection:
    normalized, backgroundish = normalize_argv(argv)
    if not normalized:
        return Inspection(False)

    executable_raw = normalized[0]
    executable = _basename(executable_raw)
    args = normalized[1:]

    if _is_allowed_wrapper(executable_raw):
        is_background = backgroundish or bool(operator_after and "&" in operator_after and "&&" not in operator_after)
        if is_background:
            return Inspection(
                True,
                "The bounded agent-check must run in the foreground; background polling recreates the wait-loop problem.",
                True,
            )
        if args != ["changed"]:
            return Inspection(
                True,
                "Only the exact command './scripts/agent-check changed' is allowed inside Codex.",
                True,
            )
        return Inspection(False, is_agent_check=True)

    if any(_is_allowed_wrapper(value) for value in args):
        return Inspection(
            True,
            "The bounded agent-check must be invoked directly with its fixed arguments.",
            True,
        )

    if executable in SHELLS:
        nested = _nested_shell_command(normalized)
        if nested is None:
            return Inspection(False)
        try:
            nested_segments = split_shell(nested)
        except ValueError:
            return Inspection(True, "Could not safely parse a nested shell command.")
        for segment in nested_segments:
            result = inspect_argv(segment.argv, segment.operator_after)
            if result.blocked:
                return result
        return Inspection(False)

    if executable in DIRECT_VALIDATION_RUNNERS:
        return Inspection(True, f"Direct validation runner '{executable}' is blocked.")

    if executable in PACKAGE_MANAGERS:
        lowered = [value.lower() for value in args]
        if executable in {"npx", "bunx"} and _contains_validation_runner(args):
            return Inspection(True, f"Direct validation through '{executable}' is blocked.")

        # npm/pnpm/yarn/bun test, run test:unit, exec vitest, dlx eslint, etc.
        meaningful = [value for value in lowered if value not in {"run", "run-script", "exec", "dlx", "--"}]
        if any(_task_name(value) for value in meaningful) or _contains_validation_runner(meaningful):
            return Inspection(True, f"Package-manager validation through '{executable}' is blocked.")
        return Inspection(False)

    if executable in PYTHON_LAUNCHERS:
        lowered = [value.lower() for value in args]
        if _contains_validation_runner(lowered):
            return Inspection(True, f"Python validation through '{executable}' is blocked.")
        if "-m" in lowered:
            index = lowered.index("-m")
            if index + 1 < len(lowered) and (
                _basename(lowered[index + 1]) in DIRECT_VALIDATION_RUNNERS
                or _task_name(lowered[index + 1])
            ):
                return Inspection(True, f"Python module validation through '{executable}' is blocked.")
        return Inspection(False)

    if executable == "cargo":
        if any(value.lower() in {"test", "check", "clippy", "build", "bench", "fmt"} for value in args):
            return Inspection(True, "Cargo validation/build commands are blocked.")
        return Inspection(False)

    if executable == "go":
        if any(value.lower() in {"test", "vet", "build"} for value in args):
            return Inspection(True, "Go validation/build commands are blocked.")
        return Inspection(False)

    if executable in {"make", "gmake"}:
        targets = [value for value in args if not value.startswith("-") and "=" not in value]
        if not targets or any(_task_name(value) for value in targets):
            return Inspection(True, "Make validation/default build is blocked.")
        return Inspection(False)

    if executable in {"just", "task", "nx", "turbo", "bazel", "bazelisk", "buck2"}:
        if any(_task_name(value) for value in args) or _contains_validation_runner(args):
            return Inspection(True, f"Validation task through '{executable}' is blocked.")
        return Inspection(False)

    if executable in {"mvn", "mvnw", "gradle", "gradlew", "dotnet", "swift"}:
        if any(_task_name(value) for value in args):
            return Inspection(True, f"Validation/build through '{executable}' is blocked.")
        return Inspection(False)

    return Inspection(False)


def normalize_patch_path(value: str) -> str:
    path = value.strip().strip("\"'").replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path


def protected_patch_paths(command: str) -> list[str]:
    found = {
        path
        for raw in PATCH_FILE_HEADER.findall(command)
        if (path := normalize_patch_path(raw)) in PROTECTED_PATHS
    }
    return sorted(found)


def deny(reason: str, guidance: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{reason} {guidance}",
        }
    }
    print(json.dumps(payload, separators=(",", ":")))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("missing tool_name")
        if tool_name not in {"Bash", "apply_patch"}:
            return 0
        command = payload.get("tool_input", {}).get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("missing tool_input.command")
    except Exception as exc:
        deny(
            f"Guard could not parse the tool request ({exc}).",
            "Review the hook input instead of bypassing it.",
        )
        return 0

    if tool_name == "apply_patch":
        if os.environ.get(EDIT_OVERRIDE_ENV) == "1":
            return 0
        protected = protected_patch_paths(command)
        if protected:
            deny(
                f"Codex may not edit active guardrail files: {', '.join(protected)}.",
                f"For deliberate maintenance, start the Codex parent process with {EDIT_OVERRIDE_ENV}=1.",
            )
        return 0

    if os.environ.get(VALIDATION_OVERRIDE_ENV) == "1":
        return 0

    try:
        segments = split_shell(command)
    except ValueError as exc:
        deny(
            f"Validation guard could not safely parse the shell command ({exc}).",
            "Use ./scripts/agent-check changed instead.",
        )
        return 0

    for segment in segments:
        result = inspect_argv(segment.argv, segment.operator_after)
        if result.blocked:
            deny(
                result.reason,
                f"Use ./scripts/agent-check changed instead. For an intentional full run, "
                f"start Codex with {VALIDATION_OVERRIDE_ENV}=1 or run it outside Codex.",
            )
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
