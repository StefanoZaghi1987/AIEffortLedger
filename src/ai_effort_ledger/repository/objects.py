"""The root commit of a repository, read from the object store of git with `zlib`.

The reader walks from the `HEAD` of the git folder itself — of the worktree, when the
folder is that of a linked worktree — through the loose reference files and `packed-refs`
of the common git directory, and reads each commit as a loose object or from a pack file
of format number 2 with its index, whole or as an `OFS_DELTA` or a `REF_DELTA` delta. It
covers the `files` reference backend and object names of 20 bytes (SHA-1); a `shallow`
file, an unborn branch, a name outside that scope, and an object it cannot read all give
None, and the caller warns (ingestion.md › Repository identity).
"""

import zlib
from pathlib import Path

_TYPES = {1: "commit", 2: "tree", 3: "blob", 4: "tag"}
_OFS_DELTA = 6
_REF_DELTA = 7
_HOPS = 10
_DEPTH = 100
_HEX = "0123456789abcdef"


def root_commit(git_folder: Path, common_dir: Path) -> str | None:
    """The root commit of the repository of this git folder with this common git directory,
    or None.

    The walk starts at the commit that the `HEAD` of the git folder itself holds — the
    worktree's `HEAD` when the folder is that of a linked worktree — and follows the first
    parent of each commit until a commit has no parent; the references and the objects it
    reads are the common git directory's. A `shallow` file marks a clone whose history
    stops before its root; a cycle among the parents ends the walk as well. None in every
    such case, and the caller warns.
    """
    if (common_dir / "shallow").is_file():
        return None
    current = _head_commit(git_folder, common_dir)
    seen: set[str] = set()
    while current is not None and current not in seen:
        seen.add(current)
        content = _commit_content(common_dir, current)
        if content is None:
            return None
        parents = _parents(content)
        if parents is None:
            return None
        if not parents:
            return current
        current = parents[0]
    return None


def _head_commit(git_folder: Path, common_dir: Path) -> str | None:
    """The commit that the `HEAD` of the git folder holds, through the symbolic references
    of the files backend; the references it names are the common git directory's."""
    text = _read_text(git_folder / "HEAD")
    for _ in range(_HOPS):
        if text is None:
            return None
        target = _symbolic_target(text)
        if target is None:
            return _object_name(text)
        text = _loose_ref(common_dir, target)
        if text is None:
            return _packed_ref(common_dir, target)
    return None


def _symbolic_target(text: str) -> str | None:
    """The reference that a symbolic reference file points to, or None for a direct value."""
    first = text.split("\n", 1)[0].strip()
    if first.startswith("ref:"):
        return first[4:].strip()
    return None


def _loose_ref(common_dir: Path, name: str) -> str | None:
    """The text of the loose reference file of the name, or None when it is not there."""
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return _read_text(common_dir.joinpath(*parts))


def _packed_ref(common_dir: Path, name: str) -> str | None:
    """The value that `packed-refs` holds for the name, or None when it is not there."""
    text = _read_text(common_dir / "packed-refs")
    if text is None:
        return None
    for line in text.splitlines():
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        held, _, reference = line.partition(" ")
        if reference.strip() == name:
            return _object_name(held)
    return None


def _parents(content: bytes) -> list[str] | None:
    """The parent names of a commit, in the order of the header; None when the content has
    no commit header.

    The header ends at the first empty line. A `parent` line that does not hold an object
    name of the scope of the reader makes the commit unreadable, so that the walk cannot
    invent a root commit.
    """
    lines = content.split(b"\n")
    if b"" not in lines:
        return None
    parents: list[str] = []
    for line in lines[:lines.index(b"")]:
        if line.startswith(b"parent "):
            name = _object_name(line[7:].decode("ascii", "replace"))
            if name is None:
                return None
            parents.append(name)
    return parents


def _commit_content(common_dir: Path, name: str) -> bytes | None:
    """The content of the commit object of the name, or None when it cannot be read."""
    read = _read_object(common_dir, name, 0)
    if read is None or read[0] != "commit":
        return None
    return read[1]


def _read_object(common_dir: Path, name: str, depth: int) -> tuple[str, bytes] | None:
    """The type and the content of the object of the name, loose first, then from a pack."""
    read = _read_loose(common_dir, name)
    if read is not None:
        return read
    return _read_from_packs(common_dir, name, depth)


def _read_text(path: Path) -> str | None:
    """The text of the file, or None when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _object_name(text: str) -> str | None:
    """The object name in the text, in lower case, when it holds 40 hexadecimal characters.

    A name of any other length is an object store outside the scope of the reader, SHA-256
    among them, and gives None.
    """
    held = text.strip().lower()
    if len(held) != 40 or any(character not in _HEX for character in held):
        return None
    return held


def _read_loose(common_dir: Path, name: str) -> tuple[str, bytes] | None:
    """The type and the content of the loose object of the name, or None."""
    try:
        data = zlib.decompress((common_dir / "objects" / name[:2] / name[2:]).read_bytes())
    except (OSError, zlib.error):
        return None
    head, _, content = data.partition(b"\0")
    parts = head.split(b" ")
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) != len(content):
        return None
    return parts[0].decode("ascii", "replace"), content


def _read_from_packs(common_dir: Path, name: str, depth: int) -> tuple[str, bytes] | None:
    """The object of the name from the first pack of the common git directory that holds it."""
    for index_path in sorted((common_dir / "objects" / "pack").glob("*.idx")):
        read = _read_from_pack(common_dir, index_path, name, depth)
        if read is not None:
            return read
    return None


def _read_from_pack(
    common_dir: Path,
    index_path: Path,
    name: str,
    depth: int,
) -> tuple[str, bytes] | None:
    """The object of the name from the pack that this index belongs to, or None."""
    try:
        index = index_path.read_bytes()
        pack = index_path.with_suffix(".pack").read_bytes()
    except OSError:
        return None
    offset = _index_offset(index, bytes.fromhex(name))
    if offset is None or offset >= len(pack):
        return None
    return _pack_object(common_dir, pack, offset, depth)


def _index_offset(index: bytes, wanted: bytes) -> int | None:
    """The offset in the pack of the object of the name, from an index of format number 2."""
    if len(index) < 8 + 1024 or index[:4] != b"\xfftOc" or int.from_bytes(index[4:8], "big") != 2:
        return None
    count = int.from_bytes(index[8 + 255 * 4:8 + 256 * 4], "big")
    names_at = 8 + 1024
    offsets_at = names_at + count * 20 + count * 4
    large_at = offsets_at + count * 4
    if len(index) < large_at + 40:
        return None
    large = (len(index) - large_at - 40) // 8
    low, high = 0, count - 1
    while low <= high:
        middle = (low + high) // 2
        at = names_at + middle * 20
        held = index[at:at + 20]
        if held == wanted:
            small = int.from_bytes(index[offsets_at + middle * 4:offsets_at + middle * 4 + 4],
                                   "big")
            if not small & 0x80000000:
                return small
            number = small & 0x7FFFFFFF
            if number >= large:
                return None
            return int.from_bytes(index[large_at + number * 8:large_at + number * 8 + 8], "big")
        if held < wanted:
            low = middle + 1
        else:
            high = middle - 1
    return None


def _pack_object(
    common_dir: Path,
    pack: bytes,
    offset: int,
    depth: int,
) -> tuple[str, bytes] | None:
    """The type and the content of the object that the pack holds at the offset, applying
    the deltas of its chain, or None when it cannot be read.

    The depth bounds the chain: git writes deltas of at most 50 objects deep, and a hand
    made store that names its own objects as bases must not walk in circles.
    """
    if depth > _DEPTH or not 0 <= offset < len(pack):
        return None
    byte = pack[offset]
    type_number = (byte >> 4) & 7
    size = byte & 0x0F
    shift = 4
    position = offset + 1
    while byte & 0x80:
        if position >= len(pack):
            return None
        byte = pack[position]
        position += 1
        size |= (byte & 0x7F) << shift
        shift += 7
    if type_number in _TYPES:
        data = _inflate(pack, position)
        if data is None or len(data) != size:
            return None
        return _TYPES[type_number], data
    if type_number == _OFS_DELTA:
        moved = _negative_distance(pack, position)
        if moved is None:
            return None
        distance, position = moved
        base = _pack_object(common_dir, pack, offset - distance, depth + 1)
        delta = _inflate(pack, position)
    elif type_number == _REF_DELTA:
        if position + 20 > len(pack):
            return None
        base = _read_object(common_dir, pack[position:position + 20].hex(), depth + 1)
        delta = _inflate(pack, position + 20)
    else:
        return None
    if base is None or delta is None or len(delta) != size:
        return None
    data = _apply_delta(base[1], delta)
    if data is None:
        return None
    return base[0], data


def _negative_distance(pack: bytes, position: int) -> tuple[int, int] | None:
    """The distance back to the base of an `OFS_DELTA`, and the position after its bytes."""
    if position >= len(pack):
        return None
    byte = pack[position]
    position += 1
    distance = byte & 0x7F
    while byte & 0x80:
        if position >= len(pack):
            return None
        byte = pack[position]
        position += 1
        distance = ((distance + 1) << 7) | (byte & 0x7F)
    return distance, position


def _inflate(pack: bytes, position: int) -> bytes | None:
    """The uncompressed bytes of the zlib stream that starts at the position."""
    try:
        return zlib.decompressobj().decompress(pack[position:])
    except zlib.error:
        return None


def _apply_delta(base: bytes, delta: bytes) -> bytes | None:
    """The bytes that the delta rebuilds from the base, or None for a delta it cannot apply.

    The delta starts with the size of the base and of the target, then holds copy
    instructions, which name an offset and a length in the base, and insert instructions,
    which carry their bytes.
    """
    position = 0
    sizes = []
    for _ in range(2):
        value = 0
        shift = 0
        while True:
            if position >= len(delta):
                return None
            byte = delta[position]
            position += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        sizes.append(value)
    if sizes[0] != len(base):
        return None
    parts: list[bytes] = []
    while position < len(delta):
        instruction = delta[position]
        position += 1
        if instruction & 0x80:
            offset = 0
            for bit in range(4):
                if instruction & (1 << bit):
                    if position >= len(delta):
                        return None
                    offset |= delta[position] << (8 * bit)
                    position += 1
            length = 0
            for bit in range(3):
                if instruction & (0x10 << bit):
                    if position >= len(delta):
                        return None
                    length |= delta[position] << (8 * bit)
                    position += 1
            if length == 0:
                length = 0x10000
            if offset + length > len(base):
                return None
            parts.append(base[offset:offset + length])
        else:
            if instruction == 0 or position + instruction > len(delta):
                return None
            parts.append(delta[position:position + instruction])
            position += instruction
    rebuilt = b"".join(parts)
    return rebuilt if len(rebuilt) == sizes[1] else None
