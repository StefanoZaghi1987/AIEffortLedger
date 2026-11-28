"""The identity of the machine: the store identifier and the installation identifier.

The salt of the installation identifier is here too: it salts the hash of the identifier.
"""

import hashlib
import re
import secrets
import subprocess
from pathlib import Path
from platform import system as running_system

UUID_TEXT = re.compile(r'"IOPlatformUUID"\s*=\s*"([^"]+)"')

MACHINE_ID_FILE = "/etc/machine-id"
CRYPTOGRAPHY_KEY = r"SOFTWARE\Microsoft\Cryptography"


def store_identifier(store_folder: Path, system: str) -> str:
    """The first 16 hexadecimal characters of the SHA-256 hash of the resolved absolute path.

    On Windows the path text is lower case before the hash, so two ways to write the same
    folder give one identifier.
    """
    absolute = str(store_folder.resolve())
    if system == "Windows":
        absolute = absolute.lower()
    return hashlib.sha256(absolute.encode("utf-8")).hexdigest()[:16]


def installation_identifier(system: str) -> str | None:
    """The installation identifier of the given system, or None when it gives none.

    Only the running system is read; another system, and a system that gives no identifier,
    give None.
    """
    if system != running_system():
        return None
    if system == "Windows":
        return _registry_guid()
    if system == "Linux":
        return _machine_id_text()
    if system == "Darwin":
        return parse_ioreg(_ioreg_text())
    return None


def parse_ioreg(text: str) -> str | None:
    """The IOPlatformUUID in the text of ioreg, or None when the text holds none."""
    found = UUID_TEXT.search(text)
    return found.group(1) if found else None


def new_salt() -> str:
    """The salt of the salted hash: 32 random hexadecimal characters."""
    return secrets.token_hex(16)


def salted_hash(identifier: str, salt: str) -> str:
    """The SHA-256 hash of the UTF-8 bytes of the salt then the identifier, as lower-case hex."""
    return hashlib.sha256((salt + identifier).encode("utf-8")).hexdigest()


def _registry_guid() -> str | None:
    """The MachineGuid value of the registry of Windows, or None when it gives none."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CRYPTOGRAPHY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return None
    return value if isinstance(value, str) and value else None


def _machine_id_text() -> str | None:
    """The text of /etc/machine-id, or None when the file gives none."""
    try:
        text = Path(MACHINE_ID_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _ioreg_text() -> str:
    """The text of the ioreg output, or "" when the program fails or finds nothing."""
    try:
        done = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return done.stdout if done.returncode == 0 else ""
