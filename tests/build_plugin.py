import struct
import zlib
from pathlib import Path


def subrecord(typ, data):
    if isinstance(typ, str):
        typ = typ.encode("ascii")
    return typ + struct.pack("<H", len(data)) + data


def cstr(text):
    return text.encode("ascii") + b"\x00"


def record(rtype, flags, formid, data, version=44):
    if isinstance(rtype, str):
        rtype = rtype.encode("ascii")
    return struct.pack("<4sIIIHHHH", rtype, len(data), flags, formid, 0, 0, version, 0) + data


def grup(label, children):
    if isinstance(label, str):
        label = label.encode("ascii")
    body = b"".join(children)
    size = 24 + len(body)
    return struct.pack("<4sI4sIHHHH", b"GRUP", size, label, 0, 0, 0, 0, 0) + body


def new_formid(master_count, local):
    return (master_count << 24) | (local & 0x00FFFFFF)


def override_formid(master_index, local):
    return (master_index << 24) | (local & 0x00FFFFFF)


def write_plugin(path, masters=(), records=(), esl=False, esm=False, version=1.7, author="synthalorian"):
    flags = 0
    if esm:
        flags |= 0x1
    if esl:
        flags |= 0x200
    grouped = {}
    order = []
    for rec in records:
        rtype = rec["type"]
        data = b""
        if rec.get("edid") is not None:
            data += subrecord("EDID", cstr(rec["edid"]))
        data += rec.get("extra", b"")
        rflags = 0
        if rec.get("compress"):
            raw = data
            data = struct.pack("<I", len(raw)) + zlib.compress(raw)
            rflags |= 0x40000
        blob = record(rtype, rflags, rec["formid"], data)
        if rtype not in grouped:
            order.append(rtype)
            grouped[rtype] = []
        grouped[rtype].append(blob)
    body = b"".join(grup(rtype, grouped[rtype]) for rtype in order)
    nrec = sum(len(items) for items in grouped.values())
    header = subrecord("HEDR", struct.pack("<fiI", float(version), nrec + len(order), 0x800))
    for master in masters:
        header += subrecord("MAST", cstr(master))
        header += subrecord("DATA", struct.pack("<Q", 0))
    header += subrecord("CNAM", cstr(author))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(record("TES4", flags, 0, header) + body)
    return path
