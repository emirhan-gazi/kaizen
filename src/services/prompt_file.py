"""Prompt file extraction and replacement service.

Supports reading and replacing prompts in source files:
- Python (.py): AST-based extraction, byte-offset replacement (D-01, D-05 to D-09)
- YAML (.yaml/.yml): PyYAML parse/dump with key path traversal (D-02)
- JSON (.json): json parse/dump with dot-path traversal (D-03)
- Plain text (.txt): entire file is the prompt (D-04)
"""

from __future__ import annotations

import ast
import json
import logging
import os

import yaml

logger = logging.getLogger(__name__)

# Format detection from file extension (D-13)
_EXT_FORMAT_MAP = {
    ".py": "python",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".txt": "text",
}


def detect_format(filepath: str) -> str:
    """Auto-detect prompt format from file extension (D-13)."""
    ext = os.path.splitext(filepath)[1].lower()
    fmt = _EXT_FORMAT_MAP.get(ext)
    if fmt is None:
        msg = f"Unsupported file extension: {ext}. Supported: {', '.join(_EXT_FORMAT_MAP)}"
        raise ValueError(msg)
    return fmt


def extract_prompt(content: str, fmt: str, locator: str) -> str:
    """Extract a prompt value from file content (D-11).

    Args:
        content: The file content as a string.
        fmt: File format — "python", "yaml", "json", or "text".
        locator: Format-specific locator:
            - python: variable name (e.g. "SUMMARIZE_PROMPT")
            - yaml: dot-separated key path (e.g. "prompts.summarize")
            - json: dot-separated key path (e.g. "prompts.summarize")
            - text: ignored (entire file is the prompt)

    Returns:
        The extracted prompt string.
    """
    if fmt == "python":
        return _extract_python(content, locator)
    if fmt == "yaml":
        return _extract_yaml(content, locator)
    if fmt == "json":
        return _extract_json(content, locator)
    if fmt == "text":
        return content.strip()
    msg = f"Unsupported format: {fmt}"
    raise ValueError(msg)


def replace_prompt(content: str, fmt: str, locator: str, new_prompt: str) -> str:
    """Replace a prompt value in file content, returning modified content (D-12).

    Args:
        content: The original file content.
        fmt: File format — "python", "yaml", "json", or "text".
        locator: Format-specific locator (same as extract_prompt).
        new_prompt: The new prompt text to insert.

    Returns:
        The modified file content with the prompt replaced.
    """
    if fmt == "python":
        return _replace_python(content, locator, new_prompt)
    if fmt == "yaml":
        return _replace_yaml(content, locator, new_prompt)
    if fmt == "json":
        return _replace_json(content, locator, new_prompt)
    if fmt == "text":
        return new_prompt + "\n"
    msg = f"Unsupported format: {fmt}"
    raise ValueError(msg)


# --- Python AST-based extraction/replacement (D-05 to D-09) ---


def _extract_python(content: str, variable_name: str) -> str:
    """Extract a string variable's value from Python source using AST (D-05, D-06)."""
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == variable_name:
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    return node.value.value
                msg = (
                    f"Variable '{variable_name}' is not a simple string literal. "
                    "Dynamic prompts (f-strings, function calls) are not supported."
                )
                raise ValueError(msg)
    msg = f"Variable '{variable_name}' not found in Python source"
    raise ValueError(msg)


def _replace_python(content: str, variable_name: str, new_prompt: str) -> str:
    """Replace a string variable's value in Python source using byte offsets (D-07).

    Preserves all other code formatting — only the string literal is replaced.
    """
    content_bytes = content.encode("utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == variable_name:
                if not (
                    isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    msg = (
                        f"Variable '{variable_name}' is not a simple string "
                        "literal — cannot replace."
                    )
                    raise ValueError(msg)

                value_node = node.value
                start = value_node.col_offset
                # Find the line start byte offset
                lines = content_bytes.split(b"\n")
                line_start = sum(
                    len(lines[i]) + 1 for i in range(value_node.lineno - 1)
                )
                byte_start = line_start + start

                # Find the end of the string literal by scanning from byte_start
                byte_end = _find_string_end(content_bytes, byte_start)

                # Build replacement string with triple quotes if multiline
                if "\n" in new_prompt:
                    replacement = '"""\n' + new_prompt + '\n"""'
                else:
                    replacement = repr(new_prompt)

                result = (
                    content_bytes[:byte_start]
                    + replacement.encode("utf-8")
                    + content_bytes[byte_end:]
                )
                return result.decode("utf-8")

    msg = f"Variable '{variable_name}' not found in Python source"
    raise ValueError(msg)


def _find_string_end(content_bytes: bytes, start: int) -> int:
    """Find the end byte offset of a Python string literal starting at `start`."""
    text = content_bytes[start:]
    # Detect triple-quoted strings
    for prefix in (b'"""', b"'''", b'r"""', b"r'''", b'b"""', b"b'''"):
        if text.startswith(prefix):
            quote = prefix[-3:]
            end_idx = text.find(quote, len(prefix))
            if end_idx == -1:
                msg = "Unterminated triple-quoted string"
                raise ValueError(msg)
            return start + end_idx + len(quote)

    # Single-quoted strings
    for prefix in (b'"', b"'", b'r"', b"r'", b'b"', b"b'"):
        if text.startswith(prefix):
            quote_char = prefix[-1:]
            i = len(prefix)
            while i < len(text):
                if text[i : i + 1] == b"\\" :
                    i += 2  # skip escaped char
                elif text[i : i + 1] == quote_char:
                    return start + i + 1
                else:
                    i += 1
            msg = "Unterminated string literal"
            raise ValueError(msg)

    msg = f"No string literal found at byte offset {start}"
    raise ValueError(msg)


# --- YAML extraction/replacement (D-02) ---


def _traverse_key_path(data: dict, key_path: str) -> tuple[dict, str]:
    """Traverse a dot-separated key path, returning (parent_dict, final_key)."""
    keys = key_path.split(".")
    current = data
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            msg = f"Key path '{key_path}' not found — missing key '{key}'"
            raise ValueError(msg)
        current = current[key]
    final_key = keys[-1]
    if not isinstance(current, dict) or final_key not in current:
        msg = f"Key path '{key_path}' not found — missing final key '{final_key}'"
        raise ValueError(msg)
    return current, final_key


def _extract_yaml(content: str, key_path: str) -> str:
    """Extract a value from YAML content using dot-separated key path."""
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        msg = "YAML content is not a mapping"
        raise ValueError(msg)
    parent, key = _traverse_key_path(data, key_path)
    value = parent[key]
    if not isinstance(value, str):
        msg = f"Value at '{key_path}' is not a string: {type(value).__name__}"
        raise ValueError(msg)
    return value


def _replace_yaml(content: str, key_path: str, new_prompt: str) -> str:
    """Replace a value in YAML content, preserving structure."""
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        msg = "YAML content is not a mapping"
        raise ValueError(msg)
    parent, key = _traverse_key_path(data, key_path)
    parent[key] = new_prompt
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


# --- JSON extraction/replacement (D-03) ---


def _extract_json(content: str, key_path: str) -> str:
    """Extract a value from JSON content using dot-separated key path."""
    data = json.loads(content)
    if not isinstance(data, dict):
        msg = "JSON content is not an object"
        raise ValueError(msg)
    parent, key = _traverse_key_path(data, key_path)
    value = parent[key]
    if not isinstance(value, str):
        msg = f"Value at '{key_path}' is not a string: {type(value).__name__}"
        raise ValueError(msg)
    return value


def _replace_json(content: str, key_path: str, new_prompt: str) -> str:
    """Replace a value in JSON content, preserving formatting."""
    data = json.loads(content)
    if not isinstance(data, dict):
        msg = "JSON content is not an object"
        raise ValueError(msg)
    parent, key = _traverse_key_path(data, key_path)
    parent[key] = new_prompt
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
