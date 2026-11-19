# Prototype findings — November 2026

Point-in-time measurements by [prototype/measure.py](../../prototype/measure.py) on the Claude Code and Claude Desktop
(Cowork) transcripts of one person on 18 November 2026, Claude Code 2.1.x. The prototype applies the definitions of
[metrics.md](../spec/metrics.md), reads transcripts only, and copies no text. Absolute hours and folder names stay in
`prototype/out/`, which git ignores (ADR 0003); this file gives ratios. It is not updated afterwards.

## Sources

- Claude Desktop Cowork sessions use the same transcript format as Claude Code, with entry point `local-agent`, under
  `%APPDATA%\Claude\local-agent-mode-sessions\…\.claude\projects\`. Their working folder is a path inside a virtual
  machine (`/sessions/<name>`), and they are kept beyond the 30 days of Claude Code, so one adapter covers both.
- Human prompts are explicit in recent versions: user records carry `origin.kind` = `human`, `task-notification`,
  `coordinator`, or `peer`. Of all user records, about 90 % are tool results and only a few percent are human prompts.
- Permission decisions carry their source: `config` (an allow rule, no person involved) or `user_temporary`,
  `user_permanent`, `user_reject` (a person). Questions to the person and plan approvals are tool calls whose results
  are decisions of the person.
- Messages typed while an agent works appear as `queue-operation` / `enqueue`.
- `system` / `turn_duration` records give the wall span of a turn, from the prompt to its end (median difference from
  "record time minus prompt time": 6 ms).
- `system` / `away_summary` records mark that the tool detected the absence of the person.
- At least 15 record types are present; the adapter must ignore unknown types and warn about unknown structure.
- Retention works as configured: between two runs on the same day, the transcripts of the 30th day back disappeared
  (about 2 % of the files).

## Human signals

Prompts are 47 % of human signals, decisions of the person 39 %, queued messages 14 %. Counting prompts only would
miss more than half of the evidence of presence.

## Human time and the idle gap

| Idle gap | Signal gaps only | Response intervals only | Both (definition of metrics.md) |
|---|---|---|---|
| 5 min | 0.52 | 0.47 | 0.61 |
| 10 min | 0.89 | 0.63 | 1.00 |
| 15 min | 1.15 | 0.71 | 1.25 |
| 30 min | 1.69 | 0.92 | 1.73 |

Values relative to the definition of metrics.md at the default idle gap of 10 minutes.

The gaps between consecutive human signals show no natural break: 65 % are under 5 minutes, 78 % under 10, 86 % under
20, and the rest spread out to several hours. The response time after an agent output behaves the same way (86 %
under 10 minutes). The idle gap is therefore a convention, and the sensitivity of human time to it is large: from 5 to
15 minutes, human time doubles.

## Agent time and blocked time

- Subagents produce 47 % of agent time; the sum over agents is 1.44 times the union, so agents often run in parallel.
- Blocked time equals 24 % of agent time. Single decision requests stay open for hours while the person is away.
- Waiting for own foreground subagents is 1 % of agent time.
- `turn_duration` is a wall span that includes blocked time and the gaps between turns: on the same sessions it is
  66 % higher than the turns of the prototype. It is not agent time.

## Activity classes (idle gap 10 minutes)

| Person only | Supervised | Unattended | Blocked |
|---|---|---|---|
| 20.0 % | 23.6 % | 42.6 % | 13.8 % |

Shares of the union of human time, agent time, and blocked time; the four classes add up to that union.

## Parallel work across projects

Human time of sessions of different projects overlaps for 3 % of human time. For this person the split rule changes
little; team data can differ.

## Project identity

Of the log folders, 12 % resolve to a repository through a git remote, read from the repository files without running
git. The others are Cowork virtual-machine paths (59 %), folders without git (24 %), or folders deleted since (6 %).
Identity rules and the repository hint recorded at ingestion are the normal case, not the exception.

## Duplicates

No response appears in more than one session: the transcripts contain no forked sessions, so the fork rule of
[event-schema.md](../spec/event-schema.md) is not tested by this data.

## Tokens and models

Three models appear, two of them from a non-Anthropic provider served through Claude Code. Cache reads are about 30
times all other token categories together, so list-price cost depends strongly on the cache prices.

## Limits

- One person, mainly the last 30 days of Claude Code plus older Cowork sessions; no Codex data on this machine.
- Human prompts in versions without `origin` rely on a heuristic on message tags.
- Interruptions are not detected.
- The prototype groups all folders without a repository identity together; the daily table is not yet a timesheet.
- Measured human time is a small part of a working day. It is a lower bound by design; the comparison with a manually
  kept timesheet is still to do.
