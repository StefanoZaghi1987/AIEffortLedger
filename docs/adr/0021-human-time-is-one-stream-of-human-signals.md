---
status: accepted
date: 2026-11-19
---

# Human time is one stream of the human signals of a person

No source records attention. The sources record human signals: prompts, queued messages, interruptions, and decisions of
the person. Human time must not grow with parallel sessions (ADR 0001), must not count the night run of an agent, and
must divide among projects so that the parts add up to the human time of the day. Therefore the human signals of all
sessions, agent tools, and machines of a person form one stream, and measured human time is the union of three kinds of
interval: a signal gap between two consecutive human signals not more than the idle gap apart (10 minutes by default); a
response interval from the last agent output or decision request of the main agent, or of a foreground subagent, of a
session to the next human signal of the same session, when not longer than the idle gap (an output of a background
subagent starts no response interval, because the person does not watch it while it runs); and an interval of the
minimum attention time (1 minute by default) that ends at a human signal that ends no other interval. The split rule
gives each instant of human time to the human signal whose interval ends first, and the instant takes the project and
the work item of that signal. A headless prompt is a human signal only when the report parameter headless prompts says
so, because no source shows whether a person or a script typed it; the default is no.

## Considered Options

- **Intervals of each session, summed**: two parallel sessions count the same minutes twice.
- **Duration of each session from its first to its last event**: counts night runs, long tool runs, and breaks.
- **Human time divided among projects in proportion to their agent time**: a person can spend minutes on a project whose
  agent runs for hours; the share is an estimate, not a measurement.
- **Headless prompts as human signals by default**: a script that sends a prompt every few minutes keeps a person
  present all night.

## Consequences

- Measured human time is a lower bound. Reports show it at idle gaps of 5, 10, and 15 minutes, and a timesheet
  confirmation declares the whole day (ADR 0011, ADR 0014).
- The idle gap, the minimum attention time, and headless prompts are report parameters: a change applies to all history
  at the next report (ADR 0002), and every report records the values that it used.
- The attributed parts and the unattributed time of a day add up to its human time, without a separate split for
  projects or work items.
