"""Tests of the platform module: folders, identifiers, salt, the lock of a store, and the
entry of the scheduled ingestion."""

import hashlib
import plistlib
import shlex
import struct
import subprocess
import sys
import time
import unittest
import zoneinfo
from pathlib import Path, PurePosixPath, PureWindowsPath
from platform import system as running_system

import support
from ai_effort_ledger import platform

_POLL_SECONDS = 15.0

# A second process that takes the lock of the file at argv[1], holds it for argv[2] seconds,
# and gives the verdict through its exit code: 0 when it took the lock, 3 when it did not
# within argv[3] tries, one try every 0.05 seconds.
_HOLDER_SOURCE = '''\
import os
import sys
import time

if sys.platform == "win32":
    import msvcrt

    def take(descriptor):
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

    def free(descriptor):
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def take(descriptor):
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def free(descriptor):
        fcntl.flock(descriptor, fcntl.LOCK_UN)

descriptor = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT)
for _ in range(int(sys.argv[3])):
    try:
        take(descriptor)
        break
    except OSError:
        time.sleep(0.05)
else:
    raise SystemExit(3)
time.sleep(float(sys.argv[2]))
free(descriptor)
'''


def _holder_process(lock_path: Path, hold_seconds: float, tries: int = 200) -> subprocess.Popen:
    """Start the second process that takes the lock of the path and holds it."""
    return subprocess.Popen(
        [
            sys.executable, "-I", "-c", _HOLDER_SOURCE,
            str(lock_path), str(hold_seconds), str(tries)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)


def _checker_exit(lock_path: Path, tries: int) -> int:
    """Let a second process try the lock and return its exit code: 0 taken, 3 not taken."""
    done = subprocess.run(
        [sys.executable, "-I", "-c", _HOLDER_SOURCE, str(lock_path), "0", str(tries)],
        check=False)
    return done.returncode


def _wait_until_held(lock_path: Path, deadline: float) -> None:
    """Poll by trying to take the lock until a second process holds it."""
    while time.monotonic() < deadline:
        try:
            with platform.StoreLock(lock_path, limit_seconds=0.1):
                pass
        except platform.LockUnavailable:
            return
    raise AssertionError("no second process took the lock within the deadline")


def _wait_until_free(lock_path: Path, deadline: float) -> None:
    """Poll by taking the lock until the operating system gives it back."""
    while time.monotonic() < deadline:
        try:
            with platform.StoreLock(lock_path, limit_seconds=0.1):
                return
        except platform.LockUnavailable:
            pass
    raise AssertionError("the lock never came free within the deadline")


class TestPlatform(unittest.TestCase):
    """The folders and the identifiers of the platform module follow the specification."""

    def test_folders_windows(self) -> None:
        environ = {"LOCALAPPDATA": r"C:\L"}
        home = Path(r"D:\Work\Product")
        self.assertEqual(
            platform.machine_folder("Windows", environ, home),
            PureWindowsPath(r"C:\L\ai-effort-ledger\machine"))
        self.assertEqual(
            platform.default_store_folder("Windows", environ, home),
            PureWindowsPath(r"C:\L\ai-effort-ledger\store"))

    def test_folders_linux_defaults(self) -> None:
        home = Path("/home/person")
        self.assertEqual(
            platform.machine_folder("Linux", {}, home),
            PurePosixPath("/home/person/.local/state/ai-effort-ledger/machine"))
        self.assertEqual(
            platform.default_store_folder("Linux", {}, home),
            PurePosixPath("/home/person/.local/share/ai-effort-ledger/store"))

    def test_folders_linux_xdg(self) -> None:
        home = Path("/home/person")
        environ = {"XDG_STATE_HOME": "/state", "XDG_DATA_HOME": "/data"}
        self.assertEqual(
            platform.machine_folder("Linux", environ, home),
            PurePosixPath("/state/ai-effort-ledger/machine"))
        self.assertEqual(
            platform.default_store_folder("Linux", environ, home),
            PurePosixPath("/data/ai-effort-ledger/store"))

    def test_folders_macos(self) -> None:
        home = Path("/home/person")
        self.assertEqual(
            platform.machine_folder("Darwin", {}, home),
            PurePosixPath("/home/person/Library/Application Support/ai-effort-ledger/machine"))
        self.assertEqual(
            platform.default_store_folder("Darwin", {}, home),
            PurePosixPath("/home/person/Library/Application Support/ai-effort-ledger/store"))

    def test_folders_are_pure_paths_of_the_system(self) -> None:
        environ = {"LOCALAPPDATA": r"C:\L"}
        windows = platform.machine_folder("Windows", environ, Path(r"D:\Work\Product"))
        self.assertIsInstance(windows, PureWindowsPath)
        self.assertNotIsInstance(windows, Path)
        posix = platform.machine_folder("Linux", {}, Path("/home/person"))
        self.assertIsInstance(posix, PurePosixPath)
        self.assertNotIsInstance(posix, Path)

    def test_store_identifier_windows_ignores_case(self) -> None:
        self.assertEqual(
            platform.store_identifier(Path(r"D:\Work\Store"), "Windows"),
            platform.store_identifier(Path(r"d:\work\store"), "Windows"))

    def test_store_identifier_is_16_hex(self) -> None:
        with support.TemporaryFolder() as folder:
            identifier = platform.store_identifier(folder, "Windows")
        self.assertEqual(len(identifier), 16)
        self.assertRegex(identifier, r"^[0-9a-f]{16}$")

    def test_parse_ioreg(self) -> None:
        text = (
            "+-o Device {\n"
            '  "IOPlatformSerialNumber" = "TEST0000"\n'
            '  "IOPlatformUUID" = "0000-TEST"\n'
            "}\n")
        self.assertEqual(platform.parse_ioreg(text), "0000-TEST")
        self.assertIsNone(platform.parse_ioreg('  "Other" = "value"\n'))

    def test_installation_identifier_of_a_system_that_is_not_running(self) -> None:
        running = running_system()
        for name in ("Windows", "Linux", "Darwin"):
            if name == running:
                continue
            identifier = platform.installation_identifier(name)
            self.assertTrue(identifier is None or isinstance(identifier, str))

    def test_new_salt_is_32_hex(self) -> None:
        salt = platform.new_salt()
        self.assertEqual(len(salt), 32)
        self.assertRegex(salt, r"^[0-9a-f]{32}$")

    def test_salted_hash_depends_on_salt(self) -> None:
        first = platform.salted_hash("0000-TEST", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        second = platform.salted_hash("0000-TEST", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertNotEqual(first, second)

    def test_salted_hash_is_the_spec_digest(self) -> None:
        salt = "0123456789abcdef0123456789abcdef"
        expected = "47016d3e9dc0f0cff11d9f0bc499a1bcef528fc95cb1f190925090a061707417"
        self.assertEqual(platform.salted_hash("0000-TEST", salt), expected)
        self.assertRegex(platform.salted_hash("0000-TEST", salt), r"^[0-9a-f]{64}$")


def _no_registry() -> str | None:
    """The fake answer of the registry of Windows: it gives no name."""
    return None


class TestTimeZones(unittest.TestCase):
    """The time zone of the operating system and the Windows names follow the specification."""

    def test_windows_name_converts(self) -> None:
        self.assertEqual(
            platform.windows_zone_to_iana("W. Europe Standard Time"), "Europe/Berlin")

    def test_unknown_windows_name(self) -> None:
        # The ledger never guesses a time zone: an unknown name gives None.
        self.assertIsNone(platform.windows_zone_to_iana("Invented Standard Time"))

    def test_linux_localtime_link(self) -> None:
        with support.TemporaryFolder() as folder:
            link = folder / "localtime"
            try:
                link.symlink_to(folder / "zoneinfo" / "Europe" / "Rome", target_is_directory=True)
            except OSError:
                self.skipTest("the system does not allow symbolic links")
            self.assertEqual(
                platform.system_time_zone("Linux", {}, link, _no_registry), "Europe/Rome")
            # An empty TZ variable falls to the link.
            self.assertEqual(
                platform.system_time_zone("Linux", {"TZ": ""}, link, _no_registry),
                "Europe/Rome")

    def test_tz_variable_wins(self) -> None:
        localtime = Path("/etc/localtime")
        for zone in (":Europe/Rome", "Europe/Rome"):
            self.assertEqual(
                platform.system_time_zone("Linux", {"TZ": zone}, localtime, _no_registry),
                "Europe/Rome")
        self.assertEqual(
            platform.system_time_zone("Darwin", {"TZ": ":Europe/Rome"}, localtime, _no_registry),
            "Europe/Rome")

    def test_tz_variable_of_another_shape_gives_none(self) -> None:
        # A `TZ` that holds a POSIX TZ string, or a path, names no zone that `tzdata`
        # holds: no time zone, as an unknown Windows name (configuration.md › Writes).
        localtime = Path("/etc/localtime")
        for given in ("CET-1CEST", "UTC0", ":CET-1CEST", "/usr/share/zoneinfo/Europe/Rome"):
            self.assertIsNone(
                platform.system_time_zone("Linux", {"TZ": given}, localtime, _no_registry),
                given)
        with support.TemporaryFolder() as folder:
            link = folder / "localtime"
            try:
                link.symlink_to(folder / "zoneinfo" / "Europe" / "Rome", target_is_directory=True)
            except OSError:
                self.skipTest("the system does not allow symbolic links")
            # The link is not consulted: the variable named a zone, and the ledger never
            # guesses one beside it.
            self.assertIsNone(
                platform.system_time_zone("Linux", {"TZ": "CET-1CEST"}, link, _no_registry))

    def test_localtime_target_zones(self) -> None:
        # The zone of a link target, checked without a symbolic link, on every system.
        self.assertEqual(
            platform.zone_of_localtime_target("/usr/share/zoneinfo/Europe/Rome"), "Europe/Rome")
        self.assertIsNone(platform.zone_of_localtime_target("/var/db/time/other/Rome"))

    def test_windows_registry_gives_none(self) -> None:
        # A registry that gives no name gives no time zone, also through the conversion.
        self.assertIsNone(
            platform.system_time_zone("Windows", {}, Path(r"C:\Windows"), _no_registry))

    def test_table_is_the_faithful_cut(self) -> None:
        self.assertEqual(len(platform.WINDOWS_ZONES), 142)
        self.assertEqual(platform.WINDOWS_ZONES["FLE Standard Time"], "Europe/Kiev")
        self.assertEqual(platform.WINDOWS_ZONES["India Standard Time"], "Asia/Calcutta")
        self.assertEqual(platform.WINDOWS_ZONES["Nepal Standard Time"], "Asia/Katmandu")
        self.assertEqual(platform.WINDOWS_ZONES["Myanmar Standard Time"], "Asia/Rangoon")

    def test_every_value_is_in_tzdata(self) -> None:
        zoneinfo.reset_tzpath(to=[])
        zoneinfo.ZoneInfo.clear_cache()
        for zone in platform.WINDOWS_ZONES.values():
            zoneinfo.ZoneInfo(zone)


class TestStoreLock(unittest.TestCase):
    """The lock of a store: a second process holds it, one process counts its nested takes."""

    def test_second_holder_waits_then_stops(self) -> None:
        with support.TemporaryFolder() as folder:
            lock_path = folder / "lock"
            holder = _holder_process(lock_path, 60.0)
            try:
                _wait_until_held(lock_path, time.monotonic() + _POLL_SECONDS)
                lock = platform.StoreLock(lock_path, limit_seconds=1.0)
                start = time.monotonic()
                with self.assertRaises(platform.LockUnavailable) as stopped:
                    lock.__enter__()
                elapsed = time.monotonic() - start
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=_POLL_SECONDS)
            self.assertGreaterEqual(elapsed, 0.9)
            self.assertLess(elapsed, _POLL_SECONDS)
            self.assertEqual(stopped.exception.code, "lock_unavailable")
            self.assertEqual(stopped.exception.values, {"path": str(lock_path)})
            self.assertEqual(stopped.exception.exit_code, 1)

    def test_lock_free_after_holder_exits(self) -> None:
        with support.TemporaryFolder() as folder:
            lock_path = folder / "lock"
            holder = _holder_process(lock_path, 5.0)
            try:
                _wait_until_held(lock_path, time.monotonic() + _POLL_SECONDS)
                _wait_until_free(lock_path, time.monotonic() + _POLL_SECONDS)
                self.assertEqual(holder.wait(timeout=_POLL_SECONDS), 0)
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=_POLL_SECONDS)

    def test_lock_free_after_holder_is_killed(self) -> None:
        with support.TemporaryFolder() as folder:
            lock_path = folder / "lock"
            holder = _holder_process(lock_path, 60.0)
            try:
                _wait_until_held(lock_path, time.monotonic() + _POLL_SECONDS)
                holder.kill()
                holder.wait(timeout=_POLL_SECONDS)
                _wait_until_free(lock_path, time.monotonic() + _POLL_SECONDS)
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=_POLL_SECONDS)

    def test_nested_take_in_one_process_does_not_wait(self) -> None:
        with support.TemporaryFolder() as folder:
            lock_path = folder / "lock"
            inner_path = folder / "sub" / ".." / "lock"
            with platform.StoreLock(lock_path):
                start = time.monotonic()
                with platform.StoreLock(inner_path, limit_seconds=5.0):
                    self.assertLess(time.monotonic() - start, 0.3)
                    self.assertEqual(_checker_exit(lock_path, tries=4), 3)
                self.assertEqual(_checker_exit(lock_path, tries=4), 3)
            self.assertEqual(_checker_exit(lock_path, tries=40), 0)


# The executable and the store folder of the entry of the scheduled ingestion, invented.
_EXE = Path("/opt/bin/ai-effort-ledger")
_STORE = Path("/home/person/Store")

# The answer of the Task Scheduler to a query of the entry, written by hand with invented text.
_QUERY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Actions Context="Author">
    <Exec>
      <Command>/opt/bin/ai-effort-ledger</Command>
      <Arguments>ingest --store "/home/person/Store"</Arguments>
    </Exec>
  </Actions>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T12:00:00</StartBoundary>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
</Task>
"""


class _SchedulerRun:
    """The fake of the scheduler program: it takes each word list and answers by its second word.

    A key of the results matches the second word, such as "/Query" or "enable"; its value is the
    exit code and the output. Every command without a key ends with exit code 0 and no output.
    """

    def __init__(self, results: dict[str, tuple[int, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.results = results or {}

    def __call__(self, words: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(words)
        code, output = self.results.get(words[1] if len(words) > 1 else "", (0, ""))
        return subprocess.CompletedProcess(words, code, output, "")


class _FailingRun:
    """The fake of the scheduler program that ends with exit code 1 on the call that
    holds its word, and with exit code 0 on every other call."""

    def __init__(self, word: str) -> None:
        self.calls: list[list[str]] = []
        self.word = word

    def __call__(self, words: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(words)
        return subprocess.CompletedProcess(words, 1 if self.word in words else 0, "", "")


def _definition(kind: str, store: Path = _STORE) -> dict[str, str]:
    """The files of the entry of the kind at 06:05, the time of the tests that read it back."""
    return platform.entry_definition(kind, _EXE, store, "06:05")


def _write_definition(folder: Path, kind: str, store: Path) -> None:
    """Write the files of the entry of the kind into the folder, as a create writes them."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in _definition(kind, store).items():
        (folder / name).write_text(text, encoding="utf-8")


def _with_systemctl(word: str) -> str | None:
    """The fake answer of the system for the folder of a program: it has systemctl."""
    return "/usr/bin/systemctl" if word == "systemctl" else None


def _without_systemctl(word: str) -> str | None:
    """The fake answer of the system for the folder of a program: it has no program."""
    return None


class _TextPath(PureWindowsPath):
    """A path whose text is the store folder exactly as the table test names it: a Path
    of Windows drops a backslash at the end, which the pair must still carry."""

    def __new__(cls, text: str) -> "_TextPath":
        made = super().__new__(cls, text)
        made._text = text
        return made

    def __str__(self) -> str:
        return self._text


# The store folders of the table test, one invented name for each form a word can hold
# (Ruling 125); the kinds of POSIX read them under a home of POSIX.
_POSIX_WORDS = (
    ("a space", "/home/person/Big Store"),
    ("a percent sign", "/home/person/100%"),
    ("a dollar", "/home/person/100$"),
    ("a name in braces", "/home/person/Cost ${NAME}"),
    ("a double quote", '/home/person/Quo"te'),
    ("a backslash in the middle", "/home/person/Back\\slash"),
    ("a non-ASCII letter", "/home/person/Città"),
    ("a tab", "/home/person/Ta\tb"),
)

# The store folders of the table test for the Task Scheduler, with the forms a folder of
# Windows holds: a drive root, a share, and a backslash at the end.
_WINDOWS_WORDS = (
    ("a space", "C:\\Big Store"),
    ("a percent sign", "C:\\100%"),
    ("a dollar", "C:\\100$"),
    ("a name in braces", "C:\\Cost ${NAME}"),
    ("a double quote", 'C:\\Quo"te'),
    ("a backslash in the middle", "C:\\Back\\slash"),
    ("a non-ASCII letter", "C:\\Città"),
    ("a tab", "C:\\Ta\tb"),
    ("a drive root", "C:\\"),
    ("a share", "\\\\server\\share\\Store"),
    ("a backslash at the end", "C:\\a b\\"),
)


def _deep_binary_plist(depth: int) -> bytes:
    """A binary plist whose top array holds an array, `depth` times over: the reader of
    plistlib takes each nesting with calls on the stack of Python, so a file deeper than
    that stack is a damaged file (the XML form of the same depth reads without it)."""
    objects = [b"\xa1" + struct.pack(">I", number + 1) for number in range(depth - 1)]
    objects.append(b"\xa0")  # the deepest array holds no element
    body = bytearray(b"bplist00")
    offsets = []
    for thing in objects:
        offsets.append(len(body))
        body += thing
    table = len(body)
    body += b"".join(struct.pack(">I", offset) for offset in offsets)
    body += struct.pack(">6xBBQQQ", 4, 4, len(objects), 0, table)
    return bytes(body)


class TestSchedulerEntries(unittest.TestCase):
    """The entry of the scheduled ingestion follows the specification, with a fake program."""

    def test_windows_definition(self) -> None:
        files = platform.entry_definition("windows", _EXE, _STORE, "12:00")
        text = files[f"{platform.ENTRY_NAME}.xml"]
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", text)
        self.assertIn("<Hidden>true</Hidden>", text)
        self.assertIn("<StartBoundary>2000-01-01T12:00:00</StartBoundary>", text)
        self.assertIn("<ScheduleByDay>", text)
        self.assertIn(f"<Command>{_EXE}</Command>", text)
        self.assertIn(f"ingest --store {_STORE}", text)  # one word, no quotes needed

    def test_launchd_definition(self) -> None:
        files = platform.entry_definition("launchd", _EXE, _STORE, "12:00")
        text = files[f"{platform.ENTRY_NAME}.plist"]
        self.assertIn(f"<string>{platform.ENTRY_NAME}</string>", text)
        self.assertIn("<key>StartCalendarInterval</key>", text)
        self.assertIn("<key>Hour</key>\n      <integer>12</integer>", text)
        self.assertIn("<key>Minute</key>\n      <integer>0</integer>", text)

    def test_systemd_definition(self) -> None:
        files = platform.entry_definition(
            "systemd", PurePosixPath("/opt/bin/ai-effort-ledger"),
            PurePosixPath("/home/person/Store"), "12:00")
        timer = files[f"{platform.ENTRY_NAME}.timer"]
        service = files[f"{platform.ENTRY_NAME}.service"]
        self.assertIn("OnCalendar=*-*-* 12:00:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn(
            "ExecStart=/opt/bin/ai-effort-ledger ingest --store /home/person/Store", service)

    def test_cron_is_one_line_to_show(self) -> None:
        files = platform.entry_definition("cron", _EXE, _STORE, "12:00")
        self.assertEqual(
            files,
            {f"{platform.ENTRY_NAME}.cron":
                f"0 12 * * * '{_EXE}' ingest --store '{_STORE}'"})

    def test_cron_line_escapes_the_percent_of_the_executable(self) -> None:
        """The executable word of the line of cron writes every `%` of the install folder
        as `\\%`, which cronie strips back to the percent before the shell runs the line;
        the install folder is no value of the command, so no guard refuses it, while the
        store word keeps its refusal (ruled 2026-11-27)."""
        executable = PurePosixPath("/opt/100%/bin/ai-effort-ledger")
        line = platform.entry_definition(
            "cron", executable, _STORE, "12:00")[f"{platform.ENTRY_NAME}.cron"]
        self.assertEqual(
            line,
            f"0 12 * * * '/opt/100\\%/bin/ai-effort-ledger' ingest --store '{_STORE}'")

    def test_definitions_keep_special_characters(self) -> None:
        store = Path(r"C:\Users\Jane Doe\Città 100%")
        text = str(store)
        windows = platform.entry_definition("windows", _EXE, store, "12:00")
        self.assertIn(f'ingest --store "{text}"', windows[f"{platform.ENTRY_NAME}.xml"])
        systemd = platform.entry_definition(
            "systemd", PurePosixPath("/opt/bin/ai-effort-ledger"), store, "12:00")
        quoted = '"' + text.replace("\\", "\\\\").replace("%", "%%") + '"'
        self.assertIn("ExecStart=/opt/bin/ai-effort-ledger ingest --store " + quoted,
                      systemd[f"{platform.ENTRY_NAME}.service"])
        cron = platform.entry_definition(
            "cron", PurePosixPath("/opt/bin/ai-effort-ledger"), store, "12:00")
        self.assertIn(
            f"ingest --store '{text}'", cron[f"{platform.ENTRY_NAME}.cron"])
        launchd = platform.entry_definition("launchd", _EXE, store, "12:00")
        self.assertIn(f"<string>{text}</string>", launchd[f"{platform.ENTRY_NAME}.plist"])

    def test_create_replaces_existing_entry(self) -> None:
        fake = _SchedulerRun()
        with support.TemporaryFolder() as folder:
            platform.create_entry(
                "windows", _EXE, folder / "Store", "12:00", fake, folder, {}, None)
            self.assertEqual(len(fake.calls), 1)
            created = fake.calls[0]
            self.assertEqual(created[:4], ["schtasks", "/Create", "/TN", platform.ENTRY_NAME])
            self.assertIn("/F", created)
            self.assertFalse(Path(created[created.index("/XML") + 1]).exists())

    def test_remove_without_entry_returns_false(self) -> None:
        fake = _SchedulerRun({"/Query": (1, "ERROR: The system cannot find the file specified.")})
        absent = platform.remove_entry("windows", fake, Path("/home/person"), {}, None)
        self.assertFalse(absent)
        self.assertEqual([call[:2] for call in fake.calls], [["schtasks", "/Query"]])

    def test_cron_create_changes_nothing(self) -> None:
        fake = _SchedulerRun()
        with support.TemporaryFolder() as folder:
            entry = platform.create_entry(
                "cron", _EXE, folder / "Store", "12:00", fake, folder, {}, None)
            self.assertEqual(fake.calls, [])
            self.assertEqual(list(folder.iterdir()), [])
        self.assertEqual(entry, platform.SchedulerEntry(
            platform.ENTRY_NAME, [str(_EXE), "ingest", "--store", str(folder / "Store")], "12:00"))

    def test_launchd_create_uses_given_uid(self) -> None:
        fake = _SchedulerRun()
        with support.TemporaryFolder() as folder:
            home = folder / "Home"
            platform.create_entry(
                "launchd", _EXE, folder / "Store", "12:00", fake, home, {}, 501)
            plist = home / "Library" / "LaunchAgents" / f"{platform.ENTRY_NAME}.plist"
            self.assertTrue(plist.exists())
        self.assertEqual(
            fake.calls,
            [["launchctl", "bootout", f"gui/501/{platform.ENTRY_NAME}"],
             ["launchctl", "bootstrap", "gui/501", str(plist)]])

    def test_launchd_create_replaces_loaded_entry(self) -> None:
        # The exit code 0 of bootout says that the loaded entry came out of the domain.
        fake = _SchedulerRun({"bootout": (0, "")})
        with support.TemporaryFolder() as folder:
            home = folder / "Home"
            platform.create_entry(
                "launchd", _EXE, folder / "Store", "12:00", fake, home, {}, 501)
            plist = home / "Library" / "LaunchAgents" / f"{platform.ENTRY_NAME}.plist"
            self.assertTrue(plist.exists())
        self.assertEqual([call[1] for call in fake.calls], ["bootout", "bootstrap"])

    def test_launchd_create_tolerates_a_failed_bootout(self) -> None:
        # The exit code 5 of bootout says that the entry was not loaded in the domain.
        fake = _SchedulerRun({"bootout": (5, "No such process")})
        with support.TemporaryFolder() as folder:
            platform.create_entry(
                "launchd", _EXE, folder / "Store", "12:00", fake, folder, {}, 501)
        self.assertEqual([call[1] for call in fake.calls], ["bootout", "bootstrap"])

    def test_launchd_bootstrap_failure_removes_plist(self) -> None:
        fake = _SchedulerRun({"bootstrap": (1, "Bootstrap failed: 5: Input/output error")})
        with support.TemporaryFolder() as folder:
            home = folder / "Home"
            with self.assertRaises(platform.SchedulerFailed) as stopped:
                platform.create_entry(
                    "launchd", _EXE, folder / "Store", "12:00", fake, home, {}, 501)
            plist = home / "Library" / "LaunchAgents" / f"{platform.ENTRY_NAME}.plist"
            self.assertFalse(plist.exists())
        self.assertEqual(stopped.exception.values, {"program": "launchctl", "exit_code": 1})
        self.assertEqual([call[1] for call in fake.calls], ["bootout", "bootstrap"])

    def test_systemd_folder_follows_xdg_config_home(self) -> None:
        fake = _SchedulerRun()
        with support.TemporaryFolder() as folder:
            platform.create_entry(
                "systemd", _EXE, folder / "Store", "12:00", fake, folder / "Home",
                {"XDG_CONFIG_HOME": str(folder)}, None)
            timer = folder / "systemd" / "user" / f"{platform.ENTRY_NAME}.timer"
            self.assertTrue(timer.exists())
            self.assertTrue((folder / "systemd" / "user" /
                             f"{platform.ENTRY_NAME}.service").exists())
        self.assertEqual([call[:2] for call in fake.calls],
                         [["systemctl", "--user"], ["systemctl", "--user"]])
        self.assertIn("daemon-reload", fake.calls[0])
        self.assertIn("enable", fake.calls[1])
        self.assertIn(f"{platform.ENTRY_NAME}.timer", fake.calls[1])

    def test_systemd_failed_create_removes_its_files(self) -> None:
        """A systemd call of the create that ends with a non-zero code raises
        `SchedulerFailed` and leaves no `.service` and no `.timer` on disk, as a failed
        bootstrap leaves no plist, so `schedule show` reads no entry that the scheduler
        never runs."""
        for step in ("daemon-reload", "enable"):
            with self.subTest(step=step), support.TemporaryFolder() as folder:
                fake = _FailingRun(step)
                with self.assertRaises(platform.SchedulerFailed) as stopped:
                    platform.create_entry(
                        "systemd", _EXE, folder / "Store", "12:00", fake, folder / "Home",
                        {"XDG_CONFIG_HOME": str(folder)}, None)
                units = folder / "systemd" / "user"
                self.assertFalse((units / f"{platform.ENTRY_NAME}.timer").exists())
                self.assertFalse((units / f"{platform.ENTRY_NAME}.service").exists())
            self.assertEqual(stopped.exception.values,
                             {"program": "systemctl", "exit_code": 1})

    def test_entry_time_is_the_time_of_the_entry(self) -> None:
        """The time of the entry is public in `platform` under its own name, in the form
        `HH:MM` of the command line: setup shows it and the entry holds it."""
        self.assertEqual(platform.entry_time("06:05"), "06:05")
        with self.assertRaises(ValueError):
            platform.entry_time("6:05")

    def test_time_must_be_hh_mm(self) -> None:
        with self.assertRaises(ValueError):
            platform.entry_definition("windows", _EXE, _STORE, "25:00")
        with self.assertRaises(ValueError):
            platform.entry_definition("cron", _EXE, _STORE, "12:00:00")
        with self.assertRaises(ValueError):  # a one-digit hour is no `HH:MM`
            platform.entry_definition("cron", _EXE, _STORE, "9:30")
        with self.assertRaises(ValueError):  # a newline after the minute is no `HH:MM`
            platform.entry_definition("windows", _EXE, _STORE, "06:05\n")

    def test_scheduler_kind(self) -> None:
        self.assertEqual(platform.scheduler_kind("Windows", _with_systemctl), "windows")
        self.assertEqual(platform.scheduler_kind("Darwin", _without_systemctl), "launchd")
        self.assertEqual(platform.scheduler_kind("Linux", _with_systemctl), "systemd")
        self.assertEqual(platform.scheduler_kind("Linux", _without_systemctl), "cron")

    def test_show_entry_reads_the_entry(self) -> None:
        fake = _SchedulerRun({"/Query": (0, _QUERY_XML)})
        entry = platform.show_entry("windows", fake, Path("/home/person"), {})
        self.assertEqual(entry, platform.SchedulerEntry(
            platform.ENTRY_NAME,
            ["/opt/bin/ai-effort-ledger", "ingest", "--store", "/home/person/Store"],
            "12:00"))

    def test_show_entry_reads_the_plist_back(self) -> None:
        fake = _SchedulerRun()
        with support.TemporaryFolder() as folder:
            home = folder / "Home"
            store = folder / "Città 100%"
            _write_definition(home / "Library" / "LaunchAgents", "launchd", store)
            entry = platform.show_entry("launchd", fake, home, {})
        self.assertEqual(entry, platform.SchedulerEntry(
            platform.ENTRY_NAME, [str(_EXE), "ingest", "--store", str(store)], "06:05"))
        self.assertEqual(fake.calls, [])  # read from the file, no program asked

    def test_show_entry_reads_the_timer_and_the_service_back(self) -> None:
        for variable in (True, False):
            with self.subTest(XDG_CONFIG_HOME=variable), support.TemporaryFolder() as folder:
                fake = _SchedulerRun()
                home = folder / "Home"
                store = folder / "Città 100%"
                configuration = folder / "Configuration" if variable else home / ".config"
                environ = {"XDG_CONFIG_HOME": str(configuration)} if variable else {}
                _write_definition(configuration / "systemd" / "user", "systemd", store)
                entry = platform.show_entry("systemd", fake, home, environ)
                self.assertEqual(entry, platform.SchedulerEntry(
                    platform.ENTRY_NAME, [str(_EXE), "ingest", "--store", str(store)], "06:05"))
                self.assertEqual(fake.calls, [])  # read from the files, no program asked

    def test_show_entry_without_files_is_none(self) -> None:
        with support.TemporaryFolder() as folder:
            for kind in ("launchd", "systemd"):
                with self.subTest(kind=kind):
                    self.assertIsNone(platform.show_entry(kind, _SchedulerRun(), folder, {}))

    def test_the_pair_of_launchd_carries_every_word(self) -> None:
        """The pair of launchd carries every word of the table: the plist holds each
        word as its own string, and the reader reads the strings back unchanged."""
        for word, folder in _POSIX_WORDS:
            with self.subTest(word=word), support.TemporaryFolder() as base:
                home = base / "Home"
                _write_definition(
                    home / "Library" / "LaunchAgents", "launchd", PurePosixPath(folder))
                entry = platform.show_entry("launchd", _SchedulerRun(), home, {})
                self.assertEqual(entry, platform.SchedulerEntry(
                    platform.ENTRY_NAME, [str(_EXE), "ingest", "--store", folder], "06:05"))

    def test_the_pair_of_systemd_carries_every_word(self) -> None:
        """The pair of systemd carries every word of the table: the writer quotes a word
        that holds whitespace, a double quote or a backslash, escapes the backslash and
        the double quote inside the quotes, and doubles `%` and `$`; the reader undoes
        exactly that."""
        for word, folder in _POSIX_WORDS:
            with self.subTest(word=word), support.TemporaryFolder() as base:
                home = base / "Home"
                _write_definition(
                    home / ".config" / "systemd" / "user", "systemd", PurePosixPath(folder))
                entry = platform.show_entry("systemd", _SchedulerRun(), home, {})
                self.assertEqual(entry, platform.SchedulerEntry(
                    platform.ENTRY_NAME, [str(_EXE), "ingest", "--store", folder], "06:05"))

    def test_the_pair_of_cron_carries_every_word(self) -> None:
        """The pair of cron is the line of the table and the shell's reading of its
        single-quoted words (`shlex` models the reading): every word of the table but the
        store word with the `%`, which `schedule create` refuses, comes back unchanged.
        The `\\%` of an executable word is one for cronie, which strips the backslash
        before the shell runs the line, so no reading of the pair undoes it."""
        for word, folder in _POSIX_WORDS:
            if word == "a percent sign":
                continue
            with self.subTest(word=word):
                line = platform.entry_definition(
                    "cron", _EXE, PurePosixPath(folder), "06:05")[f"{platform.ENTRY_NAME}.cron"]
                self.assertEqual(
                    shlex.split(line)[5:], [str(_EXE), "ingest", "--store", folder])

    def test_the_pair_of_windows_carries_every_word(self) -> None:
        """The pair of the Task Scheduler carries every word of the table: the writer
        quotes `Arguments` by the rules of `CommandLineToArgvW` (`list2cmdline`), so a
        run of backslashes before a closing quote is doubled, and the reader splits by
        the same rules."""
        for word, folder in _WINDOWS_WORDS:
            with self.subTest(word=word):
                xml = platform.entry_definition(
                    "windows", _EXE, _TextPath(folder),
                    "06:05")[f"{platform.ENTRY_NAME}.xml"]
                fake = _SchedulerRun({"/Query": (0, xml)})
                entry = platform.show_entry("windows", fake, Path("/home/person"), {})
                self.assertEqual(entry, platform.SchedulerEntry(
                    platform.ENTRY_NAME, [str(_EXE), "ingest", "--store", folder], "06:05"))

    def test_carries_word(self) -> None:
        """Every kind carries the words of the table but the one with the `%`, which cron
        refuses; a newline and a carriage return break the one line of cron; no kind
        carries another control character — exact for the XML kinds, whose text of 1.0
        admits a tab, a newline and a carriage return alone of the control characters,
        documented for systemd (control characters are not allowed, systemd.service(5)
        › Command lines), conservative for cron, whose carriers of the table are not
        verified to hold such bytes — or a surrogate, which no UTF-8 text holds."""
        for kind in ("windows", "launchd", "systemd", "cron"):
            for word, folder in _POSIX_WORDS:
                with self.subTest(kind=kind, store=folder):
                    self.assertEqual(platform.carries_word(kind, folder),
                                     kind != "cron" or word != "a percent sign")
            for word in ("nl\nl", "cr\rr"):
                with self.subTest(kind=kind, word=word):
                    self.assertEqual(platform.carries_word(kind, word), kind != "cron")
            for word in ("\x01", "\x0b", "\ud800"):
                with self.subTest(kind=kind, refused=word):
                    self.assertFalse(platform.carries_word(kind, word))

    def test_show_entry_of_damaged_files_is_none(self) -> None:
        words = [str(_EXE), "ingest", "--store", str(_STORE)]
        plist = _definition("launchd")[f"{platform.ENTRY_NAME}.plist"]
        plists = {
            "not a plist": b"Invented text that is no plist.\n",
            "a plist cut short": plist[:200].encode("utf-8"),
            "a key outside a dict": b"<plist><key>Label</key></plist>",
            "a date that is no date": b"<plist><date>never</date></plist>",
            "a plist of an unknown encoding": plist.encode("utf-8").replace(
                b'encoding="UTF-8"', b'encoding="UTF-9"'),
            "a binary plist deeper than the stack": _deep_binary_plist(5000),
            "an Hour of 24": plistlib.dumps(
                {"Label": platform.ENTRY_NAME, "ProgramArguments": words,
                 "StartCalendarInterval": {"Hour": 24, "Minute": 5}}),
            "without StartCalendarInterval": plistlib.dumps(
                {"Label": platform.ENTRY_NAME, "ProgramArguments": words}),
            "of another Label": plistlib.dumps(
                {"Label": "org.example.other", "ProgramArguments": words,
                 "StartCalendarInterval": {"Hour": 6, "Minute": 5}}),
        }
        for case, content in plists.items():
            with self.subTest(plist=case), support.TemporaryFolder() as folder:
                agents = folder / "Library" / "LaunchAgents"
                agents.mkdir(parents=True)
                (agents / f"{platform.ENTRY_NAME}.plist").write_bytes(content)
                self.assertIsNone(platform.show_entry("launchd", _SchedulerRun(), folder, {}))
        files = _definition("systemd")
        timer = files[f"{platform.ENTRY_NAME}.timer"]
        units = {
            "a timer without its service": {f"{platform.ENTRY_NAME}.timer": timer},
            "an OnCalendar of another form": {
                **files,
                f"{platform.ENTRY_NAME}.timer": timer.replace("*-*-* 06:05:00", "daily")},
            "an ExecStart whose quote is never closed": {
                **files,
                f"{platform.ENTRY_NAME}.service": "[Service]\nExecStart=\"/opt/bin/ledger\n"},
            "an ExecStart with an escape systemd does not read": {
                **files,
                f"{platform.ENTRY_NAME}.service":
                    "[Service]\nExecStart=/opt/bin/ledger ingest \\x\n"},
        }
        for case, written in units.items():
            with self.subTest(systemd=case), support.TemporaryFolder() as folder:
                units_folder = folder / ".config" / "systemd" / "user"
                units_folder.mkdir(parents=True)
                for name, text in written.items():
                    (units_folder / name).write_text(text, encoding="utf-8")
                self.assertIsNone(platform.show_entry("systemd", _SchedulerRun(), folder, {}))

    def test_show_entry_of_a_damaged_answer_is_none(self) -> None:
        """A damaged answer of the Task Scheduler is no entry, never a stop: text that is
        no XML, and an `Arguments` with a lone surrogate, which no UTF-8 text holds and
        the parser of XML refuses to encode."""
        answers = {
            "text that is no XML": "Invented text that is no XML answer.",
            "a lone surrogate in Arguments": _QUERY_XML.replace(
                'ingest --store "/home/person/Store"',
                'ingest --store "/home/person/Sto\ud800re"'),
        }
        for case, text in answers.items():
            with self.subTest(answer=case):
                fake = _SchedulerRun({"/Query": (0, text)})
                self.assertIsNone(
                    platform.show_entry("windows", fake, Path("/home/person"), {}))

    def test_show_entry_of_cron_is_none(self) -> None:
        with support.TemporaryFolder() as folder:  # the files of the other kinds are not read
            _write_definition(folder / "Library" / "LaunchAgents", "launchd", _STORE)
            _write_definition(folder / ".config" / "systemd" / "user", "systemd", _STORE)
            self.assertIsNone(platform.show_entry("cron", _SchedulerRun(), folder, {}))

    def test_failed_scheduler_program_raises(self) -> None:
        fake = _SchedulerRun({"/Create": (1, "ERROR: access denied.")})
        with self.assertRaises(platform.SchedulerFailed) as stopped:
            platform.create_entry(
                "windows", _EXE, _STORE, "12:00", fake, Path("/home/person"), {}, None)
        error = stopped.exception
        self.assertEqual(error.code, "scheduler_failed")
        self.assertEqual(error.values, {"program": "schtasks", "exit_code": 1})
        self.assertEqual(error.exit_code, 1)
