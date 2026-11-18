---
status: accepted
date: 2026-11-18
---

# Tool calls keep the tool name, the tool category, and size counters

Native logs disappear after the retention period of their agent tool, and the store keeps only what adapters write. A
value that ingestion drops today is lost for every past session. Estimates need effort in relation to size, and a
profile of the work (editing, running, reading, searching) needs the kind of each tool call. Each `tool_call` event
therefore keeps the native tool name and a tool category that is the same for every agent tool; a call of category
edit also keeps size counters: lines added, lines removed, and the file extension. The adapter computes the counters
from the tool input while it reads it and then drops the text (ADR 0003).

## Considered Options

- **Tool name and category only, size from the repositories at report time**: repository statistics do not separate
  the changes of agents from those of the person and do not see work that was abandoned or never committed. They stay
  useful as a second source of size.
- **No change until the estimation phase**: the data of every session older than the retention period is lost.
- **File paths of edited files**: paths reveal names and structure of the work and add little to the extension.

## Consequences

- The counters are approximate: an edit replaces text, so lines removed are the lines of the replaced text and lines
  added are the lines of the new text, not a diff.
- Each adapter maps its native tool names to tool categories; an unknown tool name gets the category other and a
  warning.
- The event schema changes version.
