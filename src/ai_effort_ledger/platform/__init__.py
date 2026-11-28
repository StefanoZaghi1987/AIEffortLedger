"""The folders, the identifiers, the lock, the replace of one file by another, the
scheduler entry, and the time zone that the operating system gives to one machine."""

from .folders import default_store_folder, machine_folder
from .identity import (
    installation_identifier,
    new_salt,
    parse_ioreg,
    salted_hash,
    store_identifier,
)
from .lock import LockUnavailable, StoreLock
from .replacing import replace_file
from .scheduler import (
    ENTRY_NAME,
    SchedulerEntry,
    SchedulerFailed,
    carries_word,
    create_entry,
    entry_definition,
    entry_time,
    remove_entry,
    scheduler_kind,
    show_entry,
)
from .windows_zones import WINDOWS_ZONES
from .zones import (
    registry_time_zone_name,
    system_time_zone,
    windows_zone_to_iana,
    zone_of_localtime_target,
)

__all__ = [
    "ENTRY_NAME",
    "LockUnavailable",
    "SchedulerEntry",
    "SchedulerFailed",
    "StoreLock",
    "WINDOWS_ZONES",
    "carries_word",
    "create_entry",
    "default_store_folder",
    "entry_definition",
    "entry_time",
    "installation_identifier",
    "machine_folder",
    "new_salt",
    "parse_ioreg",
    "registry_time_zone_name",
    "remove_entry",
    "replace_file",
    "salted_hash",
    "scheduler_kind",
    "show_entry",
    "store_identifier",
    "system_time_zone",
    "windows_zone_to_iana",
    "zone_of_localtime_target",
]
