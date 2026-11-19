---
status: accepted
date: 2026-11-18
---

# Size counters prefer the patch of the change and record their basis

ADR 0012 computes size counters from the tool input and accepts that they are approximate. The input is wrong exactly
where size matters: an edit that replaces every occurrence of a text shows one replacement, and a whole-file write
that replaces a file shows only the new text. Claude Code writes in the tool result of its edit tools a patch of the
change, with every added and removed line marked, and other agent tools give a patch as the tool input. Size counters
therefore come from the patch of the change when the source gives one, and from the tool input otherwise; each tool
call records its size basis, `patch` or `input`. A value that the source does not give, such as the removed lines of a
write that replaces a file without a patch, is absent, never zero. A tool call without a result made no change that
the source shows and gets no size counters. This supersedes ADR 0012 where it computes the counters only from the
tool input.

## Considered Options

- **Tool input only** (ADR 0012 as written): wrong for edits of every occurrence and for writes that replace a file.
- **Patch only**: an agent tool that gives no patch would have no size counters.

## Consequences

- A tool call with size counters has `size_basis`; the event schema has this field from its first version.
- Estimates compare counters of the same basis, or treat the input basis as approximate.
- The adapter reads the tool result before it writes the tool call, so it reads all the files of a session together,
  as the event schema already requires.
