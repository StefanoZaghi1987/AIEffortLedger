---
status: accepted
date: 2026-11-19
---

# Agent outputs keep request counts and price factors

List-price cost is computed at report time from a price table (ADR 0007), from Phase 2. Native logs disappear after
their retention period, and a value that ingestion does not write is lost for every past session (ADR 0012). The price
of a response of a model depends on more than its token usage: a provider charges some requests one by one, such as web
searches and web fetches, and facts such as the speed mode, the service tier, and the region where the model ran change
the price of each token. Claude Code writes these facts next to the token counts. Therefore an agent output keeps two
open sets next to its token usage: request counts, from a request type to a count, and price factors, from a name to a
value, written when the source gives them. The names are open, as token categories are, so each adapter writes what its
source gives.

## Considered Options

- **Token usage only**: the cost of fast responses and of web searches stays too low for good, and no report can show
  that it is too low.
- **One field for each fact of Claude Code**: a new fact, or another agent tool, needs a new field and a new schema
  version.
- **Store the price of each response**: computed costs are never stored (ADR 0007), and a later price table could not
  apply.

## Consequences

- A price table of Phase 2 gives prices for request types and for price factors; a request type or a price factor that
  the price table does not know makes the cost unknown, never zero.
- The event schema has these fields from its first version.
- The values are short names and counts that the provider writes, never text of the person (ADR 0003).
