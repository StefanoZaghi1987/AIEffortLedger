"""The forms of the dated values that a person gives as text, one definition of each,
read by every reader of such a text (command-line.md › Form).

A form is what the document says, and nothing else: a day is `YYYY-MM-DD`; an instant is
a local time `YYYY-MM-DDTHH:MM` or an RFC 3339 instant with an offset or `Z`; an hour is
`HH:MM`, two digits each. A day or instant definition also checks the calendar, so a
text of the right shape whose day or time cannot exist, such as `2026-02-30`, is of no
form; the hour needs no such check, its shape bounds the hour and the minute. What
`fromisoformat` accepts beyond these — a compact date, a week date, a space for `T`, the
seconds of a local time — follows the version of the interpreter and of no document, so
no reader takes its verdict on a person's text.
"""

import re
from datetime import date, datetime

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_LOCAL_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_OFFSET_INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
_HOUR = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


def is_day(text: str) -> bool:
    """Whether the text is a local day of the form `YYYY-MM-DD`, of a day that exists."""
    if _DAY.fullmatch(text) is None:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_local_instant(text: str) -> bool:
    """Whether the text is a local time of the person, of the form `YYYY-MM-DDTHH:MM`,
    of a day and a time that exist."""
    if _LOCAL_INSTANT.fullmatch(text) is None:
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_offset_instant(text: str) -> bool:
    """Whether the text is an RFC 3339 instant with an offset or `Z`: the date, `T`, the
    hour, the minute, the second, an optional fraction, and the offset."""
    if _OFFSET_INSTANT.fullmatch(text) is None:
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_hour(text: str) -> bool:
    """Whether the text is an hour of the form `HH:MM`, two digits for the hour and two
    for the minute."""
    return _HOUR.fullmatch(text) is not None
