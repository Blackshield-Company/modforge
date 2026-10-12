import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ESM_FLAG = 0x00000001
ESL_FLAG = 0x00000200
COMPRESSED_FLAG = 0x00040000
MAX_RECORD_SCAN = 16 * 1024 * 1024
MAX_HEADER = 1_048_576
MAX_DECOMPRESSED = 32 * 1024 * 1024


@dataclass
class Record:
    type: str
    formid: int
    edid: str | None
    flags: int
    compressed: bool


@dataclass
class Plugin:
    path: Path
    filename: str
    flags: int = 0
    esm: bool = False
    esl: bool = False
    masters: list = field(default_factory=list)
    hedr_version: float | None = None
    hedr_records: int | None = None
    hedr_next_object_id: int | None = None
    records: list = field(default_factory=list)
    parse_error: str | None = None
    header_only: bool = False
    scan_skipped: str | None = None


def iter_subrecords(data):
    i = 0
    n = len(data)
    while i + 6 <= n:
        typ, size = struct.unpack_from("<4sH", data, i)
        i += 6
        if typ == b"XXXX":
            if i + 4 > n:
                return
            size = struct.unpack_from("<I", data, i)[0]
            i += 4
            if i + 6 > n:
                return
            typ, _declared = struct.unpack_from("<4sH", data, i)
            i += 6
        if size < 0 or i + size > n:
            return
        yield typ, data[i : i + size]
        i += size


def _cstring(payload):
    return payload.split(b"\x00", 1)[0].decode("latin1")


def extract_edid(data):
    for typ, payload in iter_subrecords(data):
        if typ == b"EDID":
            return _cstring(payload)
    return None


def _walk(buf, off, end):
    records = []
    while off < end:
        if off + 24 > end:
            raise ValueError(f"truncated record at {off:#x}")
        typ = buf[off : off + 4]
        if typ == b"GRUP":
            gsize = struct.unpack_from("<I", buf, off + 4)[0]
            if gsize < 24 or off + gsize > end:
                raise ValueError(f"bad GRUP size at {off:#x}")
            records.extend(_walk(buf, off + 24, off + gsize))
            off += gsize
            continue
        rtype, dsize, rflags, rid = struct.unpack_from("<4sIII", buf, off)
        if dsize < 0 or off + 24 + dsize > end:
            raise ValueError(f"record overruns file at {off:#x}")
        data = buf[off + 24 : off + 24 + dsize]
        compressed = bool(rflags & COMPRESSED_FLAG)
        if compressed:
            if len(data) < 4:
                raise ValueError(f"compressed record too short at {off:#x}")
            declared = struct.unpack_from("<I", data, 0)[0]
            if declared > MAX_DECOMPRESSED:
                raise ValueError(f"compressed record too large at {off:#x}")
            data = zlib.decompress(data[4:])
        records.append(
            Record(
                type=rtype.decode("ascii", "replace"),
                formid=rid,
                edid=extract_edid(data),
                flags=rflags,
                compressed=compressed,
            )
        )
        off += 24 + dsize
    if off != end:
        raise ValueError("size mismatch while walking groups")
    return records


def parse_plugin(path, scan_records=True, max_bytes=MAX_RECORD_SCAN):
    path = Path(path)
    plugin = Plugin(path=path, filename=path.name)
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            head = handle.read(24)
            if len(head) < 24:
                raise ValueError("file too small for a TES4 header")
            typ, size, flags, _formid = struct.unpack_from("<4sIII", head, 0)
            if typ != b"TES4":
                raise ValueError("not a TES4 plugin")
            if size > MAX_HEADER:
                raise ValueError("TES4 header too large")
            header = handle.read(size)
            if len(header) < size:
                raise ValueError("truncated TES4 header")
            plugin.flags = flags
            plugin.esm = bool(flags & ESM_FLAG)
            plugin.esl = bool(flags & ESL_FLAG)
            masters = []
            for styp, payload in iter_subrecords(header):
                if styp == b"MAST":
                    masters.append(_cstring(payload))
                elif styp == b"HEDR":
                    if len(payload) < 12:
                        raise ValueError("HEDR shorter than 12 bytes")
                    version, num_records, next_id = struct.unpack_from("<fiI", payload, 0)
                    plugin.hedr_version = version
                    plugin.hedr_records = num_records
                    plugin.hedr_next_object_id = next_id
            plugin.masters = masters
            if scan_records and file_size > max_bytes:
                scan_records = False
                plugin.scan_skipped = f"file larger than {max_bytes} bytes"
            if not scan_records:
                plugin.header_only = True
                return plugin
            body = handle.read()
        plugin.records = _walk(body, 0, len(body))
    except Exception as exc:
        plugin.parse_error = str(exc)
    return plugin


def find_plugin_file(name, folders):
    want = name.casefold()
    for folder in folders:
        if folder is None:
            continue
        folder = Path(folder)
        if not folder.is_dir():
            continue
        direct = folder / name
        if direct.is_file():
            return direct
        try:
            for child in folder.iterdir():
                if child.is_file() and child.name.casefold() == want:
                    return child
        except OSError:
            continue
    return None
