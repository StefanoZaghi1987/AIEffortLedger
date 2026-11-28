"""The tables of the `claude_code` adapter: its source, its agent tools, the invocation that
each entrypoint gives, the record types that it knows, and the category of each native tool
name (claude-code-adapter.md › Session fields, › Records and events, › Tool categories)."""

from typing import Any

SOURCE = "claude-code-jsonl"
"""The source of the events that the adapter writes."""

TOOLS: tuple[str, ...] = ("claude-code", "claude-desktop")
"""The agent tools whose native logs the adapter reads."""

DESKTOP = "claude-desktop"
"""The agent tool whose recorded folder is searched for `.claude/projects` folders."""

ENTRYPOINTS: dict[str, str] = {
    "cli": "interactive",
    "local-agent": "interactive",
    "sdk-cli": "headless",
    "sdk-ts": "headless",
    "sdk-py": "headless",
}
"""The invocation that each value of the `entrypoint` of a record gives."""

RECORD_TYPES: frozenset[str] = frozenset({
    "assistant", "user", "queue-operation",
    "system", "attachment", "api-request", "api-request-shape", "api-request-blob",
    "permission-mode", "mode", "atis-latch", "file-history-snapshot", "file-history-delta",
    "tools-used", "cost-state", "agent-name", "session-owner", "bridge-session", "pr-link",
    "ai-title", "custom-title", "last-prompt",
})
"""Every record type that the table of records and the list without an event name."""


TOOL_CATEGORIES: dict[str, str] = {
    "Edit": "edit",
    "Write": "edit",
    "MultiEdit": "edit",
    "NotebookEdit": "edit",
    "Bash": "execute",
    "PowerShell": "execute",
    "Read": "read",
    "Grep": "search",
    "Glob": "search",
    "WebFetch": "web",
    "WebSearch": "web",
    "Agent": "delegate",
    "Task": "delegate",
    "SendMessage": "delegate",
    "SubagentHandback": "delegate",
    "ListAgents": "delegate",
    "AskUserQuestion": "decide",
    "ExitPlanMode": "decide",
    "ToolSearch": "other",
    "Skill": "other",
    "TodoWrite": "other",
    "TaskCreate": "other",
    "TaskUpdate": "other",
    "TaskStop": "other",
    "Monitor": "other",
    "ListMcpResourcesTool": "other",
}
"""The category of each native tool name of the table; a name outside it is `other`
(claude-code-adapter.md › Tool categories)."""


def invocation_of(record: dict[str, Any]) -> tuple[str, dict | None]:
    """The invocation of a record, and the warning for an entrypoint value that no invocation
    gives; a record without `entrypoint` is of unknown invocation without a warning
    (claude-code-adapter.md › Session fields)."""
    entrypoint = record.get("entrypoint")
    if entrypoint is None:
        return "unknown", None
    known = ENTRYPOINTS.get(entrypoint) if isinstance(entrypoint, str) else None
    if known is not None:
        return known, None
    return "unknown", {"code": "unknown_entrypoint", "values": {"value": entrypoint}}
