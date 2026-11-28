# The cost of the models — research of November 2026

Point-in-time research into the public facts a cost meter needs: the token categories each provider's API
response reports, the public price lists, what a Claude Code transcript carries when the model is served by
another provider, and the billing exports a person can download. Facts are the state of the pages on
2026-11-26, the day they were read, and change with provider releases; this file is not updated. Public
pages only, primary sources first: the API reference of Anthropic (`platform.claude.com/docs`), the public
price pages of Anthropic and of Zhipu AI / Z.ai (`docs.z.ai`, `docs.bigmodel.cn`), and the Claude Code
documentation (`code.claude.com/docs`). Nothing here is measured on the owner's data.

## Summary

1. The Anthropic `usage` object holds token counts and tier fields only — `input_tokens`, `output_tokens`,
   `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_creation` (5m/1h breakdown),
   `output_tokens_details.thinking_tokens`, `server_tool_use`, `service_tier`, `speed`, `inference_geo` — and
   no response field carries a monetary cost.
2. Anthropic prices every category per million tokens in USD, with published multipliers for cache writes and
   reads, batch (50 % off), fast mode, US data residency (1.1x), and prompt-length tiers on Haiku; the pricing
   page dates individual changes in footnotes but carries no general revision date.
3. Zhipu AI / Z.ai documents an OpenAI-shaped `usage` (`prompt_tokens`, `completion_tokens`,
   `prompt_tokens_details.cached_tokens`, `total_tokens`, no monetary cost), an Anthropic-compatible endpoint
   at `https://api.z.ai/api/anthropic`, and prices in USD per million tokens on `docs.z.ai` and in CNY per
   million tokens on `docs.bigmodel.cn`.
4. Claude Code documentation names the model string a session uses (set through `ANTHROPIC_MODEL`, the
   `ANTHROPIC_DEFAULT_*_MODEL` variables, `modelOverrides`, or a custom model option) and the `modelUsage`
   field of the headless result message; it documents no provider field and no transcript schema, and
   `ANTHROPIC_BASE_URL` is documented as changing where requests are sent, not which model answers them.
5. Anthropic offers a Console cost page, a daily per-user spend report CSV on subscription plans, and admin
   analytics APIs that return cost amounts in USD with token-category breakdowns; Zhipu / Z.ai public
   developer documentation documents no usage export or bill download.
6. Neither provider exposes its list prices in a machine-readable stable form — Anthropic's Models API
   carries no price field and both providers publish prices only as HTML pages — so a ledger keeps its own
   transcribed, dated price table.

## 1. The Anthropic Messages API `usage` object

The response schema of `POST /v1/messages` documents `usage` as "Billing and rate-limit usage. Anthropic's API
bills and rate-limits by token counts, as tokens represent the underlying cost to our systems."
([Messages API reference](https://platform.claude.com/docs/en/api/messages), read 2026-11-26). The documented
keys:

- `input_tokens` — "The number of input tokens which were used."
- `output_tokens` — "The number of output tokens which were used."
- `cache_creation_input_tokens` (number or null) — "The number of input tokens used to create the cache entry."
- `cache_read_input_tokens` (number or null) — "The number of input tokens read from the cache."
- `cache_creation` (object or null) — "Breakdown of cached tokens by TTL", with `ephemeral_5m_input_tokens`
  and `ephemeral_1h_input_tokens`.
- `output_tokens_details` (object or null) — "Breakdown of output tokens by category. `output_tokens` remains
  the inclusive, authoritative total used for billing." Its only documented key is `thinking_tokens`, the raw
  internal-reasoning tokens, which is always ≤ `output_tokens`.
- `server_tool_use` (object or null) — "The number of server tool requests", with `web_search_requests` and
  `web_fetch_requests`. The pricing page's code-execution example shows a further key, `code_execution_requests`
  ([pricing](https://platform.claude.com/docs/en/about-claude/pricing)), which the `ServerToolUsage` schema on
  the Messages reference page does not list; the reference is the stricter of the two and the divergence is
  reported, not resolved.
- `service_tier` — "If the request used the priority, standard, or batch tier" (`"standard"` | `"priority"` |
  `"batch"` | null).
- `speed` — "The inference speed mode used for this request" (`"standard"` | `"fast"` | null).
- `inference_geo` — "The geographic region where inference was performed for this request."

The documented total is: "Total input tokens in a request is the summation of `input_tokens`,
`cache_creation_input_tokens`, and `cache_read_input_tokens`."

No field of the response schema carries a monetary cost: the reference defines token counts, request counts,
tier/speed enums, and geography only. Cost comes from tokens times published prices, computed by the client.
Claude Code does exactly that: it "computes the dollar figure locally from token counts at list price, unless
a `modelPricing` table is in effect"
([Claude Code costs](https://code.claude.com/docs/en/costs), read 2026-11-26).

A separate `usage` object page does not exist at `https://platform.claude.com/docs/en/api/usage` (HTTP 404,
read 2026-11-26); the schema lives inline in the Messages reference.

## 2. Anthropic public pricing

The pricing documentation page states "All prices are in USD" and "All payments are in USD", and prices every
category per million tokens (MTok) ([pricing](https://platform.claude.com/docs/en/about-claude/pricing), read
2026-11-26). The model table gives five categories per model — base input tokens, 5m cache writes, 1h cache
writes, cache hits and refreshes, output tokens. Representative rows:

| Model | Base input | 5m cache write | 1h cache write | Cache hit | Output |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Claude Fable 5.2 | $8 | $10 | $16 | $0.20 | $40 |
| Claude Opus 5.5 | $4 | $5 | $8 | $0.20 | $20 |
| Claude Sonnet 5.5 | $2 | $2.50 | $4 | $0.10 | $10 |
| Claude Haiku 5.5 (prompt ≤ 100k) | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 |
| Claude Haiku 5.5 (prompt > 100k) | $0.50 | $0.625 | $1 | $0.05 | $2.50 |

Cache multipliers are published relative to base input: 5-minute write 1.25x, 1-hour write 2x, read 0.1x on
most models, with lower read multipliers on named models (0.025x on Fable 5.2 / Mythos 5.2 and Fable 5.1 /
Mythos 5.1, 0.05x on Opus 5.5 and Sonnet 5.5). Multipliers "stack with other pricing modifiers".

Price factors in public pricing:

- **Batch**: the Batch API runs at a 50 percent discount on input and output, with its own table per model.
- **Speed**: fast mode, up to 2.5x output tokens per second at premium pricing (Fable 5.2 and Mythos 5.2
  $16/$80, Opus 5.5 $8/$40, Opus 5 and Opus 4.8 $10/$50 per MTok, input/output).
- **Data residency**: `inference_geo: "us"` applies a 1.1x multiplier on every token category for Claude 4.6
  and later.
- **Long context**: a 1M-token request on Claude 4.6 and later (except Haiku 5.5) bills at standard per-token
  prices; Haiku 5.5 prices by prompt length with the 100,000-token threshold, counting cache reads and writes
  in the prompt length.
- **Partner platforms**: Amazon Bedrock and Google Cloud (Google managed) set independent prices; regional and
  multi-region endpoints on those platforms carry a 10 percent premium over global. Marketplace billing
  (Claude Platform on AWS, Claude in Microsoft Foundry) converts token usage rated in USD into Claude
  Consumption Units at $0.01 per CCU.
- **Managed Agents**: token categories at model rates plus session runtime at $0.08 per session-hour.

Dating: the page has no revision line. One change is dated in a footnote — the $2/$10 Sonnet 5 prices
"announced at launch as introductory pricing through August 31, 2026", with the "previously scheduled increase
… on September 1, 2026" cancelled. Retired models are marked, not dated. The consumer page
([claude.com/pricing](https://claude.com/pricing), read 2026-11-26) lists subscription plans (Pro $17/month
annual or $20 monthly, Max $100, Ultra $200, Team $20 or $25 per seat, Enterprise) and carries no dates either,
only "Price and plans are subject to change at Anthropic's discretion."

## 3. Zhipu AI (Z.ai) GLM API

**Usage keys.** The chat-completion reference documents the response `usage` as "Token usage statistics
returned when the model call ends" ([chat completion](https://docs.z.ai/api-reference/llm/chat-completion),
read 2026-11-26), with these keys, following the OpenAI-compatible naming:

- `prompt_tokens` — "Number of tokens in user input"
- `completion_tokens` — "Number of output tokens"
- `total_tokens` — "Total number of tokens"
- `prompt_tokens_details.cached_tokens` — "Number of tokens served from cache"

A `completion_tokens_details` object is not in the documented schema, so no reasoning-token category exists on
the Z.ai side. No field carries a monetary cost. The pages fetched document this object for the
OpenAI-compatible endpoint; the Anthropic-compatible endpoint pages document configuration, not a usage
schema, so what `usage` looks like through `https://api.z.ai/api/anthropic` is not documented in the pages
read — a finding.

**Endpoint and keys.** The coding-plan pages give the base URLs
([tool integration](https://docs.z.ai/devpack/tool/others.md) and
   [API key management](https://docs.z.ai/devpack/notice/api-key-management.md), both read 2026-11-26):
`https://api.z.ai/api/anthropic` (Anthropic Messages), `https://api.z.ai/api/coding/paas/v4` (OpenAI Chat
Completions, coding endpoint), `https://api.z.ai/api/v1` (OpenAI Responses), `https://api.z.ai/api/paas/v4`
(standard API). Since 2026-10-16 the key type — standard API key, personal coding-plan key, team-plan key, or
legacy compatible key — decides the billing, and "changing the endpoint does not change a key's billing type";
the page warns that a wrong endpoint "will result in inability to use GLM Coding Plan subscription quota".

**Prices.** The international pricing page states "All prices are in USD", per million tokens
([Z.ai pricing](https://docs.z.ai/guides/overview/pricing), read 2026-11-26): GLM-5.3 $1.4 input / $0.26 cached
input / $4.4 output; GLM-5.2 and GLM-5.1 at the same rates; GLM-5 $1 / $0.2 / $3.2; GLM-4.7 and GLM-4.6
$0.6 / $0.11 / $2.2; GLM-5.3-Flash $0.15 / $0.03 / $0.50; GLM-4.7-Flash free. Cached-input storage is marked
"Limited-time Free" per model. The domestic platform prices in CNY, per million tokens
([BigModel pricing](https://docs.bigmodel.cn/cn/guide/start/pricing), read 2026-11-26), with the billing
formula 调用费用 = 未命中缓存的输入费用 + 缓存命中费用 + 输出费用 + 缓存存储费用 (uncached input + cache hit +
output + cache storage): GLM-5.3 8 input / 28 output / 2 cache hit; GLM-5.2 the same; GLM-5 and GLM-5.1 tiered
below and above 32k input; batch runs at 5 折 (50 percent off); several Flash models are free. The page shows
no last-updated marker; neither pricing page dates its changes. The console page
`https://open.bigmodel.cn/pricing` renders no content without JavaScript (observed 2026-11-26).

## 4. Model identifiers through Claude Code

The model configuration page ([Claude Code model configuration](https://code.claude.com/docs/en/model-config),
read 2026-11-26) names the fields that determine the model string a session runs on:

- Resolution order: `/model` in session, `claude --model`, `ANTHROPIC_MODEL`, the settings `model` field, and
  `ANTHROPIC_DEFAULT_MODEL` for new sessions.
- Alias variables: `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`,
  `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_FABLE_MODEL` — each "must be a full model name, or the
  equivalent identifier for your API provider". `ANTHROPIC_SMALL_FAST_MODEL` is "deprecated in favor of
  `ANTHROPIC_DEFAULT_HAIKU_MODEL`". `CLAUDE_CODE_SUBAGENT_MODEL` sets the subagent default.
- Custom identifiers: `ANTHROPIC_CUSTOM_MODEL_OPTION` (plus `_NAME` and `_DESCRIPTION`) adds a picker entry,
  and "Claude Code skips validation for the model ID set in `ANTHROPIC_CUSTOM_MODEL_OPTION`, so you can use any
  string your API endpoint accepts". The `modelOverrides` setting maps Anthropic model IDs to provider strings
  (Bedrock inference-profile ARNs, Foundry deployment names); the `[1m]` suffix selects the 1M window and
  Claude Code "strips the suffix before sending the model ID to your provider".
- Provider routing: `ANTHROPIC_BASE_URL` "changes where requests are sent, not which model answers them".
- Fallback: the settings field `fallbackModel` takes up to three models and `--fallback-model` overrides it;
  on third-party providers the automatic model fallback resolves against `ANTHROPIC_DEFAULT_FABLE_MODEL`,
  `ANTHROPIC_DEFAULT_OPUS_MODEL`, and `ANTHROPIC_DEFAULT_SONNET_MODEL`, and a missing Opus falls back to the
  default Sonnet.

Zhipu's own Claude Code page exercises these fields with GLM strings
([Z.ai Claude Code](https://docs.z.ai/devpack/tool/claude), read 2026-11-26): `ANTHROPIC_AUTH_TOKEN` set to the
Z.ai key, `ANTHROPIC_BASE_URL` set to `https://api.z.ai/api/anthropic`, `ANTHROPIC_DEFAULT_OPUS_MODEL` and
`ANTHROPIC_DEFAULT_SONNET_MODEL` set to `glm-5.4[1m]`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` to `glm-5.3-flash[1m]`,
with further settings the page recommends (`API_TIMEOUT_MS`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW`,
`CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY`).
The model string a GLM session uses is therefore the provider string the user configured, recorded and shown
by Claude Code in that form.

What the transcript records: the documentation names the `modelUsage` field of the headless result message —
"read the actual model from the `modelUsage` field of the result message" — and the `/usage` Session block's
"Usage by model" lines list per-model token totals under model IDs. The documentation does not describe the
schema of the local session transcript file and names no provider field in it; the only provider-related
statement is the routing-only role of `ANTHROPIC_BASE_URL`. That the transcript stores the configured model
string and a request ID, but no provider field, is the finding for the provider-hint question.

## 5. Billing exports

- **Anthropic, API (Console)**: the Console Cost page (`platform.claude.com/cost`) and workspace usage and
  cost reporting; the Claude Code Analytics API returns daily per-user metrics with an Admin API key
  ([Claude Code costs](https://code.claude.com/docs/en/costs)).
- **Anthropic, subscription**: Teams and Enterprise org analytics expose a spend report CSV, updated daily,
  listing token usage and estimated spend per user and per model; Enterprise additionally exposes the
  Enterprise Analytics API through a `read:analytics` key created in claude.ai
  ([Claude Code costs](https://code.claude.com/docs/en/costs)).
- **Anthropic, admin analytics API**: the beta organization analytics endpoints return bucketed cost rows whose
  fields include `amount` ("post-discount, pre-credit", in fractional cents), `list_amount`, `currency`
  ("Currently always `\"USD\"`"), `cost_type` (`tokens`, `web_search`, `code_execution`), and `token_type`
  (`uncached_input_tokens`, `cache_creation.ephemeral_5m_input_tokens`, `cache_creation.ephemeral_1h_input_tokens`,
  `cache_read_input_tokens`, `output_tokens`)
  ([analytics API](https://platform.claude.com/docs/en/api/admin/analytics), read 2026-11-26).
- **Zhipu AI / Z.ai**: the public developer documentation documents no usage export, bill download, or
  usage-report API; the API-key page speaks of checking a key's classification in the console and nothing of
  statements ([API key management](https://docs.z.ai/devpack/notice/api-key-management.md), read 2026-11-26).
  A person's downloadable export on this side is, as far as the public pages say, nothing — a finding.

## 6. Machine-readable list prices

No stable machine-readable form of the list prices exists at either provider; that is the finding.

- **Anthropic**: the Models API, `GET /v1/models`
  ([List Models](https://platform.claude.com/docs/en/api/models/list), read 2026-11-26), is the only
  machine-readable model-metadata endpoint, and its documented `ModelInfo` fields — `id`, `display_name`,
  `created_at`, `deprecated_at`, `retires_at`, `lifecycle`, `line`, `max_input_tokens`, `max_tokens`,
  `capabilities`, `type` — include no pricing, rate, or cost field. The price lists themselves are HTML pages
  ([pricing docs](https://platform.claude.com/docs/en/about-claude/pricing),
  [claude.com/pricing](https://claude.com/pricing), both read 2026-11-26) with no documented JSON endpoint or
  downloadable price file. The nearest machine-readable money figures are the beta admin analytics reports,
  whose `amount` and `list_amount` fields carry billed and list-price values per usage row
  ([analytics API](https://platform.claude.com/docs/en/api/admin/analytics), read 2026-11-26) — actual
  billing data, not a published rate card.
- **Zhipu AI / Z.ai**: the API-reference index
  ([llms.txt](https://docs.z.ai/llms.txt), read 2026-11-26) lists no models-list endpoint and no price-query
  endpoint; the only JSON endpoint is the site's own `/openapi.json` specification, which describes the API
  surface, not prices. Prices exist only as HTML docs pages
  ([Z.ai pricing, USD](https://docs.z.ai/guides/overview/pricing),
  [BigModel pricing, CNY](https://docs.bigmodel.cn/cn/guide/start/pricing), both read 2026-11-26), with no
  documented data endpoint or file.

Consequence: a ledger that wants list prices must keep a transcribed, dated price table of its own, read by
hand from those HTML pages; no provider offers a feed to subscribe to.

## What this settles in the specification

Facts from the sections above, against the open point "Cost details" of
[docs/spec/metrics.md](../spec/metrics.md) › To be confirmed:

- **Basis that divides a subscription (tokens or list-price cost)**: no provider response carries a monetary
  cost (section 1, section 3); Claude Code's own cost figure is computed locally at list price unless the
  `modelPricing` managed setting overrides the rates (section 1). A subscription can only be divided by
  tokens or by a list-price valuation computed the same way.
- **Token categories of other providers**: Anthropic names input, output, 5m and 1h cache writes, cache reads,
  thinking tokens, and server-tool requests (section 1); Zhipu names prompt, completion, total, and cached
  tokens, with no reasoning category (section 3). A cross-provider token category map must be provider-shaped,
  not one canonical list.
- **Prices of request types and price factors**: published factors are service tier (`service_tier`), batch,
  speed (`speed`), inference geography, prompt length, and partner-platform billing units (section 2);
  Zhipu publishes an equivalent batch factor and prompt-length tiers in CNY (section 3).
- **Which cost source paid each agent output**: on Zhipu, the key type decides the billing, not the endpoint
  (section 3); on Anthropic, subscription usage draws from seat allowances and API usage from the Console
  workspace (section 5). The cost source is knowable from the credential kind, which the transcript does not
  document as recorded.
- **Provider resolution from the provider hint**: `ANTHROPIC_BASE_URL` is documented as routing-only and the
  transcript schema names no provider field (section 4); the model string alone (for example `glm-5.4[1m]`)
  must carry the hint.
- **Costs in different currencies**: Anthropic prices only in USD (section 2); Zhipu prices in USD on the
  international platform and in CNY on the domestic one, with different published numbers per currency
  (section 3), so combined reports need a dated exchange-rate table or a per-source currency field.
- **Billing periods that differ from report periods**: the Anthropic exports are daily or bucketed reports
  with monthly invoices (section 5); Zhipu documents none, which leaves its billing period unspecified in
  public facts.
