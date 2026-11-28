"""Tests of the days module: the local day of an instant, the parts of a day at changes of
daylight saving, of the day start hour, and on journeys, and the day and instant values of
the command line (metrics.md › Days and weeks, ADR 0022)."""

import unittest
import zoneinfo
from datetime import date, time, timedelta

import support
from ai_effort_ledger import days
from ai_effort_ledger.configuration import DayStartEntry, TimeZoneEntry

# Europe/Rome is UTC+1 in winter and UTC+2 in summer: it springs on the last Sunday of
# March at 01:00 UTC and falls back on the last Sunday of October at 01:00 UTC.
ROME = "Europe/Rome"


def rome_days(day_start: time = time(0, 0)) -> days.LocalDays:
    """The local days of a person in Rome from 1970, with the day start hour given."""
    return days.LocalDays(
        [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2)],
        [DayStartEntry(day_start, date(1970, 1, 1), 3)],
    )


class LocalDayTests(unittest.TestCase):
    """The local day of an instant, and the parts of a day."""

    def test_local_day(self) -> None:
        """The 23:30 UTC of 11-10 is already the 00:30 of 11-11 in Rome."""
        self.assertEqual(rome_days().local_day(support.utc("2026-11-10T23:30")),
                         date(2026, 11, 11))

    def test_day_start_hour(self) -> None:
        """With the day start at 04:00, the local 02:00 of 11-11 (01:00 UTC) is on 11-10."""
        self.assertEqual(rome_days(time(4, 0)).local_day(support.utc("2026-11-11T01:00")),
                         date(2026, 11, 10))

    def test_daylight_saving_days(self) -> None:
        """The day 2026-03-29 lasts 23 hours and the day 2026-10-25 lasts 25 hours; each
        has two parts, split at the change."""
        self.assertEqual(rome_days().day_parts(date(2026, 3, 29)), [
            (support.utc("2026-03-28T23:00"), support.utc("2026-03-29T01:00")),
            (support.utc("2026-03-29T01:00"), support.utc("2026-03-29T22:00")),
        ])
        self.assertEqual(rome_days().day_parts(date(2026, 10, 25)), [
            (support.utc("2026-10-24T22:00"), support.utc("2026-10-25T01:00")),
            (support.utc("2026-10-25T01:00"), support.utc("2026-10-25T23:00")),
        ])

    def test_change_of_day_start(self) -> None:
        """With the day start moving from 00:00 to 04:00 on 2026-12-01, the day 11-30
        lasts 28 hours: it ends at the local 04:00 of 12-01 (03:00 UTC)."""
        person = days.LocalDays(
            [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2)],
            [DayStartEntry(time(0, 0), date(1970, 1, 1), 3),
             DayStartEntry(time(4, 0), date(2026, 12, 1), 5)],
        )
        self.assertEqual(person.day_parts(date(2026, 11, 30)), [
            (support.utc("2026-11-29T23:00"), support.utc("2026-12-01T03:00")),
        ])

    def test_journey_east(self) -> None:
        """A journey to Tokyo on 12-01T00:00Z: the day 12-01 starts at 11-30T23:00Z, has
        one part in Rome and one in Tokyo, and lasts 16 hours."""
        person = days.LocalDays(
            [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2),
             TimeZoneEntry("Asia/Tokyo", support.utc("2026-12-01T00:00"), 4)],
            [DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
        )
        self.assertEqual(person.day_parts(date(2026, 12, 1)), [
            (support.utc("2026-11-30T23:00"), support.utc("2026-12-01T00:00")),
            (support.utc("2026-12-01T00:00"), support.utc("2026-12-01T15:00")),
        ])

    def test_journey_west_gives_two_parts(self) -> None:
        """A journey to New York on 12-01T03:00Z crosses the start of both days: 11-30 has
        a part in Rome and a later part in New York with a gap between them, and so has
        12-01."""
        person = days.LocalDays(
            [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2),
             TimeZoneEntry("America/New_York", support.utc("2026-12-01T03:00"), 4)],
            [DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
        )
        self.assertEqual(person.day_parts(date(2026, 11, 30)), [
            (support.utc("2026-11-29T23:00"), support.utc("2026-11-30T23:00")),
            (support.utc("2026-12-01T03:00"), support.utc("2026-12-01T05:00")),
        ])
        self.assertEqual(person.day_parts(date(2026, 12, 1)), [
            (support.utc("2026-11-30T23:00"), support.utc("2026-12-01T03:00")),
            (support.utc("2026-12-01T05:00"), support.utc("2026-12-02T05:00")),
        ])

    def test_instant_before_history_stops(self) -> None:
        """An instant before the first entry of the history falls in no local day, and the
        stop error names the instant."""
        with self.assertRaises(days.NoLocalDay) as stopped:
            rome_days().local_day(support.utc("1969-12-31T23:00"))
        error = stopped.exception
        self.assertEqual(error.code, "no_local_day")
        self.assertEqual(error.values, {"instant": "1969-12-31T23:00:00Z"})
        self.assertEqual(error.exit_code, 1)

    def test_empty_time_zone_history_stops(self) -> None:
        """Without a time zone in the history, the first local day stops with the stop
        error of the missing time zone."""
        person = days.LocalDays([], [])
        with self.assertRaises(days.NoTimeZone) as stopped:
            person.local_day(support.utc("2026-11-10T23:30"))
        error = stopped.exception
        self.assertEqual(error.code, "time_zone_missing")
        self.assertEqual(error.values, {})
        self.assertEqual(error.exit_code, 1)

    def test_two_entries_with_same_start_stop(self) -> None:
        """Two entries of one list that start at the same value stop the construction with
        the conflict, which names both entries."""
        with self.assertRaises(days.DatedFactConflict) as stopped:
            days.LocalDays(
                [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2)],
                [DayStartEntry(time(0, 0), date(2026, 1, 1), 3),
                 DayStartEntry(time(4, 0), date(2026, 1, 1), 5)],
            )
        error = stopped.exception
        self.assertEqual(error.code, "dated_fact_conflict")
        self.assertEqual(error.values, {
            "first": "day_start 00:00 from 2026-01-01",
            "second": "day_start 04:00 from 2026-01-01",
        })
        self.assertEqual(error.exit_code, 1)
        with self.assertRaises(days.DatedFactConflict) as stopped:
            days.LocalDays(
                [TimeZoneEntry(ROME, support.utc("2026-01-01T00:00"), 2),
                 TimeZoneEntry("Asia/Tokyo", support.utc("2026-01-01T00:00"), 4)],
                [DayStartEntry(time(0, 0), date(1970, 1, 1), 5)],
            )
        self.assertEqual(stopped.exception.values, {
            "first": "time_zone Europe/Rome from 2026-01-01T00:00:00Z",
            "second": "time_zone Asia/Tokyo from 2026-01-01T00:00:00Z",
        })

    def test_repeated_local_time_is_first(self) -> None:
        """The local 02:30 of the autumn change happens twice; the value reads its first
        occurrence, 00:30 UTC."""
        self.assertEqual(rome_days().local_instant("2026-10-25T02:30"),
                         support.utc("2026-10-25T00:30"))

    def test_skipped_local_time_is_after_change(self) -> None:
        """The local 02:30 of the spring change never happens; the value reads the first
        instant after the change, 01:00 UTC."""
        self.assertEqual(rome_days().local_instant("2026-03-29T02:30"),
                         support.utc("2026-03-29T01:00"))

    def test_today_and_yesterday(self) -> None:
        """`today` is the local day of the instant of the command and `yesterday` the day
        before."""
        person = rome_days()
        now = support.utc("2026-11-10T23:30")
        self.assertEqual(person.parse_day("today", now), date(2026, 11, 11))
        self.assertEqual(person.parse_day("yesterday", now), date(2026, 11, 10))

    def test_day_and_instant_values_read_the_forms_alone(self) -> None:
        """Every text of the shared table that no form of its kind holds is a wrong value
        (command-line.md › Form): a compact date, a week date, a space for `T`, the
        seconds of a local time, an offset without the second, and a day where an instant
        is read are all refused. The words of the day of the run stay for `parse_day`."""
        person = rome_days()
        now = support.utc("2026-11-10T12:00")
        for one in support.FORM_TEXTS:
            with self.subTest(text=one.text):
                if one.day or one.text in ("today", "yesterday"):
                    person.parse_day(one.text, now)
                else:
                    with self.assertRaises(ValueError):
                        person.parse_day(one.text, now)
                if one.local_instant or one.offset_instant:
                    person.local_instant(one.text)
                else:
                    with self.assertRaises(ValueError):
                        person.local_instant(one.text)

    def test_tzdata_only(self) -> None:
        """After `use_tzdata_only` the zone path is empty, so only the `tzdata` package
        serves zones, and the version of the package is readable."""
        zoneinfo.reset_tzpath()
        days.use_tzdata_only()
        self.assertEqual(zoneinfo.TZPATH, ())
        self.assertTrue(days.tzdata_version())
        local = support.utc("2026-11-10T23:30").astimezone(zoneinfo.ZoneInfo(ROME))
        self.assertEqual(local.utcoffset(), timedelta(hours=1))
