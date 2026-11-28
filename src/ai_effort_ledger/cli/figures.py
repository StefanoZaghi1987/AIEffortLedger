"""The figures of days: the one pipeline that `timesheet confirm` and every report
command share (command-line.md › Timesheet, architecture.md › Modules). It builds the
parameters of the metrics from the report parameters and the category rules of the
person, then runs `select`, `compute_metrics`, `attribute`, and `day_figures`; `reports`
imports neither `metrics` nor `attribution`, so the pipeline lives here and not in the
reports."""

import argparse
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

from .. import days, reports
from ..attribution import Attribution, attribute, effective_category, project_names
from ..configuration import PersonConfiguration, ReportParameters
from ..declared import DECLARED_DAY, Bucket, DayFigures, day_figures, proposal
from ..events import Event
from ..index import LocalIndex
from ..ingestion import held_back_sessions
from ..ingestion.run import INDEX_FILE
from ..metrics import MetricsParameters, compute_metrics, stream_of
from ..selection import Selection, select
from . import Context, inside_folder, machine_data_folder

__all__ = [
    "Figures",
    "figures_after_confirmation",
    "figures_of_days",
    "metrics_parameters",
    "proposed_values",
    "report_names",
    "report_options",
    "report_warnings",
]

_REPORT_PARAMETERS = ("idle_gap", "minimum_attention", "stale_limit", "headless_prompts",
                      "timesheet_granularity", "language")
"""The report parameters that a command of the figures takes as options, the keys that
`resolve_parameters` reads (command-line.md › Form): the five that change the figures,
and `language`, which the record of the report holds (metrics.md › Reproducibility)."""


class Figures(NamedTuple):
    """The figures of a period of local days: the selection of its events, the
    attribution of the report, and the figures of each of its days, in the order of the
    days (command-line.md › Reports, metrics.md › Declared values)."""

    selection: Selection
    attribution: Attribution
    days: list[DayFigures]


def report_options(options: argparse.Namespace) -> dict[str, object]:
    """The report parameters of a command line, as `resolve_parameters` reads them
    (configuration.md › Order): the value of each parameter that the command line gives,
    and None for the ones that it does not. The words `yes` and `no` that the parser
    holds for `--headless-prompts` become the truth value that the parameter holds.
    `language` is the value of `--language` when the command line gives the option, and
    None when it does not, so that the person configuration or the default gives it, the
    value that `main` resolved into the language of the output."""
    given: dict[str, object] = {}
    for name in _REPORT_PARAMETERS:
        value = getattr(options, name, None)
        if name == "headless_prompts" and value is not None:
            value = value == "yes"
        if name == "language" and not getattr(options, "language_given", False):
            value = None
        given[name] = value
    return given


def metrics_parameters(
    person: PersonConfiguration,
    parameters: ReportParameters,
) -> MetricsParameters:
    """The parameters that the human time and the turns use, built here because
    `configuration` and `attribution` are not below `metrics` (architecture.md ›
    Modules): the durations and the headless prompts of the report parameters, and the
    category that the category rules of the person give to a tool call."""
    return MetricsParameters(
        idle_gap=parameters.idle_gap,
        minimum_attention=parameters.minimum_attention,
        stale_limit=parameters.stale_limit,
        headless_prompts=parameters.headless_prompts,
        category=effective_category(person.category_rules),
    )


def figures_of_days(
    context: Context,
    store_folder: Path,
    person: PersonConfiguration,
    parameters: ReportParameters,
    first: date,
    last: date,
) -> Figures:
    """The figures of the local days from `first` to `last` of the person, through the
    one pipeline of the module: `select` brings the local index up to
    date and reads the events of the period once, `compute_metrics` computes the figures
    of those events once, `attribute` gives every event its bucket once — with the
    confirmations of the selection, that the names of the report need — and `day_figures`
    computes the figures of each day of the period once, on the events of the selection
    in the order of the stream, which the pipeline builds once (metrics.md › Declared
    values, › Human time)."""
    held = metrics_parameters(person, parameters)
    local = days.LocalDays(person.time_zones, person.day_starts)
    inside = inside_folder(context, store_folder)
    inside.mkdir(parents=True, exist_ok=True)
    index = LocalIndex(inside / INDEX_FILE)
    try:
        selection = select(index, store_folder, local, first, last, parameters,
                           held_back_sessions(machine_data_folder(context), store_folder,
                                              context.system))
    finally:
        index.close()
    metrics = compute_metrics(selection.session_events, selection.manual_entries, held)
    attribution = attribute(selection.session_events, selection.annotations,
                            selection.manual_entries, metrics, person, local,
                            selection.confirmations)
    stream = stream_of(selection.session_events)
    computed = [day_figures(one, attribution, stream, selection.confirmations,
                            selection.cancelled, local, held)
                for one in _each_day(first, last)]
    return Figures(selection, attribution, computed)


def report_warnings(
    figures: Figures,
    days: Sequence[DayFigures] | None = None,
) -> list[dict]:
    """The warnings of a report of the figures (command-line.md › Reports): the ones of
    the selection, then the ones of the attribution, then the timesheet warnings of each
    day of the period, in the order of the days. `days` gives figures of days other than
    those of `figures`, for a caller that computed them again after it wrote to the
    store, as `timesheet confirm` does once its confirmation is among the events."""
    held = figures.days if days is None else days
    return [*figures.selection.warnings, *figures.attribution.warnings,
            *(warning for one in held for warning in one.timesheet.warnings)]


def figures_after_confirmation(
    figures: Figures,
    day: date,
    confirmation: Event,
    person: PersonConfiguration,
    parameters: ReportParameters,
) -> DayFigures:
    """The figures of one day again, once a timesheet confirmation is among the events
    of the selection of `figures` (metrics.md › Declared values): the command that wrote
    the confirmation shows and warns about the day as the reports compute it, through
    the same `day_figures` of the pipeline and the attribution that it built, with the
    confirmation added to the confirmations of the selection. No stage reads the store
    again."""
    local = days.LocalDays(person.time_zones, person.day_starts)
    return day_figures(day, figures.attribution,
                       stream_of(figures.selection.session_events),
                       [*figures.selection.confirmations, confirmation],
                       figures.selection.cancelled, local,
                       metrics_parameters(person, parameters))


def proposed_values(day: DayFigures, granularity: int) -> dict[Bucket, int]:
    """The values that a day shows as proposed, in whole seconds (command-line.md ›
    Timesheet; metrics.md › Declared values): the proposal of a measured day, each entry
    the measured human time with manual entries of its bucket rounded up to the timesheet
    granularity; the timesheet entries of a declared day. A bucket without a proposed value
    holds none. `timesheet <day>` shows them, and `timesheet confirm` confirms them when no
    option changes them."""
    sheet = day.timesheet
    if sheet.state == DECLARED_DAY:
        return {line.bucket: line.declared for line in sheet.lines if line.declared}
    return proposal({line.bucket: line.with_manual for line in sheet.lines}, granularity)


def report_names(
    figures: Figures,
    person: PersonConfiguration | None = None,
    confirmations: Sequence[Event] = (),
) -> reports.Names:
    """The names that the documents of the figures show for the projects and the work
    items (ADR 0019): those of the attribution of the figures. `confirmations` gives the
    timesheet confirmations that a command wrote after it computed the figures, as
    `timesheet confirm` does: a project or a work item that only they name takes the name
    that the attribution gives to one of a confirmation — the name of `person`, the
    configuration the figures were computed from, else the default name of a repository
    identity, else the identifier itself — so the document shows the names of the next
    report of the day."""
    attribution = figures.attribution
    projects = dict(attribution.names)
    work_items = dict(attribution.work_item_names)
    entries = [entry for confirmation in confirmations
               for entry in confirmation.get("entries", [])
               if entry.get("project") is not None]
    if person is None or not entries:
        return reports.Names(projects, work_items)
    named = {entry["project"] for entry in entries}
    if not named <= set(projects):
        projects, _errors = project_names(sorted(set(projects) | named),
                                          attribution.repository_hints, person)
    for entry in entries:
        if entry.get("work_item") is not None:
            pair = (entry["project"], entry["work_item"])
            work_items.setdefault(pair, attribution.work_item_name(*pair))
    return reports.Names(projects, work_items)


def _each_day(first: date, last: date) -> list[date]:
    """The local days of a period, in the order of the days (command-line.md › Form):
    a period and every range of days in an option includes both end days."""
    return [first + timedelta(days=one) for one in range((last - first).days + 1)]
