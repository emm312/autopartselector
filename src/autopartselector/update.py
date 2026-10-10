"""Build a small in-stock parts DB from Bouni's kicad-jlcpcb-tools parts DB.

The upstream DB is a ~5GB SQLite file shipped as a split zip (~1GB). Rather than
unpacking it to disk, we inflate the zip stream and decode SQLite table-leaf pages
on the fly, keeping the rows from `parts_content` (the FTS5 content table). Descriptions
are only kept for the categories that are matched on them (passives, diodes).
"""

from __future__ import annotations

import os
import sqlite3
import struct
import sys
import time
import urllib.request
import zlib
from pathlib import Path
from typing import Iterable, Iterator

BASE_URL = "https://bouni.github.io/kicad-jlcpcb-tools/"
CHUNK_COUNT_URL = BASE_URL + "chunk_num_fts5.txt"

# parts_content columns c0..c11 (see `CREATE VIRTUAL TABLE parts using fts5`)
COLUMNS = [
    "lcsc", "category", "subcategory", "mfr", "package", "joints",
    "manufacturer", "library_type", "description", "datasheet", "price", "stock",
]
# Subcategories whose description and datasheet are kept; other parts are matched by MPN only.
KEEP_SUBCATEGORIES = {
    "Chip Resistor - Surface Mount",
    "Current Sense / Shunt Resistors",
    "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
    "Inductors (SMD)",
    "Power Inductors",
    "Molding Power Inductors",
    # diodes / LEDs (matched by part number)
    "Switching Diodes",
    "Diodes - General Purpose",
    "Schottky Diodes",
    "Zener Diodes",
    "Fast Recovery / High Efficiency Diodes",
    "Super Barrier Rectifiers (SBR)",
    "Avalanche Diodes",
    "Bridge Rectifiers",
    "ESD and Surge Protection (TVS/ESD)",
    "LED Indication - Discrete",
}

PAGE_SIZE = 4096  # overwritten from the DB header


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    p = Path(base) / "autopartselector"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_db_path() -> Path:
    return cache_dir() / "parts.sqlite3"


# --- byte sources -----------------------------------------------------------

def _http_chunks() -> Iterator[bytes]:
    n = int(urllib.request.urlopen(CHUNK_COUNT_URL, timeout=60).read().strip())
    for i in range(1, n + 1):
        url = f"{BASE_URL}parts-fts5.db.zip.{i:03d}"
        sys.stderr.write(f"  fetching {url}\n")
        with urllib.request.urlopen(url, timeout=120) as r:
            while b := r.read(1 << 20):
                yield b


def _local_chunks(directory: Path) -> Iterator[bytes]:
    files = sorted(directory.glob("parts-fts5.db.zip.*"))
    if not files:
        raise SystemExit(f"no parts-fts5.db.zip.* files in {directory}")
    for f in files:
        with open(f, "rb") as fh:
            while b := fh.read(1 << 22):
                yield b


def _inflate_zip_member(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Yield the decompressed bytes of the first (only) member of a zip stream."""
    it = iter(chunks)
    head = b""
    while len(head) < 30:
        head += next(it)
    if head[:4] != b"PK\x03\x04":
        raise ValueError("not a zip stream")
    method = struct.unpack("<H", head[8:10])[0]
    n, m = struct.unpack("<HH", head[26:30])
    while len(head) < 30 + n + m:
        head += next(it)
    rest = head[30 + n + m:]
    if method != 8:
        raise ValueError(f"unsupported zip compression method {method}")
    d = zlib.decompressobj(-15)
    yield d.decompress(rest)
    for b in it:
        if d.eof:
            break
        yield d.decompress(b)


def _pages(data: Iterable[bytes]) -> Iterator[tuple[int, bytes]]:
    global PAGE_SIZE
    buf = bytearray()
    pageno = 0
    for b in data:
        buf += b
        if pageno == 0 and len(buf) >= 100:
            if buf[:16] != b"SQLite format 3\x00":
                raise ValueError("not an SQLite file")
            ps = struct.unpack(">H", buf[16:18])[0]
            PAGE_SIZE = 65536 if ps == 1 else ps
        while len(buf) >= PAGE_SIZE:
            pageno += 1
            yield pageno, bytes(buf[:PAGE_SIZE])
            del buf[:PAGE_SIZE]


# --- SQLite record decoding --------------------------------------------------

def _varint(b: bytes, i: int) -> tuple[int, int]:
    v = 0
    for k in range(8):
        c = b[i + k]
        v = (v << 7) | (c & 0x7F)
        if c < 0x80:
            return v, i + k + 1
    return (v << 8) | b[i + 8], i + 9


def _decode_record(p: bytes) -> list | None:
    try:
        hlen, i = _varint(p, 0)
        types = []
        while i < hlen:
            t, i = _varint(p, i)
            types.append(t)
        out = []
        j = hlen
        for t in types:
            if t == 0:
                out.append(None)
            elif 1 <= t <= 6:
                size = (1, 2, 3, 4, 6, 8)[t - 1]
                out.append(int.from_bytes(p[j:j + size], "big", signed=True))
                j += size
            elif t == 7:
                out.append(struct.unpack(">d", p[j:j + 8])[0])
                j += 8
            elif t in (8, 9):
                out.append(t - 8)
            elif t >= 12:
                size = (t - 12) // 2 if t % 2 == 0 else (t - 13) // 2
                raw = p[j:j + size]
                out.append(raw if t % 2 == 0 else raw.decode("utf-8", "replace"))
                j += size
            else:
                return None
        return out
    except IndexError:
        return None


def _leaf_cells(page: bytes, pageno: int) -> Iterator[tuple[bytes, int | None, int]]:
    """Yield (local_payload, overflow_page_or_None, total_payload_len) for a table-leaf page."""
    off = 100 if pageno == 1 else 0
    if page[off] != 0x0D:
        return
    ncells = struct.unpack(">H", page[off + 3:off + 5])[0]
    u = PAGE_SIZE
    x = u - 35
    for c in range(ncells):
        ptr = struct.unpack(">H", page[off + 8 + 2 * c:off + 10 + 2 * c])[0]
        if ptr >= u:
            continue
        plen, i = _varint(page, ptr)
        _rowid, i = _varint(page, i)
        if plen <= x:
            yield page[i:i + plen], None, plen
        else:
            m = ((u - 12) * 32 // 255) - 23
            k = m + ((plen - m) % (u - 4))
            local = k if k <= x else m
            ovf = struct.unpack(">I", page[i + local:i + local + 4])[0]
            yield page[i:i + local], ovf, plen


def _wanted(rec: list | None) -> bool:
    return (
        rec is not None
        and len(rec) == len(COLUMNS) + 1
        and isinstance(rec[1], str) and rec[1].startswith("C")
    )


def extract_rows(data: Iterable[bytes]) -> Iterator[list]:
    """Yield decoded parts_content rows (without the id column)."""
    pending: dict[int, tuple[bytearray, int]] = {}  # next overflow page -> (payload so far, total len)
    stats = {"overflow_lost": 0}
    for pageno, page in _pages(data):
        if pageno in pending:
            payload, total = pending.pop(pageno)
            nxt = struct.unpack(">I", page[:4])[0]
            payload += page[4:4 + min(PAGE_SIZE - 4, total - len(payload))]
            if len(payload) >= total or nxt == 0:
                rec = _decode_record(bytes(payload))
                if _wanted(rec):
                    yield rec[1:]
            else:
                pending[nxt] = (payload, total)
            continue
        if page[0] != 0x0D and not (pageno == 1):
            continue
        for local, ovf, total in _leaf_cells(page, pageno):
            if ovf is None:
                rec = _decode_record(local)
                if _wanted(rec):
                    yield rec[1:]
            elif ovf > pageno:
                pending[ovf] = (bytearray(local), total)
            else:
                stats["overflow_lost"] += 1
    if stats["overflow_lost"] or pending:
        sys.stderr.write(f"  note: {stats['overflow_lost'] + len(pending)} rows skipped (backward overflow chains)\n")


def build(out: Path, chunk_dir: Path | None = None, min_stock: int = 1) -> int:
    src = _local_chunks(chunk_dir) if chunk_dir else _http_chunks()
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE parts (lcsc INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, mfr TEXT, "
        "package TEXT, manufacturer TEXT, library_type TEXT, description TEXT, datasheet TEXT, "
        "price TEXT, stock INTEGER)"
    )
    t0 = time.time()
    n = 0
    batch = []
    for r in extract_rows(_inflate_zip_member(src)):
        d = dict(zip(COLUMNS, r))
        try:
            lcsc = int(str(d["lcsc"]).lstrip("C"))
            stock = int(d["stock"] or 0)
        except ValueError:
            continue
        if stock < min_stock:
            continue
        keep = d["subcategory"] in KEEP_SUBCATEGORIES
        batch.append((lcsc, d["category"], d["subcategory"], d["mfr"], d["package"], d["manufacturer"],
                      d["library_type"], d["description"] if keep else None, d["datasheet"] if keep else None,
                      str(d["price"] or ""), stock))
        n += 1
        if len(batch) >= 5000:
            conn.executemany("INSERT OR REPLACE INTO parts VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
            batch.clear()
    conn.executemany("INSERT OR REPLACE INTO parts VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
    conn.execute("CREATE INDEX idx_sub_pkg ON parts(subcategory, package)")
    conn.execute("CREATE INDEX idx_mfr ON parts(mfr COLLATE NOCASE)")
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta VALUES ('built_at', ?)", (time.strftime("%Y-%m-%dT%H:%M:%S"),))
    conn.commit()
    conn.close()
    os.replace(tmp, out)
    sys.stderr.write(f"  wrote {n} parts to {out} in {time.time() - t0:.0f}s\n")
    return n
