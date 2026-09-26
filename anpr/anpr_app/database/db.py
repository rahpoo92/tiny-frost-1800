"""SQLite data access layer: people, their plates, and the entry/exit log.

A plain sqlite3 wrapper rather than an ORM -- the schema is three small
tables and doesn't need one. A single persistent connection is shared and
guarded by a lock, since the camera worker thread and the GUI thread both
touch the database (SQLite connections aren't safe to use from multiple
threads without either that or opening a new connection per call).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..vision.plate_letters import PlateNumber

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    title TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_key TEXT NOT NULL UNIQUE,
    part1 TEXT NOT NULL,
    letter_slug TEXT NOT NULL,
    part2 TEXT NOT NULL,
    province TEXT NOT NULL,
    person_id INTEGER REFERENCES person(id) ON DELETE SET NULL,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_key TEXT NOT NULL,
    plate_display TEXT NOT NULL,
    person_id INTEGER REFERENCES person(id) ON DELETE SET NULL,
    person_name_snapshot TEXT,
    direction TEXT NOT NULL,
    confidence REAL,
    camera_name TEXT,
    snapshot_path TEXT,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_access_log_plate_key ON access_log(plate_key);
CREATE INDEX IF NOT EXISTS idx_access_log_occurred_at ON access_log(occurred_at);
CREATE INDEX IF NOT EXISTS idx_plate_person_id ON plate(person_id);
"""


@dataclass
class Person:
    id: int
    full_name: str
    title: str | None
    notes: str | None
    active: bool
    created_at: str

    @property
    def display_name(self) -> str:
        return f"{self.title} {self.full_name}".strip() if self.title else self.full_name

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Person":
        return cls(
            id=row["id"],
            full_name=row["full_name"],
            title=row["title"],
            notes=row["notes"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )


@dataclass
class PlateRecord:
    id: int
    plate_key: str
    part1: str
    letter_slug: str
    part2: str
    province: str
    person_id: int | None
    notes: str | None
    active: bool
    created_at: str

    def plate_number(self) -> PlateNumber:
        return PlateNumber(self.part1, self.letter_slug, self.part2, self.province)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "PlateRecord":
        return cls(
            id=row["id"],
            plate_key=row["plate_key"],
            part1=row["part1"],
            letter_slug=row["letter_slug"],
            part2=row["part2"],
            province=row["province"],
            person_id=row["person_id"],
            notes=row["notes"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )


@dataclass
class AccessLogEntry:
    id: int
    plate_key: str
    plate_display: str
    person_id: int | None
    person_name_snapshot: str | None
    direction: str
    confidence: float | None
    camera_name: str | None
    snapshot_path: str | None
    occurred_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "AccessLogEntry":
        return cls(
            id=row["id"],
            plate_key=row["plate_key"],
            plate_display=row["plate_display"],
            person_id=row["person_id"],
            person_name_snapshot=row["person_name_snapshot"],
            direction=row["direction"],
            confidence=row["confidence"],
            camera_name=row["camera_name"],
            snapshot_path=row["snapshot_path"],
            occurred_at=row["occurred_at"],
        )


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- person -----------------------------------------------------

    def add_person(self, full_name: str, title: str | None = None, notes: str | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO person (full_name, title, notes, active, created_at) VALUES (?, ?, ?, 1, ?)",
                (full_name, title, notes, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_person(
        self,
        person_id: int,
        full_name: str,
        title: str | None = None,
        notes: str | None = None,
        active: bool | None = None,
    ) -> None:
        """Replaces full_name/title/notes outright (title=None or notes=None clears them).

        active is a separate, genuinely optional flag: pass it only to change it.
        """
        fields = ["full_name = ?", "title = ?", "notes = ?"]
        values: list = [full_name, title, notes]
        if active is not None:
            fields.append("active = ?")
            values.append(int(active))
        values.append(person_id)
        with self._lock:
            self._conn.execute(f"UPDATE person SET {', '.join(fields)} WHERE id = ?", values)
            self._conn.commit()

    def get_person(self, person_id: int) -> Person | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)).fetchone()
        return Person.from_row(row) if row else None

    def list_persons(self, include_inactive: bool = True) -> list[Person]:
        query = "SELECT * FROM person"
        if not include_inactive:
            query += " WHERE active = 1"
        query += " ORDER BY full_name"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [Person.from_row(r) for r in rows]

    def delete_person(self, person_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM person WHERE id = ?", (person_id,))
            self._conn.commit()

    # ---- plate --------------------------------------------------------

    def add_plate(
        self,
        plate: PlateNumber,
        person_id: int | None = None,
        notes: str | None = None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO plate (plate_key, part1, letter_slug, part2, province, person_id, notes, active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    plate.to_key(),
                    plate.part1,
                    plate.letter_slug,
                    plate.part2,
                    plate.province,
                    person_id,
                    notes,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_plate(
        self,
        plate_id: int,
        person_id: int | None,
        notes: str | None = None,
        active: bool | None = None,
    ) -> None:
        """Replaces person_id/notes outright (person_id=None clears ownership).

        active is a separate, genuinely optional flag: pass it only to change it.
        """
        fields = ["person_id = ?", "notes = ?"]
        values: list = [person_id, notes]
        if active is not None:
            fields.append("active = ?")
            values.append(int(active))
        values.append(plate_id)
        with self._lock:
            self._conn.execute(f"UPDATE plate SET {', '.join(fields)} WHERE id = ?", values)
            self._conn.commit()

    def delete_plate(self, plate_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM plate WHERE id = ?", (plate_id,))
            self._conn.commit()

    def find_plate_by_key(self, plate_key: str) -> PlateRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM plate WHERE plate_key = ?", (plate_key,)).fetchone()
        return PlateRecord.from_row(row) if row else None

    def list_plates(self, person_id: int | None = None, include_inactive: bool = True) -> list[PlateRecord]:
        query = "SELECT * FROM plate"
        clauses, values = [], []
        if person_id is not None:
            clauses.append("person_id = ?")
            values.append(person_id)
        if not include_inactive:
            clauses.append("active = 1")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(query, values).fetchall()
        return [PlateRecord.from_row(r) for r in rows]

    # ---- access log -----------------------------------------------------

    def insert_access_log(
        self,
        plate_key: str,
        plate_display: str,
        direction: str,
        person_id: int | None = None,
        person_name_snapshot: str | None = None,
        confidence: float | None = None,
        camera_name: str | None = None,
        snapshot_path: str | None = None,
        occurred_at: datetime | None = None,
    ) -> int:
        occurred_at = occurred_at or datetime.now()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO access_log
                   (plate_key, plate_display, person_id, person_name_snapshot, direction,
                    confidence, camera_name, snapshot_path, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plate_key,
                    plate_display,
                    person_id,
                    person_name_snapshot,
                    direction,
                    confidence,
                    camera_name,
                    snapshot_path,
                    occurred_at.isoformat(timespec="seconds"),
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_last_log_for_plate(self, plate_key: str) -> AccessLogEntry | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM access_log WHERE plate_key = ? ORDER BY occurred_at DESC, id DESC LIMIT 1",
                (plate_key,),
            ).fetchone()
        return AccessLogEntry.from_row(row) if row else None

    def query_logs(
        self,
        plate_key: str | None = None,
        person_id: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[AccessLogEntry]:
        clauses, values = [], []
        if plate_key:
            clauses.append("plate_key = ?")
            values.append(plate_key)
        if person_id is not None:
            clauses.append("person_id = ?")
            values.append(person_id)
        if start is not None:
            clauses.append("occurred_at >= ?")
            values.append(start.isoformat(timespec="seconds"))
        if end is not None:
            clauses.append("occurred_at <= ?")
            values.append(end.isoformat(timespec="seconds"))
        query = "SELECT * FROM access_log"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?"
        values.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(query, values).fetchall()
        return [AccessLogEntry.from_row(r) for r in rows]
