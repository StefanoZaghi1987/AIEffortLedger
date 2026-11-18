---
status: accepted
date: 2026-11-18
---

# Human time, agent time, and calendar time are separate quantities

Effort is reported as human time, agent time, calendar time, token usage, and cost, and these quantities are never
added together or converted into each other. A single "hours" figure that grows with every event counts an agent's
night run as human time and multiplies it by the hourly rate of the person. Human time across parallel sessions is a
union (a person attends one thing at a time), and agent time across parallel agents is a sum (like CPU time). An
agent that waits for a decision of a person is neither working nor attended: its blocked time is a quantity of its
own. Every instant falls in exactly one activity class (person only, supervised, unattended, blocked, idle), so every
working pattern in the domain needs no special case: parallel or sequential work, night and weekend runs,
long-running tasks, and deferred review.

## Considered Options

- **One "hours" quantity from event gaps**: simple, but mixes human and agent time and double counts parallel
  sessions per project.
- **Agent time converted into "human-equivalent" hours**: rejected; the conversion factor is an estimate, not a
  measurement. A human-equivalent figure, where needed, is a declared value with its own source.
- **Blocked time counted as agent time** (as the wall span of a turn that Claude Code reports): rejected; an agent
  blocked overnight on a permission request would count as hours of work. Measured on real logs, blocked time was
  equal to 24 % of agent time.

## Consequences

- Person cost is human time × hourly rate only; agent time contributes through list-price cost and actual cost.
- Reports show at least two time columns. A reader who expects one total must learn the distinction from the glossary.
