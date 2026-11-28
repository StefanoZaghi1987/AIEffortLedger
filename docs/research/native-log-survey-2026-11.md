# Native log survey — 2026-11-27

Ratios only, and the three totals of the sample, from `prototype/survey.py` on a copy of the native logs of one
machine (gate G2; the owner allowed the run on 2026-11-27). The output of the survey is
`prototype/out/survey-2026-11-27.md` (not tracked); this note holds what the rulings of the gate rest on. No value of
a free-text field, no personal path.

## The sample

425 transcript files, `cc/` 90.8 % and `desktop/<1-23>/` 9.2 % of them (every `.claude/projects/` folder under the
local agent mode sessions of the desktop application, numbered by sort). 139 571 records; no line of the files fails
to read as JSON. Record types of the newer shapes beside the four of the adapter, each a share of the records:
`api-request-blob` 7.5 %, `atis-latch` 2.5 %, `last-prompt` 2.5 %, `queue-operation` 1.7 %, `session-owner` 1.0 %,
`bridge-session` 1.0 %, `agent-name` 0.30 %, `tools-used` 0.43 %, `file-history-delta` 0.48 %, `cost-state` 0.13 %,
`fork-context-ref` 0.002 %.

## The findings the gate asked for

- **User records and interruptions**: 28 127 user records; 6.1 % of them hold a text, and 0.021 % of them a text that
  starts with the interruption prefix. `toolDenialKind` values, each a share of the user records: `user-rejected`
  0.14 %, `automode-unavailable` 0.10 %, `permission-rule` 0.025 %, `cancelled` 0.018 %, `automode-blocked` 0.007 %,
  `interrupted` 0.004 %. No counter-example of an interruption without its user record in the sample.
- **Delegation tool results**: `Agent` results are 0.31 % of the records: an object for 0.25 % of the records (every
  one holds `agentId`), a text for 0.009 %, no result for 0.053 %; `Task` results none. Tool results with no tool
  call of the same file: 0.002 % of the records.
- **Subagent files**: every subagent file's records name a parent of the same file (no record whose `agentId` is not
  an agent of its file; no distinct foreign agent across all files). No nested subagent in the sample. Parent keys:
  `assistant`/`attachment`/`user` hold `parentUuid` (string; null once per file) and `isSidechain` (boolean); the
  newer files also hold `progress.parentToolUseID` and `progress.parentUuid` (string).
- **Edit tools**: `Edit` inputs are 2.8 % of the records, and the `old_string` and `new_string` keys sit on the same
  2.8 % of them: no Edit input lacks its text keys. `Write` `content` on 0.96 % of the records. `MultiEdit` and
  `NotebookEdit`: no call (no record holds any of their input keys).
- **Origins**: `user.origin` on 0.52 % of the records, every one with `origin.kind` (string). Newer origin key paths
  beside `kind`: `from`, `name`, `body`, `producer`, `runId`, `msg_id`, `fromMode`, `handback`, `handbackReportText`,
  `handbackToolUseId`, `senderTaskId`, `hopChain`, `fullHopChain`, `verifiedLocal` — key names and their JSON types
  alone; the values are data.

## What the sample cannot settle

- A tag text (`<task-notification`, `<local-command-stdout`, `<local-command-caveat`, `<system-reminder`) on a
  `user` record without `origin` in the file of a subagent: the survey counts no tag prefixes; the item keeps its
  trigger `with a real sample`.
- An interruption prefix on a record that also matches a machine-origin row: the survey holds no prefix-by-origin
  table; the item keeps its trigger `with a real sample`.
- Orchestrated sessions: `session-owner` (1.0 % of the records) and `bridge-session` (1.0 %) records are the
  candidate signs; their values are data, and the item keeps its trigger `with a real sample`.

## The rulings this note feeds

Controller Ruling 137 (2026-11-27): the four closures and the kept triggers are in the SDD ledger
(`progress.md`); each closed item is deleted from `claude-code-adapter.md` › To be confirmed, and the link sentence
of the subagent rows carries the text-result rule.
