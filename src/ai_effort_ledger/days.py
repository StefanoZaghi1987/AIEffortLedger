"""The local days of a person: the local day of an instant, the parts of a day, and the
day and instant values of the command line (metrics.md › Days and weeks, ADR 0022).

Data stays in UTC; a local day exists only through the dated facts of the person: the
time-zone history and the day start hours (configuration.md › Format). The ledger reads
time zones only from the `tzdata` package, on every operating system (ADR 0022); the
command calls `use_tzdata_only` before it reads one.
"""

import tzdata
import zoneinfo
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from operator import attrgetter
from zoneinfo import ZoneInfo

from .configuration import (
    DayStartEntry,
    TimeZoneEntry,
    is_day,
    is_local_instant,
    is_offset_instant,
)

_UTC = timezone.utc
_ONE_DAY = timedelta(days=1)
_ONE_HOUR = timedelta(hours=1)
_ONE_SECOND = timedelta(seconds=1)
# The instants of a day lie within about half a day of UTC from its wall-clock bounds;
# the search around the bounds takes two full days of margin, so that every instant of
# the day is inside whatever offset the zones hold.
_MARGIN = timedelta(days=2)


class NoLocalDay(Exception):
    """The stop error of an instant that falls in no local day.

    A stop error carries a code, values, and an exit code; the output language holds the
    text. An instant before the first entry of the time-zone history or of the day start
    hours falls in no local day (configuration.md › Format, ADR 0022).
    """

    def __init__(self, instant: datetime) -> None:
        self.code = "no_local_day"
        self.values = {"instant": _instant_text(instant)}
        self.exit_code = 1
        super().__init__(_instant_text(instant))


class DatedFactConflict(Exception):
    """The stop error of two dated facts of one list that start at the same value.

    The two entries leave instants without a local day, so every command that needs
    local days stops (configuration.md › Format).
    """

    def __init__(self, first: str, second: str) -> None:
        self.code = "dated_fact_conflict"
        self.values = {"first": first, "second": second}
        self.exit_code = 1
        super().__init__(f"{first}, {second}")


class NoTimeZone(Exception):
    """The stop error of a person whose time-zone history is empty."""

    def __init__(self) -> None:
        self.code = "time_zone_missing"
        self.values: dict[str, object] = {}
        self.exit_code = 1
        super().__init__("time_zone_missing")


def use_tzdata_only() -> None:
    """Serve time zones only from the `tzdata` package, never from the machine (ADR 0022)."""
    zoneinfo.reset_tzpath(to=[])
    zoneinfo.ZoneInfo.clear_cache()


def tzdata_version() -> str:
    """The version of the `tzdata` package; every report records it."""
    return tzdata.__version__


class LocalDays:
    """The local days of a person, from the time-zone history and the day start hours.

    The histories are dated facts: each entry is valid from its start to the start of the
    next entry of the same list, and never before its own start (configuration.md ›
    Format). Two entries of one list that share their start stop the construction with
    `DatedFactConflict`; an empty time-zone history stops the first use with `NoTimeZone`.
    """

    def __init__(
        self,
        time_zones: Sequence[TimeZoneEntry],
        day_starts: Sequence[DayStartEntry],
    ) -> None:
        self._time_zones = sorted(time_zones, key=attrgetter("start"))
        self._day_starts = sorted(day_starts, key=attrgetter("start"))
        self._zones = {entry.zone: ZoneInfo(entry.zone) for entry in self._time_zones}
        self._stop_conflict()

    def local_day(self, instant: datetime) -> date:
        """The local day of the instant: the date whose day start hour the local time of
        the instant reaches, or the date before when it does not (metrics.md › Days and
        weeks)."""
        local = instant.astimezone(self._zone_at(instant))
        day = local.date()
        hour = self._hour_at(day)
        if hour is None:
            raise NoLocalDay(instant)
        if local.time() < hour:
            if self._hour_at(day - _ONE_DAY) is None:
                raise NoLocalDay(instant)
            day -= _ONE_DAY
        return day

    def day_parts(self, day: date) -> list[tuple[datetime, datetime]]:
        """The parts of the local day, as UTC intervals with the start included and the
        end excluded (metrics.md › Days and weeks).

        Each part lies between two changes of the offset: a change of daylight saving
        inside the day splits it, and a journey splits it where the zone history changes,
        so a journey to the west that crosses the start of the day gives two parts with a
        gap between them.
        """
        if not self._time_zones:
            raise NoTimeZone()
        hour = self._hour_at(day)
        if hour is None:
            raise NoLocalDay(_nominal(day))
        wall_start = datetime.combine(day, hour)
        wall_end = datetime.combine(day + _ONE_DAY, self._hour_at(day + _ONE_DAY))
        parts: list[tuple[datetime, datetime]] = []
        for entry, start, end in self._segments():
            zone = self._zones[entry.zone]
            window_start = max(start, _estimate(wall_start) - _MARGIN)
            window_end = _estimate(wall_end) + _MARGIN
            if end is not None and window_end > end:
                window_end = end
            if window_start >= window_end:
                continue
            for run_start, run_end, offset in _runs(zone, window_start, window_end):
                begin = max(run_start, _absolute(wall_start, offset))
                finish = min(run_end, _absolute(wall_end, offset))
                if begin < finish:
                    parts.append((begin, finish))
        if not parts:
            raise NoLocalDay(_nominal(day))
        return parts

    def local_instant(self, text: str) -> datetime:
        """The instant of an instant value of the command line (command-line.md › Form):
        a local time `YYYY-MM-DDTHH:MM` or an RFC 3339 instant with an offset or `Z`, and
        no other text.

        An RFC 3339 instant stays as it is, in UTC. A local time is the first instant
        whose local time reaches it in the zone that is valid there: a change of daylight
        saving that repeats it gives its first occurrence, and a change that skips it
        gives the change itself (metrics.md › Days and weeks).
        """
        if not (is_local_instant(text) or is_offset_instant(text)):
            raise ValueError(f"{text!r} is not an instant")
        moment = datetime.fromisoformat(text)
        if moment.tzinfo is not None:
            return moment.astimezone(_UTC)
        if not self._time_zones:
            raise NoTimeZone()
        for entry, start, end in self._segments():
            zone = self._zones[entry.zone]
            if _local_time(start, zone) >= moment:
                return start
            candidate = _resolve(zone, moment)
            if start <= candidate and (end is None or candidate < end):
                return candidate
        raise NoLocalDay(moment.replace(tzinfo=_UTC))

    def parse_day(self, text: str, now: datetime) -> date:
        """The day of a day value of the command line (command-line.md › Form): a date
        `YYYY-MM-DD`, or `today` or `yesterday`, a local day of the person; a text of
        no other form raises ValueError."""
        if text == "today":
            return self.local_day(now)
        if text == "yesterday":
            return self.local_day(now) - _ONE_DAY
        if not is_day(text):
            raise ValueError(f"{text!r} is not a day")
        return date.fromisoformat(text)

    def _stop_conflict(self) -> None:
        """Stop at the first two entries of one list that share their start."""
        histories = (
            (self._time_zones, _describe_time_zone),
            (self._day_starts, _describe_day_start),
        )
        for entries, describe in histories:
            for earlier, later in zip(entries, entries[1:]):
                if earlier.start == later.start:
                    raise DatedFactConflict(describe(earlier), describe(later))

    def _zone_at(self, instant: datetime) -> ZoneInfo:
        """The time zone of the history that is valid at the instant."""
        return self._zones[self._time_zone_entry_at(instant).zone]

    def _time_zone_entry_at(self, instant: datetime) -> TimeZoneEntry:
        """The entry of the time-zone history that is valid at the instant."""
        if not self._time_zones:
            raise NoTimeZone()
        found = None
        for entry in self._time_zones:
            if entry.start > instant:
                break
            found = entry
        if found is None:
            raise NoLocalDay(instant)
        return found

    def _hour_at(self, day: date) -> time | None:
        """The day start hour valid on the date, or None before the first entry."""
        found = None
        for entry in self._day_starts:
            if entry.start > day:
                break
            found = entry.hour
        return found

    def _segments(self) -> list[tuple[TimeZoneEntry, datetime, datetime | None]]:
        """The spans of the time-zone history: each zone from its start to the start of
        the next one, the last open-ended."""
        spans = []
        for position, entry in enumerate(self._time_zones):
            end = None
            if position + 1 < len(self._time_zones):
                end = self._time_zones[position + 1].start
            spans.append((entry, entry.start, end))
        return spans


def _runs(
    zone: ZoneInfo,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime, timedelta]]:
    """The runs of constant offset of the zone inside the interval, each from its first
    instant to the first instant of the next offset.

    The walk probes the offset every hour and, at a change, finds the exact instant by
    halving; tzdata changes offsets at whole seconds, and two changes never fall within
    one hour of each other in its data.
    """
    runs = []
    run_start = start
    offset = _offset(zone, start)
    moment = start
    while moment < end:
        step = min(moment + _ONE_HOUR, end)
        step_offset = _offset(zone, step)
        if step_offset != offset:
            change = _change_instant(zone, moment, step, step_offset)
            runs.append((run_start, change, offset))
            run_start = change
            offset = step_offset
        moment = step
    runs.append((run_start, end, offset))
    return runs


def _change_instant(
    zone: ZoneInfo,
    before: datetime,
    after: datetime,
    target: timedelta,
) -> datetime:
    """The first instant of the interval whose offset is the target, when the offsets at
    the two ends differ."""
    while after - before > _ONE_SECOND:
        middle = before + (after - before) / 2
        if _offset(zone, middle) == target:
            after = middle
        else:
            before = middle
    return after


def _resolve(zone: ZoneInfo, wall: datetime) -> datetime:
    """The first instant whose local time in the zone reaches the wall time: the first
    occurrence when a change of daylight saving repeats it, and the change itself when
    the change skips it (metrics.md › Days and weeks)."""
    early = wall.replace(tzinfo=zone, fold=0).astimezone(_UTC)
    late = wall.replace(tzinfo=zone, fold=1).astimezone(_UTC)
    if early <= late:
        return early
    return _change_instant(zone, late, early, _offset(zone, early))


def _offset(zone: ZoneInfo, moment: datetime) -> timedelta:
    """The offset of the zone at the instant."""
    return moment.astimezone(zone).utcoffset()


def _local_time(moment: datetime, zone: ZoneInfo) -> datetime:
    """The naive local time of the instant in the zone."""
    return moment.astimezone(zone).replace(tzinfo=None)


def _absolute(wall: datetime, offset: timedelta) -> datetime:
    """The instant of a wall time under a constant offset, as UTC."""
    return (wall - offset).replace(tzinfo=_UTC)


def _estimate(wall: datetime) -> datetime:
    """The instant of a wall time read as if the offset were zero, an estimate that only
    bounds where the day can lie."""
    return wall.replace(tzinfo=_UTC)


def _instant_text(instant: datetime) -> str:
    """The instant as RFC 3339 in UTC, with `Z` for the offset (command-line.md › Form)."""
    return instant.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _nominal(day: date) -> datetime:
    """The midnight of a day as UTC, the instant that a stop error names when the day has
    no part and no instant of its own."""
    return datetime.combine(day, time(0, 0), tzinfo=_UTC)


def _describe_time_zone(entry: TimeZoneEntry) -> str:
    """The text that names one entry of the time-zone history."""
    return f"time_zone {entry.zone} from {_instant_text(entry.start)}"


def _describe_day_start(entry: DayStartEntry) -> str:
    """The text that names one entry of the day start hours."""
    return f"day_start {entry.hour.strftime('%H:%M')} from {entry.start.isoformat()}"
