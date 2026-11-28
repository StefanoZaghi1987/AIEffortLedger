"""The size counters of a call of a tool: the lines that its change adds and removes, the
extension of the file that it names, and the basis of the counters (claude-code-adapter.md
› Size counters; event-schema.md › Keys and invariants; ADR 0016)."""

from typing import Any

from .tables import TOOL_CATEGORIES

EDIT = "edit"
"""The category of the tools whose calls take size counters."""

PATH_KEYS: dict[str, str] = {
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}
"""The key of the input that names the file of each tool of the edit category
(claude-code-adapter.md › Size counters)."""


def count_lines(text: str) -> int:
    """The lines of a text: its line breaks, plus one when the text does not end with a line
    break; an empty text has no lines (event-schema.md › Keys and invariants, gate G4)."""
    if not text:
        return 0
    lines = text.count("\n")
    return lines if text.endswith("\n") else lines + 1


def file_extension(path: str) -> str | None:
    """The part of the file name of a path after its last dot, in lower case; a name without a
    dot, or whose only dot is its first character, has no file extension (event-schema.md ›
    Keys and invariants)."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0:
        return None
    return name[dot + 1:].lower() or None


def size_counters(
    tool_name: str, tool_input: dict, result_record: dict | None, is_error: bool
) -> dict[str, object]:
    """The size counters of one use of a tool: the added and removed lines of the patch that
    its result holds, with the size basis `patch`, or, without a patch, of the texts of its
    input, with the size basis `input`, and the extension of the file that the input names. An
    empty dict for a call that is not of the edit category, that has no result, or whose result
    is an error, because the edit changed no file; a counter that no text of the input gives
    stays absent (claude-code-adapter.md › Size counters; event-schema.md › Keys and
    invariants)."""
    if is_error or result_record is None or TOOL_CATEGORIES.get(tool_name) != EDIT:
        return {}
    counters: dict[str, object] = {}
    path = tool_input.get(PATH_KEYS.get(tool_name, ""))
    if isinstance(path, str):
        extension = file_extension(path)
        if extension is not None:
            counters["file_ext"] = extension
    patch = _patch_counts(result_record)
    if patch is not None:
        counters["lines_added"] = patch[0]
        counters["lines_removed"] = patch[1]
        counters["size_basis"] = "patch"
        return counters
    counters.update(_input_counts(tool_name, tool_input, result_record))
    if any(key in counters for key in ("lines_added", "lines_removed")):
        counters["size_basis"] = "input"
    return counters


def _patch_counts(result_record: dict[str, Any]) -> tuple[int, int] | None:
    """The added and removed lines of the patch of the change that the result of a tool holds,
    or None when it holds no patch: a `structuredPatch` without hunks gives no patch
    (claude-code-adapter.md › Size counters)."""
    patch = result_record.get("structuredPatch")
    if not isinstance(patch, list) or not patch:
        return None
    added = removed = 0
    for hunk in patch:
        if not isinstance(hunk, dict):
            continue
        lines = hunk.get("lines")
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, str):
                continue
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1
    return added, removed


def _input_counts(
    tool_name: str, tool_input: dict[str, Any], result_record: dict[str, Any]
) -> dict[str, object]:
    """The counters that the texts of the input give without a patch, for each tool of the edit
    category: the lines of the new text and of the replaced text; the removed lines of a write
    are absent, or zero when its result says that the file is new, and the removed lines of a
    notebook are always absent (claude-code-adapter.md › Size counters)."""
    counters: dict[str, object] = {}
    if tool_name == "Write":
        added = _lines_of(tool_input.get("content"))
        if added is not None:
            counters["lines_added"] = added
        if result_record.get("type") == "create":
            counters["lines_removed"] = 0
    elif tool_name == "NotebookEdit":
        added = _lines_of(tool_input.get("new_source"))
        if added is not None:
            counters["lines_added"] = added
    else:
        if tool_name == "MultiEdit":
            edits = tool_input.get("edits")
            added = _sum_of(edits, "new_string")
            removed = _sum_of(edits, "old_string")
        else:
            added = _lines_of(tool_input.get("new_string"))
            removed = _lines_of(tool_input.get("old_string"))
        if added is not None:
            counters["lines_added"] = added
        if removed is not None:
            counters["lines_removed"] = removed
    return counters


def _lines_of(text: Any) -> int | None:
    """The lines of the text that the input holds, or None when it holds no text."""
    return count_lines(text) if isinstance(text, str) else None


def _sum_of(edits: Any, key: str) -> int | None:
    """The lines of the text that the items of the edits of a MultiEdit hold under the key, or
    None when no item holds one."""
    if not isinstance(edits, list):
        return None
    counts = [count_lines(item[key]) for item in edits
              if isinstance(item, dict) and isinstance(item.get(key), str)]
    return sum(counts) if counts else None
