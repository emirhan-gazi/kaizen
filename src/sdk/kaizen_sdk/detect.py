"""Prompt source detection via inspect.stack() and AST parsing.

Walks the call stack to find the caller outside the SDK, then parses
the caller's source file with ast to find the variable holding the prompt text.
"""

from __future__ import annotations

import ast
import inspect
import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class PromptSource:
    """Detected prompt source location."""

    file: str
    variable: str | None
    line: int | None
    task_name: str


_SDK_DIR = os.path.dirname(os.path.abspath(__file__))


def detect_prompt_source(prompt_text: str) -> PromptSource:
    """Walk the call stack to find the prompt's source file and variable.

    Returns a PromptSource with file path, variable name (if detected),
    line number, and auto-generated task name.
    """
    frame_info = _find_caller_frame()
    if frame_info is None:
        return PromptSource(
            file="<unknown>",
            variable=None,
            line=None,
            task_name="unknown_prompt",
        )

    filename, lineno, local_vars = frame_info
    variable = _find_variable_for_value(filename, prompt_text, local_vars)
    task_name = _make_task_name(filename, variable)

    return PromptSource(
        file=filename,
        variable=variable,
        line=lineno,
        task_name=task_name,
    )


def _find_caller_frame() -> tuple[str, int, dict] | None:
    """Walk stack frames to find the first frame outside the SDK package."""
    for frame_info in inspect.stack():
        filepath = os.path.abspath(frame_info.filename)
        if not filepath.startswith(_SDK_DIR) and filepath != __file__:
            return (
                frame_info.filename,
                frame_info.lineno,
                frame_info.frame.f_locals,
            )
    return None


@lru_cache(maxsize=128)
def _parse_file_assignments(filepath: str) -> dict[str, str]:
    """Parse a Python file and extract top-level string variable assignments.

    Returns {variable_name: string_value} for simple string assignments.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    assignments: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(
                node.value, ast.Constant
            ):
                if isinstance(node.value.value, str):
                    assignments[target.id] = node.value.value
    return assignments


def _find_variable_for_value(
    filepath: str, prompt_text: str, local_vars: dict
) -> str | None:
    """Find the variable name that holds the given prompt text.

    Strategy:
    1. Check local variables for exact match
    2. Fall back to AST-parsed file assignments for exact match
    """
    for name, value in local_vars.items():
        if isinstance(value, str) and value == prompt_text and not name.startswith("_"):
            return name

    if filepath != "<unknown>" and filepath.endswith(".py"):
        assignments = _parse_file_assignments(filepath)
        for name, value in assignments.items():
            if value == prompt_text:
                return name

    return None


def _make_task_name(filepath: str, variable: str | None) -> str:
    """Generate a task name from file path and variable name.

    Pattern: "filename_variable" e.g. "prompts_summarize_prompt"
    """
    basename = os.path.basename(filepath)
    name_part = (
        os.path.splitext(basename)[0] if basename != "<unknown>" else "unknown"
    )

    if variable:
        task_name = f"{name_part}_{variable}".lower()
    else:
        task_name = f"{name_part}_prompt".lower()

    return "".join(c if c.isalnum() or c == "_" else "_" for c in task_name)
