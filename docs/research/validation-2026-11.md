# Validation of the prototype — November 2026

Point-in-time validation of [prototype/measure.py](../../prototype/measure.py) against [metrics.md](../spec/metrics.md),
on 18 November 2026. Two layers: synthetic scenarios with hand-computed expectations
([prototype/tests](../../prototype/tests)), and checks on a fixed snapshot of the real transcripts of one person
([prototype/validate.py](../../prototype/validate.py)). No manually kept timesheet was available, so the share of a
working day that the sources see is estimated from the presence span instead. Absolute values stay in `prototype/out/`
(ADR 0003). This file is not updated afterwards.

## Scenarios

Thirteen scenarios pass: the example morning (human time, agent time, blocked time, and all four activity classes),
an overnight run woken by a notification, a permission answered by a rule, a permission blocked overnight, a question
to the person, a background subagent, parallel sessions of two projects, a turn across midnight, a stale turn, and
prompts in formats without `origin`.

Two scenarios found errors in the prototype, both fixed before the measurements below:

- after a turn closed for staleness, the next turn was compared with the old last output and discarded;
- a stale turn dropped its pending tool calls, so a permission answered the next morning lost its blocked time and its
  human signal.

On the real data the fixes change agent time by less than 0.5 % and leave the ratios of
[prototype-findings-2026-11.md](prototype-findings-2026-11.md) unchanged within their rounding.

## Real data

| Check | Result |
|---|---|
| Determinism | A second read and a reversed file order give identical results |
| Prompt heuristic for formats without `origin`, on the records that carry `origin` | Precision 100 %, recall 100 % |
| Turns against Claude Code `turn_duration`, on the turns without blocked time | Median coverage 100 %; 93 % of turns covered at least 95 % |
| Minimum attention time 30 s / 60 s / 120 s | Human time 98 % / 100 % / 103 % |
| Stale limit 2 h / 4 h / 8 h | Agent time 100 % / 100 % / 133 % |
| Naive per-line token sum against one count per response | Output 300 %, cache read 253 % |
| Human time inside the daily presence span (first to last human signal) | Median 19.5 % (p10 2.5 %, p90 64.5 %) over the days of the snapshot |
| Days with agent time and no human signal | About 5 % of the days |

## Conclusions

- The prototype applies the definitions of metrics.md: every hand-computed scenario matches, and the results do not
  depend on reading order.
- Turn detection agrees with the turn boundaries that Claude Code records itself, wherever no blocked time
  intervenes; the remaining difference of `turn_duration` is blocked time and gaps between turns, as the definitions
  intend.
- The prompt heuristic for old formats is reliable on every record where it can be checked.
- Minimum attention time hardly matters; the default of 1 minute is safe.
- The stale limit is robust between 2 and 4 hours; at 8 hours, silences of an idle session start to count as agent
  time.
- Counting tokens per transcript line triples output tokens: one `agent_output` per response, as the event schema
  requires, is necessary, not an optimization.
- Measured human time is a narrow lower bound. It covers a median fifth of the span between the first and the last
  human signal of a day. The rest of the span is reading, testing, reviewing, and work outside the agent tools, which
  no transcript sees. A timesheet built only on measured human time would understate the day several times over;
  declared values and an upper bound are needed to frame it.
