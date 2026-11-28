"""The configuration of the machine and of the person: the reading and the writing of the
files that hold them, the values and the rules they give, and the report parameters
(configuration.md, ADR 0017)."""

from .forms import (
    is_day,
    is_hour,
    is_local_instant,
    is_offset_instant,
)
from .machine import (
    MachineConfiguration,
    read_machine_configuration,
    refresh_machine,
    write_machine_configuration,
)
from .person import (
    CategoryRule,
    DayStartEntry,
    IdentityRule,
    PersonConfiguration,
    ProjectName,
    TimeZoneEntry,
    WorkItemName,
    read_person_configuration,
    resolve_parameters,
)
from .values import (
    ConfigurationUnreadable,
    ReportParameters,
    SetupRequired,
    parse_duration,
    pattern_matches,
)
from .writes import (
    ENTRY_KEYS,
    WrongValue,
    append_entry,
    basic_string,
    create_person_configuration,
)

__all__ = [
    "CategoryRule",
    "ConfigurationUnreadable",
    "DayStartEntry",
    "ENTRY_KEYS",
    "IdentityRule",
    "MachineConfiguration",
    "PersonConfiguration",
    "ProjectName",
    "ReportParameters",
    "SetupRequired",
    "TimeZoneEntry",
    "WorkItemName",
    "WrongValue",
    "append_entry",
    "basic_string",
    "create_person_configuration",
    "is_day",
    "is_hour",
    "is_local_instant",
    "is_offset_instant",
    "parse_duration",
    "pattern_matches",
    "read_machine_configuration",
    "read_person_configuration",
    "refresh_machine",
    "resolve_parameters",
    "write_machine_configuration",
]
