"""The text of the reports (command-line.md › Output, › Reports): one table for each
section of the document of a command, the durations as H:MM in whole minutes, and the
project names, work item names, and notes as the person wrote them.

No sentence of the spec fixes the layout of a table, and the command line and its JSON
output are the stable contract, so this interface fixes the layout:
the text of a document is a group of sections, separated by one empty line, and a
section is a title line, a table, or a group of figure lines. A table has the labels of
its column keys as a header — the keys of the document, in order — and one row for each
entry of the document, with the totals row of a day last. The tables against the frozen
reports hold the one exception: a figure or a fact whose value is an
object shows as one row for each scalar leaf that differs, named by its dotted path. A document
that holds `frozen` is that of `frozen list` or of `frozen show`: the list is one table under
the title of the frozen reports; the frozen report of `frozen show` opens with one title line
that names it, and its sections are those of its own command, then those against the report of
now. A report whose document holds `frozen_id` ends with the line of that identifier. A
document that holds `event_uid` and `entries` is that of `timesheet confirm`: the line of the
identifier of the confirmation, then the table of the entries of the day in the columns of
`timesheet <day>`, with no title line and no totals row, because the document holds neither
the day, its state, nor its totals. Two spaces separate the columns, every column is as wide
as its widest cell, the first column and the columns whose cells hold no number are
left-aligned, and the numbers are right-aligned. A share and the parallel ratio show
with two decimals. The text meets the values only as the document holds them and never
reshapes them: the renderer reads no values of the configuration or of the store and
translates no name. Where a table names a machine, its column Machine shows the machine
label when the store holds one for that machine, and the identifier otherwise: `frozen list`
takes the label from the `machine_label` of its rows, and `entries`, whose document holds
the fields of the events alone, from the labels that its caller passes. The report of a day
holds one sentence that its document does not: the note of `language` that the activity
classes of the projects and of the work items do not always add up to those of the person, a
section of one line after the table of the work items, on every day — also one where they
add up — because the renderer computes nothing to qualify it (metrics.md › Activity
classes)."""

import json
import re
from collections.abc import Mapping, Sequence

from ..declared import DECLARED_DAY
from ..language import label, note

_KEY_FACTS = ("event_uid", "kind", "timestamp")
"""The keys that each entry of `entries` holds first (command-line.md › JSON documents)."""

_FROZEN_COLUMNS = ("id", "report", "from", "to", "note", "machine", "frozen_at")
"""The columns of the table of `frozen list`, the keys of its rows in order but
`machine_label` (command-line.md › JSON documents): the column `machine` shows the machine
label of a row that holds one in place of the identifier."""

_TIMESHEET_COLUMNS = ("project", "work_item", "measured", "with_manual_entries",
                      "declared", "inferred_human_share", "inferred_agent_share")
"""The columns of the table of the entries of a day, the keys of the document in order."""

_SESSION_COLUMNS = ("session_id", "tool", "start", "end", "cwd", "branch", "project",
                    "work_item", "human_time", "agent_time")
"""The columns of the table of the sessions of a day, the keys of the document in order."""

_ACTIVITY_CLASSES = ("person_only", "supervised", "unattended", "blocked", "idle")
"""The activity classes in the order of the table of metrics.md › Activity classes."""

_DURATION_FIELDS = frozenset({"duration"})
"""The fields of an event whose value is a duration in whole seconds (command-line.md ›
JSON documents)."""

_DIFFERENCE_COLUMNS = ("day", "project", "work_item", "figure", "frozen", "now")
"""The columns of the table of the differences against the frozen reports: the keys of
its rows in order, a key that a row does not hold leaving an empty cell (command-line.md
› Frozen reports, › JSON documents)."""

_CHANGED_COLUMNS = ("path", "frozen", "now")
"""The columns of the table of the report parameters, rules, and dated facts that changed
between the report records (command-line.md › JSON documents)."""

_DURATIONS = frozenset({"total", "measured_total", "measured", "with_manual_entries",
                        "declared", "human_time", "agent_time", "blocked_time",
                        "activity_classes", "human_time_at_idle_gaps",
                        "parameters.idle_gap", "parameters.minimum_attention",
                        "parameters.stale_limit", "parameters.timesheet_granularity"})
"""The figures of `differences` and the facts of `changed` whose value, or whose leaves,
is a duration in whole seconds (command-line.md › JSON documents, › Output)."""

_DECIMAL_FIGURES = frozenset({"inferred_human_share", "inferred_agent_share",
                              "unknown_invocation_share", "parallel_ratio"})
"""The figures of a difference whose value is a number from a division, a share or the
parallel ratio, that the text shows with two decimals (command-line.md › JSON
documents)."""

_NUMBER = re.compile(r"[0-9]+(?::[0-9]{2})?(?:\.[0-9]+)?\Z")
"""The cells that hold a number: a count of seconds, a duration, or a share or the
parallel ratio."""


def format_duration(seconds: int) -> str:
    """The duration as H:MM: whole minutes, the seconds left out, the hours beyond 24
    kept, so that the table never shows more than the value (command-line.md › Output)."""
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}"


def render(document: dict, language: str,
           machine_labels: Mapping[str, str] | None = None) -> str:
    """The text of the document of one command of the reports (command-line.md ›
    Output): one table for each section of the document, the sections separated by one
    empty line, the titles and the states from `language.label`, and no line at the
    end — the writer of the text adds it. `machine_labels` holds the machine label of each
    machine that has one, by its identifier, for the column Machine of `entries`."""
    sections = _sections(document, language, machine_labels or {})
    return "\n\n".join("\n".join(section) for section in sections)


def _sections(document: dict, language: str,
              machine_labels: Mapping[str, str]) -> list[list[str]]:
    """The sections of the document of one command: those of its own shape, and — for a
    report whose document holds `frozen_id`, as the document of a report with `--freeze`
    does — the line of the identifier of its frozen report last (command-line.md › Frozen
    reports)."""
    if "frozen" in document:
        return _frozen(document, language)
    sections = (_timesheet(document, language) if "days" in document
              else _day_report(document, language) if "person" in document
              else _sessions(document, language) if "sessions" in document
              else _day_sections(document, language) if "context" in document
              else _confirmation(document, language) if "event_uid" in document
              else _entries(document, language, machine_labels))
    if "frozen_id" in document:
        sections.append([f"{label('frozen_report', language)}  {document['frozen_id']}"])
    return sections


def _frozen(document: dict, language: str) -> list[list[str]]:
    """The sections of `frozen list` and of `frozen show` (command-line.md › Frozen reports):
    the list of the frozen reports is one table under the title of the frozen reports; the
    one frozen report of `frozen show` opens with one title line — the label of a frozen
    report, its identifier, and its command — followed by the sections of its own command,
    which hold no line of the identifier because the title names it, and by the sections
    against the report of now."""
    frozen = document["frozen"]
    if isinstance(frozen, list):
        return [[label("frozen_reports", language),
                 *_table(_FROZEN_COLUMNS,
                         [[_cell(key, row.get("machine_label", row.get("machine"))
                                 if key == "machine" else row.get(key))
                           for key in _FROZEN_COLUMNS]
                          for row in frozen], language)]]
    kept = {key: value for key, value in frozen.items() if key != "frozen_id"}
    title = [label("frozen_report", language)]
    if "frozen_id" in frozen:
        title.append(frozen["frozen_id"])
    title.append(frozen["command"])
    return [["  ".join(title)],
            *_sections(kept, language, {}), *_frozen_sections(document, language)]


def _timesheet(document: dict, language: str) -> list[list[str]]:
    """The sections of `report timesheet` (command-line.md › JSON documents): one group
    of sections for each day of the period, in the order of the days, then the sections
    against the frozen reports when the document holds them."""
    sections: list[list[str]] = []
    for day in document["days"]:
        sections.extend(_day_sections(day, language))
    sections.extend(_frozen_sections(document, language))
    return sections


def _day_report(document: dict, language: str) -> list[list[str]]:
    """The sections of `report day` (command-line.md › JSON documents): the day, then one
    table for the person, for the projects, and for the work items, with a column for
    the parallel ratio beside the agent time and one for each activity class that the
    figures of the day hold, then the note that the activity classes of the projects and
    of the work items do not always add up to those of the person — a section of one
    line that the document does not hold —, then the share of the unknown invocation,
    the human time at the idle gaps of a measured day, and the sections against the
    frozen reports when the document holds them. The person holds no shares and a work
    item holds no project in the document."""
    classes = [name for name in _ACTIVITY_CLASSES
               if any(name in entry["activity_classes"] for entry in
                      [document["person"], *document["projects"],
                       *document["work_items"]])]
    measures = ("human_time", "agent_time", "parallel_ratio", "blocked_time", *classes)
    sections: list[list[str]] = [[_day_title(document, language)],
                               [label("person", language),
                                *_table(measures, [_measures_row(document["person"],
                                                                 classes, False)],
                                        language)],
                               [label("projects", language),
                                *_table(("project", *measures, "inferred_human_share",
                                         "inferred_agent_share"),
                                        [_measures_row(entry, classes, True,
                                                       _project_cell(entry["project"],
                                                                     language))
                                         for entry in document["projects"]], language)],
                               [label("work_items", language),
                                *_table(("work_item", *measures, "inferred_human_share",
                                         "inferred_agent_share"),
                                        [_measures_row(entry, classes, True,
                                                       _shown(entry["work_item"]))
                                         for entry in document["work_items"]], language)],
                               [note("activity_classes_do_not_add_up", language)],
                               _share_section(document, language)]
    if document.get("human_time_at_idle_gaps"):
        sections.append(_idle_gaps_section(document["human_time_at_idle_gaps"], language))
    sections.extend(_frozen_sections(document, language))
    return sections


def _frozen_sections(document: dict, language: str) -> list[list[str]]:
    """The sections that a report against frozen reports adds (command-line.md › Frozen
    reports): the table of the figures that differ, one row for each figure of each day,
    project, and work item, then the table of the report parameters, rules, and dated
    facts that changed; a figure or a fact whose value is an object gives one row for
    each of its leaves, and a document that holds neither key gives no section."""
    sections: list[list[str]] = []
    if "differences" in document:
        sections.append([label("differences", language),
                         *_table(_DIFFERENCE_COLUMNS,
                                 [row for held in document["differences"]
                                  for row in _difference_rows(held, language)],
                                 language)])
    if "changed" in document:
        sections.append([label("changed", language),
                         *_table(_CHANGED_COLUMNS,
                                 [row for held in document["changed"]
                                  for row in _changed_rows(held)], language)])
    return sections


def _difference_rows(held: dict, language: str) -> list[list[str]]:
    """The rows that one row of `differences` gives: the day, the project and the work
    item that hold the figure when the row names them — the unattributed time is a
    project the row names as null — and one row for each leaf of the figure, with its
    frozen value and its value of now; a value that the row does not hold is no
    cell."""
    head = [held["day"],
            _project_cell(held["project"], language) if "project" in held else "",
            _shown(held["work_item"]) if "work_item" in held else ""]
    return [[*head, name, _value_cell(held["figure"], frozen),
             _value_cell(held["figure"], now)]
            for name, frozen, now in _leaves(held["figure"], held.get("frozen"),
                                             held.get("now"))]


def _changed_rows(held: dict) -> list[list[str]]:
    """The rows that one row of `changed` gives: one row for each leaf of the fact of the
    report record, with its frozen value and its value of now."""
    return [[name, _value_cell(held["path"], frozen), _value_cell(held["path"], now)]
            for name, frozen, now in _leaves(held["path"], held.get("frozen"),
                                             held.get("now"))]


def _leaves(name: str, frozen: object, now: object) -> list[tuple[str, object, object]]:
    """The leaves of one figure or fact of the tables against the frozen reports
    (command-line.md › Frozen reports): a value that is no object is
    its own leaf, under the name of its figure or fact; a value that is an object gives
    one leaf for each key that its two objects name, under the dotted path of the key,
    the keys of the frozen object first. A null or absent leaf is None; a leaf that is
    the same on both sides gives no row — which leaves out a leaf that neither object
    holds, null on one side and absent on the other."""
    if not (isinstance(frozen, dict) or isinstance(now, dict)):
        return [(name, frozen, now)]
    held = frozen if isinstance(frozen, dict) else {}
    current = now if isinstance(now, dict) else {}
    leaves: list[tuple[str, object, object]] = []
    for key in [*held, *(one for one in current if one not in held)]:
        before, after = held.get(key), current.get(key)
        if before == after:
            continue
        leaves.append((f"{name}.{key}", before, after))
    return leaves


def _value_cell(name: str, value: object) -> str:
    """One cell of the two tables against the frozen reports: the value of a figure, of a
    fact of the report record, or of one leaf of them, which has the kind of its figure
    or fact (command-line.md › Output). A duration shows as H:MM and a share or the
    parallel ratio with two decimals; any other value shows as the document holds it,
    and a value of more than one part as its JSON text; no value, no cell."""
    if value is None:
        return ""
    if name in _DURATIONS:
        return format_duration(value)
    if name in _DECIMAL_FIGURES:
        return _decimal(value)
    return _cell(name, value)


def _day_sections(day: dict, language: str) -> list[list[str]]:
    """The sections of one day of the timesheets (command-line.md › JSON documents): the
    table of its entries with the totals row last, then the context of `timesheet
    <day>`, the share of the unknown invocation, and the human time at the idle gaps of
    a measured day, in the order of the document. The context shows the parallel ratio
    of the day right after its agent time when it holds the key, which a day without
    agent time does not."""
    columns = list(_TIMESHEET_COLUMNS)
    if any("proposed" in entry for entry in day["entries"]):
        columns.append("proposed")
    rows = [_entry_row(entry, language) for entry in day["entries"]]
    rows.append(_totals_row(day, language, len(columns)))
    sections = [[_day_title(day, language), *_table(columns, rows, language)]]
    context = day.get("context")
    if context is not None:
        figures = [f"{label('agent_time', language)}  "
                   f"{_duration(context['agent_time'])}"]
        if "parallel_ratio" in context:
            figures.append(f"{label('parallel_ratio', language)}  "
                           f"{_decimal(context['parallel_ratio'])}")
        if context["presence_span"] is not None:
            figures.append(f"{label('presence_span', language)}  "
                           f"{_duration(context['presence_span'])}")
        sections.append(figures)
    sections.append(_share_section(day, language))
    if day.get("human_time_at_idle_gaps"):
        sections.append(_idle_gaps_section(day["human_time_at_idle_gaps"], language))
    return sections


def _sessions(document: dict, language: str) -> list[list[str]]:
    """The sections of `sessions <day>` (command-line.md › JSON documents): one row for
    each project and work item of a session — the part that the split rule gives — with
    the keys of the session repeated on it, and one row for a session that holds no
    part, its part cells empty. A session whose document holds no folder or no branch
    leaves the cell empty."""
    rows = []
    for session in document["sessions"]:
        for part in session["parts"] or [None]:
            rows.append([session["session_id"], session["tool"], session["start"],
                         session["end"], _own(session, "cwd"), _own(session, "branch"),
                         *_part_cells(part, language)])
    return [[f"{document['day']}  {label('sessions', language)}",
             *_table(_SESSION_COLUMNS, rows, language)]]


def _own(session: dict, key: str) -> str:
    """The cell of a key that a session may hold or not: its text, or no cell when the
    session holds none, because an absent field is not written."""
    value = session.get(key)
    return "" if value is None else value


def _part_cells(part: dict | None, language: str) -> list[str]:
    """The cells of one part of a session: the names that reports show, the
    unattributed time for a part whose project the document holds as null, and no cell
    for a session that holds no part."""
    if part is None:
        return ["", "", "", ""]
    return [_project_cell(part["project"], language), _shown(part["work_item"]),
            _duration(part["human_time"]), _duration(part["agent_time"])]


def _confirmation(document: dict, language: str) -> list[list[str]]:
    """The sections of `timesheet confirm` (command-line.md › JSON documents): the line of
    the identifier of the confirmation that the command wrote, then the table of the
    entries of the day in the columns of `timesheet <day>`, the proposed value last."""
    rows = [_entry_row(entry, language) for entry in document["entries"]]
    return [[f"{label('event_uid', language)}: {document['event_uid']}"],
            _table((*_TIMESHEET_COLUMNS, "proposed"), rows, language)]


def _entries(document: dict, language: str,
             machine_labels: Mapping[str, str]) -> list[list[str]]:
    """The sections of `entries` (command-line.md › JSON documents): `event_uid`, `kind`,
    and `timestamp` first, then the other fields of the events by name, one column for
    each field that any entry holds, a field that one entry misses holding no cell; the
    column of `machine` shows the machine label of the machine of an event when
    `machine_labels` holds one, and its identifier otherwise."""
    rest = sorted({key for entry in document["entries"] for key in entry} - set(_KEY_FACTS))
    columns = [*_KEY_FACTS, *rest]
    rows = [[_cell(key, machine_labels.get(entry["machine"], entry["machine"])
                   if key == "machine" else entry.get(key))
             for key in columns] for entry in document["entries"]]
    return [[f"{document['day']}  {label('events', language)}",
             *_table(columns, rows, language)]]


def _entry_row(entry: dict, language: str) -> list[str]:
    """One row of the table of the entries of a day: the names that reports show, the
    durations as H:MM, and the shares with two decimals; the proposed value last on the
    day of `timesheet <day>`."""
    row = [_project_cell(entry["project"], language), _shown(entry["work_item"]),
           _duration(entry["measured"]), _duration(entry["with_manual_entries"]),
           _duration(entry["declared"]), _decimal(entry["inferred_human_share"]),
           _decimal(entry["inferred_agent_share"])]
    if "proposed" in entry:
        row.append(_duration(entry["proposed"]))
    return row


def _totals_row(day: dict, language: str, width: int) -> list[str]:
    """The totals row of the table of a day: the measured total under the measured
    column, and the total under the column of its kind — the columns with manual
    entries of a measured day, the declared of a declared day. The document holds the
    total of no share, so the cells of the shares stay empty."""
    declared = day["state"] == DECLARED_DAY
    row = [label("total", language), "", _duration(day["measured_total"]),
           "" if declared else _duration(day["total"]),
           _duration(day["total"]) if declared else ""]
    return row + [""] * (width - len(row))


def _measures_row(entry: dict, classes: Sequence[str], shares: bool,
                  name: str | None = None) -> list[str]:
    """One row of the measures of the person, of a project, or of a work item of a day:
    the durations as H:MM, the parallel ratio with two decimals — an absent key an empty
    cell, also for a frozen document of an older version —, one cell for each activity
    class that the day shows, and the shares of a project or a work item."""
    row = [] if name is None else [name]
    row += [_duration(entry["human_time"]), _duration(entry["agent_time"]),
            _decimal(entry.get("parallel_ratio")), _duration(entry["blocked_time"])]
    row += [_duration(entry["activity_classes"].get(name)) for name in classes]
    if shares:
        row += [_decimal(entry["inferred_human_share"]),
                _decimal(entry["inferred_agent_share"])]
    return row


def _share_section(day: dict, language: str) -> list[str]:
    """The figure line of the share of human signals from sessions of unknown
    invocation (command-line.md › Reports)."""
    return [f"{label('unknown_invocation_share', language)}  "
            f"{_decimal(day['unknown_invocation_share'])}"]


def _idle_gaps_section(gaps: dict, language: str) -> list[str]:
    """The table of the human time at the idle gaps (command-line.md › Reports), a row
    for each gap in the order of the document. The caller shows the section only when the
    document holds the figure with at least one gap: a measured day without events holds
    its gaps at zero and shows them, and a declared day holds no such figure."""
    return [label("human_time_at_idle_gaps", language),
            *_table(("idle_gap", "human_time"),
                    [(_duration(int(gap)), _duration(seconds))
                     for gap, seconds in gaps.items()], language)]


def _day_title(day: dict, language: str) -> str:
    """The title of the sections of a day: the day and its state (command-line.md ›
    Reports)."""
    return f"{day['day']}  {label(day['state'], language)}"


def _table(columns: Sequence[str], rows: Sequence[Sequence[str]], language: str) -> list[str]:
    """The lines of one table: the labels of the columns as a header, then the rows;
    each column as wide as its widest cell, two spaces between the columns, the first
    column and the columns whose cells hold no number left-aligned, the numbers
    right-aligned, and no space at the end of a line."""
    header = [label(column, language) for column in columns]
    width = [len(cell) for cell in header]
    for row in rows:
        for position, cell in enumerate(row):
            width[position] = max(width[position], len(cell))
    numbers = [bool(rows) and all(_NUMBER.fullmatch(row[position]) for row in rows
                                  if row[position]) for position in range(len(columns))]

    def line(cells: Sequence[str]) -> str:
        """One line of the table: every cell at the width of its column."""
        return "  ".join(cell.rjust(width[position]) if numbers[position] and position
                         else cell.ljust(width[position])
                         for position, cell in enumerate(cells)).rstrip()

    return [line(header), *(line(row) for row in rows)]


def _project_cell(project: dict | None, language: str) -> str:
    """The name that reports show for the project of an entry or of a part, or the
    unattributed time, which has no project (command-line.md › Reports)."""
    return label("unattributed", language) if project is None else project["name"]


def _shown(held: dict | None) -> str:
    """The name that reports show for a work item, or no cell when the entry or the
    part holds none."""
    return "" if held is None else held["name"]


def _duration(seconds: int | None) -> str:
    """A duration as H:MM, or no cell when the document holds none."""
    return "" if seconds is None else format_duration(seconds)


def _decimal(value: float | None) -> str:
    """A share or a ratio with two decimals, or no cell when the document holds none."""
    return "" if value is None else f"{value:.2f}"


def _cell(key: str, value: object) -> str:
    """One cell of the table of the entries: the value as the document holds it, a
    duration of an event as H:MM (command-line.md › Output), and a missing field as no
    cell; a value of more than one part, such as the key that a retraction cancels,
    shows as its JSON text."""
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if key in _DURATION_FIELDS and isinstance(value, int):
        return format_duration(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
