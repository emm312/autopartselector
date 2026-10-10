import sqlite3
import zipfile

from autopartselector import update


def test_stream_extract_from_zipped_sqlite(tmp_path):
    db = tmp_path / "parts-fts5.db"
    conn = sqlite3.connect(db)
    cols = ", ".join(f"c{i}" for i in range(12))
    conn.execute(f"CREATE TABLE parts_content(id INTEGER PRIMARY KEY, {cols})")
    rows = [
        ("C25804", "Resistors", "Chip Resistor - Surface Mount", "0603WAF1002T5E", "0603", 2, "UNI-ROYAL",
         "Basic", "100mW 10kΩ 75V ±1%", "ds", "1-:0.002", 22960732),
        ("C1", "Diodes", "Zener Diodes", "x", "SOD-123", 2, "m", "Extended", "d", "ds", "1-:0.1", 5),
    ]
    rows += [(f"C{100 + i}", "Resistors", "Chip Resistor - Surface Mount", "z", "0402", 2, "m", "Extended",
              f"{i}Ω", "", "", i) for i in range(2000)]
    # long description forces an overflow chain (allocated after its leaf page -> forward pointer)
    rows.append(("C2", "Capacitors", "Multilayer Ceramic Capacitors MLCC - SMD/SMT", "y", "0402", 2, "m",
                 "Extended", "100nF 16V X7R " + "x" * 9000, "ds", "1-:0.01", 10))
    conn.executemany(f"INSERT INTO parts_content({cols}) VALUES ({','.join('?' * 12)})", rows)
    conn.commit()
    conn.close()

    with zipfile.ZipFile(tmp_path / "x.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "parts-fts5.db")
    data = (tmp_path / "x.zip").read_bytes()
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    for i in range(0, len(data), 50_000):
        (chunks / f"parts-fts5.db.zip.{i // 50_000 + 1:03d}").write_bytes(data[i:i + 50_000])

    out = tmp_path / "passives.sqlite3"
    n = update.build(out, chunks, min_stock=1)
    got = {r[0]: r for r in sqlite3.connect(out).execute("SELECT lcsc, library_type, description FROM parts")}
    assert 25804 in got and got[25804][1] == "Basic"
    assert 1 not in got  # not a passive subcategory
    assert got[2][2].startswith("100nF 16V X7R xxx") and len(got[2][2]) > 9000
    assert 100 not in got  # stock 0 filtered
    assert n == len(got) == 2 + 1999
