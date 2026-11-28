# Benchmark — gate G5, 2026-11-27

The run of `tests/benchmark.py` (30 days, 300,000 invented lines, 270,000 events) at the tip
`5072db2` of `feat-phase-1-implementation`, on the owner's laptop, run by hand through the
controller at the owner's ruling (panel, Ruling 176 (11)). Each time is one command through
`cli.main`, timed from its call to its end: in the time are the reading of the two
configurations, the command, and the JSON document that it writes into a stream in memory;
outside every time are the start of the interpreter and the imports, and the writing of the
invented native logs.

| Command | Time | The criterion of product.md › Acceptance criteria (10) |
|---|---|---|
| `ingest --json` (the first ingestion) | 47.739 s | less than 1 minute |
| `report timesheet --from 2026-10-29 --to 2026-11-27 --json` (the daily timesheet of one month) | 20.607 s | less than 30 seconds |
| `timesheet 2026-11-27 --json` (the timesheet of one day) | 1.620 s | less than 5 seconds |
| `report day 2026-11-27 --json` (the report of one day) | 1.646 s | less than 5 seconds |

Processor: Intel64 Family 6 Model 183 Stepping 1, GenuineIntel.

All four times are under their criteria. The month timesheet held 20.707 s before the
quality round's split fix and 20.607 s after it; the ingestion 49.930 s before and 47.739 s
after (both runs on the same processor).
