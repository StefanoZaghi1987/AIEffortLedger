"""The local index of a store: an SQLite file of one machine that holds every line of every
segment and the state of each segment.

The index holds one row for each complete line of a segment — the event when the line is one,
the broken and the left-out lines as rows of their own — with the segment and the byte offset
of the line (`architecture.md` › Local index). For each segment it keeps the bytes that it
indexed, the hash of its last indexed line, and the chained hash of its indexed lines, so
an update reads only the new bytes of a segment whose last indexed line is still at the same
place, reads a segment again where it is not, such as after a purge, and removes the events of
a segment that no longer exists. The index is never shared and no result depends on it: a
report with an empty index gives the same figures. Every read gives a copy only when no purge
blocks it (`ingestion.md` › Store), and every query gives one copy for each event key, the
winning one (`event-schema.md` › Keys and invariants).
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from .events import (
    Decoded,
    Event,
    EventKey,
    decode_line,
    event_key,
    event_order,
    format_instant,
    version_key,
    winning_copy,
)
from .store import PurgeSet, SegmentLine, read_lines, segment_names

INDEX_FORMAT = 1
"""The format of the index that this version of the ledger writes."""

_SEGMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS segments (
    name TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    last_offset INTEGER NOT NULL,
    last_hash TEXT NOT NULL,
    chained TEXT NOT NULL
)
"""

_LINES_TABLE = """
CREATE TABLE IF NOT EXISTS lines (
    segment TEXT NOT NULL,
    offset INTEGER NOT NULL,
    number INTEGER NOT NULL,
    state TEXT NOT NULL,
    newer INTEGER NOT NULL,
    key TEXT,
    source TEXT,
    tool TEXT,
    session_id TEXT,
    kind TEXT,
    timestamp TEXT,
    ingested_at TEXT,
    day TEXT,
    "start" TEXT,
    "end" TEXT,
    cwd TEXT,
    event TEXT,
    PRIMARY KEY (segment, offset)
)
"""

_LINES_KIND_INDEX = "CREATE INDEX IF NOT EXISTS lines_kind ON lines(kind)"
_LINES_BROKEN_INDEX = (
    "CREATE INDEX IF NOT EXISTS lines_broken ON lines(segment, number)"
    " WHERE state = 'broken'")
_LINES_NEWER_INDEX = (
    "CREATE INDEX IF NOT EXISTS lines_newer ON lines(newer) WHERE newer = 1")
_LINES_KEY_INDEX = "CREATE INDEX IF NOT EXISTS lines_key ON lines(key)"

_INSERT_SEGMENT = (
    "INSERT OR REPLACE INTO segments (name, size, last_offset, last_hash, chained)"
    " VALUES (?, ?, ?, ?, ?)")
_INSERT_LINE = (
    "INSERT OR IGNORE INTO lines"
    " (segment, offset, number, state, newer, key, source, tool, session_id, kind, timestamp,"
    " ingested_at, day, \"start\", \"end\", cwd, event)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")


class IndexBusy(Exception):
    """The stop error of an index that another connection holds past the limit.

    A stop error carries a code, values, and an exit code; the output language holds the text.
    """

    def __init__(self, path: Path) -> None:
        self.code = "index_busy"
        self.values = {}
        self.exit_code = 1
        super().__init__(str(path))


class SegmentState(NamedTuple):
    """The state that the index keeps of one segment: its name, the number of bytes that it
    indexed, and the chained hash of those lines as lowercase hexadecimal text."""

    segment: str
    size: int
    chained_hash: str


class BrokenLine(NamedTuple):
    """One broken line that the index holds: the name of its segment and its number from 1."""

    segment: str
    number: int


class IndexUpdate(NamedTuple):
    """What one update read: its lines, the broken ones among them, and whether one is of a
    newer schema version. The lines of the updates before it are not named."""

    lines_read: int
    broken: list[BrokenLine]
    newer: bool


def _is_busy(error: sqlite3.OperationalError) -> bool:
    """Whether the error of SQLite says that another connection holds the index."""
    text = str(error).lower()
    return "locked" in text or "busy" in text


def _complete_line(path: Path, offset: int) -> bytes | None:
    """The complete line of the segment at the byte offset, or None when there is none."""
    if not path.is_file():
        return None
    with open(path, "rb") as segment_file:
        segment_file.seek(offset)
        data = segment_file.readline()
    return data if data.endswith(b"\n") else None


def _key_text(key: EventKey) -> str:
    """The event key as the text that the `key` column of the index holds."""
    return json.dumps(key.to_json(), sort_keys=True, separators=(",", ":"))


def _event_text(event: Event) -> str:
    """The event as the JSON text that the `event` column of the index holds."""
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _result_order(event: Event) -> tuple:
    """The order of an event in the results of the queries: by timestamp, then by the key order
    that the tie-breaks use (`event-schema.md` › Keys and invariants)."""
    return (event["timestamp"], event_order(event))


def _winning(
    rows: Iterable[tuple[Event, str]],
    purges: PurgeSet,
) -> tuple[Event, str] | None:
    """The winning copy among the copies that the purges do not block, as an event with the
    name of the segment that holds it, or None when every copy is blocked: the earliest
    `ingested_at`, and, at equal instants, the first segment name (`event-schema.md` › Keys
    and invariants). Every query of the index goes through it, because every read leaves out
    the copies that a purge blocks (`ingestion.md` › Store)."""
    winner: tuple[Event, str] | None = None
    for row in rows:
        if purges.blocks(row[0]):
            continue
        winner = row if winner is None else winning_copy(winner, row)
    return winner


class LocalIndex:
    """The local index of a store at the path of its SQLite file.

    The connection runs in WAL mode and waits at most `limit_seconds` for a write
    (`architecture.md` › Local index); a command that cannot write within the limit stops with
    `IndexBusy`.
    """

    def __init__(self, path: Path, limit_seconds: float = 30.0) -> None:
        self.path = path
        self.limit_seconds = limit_seconds
        self._connection: sqlite3.Connection | None = None

    def update(self, store_folder: Path) -> IndexUpdate:
        """Bring the index up to date with the segments of the store, and give the lines of
        this update: how many lines it read, which of them are broken, and whether one is of a
        newer schema version. The lines of the updates before it are not named."""
        lines_read = 0
        broken: list[BrokenLine] = []
        newer = False
        try:
            connection = self._connect()
            if self._ensure_schema(connection):
                self._wipe(connection)
            stored = {row[0] for row in connection.execute("SELECT name FROM segments")}
            for name in segment_names(store_folder):
                stored.discard(name)
                read = self._update_segment(connection, store_folder, name)
                lines_read += read.lines_read
                broken.extend(read.broken)
                newer = newer or read.newer
            for name in sorted(stored):
                with self._transaction(connection):
                    connection.execute("DELETE FROM lines WHERE segment = ?", (name,))
                    connection.execute("DELETE FROM segments WHERE name = ?", (name,))
        except sqlite3.OperationalError as error:
            if _is_busy(error):
                raise IndexBusy(self.path) from None
            raise
        return IndexUpdate(lines_read, broken, newer)

    def rebuild(self, store_folder: Path) -> None:
        """Build the index again from every segment of the store."""
        try:
            connection = self._connect()
            self._ensure_schema(connection)
            self._wipe(connection)
        except sqlite3.OperationalError as error:
            if _is_busy(error):
                raise IndexBusy(self.path) from None
            raise
        self.update(store_folder)

    def segment_states(self) -> list[SegmentState]:
        """The state that the index keeps of each segment, in the order of their names."""
        connection = self._connect()
        rows = connection.execute("SELECT name, size, chained FROM segments ORDER BY name")
        return [SegmentState(row[0], row[1], row[2]) for row in rows]

    def broken_lines(self) -> list[BrokenLine]:
        """Every broken line that the index holds, also those of an earlier update, in the
        order of their segments and numbers."""
        connection = self._connect()
        rows = connection.execute(
            "SELECT segment, number FROM lines WHERE state = 'broken' ORDER BY segment, number")
        return [BrokenLine(row[0], row[1]) for row in rows]

    def has_newer(self) -> bool:
        """Whether the index holds a line of a newer schema version, also of an earlier
        update."""
        connection = self._connect()
        row = connection.execute("SELECT 1 FROM lines WHERE newer = 1 LIMIT 1").fetchone()
        return row is not None

    def has_key(self, key: EventKey, purges: PurgeSet) -> bool:
        """Whether the index holds a copy of the key that no purge blocks; it is False when
        every copy of the key is blocked."""
        return self._winner_of_key(key, purges) is not None

    def counts(self) -> tuple[int, int]:
        """The numbers that the index holds: its segments and its lines."""
        connection = self._connect()
        segments = connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        lines = connection.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
        return segments, lines

    def close(self) -> None:
        """Close the connection of the index; a read or a write opens it again."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def sessions_between(
        self,
        start: datetime,
        end: datetime,
        *,
        purges: PurgeSet,
        decoded: dict[int, tuple[Event, str]] | None = None,
    ) -> set[tuple[str, str]]:
        """The sessions that hold an event of the period, as `tool` and `session_id`: the
        period holds its start instant and excludes its end instant. `decoded` holds the
        rows that an earlier query of the same index decoded, by their row identifier, so
        that none is decoded twice. The events the query reads are the objects the table
        holds: a caller that keeps the table and changes an event changes what a later
        call gives."""
        sessions: set[tuple[str, str]] = set()
        for event in self._winning_events(
                purges, " AND timestamp >= ? AND timestamp < ?",
                (format_instant(start), format_instant(end)), decoded):
            held = (event.get("tool"), event.get("session_id"))
            if None not in held:
                sessions.add(held)
        return sessions

    def session_events(
        self,
        sessions: Iterable[tuple[str, str]],
        *,
        purges: PurgeSet,
        decoded: dict[int, tuple[Event, str]] | None = None,
    ) -> list[Event]:
        """Every event of the sessions, in the order of their timestamps: an event is of the
        session that its winning copy holds. The query keeps every key that has a copy whose
        `session_id` is the identifier of one of the sessions, whatever its agent tool, because
        one identifier can be held under two tools, and reads the rows of every copy of such
        a key, in chunks by their row identifier when few are wanted,
        or as one read of the table when most are; the winning copy decides whether the
        event is of a session. `decoded` holds the rows that an earlier query of the same
        index decoded, by their row identifier, so that none is decoded twice. The events the
        query returns are the objects the table holds: a caller that keeps the table and
        changes an event changes what a later call gives."""
        wanted = set(sessions)
        if not wanted:
            return []
        connection = self._connect()
        names = {session_id for _, session_id in wanted}
        with self._read_transaction(connection):
            narrow = connection.execute(
                "SELECT rowid, key, session_id FROM lines WHERE state = 'event'").fetchall()
            keys = {key for _rowid, key, session_id in narrow if session_id in names}
            rowids = [rowid for rowid, key, _session_id in narrow if key in keys]
            selections: list[tuple[str, tuple]] | None = None
            if len(rowids) * 3 <= len(narrow):
                selections = [
                    (" AND rowid IN (" + ", ".join("?" * len(piece)) + ")", tuple(piece))
                    for piece in (rowids[first:first + 500]
                                  for first in range(0, len(rowids), 500))]
            given = [event
                     for event in self._winning_events(purges, decoded=decoded,
                                                       selections=selections)
                     if (event.get("tool"), event.get("session_id")) in wanted]
        given.sort(key=_result_order)
        return given

    def sessions_and_events(
        self,
        start: datetime,
        end: datetime,
        *,
        purges: PurgeSet,
    ) -> tuple[set[tuple[str, str]], list[Event]]:
        """The sessions that hold an event of the period and every event of those sessions,
        as `sessions_between` and `session_events` give them, with each row of the index
        decoded at most once: the first query decodes the rows of the period, and the
        second takes them back by their row identifier. Both run in one read transaction,
        because a purge that reads a segment again between the two queries changes the row
        identifiers that the table of the decoded rows is keyed by. The events of the result
        are the objects that table holds."""
        decoded: dict[int, tuple[Event, str]] = {}
        with self._read_transaction(self._connect()):
            sessions = self.sessions_between(start, end, purges=purges, decoded=decoded)
            return sessions, self.session_events(sessions, purges=purges, decoded=decoded)

    def confirmations_of(self, days: Iterable[str], *, purges: PurgeSet) -> list[Event]:
        """The timesheet confirmations whose `day` is one of the days, also the ones a
        retraction names, in the order of their timestamps."""
        wanted = list(days)
        if not wanted:
            return []
        marks = ", ".join("?" * len(wanted))
        given = list(self._winning_events(
            purges, f" AND kind = 'timesheet_confirmation' AND day IN ({marks})", tuple(wanted)))
        given.sort(key=_result_order)
        return given

    def intervals_between(
        self,
        start: datetime,
        end: datetime,
        *,
        purges: PurgeSet,
    ) -> list[Event]:
        """The manual entries and the interval annotations whose interval meets the period, in
        the order of their timestamps: an interval holds its start instant and excludes its end
        instant (`event-schema.md` › Fields)."""
        given = list(self._winning_events(
            purges,
            " AND kind IN ('manual_entry', 'annotation')"
            " AND \"start\" < ? AND \"end\" > ?",
            (format_instant(end), format_instant(start))))
        given.sort(key=_result_order)
        return given

    def bookkeeping(self, *, purges: PurgeSet) -> list[Event]:
        """The retractions, the purges, and the annotations of a session, of any instant, in the
        order of their timestamps."""
        given = [event for event in self._winning_events(
                     purges, " AND kind IN ('retraction', 'purge', 'annotation')")
                 if event["kind"] != "annotation" or "annotates" in event]
        given.sort(key=_result_order)
        return given

    def native_id_owner(
        self,
        source: str,
        native_id: str,
        *,
        purges: PurgeSet,
    ) -> tuple[str, str] | None:
        """The session that holds the key (`source`, `native_id`), as `tool` and `session_id`,
        or None when the index holds no copy of it that the purges leave, or when the winning
        copy holds no session."""
        winner = self._winner_of_key(EventKey(source, native_id=native_id), purges)
        if winner is None:
            return None
        held = (winner.get("tool"), winner.get("session_id"))
        return None if None in held else held

    def ledger_events_between(
        self,
        parts: Sequence[tuple[datetime, datetime]],
        *,
        purges: PurgeSet,
    ) -> list[Event]:
        """The events of the source `ledger` whose `timestamp` is in one of the parts, in the
        order of their timestamps; each part holds its start instant and excludes its end
        instant."""
        clauses: list[str] = []
        parameters: list[str] = []
        for start, end in parts:
            clauses.append("(timestamp >= ? AND timestamp < ?)")
            parameters.extend((format_instant(start), format_instant(end)))
        if not clauses:
            return []
        where = " AND source = 'ledger' AND (" + " OR ".join(clauses) + ")"
        given = list(self._winning_events(purges, where, tuple(parameters)))
        given.sort(key=_result_order)
        return given

    def tools_of_session(self, session_id: str, *, purges: PurgeSet) -> set[str]:
        """The agent tools that hold the session identifier."""
        return {event["tool"] for event in self._winning_events(purges)
                if event.get("session_id") == session_id and "tool" in event}

    def keys_written_below(
        self,
        version: str,
        source: str | None = None,
        *,
        purges: PurgeSet,
    ) -> list[EventKey]:
        """The keys of the events of every kind but `purge` whose winning copy holds a
        `writer_version` under the version, of the source when it is given, in the order of
        their timestamps (`command-line.md` › Purge): a purge never removes a purge event, or
        the keys that the removed purge blocked would come back."""
        limit = version_key(version)
        where = " AND kind != 'purge'" + ("" if source is None else " AND source = ?")
        parameters = () if source is None else (source,)
        winners = [event for event in self._winning_events(purges, where, parameters)
                   if version_key(event["writer_version"]) < limit]
        winners.sort(key=_result_order)
        return [event_key(event) for event in winners]

    def sessions_of_keys(
        self,
        keys: Iterable[EventKey],
        *,
        purges: PurgeSet,
    ) -> set[tuple[str, str]]:
        """The sessions that hold the keys, as `tool` and `session_id`: the sessions that a
        purge with a corrected version names (`ingestion.md` › Store). The keys go into the
        statement in chunks of 500 placeholders, as `session_events` reads its rows in
        chunks, so a purge that names more keys than one statement takes still completes."""
        wanted = [_key_text(key) for key in keys]
        if not wanted:
            return set()
        selections = [
            (" AND key IN (" + ", ".join("?" * len(piece)) + ")", tuple(piece))
            for piece in (wanted[first:first + 500]
                          for first in range(0, len(wanted), 500))]
        sessions: set[tuple[str, str]] = set()
        for event in self._winning_events(purges, selections=selections):
            held = (event.get("tool"), event.get("session_id"))
            if None not in held:
                sessions.add(held)
        return sessions

    def ledger_event_by_uid(self, event_uid: str, *, purges: PurgeSet) -> Event | None:
        """The event of the source `ledger` with the event identifier, or None when the index
        holds no copy of it that the purges leave."""
        return self._winner_of_key(EventKey("ledger", event_uid=event_uid), purges)

    def purge_events(self) -> list[Event]:
        """Every purge of the store, one copy for each key, in the order of their timestamps:
        `PurgeSet.from_events(index.purge_events())` builds the set of purges that the other
        queries of the index take."""
        given = list(self._winning_events(PurgeSet.from_events([]), " AND kind = 'purge'"))
        given.sort(key=_result_order)
        return given

    def _connect(self) -> sqlite3.Connection:
        """The one connection of the index, in WAL mode, waiting at most the limit for a
        write."""
        if self._connection is None:
            try:
                connection = sqlite3.connect(
                    self.path, isolation_level=None, timeout=self.limit_seconds)
                connection.execute("PRAGMA journal_mode=wal")
            except sqlite3.OperationalError as error:
                if _is_busy(error):
                    raise IndexBusy(self.path) from None
                raise
            self._connection = connection
        return self._connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> bool:
        """Create the tables when they are missing, add the indexes of the lines that are
        missing — one on the kind, two partial ones, on the broken lines and on the lines of
        a newer schema version, and one on the key of every row — and give whether the
        stored format is another one, so that the caller builds the index again. A file that
        an earlier version wrote gains the indexes here, without a build again: an index
        holds no row, and the format describes the tables and their rows."""
        connection.execute("CREATE TABLE IF NOT EXISTS meta (format INTEGER NOT NULL)")
        connection.execute(_SEGMENTS_TABLE)
        connection.execute(_LINES_TABLE)
        connection.execute(_LINES_KIND_INDEX)
        connection.execute(_LINES_BROKEN_INDEX)
        connection.execute(_LINES_NEWER_INDEX)
        connection.execute(_LINES_KEY_INDEX)
        row = connection.execute("SELECT format FROM meta").fetchone()
        if row is None:
            connection.execute("INSERT INTO meta (format) VALUES (?)", (INDEX_FORMAT,))
            return False
        return row[0] != INDEX_FORMAT

    def _winner_of_key(self, key: EventKey, purges: PurgeSet) -> Event | None:
        """The winning copy of the key among the copies that the purges do not block, as its
        event, or None when the index holds no copy of the key or every copy is blocked."""
        rows = self._connect().execute(
            "SELECT segment, event FROM lines WHERE state = 'event' AND key = ?",
            (_key_text(key),))
        winner = _winning(((json.loads(event), segment) for segment, event in rows), purges)
        return None if winner is None else winner[0]

    def _winning_events(
        self,
        purges: PurgeSet,
        where: str = "",
        parameters: tuple[str, ...] = (),
        decoded: dict[int, tuple[Event, str]] | None = None,
        selections: list[tuple[str, tuple]] | None = None,
    ) -> Iterator[Event]:
        """For each key among the rows that the where clause selects, the winning copy that the
        purges do not block, as its event. The clause selects only what is the same in every
        copy of a key, such as the kind or the timestamp; what the winning copy alone decides,
        such as its session, the caller reads from the events. `decoded` holds the rows that
        an earlier query of the same index decoded, by their row identifier; `selections`
        gives several clauses and their parameters in the place of the one clause, such as
        the row identifiers of the wanted rows, in chunks that hold few parameters."""
        copies: dict[str, list[tuple[Event, str]]] = {}
        for clause, values in ([(where, parameters)] if selections is None else selections):
            rows = self._connect().execute(
                "SELECT rowid, key, segment, event FROM lines WHERE state = 'event'" + clause,
                values)
            for rowid, key, segment, event in rows:
                held = None if decoded is None else decoded.get(rowid)
                if held is None:
                    held = (json.loads(event), segment)
                    if decoded is not None:
                        decoded[rowid] = held
                copies.setdefault(key, []).append(held)
        for group in copies.values():
            winner = _winning(group, purges)
            if winner is not None:
                yield winner[0]

    def _wipe(self, connection: sqlite3.Connection) -> None:
        """Remove every line, every segment state, and the stored format, so that the caller
        builds the index again."""
        with self._transaction(connection):
            connection.execute("DELETE FROM lines")
            connection.execute("DELETE FROM segments")
            connection.execute("DELETE FROM meta")
            connection.execute("INSERT INTO meta (format) VALUES (?)", (INDEX_FORMAT,))

    @contextmanager
    def _transaction(self, connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        """One write transaction, which begins before the caller reads the stored state, so
        that two updates of the same index add each line once and a later commit never writes
        an older size or chained hash."""
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    @contextmanager
    def _read_transaction(self, connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        """One read transaction around the statements of a caller that reads the rows of
        more than one query against one another: in WAL mode it is a snapshot that no
        writer waits for, and inside it the row identifiers of the rows cannot change, as
        they do when a purge reads a segment again and the index holds its lines again. A
        caller that is inside a transaction already runs its statements in it."""
        if connection.in_transaction:
            yield connection
            return
        connection.execute("BEGIN")
        try:
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def _update_segment(
        self,
        connection: sqlite3.Connection,
        store_folder: Path,
        name: str,
    ) -> IndexUpdate:
        """Bring one segment up to date in one transaction, which begins before the stored
        state of the segment is read. A segment whose last indexed line is still at its place
        gives only the lines after it; the index reads a segment again where it is not and
        removes the lines that it held of it."""
        lines_read = 0
        broken: list[BrokenLine] = []
        newer = False
        with self._transaction(connection):
            row = connection.execute(
                "SELECT size, last_offset, last_hash, chained FROM segments WHERE name = ?",
                (name,)).fetchone()
            last_number = connection.execute(
                "SELECT MAX(number) FROM lines WHERE segment = ?", (name,)).fetchone()[0]
            held = _complete_line(store_folder / name, row[1]) if row is not None else None
            resumes = (row is not None and held is not None
                       and hashlib.sha256(held).hexdigest() == row[2])
            if resumes:
                chained = bytes.fromhex(row[3])
                offset = row[1] + len(held)
                size = row[0]
                last_offset = row[1]
                last_hash = row[2]
                first_number = 1 if last_number is None else last_number + 1
            else:
                chained = hashlib.sha256(b"").digest()
                offset = 0
                size = 0
                last_offset = 0
                last_hash = ""
                first_number = 1
                connection.execute("DELETE FROM lines WHERE segment = ?", (name,))
            for line in read_lines(store_folder, name, offset=offset, first_number=first_number):
                decoded = decode_line(line.data)
                connection.execute(_INSERT_LINE, self._row(name, line, decoded))
                chained = hashlib.sha256(chained + line.data).digest()
                last_offset = line.offset
                last_hash = hashlib.sha256(line.data).hexdigest()
                size = line.offset + len(line.data)
                lines_read += 1
                newer = newer or decoded.newer
                if decoded.state == "broken":
                    broken.append(BrokenLine(name, line.number))
            connection.execute(
                _INSERT_SEGMENT, (name, size, last_offset, last_hash, chained.hex()))
        return IndexUpdate(lines_read, broken, newer)

    def _row(self, segment: str, line: SegmentLine, decoded: Decoded) -> tuple:
        """The values of one line for the `lines` table: an event with its fields, a broken or
        left-out line with none of them."""
        if decoded.state != "event":
            return (segment, line.offset, line.number, decoded.state, decoded.newer,
                    None, None, None, None, None, None, None, None, None, None, None, None)
        event = decoded.event
        return (
            segment, line.offset, line.number, decoded.state, decoded.newer,
            _key_text(event_key(event)), event["source"], event.get("tool"),
            event.get("session_id"), event["kind"], event["timestamp"], event["ingested_at"],
            event.get("day"), event.get("start"), event.get("end"), event.get("cwd"),
            _event_text(event))
