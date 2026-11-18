---
status: accepted
date: 2026-11-18
---

# Every report shows list-price cost; actual cost comes from typed cost sources

List-price cost (token usage × the dated price table for that provider and model) is always computed, because it is
the only cost comparable across tools, providers, models, and payment types. Actual cost comes from a cost source of
type `subscription` (a fixed fee divided over the usage of its billing period), `metered` (usage × the price actually
paid, or a provider billing API), or `imported` (a provider export such as a team spend report or an analytics API).
Costs are never stored in events; they are computed at report time. Models resolve to prices through an explicit
table keyed by provider and model identifier, never by matching part of a model name.

## Considered Options

- **Flat subscription divided over the measured projects only**: rejected; usage outside the measured tools (web chat,
  other projects) also consumes the subscription, so the division covers all usage of the period and reports the
  unmeasured share separately.

## Consequences

- A model served through a compatible endpoint of another provider gets the price of that provider, not of the model
  family its name resembles.
