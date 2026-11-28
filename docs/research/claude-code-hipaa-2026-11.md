# The HIPAA configuration of Claude Code and the retention of Claude Desktop native logs (2026-11)

Point-in-time note. It records what the documentation and the support articles of Anthropic say of the HIPAA
configuration of Claude Code, which [claude-code-adapter.md](../spec/claude-code-adapter.md) › Retention relies on:
how Claude Code learns that it applies, what it leaves on a computer, and what `cleanupPeriodDays` deletes under it.
Sources, read 2026-11-25, in the table at the end. The note quotes; it decides nothing. It changes no sentence of
[claude-code-settings-2026-11.md](claude-code-settings-2026-11.md), whose facts on the cleanup keys and on the managed
sources its quotes confirm.

## Method

One web search restricted to Anthropic domains (`code.claude.com`, `docs.claude.com`, `docs.anthropic.com`,
`anthropic.com`, `claude.com`, `support.claude.com`, `support.anthropic.com`), with the query "Claude Code HIPAA
configuration cleanupPeriodDays desktopSessionCleanupPeriodDays": it returned the Anthropic pages below and
third-party pages, which were not read. The Anthropic pages below were then read in full (the settings reference in
five consecutive chunks covering its whole 462,469 characters; the monitoring page in two chunks covering its whole
183,752 characters), and the changelog `CHANGELOG.md` of the `anthropics/claude-code` repository in five chunks
covering versions 2.1.332 down to 2.1.267, 2.1.252 down to 2.1.229, and 2.1.204 down to 2.1.147 (partly), see
section 3.

## 1. What the HIPAA configuration is, and who has it

An organization setting of Claude Enterprise plans, applied by the organization's Primary Owner, for organizations
under a Business Associate Agreement with Anthropic.

> The HIPAA configuration is an organization setting on Claude Enterprise plans, for organizations that handle
> protected health information (PHI) and have a Business Associate Agreement (BAA) with Anthropic. It applies to
> Claude Code (local mode) and Cowork (local mode), and it restricts features in both products.

(Set up Claude Code (local mode) for a HIPAA-ready organization — https://code.claude.com/docs/en/hipaa-setup.md,
read 2026-11-25, page top. "(local mode)" the same page defines as a local session: Claude Code in the terminal,
Claude Code in the Code tab of Claude Desktop, Cowork in Claude Desktop; the VS Code and JetBrains extensions "aren't
part of (local mode) ... your BAA doesn't cover them".)

The support article for the Primary Owner says the same and adds who applies it:

> The HIPAA configuration is an organization setting on Enterprise plans.

> Only the Primary Owner can apply the HIPAA configuration.

> Available on Enterprise plans with an Anthropic account team.

> The button is grayed out until Anthropic turns it on for your organization.

(Use Claude Code (local mode) and Cowork (local mode) on a HIPAA-ready Enterprise plan —
https://support.claude.com/en/articles/17318731, read 2026-11-25.) The BAA support article states the BAA side:

> The HIPAA configuration is an organization setting that brings Claude Code (local mode) and Cowork (local mode)
> under your Business Associate Agreement (BAA) with Anthropic.

> Standard Claude Enterprise plans do not include BAA coverage without action from a Primary Owner.

(Business Associate Agreements (BAA) for Commercial Customers —
https://support.claude.com/en/articles/8114513-business-associate-agreements-baa-for-commercial-customers, read
2026-11-25.)

It is not a plan alone and not a settings key: it takes effect per session, only under an eligible sign-in and
connection, and the program learns of it from Anthropic's servers.

> The HIPAA configuration takes effect only in sessions where a developer signs in with a Claude Enterprise account
> and Claude Code connects directly to the Claude API. On any other connection, developers can keep using Claude
> Code, but it doesn't apply the HIPAA configuration.

The page's table marks eligible only "A Claude Enterprise account, connecting directly to the Claude API"; Bedrock,
Google Cloud's Agent Platform, Microsoft Foundry, Claude Platform on AWS, a Claude apps gateway, an LLM gateway or
any other custom `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` or `apiKeyHelper` without Enterprise sign-in, and a
Claude Console API key or federation credentials are all "No" (https://code.claude.com/docs/en/hipaa-setup.md, ›
Check how developers sign in and connect, read 2026-11-25).

How the program on the machine knows that it applies:

> Claude Code learns that your organization has the HIPAA configuration by fetching your organization's policy from
> `api.anthropic.com`, when it starts and again about every hour while the session is in use. The policy is a record
> of your organization's HIPAA status and the feature restrictions that follow from it.

(https://code.claude.com/docs/en/hipaa-setup.md, › Allow network access, read 2026-11-25. The same section's host
table names `api.anthropic.com` "Claude API requests, telemetry, and the organization policy that tells Claude Code
the HIPAA configuration is on".) Claude Desktop learns it the same way:

> `api.anthropic.com` | Claude API requests, update checks, and the status that tells Claude Desktop the HIPAA
> configuration is on

(Set up Cowork (local mode) for a HIPAA-ready organization — https://claude.com/docs/cowork/hipaa-setup, › Allow
network access for Claude Desktop, read 2026-11-25.) Version floor:

> The HIPAA configuration requires Claude Code v2.1.285 or later and Claude Desktop v2.19675.0 or later.

(https://code.claude.com/docs/en/hipaa-setup.md, › Update Claude Code and Claude Desktop, read 2026-11-25.)

## 2. What it leaves on the machine that another program could read

The primary sources name these traces, all of them produced by the programs themselves, and none documented as a
file, a registry value, a configuration profile, an environment variable, or a settings key (all quotes
https://code.claude.com/docs/en/hipaa-setup.md, › Confirm the configuration on a computer, read 2026-11-25, unless
marked):

- A startup notice: "Confirm that Claude Code prints `Per your organization's policy, some features are limited ·
  /status for details` when it starts."
- A footer tag: "Confirm that a `HIPAA configured` tag appears at the right of the footer, below the prompt. Before
  v2.1.286, the tag read `HIPAA`."
- A line of `/status`: "Enter `/status` at the prompt. Confirm that the **Status** tab lists `HIPAA` on the
  `Organization configuration` line."
- A diagnostic line, from the same page's troubleshooting list: "look for an `Organization policy` line in `/status`,
  which gives the cause. Outside a session, run `claude doctor` and read the same line, which says where Claude Code
  loaded the policy from or why the policy didn't load."
- In Claude Desktop, a title-bar label: "Confirm that the title bar shows a **HIPAA configured** label. On a Mac,
  open the sidebar to see it." (https://claude.com/docs/cowork/hipaa-setup, › Confirm the HIPAA configuration in
  Claude Desktop, read 2026-11-25; the same page's troubleshooting adds "open the account menu, which shows the same
  **HIPAA configured** label".)
- Lifetime of the state, from the table of what developers see: "Restrictions remain after `/login` to a different
  organization | The HIPAA status lasts until Claude Code restarts"
  (https://code.claude.com/docs/en/hipaa-setup.md, › What developers see in Claude Code, read 2026-11-25).

No primary source says that this fetched policy is written anywhere on the machine. The caches the `.claude`
directory page documents are two, and neither is tied to the HIPAA status:

> `remote-settings.json` | Cached copy of server-managed settings for your organization, or `{}` when your
> organization has configured none. Only present when the session fetches them. Claude Code checks for updates at
> startup and hourly during a session. Claude Code deletes it when you log out.

> `policy-limits.json` | Cached feature policy settings for your organization. Only present for some account types.
> Refreshed automatically. A `policy-limits.json.stamp.json` sidecar records which account or API key the cache
> belongs to. Claude Code deletes both files when you log out.

(Explore the .claude directory — https://code.claude.com/docs/en/claude-directory.md, › Kept until you delete them,
read 2026-11-25.) The settings page, read in full, names four settings files and the managed sources — server-managed
settings, MDM or OS-level policies, `managed-settings.json` files, parent settings from an embedding host — and no
HIPAA key or HIPAA file (Settings files and precedence — https://code.claude.com/docs/en/settings.md, read
2026-11-25). The data-usage page, read in full, names no on-machine trace of the configuration either (Data usage —
https://code.claude.com/docs/en/data-usage.md, read 2026-11-25).

Two machine-resident files an organization deploys exist beside this, and the docs keep them separate from the
HIPAA status itself: the Claude Code managed settings (a `managed-settings.json` in a system directory, an MDM
policy, or server-managed settings), of which the HIPAA setup page says "The settings apply whether or not the HIPAA
configuration is in effect" (https://code.claude.com/docs/en/hipaa-setup.md, › Deploy managed settings, read
2026-11-25); and the Claude Desktop policy, delivered "as a configuration profile on macOS or as registry values on
Windows" — the sample uses the macOS domain `com.anthropic.claudefordesktop` and the Windows key
`HKLM\SOFTWARE\Policies\Claude` — whose keys the sample sets are `forceLoginOrgUUID`, `isLocalDevMcpEnabled`,
`isDesktopExtensionEnabled`, and `otlpContentCapture`, none of them a record of the HIPAA status
(https://claude.com/docs/cowork/hipaa-setup, › Deploy the Claude Desktop policy, read 2026-11-25). That page adds
one on-demand file: "go to **Help > Troubleshooting > Generate Diagnostic Report** and click **Export to file**. In
the saved `.zip` file, `managed-config.txt` lists each of the two keys with its value, marked as a default if the
policy didn't set it" (› Confirm the Claude Desktop policy loaded, read 2026-11-25) — a report of the deployed
policy keys, not of the status.

## 3. What `cleanupPeriodDays` deletes under it, and since which version

Without the configuration, a transcript of a session started or most recently continued in Claude Desktop or Cowork
is kept at any age unless the desktop key sets a limit:

> **Claude Desktop and Cowork transcripts**: Claude Code keeps the transcript of a session you started or most
> recently continued in Claude Desktop or Cowork at any age. To give these transcripts an age limit, set
> [`desktopSessionCleanupPeriodDays`](https://code.claude.com/docs/en/settings-reference#desktopsessioncleanupperioddays).
> Requires Claude Code v2.1.248 or later; earlier versions delete them after `cleanupPeriodDays`.

Under the configuration, `cleanupPeriodDays` deletes them alone, and the desktop key is ignored:

> Claude Code deletes these transcripts after `cleanupPeriodDays` instead in cases such as these:
>
> * [Managed settings](https://code.claude.com/docs/en/managed-settings.md) set `cleanupPeriodDays`
> * The [HIPAA configuration applies to your sessions](https://code.claude.com/docs/en/hipaa-setup.md#check-how-developers-sign-in-and-connect)

(Both quotes https://code.claude.com/docs/en/claude-directory.md, › Cleaned up automatically, read 2026-11-25. The
list is introduced by "in cases such as these", which marks it as not exhaustive.) The settings reference states the
same from the other key's side:

> By default, Claude Code keeps transcripts of sessions you started or most recently continued in Claude Desktop or
> Cowork past this period, even if you set this key yourself. This period [still applies to them in some
> cases](https://code.claude.com/docs/en/claude-directory.md#cleaned-up-automatically), such as under the HIPAA
> configuration. Before v2.1.248, Claude Code deleted them after this period.

(All settings — https://code.claude.com/docs/en/settings-reference.md, › `cleanupPeriodDays`, read 2026-11-25.) And
the desktop key's entry defers to that page's list:

> Claude Code deletes each transcript once it's older than both this limit and
> [`cleanupPeriodDays`](#cleanupperioddays), so with `cleanupPeriodDays` at its default of 30, a value of `7` still
> keeps them 30 days. [Cleaned up automatically](https://code.claude.com/docs/en/claude-directory.md#cleaned-up-automatically)
> lists cases where `cleanupPeriodDays` applies instead and Claude Code ignores this key.

(https://code.claude.com/docs/en/settings-reference.md, › `desktopSessionCleanupPeriodDays`, read 2026-11-25.)

Claude Desktop's own deletion under the configuration, for the Code tab and for Cowork (where the native logs of
Claude Desktop sessions live — `~/.claude/projects/` for Code tab transcripts, the Claude Desktop data folder for
Cowork tasks):

> With the HIPAA configuration applied, Claude Desktop deletes local Code tab sessions that have been inactive for
> longer than `cleanupPeriodDays`, including starred ones. It deletes them only while it's running.

(https://code.claude.com/docs/en/hipaa-setup.md, › Manage local session data › Code tab data, read 2026-11-25.)

> With the HIPAA configuration applied, Claude Desktop deletes Cowork tasks that have been inactive for longer than
> `cleanupPeriodDays`, including starred and archived ones. Running or opening a task counts as activity.

> Claude Desktop checks for tasks to delete after it starts, and every six hours while it stays open.

(https://claude.com/docs/cowork/hipaa-setup, › When Claude Desktop deletes Cowork tasks, read 2026-11-25. The same
section lists the conditions: Claude Desktop open, the owner signed in, switched to the organization, online, and
"Claude Desktop can read `cleanupPeriodDays`".)

The prompt history file is also touched under the configuration only:

> `history.jsonl` | Prompts you've typed, with timestamp and project path. Used for up-arrow recall, `Ctrl+R`
> history search, and `!` shell-command completion. Each sweep removes the entries older than `cleanupPeriodDays`
> when the [HIPAA configuration applies to your sessions](https://code.claude.com/docs/en/hipaa-setup.md#check-how-developers-sign-in-and-connect).

(https://code.claude.com/docs/en/claude-directory.md, › Kept until you delete them, read 2026-11-25. The section's
heading holds otherwise: "Apart from the rows that say otherwise, the retention cleanup sweep doesn't remove the
paths below".)

Versions. The desktop key exists since Claude Code v2.1.248, and before that version the desktop transcripts were
deleted after `cleanupPeriodDays` (the two quotes above, claude-directory.md and settings-reference.md, read
2026-11-25). The changelog entry of v2.1.248 reads:

> "Fixed Claude Desktop and Cowork sessions disappearing after 30 days" ... "the new `desktopSessionCleanupPeriodDays`
> setting caps the exemption"

(Claude Code changelog — https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md, › 2.1.248, read
2026-11-25.) For the HIPAA-specific rule itself no primary source names a release: the changelog ranges read
(2.1.332–2.1.267, 2.1.252–2.1.229, 2.1.204–2.1.147, partly — the chunk 2.1.290–2.1.284 contains the complete
2.1.285 entry and 2.1.284 down to its cut-off) name no HIPAA bullet at all (read 2026-11-25). The rule can only
arise from v2.1.285 on, the minimum version the HIPAA configuration requires (section 1).

## 4. The defaults and the validation of the two cleanup keys

`cleanupPeriodDays` (https://code.claude.com/docs/en/settings-reference.md, › `cleanupPeriodDays`, read 2026-11-25):

> * **Scope**: [`Any file`](#scopes)
> * **Type**: number of days, a whole number, minimum `1`
> * **Default**: `30`

> Setting `0` fails validation, so pick a large value such as `3650` for long retention.

The `.claude` directory page agrees: "The default is 30 days and the minimum is 1; setting `0` fails with a
validation error" (https://code.claude.com/docs/en/claude-directory.md, › Cleaned up automatically, read
2026-11-25). In the managed-source merge table it is an ordinary value: "Every other key | Takes the value from the
highest source that sets it | [`cleanupPeriodDays`](#cleanupperioddays), [`model`](#model)"
(https://code.claude.com/docs/en/settings-reference.md, › `managedSourcesBehavior`, read 2026-11-25).

`desktopSessionCleanupPeriodDays` (https://code.claude.com/docs/en/settings-reference.md, ›
`desktopSessionCleanupPeriodDays`, read 2026-11-25):

> * **Scope**: [`User or managed`](#scopes). Claude Code also reads the key from a file you pass with `--settings`,
>   and ignores it in project and local settings.
> * **Type**: number of days, a whole number, minimum `0`
> * **Default**: `0`, which sets no age limit

> Without this key, Claude Code [keeps those transcripts at any age](https://code.claude.com/docs/en/claude-directory.md#cleaned-up-automatically),
> except in cases such as a session you deleted in Claude Desktop. Requires Claude Code v2.1.248 or later.

Validation behaviour when a value cannot be determined (https://code.claude.com/docs/en/claude-directory.md, ›
Cleaned up automatically › Paused sweep, read 2026-11-25):

> **Paused sweep**: if Claude Code can't safely determine the retention period, it pauses the sweep; the
> [`retention_sweep` event](https://code.claude.com/docs/en/monitoring-usage#retention-sweep-event) reports why.
> When the cause is a settings file that can't be read or parsed, or settings errors with `cleanupPeriodDays` or
> `desktopSessionCleanupPeriodDays` set, `/status` shows a warning until you fix the cause.

> When [managed settings](https://code.claude.com/docs/en/managed-settings.md) provide `cleanupPeriodDays`, Claude
> Code runs the sweep at the managed value even when a lower-priority settings file has errors.

The OpenTelemetry event's skip reasons name both keys:

> * `"settings_unknowable"`: A settings source couldn't be read or parsed, so `cleanupPeriodDays` or
>   `desktopSessionCleanupPeriodDays` may be set to a value Claude Code can't see
> * `"settings_invalid_key_set"`: Settings have validation errors and `cleanupPeriodDays` or
>   `desktopSessionCleanupPeriodDays` is explicitly set, so falling back to the default could delete or keep files
>   against that setting

(Monitoring usage (OpenTelemetry events) — https://code.claude.com/docs/en/monitoring-usage.md, › Retention sweep
event, read 2026-11-25. The same event carries `transcripts_exempted_desktop`, "Number of transcripts past the
retention period that the sweep kept under the Claude Desktop and Cowork rule ... Requires Claude Code v2.1.248 or
later".) Claude Desktop skips its HIPAA deletion the same way:

> * **Claude Desktop can read `cleanupPeriodDays`**: if `managed-settings.json` can't be parsed, Claude Desktop
>   skips the check and deletes nothing. The same happens when no managed value is set and the member's settings
>   file can't be parsed or sets an invalid value

(https://claude.com/docs/cowork/hipaa-setup, › When Claude Desktop deletes Cowork tasks, read 2026-11-25. The same
section: "The value must be a whole number of 1 or more. Without a managed value, Claude Desktop uses the value in
the member's `~/.claude/settings.json`, or 30 days." For server-managed settings: "Claude Desktop reads
server-managed settings for this check, and uses one managed source at a time".)

Finally, the configuration itself caps nothing:

> The HIPAA configuration doesn't limit `cleanupPeriodDays`, so a developer can raise it in their own settings. When
> you set it in managed settings, Claude Code ignores the developer's value.

(https://code.claude.com/docs/en/hipaa-setup.md, › Deploy managed settings › What each key does, read 2026-11-25.)
Anthropic's own example managed file for HIPAA organizations sets `"cleanupPeriodDays": 30` and does not set
`desktopSessionCleanupPeriodDays` (settings-hipaa.json —
https://raw.githubusercontent.com/anthropics/claude-code/main/examples/settings/settings-hipaa.json, read
2026-11-25); the setup page's sample sets the same four keys, among them `"cleanupPeriodDays": 30`
(https://code.claude.com/docs/en/hipaa-setup.md, › Deploy managed settings, read 2026-11-25).

## Sources

| URL | Title | Date read | Primary | What it settles |
| :- | :- | :- | :- | :- |
| https://code.claude.com/docs/en/hipaa-setup.md | Set up Claude Code (local mode) for a HIPAA-ready organization | 2026-11-25 | Yes | Q1 definition, Primary Owner, eligibility, policy fetch from `api.anthropic.com`, v2.1.285 floor; Q2 the four in-program traces and no file; Q3 Code tab deletion under the configuration; Q4 "doesn't limit `cleanupPeriodDays`" and the sample managed file |
| https://claude.com/docs/cowork/hipaa-setup | Set up Cowork (local mode) for a HIPAA-ready organization | 2026-11-25 | Yes | Q1 Claude Desktop's status source; Q2 title-bar and account-menu labels, the Claude Desktop policy channels and diagnostic report; Q3 Cowork task deletion, its conditions and cadence; Q4 validation skip and the value chain managed › user › 30 |
| https://support.claude.com/en/articles/17318731 | Use Claude Code (local mode) and Cowork (local mode) on a HIPAA-ready Enterprise plan | 2026-11-25 | Yes | Q1 who applies it (Primary Owner only), Enterprise plans with account team, Anthropic enabling the button, per-member application; Q2 `/status` and label confirmation |
| https://support.claude.com/en/articles/8114513-business-associate-agreements-baa-for-commercial-customers | Business Associate Agreements (BAA) for Commercial Customers | 2026-11-25 | Yes | Q1 the BAA relationship of the configuration and that standard Enterprise plans need Primary Owner action |
| https://code.claude.com/docs/en/claude-directory.md | Explore the .claude directory | 2026-11-25 | Yes | Q3 the two-case rule (managed settings, HIPAA) and the v2.1.248 floor; Q3 `history.jsonl` under HIPAA; Q4 defaults and the paused sweep |
| https://code.claude.com/docs/en/settings-reference.md | All settings (settings reference) | 2026-11-25 | Yes | Q3 both keys' interaction with the HIPAA case; Q4 Scope, Type, Default of both keys, `0` failing validation, merge row |
| https://code.claude.com/docs/en/settings.md | Settings files and precedence | 2026-11-25 | Yes | Q2 absence: the four files and managed sources, no HIPAA key or file |
| https://code.claude.com/docs/en/data-usage.md | Data usage | 2026-11-25 | Yes | Q2 absence: retention and telemetry, no on-machine trace of the configuration; local plaintext retention of 30 days by default |
| https://code.claude.com/docs/en/monitoring-usage.md | Monitoring usage (OpenTelemetry events) | 2026-11-25 | Yes | Q4 the `retention_sweep` event, its skip reasons naming both keys, `transcripts_exempted_desktop` |
| https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md | Claude Code changelog | 2026-11-25 | Yes | Q3 the v2.1.248 introduction bullet; the absence of HIPAA bullets in the ranges read |
| https://raw.githubusercontent.com/anthropics/claude-code/main/examples/settings/settings-hipaa.json | settings-hipaa.json (settings examples repository) | 2026-11-25 | Yes | Q4 the example sets `cleanupPeriodDays: 30` and no `desktopSessionCleanupPeriodDays` |

## What no primary source says

- No primary source names any file, Windows registry value, macOS configuration profile, environment variable, or
  settings key on the machine that records or reveals that the HIPAA configuration applies; every trace the docs
  name is program output (`/status`, `claude doctor`, the startup notice, the footer tag, the Claude Desktop
  title-bar and account-menu labels), and none is documented as a file another program can read.
- No primary source says whether the organization policy that Claude Code fetches at start and about hourly from
  `api.anthropic.com` is cached on disk; the two caches documented under `~/.claude` (`remote-settings.json`,
  `policy-limits.json`) are described as the cache of server-managed settings and of feature policy settings, and no
  source ties either to the HIPAA status.
- No primary source says how Claude Desktop learns the status beyond "the status that tells Claude Desktop the HIPAA
  configuration is on" from `api.anthropic.com`; only Claude Code's cadence (start and about hourly) is documented.
- No primary source dates the HIPAA-specific deletion rule (`cleanupPeriodDays` deletes Claude Desktop and Cowork
  transcripts alone); it is stated only in the current pages, and the changelog ranges read — including the
  complete 2.1.285 entry — name no HIPAA bullet. The rule can only arise from v2.1.285 on, the version the
  configuration requires.
- No primary source names the file whose `cleanupPeriodDays` value pairs with Claude Desktop's deletion of Code tab
  sessions under the configuration; only the Cowork page documents a chain there (managed value, else the member's
  user settings, else 30 days).
- No primary source says what the sweep does on a machine where the hourly policy fetch fails after a
  HIPAA-eligible start; the docs describe only the `Organization policy` diagnostic line and that "The HIPAA status
  lasts until Claude Code restarts".
