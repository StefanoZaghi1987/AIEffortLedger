---
status: accepted
date: 2026-11-18
---

# A subscription fee divides over the usage known to the ledger

ADR 0007 divides the fee of a subscription over all usage of its billing period and reports the unmeasured share
separately. The total usage of a period is known only when an imported cost source gives it; without one, usage outside
the measured agent tools (web chat, machines without ingestion) is unknown. The fee of each billing period therefore
divides over the usage that the ledger knows: the imported total when an imported cost source gives one, otherwise the
sum of measured and declared usage. When an imported total exists, the share that no measured or declared usage
explains is reported as unattributed. When none exists,
the report states that the unmeasured share is unknown and that the allocated cost of each project is an upper bound.

## Considered Options

- **Divide over all usage of the period** (ADR 0007): not computable without an imported total.
- **A declared share of unmeasured usage as the default**: a guess applied to every report; it can come later as a
  declared value that a person sets explicitly.

## Consequences

- List-price cost stays the figure that compares tools, providers, and models (ADR 0007); the allocated fee answers
  what a project cost under the subscription actually paid.
