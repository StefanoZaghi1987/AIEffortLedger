"""The report record: the facts with which one report computed its figures, so that two
reports of one period can show what changed between them (architecture.md › Report
record, metrics.md › Reproducibility)."""

from dataclasses import asdict

from ..configuration import IdentityRule, PersonConfiguration, ReportParameters
from ..events import format_instant
from ..selection import Selection


def report_record(
    parameters: ReportParameters,
    person: PersonConfiguration,
    selection: Selection,
    configuration_errors: list[dict],
    ledger: str,
    tzdata: str,
) -> dict:
    """The record of one report (architecture.md › Report record): the versions of the
    ledger and of `tzdata`, the report parameters, the identity rules and the category
    rules, the dated facts, the configuration errors, and the state of the store that it
    read, as the JSON document holds them. The rules hold the values that a rule reads,
    not the line of the file that holds it; the configuration errors are carried as
    produced."""
    return {
        "ledger": ledger,
        "tzdata": tzdata,
        "parameters": asdict(parameters),
        "identity_rules": [_identity_rule(rule) for rule in person.identity_rules],
        "category_rules": [{"tool": rule.tool, "category": rule.category}
                           for rule in person.category_rules],
        "dated_facts": {
            "time_zones": [{"zone": entry.zone, "from": format_instant(entry.start)}
                           for entry in person.time_zones],
            "day_starts": [{"hour": f"{entry.hour:%H:%M}",
                            "from": entry.start.isoformat()}
                           for entry in person.day_starts],
        },
        "configuration_errors": list(configuration_errors),
        "segments": [{"segment": held.segment, "size": held.size,
                      "chained_hash": held.chained_hash} for held in selection.segments],
        "broken_lines": [{"segment": held.segment, "line": held.number}
                         for held in selection.broken],
    }


def _identity_rule(rule: IdentityRule) -> dict:
    """One identity rule as the record holds it: the project that it gives and its
    conditions, with a null for each condition that it does not hold."""
    return {
        "project": rule.project,
        "repository": rule.repository,
        "folder": rule.folder,
        "branch": rule.branch,
        "from": rule.first.isoformat() if rule.first is not None else None,
        "to": rule.last.isoformat() if rule.last is not None else None,
    }
