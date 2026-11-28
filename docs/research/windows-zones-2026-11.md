# Windows time-zone names to IANA zones — the CLDR release choice (2026-11)

Point-in-time note that precedes plan Task 43: the ledger converts Windows time-zone names (for
example `W. Europe Standard Time`) to IANA zone names (for example `Europe/Berlin`) with a
committed table of the territory `001` rows of one CLDR release (CLDR = Unicode Common Locale Data
Repository; `common/supplemental/windowsZones.xml` maps Windows names to IANA zones per territory;
territory `001` is the "world" default mapping). The open choice is which CLDR release pins the
table and how an update reaches a future release of the ledger. This note gathers the facts; the
owner rules. Facts are the state on 2026-11-23; the committed table of the core is the current
truth, this file is not updated.

Every `windowsZones.xml` fact below was checked by fetching the file of the named release tag from
raw.githubusercontent.com and counting the rows cited; the zoneinfo check ran in the project
virtual environment (Python 3.12, `tzdata` 2026.6) on 2026-11-23.

## Facts

### Releases and cadence

- The current release is CLDR 49, released 2026-10-22
  ([cldr.unicode.org](https://cldr.unicode.org/)).
- CLDR ships one or two data releases per year plus dot releases. The download page lists: 47 on
  2025-03-13, 48 on 2025-10-29, 48.1 on 2026-01-08, 48.2 on 2026-03-17, 49 on 2026-10-22
  ([downloads](https://cldr.unicode.org/index/downloads)). The CLDR 48 page adds dot releases
  48.2.1, 48.2.2, and 48.2.3, each stated as "Compatibility with TZDB 2026c", "2026d", and "2026e"
  ([CLDR 48](https://cldr.unicode.org/index/downloads/cldr-48)) — dot releases exist to track the
  IANA tz database between data releases.
- Release tags on `github.com/unicode-org/cldr` have the form `release-49`, `release-48`,
  `release-48-2`, `release-47` (checked via the GitHub tags API on 2026-11-23).

### The file of release-49

- Stable URL of the file of the release: [windowsZones.xml of release-49][wz] (the same bytes were
  fetched from raw.githubusercontent.com under the tag ref).
- The file holds 505 `<mapZone>` rows in total; 142 of them have `territory="001"` (counted in the
  fetched file). The 142 rows carry 142 distinct `other` values, so every Windows name in the file
  has exactly one default row — as the LDML spec requires: "For each unique Windows TZID, there
  must be exactly one `<mapZone>` element with `territory="001"`", and that mapping "is used as
  the default mapping for the Windows TZID"
  ([UTS #35](https://unicode.org/reports/tr35/tr35-dates.html), section Windows Zones, under
  Supplemental Time Zone Data).
- Illustrative rows of territory `001`, verbatim from the release-49 file:

  ```xml
  <mapZone other="Dateline Standard Time" territory="001" type="Etc/GMT+12"/>
  <mapZone other="UTC" territory="001" type="Etc/UTC"/>
  <mapZone other="W. Europe Standard Time" territory="001" type="Europe/Berlin"/>
  <mapZone other="FLE Standard Time" territory="001" type="Europe/Kiev"/>
  ```

- No territory-`001` row maps to more than one IANA zone (0 of the 142). Multi-zone values exist
  only in territory-specific rows, 43 rows in the file, for example `Alaskan Standard Time` / `US`
  maps to a list of six zones; the spec says the first entry of such a list is the default for
  that territory ([UTS #35](https://unicode.org/reports/tr35/tr35-dates.html)).
- Standard/daylight mechanics: the release-49 file has no `standard` or `dst` attribute at all —
  the [DTD of release-49][d] defines `mapZone` with only `type` and `other` (required) and
  `territory` and `references` (implied), and the string "Daylight" does not occur in the file (0
  occurrences). Only Windows standard names map (142 distinct values, of which all but ten end in
  "Standard Time"; the ten are the UTC-offset family `UTC`, `UTC+12`, `UTC+13`, `UTC-02`,
  `UTC-08`, `UTC-09`, `UTC-11` and `Russia Time Zone 3/10/11`). Daylight behaviour comes from the
  rules of the mapped IANA zone, not from a second mapping.
- The spec defines a third territory: "The territory 'ZZ' is used when a Unicode time zone ID is
  not associated with a specific territory"
  ([UTS #35](https://unicode.org/reports/tr35/tr35-dates.html)); the release-49 file has 27 `ZZ`
  rows, which the ledger's table does not need.
- The `mapTimezones` element opens with `otherVersion="7e11800" typeVersion="2021a"`. Per the spec
  these attributes "specify the versions of two systems": the Windows data and the tz database the
  mapping was last checked against ([UTS #35](https://unicode.org/reports/tr35/tr35-dates.html)).
  The attribute is not a freshness signal: it reads `typeVersion="2021a"` in release-47,
  release-48, and release-49 alike, while the commit messages of the same file reference later
  tzdb updates (for example "Update CLDR data to TZDB 2025b", 2025-04-10). Judge freshness from
  the release, not from this attribute.

### How the file changes

- The commit history of `common/supplemental/windowsZones.xml` ([history][hist]) shows one to two
  commits per year, and exactly one landed in each of the last two data releases:
  - [c33a1f0a](https://github.com/unicode-org/cldr/commit/c33a1f0a), 2025-04-10, "Update CLDR data
    to TZDB 2025b" — landed in release-48; it changed one territory row (`Magallanes Standard
    Time` / `CL` gained `America/Coyhaique` as a second zone; the release-47 and release-48 files
    both hold 139 territory-`001` rows, counted in the fetched files). The new zone
    `America/Coyhaique` is named on the
    [CLDR 48 page](https://cldr.unicode.org/index/downloads/cldr-48).
  - [c4bb2c19](https://github.com/unicode-org/cldr/commit/c4bb2c19), 2026-10-09, "CLDR-19827
    Update Windows zones" (+14 −3 lines) — landed in release-49; it splits Windows zone names
    along Canadian provinces: territory-`001` rows went 139 → 142, with new default rows
    `British Columbia Standard Time` → `America/Vancouver`, `Alberta Standard Time` →
    `America/Edmonton`, `Manitoba Standard Time` → `America/Winnipeg`, and the corresponding `CA`
    rows re-scoped (`Pacific Standard Time`/`CA` removed, `Mountain Standard Time`/`CA` reduced,
    `Central Standard Time`/`CA` reduced). Diffed release-48 against release-49 on 2026-11-23.
    This is the material change pattern: Microsoft adds Windows zone names, CLDR maps them, and
    the `001` table grows.
- None of the TZDB-compat dot releases 48.1, 48.2, 48.2.1–48.2.3 touched `windowsZones.xml` (no
  commit in the file history between 2025-04-10 and 2026-10-09) — tzdb rule changes flow into
  `metaZones.xml` and the zone rules, not into the Windows-name mapping.
- CLDR also prunes: [ac0de544](https://github.com/unicode-org/cldr/commit/ac0de544), 2024-08-28,
  "Remove deprecated zone IDs from metaZones/windowsZones" deleted the four `ZZ` rows that mapped
  the fixed-offset IDs `PST8PDT`, `MST7MDT`, `CST6CDT`, `EST5EDT` (patch inspected on 2026-11-23).
  The territory-`001` rows were not touched by that cleanup.

### Zone id aliasing and what zoneinfo accepts

- The territory-`001` table of release-49 maps to legacy tzdb names that still exist in the IANA
  database as links, not as primary names: `Europe/Kiev`, `Asia/Calcutta`, `Asia/Katmandu`,
  `Asia/Rangoon` (read in the release-49 file). IANA renamed `Europe/Kiev` to `Europe/Kyiv` in
  tzdb 2022b ([NEWS](https://data.iana.org/time-zones/tzdb/NEWS)) and keeps the old names as links
  ([backward](https://data.iana.org/time-zones/tzdb/backward): `Link Europe/Kyiv Europe/Kiev`,
  `Link Asia/Kolkata Asia/Calcutta`, `Link Asia/Kathmandu Asia/Katmandu`,
  `Link Asia/Yangon Asia/Rangoon`).
- The CLDR mapping therefore points at IDs one tzdb generation behind for a few zones; that is by
  design and harmless for a consumer that resolves links: all 142 territory-`001` values of
  release-49 open with `zoneinfo.ZoneInfo` against `tzdata` 2026.6, 0 failures (checked
  2026-11-23, project virtual environment).
- ICU, the reference consumer, generates its `windowsZones.res` from CLDR's `windowsZones.xml` —
  the header of [windowsZones.txt][icuwz] reads "Generated using tools/cldr/cldr-to-icu/". ICU's
  zone rules derive from the IANA database, and ICU publishes updated zone data on each IANA
  release ([ICU userguide](https://unicode-org.github.io/icu/userguide/datetime/timezone/)). The
  ledger does not use ICU; its chain is CLDR (the name mapping, committed here) and IANA tzdb
  through `tzdata` (the rules).

## Options for the release choice

### Best — pin the current stable release (CLDR 49)

Commit the 142 territory-`001` rows of [release-49][wz] (2026-10-22, the newest data release) as
the table, with the release tag named in the module.

- Costs: none beyond the table itself (142 rows of data; size is not a concern).
- Risks: CLDR 49 is a snapshot; a CLDR 50 could add or re-scope Windows names (the pattern of the
  49 Canadian split). The ledger would answer an unknown new Windows name until the owner
  refreshes the table. Also, 142 rows include 4 IDs that are tzdb links (`Europe/Kiev`,
  `Asia/Calcutta`, `Asia/Katmandu`, `Asia/Rangoon`) — they open today (verified), but a consumer
  that rejects link names would not.
- Binds: the release tag `release-49` named in the data module, and the committed rows. Conversion
  is deterministic and tests are stable, because the table changes only when the owner changes it.

### Cleanest — pin CLDR 49 and re-verify against tzdata at test time

The same committed table, plus a unit test that opens every zone value of the table with
`zoneinfo` and asserts a few fixed conversions.

- Costs: one test to write and maintain.
- Risks: the test depends on the installed `tzdata`; a future CLDR mapping to a very new zone (the
  `America/Coyhaique` pattern) would fail the test until `tzdata` is bumped — that failure is the
  point: it surfaces the drift at test time instead of at run time. Pinning the test to the
  `tzdata` version keeps it reproducible; leaving it unpinned makes it an early-warning.
- Binds: as Best, plus the test and (optionally) the `tzdata` floor. The variant "pin the release
  that ICU derives from" adds nothing here: ICU generates its table from CLDR itself (header of
  [windowsZones.txt][icuwz]), so its pin is downstream of the same file, and the ledger has no ICU
  dependency to align with.

### Most general — a regeneration path

Keep the table committed, and add a small standard-library script that takes a release tag,
fetches the `windowsZones.xml` of that tag, extracts the territory-`001` rows, and rewrites the
table file; the diff lands as one reviewable commit, gated by the test of the Cleanest option.

- Costs: one script to maintain and one documented step (where it runs, which tag it names).
- Risks: a regeneration from a future release could change mapping values, not only add rows — the
  review diff and the test are the guards. The script is the only code that would need to parse
  the file; if it is never run, the table stays as committed.
- Binds: the tag is a named parameter of the script run, recorded in the commit message; the table
  file format stays the single interface between the script and the core.

## The update path

How a future CLDR release's table reaches a new ledger release:

- **Manual re-export, test-gated.** The owner fetches the file of the new release tag, re-cuts the
  `001` rows, commits, and the zoneinfo test gates every value. Changes are rare (one commit per
  data release in the last two cycles) and visible in advance: the CLDR release pages list
  supplemental-data changes ([CLDR 49](https://cldr.unicode.org/index/downloads/cldr-49):
  "Metazone and timezone data"), and dot releases for TZDB compatibility have not touched
  `windowsZones.xml` so far, so only data releases need watching.
- **Committed generator script.** The Most general option above makes the re-export reproducible
  and turns the update diff into an exact row-level record; its cost is the script itself.
- **Release-notes watch.** Watching the CLDR release pages and the file's commit history
  ([history][hist]) tells the owner *when* to update; it is a hygiene rule, not a mechanism, and
  pairs with either path above.

## Sources

Read 2026-11-23 unless stated otherwise:

- https://cldr.unicode.org/ — current release and date (CLDR 49, 2026-10-22).
- https://cldr.unicode.org/index/downloads — release table with dates.
- https://cldr.unicode.org/index/downloads/cldr-49 — supplemental-data changes of CLDR 49.
- https://cldr.unicode.org/index/downloads/cldr-48 — TZDB-compat dot releases 48.2.1–48.2.3;
  `America/Coyhaique`.
- [windowsZones.xml of release-49][wz], and of [release-48][r48] and [release-47][r47] for the
  comparisons — fetched from raw.githubusercontent.com under the tag refs and counted (505 rows,
  142 of territory `001` in release-49).
- [The supplemental DTD of release-49][d] — `mapZone` attribute list (no `standard`/`dst`).
- https://unicode.org/reports/tr35/tr35-dates.html — section Windows Zones: the requirement of one
  `001` row per Windows TZID, the default-mapping rule, `otherVersion`/`typeVersion`, territory
  `ZZ`.
- [Commit history of windowsZones.xml][hist].
- https://github.com/unicode-org/cldr/commit/c4bb2c19 — CLDR-19827, the release-49 change (+14 −3,
  Canadian split); https://github.com/unicode-org/cldr/commit/c33a1f0a — TZDB 2025b, the
  release-48 change; https://github.com/unicode-org/cldr/commit/ac0de544 — deprecated-zone-ID
  cleanup.
- [ICU windowsZones.txt][icuwz] — "Generated using tools/cldr/cldr-to-icu/".
- https://unicode-org.github.io/icu/userguide/datetime/timezone/ — ICU zone data origin and update
  route.
- https://data.iana.org/time-zones/tzdb/backward — the link names (`Link Europe/Kyiv Europe/Kiev`,
  …).
- https://data.iana.org/time-zones/tzdb/NEWS — tzdb 2022b, "Rename Europe/Kiev to Europe/Kyiv".
- Further reading (not used as a fact source above): the Windows-side list of zone names and
  offsets is documented by Microsoft at
  https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/default-time-zones.

[wz]: https://github.com/unicode-org/cldr/blob/release-49/common/supplemental/windowsZones.xml
[r48]: https://github.com/unicode-org/cldr/blob/release-48/common/supplemental/windowsZones.xml
[r47]: https://github.com/unicode-org/cldr/blob/release-47/common/supplemental/windowsZones.xml
[d]: https://raw.githubusercontent.com/unicode-org/cldr/release-49/common/dtd/ldmlSupplemental.dtd
[icuwz]: https://github.com/unicode-org/icu/blob/main/icu4c/source/data/misc/windowsZones.txt
[hist]: https://github.com/unicode-org/cldr/commits/main/common/supplemental/windowsZones.xml
